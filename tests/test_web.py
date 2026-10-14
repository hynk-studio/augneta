import json
from pathlib import Path

import pytest

from augneta.experiment import MAIN_CONDITIONS
from augneta.recording import replay
from augneta.web import create_app


@pytest.fixture
def client(tmp_path, config):
    app = create_app(tmp_path, participant_kind="synthetic", config=config)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize("condition", MAIN_CONDITIONS)
def test_http_trial_roundtrip_and_replay(client, condition):
    response = client.post("/api/trials", json={"condition": condition, "seed": 7})
    assert response.status_code == 200
    view = response.json
    if condition == "none":
        assert view["feedback"] is None
    else:
        assert "mean" not in view["feedback"]
    assert all(name not in view for name in ("ground_truth", "flow", "sensor_observations", "belief", "config"))
    for step in range(view["total_steps"]):
        response = client.post("/api/step", json={"trial_id": view["trial_id"], "expected_step": step, "action": [1, 0]})
        assert response.status_code == 200
        view = response.json
    assert view["complete"]
    assert view["summary"]["status"] == "complete"
    assert replay(view["recording"])["replay_verified"]
    records = [json.loads(line) for line in (Path(view["recording"]) / "trace.jsonl").read_text().splitlines()]
    assert all(record["action"] == record["applied_action"] == [1, 0] for record in records)


@pytest.mark.parametrize("body", [
    {"condition": "oracle_diagnostic"}, {"human_evidence": True}, {"hardware_verified": True},
    {"participant_kind": "human"}, {"output": "hardware"}, {"seed": -1},
])
def test_api_rejects_oracle_evidence_promotion_and_bad_input(client, body):
    assert client.post("/api/trials", json=body).status_code == 400


def test_stale_actions_never_advance_twice(client):
    trial = client.post("/api/trials", json={}).json
    request = {"trial_id": trial["trial_id"], "expected_step": 0, "action": [0.5, 0]}
    assert client.post("/api/step", json=request).json["visible"]["step"] == 1
    assert client.post("/api/step", json=request).status_code == 409
    response = client.post("/api/stop", json={"trial_id": trial["trial_id"]})
    assert response.json["summary"]["completed_steps"] == 1
    assert response.json["summary"]["normalized_tracking_rmse"] is None
    assert replay(trial["recording"])["replay_verified"]


def test_bad_action_does_not_advance_and_superseded_trials_rejected(client):
    old = client.post("/api/trials", json={}).json
    assert client.post("/api/step", json={"trial_id": old["trial_id"], "expected_step": 0, "action": [8, 0]}).status_code == 400
    new = client.post("/api/trials", json={}).json
    assert replay(old["recording"])["steps"] == 0
    assert client.post("/api/step", json={"trial_id": old["trial_id"], "expected_step": 0, "action": [0, 0]}).status_code == 400
    assert client.post("/api/step", json={"trial_id": new["trial_id"], "expected_step": 0, "action": [0, 0]}).json["visible"]["step"] == 1
    client.post("/api/stop", json={"trial_id": new["trial_id"]})


def test_app_assets_and_local_request_boundary(client):
    for path in ("/", "/static/app.js", "/static/style.css", "/api/health"):
        assert client.get(path).status_code == 200
    assert client.get("/api/health").json["hardware_verified"] is False
    assert client.post("/api/trials", data="{}").status_code == 415
    assert client.post("/api/trials", json={}, headers={"Origin": "https://unrelated.example"}).status_code == 403
    assert client.get("/evaluation_only.jsonl").status_code == 404
