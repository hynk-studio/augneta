"""Local P1 first-session rehearsal server and per-session group summary."""

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import webbrowser

from flask import Flask, jsonify, request, send_from_directory

from study import BANK, Conflict, Study


def create_app(database, kind="developer", *, self_check=False):
    study = Study(database, kind, self_check=self_check)
    app = Flask(__name__, static_folder=str(Path(__file__).parent / "ui"), static_url_path="/ui")
    if self_check:
        # A local return can restore the one operator's saved record without a cookie.
        app.config["TRUSTED_HOSTS"] = ["127.0.0.1", "localhost"]
    # Cookies are shared between localhost ports. Bind this cookie to the chosen database.
    suffix = hashlib.sha256(str(study.database.resolve()).encode()).hexdigest()[:12]
    cookie = f"augneta_p1_{suffix}"
    app.config["MAX_CONTENT_LENGTH"] = 8192

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'")
        return response

    @app.before_request
    def check_post():
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site" or (origin and origin != request.host_url.rstrip("/")):
                return jsonify(error="이 서버의 화면에서 진행해 주세요."), 403
            if not request.is_json:
                return jsonify(error="JSON 본문이 필요합니다."), 415

    @app.errorhandler(Conflict)
    def stale(error):
        return jsonify(error=str(error)), 409

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def unknown(_error):
        return jsonify(error="이 브라우저의 리허설을 찾을 수 없습니다."), 404

    def body(fields):
        data = request.get_json()
        if not isinstance(data, dict) or set(data) != set(fields):
            raise ValueError("Unexpected request fields.")
        return data

    def with_cookie(data, token):
        response = jsonify(data)
        response.set_cookie(cookie, token, httponly=True, samesite="Strict", max_age=7*24*3600)
        return response

    def welcome():
        state = {"phase": "welcome", "participant_kind": study.kind}
        if self_check:
            state["self_check"] = True
        return with_cookie(state, secrets.token_urlsafe(24))

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/display.js")
    def display():
        return send_from_directory(BANK / "preview", "display.js")

    @app.get("/api/session")
    def current():
        try:
            return jsonify(study.current(request.cookies.get(cookie)))
        except KeyError:
            if self_check:
                token = study.personal_session()
                if token:
                    return with_cookie(study.current(token), token)
            return welcome()

    @app.post("/api/start")
    def start():
        data = body(("exposure",) if self_check else ())
        token = request.cookies.get(cookie)
        if not token:
            raise Conflict("먼저 시작 화면을 열어 주세요.")
        token = study.start(token, exposure=data.get("exposure"))
        return with_cookie(study.current(token), token)

    @app.post("/api/event")
    def event():
        data = body(("revision", "action", "value"))
        return jsonify(study.event(request.cookies.get(cookie), data["revision"], data["action"], data["value"]))

    @app.post("/api/new")
    def new_session():
        body(())
        if self_check:
            raise Conflict("이 개인 점검 파일에는 한 번의 기록이 저장됩니다.")
        if study.current(request.cookies.get(cookie))["phase"] != "complete":
            raise Conflict("진행 중인 리허설이 있습니다.")
        return welcome()

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "summary"))
    parser.add_argument("--kind", choices=("developer", "synthetic"), default="developer")
    parser.add_argument("--self-check", action="store_true", help="One operator, two visits, local results")
    parser.add_argument("--open", action="store_true", help="Open the local session in the default browser")
    parser.add_argument("--db", type=Path, help="Defaults to runs/p1-pilot/<kind>.sqlite3")
    parser.add_argument("--port", type=int, help="Defaults to 8013 for a self-check, otherwise 8012")
    args = parser.parse_args()
    prefix = "self-check-" if args.self_check else ""
    port = args.port if args.port is not None else (8013 if args.self_check else 8012)
    db = args.db or Path("runs/p1-pilot") / f"{prefix}{args.kind}.sqlite3"
    if args.command == "summary":
        if not db.is_file():
            parser.error(f"No rehearsal database at {db}")
        print(json.dumps(Study(db, args.kind, self_check=args.self_check).summary(), indent=2, allow_nan=False))
    else:
        app = create_app(db, args.kind, self_check=args.self_check)
        if args.open:
            from werkzeug.serving import make_server
            with make_server("127.0.0.1", port, app, threaded=True) as server:
                url = f"http://127.0.0.1:{server.server_port}/"
                print(f"Augneta P1  {url}", flush=True)
                webbrowser.open(url)
                server.serve_forever()
        else:
            app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
