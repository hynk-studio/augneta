"""Origin validation at the WSGI boundary; these are simulated proxy requests."""

import pytest

from augneta.recording import replay
from augneta.web import create_app


def assert_trial_lifecycle(client, base_url, origin, extra_headers=None):
    headers = {"Origin": origin, "Sec-Fetch-Site": "same-origin", **(extra_headers or {})}

    def post(path, data):
        response = client.post(path, base_url=base_url, headers=headers, json=data)
        assert response.status_code == 200, response.json
        assert "Access-Control-Allow-Origin" not in response.headers
        return response.json

    trial = post("/api/trials", {})
    result = post("/api/step", {"trial_id": trial["trial_id"], "expected_step": 0, "action": [1, 0]})
    assert result["visible"]["step"] == 1
    stopped = post("/api/stop", {"trial_id": trial["trial_id"]})
    assert stopped["summary"]["completed_steps"] == 1
    assert stopped["summary"]["normalized_tracking_rmse"] is None
    assert replay(trial["recording"])["replay_verified"]


@pytest.mark.parametrize("public_origin", [None, "https://preview.example"])
@pytest.mark.parametrize("base_url", ["http://localhost:8000", "http://127.0.0.1:8000"])
def test_direct_localhost_lifecycle_preserved(tmp_path, config, public_origin, base_url):
    client = create_app(tmp_path, config=config, participant_kind="synthetic",
                        public_origin=public_origin).test_client()
    assert_trial_lifecycle(client, base_url, base_url)


@pytest.mark.parametrize("base_url,forwarded", [
    ("http://preview.example", {"X-Forwarded-Proto": "https"}),  # Reported reproduction.
    ("http://127.0.0.1:8000", {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "preview.example"}),
    ("http://127.0.0.1:8000", {}),  # Explicit configuration works without trusting any headers.
])
def test_configured_https_origin_start_step_stop(tmp_path, config, base_url, forwarded):
    client = create_app(tmp_path, config=config, participant_kind="synthetic",
                        public_origin="https://preview.example").test_client()
    assert_trial_lifecycle(client, base_url, "https://preview.example", forwarded)


def test_forwarded_headers_alone_do_not_enable_preview(tmp_path, config):
    client = create_app(tmp_path, config=config, participant_kind="synthetic").test_client()
    response = client.post("/api/trials", base_url="http://preview.example", json={}, headers={
        "Origin": "https://preview.example", "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "preview.example", "Forwarded": 'proto=https;host="preview.example"',
    })
    assert response.status_code == 403


@pytest.mark.parametrize("origin", [
    "https://unrelated.example", "https://preview.example.unrelated.example",
    "http://preview.example", "https://preview.example:444", "null",
    "https://preview.example https://unrelated.example",
])
def test_unrelated_origins_cannot_start_step_or_stop(tmp_path, config, origin):
    client = create_app(tmp_path, config=config, participant_kind="synthetic",
                        public_origin="https://preview.example").test_client()
    base_url = "http://127.0.0.1:8000"
    good = {"Origin": "https://preview.example"}
    # Spoofed forwarded values cannot admit an otherwise rejected Origin.
    bad = {"Origin": origin, "X-Forwarded-Proto": "https",
           "X-Forwarded-Host": "unrelated.example", "Forwarded": 'proto=https;host="unrelated.example"'}
    started = client.post("/api/trials", base_url=base_url, headers=good, json={})
    assert started.status_code == 200
    trial = started.json
    requests = [
        ("/api/trials", {}),
        ("/api/step", {"trial_id": trial["trial_id"], "expected_step": 1, "action": [-1, 0]}),
        ("/api/stop", {"trial_id": trial["trial_id"]}),
    ]
    for step, (path, data) in enumerate(requests):
        denied = client.post(path, base_url=base_url, headers=bad, json=data)
        assert denied.status_code == 403
        # A denied start/step/stop must not replace, advance, or stop the active trial.
        accepted = client.post("/api/step", base_url=base_url, headers=good, json={
            "trial_id": trial["trial_id"], "expected_step": step, "action": [1, 0]})
        assert accepted.status_code == 200
        assert accepted.json["visible"]["step"] == step + 1
    assert client.post("/api/stop", base_url=base_url, headers=good,
                       json={"trial_id": trial["trial_id"]}).status_code == 200
    assert replay(trial["recording"])["steps"] == 3


def test_explicit_origin_does_not_override_cross_site_rejection(tmp_path, config):
    client = create_app(tmp_path, config=config, participant_kind="synthetic",
                        public_origin="https://preview.example").test_client()
    response = client.post("/api/trials", json={}, headers={
        "Origin": "https://preview.example", "Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


@pytest.mark.parametrize("configured,serialized", [
    ("https://Preview.Example:443", "https://preview.example"),
    ("http://Preview.Example:80", "http://preview.example"),
    ("https://preview.example:8443", "https://preview.example:8443"),
    ("https://[::1]:8443", "https://[::1]:8443"),
])
def test_public_origin_uses_browser_serialization(tmp_path, config, configured, serialized):
    client = create_app(tmp_path, config=config, participant_kind="synthetic",
                        public_origin=configured).test_client()
    assert_trial_lifecycle(client, "http://127.0.0.1:8000", serialized)


@pytest.mark.parametrize("origin", [
    "", "*", "https://*.example", "preview.example", "file://preview.example",
    "https://", "https://user:password@preview.example", "https://preview.example/",
    "https://preview.example/path", "https://preview.example?query=1", "https://preview.example#part",
    "https://preview.example:bad", "https://preview.example:65536", "https://preview.example:0",
    "https://preview.example:", "https://preview.example\n", "https://preview.example\\path",
])
def test_invalid_public_origin_fails_at_startup(tmp_path, origin):
    with pytest.raises(ValueError, match="public_origin must be an http"):
        create_app(tmp_path, public_origin=origin)
    assert list(tmp_path.iterdir()) == []
