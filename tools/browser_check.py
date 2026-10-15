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
    config = Config(task="safe_zone", safe_zone_half_width=0.3, seed=19,
                    dt_s=0.02, steps=100, evaluation_start_step=10, evaluation_end_step=100)
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
            page.wait_for_function("() => !document.querySelector('#start').disabled")
            assert page.locator("#task").input_value() == "safe_zone"
            assert page.locator("#zone-size").input_value() == "0.3"
            assert page.locator("#seed").input_value() == "19"
            checks.append("server task/size/seed defaults loaded by real browser")
            for task, condition in ((t, c) for t in ("tracking", "safe_zone")
                                    for c in ("none", "dashboard", "sensory_preview")):
                page.select_option("#task", task)
                page.select_option("#condition", condition)
                assert page.locator("#zone-setting").is_visible() == (task == "safe_zone")
                if task == "safe_zone":
                    page.fill("#zone-size", "0.25")
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
                # Inspect the real canvas raster: target orange is absent in safe_zone.
                orange_pixels = page.evaluate("""() => {
                  const c = document.querySelector('#arena');
                  const pixels = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
                  let n = 0;
                  for (let i = 0; i < pixels.length; i += 4)
                    if (pixels[i] === 206 && pixels[i+1] === 103 && pixels[i+2] === 61) n++;
                  return n;
                }""")
                assert (orange_pixels > 0) == (task == "tracking")
                if task == "safe_zone":
                    # Square top edge for h=.25 and arena A=1 on the 720x620 canvas.
                    pixel = page.evaluate("() => Array.from(document.querySelector('#arena').getContext('2d').getImageData(360, 237, 1, 1).data)")
                    assert pixel == [21, 122, 110, 255]
                page.screenshot(path=str(args.out / f"{task}-{condition}.png"), full_page=True)
                if condition == "none":
                    assert page.locator("#telemetry").is_hidden()
                else:
                    assert page.locator("#telemetry").is_visible()
                assert page.locator("#preview-note").is_visible() == (condition == "sensory_preview")
                page.click("#pause")
                page.keyboard.down("w")
                page.wait_for_timeout(120)
                page.keyboard.up("w")
                button = page.locator('[data-key="ArrowDown"]').bounding_box()
                page.mouse.move(button["x"] + button["width"] / 2, button["y"] + button["height"] / 2)
                page.mouse.down()
                page.wait_for_timeout(100)
                page.mouse.up()
                page.wait_for_function("() => document.querySelector('#status').textContent.startsWith('Trial complete')")
                assert page.locator("#score").inner_text() != "Incomplete"
                assert ("Safe-zone" in page.locator("#objective").inner_text()) == (task == "safe_zone")
                expected_label = "NORMALIZED OUTSIDE DISTANCE" if task == "safe_zone" else "NORMALIZED TRACKING RMSE"
                assert page.locator("#metric-label").inner_text() == expected_label
                checks.append(f"{task}/{condition}: keyboard, pause/resume, feedback visibility, completion")

            # Both objectives preserve interrupted traces, including a browser blur pause.
            for task in ("tracking", "safe_zone"):
                page.select_option("#task", task)
                page.click("#start")
                page.wait_for_function("() => { const k = Number(document.querySelector('#arena').dataset.step); return k >= 2 && k < 100; }")
                page.evaluate("window.dispatchEvent(new Event('blur'))")
                page.wait_for_timeout(100)
                paused_step = page.locator("#arena").get_attribute("data-step")
                page.wait_for_timeout(100)
                assert page.locator("#arena").get_attribute("data-step") == paused_step
                page.click("#stop")
                page.wait_for_function("() => document.querySelector('#score').textContent === 'Incomplete'")
                checks.append(f"{task}: dispatched blur pauses; early stop retains incomplete trace")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(args.out / "mobile.png"), full_page=True)
            assert not errors, errors
            browser.close()
        results = [replay(path) for path in paths]
        assert len(results) == 8
        assert [r["status"] for r in results] == ["complete"] * 6 + ["incomplete_or_invalid"] * 2
        assert all(r["safe_zone_half_width"] == 0.25 for r in results if r["task"] == "safe_zone")
        assert all(r["participant_kind"] == "synthetic" and not r["human_evidence"]
                   and not r["hardware_verified"] for r in results)
        for path in paths[:6]:
            records = [json.loads(line) for line in (path / "trace.jsonl").read_text().splitlines()]
            assert any(r["applied_action"] == [1.0, 0.0] for r in records), "right key did not reach physics"
            assert any(r["applied_action"] == [0.0, 1.0] for r in records), "W key after resume did not reach physics"
            assert any(r["applied_action"] == [0.0, -1.0] for r in records), "pointer control did not reach physics"
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
