"""Build fresh retention items and matched geometry probes from the P1 physics evaluator."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random

from augneta.experiment import evidence
from gate_task import GOALS, SIDES, Layout, gate_axis, measure_case, opposite, signal_direction
from run_study import stimulus, write_json

ROOT = Path(__file__).resolve().parent
RETENTION_MAPS = (
    Layout("R1", (.025, -.035), .385, -13., .150, 120000),
    Layout("R2", (-.045, -.015), .415, 9., .165, 121000),
    Layout("R3", (.04, .035), .365, 22., .145, 122000),
    Layout("R4", (-.025, .045), .440, -20., .170, 123000),
)
PROBE_MAPS = tuple(Layout(name, (0., 0.), .35, angle, .16, 140000)
                   for name, angle in (("G1", 76.), ("G2", -76.)))


def entry(case, goal):
    return {"map": case["map"], "seed": case["seed"], "item": stimulus(case, goal),
            "answer": case["answers"][goal]}


def retention():
    items, counts = [], {}
    for map_index, layout in enumerate(RETENTION_MAPS):
        cases = [measure_case(layout, layout.first_seed + i) for i in range(128)]
        available = [c for c in cases if c["reason"] == "eligible" and c["signal_direction"] is not None]
        counts[layout.name] = {side: sum(c["flow"] == side for c in available) for side in SIDES}
        for side_index, side in enumerate(SIDES):
            by_side = [c for c in available if c["flow"] == side]
            if len(by_side) < 2:
                raise ValueError(f"Too few eligible scenes in {layout.name} for {side}: {counts}")
            for i, case in enumerate(by_side[:2]):
                items.append(entry(case, GOALS[(map_index + side_index + i) % 2]))
    random.Random(17047).shuffle(items)
    return items, counts


def probes():
    available = defaultdict(list)
    for offset in range(384):
        pair = [measure_case(layout, layout.first_seed + offset) for layout in PROBE_MAPS]
        a, b = pair
        if a["signal"] != b["signal"]:
            raise ValueError("Geometry changed the available signal")
        if a["reason"] != "eligible" or b["reason"] != "eligible" or a["flow"] == b["flow"]:
            continue
        if None in (a["signal_direction"], b["signal_direction"]) or a["signal_direction"] == b["signal_direction"]:
            continue
        vertical = signal_direction(a["signal"], (0., 1.))
        if vertical is not None:
            available["up" if vertical == "right" else "down"].append(pair)
    pairs = []
    for vertical in ("up", "down"):
        if len(available[vertical]) < len(GOALS):
            raise ValueError(f"Too few matched {vertical} pairs: {len(available[vertical])}")
        for goal, pair in zip(GOALS, available[vertical]):
            pairs.append([entry(case, goal) for case in pair])
    rng = random.Random(19079)
    rng.shuffle(pairs)
    # Counterbalance the first map of each pair and vary the order of its counterpart.
    first = [pair[i % 2] for i, pair in enumerate(pairs)]
    second = [pair[1 - i % 2] for i, pair in enumerate(pairs)]
    return first + [second[i] for i in (1, 0, 3, 2)], {k: len(v) for k, v in available.items()}


def first_forms():
    with (ROOT / "results/item-key.csv").open() as stream:
        keys = {(r["form"], int(r["position"])): r for r in csv.DictReader(stream)}
    forms = {}
    for form in ("A", "B"):
        items = json.loads((ROOT / "preview" / f"form-{form.lower()}.json").read_text())
        forms[form] = [dict(item=item, **{k: keys[form, i][k] for k in ("answer", "seed", "map")})
                       for i, item in enumerate(items, 1)]
    return forms


def audit(entries):
    signal_cells, map_cells = defaultdict(Counter), defaultdict(Counter)
    counts = Counter()
    for row in entries:
        item, answer = row["item"], row["answer"]
        goal, signal, geometry = item["goal"], item["signal"], item["geometry"]
        horizontal = signal_direction(signal, (1., 0.))
        counts["horizontal_readable"] += horizontal is not None
        for name, sensed in (("horizontal_right_fallback", horizontal or "right"),
                             ("horizontal_left_fallback", horizontal or "left"),
                             ("map_signal_goal", signal_direction(signal, gate_axis(geometry)) or "right")):
            choice = sensed if goal == "reach" else opposite(sensed)
            counts[name] += choice == answer
        signal_cells[(goal, json.dumps(signal, sort_keys=True))][answer] += 1
        map_cells[(goal, row["map"])][answer] += 1
    return {"items": len(entries), **counts,
            "signal_goal_lookup_ceiling": sum(max(cell.values()) for cell in signal_cells.values()),
            "map_goal_lookup_ceiling": sum(max(cell.values()) for cell in map_cells.values())}


def build(out):
    first = first_forms()
    retest, ret_counts = retention()
    diagnostic, probe_counts = probes()
    forms = {**first, "R": retest, "G": diagnostic}
    previously_seen = {int(r["seed"]) for form in first.values() for r in form} | {710003, 710029}
    r_seeds, g_seeds = ({row["seed"] for row in seq} for seq in (retest, diagnostic))
    if previously_seen & (r_seeds | g_seeds) or r_seeds & g_seeds or (len(r_seeds), len(g_seeds)) != (16, 4):
        raise ValueError("Unexpected seed overlap")
    audit_results = {name: audit(rows) for name, rows in forms.items()}
    g = audit_results["G"]
    ready = g["signal_goal_lookup_ceiling"] == 4 and g["map_signal_goal"] >= 6
    summary = {**evidence("synthetic"), "retention_candidates": 512, "retention_available": ret_counts,
               "probe_seed_pairs_screened": 384, "probe_available_pairs": probe_counts,
               "scores": audit_results, "diagnostic_criterion_met": ready}
    write_json(out / "audit.json", summary)
    if not ready:
        raise ValueError("Diagnostic criteria were not met; inspect the audit before use.")
    write_json(out / "bank.json", {"retention": retest, "diagnostic": diagnostic})
    return summary


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--out", type=Path, required=True, help="New directory for the audit and server-side bank")
    out = args.parse_args().out
    out.mkdir(parents=True, exist_ok=False)
    print(json.dumps(build(out), indent=2))
