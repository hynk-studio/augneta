import json

import pytest

from augneta.cli import main, run_smoke
from augneta.config import Config, canonical
from augneta.experiment import ChangeEvent, ORACLE_CONDITION, Trial, evidence
from augneta.recording import Recorder, replay


def record_trial(path, config, *, condition="dashboard", changes=(), participant_kind="synthetic", oracle=False, stop_at=None):
    trial = Trial(config, condition, changes=changes, oracle=oracle)
    recorder = Recorder(path, trial, participant_kind=participant_kind)
    while not trial.complete and (stop_at is None or trial.step < stop_at):
        recorder.append(*trial.advance((0.25, -0.1)))
    recorder.finish(trial)
    return recorder


def test_replay_includes_independent_model_and_encoder_changes(tmp_path, config):
    path = tmp_path / "trial"
    record_trial(path, config, changes=[ChangeEvent(8, "estimator", "rw-kalman-v2"),
                                        ChangeEvent(13, "encoder", "polar8-rotated-v1")])
    result = replay(path)
    assert result["replay_verified"] and result["steps"] == config.steps
    trace = [json.loads(line) for line in (path / "trace.jsonl").read_text().splitlines()]
    assert trace[8]["events"][0]["component"] == "estimator"
    assert trace[8]["events"][0]["state_transfer"] == "reset"
    assert trace[13]["events"][0]["component"] == "encoder"
    assert trace[13]["feedback_packet"]["emitted_step"] == 13
    assert trace[13]["belief"]["estimator_id"] == "rw-kalman-v2"
    assert trace[13]["feedback_packet"]["encoder_id"] == "polar8-rotated-v1"
    assert '"flow"' not in (path / "trace.jsonl").read_text()
    assert all(json.loads(line)["access"] == "evaluator_only"
               for line in (path / "evaluation_only.jsonl").read_text().splitlines())


@pytest.mark.parametrize("key", ["human_evidence", "hardware_verified", "participant_kind"])
def test_metadata_evidence_cannot_be_promoted(tmp_path, config, key):
    path = tmp_path / "trial"
    record_trial(path, config)
    metadata = json.loads((path / "metadata.json").read_text())
    metadata[key] = "human" if key == "participant_kind" else True
    (path / "metadata.json").write_text(canonical(metadata))
    with pytest.raises(ValueError):
        replay(path)


def test_summary_evidence_cannot_be_promoted(tmp_path, config):
    path = tmp_path / "trial"
    record_trial(path, config)
    summary = json.loads((path / "summary.json").read_text())
    summary["hardware_verified"] = True
    (path / "summary.json").write_text(canonical(summary))
    with pytest.raises(ValueError, match="summary/evidence"):
        replay(path)


@pytest.mark.parametrize("section", ["action", "output_acknowledgement", "events"])
def test_trace_tampering_is_detected(tmp_path, config, section):
    path = tmp_path / "trial"
    record_trial(path, config)
    trace = [json.loads(line) for line in (path / "trace.jsonl").read_text().splitlines()]
    trace[0][section] = {"action": [0, 0], "output_acknowledgement": "device_ack", "events": [{"identity": "unknown"}]}[section]
    (path / "trace.jsonl").write_text("\n".join(map(canonical, trace)))
    with pytest.raises(ValueError, match="mismatch"):
        replay(path)


def test_partial_trial_replays_but_does_not_report_success(tmp_path, config):
    path = tmp_path / "trial"
    record_trial(path, config, stop_at=10)
    result = replay(path)
    assert result["replay_verified"]
    assert result["status"] == "incomplete_or_invalid"
    assert result["normalized_tracking_rmse"] is None


def test_oracle_is_explicit_labelled_and_separate(tmp_path, config):
    with pytest.raises(ValueError, match="oracle"):
        Trial(config, ORACLE_CONDITION)
    with pytest.raises(ValueError, match="separate"):
        Trial(config, "dashboard", oracle=True)
    result = run_smoke(tmp_path / "main", config)
    assert not any(r["diagnostic"] for r in result["results"])
    oracle = run_smoke(tmp_path / "diagnostic", config, oracle=True)
    assert oracle["kind"] == "oracle_diagnostic"
    assert len(oracle["results"]) == 1
    assert oracle["results"][0]["diagnostic"]
    path = tmp_path / "diagnostic" / ORACLE_CONDITION
    trace = [json.loads(line) for line in (path / "trace.jsonl").read_text().splitlines()]
    truths = [json.loads(line) for line in (path / "evaluation_only.jsonl").read_text().splitlines()]
    assert all(r["belief"]["mean"] == t["flow"] for r, t in zip(trace, truths))
    metadata = json.loads((path / "metadata.json").read_text())
    metadata["diagnostic"] = False
    (path / "metadata.json").write_text(canonical(metadata))
    with pytest.raises(ValueError, match="oracle"):
        replay(path)


@pytest.mark.parametrize("kind", ["synthetic", "developer"])
def test_software_only_labels_and_no_device_ack(tmp_path, config, kind):
    path = tmp_path / "trial"
    record_trial(path, config, participant_kind=kind)
    result = replay(path)
    assert result["participant_kind"] == kind
    assert result["human_evidence"] is False
    assert result["hardware_verified"] is False
    assert all(json.loads(line)["output_acknowledgement"] is None
               for line in (path / "trace.jsonl").read_text().splitlines())
    with pytest.raises(ValueError, match="synthetic"):
        Recorder(tmp_path / "wrong", Trial(config, "none"), participant_kind="developer", policy_id="script")
    with pytest.raises(ValueError):
        evidence("approved_participant")


def test_unavailable_hardware_and_invalid_config_fail_without_output(tmp_path, capsys):
    output = tmp_path / "must_not_exist"
    assert main(["smoke", "--out", str(output), "--output", "hardware"]) == 2
    assert "hardware output is unavailable" in capsys.readouterr().err
    assert not output.exists()
    bad_config = tmp_path / "bad.json"
    bad_config.write_text('{"sensor_noise_std": -1}')
    assert main(["smoke", "--out", str(output), "--config", str(bad_config)]) == 2
    assert not output.exists()


def test_existing_logs_are_never_overwritten(tmp_path, config):
    path = tmp_path / "trial"
    record_trial(path, config)
    original = (path / "trace.jsonl").read_bytes()
    with pytest.raises(FileExistsError):
        run_smoke(path, config)
    assert (path / "trace.jsonl").read_bytes() == original


@pytest.mark.parametrize("values", [
    {"dt_s": 0}, {"dt_s": float("nan")}, {"seed": -1}, {"seed": True},
    {"sensor_noise_std": 0}, {"sensor_noise_std": 1e300}, {"sensor_period_steps": 0},
    {"sensor_delay_steps": -1}, {"sensor_dropout_probability": 1.1},
    {"evaluation_end_step": 601}, {"target_radius": 1}, {"feedback_period_steps": 1.5},
    {"unrecognized": 1},
])
def test_invalid_configs_rejected(values):
    with pytest.raises(ValueError):
        Config.from_dict(values)
