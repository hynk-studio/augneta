"""Generate the two-goal gate task and audit it using scripted policies."""

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import asdict
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from augneta.config import Config
from augneta.experiment import evidence

from gate_task import (
    CONFIRMATION, CONFIRMATION_SEEDS, DEVELOPMENT, DEVELOPMENT_SEEDS, GOALS, HORIZON_TICKS,
    MIN_THROTTLE_GAP, OBSERVE_TICKS, SIDES, THROTTLE_DIVISIONS, measure_case,
)


ORDER_SEEDS = {"A": 7123, "B": 8459}
POLICIES = ("always_left", "always_right", "goal_only", "follow_code", "oppose_code",
            "screen_and_goal", "code_and_goal")


def scores(items):
    correct = Counter()
    for case, goal in items:
        answer = case["answers"][goal]
        for policy in POLICIES:
            correct[policy] += case["choices"][goal][policy] == answer
        correct["drifting_screen_and_goal"] += case["drifting_screen"][goal] == answer
    return {"items": len(items), "correct": dict(correct)}


def choose_forms(cases, layouts):
    """Choose by seed order and physical stratum. This step never inspects cue accuracy."""
    forms = {name: [] for name in ORDER_SEEDS}
    shortfalls = []
    for i, layout in enumerate(layouts):
        for j, side in enumerate(SIDES):
            stratum = sorted((c for c in cases if c["map"] == layout.name and c["flow"] == side
                              and c["reason"] == "eligible"), key=lambda c: c["seed"])
            if len(stratum) < 2:
                shortfalls.append({"map": layout.name, "current": side, "available": len(stratum)})
            for k, case in enumerate(stratum[:2]):
                goal_index = (i + j + k) % 2
                forms["A"].append((case, GOALS[goal_index]))
                forms["B"].append((case, GOALS[1 - goal_index]))
    if shortfalls:
        return {}, shortfalls
    for name, order_seed in ORDER_SEEDS.items():
        random.Random(order_seed).shuffle(forms[name])
    return forms, []


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_table(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def audit_row(case, goal):
    return {
        "map": case["map"], "seed": case["seed"], "goal": goal, "eligibility": case["reason"],
        "current_at_choice": case["flow"], "code_direction": case["signal_direction"],
        "left_min_throttle_step": case["thrust"]["left"], "right_min_throttle_step": case["thrust"]["right"],
        "left_marker_crosses": case["hits"]["left"], "right_marker_crosses": case["hits"]["right"],
        "answer": (case["answers"] or {}).get(goal), **case["choices"][goal],
        "drifting_screen_and_goal": case["drifting_screen"][goal],
    }


def stimulus(case, goal):
    # This allowlist is the entire item payload used by the reviewer-facing preview.
    # The observing station is fixed throughout. No case ID, seed, choices or key is sent.
    return {"goal": goal, "geometry": case["geometry"], "signal": case["signal"]}


def write_forms(out, forms):
    public = out / "forms"
    public.mkdir()
    key_rows = []
    for name, items in forms.items():
        write_json(public / f"form-{name.lower()}.json", [stimulus(c, g) for c, g in items])
        for position, (case, goal) in enumerate(items, start=1):
            key_rows.append({"form": name, "position": position, **audit_row(case, goal)})
    write_table(out / "item-key.csv", key_rows)


def form_passes(form):
    counts, n = form["correct"], form["items"]
    controls = [counts[p] for p in POLICIES if p != "code_and_goal"]
    return (counts["screen_and_goal"] == n / 2 and counts["code_and_goal"] >= .75 * n
            and counts["code_and_goal"] > max(controls))


def substitute_blank_cues(forms, reserve):
    # The two forms contain the same scenes. Use the first eligible reserve seed in
    # the same physical stratum with a readable code, including wrong-direction codes.
    replacements, shortfalls = {}, []
    for case, _ in forms["A"]:
        if case["signal_direction"] is not None:
            continue
        key = (case["map"], case["seed"])
        match = next((c for c in reserve if c["map"] == case["map"] and c["flow"] == case["flow"]
                      and c["reason"] == "eligible" and c["signal_direction"] is not None
                      and c["seed"] not in {r["seed"] for r in replacements.values()}), None)
        if match is None:
            shortfalls.append(key)
        else:
            replacements[key] = match
    revised = {
        name: [(replacements.get((c["map"], c["seed"]), c), g) for c, g in items]
        for name, items in forms.items()
    }
    return revised, replacements, shortfalls


def screen_lookup_ceiling(items, include_status):
    # For each identical visible input, the best memorized rule chooses its majority answer.
    cells = defaultdict(Counter)
    for case, goal in items:
        key = (case["map"], goal)
        if include_status:
            key += tuple(case["signal"][k] for k in ("uncertainty_level", "age_steps", "dropped", "sensor_status"))
        cells[key][case["answers"][goal]] += 1
    return sum(max(counts.values()) for counts in cells.values())


def prepare_first_bank(forms, out, original_passed):
    out.mkdir()
    needed = {c["map"] for c, _ in forms["A"] if c["signal_direction"] is None}
    reserve = [measure_case(layout, layout.first_seed + 1000 + offset)
               for layout in CONFIRMATION if layout.name in needed
               for offset in range(CONFIRMATION_SEEDS)]
    if reserve:
        write_table(out / "reserve-candidates.csv", [audit_row(c, g) for c in reserve for g in GOALS])
    revised, replacements, shortfalls = substitute_blank_cues(forms, reserve)
    form_scores = {name: scores(items) for name, items in revised.items()}
    passed = original_passed and not shortfalls and all(form_passes(s) for s in form_scores.values())
    status = {
        **evidence("synthetic"), "reserve_candidates": len(reserve),
        "reserve_reasons": dict(Counter(c["reason"] for c in reserve)),
        "reserve_eligible_by_map_and_current_with_readable_code": {
            name: {side: sum(c["map"] == name and c["flow"] == side and c["reason"] == "eligible"
                             and c["signal_direction"] is not None for c in reserve) for side in SIDES}
            for name in sorted(needed)
        },
        "replacements": [{"map": name, "original_seed": seed, "reserve_seed": case["seed"]}
                         for (name, seed), case in replacements.items()],
        "unfilled": shortfalls, "forms": form_scores,
        "descriptive_lookup_ceiling_correct": {
            name: {"geometry_and_goal": screen_lookup_ceiling(items, False),
                   "geometry_goal_and_status": screen_lookup_ceiling(items, True)}
            for name, items in revised.items()
        },
        "decision": "candidate_for_pilot_preparation" if passed else "revise_items",
    }
    if not shortfalls:
        write_forms(out, revised)
    write_json(out / "summary.json", status)
    return status


def run(split, out, prepare_bank=False):
    confirm = split == "confirmation"
    layouts, n_seeds = (CONFIRMATION, CONFIRMATION_SEEDS) if confirm else (DEVELOPMENT, DEVELOPMENT_SEEDS)
    cases = [measure_case(layout, seed) for layout in layouts
             for seed in range(layout.first_seed, layout.first_seed + n_seeds)]
    eligible = [case for case in cases if case["reason"] == "eligible"]
    paired = [(case, goal) for case in eligible for goal in GOALS]
    config = Config().to_dict()
    del config["seed"]  # The candidate map and offset below supply the seed.
    summary = {
        **evidence("synthetic"), "split": split, "config_except_seed": config,
        "estimator_id": "rw-kalman-v1", "encoder_id": "polar8-v1", "component_changes": [],
        "map_layouts": [asdict(layout) for layout in layouts], "consecutive_seeds_per_map": n_seeds,
        "choice_tick": OBSERVE_TICKS, "post_choice_ticks": HORIZON_TICKS,
        "throttle_divisions": THROTTLE_DIVISIONS, "min_gap_in_grid_steps": MIN_THROTTLE_GAP,
        "candidate_scenes": len(cases), "eligible_scenes": len(eligible),
        "reasons": dict(Counter(c["reason"] for c in cases)),
        "eligible_left_right_by_map": {
            layout.name: {side: sum(c["map"] == layout.name and c["flow"] == side for c in eligible)
                          for side in SIDES} for layout in layouts
        },
        "eligible_scenes_without_a_code_direction": sum(c["signal_direction"] is None for c in eligible),
        "eligible_paired_scores": scores(paired),
    }

    write_table(out / "candidates.csv", [audit_row(case, goal) for case in cases for goal in GOALS])
    if confirm:
        forms, shortfalls = choose_forms(eligible, layouts)
        summary["shortfalls"] = shortfalls
        summary["form_order_seeds"] = ORDER_SEEDS
        summary["forms"] = {name: scores(items) for name, items in forms.items()}
        primary = summary["eligible_paired_scores"]
        passes = bool(forms) and primary["correct"]["code_and_goal"] >= .75 * primary["items"]
        passes = passes and all(form_passes(form) for form in summary["forms"].values())
        summary["first_bank_decision"] = "candidate_for_pilot_preparation" if passes else "revise_items"
        # Retain the predetermined bank even on a poor cue result, so the failure is inspectable.
        if forms:
            write_forms(out, forms)
            if prepare_bank:
                prepare_first_bank(forms, out / "pilot-bank", passes)

    write_json(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("development", "confirmation"))
    parser.add_argument("--out", type=Path, required=True, help="New output directory")
    parser.add_argument("--prepare-bank", action="store_true", help="Prepare the scored forms using the fresh reserve rule")
    args = parser.parse_args()
    if args.prepare_bank and args.split != "confirmation":
        parser.error("--prepare-bank applies to confirmation forms")
    if args.out.exists():
        parser.error("Choose a new output directory to preserve the previous run.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.out.parent) as temporary:
        staged = Path(temporary) / "study"
        staged.mkdir()
        summary = run(args.split, staged, args.prepare_bank)
        staged.rename(args.out)
    print(f"{args.split}: {summary['eligible_scenes']}/{summary['candidate_scenes']} eligible scenes")
    if "first_bank_decision" in summary:
        print("Initial bank:", summary["first_bank_decision"])
    if args.prepare_bank and summary.get("forms"):
        pilot = json.loads((args.out / "pilot-bank/summary.json").read_text())
        print("Scored forms:", pilot["decision"])


if __name__ == "__main__":
    main()
