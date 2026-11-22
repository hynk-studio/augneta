"""Exercise the randomized first session or a two-visit self-check through the browser."""

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from playwright.async_api import async_playwright
from werkzeug.serving import make_server, WSGIRequestHandler

from app import create_app
from study import PRACTICE_SLOTS, Study


class QuietRequests(WSGIRequestHandler):
    def log_request(self, *args):
        pass


async def play_gates(page, phase, total, index, out):
    items = []
    await page.wait_for_selector(f"body[data-phase={phase}]")
    for i in range(total):
        saved = await page.evaluate("fetch('/api/session').then(r=>r.json())")
        assert saved["phase"] == phase and saved["index"] == i
        assert set(saved["item"]) == {"geometry","goal","signal"}
        assert not {"answer","score","correct","result"} & saved.keys()
        items.append(saved["item"])
        assert await page.locator("#signal-title").text_content() == "고정 부호"
        assert await page.locator("#score").is_hidden() and await page.locator("#review").is_hidden()
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if i == 0:
            await page.screenshot(path=out / f"{phase}-{index}.png")
        if i == 4 and index == 1:
            await page.reload()
            await page.wait_for_selector(f"body[data-phase={phase}]")
            assert saved == await page.evaluate("fetch('/api/session').then(r=>r.json())")
        await page.locator("#left").click()
        await page.locator("#choose").click()
        await page.wait_for_function("""([phase, i, total]) => document.body.dataset.phase !== phase ||
              document.getElementById('status').textContent.endsWith((i + 2) + ' / ' + total)""",
                                     arg=[phase, i, total])
    return items


async def exercise(browser, base_url, width, index, out, self_check=False):
    context = await browser.new_context(viewport={"width":width,"height":780}, accept_downloads=True)
    page = await context.new_page()
    page.set_default_timeout(12000)
    errors, paths = [], set()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda req: paths.add(req.url.removeprefix(base_url)))
    await page.goto(base_url + "/")
    if self_check:
        await page.locator("#exposure").select_option("rule")
    await page.locator("#start").click()
    for slot in PRACTICE_SLOTS:
        await page.locator(f'[data-slot="{slot}"]').click()
        await page.locator("#practice-next").click()
    for block in (1, 2):
        if index == 2 and block == 1:
            # Simulate a focus loss after Begin is sent, before its response arrives.
            async def blur_while_begin_pending(route):
                if route.request.post_data_json["action"] == "begin":
                    await page.evaluate("window.dispatchEvent(new Event('blur'))")
                await route.continue_()
            await page.route("**/api/event", blur_while_begin_pending)
        await page.locator("#train-begin").click()
        await page.wait_for_selector("body[data-phase=training]")
        if index == 2 and block == 1:
            await page.unroute("**/api/event", blur_while_begin_pending)
            assert not await page.locator("#field").is_visible()
            await page.get_by_role("button", name="훈련 계속").click()
        # Read the displayed training mode and exercise physical input via real UI handlers.
        mode = await page.locator("#signal-title").inner_text()
        await page.locator("body").press("ArrowRight")
        await page.keyboard.down("ArrowUp")
        await page.wait_for_timeout(350)
        await page.keyboard.up("ArrowUp")
        if index == 0 and block == 1:
            await page.locator("#pause").click()
            await page.wait_for_timeout(150)
            assert not await page.locator("#field").is_visible()
            before = await page.locator("#time").inner_text()
            await page.wait_for_timeout(220)
            assert before == await page.locator("#time").inner_text()
            await page.reload()
            await page.get_by_role("button", name="훈련 계속").wait_for()
            assert not await page.locator("#field").is_visible()
            await page.get_by_role("button", name="훈련 계속").click()
        if block == 1:
            await page.screenshot(path=out / f"training-{index}.png")
        phase = "training_ready" if block == 1 else "transfer_ready"
        await page.wait_for_selector(f"body[data-phase={phase}]",timeout=75000)
    await page.locator("#gate-begin").click()
    transfer_items = await play_gates(page, "transfer", 16, index, out)
    await page.wait_for_selector("body[data-phase=reflection]")
    assert "result" not in await page.evaluate("fetch('/api/session').then(r=>r.json())")
    await page.locator("#finish").click()
    if self_check:
        await page.wait_for_selector("body[data-phase=return_wait]")
        assert not await page.locator("#score").is_visible()
        await context.clear_cookies()
        await page.set_viewport_size({"width":360, "height":780})
        await page.reload()
        await page.locator("#return-begin").click()
        await play_gates(page, "retention", 16, index, out)
        await page.locator("#diagnostic-begin").click()
        await play_gates(page, "diagnostic", 8, index, out)
        await page.wait_for_selector("body[data-phase=return_reflection]")
        await page.locator("#finish").click()
    await page.wait_for_selector("body[data-phase=complete]")
    assert await page.locator("#score").text_content() == "8 / 16"
    async with page.expect_download() as download:
        await page.locator("#download").click()
    payload = json.loads((await (await download.value).path()).read_text())
    assert payload["practice_correct"] == 8 and sum(x["steps"] for x in payload["training"]) == 1200
    assert mode == {"code":"고정 부호","arrow":"흐름 화살표"}[payload["arm"]]
    assert not errors and not any("item-key" in p or "form-" in p or "/results/" in p for p in paths)
    assert not payload["human_evidence"] and not payload["hardware_verified"]
    if self_check:
        assert payload["started_before_target"] and payload["prior_exposure"] == "rule"
        assert (payload["retention"]["correct"], payload["diagnostic"]["correct"]) == (8, 4)
        assert (await download.value).suggested_filename == "augneta-p1-self-check.json"
        assert await page.locator("#again").is_hidden() and await page.locator("#return-score").is_visible()
        assert len(await page.locator("#review li").all()) == 40
    await context.close()
    return payload, transfer_items


async def run(args, database):
    server = make_server("127.0.0.1",0, create_app(database,"synthetic",self_check=args.self_check), threaded=True, request_handler=QuietRequests)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        async with async_playwright() as pw:
            async with await pw.chromium.launch(executable_path=args.chromium) as browser:
                if args.self_check:
                    result, _ = await exercise(browser, f"http://127.0.0.1:{server.server_port}", 1050, 0, args.out, True)
                    summary = {"participant_kind":"synthetic", "human_evidence":False, "chromium":browser.version,
                               "viewports_px":[1050,360], "training_steps":sum(b["steps"] for b in result["training"]),
                               "first_correct":result["correct"], "retention_correct":result["retention"]["correct"],
                               "diagnostic_correct":result["diagnostic"]["correct"], "scripted_gate_policy":"always_left",
                               "actual_interval_seconds":result["actual_interval_seconds"],
                               "early_return":result["started_before_target"], "checked_download":True}
                    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
                    print(json.dumps(summary, indent=2))
                    return
                work = [exercise(browser, f"http://127.0.0.1:{server.server_port}", width, i, args.out)
                        for i,width in enumerate((1050,360,360,1050))]
                runs = await asyncio.gather(*work)
                version = browser.version
        by_cell = {(p["arm"],p["form"]): items for p, items in runs}
        assert len(by_cell) == 4 and all(by_cell["code",f] == by_cell["arrow",f] for f in ("A","B"))
        summary = Study(database,"synthetic").summary()
        assert all(g["mean_first_block_accuracy"] == .5 and g["sessions_finished"] == 2 for g in summary["arms"].values())
        summary["chromium"] = version
        summary["scripted_gate_policy"] = "always_left"
        summary["completed_cells"] = sorted([
            {"arm":p["arm"], "form":p["form"], "correct":p["correct"], "total":p["total"],
             "foreground_s":[round(b["foreground_s"],2) for b in p["training"]]} for p,_ in runs
        ],key=lambda x:(x["arm"],x["form"]))
        print(json.dumps(summary,indent=2))
        (args.out / "summary.json").write_text(json.dumps(summary,indent=2) + "\n")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True,help="New directory for screenshots and aggregate results")
    parser.add_argument("--chromium",help="Optional Chromium or headless shell executable")
    parser.add_argument("--self-check",action="store_true",help="Check both visits and download in the single-operator mode")
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    with TemporaryDirectory() as tmp:
        asyncio.run(run(args, Path(tmp)/"synthetic.sqlite3"))
