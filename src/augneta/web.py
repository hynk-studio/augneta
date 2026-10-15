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
from .calibration_session import CalibrationSession
from .tactile import TactileProfile
from .task_presentation import CONDITIONS as SIX_SLOT_CONDITIONS, export_candidate, import_candidate


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
    calibration = {}
    cancelled_starts = set()
    used_starts = set()

    def end_active():
        if active:
            active["recorder"].finish(active["trial"])

    def cleanup():
        end_active()
        if calibration:
            calibration["session"].stop()

    atexit.register(cleanup)

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

    @app.get("/calibration")
    def calibration_page():
        return send_from_directory(app.static_folder, "calibration.html")

    @app.get("/api/calibration/defaults")
    def calibration_defaults():
        return jsonify(profile=TactileProfile().to_dict(), output_mode="visual_rehearsal",
                       hardware_verified=False, human_evidence=False)

    @app.post("/api/tactile-preview")
    def tactile_preview():
        data = payload(("profile", "direction", "level"))
        profile = TactileProfile.from_dict(data["profile"]) if "profile" in data else TactileProfile()
        return jsonify(profile.matched_preview(profile.spec.code(data.get("direction"), data.get("level"))))

    @app.post('/api/candidate-profile')
    def candidate_profile():
        data = payload(('profile',))
        return jsonify(export_candidate(TactileProfile.from_dict(data.get('profile')), participant_kind))

    @app.post('/api/candidate-import')
    def candidate_import():
        data = payload(('candidate', 'scope'))
        if data.get('scope', 'task') not in ('task', 'calibration'):
            raise ValueError('unknown candidate scope')
        profile = import_candidate(data.get('candidate'), for_task=data.get('scope', 'task') == 'task')
        return jsonify(profile_sha256=profile.identity, code_id=profile.spec.identity,
                       profile_status='unvalidated_hardware_candidate')

    @app.post("/api/calibration/start")
    def calibration_start():
        data = payload(("profile", "seed"))
        profile = TactileProfile.from_dict(data["profile"]) if "profile" in data else TactileProfile()
        with lock:
            session = CalibrationSession(Path(log_root) / "calibration", profile,
                                         data.get("seed", 7), participant_kind)
            if calibration:
                calibration["session"].stop()
            calibration["session"] = session
            return jsonify(session.view())

    def selected_calibration(data):
        session = calibration.get("session")
        if session is None or data.get("session_id") != session.id:
            raise ValueError("unknown or superseded calibration session")
        return session

    @app.post("/api/calibration/present")
    def calibration_present():
        data = payload(("session_id", "expected_index"))
        with lock:
            return jsonify(selected_calibration(data).present(data.get("expected_index")))

    @app.post("/api/calibration/respond")
    def calibration_respond():
        data = payload(("session_id", "expected_index", "response"))
        with lock:
            return jsonify(selected_calibration(data).respond(data.get("expected_index"), data.get("response")))

    @app.post("/api/calibration/freeze")
    def calibration_freeze():
        data = payload(("session_id", "profile"))
        profile = TactileProfile.from_dict(data.get("profile"))
        with lock:
            return jsonify(selected_calibration(data).freeze(profile))

    @app.post("/api/calibration/stop")
    def calibration_stop():
        data = payload(("session_id",))
        with lock:
            return jsonify(selected_calibration(data).stop())

    @app.get("/api/calibration/<identifier>/export")
    def calibration_export(identifier):
        with lock:
            return jsonify(selected_calibration({"session_id": identifier}).export())

    @app.get("/api/trial-defaults")
    def trial_defaults():
        return jsonify(task=default_config.task, seed=default_config.seed,
                       safe_zone_half_width=default_config.safe_zone_half_width,
                       arena_half_width=default_config.arena_half_width)

    def validate_start_id(value):
        if not isinstance(value, str):
            raise ValueError('start ID must be a UUID')
        try:
            if str(uuid.UUID(value)) != value:
                raise ValueError('noncanonical start ID')
        except (ValueError, AttributeError):
            raise ValueError('start ID must be a UUID') from None

    @app.post('/api/cancel-start')
    def cancel_start():
        data = payload(('start_id',))
        identifier = data.get('start_id')
        validate_start_id(identifier)
        with lock:
            cancelled_starts.add(identifier)
            if active and active['id'] == identifier:
                active['stopped'] = True
                active['recorder'].finish(active['trial'])
            return jsonify(cancelled=True)

    @app.post("/api/trials")
    def start():
        data = payload(("condition", "seed", "task", "safe_zone_half_width", "candidate", "start_id"))
        condition = data.get("condition", "none")
        if condition not in MAIN_CONDITIONS + SIX_SLOT_CONDITIONS:
            raise ValueError("only main development conditions are available in the UI")
        settings = default_config.to_dict()
        settings["seed"] = data.get("seed", settings["seed"])
        for key in ("task", "safe_zone_half_width"):
            if key in data:
                settings[key] = data[key]
        start_id = data.get('start_id')
        if start_id is not None:
            validate_start_id(start_id)
            if condition not in SIX_SLOT_CONDITIONS:
                raise ValueError('start ID requires six-slot rehearsal')
        trial = Trial(Config.from_dict(settings), condition, candidate=data.get("candidate"))
        with lock:
            if start_id is not None:
                if start_id in cancelled_starts or start_id in used_starts:
                    raise ValueError('cancelled or duplicate start ID')
                used_starts.add(start_id)
            end_active()
            identifier = start_id or str(uuid.uuid4())
            recorder = Recorder(Path(log_root) / session_id / identifier, trial,
                                participant_kind=participant_kind, session_id=session_id)
            active.update(trial=trial, recorder=recorder, id=identifier, stopped=False)
            recorder.transport("start", trial)
            return jsonify(view())

    def selected(data):
        if not active or data.get("trial_id") != active["id"]:
            raise ValueError("unknown or superseded trial")

    @app.post("/api/step")
    def step():
        data = payload(("trial_id", "expected_step", "action", "presentation_epoch"))
        with lock:
            selected(data)
            trial = active["trial"]
            if trial.presentation and (type(data.get('presentation_epoch')) is not int or
                    data['presentation_epoch'] != trial.presentation.epoch):
                raise ValueError('stale presentation epoch')
            if active["stopped"]:
                raise ValueError("trial was stopped; start a new trial")
            if type(data.get("expected_step")) is not int or data["expected_step"] != trial.step:
                return jsonify(error="step conflict; duplicate or stale input"), 409
            started = time.monotonic()
            record, truth = trial.advance(data.get("action"))
            active["recorder"].append(record, truth)
            active["recorder"].transport("step", trial)
            if trial.complete:
                active["recorder"].finish(trial)
            result = view()
            result["server_processing_ms"] = (time.monotonic() - started) * 1000
            return jsonify(result)

    @app.post('/api/presentation-lifecycle')
    def presentation_lifecycle():
        data = payload(('trial_id', 'action', 'expected_epoch'))
        with lock:
            selected(data)
            if active['trial'].complete and active['trial'].presentation:
                return jsonify(view())
            active['recorder'].transition(active['trial'], data.get('action'), data.get('expected_epoch'))
            if data['action'] == 'stop':
                active['stopped'] = True
                active['recorder'].finish(active['trial'])
            return jsonify(view())

    @app.post("/api/stop")
    def stop():
        data = payload(("trial_id",))
        with lock:
            selected(data)
            active["stopped"] = True
            summary = active["recorder"].finish(active["trial"])
            return jsonify(summary=summary)

    return app
