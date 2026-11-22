"""Generate the two-goal gate task and audit it using scripted policies."""

import argparse
from collections import Counter
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


def run(split, out):
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
        for form in summary["forms"].values():
            counts, n = form["correct"], form["items"]
            controls = [counts[p] for p in POLICIES if p != "code_and_goal"]
            passes = (passes and counts["screen_and_goal"] == n / 2
                      and counts["code_and_goal"] >= .75 * n and counts["code_and_goal"] > max(controls))
        summary["first_bank_decision"] = "candidate_for_pilot_preparation" if passes else "revise_items"
        # Retain the predetermined bank even on a poor cue result, so the failure is inspectable.
        if forms:
            public = out / "forms"
            public.mkdir()
            key_rows = []
            for name, items in forms.items():
                write_json(public / f"form-{name.lower()}.json", [stimulus(c, g) for c, g in items])
                for position, (case, goal) in enumerate(items, start=1):
                    key_rows.append({"form": name, "position": position, **audit_row(case, goal)})
            write_table(out / "item-key.csv", key_rows)

    write_json(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("development", "confirmation"))
    parser.add_argument("--out", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a new output directory to preserve the previous run.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.out.parent) as temporary:
        staged = Path(temporary) / "study"
        staged.mkdir()
        summary = run(args.split, staged)
        staged.rename(args.out)
    print(f"{args.split}: {summary['eligible_scenes']}/{summary['candidate_scenes']} eligible scenes")
    if "first_bank_decision" in summary:
        print(summary["first_bank_decision"])


if __name__ == "__main__":
    main()
