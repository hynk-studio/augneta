import csv
from collections import Counter
import json
from pathlib import Path

from augneta.config import Config

from gate_task import (CONFIRMATION, CONFIRMATION_SEEDS, DEVELOPMENT, DEVELOPMENT_SEEDS, GOALS,
                       crosses_disk, decisions, grade, opposite, physical_outcomes)
from run_study import screen_lookup_ceiling, substitute_blank_cues


ROOT = Path(__file__).parent


def test_physics_and_ambiguous_outcomes():
    assert crosses_disk((-1, 0), (1, 0), (0, 0), .1)
    assert not crosses_disk((-1, .2), (1, .2), (0, 0), .1)
    flow, thrust, hits = physical_outcomes(Config(flow_strength=0), DEVELOPMENT[0].geometry())
    assert flow is None and thrust["left"] == thrust["right"] and not any(hits.values())
    assert grade(flow, thrust, hits)[0] is None
    assert grade("right", {"left": 8, "right": 2}, {"left": False, "right": False})[0] is None
    assert grade("right", {"left": 8, "right": 2}, {"left": True, "right": True})[0] is None
    assert grade("right", {"left": 8, "right": 2}, {"left": True, "right": False})[0] == {
        "reach": "right", "release": "left"
    }


def test_policy_uses_channels_and_goal_separately():
    geo = DEVELOPMENT[0].geometry()
    trail = [geo["center"]] * 3
    for active_slot, direction in ((0, "right"), (4, "left")):
        channels = [0] * 8
        channels[active_slot] = .5
        both = [decisions(g, geo, {"channels": channels}, trail, .05, 1.2) for g in GOALS]
        assert [p["code_and_goal"] for p in both] == [direction, opposite(direction)]
        assert [p["follow_code"] for p in both] == [direction] * 2
        assert [p["screen_and_goal"] for p in both] == ["right", "left"]


def test_reserve_does_not_select_for_correct_cue():
    original = {"map": "test", "seed": 1, "flow": "left", "signal_direction": None}
    # A readable but inaccurate signal is the first eligible reserve, and must be kept.
    reserve = [dict(original, seed=2, reason="eligible", signal_direction="right"),
               dict(original, seed=3, reason="eligible", signal_direction="left")]
    forms = {"A": [(original, "reach")], "B": [(original, "release")]}
    fixed, _, missing = substitute_blank_cues(forms, reserve)
    assert not missing
    assert fixed == {"A": [(reserve[0], "reach")], "B": [(reserve[0], "release")]}
    assert substitute_blank_cues(forms, [])[2] == [("test", 1)]


def test_split_and_form_balance_and_public_projection():
    dev = {m.first_seed + i for m in DEVELOPMENT for i in range(DEVELOPMENT_SEEDS)}
    confirm = {m.first_seed + i for m in CONFIRMATION for i in range(CONFIRMATION_SEEDS)}
    reserve = {m.first_seed + 1000 + i for m in CONFIRMATION for i in range(CONFIRMATION_SEEDS)}
    assert len(dev) == 96 and len(confirm) == 320 and dev.isdisjoint(confirm)
    assert reserve.isdisjoint(confirm | dev)
    with (ROOT / "results/item-key.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    forms = {}
    for name in ("A", "B"):
        public = json.loads((ROOT / "preview" / f"form-{name.lower()}.json").read_text())
        key = [r for r in rows if r["form"] == name]
        assert len(key) == len(public) == 16
        assert len({r["seed"] for r in key}) == 16
        assert len({(r["map"], r["goal"], r["answer"]) for r in key}) == 16
        assert set(Counter((r["goal"], r["current_at_choice"]) for r in key).values()) == {4}
        by_seed = {}
        for position, (item, r) in enumerate(zip(public, key), 1):
            assert set(item) == {"goal", "geometry", "signal"}
            assert set(item["geometry"]) == {"left", "right", "center", "radius"}
            assert set(item["signal"]) == {"channels", "age_steps", "dropped", "sensor_status", "uncertainty_level"}
            assert r["goal"] == item["goal"] and int(r["position"]) == position
            assert r["code_direction"] and len(item["signal"]["channels"]) == 8
            by_seed[r["seed"]] = (item, r["answer"])
        forms[name] = by_seed
    assert forms["A"].keys() == forms["B"].keys()
    for seed, (a, answer) in forms["A"].items():
        b, other_answer = forms["B"][seed]
        assert a["geometry"] == b["geometry"] and a["signal"] == b["signal"]
        assert a["goal"] != b["goal"] and answer == opposite(other_answer)

def test_screen_lookup_ceiling_counts_only_indistinguishable_inputs():
    def case(answer, age):
        return {"map": "same", "answers": {"reach": answer},
                "signal": {"uncertainty_level": 1, "age_steps": age,
                           "dropped": False, "sensor_status": "held"}}
    items = [(case("left", 4), "reach"), (case("right", 4), "reach"), (case("right", 8), "reach")]
    assert screen_lookup_ceiling(items, False) == 2
    assert screen_lookup_ceiling(items, True) == 2
    items.append((case("left", 4), "reach"))
    assert screen_lookup_ceiling(items, False) == 2
    assert screen_lookup_ceiling(items, True) == 3
