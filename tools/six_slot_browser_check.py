"""Real Chromium software workflow check; all responses and controls are synthetic."""

import argparse
import asyncio
import json
from pathlib import Path
import threading

from playwright.async_api import async_playwright
from werkzeug.serving import make_server

from augneta.config import Config
from augneta.recording import replay, software_identity, write_json
from augneta.web import create_app


async def check(out, executable):
    out.mkdir(parents=True, exist_ok=False)
    app = create_app(out/'runs', participant_kind='synthetic', config=Config(
        dt_s=.02, steps=150, evaluation_start_step=10, evaluation_end_step=150,
        sensor_dropout_probability=0, sensor_delay_steps=0))
    server=make_server('127.0.0.1', 0, app, threaded=True)
    worker=threading.Thread(target=server.serve_forever, daemon=True);worker.start()
    url=f'http://127.0.0.1:{server.server_port}'
    errors, checks, paths = [], [], []
    page_errors, failed_requests, accepted_inputs = [], [], []
    expected_console_errors = []
    injecting_error = False
    async def noted(name):
        checks.append(name);print(name,flush=True)
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True, executable_path=executable)
            page=await browser.new_page(viewport={'width':1280,'height':1100}, accept_downloads=True)
            page.on('pageerror',lambda error:page_errors.append(str(error)))
            page.on('console',lambda m:(expected_console_errors if injecting_error else errors).append(m.text) if m.type=='error' else None)
            async def observe(response):
                if response.status >= 400:
                    failed_requests.append({'url':response.url, 'status':response.status, 'body':await response.json()})
                if response.url.endswith('/api/trials') and response.ok:
                    try: paths.append(Path((await response.json())['recording']))
                    except Exception: pass  # Navigated-away response is checked from disk below.
            page.on('response',observe)
            route_mode = 'pass'
            delayed = False
            slow_count = 0
            pending_routes = set()
            seen=asyncio.Event();released=asyncio.Event()
            start_seen=asyncio.Event();start_release=asyncio.Event()
            async def step_route(route):
                nonlocal delayed, slow_count
                pending_routes.add(route)
                mode = route_mode
                try:
                    if mode == 'delay_once' and not delayed:
                        delayed=True; response=await route.fetch(); seen.set()
                        await released.wait(); await route.fulfill(response=response)
                    elif mode == 'slow':
                        slow_count += 1
                        response=await route.fetch(); await asyncio.sleep(.3)
                        await route.fulfill(response=response)
                    elif mode == 'fail':
                        await route.fulfill(status=503, content_type='application/json', body='{"error":"injected transport failure"}')
                    else: await route.continue_()
                finally: pending_routes.discard(route)
            async def start_route(route):
                if route_mode != 'late_start':
                    await route.continue_();return
                response=await route.fetch();start_seen.set();await start_release.wait()
                try: await route.fulfill(response=response)
                except Exception: pass  # navigation destroyed the requesting document
            await page.route('**/api/step',step_route)
            await page.route('**/api/trials',start_route)
            async def settled():
                for _ in range(100):
                    if not pending_routes: return
                    await asyncio.sleep(.02)
                raise AssertionError('test route did not settle')
            await page.goto(url+'/calibration')
            await page.locator('#start-cal').wait_for(state='visible')
            await page.wait_for_function("() => !document.querySelector('#start-cal').disabled")
            await page.locator('#gains input').nth(0).fill('0.5')
            await page.fill('#pulse','200')
            await page.click('#start-cal')
            for phase in ('fit','validation'):
                if phase=='validation': await page.click('#freeze')
                for _ in range(14):
                    await page.click('#present')
                    await page.wait_for_function("() => document.querySelector('#progress-label').textContent.includes('awaiting response')")
                    values=[float(v) for v in await page.locator('.slot span').all_text_contents()]
                    direction=max(range(6),key=lambda i:values[i])
                    normalized=values[direction]/(.5 if direction==0 else 1)
                    await page.wait_for_function("() => !document.querySelector('#response-fields').disabled")
                    if normalized==0: await page.click('#zero')
                    else:
                        await page.select_option('#response-direction',str(direction))
                        await page.select_option('#response-level','1' if normalized<.375 else '2')
                        await page.click('#respond')
                await page.wait_for_function("() => document.querySelector('#progress-label').textContent.includes('review') || document.querySelector('#progress-label').textContent.includes('complete')")
            await page.wait_for_function("() => !document.querySelector('#export-session').disabled")
            async with page.expect_download() as download:
                await page.click('#save-profile')
            candidate=out/'candidate.json';await (await download.value).save_as(candidate)
            async with page.expect_download() as download:
                await page.click('#export-session')
            calibration=out/'calibration.json';await (await download.value).save_as(calibration)
            saved=json.loads(calibration.read_text())
            assert saved['state']=='complete' and saved['participant_kind']=='synthetic'
            assert all(len(saved['responses'][phase])==14 for phase in ('fit','validation'))
            await page.set_viewport_size({'width':390,'height':844})
            assert await page.evaluate('() => document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(out/'calibration-mobile.png'),full_page=True)
            await noted('real calibration UI: 14 fit + 14 validation responses, frozen candidate/session downloads, mobile overflow')

            await page.set_viewport_size({'width':1280,'height':1100})
            await page.goto(url+'/')
            await page.wait_for_function("() => !document.querySelector('#start').disabled")
            await page.select_option('#condition','six_slot_dashboard')
            assert await page.locator('#start').is_disabled()
            await page.set_input_files('#candidate-file',candidate)
            await page.wait_for_function("() => !document.querySelector('#start').disabled")
            assert json.loads(candidate.read_text())['profile_sha256'] in await page.locator('#candidate-status').inner_text()

            async def active():
                await page.wait_for_function("() => Number(document.querySelector('#arena').dataset.step) >= 2 && Number(document.querySelector('#arena').dataset.step) < 150")
            async def blank():
                assert await page.locator('#telemetry').is_hidden()
                assert await page.evaluate("() => !document.querySelector('#feedback').getContext('2d').getImageData(0,0,360,300).data.some(v=>v)")
            async def stop():
                await page.click('#stop')
                await page.wait_for_function("() => document.querySelector('#status').textContent.startsWith('Trial stopped')")
                assert await page.locator('#score').inner_text()=='Incomplete'
                await blank()

            for task in ('tracking','safe_zone'):
                for condition in ('six_slot_dashboard','six_slot_preview'):
                    await page.select_option('#task',task);await page.select_option('#condition',condition)
                    await page.click('#start');await active()
                    assert await page.locator('#candidate-file').is_disabled()
                    def accepts(action):
                        return lambda response: response.url.endswith('/api/step') and response.ok and response.request.post_data_json['action']==action
                    for key, action in [('ArrowRight',[1,0]),('w',[0,1])]:
                        try:
                            async with page.expect_response(accepts(action),timeout=2000) as accepted:
                                await page.keyboard.down(key)
                            response=await accepted.value
                            assert (await response.json())['visible']['step']==response.request.post_data_json['expected_step']+1
                            accepted_inputs.append({'task':task,'condition':condition,'input':key,'request':response.request.post_data_json})
                        finally: await page.keyboard.up(key)
                    pointer=page.locator('[data-key="ArrowDown"]')
                    await pointer.scroll_into_view_if_needed();await pointer.hover()
                    button=await pointer.bounding_box()
                    x,y=button['x']+button['width']/2,button['y']+button['height']/2
                    assert 0<=x<1280 and 0<=y<1100,button
                    hit=await page.evaluate("({x,y}) => document.elementFromPoint(x,y)?.closest('button')?.dataset.key",{'x':x,'y':y})
                    assert hit=='ArrowDown',(button,hit)
                    try:
                        async with page.expect_response(accepts([0,-1]),timeout=2000) as accepted:
                            await page.mouse.move(x,y);await page.mouse.down()
                        response=await accepted.value
                        assert (await response.json())['visible']['step']==response.request.post_data_json['expected_step']+1
                        accepted_inputs.append({'task':task,'condition':condition,'input':'pointer ArrowDown','box':button,'hit':hit,'request':response.request.post_data_json})
                    finally: await page.mouse.up()
                    await page.wait_for_function("() => document.querySelector('#feedback').dataset.phase === 'pulse'")
                    pulse_y=await page.locator('[data-key="ArrowDown"]').evaluate('(el) => el.getBoundingClientRect().y + scrollY')
                    await page.screenshot(path=str(out/f'{task}-{condition}.png'),full_page=True)
                    await page.wait_for_function("() => document.querySelector('#feedback').dataset.phase === 'gap'")
                    await blank()
                    gap_y=await page.locator('[data-key="ArrowDown"]').evaluate('(el) => el.getBoundingClientRect().y + scrollY')
                    assert abs(pulse_y-gap_y)<1,(pulse_y,gap_y)
                    await page.click('#pause')
                    await page.wait_for_function("() => !document.querySelector('#pause').disabled && document.querySelector('#pause').textContent === 'Resume'")
                    paused=await page.locator('#arena').get_attribute('data-step')
                    await page.wait_for_timeout(180)
                    assert await page.locator('#arena').get_attribute('data-step')==paused
                    await blank();await page.click('#pause')
                    await page.wait_for_function("() => document.querySelector('#status').textContent.startsWith('Trial complete')")
                    assert await page.locator('#score').inner_text()!='Incomplete'
                    await blank()
                    await noted(f'{task}/{condition}: import frozen, direct arrow/W/pointer, common gap, pause/resume, completion clear')
            for task in ('tracking','safe_zone'):
                await page.select_option('#task',task);await page.click('#start');await active();await stop()
                await noted(f'{task}: stopped partial trace without score')

            # Delay a real server response, pause then resume while that reply is pending.
            route_mode = 'delay_once'
            await page.click('#start');await seen.wait()
            await page.click('#pause')
            await page.wait_for_function("() => !document.querySelector('#pause').disabled")
            await blank()
            await page.click('#pause')
            await page.wait_for_function("() => !document.querySelector('#pause').disabled")
            await page.wait_for_timeout(250);await blank()  # resumed pulse expires even with no step replies
            released.set();await page.wait_for_timeout(150)
            await page.wait_for_function("() => Number(document.querySelector('#arena').dataset.step)>2")
            await stop();await settled();route_mode = 'pass'
            await noted('delayed reply across pause/resume cannot revive old pulse; fresh stepping resumes')

            # Every step reply arrives too late for a pulse: both views stay blank.
            for condition in ('six_slot_dashboard','six_slot_preview'):
                route_mode = 'slow'
                before_slow = slow_count
                await page.select_option('#condition',condition);await page.click('#start')
                await page.wait_for_timeout(850);await blank();await stop()
                await settled();assert slow_count - before_slow >= 2
                route_mode = 'pass'
            await noted('both views suppress slow replies and finite pulse expiry')

            # A deliberately failed request clears both payload and status, requires Stop.
            injecting_error = True
            route_mode = 'fail'
            await page.click('#start')
            await page.wait_for_function("() => document.querySelector('#status').textContent.includes('Paused after error')")
            await blank();assert await page.locator('#pause').is_disabled()
            await stop();await settled();route_mode = 'pass'
            injecting_error = False
            await noted('injected HTTP failure clears presentation and requires explicit Stop')

            # Real navigation while creation response is outstanding; known start ID cancels it.
            route_mode = 'late_start'
            await page.click('#start');await start_seen.wait()
            await page.goto(url+'/calibration');start_release.set()
            await page.wait_for_timeout(200)
            route_mode = 'pass'
            assert await page.locator('.slot.active').count()==0
            await noted('actual page navigation cancels pending start; no late task output on calibration page')
            await page.goto(url+'/');await page.wait_for_function("() => !document.querySelector('#start').disabled")
            await page.select_option('#condition','six_slot_preview');await page.set_input_files('#candidate-file',candidate)
            await page.wait_for_function("() => !document.querySelector('#start').disabled")
            await page.click('#start');await active()
            await page.goto(url+'/calibration');await page.wait_for_timeout(200)
            await noted('actual navigation stops active task and preserves partial recording')

            await page.goto(url+'/');await page.wait_for_function("() => !document.querySelector('#start').disabled")
            await page.select_option('#condition','six_slot_dashboard');await page.set_input_files('#candidate-file',candidate)
            await page.wait_for_function("() => !document.querySelector('#start').disabled")
            await page.set_viewport_size({'width':390,'height':844})
            assert await page.evaluate('() => document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(out/'task-mobile.png'),full_page=True)
            await noted('task mobile candidate import and layout have no document overflow')
            # A pause may overtake an already-sent step. That exact rejected
            # epoch is intended API behavior, and Chromium logs its HTTP 400.
            rejected = [r for r in failed_requests if r['status']==400]
            injected = [r for r in failed_requests if r['status']==503]
            assert all(r['url'].endswith('/api/step') and r['body']=={'error':'stale presentation epoch'} for r in rejected),failed_requests
            assert all(r['body']=={'error':'injected transport failure'} for r in injected)
            assert len(failed_requests)==len(rejected)+len(injected)
            assert len(errors)==len(rejected) and all('status of 400' in m for m in errors),errors
            assert len(expected_console_errors)==len(injected)==1 and all('503' in m for m in expected_console_errors)
            assert not page_errors,page_errors
            await browser.close()
        # Include pending-start records whose response disappeared with navigation.
        paths=sorted((out/'runs').glob('*/*/metadata.json'))
        results=[replay(p.parent) for p in paths]
        assert len(results)==12, len(results)
        assert sum(r['status']=='complete' for r in results)==4
        for p in paths:
            meta=json.loads(p.read_text())
            assert meta['candidate']['profile_sha256']==json.loads(candidate.read_text())['profile_sha256']
            if json.loads((p.parent/'summary.json').read_text())['status']=='complete':
                records=[json.loads(x) for x in (p.parent/'trace.jsonl').read_text().splitlines()]
                for action in ([1.,0.],[0.,1.],[0.,-1.]):
                    assert any(r['action']==r['applied_action']==action for r in records),action
        write_json(out/'results.json',{'checks':checks,'replays':results,'unexpected_console_errors':[], 'page_errors':page_errors,
            'expected_stale_request_console_errors':errors,'observed_failed_requests':failed_requests,'accepted_inputs':accepted_inputs,
            'expected_console_errors_from_injected_503':expected_console_errors,
            'source':software_identity(),'browser':'real headless Chromium','chromium_executable':executable,
            'participant_kind':'synthetic','human_evidence':False,'hardware_verified':False,
            'human_usability_validated':False})
        print(f'PASS: {len(checks)} browser checks; {len(results)} exact replays',flush=True)
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    args=parser.parse_args()
    asyncio.run(check(args.out,args.chromium))
