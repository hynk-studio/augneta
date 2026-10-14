"""A local-only development UI. No autonomous action selection or device output."""

import atexit
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .config import Config
from .experiment import MAIN_CONDITIONS, Trial, evidence
from .recording import Recorder


def _normalize_public_origin(origin):
    """Validate one operator-configured origin, never a request-derived URL."""
    if origin is None:
        return None
    message = "public_origin must be an http(s) origin: scheme://host[:port], without credentials, path, query, or fragment"
    if (not isinstance(origin, str) or not origin or any(not 33 <= ord(c) <= 126 for c in origin)
            or any(c in origin for c in "\\*%")):
        raise ValueError(message)
    try:
        url = urlsplit(origin)
        port = url.port  # Also rejects malformed or out-of-range ports.
        if (url.scheme not in ("http", "https") or not url.hostname
                or url.username is not None or url.password is not None or port == 0
                or url.netloc.endswith(":") or origin != f"{url.scheme}://{url.netloc}"):
            raise ValueError(message)
    except ValueError:
        raise ValueError(message) from None
    host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
    suffix = f":{port}" if port is not None and port != {"http": 80, "https": 443}[url.scheme] else ""
    return f"{url.scheme}://{host}{suffix}"


def create_app(log_root="runs/ui", *, participant_kind="developer", config=None, public_origin=None):
    public_origin = _normalize_public_origin(public_origin)
    labels = evidence(participant_kind)
    default_config = config or Config()
    app = Flask(__name__, static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 8192
    session_id = str(uuid.uuid4())
    lock = threading.Lock()
    active = {}

    def end_active():
        if active:
            active["recorder"].finish(active["trial"])

    atexit.register(end_active)

    @app.before_request
    def local_json_requests():
        # Keep direct access; optionally allow one known preview origin. Forwarded
        # headers never establish trust or change the request's scheme/host.
        if request.method == "POST":
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                return jsonify(error="cross-site control is not allowed"), 403
            origin = request.headers.get("Origin")
            if origin and origin not in (request.host_url.rstrip("/"), public_origin):
                return jsonify(error="origin does not match this server or its configured public origin"), 403
            if not request.is_json:
                return jsonify(error="application/json is required"), 415

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        return response

    @app.errorhandler(ValueError)
    def bad_value(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    def payload(allowed):
        data = request.get_json()
        if not isinstance(data, dict) or set(data) - set(allowed):
            raise ValueError("unexpected request fields")
        return data

    def view():
        trial = active["trial"]
        return {**trial.view(), **labels, "trial_id": active["id"],
                "dt_s": trial.config.dt_s, "total_steps": trial.config.steps,
                "arena_half_width": trial.config.arena_half_width,
                "recording": str(active["recorder"].directory),
                "summary": trial.summary() if trial.complete else None}

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ready", **labels)

    @app.post("/api/trials")
    def start():
        data = payload(("condition", "seed"))
        condition = data.get("condition", "none")
        if condition not in MAIN_CONDITIONS:
            raise ValueError("only main development conditions are available in the UI")
        settings = default_config.to_dict()
        settings["seed"] = data.get("seed", settings["seed"])
        trial = Trial(Config.from_dict(settings), condition)
        with lock:
            end_active()
            identifier = str(uuid.uuid4())
            recorder = Recorder(Path(log_root) / session_id / identifier, trial,
                                participant_kind=participant_kind, session_id=session_id)
            active.update(trial=trial, recorder=recorder, id=identifier, stopped=False)
            return jsonify(view())

    def selected(data):
        if not active or data.get("trial_id") != active["id"]:
            raise ValueError("unknown or superseded trial")

    @app.post("/api/step")
    def step():
        data = payload(("trial_id", "expected_step", "action"))
        with lock:
            selected(data)
            trial = active["trial"]
            if active["stopped"]:
                raise ValueError("trial was stopped; start a new trial")
            if type(data.get("expected_step")) is not int or data["expected_step"] != trial.step:
                return jsonify(error="step conflict; duplicate or stale input"), 409
            started = time.monotonic()
            record, truth = trial.advance(data.get("action"))
            active["recorder"].append(record, truth)
            if trial.complete:
                active["recorder"].finish(trial)
            result = view()
            result["server_processing_ms"] = (time.monotonic() - started) * 1000
            return jsonify(result)

    @app.post("/api/stop")
    def stop():
        data = payload(("trial_id",))
        with lock:
            selected(data)
            active["stopped"] = True
            summary = active["recorder"].finish(active["trial"])
            return jsonify(summary=summary)

    return app
