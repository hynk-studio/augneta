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


def safe_zone_error(states, *, config, completed):
    """Closed central square; right-endpoint tick occupancy, full window only."""
    if not 0 < config.safe_zone_half_width < config.arena_half_width:
        raise ValueError("safe zone must fit strictly inside arena")
    start, end = config.evaluation_start_step, config.evaluation_end_step
    states = list(states)
    if any(type(s.get("step")) is not int for s in states):
        raise ValueError("metric states need integer steps")
    window = [s for s in states if start < s["step"] <= end]
    valid = (completed is True and [s["step"] for s in window] == list(range(start + 1, end + 1))
             and all(isinstance(s.get("position"), (list, tuple)) and len(s["position"]) == 2
                     and all(type(v) in (int, float) and math.isfinite(v) and abs(v) <= config.arena_half_width
                             for v in s["position"])
                     for s in window))
    distances = [math.hypot(*(max(0.0, abs(v) - config.safe_zone_half_width)
                              for v in s["position"])) for s in window] if valid else []
    count = sum(d > 0 for d in distances)
    denominator = math.sqrt(2) * (config.arena_half_width - config.safe_zone_half_width)
    return {"status": "complete" if valid else "incomplete_or_invalid",
            "evaluation_window": {"start_exclusive": start, "end_inclusive": end},
            "samples": len(window), "expected_samples": end - start,
            "safe_zone_half_width": config.safe_zone_half_width,
            "boundary": "included", "normalization": "farthest_arena_corner_to_square",
            "normalization_constant": denominator,
            "evaluation_duration_s": (end - start) * config.dt_s,
            "outside_samples": count if valid else None,
            "outside_time_s": count * config.dt_s if valid else None,
            "outside_fraction": count / len(window) if valid else None,
            "normalized_outside_distance": math.fsum(distances) / len(window) / denominator if valid else None}
