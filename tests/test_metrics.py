import math

import pytest

from augneta.metrics import tracking_error


def test_metric_matches_independent_three_four_five_example():
    states = [
        {"step": 0, "position": [100, 100], "target": [0, 0]},  # excluded
        {"step": 1, "position": [3, 4], "target": [0, 0]},  # squared error 25
        {"step": 2, "position": [0, 0], "target": [0, 0]},  # squared error 0
        {"step": 3, "position": [100, 100], "target": [0, 0]},  # excluded
    ]
    result = tracking_error(states, start_step=0, end_step=2, arena_half_width=5, completed=True)
    assert result["tracking_rmse"] == pytest.approx(math.sqrt(12.5))
    assert result["normalization_constant"] == pytest.approx(math.sqrt(10**2 + 10**2))
    assert result["normalized_tracking_rmse"] == pytest.approx(0.25)
    assert result["samples"] == 2


@pytest.mark.parametrize("steps", [[], [1], [2, 1], [1, 1, 2]])
def test_missing_or_duplicate_samples_invalidate_score(steps):
    states = [{"step": step, "position": [0, 0], "target": [1, 0]} for step in steps]
    result = tracking_error(states, start_step=0, end_step=2, arena_half_width=1, completed=True)
    assert result["normalized_tracking_rmse"] is None
    assert result["status"] == "incomplete_or_invalid"


def test_nonfinite_data_and_bad_normalization_do_not_pass():
    states = [{"step": 1, "position": [float("inf"), 0], "target": [0, 0]}]
    assert tracking_error(states, start_step=0, end_step=1, arena_half_width=1, completed=True)["tracking_rmse"] is None
    with pytest.raises(ValueError):
        tracking_error(states, start_step=0, end_step=1, arena_half_width=0, completed=True)


@pytest.mark.parametrize("position", [[], [1], [1, 2, 3], [True, 0], "12"])
def test_invalid_vector_shapes_cannot_receive_zero_error(position):
    result = tracking_error([{"step": 1, "position": position, "target": [0, 0]}],
                            start_step=0, end_step=1, arena_half_width=1, completed=True)
    assert result["tracking_rmse"] is None
