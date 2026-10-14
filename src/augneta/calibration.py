"""Reproducible code-identification plans and descriptive confusion counts.

This module neither presents stimuli nor collects participant records. Plan
answers are operator-only material; never expose them to a blinded response UI.
"""

import hashlib
import random

from .config import canonical
from .haptics import OutputProfile


def calibration_plan(seed=7, blocks=2, profile=None):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be in [0, 2**32)")
    if type(blocks) is not int or not 1 <= blocks <= 20:
        raise ValueError("blocks must be an integer in [1, 20]")
    rng = random.Random(seed)
    profile = profile or OutputProfile()
    trials = []
    for block in range(blocks):
        # Balanced counts within each block; random ordering, NOT a claim of
        # participant-order counterbalancing or perceptual equivalence.
        codes = [(channel, level) for channel in range(8) for level in range(1, 5)]
        codes += [(None, 0)] * 4
        rng.shuffle(codes)
        for channel, level in codes:
            trials.append({"trial_id": len(trials) + 1, "block": block + 1,
                           "channel": channel, "level": level})
    plan = {"schema_version": 1, "kind": "unadministered_identification_plan",
            "code_id": "logical-eight-channel-four-level-v1", "seed": seed,
            "blocks": blocks, "trials": trials, "output_profile": profile.to_dict(),
            "output_profile_sha256": profile.identity,
            "human_evidence": False, "hardware_verified": False}
    return {**plan, "plan_sha256": hashlib.sha256(canonical(plan).encode()).hexdigest()}


def score_responses(plan, responses):
    """Count errors/missing trials without estimating learning or declaring pass.

    The caller must label response provenance. Omitted trials are missing;
    null choices in an existing record are explicit 'cannot identify' answers.
    A zero catch is correct only for channel=None and level=0.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    profile = OutputProfile.from_dict(plan.get("output_profile"))
    if canonical(plan) != canonical(calibration_plan(plan.get("seed"), plan.get("blocks"), profile)):
        raise ValueError("plan content or identity mismatch")
    if not isinstance(responses, list):
        raise ValueError("responses must be a list")
    known = {trial["trial_id"]: trial for trial in plan["trials"]}
    by_id = {}
    for response in responses:
        if not isinstance(response, dict) or set(response) != {"trial_id", "channel", "level"}:
            raise ValueError("response needs trial_id, channel, and level only")
        trial_id = response["trial_id"]
        if type(trial_id) is not int or trial_id not in known or trial_id in by_id:
            raise ValueError("unknown or duplicate response trial")
        for key, upper in (("channel", 7), ("level", 4)):
            value = response[key]
            if value is not None and (type(value) is not int or not 0 <= value <= upper):
                raise ValueError(f"invalid response {key}")
        by_id[trial_id] = response
    direction = [[0] * 9 for _ in range(8)]  # ninth column: cannot identify
    magnitude = [[0] * 6 for _ in range(5)]  # sixth column: cannot identify
    correct = 0
    catches = 0
    false_positives = 0
    for trial_id, response in by_id.items():
        expected = known[trial_id]
        channel, level = response["channel"], response["level"]
        if expected["channel"] is not None:
            direction[expected["channel"]][channel if channel is not None else 8] += 1
        else:
            catches += 1
            false_positives += int(channel is not None or (level is not None and level > 0))
        magnitude[expected["level"]][level if level is not None else 5] += 1
        correct += int((channel, level) == (expected["channel"], expected["level"]))
    return {"plan_sha256": plan["plan_sha256"], "planned_trials": len(known),
            "answered_trials": len(by_id), "missing_trials": len(known) - len(by_id),
            "complete": len(by_id) == len(known), "correct_trials": correct,
            "joint_accuracy_answered": correct / len(by_id) if by_id else None,
            "joint_accuracy_planned": correct / len(known),
            "direction_confusion": direction, "magnitude_confusion": magnitude,
            "answered_catch_trials": catches, "catch_false_positives": false_positives,
            "inference": "descriptive_only_no_learning_or_acceptance_claim"}
