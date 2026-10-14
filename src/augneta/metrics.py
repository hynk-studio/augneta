"""Predeclared tracking metric; incomplete trials do not get a successful score."""

import math


def tracking_error(states, *, start_step, end_step, arena_half_width, completed):
    denominator = 2 * math.sqrt(2) * arena_half_width
    if (not math.isfinite(denominator) or denominator <= 0
            or type(start_step) is not int or type(end_step) is not int
            or not 0 <= start_step < end_step):
        raise ValueError("invalid metric window or normalization")
    states = list(states)
    if any(type(s.get("step")) is not int for s in states):
        raise ValueError("metric states need integer steps")
    window = [s for s in states if start_step < s["step"] <= end_step]
    expected_steps = list(range(start_step + 1, end_step + 1))
    valid = completed is True and [s["step"] for s in window] == expected_steps
    valid_vectors = all(
        isinstance(s.get(key), (list, tuple)) and len(s[key]) == 2
        and all(type(v) in (int, float) and math.isfinite(v) for v in s[key])
        for s in window for key in ("position", "target"))
    valid = valid and valid_vectors
    squared = [math.dist(s["position"], s["target"])**2 for s in window] if valid_vectors else []
    valid = valid and all(math.isfinite(v) for v in squared)
    rmse = math.sqrt(math.fsum(squared) / len(squared)) if valid else None
    return {"status": "complete" if valid else "incomplete_or_invalid",
            "evaluation_window": {"start_exclusive": start_step, "end_inclusive": end_step},
            "samples": len(window), "expected_samples": end_step - start_step,
            "normalization": "arena_diagonal", "normalization_constant": denominator,
            "tracking_rmse": rmse,
            "normalized_tracking_rmse": rmse / denominator if rmse is not None else None}
