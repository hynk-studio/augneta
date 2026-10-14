"""Real headless Chromium interaction, labelled synthetic; not human usability."""

import argparse
import json
from pathlib import Path
import shutil
import threading

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from augneta.config import Config
from augneta.recording import replay, write_json
from augneta.web import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new artifact directory")
    parser.add_argument("--chromium", default=shutil.which("chromium"), help="system Chromium executable; otherwise use Playwright's installed browser")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    config = Config(dt_s=0.02, steps=100, evaluation_start_step=10, evaluation_end_step=100)
    app = create_app(args.out / "runs", participant_kind="synthetic", config=config)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    errors = []
    paths = []
    checks = []
    try:
        with sync_playwright() as playwright:
            options = {"headless": True}
            if args.chromium:
                options["executable_path"] = args.chromium
            browser = playwright.chromium.launch(**options)
            page = browser.new_page(viewport={"width": 1280, "height": 1100})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

            def observe(response):
                if response.url.endswith("/api/trials") and response.ok:
                    paths.append(Path(response.json()["recording"]))

            page.on("response", observe)
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            assert page.title() == "Augneta · Hidden flow"
            for condition in ("none", "dashboard", "sensory_preview"):
                page.select_option("#condition", condition)
                page.click("#start")
                # The previous trial may still show step=100 while start is pending.
                # Wait for a new active trial before sending a held-key event.
                page.wait_for_function("() => { const k = Number(document.querySelector('#arena').dataset.step); return k >= 2 && k < 100; }")
                page.keyboard.down("ArrowRight")
                page.wait_for_timeout(200)
                page.keyboard.up("ArrowRight")
                page.click("#pause")
                page.wait_for_timeout(100)  # allow at most one outstanding request to finish
                paused_step = page.locator("#arena").get_attribute("data-step")
                page.wait_for_timeout(150)
                assert page.locator("#arena").get_attribute("data-step") == paused_step
                assert page.locator("#pause").inner_text() == "Resume"
                page.screenshot(path=str(args.out / f"{condition}.png"), full_page=True)
                if condition == "none":
                    assert page.locator("#telemetry").is_hidden()
                else:
                    assert page.locator("#telemetry").is_visible()
                assert page.locator("#preview-note").is_visible() == (condition == "sensory_preview")
                page.click("#pause")
                page.keyboard.down("w")
                page.wait_for_timeout(120)
                page.keyboard.up("w")
                page.wait_for_function("() => document.querySelector('#status').textContent.startsWith('Trial complete')")
                assert page.locator("#score").inner_text() != "Incomplete"
                checks.append(f"{condition}: keyboard, pause/resume, feedback visibility, completion")

            # A stopped run must not receive a successful score, even in the UI.
            page.click("#start")
            page.wait_for_function("() => { const k = Number(document.querySelector('#arena').dataset.step); return k >= 2 && k < 100; }")
            page.click("#stop")
            page.wait_for_function("() => document.querySelector('#score').textContent === 'Incomplete'")
            checks.append("early stop: incomplete score and retained trace")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(args.out / "mobile.png"), full_page=True)
            assert not errors, errors
            browser.close()
        results = [replay(path) for path in paths]
        assert len(results) == 4
        assert all(r["participant_kind"] == "synthetic" and not r["human_evidence"]
                   and not r["hardware_verified"] for r in results)
        for path in paths[:3]:
            records = [json.loads(line) for line in (path / "trace.jsonl").read_text().splitlines()]
            assert any(r["applied_action"] == [1.0, 0.0] for r in records), "right key did not reach physics"
            assert any(r["applied_action"] == [0.0, 1.0] for r in records), "W key after resume did not reach physics"
        result = {"browser_checks_passed": True, "checks": checks, "replays": results,
                  "console_errors": errors, "participant_kind": "synthetic",
                  "human_evidence": False, "hardware_verified": False,
                  "human_usability_validated": False, "chromium_executable": args.chromium}
        write_json(args.out / "results.json", result)
        print(json.dumps(result, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
