from dataclasses import replace
import json
import math

import pytest

from augneta.config import Config
from augneta.experiment import Trial, synthetic_action
from augneta.metrics import safe_zone_error
from augneta.recording import Recorder, replay
from augneta.sensitivity import diagnostic_results, validate_design, _pair, _run
from augneta.web import create_app


def test_closed_square_distance_denominators_and_window():
    c = Config(steps=4, evaluation_start_step=1, evaluation_end_step=3, safe_zone_half_width=0.5)
    states = [{"step": i, "position": p} for i, p in enumerate(
        ([1, 1], [1, 1], [0.5, -0.5], [1, 1], [1, 1]))]
    result = safe_zone_error(states, config=c, completed=True)
    assert result["samples"] == 2
    assert result["outside_time_s"] == c.dt_s
    assert result["outside_fraction"] == 0.5
    assert result["normalized_outside_distance"] == pytest.approx(0.5)
    assert result["normalization_constant"] == math.sqrt(2) * 0.5
    for interrupted in (states[:3], states):
        assert safe_zone_error(interrupted, config=c, completed=False)["outside_fraction"] is None
    assert safe_zone_error(states[:3], config=c, completed=True)["outside_fraction"] is None


@pytest.mark.parametrize("position", [[float('nan'), 0], [True, 0], [1], '12'])
def test_invalid_positions_never_score(position):
    c = Config(steps=1, evaluation_start_step=0, evaluation_end_step=1, sensor_delay_steps=0)
    assert safe_zone_error([{"step": 1, "position": position}], config=c, completed=True)["normalized_outside_distance"] is None


@pytest.mark.parametrize("changes", [{"task": "other"}, {"safe_zone_half_width": 0},
    {"safe_zone_half_width": 1}, {"safe_zone_half_width": float('nan')}, {"safe_zone_half_width": True}])
def test_invalid_task_config(changes):
    with pytest.raises(ValueError):
        Config(task="safe_zone", **changes) if "task" not in changes else Config(**changes)


@pytest.mark.parametrize("task", ["tracking", "safe_zone"])
@pytest.mark.parametrize("stop_at", [0, 5, 10, 12])
def test_recording_replays_both_tasks_and_stop(tmp_path, task, stop_at):
    c = Config(task=task, steps=12, evaluation_start_step=2, evaluation_end_step=10)
    t = Trial(c, "dashboard")
    recorder = Recorder(tmp_path / 'run', t, participant_kind="synthetic", policy_id="visible-pd-v2")
    completed = stop_at == 12
    for _ in range(stop_at):
        recorder.append(*t.advance(synthetic_action(t.view(), c.control_gain)))
    result = recorder.finish(t)
    assert result["status"] == ("complete" if completed else "incomplete_or_invalid")
    assert replay(tmp_path / 'run')["task"] == task
    assert recorder.metadata["config"]["task"] == task


def test_same_actions_same_beliefs_and_encoding_across_objectives():
    c = Config(steps=32, evaluation_start_step=2, evaluation_end_step=32)
    a, b = Trial(c, "dashboard"), Trial(replace(c, task="safe_zone"), "dashboard")
    while not a.complete:
        assert a.view()["feedback"] == b.view()["feedback"]
        r1, truth1 = a.advance((0.3, -0.2))
        r2, truth2 = b.advance((0.3, -0.2))
        assert r1 == r2 and truth1 == truth2
        assert r1["belief"]["now_step"] == r1["step"]
        assert all(o["available_step"] <= r1["step"] for o in r1["sensor_observations"])


def test_policy_contract_reads_no_evaluator_or_observation_fields():
    class Restricted(dict):
        def __getitem__(self, key):
            assert key in ("visible", "feedback", "task", "target", "position", "velocity")
            return super().__getitem__(key)
    state = Restricted(position=[0.2, -0.1], velocity=[0, 0])
    # Safe-zone reference is fixed; even the moving target is unnecessary.
    view = Restricted(visible=state, feedback=None, task="safe_zone")
    assert synthetic_action(view, 2) == (-0.5, 0.25)


@pytest.mark.parametrize("args", [((7,), (7,), (0,), (0,)), ((), (8,), (0,), (0,)),
    ((7, 7), (8,), (0,), (0,)), ((7,), (8,), (-1,), (0,)),
    ((7,), (8,), (0,), (True,)), ((7,), (8,), (0,), (101,))])
def test_invalid_split_and_grid(args):
    with pytest.raises(ValueError):
        validate_design(*args)


def test_paired_diagnostic_deterministic_and_complete():
    args = dict(development=(7,), check=(101,), strengths=(0, 0.65), delays=(0, 4))
    first, second = diagnostic_results(**args), diagnostic_results(**args)
    assert first == second
    assert first["pairing_verified"]
    assert len(first["cells"]) == 16
    assert {(c["split"], c["task"], c["flow_strength"], c["sensor_delay_steps"]) for c in first["cells"]} == {
        (split, task, strength, delay) for split in ("development", "check")
        for task in ("tracking", "safe_zone") for strength in (0, 0.65) for delay in (0, 4)}
    assert first["participant_kind"] == "synthetic" and first["human_evidence"] is False
    for cell in first["cells"]:
        p = cell["pairs"][0]
        assert p["matched_views_identical"]
        assert p["paired_differences_vs_none"]["dashboard"] == p["paired_differences_vs_none"]["sensory_preview"]
        assert p["config"]["task"] == cell["task"]
        assert all(s["status"] == "complete" for s in p["summaries"].values())


def test_task_api_validation_stop_and_calibration_preserved(tmp_path):
    c = Config(steps=2, evaluation_start_step=0, evaluation_end_step=2, sensor_delay_steps=0)
    client = create_app(tmp_path, participant_kind="synthetic", config=c).test_client()
    assert client.get('/calibration').status_code == 200
    assert client.post('/api/trials', json={"task": "safe_zone", "safe_zone_half_width": 2}).status_code == 400
    v = client.post('/api/trials', json={"task": "safe_zone", "safe_zone_half_width": 0.3}).get_json()
    assert v["objective"]["half_width"] == 0.3
    assert v["task"] == "safe_zone"
    r = client.post('/api/stop', json={"trial_id": v["trial_id"]}).get_json()["summary"]
    assert r["outside_time_s"] is None and r["status"] == "incomplete_or_invalid"


def test_tracking_small_arena_does_not_depend_on_unused_safe_zone():
    assert Config(7).seed == 7  # Preserve the existing positional seed argument.
    c = Config(arena_half_width=0.1, target_radius=0.05)
    with pytest.raises(ValueError, match="fit strictly"):
        safe_zone_error([], config=c, completed=False)
    assert Trial(c, "none").view()["objective"] == {"kind": "tracking"}
    with pytest.raises(ValueError, match="fit strictly"):
        replace(c, task="safe_zone")


@pytest.mark.parametrize("steps", [[], [1], [2, 1], [1, 1, 2]])
def test_safe_zone_invalid_window_never_scores(steps):
    c = Config(steps=2, evaluation_start_step=0, evaluation_end_step=2, sensor_delay_steps=0)
    states = [{"step": i, "position": [0, 0]} for i in steps]
    result = safe_zone_error(states, config=c, completed=True)
    assert result["outside_time_s"] is None
    assert result["outside_fraction"] is None
    assert result["normalized_outside_distance"] is None


def test_safe_zone_axis_distance_and_boundary():
    c = Config(steps=4, evaluation_start_step=0, evaluation_end_step=4, safe_zone_half_width=0.5)
    states = [{"step": i + 1, "position": p} for i, p in enumerate(
        ([0, 0], [0.5, 0.2], [1, 0], [1, 1]))]
    result = safe_zone_error(states, config=c, completed=True)
    assert result["outside_samples"] == 2
    assert result["outside_fraction"] == 0.5
    assert result["evaluation_duration_s"] == 4 * c.dt_s
    assert result["normalized_outside_distance"] == pytest.approx((0.5 + math.sqrt(0.5)) / 4 / math.sqrt(0.5))


@pytest.mark.parametrize("tamper", ["task", "zone", "score"])
def test_safe_zone_replay_detects_changed_configuration_and_score(tmp_path, tamper):
    c = Config(task="safe_zone", steps=8, evaluation_start_step=0, evaluation_end_step=8)
    trial = Trial(c, "none")
    recorder = Recorder(tmp_path / 'run', trial, participant_kind="synthetic")
    while not trial.complete:
        recorder.append(*trial.advance((1, 0)))
    recorder.finish(trial)
    filename = 'summary.json' if tamper == 'score' else 'metadata.json'
    path = tmp_path / 'run' / filename
    data = json.loads(path.read_text())
    if tamper == 'score':
        data['normalized_outside_distance'] = 0.99
    else:
        data['config']['task' if tamper == 'task' else 'safe_zone_half_width'] = 'tracking' if tamper == 'task' else 0.8
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identity mismatch|summary/evidence"):
        replay(tmp_path / 'run')


def test_actual_diagnostic_policy_boundary(monkeypatch):
    seen = []
    def policy(view, gain):
        assert set(view) == {"visible", "feedback", "task", "objective", "condition", "diagnostic", "complete"}
        assert set(view['visible']) == {"step", "time_s", "position", "velocity"}
        assert view['diagnostic'] is False
        if view['feedback']:
            assert view['feedback']['emitted_step'] <= view['visible']['step']
        seen.append(view['visible']['step'])
        return synthetic_action(view, gain)
    monkeypatch.setattr('augneta.sensitivity.synthetic_action', policy)
    _run(Config(task="safe_zone", steps=8, evaluation_start_step=0, evaluation_end_step=8), 'dashboard')
    assert seen == list(range(8))


def test_matched_audit_detects_timing_difference_even_with_equal_scores(monkeypatch):
    original = Trial.view
    def changed_view(self):
        v = original(self)
        if v['condition'] == 'sensory_preview':
            v['feedback']['emitted_step'] += 1  # decoding/action unchanged
        return v
    monkeypatch.setattr(Trial, 'view', changed_view)
    result = _pair(Config(task='safe_zone', flow_strength=0, steps=8,
                          evaluation_start_step=0, evaluation_end_step=8))
    assert result['summaries']['dashboard']['normalized_outside_distance'] == result['summaries']['sensory_preview']['normalized_outside_distance']
    assert result['matched_views_identical'] is False


def test_defaults_invalid_switch_and_stopped_run_preservation(tmp_path):
    c = Config(task="safe_zone", safe_zone_half_width=0.3, seed=123, steps=8,
               evaluation_start_step=0, evaluation_end_step=4)
    client = create_app(tmp_path, participant_kind="synthetic", config=c).test_client()
    defaults = client.get('/api/trial-defaults').get_json()
    assert defaults == dict(task='safe_zone', safe_zone_half_width=0.3, seed=123, arena_half_width=1.0)
    v = client.post('/api/trials', json={}).get_json()
    assert v['task'] == defaults['task'] and v['objective']['half_width'] == 0.3
    assert client.post('/api/trials', json={'task':'safe_zone', 'safe_zone_half_width':1}).status_code == 400
    for i in range(5):
        response = client.post('/api/step', json={'trial_id':v['trial_id'], 'expected_step':i, 'action':[0, 0]})
        assert response.status_code == 200
    result = client.post('/api/stop', json={'trial_id':v['trial_id']}).get_json()['summary']
    assert result['samples'] == 4 and result['outside_fraction'] is None
    assert replay(v['recording'])['status'] == 'incomplete_or_invalid'
    assert client.post('/api/step', json={'trial_id':v['trial_id'], 'expected_step':5, 'action':[0, 0]}).status_code == 400
    assert client.post('/api/trials', json={'task':'tracking'}).get_json()['task'] == 'tracking'


def test_review_did_not_retune_exposed_check_design():
    import hashlib
    from augneta.config import canonical
    from augneta.sensitivity import diagnostic_design
    assert hashlib.sha256(canonical(diagnostic_design()).encode()).hexdigest() == "d894a2a9404a29a6340283af0af446b863a4c022657d6264e26c4f978a44fc2b"
