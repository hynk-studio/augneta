from dataclasses import replace
import json
import math

import pytest

from augneta.cli import main
from augneta.estimation import Belief
from augneta.feedback import Encoder
from augneta.haptic_bench import run_haptic_smoke
from augneta.haptics import MockOutput, OutputProfile, render_frame


def packet(step=0, encoder="polar8-v1"):
    return Encoder(encoder).encode(Belief(step, (0.75, 0.0), 0.25, 0,
                                         "held", False, 0, "rw-kalman-v1")).to_dict()


def test_calibration_and_rotation_preserve_semantics():
    profile = OutputProfile(actuator_count=16, channel_map=(7, 8, 9, 10, 11, 12, 13, 14),
                            levels=((0.0, 0.1, 0.3, 0.6, 0.8),) * 8)
    source = packet(4, "polar8-rotated-v1")
    frame = render_frame(source, profile)
    # East, magnitude two, encoder rotation +2, then physical slot nine.
    assert frame["actuator_levels"] == [0.0] * 9 + [0.3] + [0.0] * 6
    assert frame["feedback_packet"] == source
    assert frame["feedback_packet"]["direction_bin"] == 0
    assert OutputProfile.from_dict(profile.to_dict()) == profile
    assert profile.identity != OutputProfile().identity
    frame["feedback_packet"]["channels"][2] = 0
    assert source["channels"][2] == 0.5


@pytest.mark.parametrize("changes", [
    {"channel_map": (0,) * 8}, {"channel_map": tuple(range(1, 9))},
    {"actuator_count": 2}, {"actuator_count": True},
    {"levels": ((0, 0.1, 0.1, 0.5, 1),) * 8},
    {"levels": ((0, 0.1, 0.2, 0.5, math.nan),) * 8},
    {"levels": ((0, 0.1, 0.2, 0.5, 1.1),) * 8},
    {"levels": ((0.1, 0.2, 0.3, 0.5, 1),) * 8},
    {"pulse_ms": 0}, {"pulse_ms": 251}, {"max_packet_age_ms": 1001},
])
def test_invalid_profiles_rejected(changes):
    with pytest.raises(ValueError):
        replace(OutputProfile(), **changes)


@pytest.mark.parametrize("changes", [
    {"target": [0, 0]}, {"truth": [1, 1]}, {"action": [1, 0]},
    {"estimator_id": "oracle-truth-v1"}, {"channel_offset": 2},
    {"channels": [True, 0, 0, 0, 0, 0, 0, 0]},
    {"channels": [math.nan] * 8}, {"direction_bin": True},
    {"last_sample_step": 5}, {"age_steps": 99}, {"delayed": 1},
])
def test_malformed_packet_disarms(changes):
    output = MockOutput()
    epoch = output.arm(0)
    output.deliver(packet(), emitted_at_ms=0, now_ms=0, epoch=epoch)
    with pytest.raises((ValueError, TypeError)):
        output.deliver({**packet(4), **changes}, emitted_at_ms=10, now_ms=10, epoch=epoch)
    assert not output.armed and output.active_frame is None
    assert output.events[-1]["actuator_levels"] == [0.0] * 8


def test_stop_disconnect_epoch_and_no_implicit_resume():
    output = MockOutput()
    assert output.deliver(packet(), emitted_at_ms=0, now_ms=0, epoch=0)["kind"] == "rejected_session"
    old_epoch = output.arm(0)
    output.deliver(packet(), emitted_at_ms=0, now_ms=0, epoch=old_epoch)
    output.stop(20, "disconnect")
    assert output.active_frame is None
    assert output.deliver(packet(4), emitted_at_ms=30, now_ms=30, epoch=old_epoch)["kind"] == "rejected_session"
    new_epoch = output.arm(40)
    assert new_epoch != old_epoch
    assert output.deliver(packet(4), emitted_at_ms=40, now_ms=40, epoch=old_epoch)["kind"] == "rejected_session"
    assert output.active_frame is None
    assert output.deliver(packet(), emitted_at_ms=40, now_ms=40, epoch=new_epoch)["kind"] == "command"
    output.stop(50, "pause")
    output.tick(1000)
    assert not output.armed and output.active_frame is None


def test_duplicate_does_not_extend_pulse_and_expiry_clears_mirror():
    output = MockOutput()
    epoch = output.arm(0)
    event = output.deliver(packet(), emitted_at_ms=0, now_ms=0, epoch=epoch)
    assert event["expires_at_ms"] == 100
    assert output.deliver(packet(), emitted_at_ms=0, now_ms=90, epoch=epoch)["kind"] == "rejected_order"
    assert output.active_frame is not None
    output.tick(100)
    assert output.active_frame is None
    assert output.events[-1]["kind"] == "expired"
    assert output.events[-1]["actuator_levels"] == [0.0] * 8


def test_packet_freshness_is_not_age_of_the_sensor_sample():
    output = MockOutput()
    epoch = output.arm(0)
    # Old observation in a newly emitted, causal estimate remains valid.
    source = packet(100)
    assert source["age_steps"] == 100
    assert output.deliver(source, emitted_at_ms=5000, now_ms=5000, epoch=epoch)["kind"] == "command"
    # A newer *packet* delayed 250 ms is rejected, without replaying a queue.
    assert output.deliver(packet(104), emitted_at_ms=5200, now_ms=5450, epoch=epoch)["kind"] == "rejected_stale"
    assert output.active_frame is None
    # Relabelling the same stale step as newly arrived cannot rescue it.
    assert output.deliver(packet(104), emitted_at_ms=5450, now_ms=5450, epoch=epoch)["kind"] == "rejected_order"
    event = output.deliver(packet(108), emitted_at_ms=5460, now_ms=5680, epoch=epoch)
    assert event["expires_at_ms"] == 5710  # truncated by freshness deadline
    output.tick(5710)
    assert output.active_frame is None


@pytest.mark.parametrize("time", [-1, math.nan, math.inf, True])
def test_invalid_clock_rejected(time):
    output = MockOutput()
    epoch = output.arm(0)
    output.deliver(packet(), emitted_at_ms=0, now_ms=0, epoch=epoch)
    with pytest.raises(ValueError):
        output.tick(time)
    assert not output.armed and output.active_frame is None


def test_clock_rollback_stops_output():
    output = MockOutput()
    epoch = output.arm(50)
    output.deliver(packet(), emitted_at_ms=50, now_ms=50, epoch=epoch)
    with pytest.raises(ValueError):
        output.tick(49)
    assert not output.armed and output.active_frame is None


def test_future_emission_disarms_and_ack_fields_never_claim_hardware():
    output = MockOutput()
    epoch = output.arm(0)
    event = output.deliver(packet(), emitted_at_ms=0, now_ms=0, epoch=epoch)
    assert event["clock_domain"] == "synthetic_ms"
    assert event["mock_accepted_at_ms"] == 0
    assert all(event[key] is None for key in (
        "transport_acknowledged_at_ms", "device_acknowledged_at_ms", "measured_onset_ms"))
    event["frame"]["actuator_levels"][0] = 1
    assert output.active_frame["actuator_levels"][0] == 0.5
    with pytest.raises(ValueError):
        output.deliver(packet(4), emitted_at_ms=11, now_ms=10, epoch=epoch)
    assert not output.armed and output.active_frame is None


def test_real_trial_to_output_and_replay(tmp_path, config):
    directory = tmp_path / "bench"
    result = run_haptic_smoke(directory, config)
    assert result["steps"] == 40
    assert result["command_count"] == result["shared_packet_checks"] == 10
    assert result["tracking_replay_verified"] and result["final_output_stopped"]
    assert result["participant_kind"] == "synthetic"
    assert not result["human_evidence"] and not result["hardware_verified"]
    assert result["physical_timing_measurements"] == 0
    events = [json.loads(line) for line in (directory / "output_events.jsonl").read_text().splitlines()]
    trace = [json.loads(line) for line in (directory / "tracking/trace.jsonl").read_text().splitlines()]
    commands = [event for event in events if event["kind"] == "command"]
    for command in commands:
        packet_value = command["frame"]["feedback_packet"]
        assert packet_value == trace[packet_value["emitted_step"]]["intended_feedback"]
    assert events[-1]["kind"] == "stopped"
    with pytest.raises(FileExistsError):
        run_haptic_smoke(directory, config)


def test_hardware_cli_cannot_actuate_or_create_artifacts(tmp_path, capsys):
    directory = tmp_path / "hardware"
    assert main(["haptic-smoke", "--output", "hardware", "--out", str(directory)]) == 2
    assert "physical hardware output is unavailable" in capsys.readouterr().err
    assert not directory.exists()
