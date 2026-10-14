from dataclasses import fields, replace
import inspect
import math

import pytest

from augneta.estimation import Belief, CausalEstimator, SensorObservation
from augneta.experiment import ChangeEvent, MAIN_CONDITIONS, Trial, synthetic_action
from augneta.feedback import Encoder
from augneta.simulation import World


def run_actions(trial):
    records, truths = [], []
    while not trial.complete:
        action = (math.sin(trial.step / 3), -0.35)
        record, truth = trial.advance(action)
        records.append(record)
        truths.append(truth)
    return records, truths, trial.summary()


@pytest.mark.parametrize("condition", MAIN_CONDITIONS)
def test_same_seed_config_actions_reproduce_every_field(config, condition):
    assert run_actions(Trial(config, condition)) == run_actions(Trial(config, condition))
    assert run_actions(Trial(config, condition))[1] != run_actions(Trial(replace(config, seed=8), condition))[1]


def test_main_conditions_apply_identical_direct_actions(config):
    runs = [run_actions(Trial(config, condition))[0] for condition in MAIN_CONDITIONS]
    for steps in zip(*runs):
        assert all(s["visible_after"] == steps[0]["visible_after"] for s in steps)
        for record in steps:
            assert record["action"] == record["applied_action"]
            assert record["action"] == [math.sin(record["step"] / 3), -0.35]
    assert all(r["intended_feedback"] is None for r in runs[0])


def test_boundary_collision_stops_normal_velocity(config):
    world = World(replace(config, flow_strength=0))
    for _ in range(200):
        state = world.advance((1, 0))
        assert abs(state.position[0]) <= config.arena_half_width
    assert state.position == (config.arena_half_width, 0.0)
    assert state.velocity == (0.0, 0.0)


def test_delayed_kalman_uses_measurement_time_then_predicts():
    estimator = CausalEstimator(0.1, 0.5)
    result = estimator.update(10, [SensorObservation(0, 10, (1.0, 2.0), False)])
    # Independent scalar update: prior=1, R=.25, K=.8, posterior=.2;
    # the ten-tick delay adds .04 * 1 second of random-walk variance.
    assert result.mean == pytest.approx((0.8, 1.6))
    assert result.variance == pytest.approx(0.24)
    assert result.last_sample_step == 0
    no_delay = CausalEstimator(0.1, 0.5)
    no_delay.update(0, [SensorObservation(0, 0, (1.0, 2.0), False)])
    assert no_delay.update(10, []).variance == pytest.approx(result.variance)


def test_future_batch_rejected_before_any_state_change():
    estimator = CausalEstimator(0.1, 0.5)
    with pytest.raises(ValueError, match="future"):
        estimator.update(2, [SensorObservation(0, 0, (5, 5), False),
                             SensorObservation(3, 3, (8, 8), False)])
    result = estimator.update(2, [])
    assert result.mean == (0, 0)
    assert result.variance == pytest.approx(1.008)
    with pytest.raises(ValueError, match="monotonically"):
        estimator.update(2, [])
    with pytest.raises(ValueError, match="timestamps"):
        SensorObservation(5, 4, (1, 1), False)


def test_late_out_of_order_samples_explicitly_ignored():
    estimator = CausalEstimator(0.05, 0.2)
    first = estimator.update(8, [SensorObservation(6, 8, (1, 0), False)])
    late = estimator.update(9, [SensorObservation(2, 9, (-100, 0), False)])
    assert late.ignored_stale == 1
    assert late.mean == first.mean
    assert late.variance > first.variance


def test_sensor_delay_retains_original_sample_and_noise(config):
    delayed = World(config)
    instant = World(replace(config, sensor_delay_steps=0))
    original = {}
    delivered_count = 0
    for step in range(config.steps):
        for observation in instant.observations():
            original[step] = observation
        for observation in delayed.observations():
            source = original[observation.sample_step]
            assert step == observation.available_step == source.sample_step + config.sensor_delay_steps
            assert observation.value == source.value
            assert observation.dropped == source.dropped
            delivered_count += 1
        delayed.advance((0, 0))
        instant.advance((0, 0))
    assert delivered_count == 9


def test_missing_observations_remain_explicit_and_uncertain(config):
    trial = Trial(replace(config, sensor_dropout_probability=1), "dashboard")
    records, _, _ = run_actions(trial)
    assert all(r["belief"]["mean"] == [0.0, 0.0] for r in records)
    assert records[-1]["belief"]["variance"] > records[0]["belief"]["variance"]
    assert records[0]["belief"]["sensor_status"] == "waiting"
    assert records[4]["belief"]["sensor_status"] == "dropout"
    assert records[4]["feedback_packet"]["dropped"]
    assert records[-1]["belief"]["last_sample_step"] is None
    for record in records:
        assert all(o["value"] is None and o["dropped"] for o in record["sensor_observations"])


def test_observation_boundary_and_encoder_have_no_truth_target_or_future(config, monkeypatch):
    assert {f.name for f in fields(SensorObservation)} == {"sample_step", "available_step", "value", "dropped"}
    observation = SensorObservation(0, 0, (0.5, -0.4), False)
    for forbidden in ("ground_truth", "flow", "target", "seed", "future", "world"):
        assert not hasattr(observation, forbidden)
        assert not hasattr(CausalEstimator(0.05, 0.2), forbidden)
    assert list(inspect.signature(Encoder.encode).parameters) == ["self", "belief"]
    monkeypatch.setattr(World, "observations", lambda world: (observation,) if world.step == 0 else ())
    one = Trial(config, "dashboard")
    two = Trial(replace(config, seed=987, flow_strength=20, target_radius=0.9), "dashboard")
    # Different hidden worlds and targets, exactly equal permitted observations.
    assert one.view()["feedback"] == two.view()["feedback"]
    assert set(one.view()) == {"visible", "condition", "diagnostic", "complete", "feedback"}
    assert set(one.view()["visible"]) == {"step", "time_s", "position", "velocity", "target"}


def test_matched_packet_timing_uncertainty_dropouts_and_quantization(config):
    dashboard = Trial(config, "dashboard")
    preview = Trial(config, "sensory_preview")
    previous = None
    while not dashboard.complete:
        packet = dashboard.view()["feedback"]
        assert packet == preview.view()["feedback"]
        if dashboard.step % config.feedback_period_steps:
            assert packet == previous
        assert packet["emitted_step"] <= dashboard.step
        assert packet["magnitude_level"] in range(5)
        assert packet["uncertainty_level"] in range(9)
        previous = packet
        action = (0.4, -0.7)
        dashboard.advance(action)
        preview.advance(action)


def test_environmental_direction_and_zero_magnitude_code():
    encoder = Encoder()
    packet = encoder.encode(Belief(0, (1.5, 0), 0.0625, 0, "fresh", False, 0, "test"))
    assert packet.direction_bin == 0  # Eastward environmental force, not a westward action.
    assert packet.magnitude_level == 4
    assert packet.uncertainty_level == 1
    assert packet.channels == (1, 0, 0, 0, 0, 0, 0, 0)
    zero = encoder.encode(Belief(0, (-0.01, 0.01), 1, None, "waiting", False, 0, "test"))
    assert zero.magnitude_level == zero.direction_bin == 0
    assert zero.channels == (0,) * 8


def test_estimator_update_preserves_external_semantic_code(config):
    updated = Trial(config, "dashboard", changes=[ChangeEvent(8, "estimator", "rw-kalman-v2")])
    records, _, _ = run_actions(updated)
    assert records[7]["belief"]["estimator_id"] == "rw-kalman-v1"
    assert records[8]["belief"]["estimator_id"] == "rw-kalman-v2"
    assert {r["feedback_packet"]["encoder_id"] for r in records} == {"polar8-v1"}
    assert {r["feedback_packet"]["channel_offset"] for r in records} == {0}
    same_belief = Belief(8, (0, 1.5), 0.1, 4, "fresh", False, 0, "rw-kalman-v1")
    old = Encoder().encode(same_belief)
    new = Encoder().encode(replace(same_belief, estimator_id="rw-kalman-v2"))
    assert (old.direction_bin, old.channels, old.magnitude_level) == (new.direction_bin, new.channels, new.magnitude_level)


def test_synthetic_policy_only_uses_public_view(config):
    one = Trial(config, "dashboard")
    two = Trial(config, "sensory_preview")
    while not one.complete:
        action = synthetic_action(one.view(), config.control_gain)
        assert action == synthetic_action(two.view(), config.control_gain)
        one.advance(action)
        two.advance(action)
    assert one.summary()["normalized_tracking_rmse"] == two.summary()["normalized_tracking_rmse"]


@pytest.mark.parametrize("action", [(float("nan"), 0), (2, 0), (0,), (True, 0), "left"])
def test_invalid_actions_do_not_advance_trial(config, action):
    trial = Trial(config, "none")
    with pytest.raises(ValueError):
        trial.advance(action)
    assert trial.step == 0
