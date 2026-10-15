// Behavioral DOM harness backed by the real Flask API; no browser/layout claims.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {readFileSync} from 'node:fs';
import readline from 'node:readline';
import vm from 'node:vm';

const python = process.env.AUGNETA_TEST_PYTHON || 'python';
const child = spawn(python, ['-u', '-c', String.raw`
import json, sys, tempfile
from augneta import web
from augneta.calibration_session import CalibrationSession
clock=[0.0]
web.CalibrationSession=lambda *args: CalibrationSession(*args, clock=lambda: clock[0])
with tempfile.TemporaryDirectory() as root:
 app=web.create_app(root,participant_kind='synthetic')
 app.config['TESTING']=True
 client=app.test_client()
 for line in sys.stdin:
  data=json.loads(line); clock[0]=data['now']/1000
  r=client.open(data['path'],method=data['method'],json=data.get('body'))
  print(json.dumps({'status':r.status_code,'body':r.get_json()}),flush=True)
`], {stdio:['pipe','pipe','inherit']});
const waiting = [];
const lines = readline.createInterface({input:child.stdout});
lines.on('line', line => waiting.shift()?.resolve(JSON.parse(line)));
child.on('exit', code => { while(waiting.length) waiting.shift().reject(new Error(`API process exited ${code}`)); });
let now = 0, timerID = 0;
const timers = new Map(), downloads = new Map();
const setTimer = (fn, ms) => { const id = ++timerID; timers.set(id,{fn,at:now+ms}); return id; };
function advance(ms) {
  now += ms;
  for (const [id,t] of [...timers]) if (t.at <= now) { timers.delete(id); t.fn(); }
}
function rpc(path, options = {}) {
  return new Promise((resolve,reject) => {
    waiting.push({resolve,reject});
    child.stdin.write(JSON.stringify({path,method:options.method||'GET',body:options.body?JSON.parse(options.body):undefined,now})+'\n');
  });
}
let holdPath = null, releaseHeld = null, heldReceived = false;
async function fetchAPI(path, options) {
  const response = await rpc(path, options);
  if (holdPath === path) {
    holdPath = null; heldReceived = true;
    await new Promise(resolve => { releaseHeld = resolve; });
  }
  return {ok:response.status < 400,status:response.status,json:async()=>response.body};
}
class Element {
  constructor(tag='div') {
    this.tag=tag; this.children=[]; this.value=''; this.disabled=false; this.hidden=false;
    this.dataset={}; this.textContent=''; this.files=[]; this.classes=new Set();
    this.classList={add:v=>this.classes.add(v),remove:v=>this.classes.delete(v),
      toggle:(v,on)=>on?this.classes.add(v):this.classes.delete(v),contains:v=>this.classes.has(v)};
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=[...nodes]; this.value=''; }
  add(option) { this.children.push(option); if(this.children.length===1)this.value=String(option.value); }
  createTHead() { const h=new Element('thead'); this.append(h); return h; }
  insertRow() { const r=new Element('tr'); this.append(r); return r; }
  insertCell() { const c=new Element('td'); this.append(c); return c; }
  click() { return this.onclick?.(); }
}
const html=readFileSync(new URL('../src/augneta/static/calibration.html',import.meta.url),'utf8');
const elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
assert.equal(elements.size,[...html.matchAll(/id="([^"]+)"/g)].length,'duplicate IDs');
const events=new Map();
const document={hidden:false,getElementById:id=>{
  assert.ok(elements.has(id),`missing HTML element ${id}`); return elements.get(id);
},createElement:tag=>new Element(tag),addEventListener:(name,fn)=>events.set(name,fn)};
const context=vm.createContext({document,fetch:fetchAPI,structuredClone,Blob,
  Option:class{constructor(text,value){this.text=text;this.value=value;}},
  URL:{createObjectURL:blob=>{const id=`blob:${downloads.size}`;downloads.set(id,blob);return id;},revokeObjectURL:()=>{}},
  setTimeout:setTimer,clearTimeout:id=>timers.delete(id),console});
const get=id=>elements.get(id);
const state=()=>vm.runInContext('session',context);
const pause=()=>new Promise(resolve=>setTimeout(resolve,1));
async function until(check) {
  for(let i=0;i<2000;i++){if(check())return;await pause();}
  throw new Error('Client did not reach expected state');
}
async function click(id) { assert.equal(get(id).disabled,false,`${id} disabled`); await get(id).click(); }

try {
  vm.runInContext(readFileSync(new URL('../src/augneta/static/calibration.js',import.meta.url),'utf8'),context);
  await until(()=>!vm.runInContext('busy',context));
  assert.match(get('cal-status').textContent,/Ready/);
  await click('start-cal');
  for(const phase of ['fit','validation']) {
    if(phase==='validation') {
      get('gains').children.forEach(label=>{label.children[0].value='0.5';});
      await click('freeze');
      assert.equal(get('profile-fields').disabled,true);
    }
    for(let i=0;i<state().phase_total;i++) {
      await click('present');
      assert.equal(get('response-fields').disabled,true);
      const slots=[...get('left-slots').children,...get('right-slots').children];
      const levels=slots.map(slot=>Number(slot.children[0].textContent));
      const direction=levels.indexOf(Math.max(...levels));
      advance(300);
      assert.ok(slots.every(slot=>!slot.classList.contains('active')));
      assert.equal(get('response-fields').disabled,false);
      if(Math.max(...levels)===0) await click('zero');
      else {
        get('response-direction').value=String(direction);
        get('response-level').value=String(Math.round(Math.max(...levels)/(phase==='fit'?.25:.125)));
        await click('respond');
      }
    }
  }
  assert.equal(state().state,'complete');
  assert.equal(state().reports.validation.joint_accuracy,1);
  await click('export-session');
  const record=JSON.parse(await [...downloads.values()].at(-1).text());
  assert.equal(record.responses.fit.length,14); assert.equal(record.responses.validation.length,14);
  get('profile-file').files=[{size:1000,text:async()=>JSON.stringify(record)}];
  await get('profile-file').onchange();
  await click('start-cal');
  assert.deepEqual(Array.from(state().profile.gains),[.5,.5,.5,.5,.5,.5]);
  // Stop an in-flight presentation and release its response after the tab hides.
  holdPath='/api/calibration/present';
  const pending=click('present');
  await until(()=>heldReceived);
  document.hidden=true; events.get('visibilitychange')();
  await until(()=>state().state==='stopped');
  releaseHeld(); await pending;
  advance(1000);
  assert.equal(state().state,'stopped');
  assert.ok([...get('left-slots').children,...get('right-slots').children].every(slot=>!slot.classList.contains('active')));
  assert.equal(get('response-fields').disabled,true);
  console.log('PASS: real Flask API + DOM harness: 28 responses, freeze, export/import, stop, late presentation after tab hide');
  console.log('No real browser, layout, physical timing, or tactile perception was tested.');
} finally { child.stdin.end(); lines.close(); child.kill(); }
