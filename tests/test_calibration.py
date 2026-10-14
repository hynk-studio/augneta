from collections import Counter
from copy import deepcopy
import json

import pytest

from augneta.calibration import calibration_plan, score_responses
from augneta.cli import main


def test_balanced_randomized_plan_includes_silence():
    plan = calibration_plan(7, 2)
    assert plan == calibration_plan(7, 2)
    assert plan["trials"] != calibration_plan(8, 2)["trials"]
    assert len(plan["trials"]) == 72
    for block in (1, 2):
        counts = Counter((t["channel"], t["level"]) for t in plan["trials"] if t["block"] == block)
        assert counts.pop((None, 0)) == 4
        assert counts == Counter({(channel, level): 1 for channel in range(8) for level in range(1, 5)})
    assert plan["kind"] == "unadministered_identification_plan"
    assert not plan["human_evidence"] and not plan["hardware_verified"]


def test_confusion_counts_errors_unknowns_and_missing_separately():
    plan = calibration_plan(7, 1)
    ids = {(t["channel"], t["level"]): t["trial_id"] for t in plan["trials"]}
    responses = [
        {"trial_id": ids[(0, 1)], "channel": 0, "level": 1},  # correct
        {"trial_id": ids[(1, 2)], "channel": 2, "level": 3},  # two confusions
        {"trial_id": ids[(3, 4)], "channel": None, "level": None},  # cannot identify
        {"trial_id": ids[(None, 0)], "channel": 5, "level": 1},  # false positive
    ]
    score = score_responses(plan, responses)
    assert score["answered_trials"] == 4 and score["missing_trials"] == 32
    assert score["correct_trials"] == 1 and not score["complete"]
    assert score["joint_accuracy_answered"] == 0.25
    assert score["joint_accuracy_planned"] == 1 / 36
    assert score["direction_confusion"][0][0] == 1
    assert score["direction_confusion"][1][2] == 1
    assert score["direction_confusion"][3][8] == 1
    assert sum(map(sum, score["direction_confusion"])) == 3
    assert score["magnitude_confusion"][2][3] == 1
    assert score["magnitude_confusion"][4][5] == 1
    assert score["magnitude_confusion"][0][1] == 1
    assert sum(map(sum, score["magnitude_confusion"])) == 4
    assert score["answered_catch_trials"] == score["catch_false_positives"] == 1


def test_empty_is_not_a_pass_and_zero_catches_have_no_direction():
    plan = calibration_plan(7, 1)
    empty = score_responses(plan, [])
    assert empty["joint_accuracy_answered"] is None
    assert empty["missing_trials"] == 36 and not empty["complete"]
    catches = [{"trial_id": t["trial_id"], "channel": None, "level": 0}
               for t in plan["trials"] if t["level"] == 0]
    result = score_responses(plan, catches)
    assert result["correct_trials"] == 4
    assert result["catch_false_positives"] == 0
    assert sum(map(sum, result["direction_confusion"])) == 0
    assert result["inference"] == "descriptive_only_no_learning_or_acceptance_claim"


@pytest.mark.parametrize("responses", [
    [{"trial_id": 999, "channel": 0, "level": 1}],
    [{"trial_id": True, "channel": 0, "level": 1}],
    [{"trial_id": 1, "channel": 8, "level": 1}],
    [{"trial_id": 1, "channel": 0, "level": -1}],
    [{"trial_id": 1, "channel": 0, "level": True}],
    [{"trial_id": 1, "channel": 0, "level": 1, "name": "do not collect"}],
    [{"trial_id": 1, "channel": 0, "level": 1}] * 2,
])
def test_invalid_and_duplicate_responses_are_not_counted(responses):
    with pytest.raises(ValueError):
        score_responses(calibration_plan(), responses)


def test_edited_answer_key_or_profile_rejected():
    plan = calibration_plan()
    for change in ("answer", "profile", "evidence", "type"):
        changed = deepcopy(plan)
        if change == "answer":
            changed["trials"][0]["level"] = 99
        elif change == "profile":
            changed["output_profile"]["profile_id"] = "different-placement"
        elif change == "evidence":
            changed["human_evidence"] = True
        else:
            changed["trials"][0]["trial_id"] = 1.0
        with pytest.raises(ValueError):
            score_responses(changed, [])


@pytest.mark.parametrize("seed, blocks", [(True, 2), (-1, 2), (7, 0), (7, 21), (7, 1.5)])
def test_plan_rejects_invalid_sizes(seed, blocks):
    with pytest.raises(ValueError):
        calibration_plan(seed, blocks)


def test_plan_cli_writes_no_fake_participant_responses(tmp_path, capsys):
    directory = tmp_path / "plan"
    arguments = ["calibration-plan", "--out", str(directory), "--seed", "8", "--blocks", "1"]
    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["planned_trials"] == 36 and result["responses_collected"] == 0
    assert json.loads((directory / "responses.json").read_text()) == []
    assert json.loads((directory / "plan.json").read_text()) == calibration_plan(8, 1)
    assert main(arguments) == 2
    assert json.loads((directory / "responses.json").read_text()) == []
