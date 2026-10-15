from dataclasses import replace
import json
import math
from types import SimpleNamespace

import pytest

from augneta.calibration_session import CalibrationSession
from augneta.config import Config
from augneta.estimation import Belief
from augneta.experiment import Trial, synthetic_action
from augneta.tactile import CodeSpec, TactileProfile
from augneta import web


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def wait_for(self, profile):
        self.now += (profile.pulse_ms + profile.gap_ms) / 1000 + 0.001


def answer_preview(stimulus, profile):
    """Synthetic decoder of the visible default one-hot candidate, not human data."""
    values = stimulus["left"] + stimulus["right"]
    if max(values) == 0:
        return {"kind": "zero", "direction": None, "level": 0}
    slot = values.index(max(values))
    strength = values[slot] / profile.gains[slot]
    level = min(range(1, profile.spec.levels + 1), key=lambda i: abs(profile.intensities[i] - strength))
    return {"kind": "identified", "direction": slot, "level": level}


def complete_phase(session, clock):
    while session.state == "ready":
        result = session.present(session.index)
        clock.wait_for(session.profile)
        session.respond(session.index, answer_preview(result["stimulus"], session.profile))


def test_six_motor_representation_preserves_semantics_when_gain_changes():
    first = TactileProfile()
    changed = replace(first, gains=(0.5,) * 6)
    code = first.spec.code(4, 2)
    a, b = first.matched_preview(code), changed.matched_preview(code)
    assert a["semantic_state"] == b["semantic_state"]
    assert a["visual"] == b["visual"]
    assert a["command"]["right"][1] == 2 * b["command"]["right"][1]
    assert len(a["command"]["left"]) == len(a["command"]["right"]) == 3
    assert first.identity != changed.identity
    assert TactileProfile.from_dict(first.to_dict()) == first


def test_direction_count_is_not_motor_count_and_no_silent_aliasing():
    base = TactileProfile()
    eight = replace(base, spec=CodeSpec(directions=8), patterns=base.patterns + (
        (1., 1., 0., 0., 0., 0.), (0., 0., 0., 1., 1., 0.)))
    frames = [eight.render(eight.spec.code(d, 1)) for d in range(8)]
    assert len({tuple(f["left"] + f["right"]) for f in frames}) == 8
    assert all(len(f["left"] + f["right"]) == 6 for f in frames)
    four = replace(base, spec=CodeSpec(directions=4), patterns=base.patterns[:4])
    assert four.spec.code(3, 1)["direction"] == 3
    with pytest.raises(ValueError):
        replace(base, patterns=(base.patterns[0],) * 6)


def test_zero_magnitude_carries_no_direction():
    profile = TactileProfile()
    for mean in ((0, 0), (0.001, -0.001), (-0.001, 0.001)):
        code = profile.spec.encode(SimpleNamespace(mean=mean))
        assert code["direction"] is None
        assert profile.matched_preview(code)["visual"]["force"] == [0, 0]
        assert profile.render(code)["left"] + profile.render(code)["right"] == [0] * 6
    with pytest.raises(ValueError):
        profile.spec.code(0, 0)


@pytest.mark.parametrize("change", [
    {"gains": (True,) * 6}, {"gains": (float('nan'),) * 6}, {"gains": (1.1,) * 6},
    {"intensities": (0., .5, .25)}, {"pulse_ms": True}, {"gap_ms": -1},
    {"patterns": ((1.,) * 5,) * 6},
])
def test_invalid_output_profiles_rejected(change):
    with pytest.raises(ValueError):
        replace(TactileProfile(), **change)


def test_reject_unknown_information_and_mismatched_meanings():
    p = TactileProfile()
    with pytest.raises(ValueError):
        p.render({**p.spec.code(0, 1), "target": [1, 1]})
    with pytest.raises(ValueError):
        p.render(CodeSpec(directions=4).code(0, 1))
    with pytest.raises(ValueError):
        TactileProfile.from_dict({**p.to_dict(), "hardware_verified": True})


def test_causal_trial_beliefs_can_render_both_views_without_evaluator_truth():
    trial = Trial(Config(steps=40, evaluation_start_step=4, evaluation_end_step=40), "dashboard")
    profile = TactileProfile()
    count = 0
    while not trial.complete:
        record, _evaluator_only = trial.advance(synthetic_action(trial.view(), trial.config.control_gain))
        belief = Belief(**record["belief"])
        preview = profile.matched_preview(profile.spec.encode(belief))
        code, visual, command = preview["semantic_state"], preview["visual"], preview["command"]
        assert math.hypot(*visual["force"]) == pytest.approx(code["level"] / profile.spec.levels * profile.spec.max_magnitude)
        assert (visual["pulse_ms"], visual["gap_ms"]) == (command["pulse_ms"], command["gap_ms"])
        assert not preview["hardware_verified"] and not preview["human_evidence"]
        count += 1
    assert count == 40


def test_fit_freeze_holdout_and_export_are_separate(tmp_path):
    clock = Clock()
    s = CalibrationSession(tmp_path, clock=clock, participant_kind="synthetic")
    with pytest.raises(ValueError):
        s.freeze(s.profile)
    complete_phase(s, clock)
    assert s.state == "review" and len(s.records["fit"]) == 14
    assert s.view()["reports"]["fit"]["joint_accuracy"] == 1
    assert "validation" not in s.view()["reports"]
    changed = replace(s.profile, gains=(0.5,) * 6)
    s.freeze(changed)
    with pytest.raises(ValueError):
        s.freeze(s.profile)
    complete_phase(s, clock)
    data = s.export()
    assert data["state"] == "complete"
    assert data["reports"]["validation"]["joint_accuracy"] == 1
    assert data["fit_profile"]["gains"] != data["validation_profile"]["gains"]
    assert {r["profile_sha256"] for r in data["responses"]["validation"]} == {changed.identity}
    assert data["profile_status"] == "unvalidated_hardware_candidate"
    assert not data["hardware_verified"] and not data["human_evidence"]
    assert json.loads((s.directory / "session.json").read_text()) == data


def test_phase_freeze_cannot_remap_the_learned_meaning(tmp_path):
    clock = Clock(); s = CalibrationSession(tmp_path, clock=clock)
    complete_phase(s, clock)
    with pytest.raises(ValueError):
        s.freeze(replace(s.profile, patterns=s.profile.patterns[::-1]))
    assert s.state == "review" and s.validation_profile is None


def test_response_lifecycle_stop_and_unknown_preserve_incomplete_data(tmp_path):
    clock = Clock(); s = CalibrationSession(tmp_path, clock=clock)
    answer = {"kind": "unknown", "direction": None, "level": None}
    with pytest.raises(ValueError): s.respond(0, answer)
    with pytest.raises(ValueError): s.present(True)
    first = s.present(0)
    assert not {"expected", "seed", "plan", "semantic_state"} & first.keys()
    with pytest.raises(ValueError): s.present(0)
    with pytest.raises(ValueError): s.respond(0, answer)  # pulse/gap still active
    with pytest.raises(ValueError): s.export()
    clock.wait_for(s.profile)
    with pytest.raises(ValueError): s.respond(0, {**answer, "level": 1})
    s.respond(0, answer)
    with pytest.raises(ValueError): s.respond(0, answer)
    s.stop(); s.stop()
    data = s.export()
    assert data["reports"]["fit"]["answered"] == 1
    assert data["reports"]["fit"]["response_counts"] == {"unknown": 1}
    assert data["reports"]["validation"]["joint_accuracy"] is None
    assert data["planned_per_phase"]["fit"] == 14
    with pytest.raises(ValueError): s.present(1)


@pytest.fixture
def calibration_client(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(web, "CalibrationSession", lambda *args: CalibrationSession(*args, clock=clock))
    app = web.create_app(tmp_path, participant_kind="synthetic")
    app.config["TESTING"] = True
    return app.test_client(), clock


def test_full_http_calibration_roundtrip_and_reloaded_profile(calibration_client):
    c, clock = calibration_client
    assert c.get('/calibration').status_code == 200
    for path in ('/static/calibration.js', '/static/calibration.css'):
        assert c.get(path).status_code == 200
    default = c.get('/api/calibration/defaults').json["profile"]
    v = c.post('/api/calibration/start', json={"profile": default}).json
    identifier = v["session_id"]
    assert c.get(f'/api/calibration/{identifier}/export').status_code == 400
    for phase in ('fit', 'validation'):
        if phase == 'validation':
            result = c.post('/api/calibration/freeze', json={"session_id": identifier, "profile": default})
            assert result.status_code == 200
            v = result.json
        while v["state"] == "ready":
            selection = {"session_id": identifier, "expected_index": v["index"]}
            presentation = c.post('/api/calibration/present', json=selection)
            assert presentation.status_code == 200
            assert "validation" not in presentation.json["reports"]
            clock.wait_for(TactileProfile())
            v = c.post('/api/calibration/respond', json={**selection,
                "response": answer_preview(presentation.json["stimulus"], TactileProfile())}).json
    assert v["state"] == 'complete'
    exported = c.get(f'/api/calibration/{identifier}/export').json
    assert exported["reports"]["fit"]["answered"] == exported["reports"]["validation"]["answered"] == 14
    new = c.post('/api/calibration/start', json={"profile": exported["profile"]}).json
    assert new["profile_sha256"] == exported["profile_sha256"]
    assert new["reports"] == {}
    assert c.post('/api/calibration/present', json={"session_id": identifier, "expected_index": 0}).status_code == 400


@pytest.mark.parametrize('body', [{"output": "hardware"}, {"human_evidence": True},
    {"participant_kind": "human"}, {"seed": True}, {"seed": -1}, {"profile": {}}])
def test_http_bad_start_preserves_existing_session(calibration_client, body):
    c, _ = calibration_client
    s = c.post('/api/calibration/start', json={}).json
    assert c.post('/api/calibration/start', json=body).status_code == 400
    assert c.post('/api/calibration/present', json={"session_id": s["session_id"], "expected_index": 0}).status_code == 200


def test_calibration_routes_retain_origin_and_truth_boundaries(calibration_client):
    c, _ = calibration_client
    assert c.post('/api/calibration/start', json={}, headers={"Origin": "https://elsewhere.example"}).status_code == 403
    assert c.post('/api/calibration/start', data='{}').status_code == 415
    assert c.post('/api/tactile-preview', json={"direction": 0, "level": 1, "target": [0, 1]}).status_code == 400
    a = c.post('/api/tactile-preview', json={"direction": 0, "level": 1}).json
    assert a['visual']['force'] == [0.75, 0.0]
    assert a['command']['left'] == [0.25, 0, 0]
    assert a['command']['right'] == [0, 0, 0]
