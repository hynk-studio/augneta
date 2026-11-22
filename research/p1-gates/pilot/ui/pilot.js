import {circle, drawCode, drawMap, prompts, qualityText} from "/display.js";

const el = id => document.getElementById(id);
const sections = ["welcome", "practice", "training-ready", "live", "transfer-ready", "return-wait",
  "diagnostic-ready", "reflection", "complete"];
const gateTitles = {transfer:"첫 관문 검사", retention:"두 번째 방문 · 첫 묶음", diagnostic:"두 번째 방문 · 마지막 묶음"};
const directions = ["오른쪽", "오른쪽 위", "위", "왼쪽 위", "왼쪽", "왼쪽 아래", "아래", "오른쪽 아래"];
const keys = new Map([["ArrowLeft","left"],["KeyA","left"],["ArrowRight","right"],["KeyD","right"],
  ["ArrowUp","up"],["KeyW","up"],["ArrowDown","down"],["KeyS","down"]]);
const controls = new Map();
let state, busy = false, running = false, timer, lastTick, nextTickAt, selected = null;
let pauseCount = 0;

async function api(path, body) {
  const options = body === undefined ? {} : {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "요청을 처리할 수 없습니다.");
  return data;
}

function pause() {
  pauseCount++;
  running = false;
  clearTimeout(timer);
  controls.clear();
  paintPad();
  el("pause").textContent = "훈련 계속";
  if (state?.phase === "training") {
    el("field").hidden = true;
    el("frozen").hidden = false;
  }
}

async function send(path, body) {
  if (busy) return false;
  busy = true;
  try {
    state = await api(path, body);
    el("error").hidden = true;
    render();
    return true;
  } catch (error) {
    pause();
    try { state = await api("/api/session"); render(); } catch { /* A reload can recover the saved state. */ }
    el("error").textContent = `진행 상태를 확인해 주세요. ${error.message}`;
    el("error").hidden = false;
    return false;
  } finally { busy = false; }
}

function event(action, value = null) {
  return send("/api/event", {revision:state.revision, action, value});
}

function paintPad() {
  const held = new Set(controls.values());
  document.querySelectorAll("[data-key]").forEach(b => b.classList.toggle("active", held.has(b.dataset.key)));
}

function resume() {
  if (busy || running || state.phase !== "training" || document.hidden) return;
  running = true;
  lastTick = performance.now();
  nextTickAt = lastTick + state.dt_ms;
  el("field").hidden = false;
  el("frozen").hidden = true;
  el("pause").textContent = "일시정지";
  timer = setTimeout(tick, state.dt_ms);
}

async function tick() {
  if (!running || document.hidden) { pause(); return; }
  const now = performance.now();
  if (now < nextTickAt) {
    timer = setTimeout(tick, Math.ceil(nextTickAt - now));
    return;
  }
  const held = new Set(controls.values());
  const action = [Number(held.has("right")) - Number(held.has("left")), Number(held.has("up")) - Number(held.has("down"))];
  const active_ms = now - lastTick;
  lastTick = now;
  if (!await event("steer", {action, active_ms}) || !running) return;
  if (state.phase !== "training") { pause(); return; }
  // Never apply an action to unseen catch-up frames. A slow request lengthens the actual exposure.
  const received = performance.now();
  nextTickAt += state.dt_ms;
  if (received >= nextTickAt) nextTickAt = received + state.dt_ms;
  timer = setTimeout(tick, Math.ceil(nextTickAt - received));
}

function drawTraining(canvas, position) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0,0,600,290);
  const size = 264, x0 = 300 - size / 2, y0 = 13;
  ctx.fillStyle = "#edf3ea"; ctx.fillRect(x0,y0,size,size);
  ctx.strokeStyle = "#c9d7c9"; ctx.lineWidth = 1;
  for(let i = 0; i <= 4; i++) {
    const k = i * size / 4;
    ctx.beginPath(); ctx.moveTo(x0+k,y0); ctx.lineTo(x0+k,y0+size);
    ctx.moveTo(x0,y0+k); ctx.lineTo(x0+size,y0+k); ctx.stroke();
  }
  circle(ctx,300,145,12,null,"#a65d34");
  const x = 300 + position[0]*size/2, y = 145-position[1]*size/2;
  circle(ctx,x,y,7,"#196557",null);
  canvas.setAttribute("aria-label", `중앙 표적과 부표. 부표 좌표 ${position.map(v=>v.toFixed(2)).join(", ")}`);
}

function drawArrow(canvas, channels) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0,0,180,180);
  circle(ctx,90,90,60,null,"#c8d6cb");
  const level = Math.max(...channels);
  if (level) {
    const slot = channels.indexOf(level), length = 60 * level;
    ctx.save(); ctx.translate(90,90); ctx.rotate(-slot*Math.PI/4);
    ctx.beginPath(); ctx.moveTo(0,0); ctx.lineTo(length,0);
    ctx.strokeStyle="#146655"; ctx.lineWidth=4; ctx.stroke();
    ctx.beginPath(); ctx.moveTo(length,0); ctx.lineTo(length-9,-6); ctx.lineTo(length-9,6);
    ctx.closePath(); ctx.fillStyle="#146655"; ctx.fill(); ctx.restore();
  }
  canvas.setAttribute("aria-label", level ? `흐름 화살표 ${directions[channels.indexOf(level)]}, 세기 ${level*4}/4` : "세기 0/4");
}

function show(section, status) {
  for (const name of sections) el(name).hidden = name !== section;
  if (el("status").textContent !== status) el("status").textContent = status;
}

function render() {
  const s = state, p = s.phase;
  document.body.dataset.phase = p;
  if (p === "welcome") {
    show("welcome","첫 세션"); drawCode(el("example-code"), [0,.75,0,0,0,0,0,0]);
    el("personal-intro").hidden = !s.self_check;
  } else if (p === "practice" || p === "practice_feedback") {
    show("practice",`방향 연습 · ${s.index+1} / ${s.total}`);
    const feedback = p === "practice_feedback";
    const channels = feedback ? directions.map((_,i)=>i === s.expected_slot ? .75 : 0) : s.channels;
    drawCode(el("practice-code"),channels);
    document.querySelectorAll("#direction-buttons button").forEach(b => { b.disabled = feedback; });
    el("practice-feedback").textContent = feedback ? `${s.chosen_slot === s.expected_slot ? "맞았습니다." : "이 부호를 다시 확인하세요."} 물이 흐르는 쪽은 ${directions[s.expected_slot]}입니다.` : "";
    el("practice-next").hidden = !feedback;
  } else if (p === "training_ready") {
    pause();
    show("training-ready",`부표 훈련 · ${s.block} / ${s.blocks}`);
    el("arm-description").textContent = s.arm === "code" ? "켜진 점으로 흐름을 표시합니다. 한 구간은 30초입니다." :
      "화살표의 방향과 길이로 흐름을 표시합니다. 한 구간은 30초입니다.";
  } else if (p === "training") {
    show("live",`부표 훈련 · ${s.block} / ${s.blocks}`);
    el("field").hidden = !running; el("frozen").hidden = running;
    el("controls").hidden = false; el("gate-controls").hidden = true;
    el("live-title").textContent = "부표를 중앙에 유지하세요";
    el("time").textContent = `${((s.steps-s.step)*s.dt_ms/1000).toFixed(1)}초`;
    el("signal-title").textContent = s.arm === "code" ? "고정 부호" : "흐름 화살표";
    el("pause").textContent = running ? "일시정지" : "훈련 계속";
    drawTraining(el("map"),s.position);
    (s.arm === "code" ? drawCode : drawArrow)(el("ring"),s.signal.channels);
    el("quality").textContent = qualityText(s.signal);
  } else if (p === "transfer_ready") {
    pause(); show("transfer-ready","첫 관문 검사");
    if (s.self_check) el("first-instructions").textContent = "총 16문항입니다. 확정한 선택은 되돌릴 수 없습니다. 점수는 두 번째 방문을 마치면 볼 수 있습니다.";
  } else if (p === "return_wait") {
    show("return-wait","첫 방문 완료");
    const target = new Date(s.target_at * 1000).toLocaleString("ko-KR");
    el("return-time").textContent = `다음 방문 목표 시각은 ${target}입니다. 일찍 또는 늦게 시작해도 실제 간격이 기록됩니다.`;
  } else if (p === "diagnostic_ready") {
    show("diagnostic-ready","두 번째 방문 · 첫 묶음 완료");
  } else if (p in gateTitles) {
    show("live",`${gateTitles[p]} · ${s.index+1} / ${s.total}`);
    el("field").hidden = false; el("frozen").hidden = true;
    el("time").textContent = ""; el("controls").hidden = true; el("gate-controls").hidden = false;
    el("live-title").textContent = prompts[s.item.goal]; el("signal-title").textContent="고정 부호";
    drawMap(el("map"),s.item.geometry); drawCode(el("ring"),s.item.signal.channels);
    el("quality").textContent=qualityText(s.item.signal);
    selectGate(null);
  } else if (p === "reflection" || p === "return_reflection") {
    show("reflection", "관문 선택 완료");
    const note = el("note");
    if (note.dataset.phase !== p) { note.value = ""; note.dataset.phase = p; }
    el("finish").textContent = s.self_check && p === "reflection" ? "첫 방문 저장" : "결과 보기";
  } else if (p === "complete") {
    show("complete",s.self_check ? "개인 점검 완료" : "리허설 완료");
    const r=s.result;
    el("result-title").textContent = s.self_check ? "두 방문의 개인 점검 결과" : "첫 관문 검사 결과";
    el("score").textContent=`${r.correct} / ${r.total}`;
    el("score-detail").textContent=`첫 검사 · 도착 ${r.by_goal.reach.correct}/${r.by_goal.reach.total} · 방류 ${r.by_goal.release.correct}/${r.by_goal.release.total} · 방향 연습 ${r.practice_correct}/${r.practice_total}`;
    el("training-detail").textContent=`${r.arm === "code" ? "고정 부호" : "화살표"} 훈련 · ${r.form}형 · 훈련 화면 진행 시간 ${r.training.map(b=>b.foreground_s.toFixed(1)+"초").join(" + ")}`;
    const blocks = [["첫 검사", r.items]];
    el("again").hidden = Boolean(s.self_check);
    el("return-score").hidden = !s.self_check;
    if (s.self_check) {
      el("return-score").textContent = `재검사 ${r.retention.correct}/${r.retention.total} · 배치 진단 ${r.diagnostic.correct}/${r.diagnostic.total} · 실제 간격 ${(r.actual_interval_seconds/3600).toFixed(2)}시간`;
      blocks.push(["재검사", r.retention.items], ["배치 진단", r.diagnostic.items]);
    }
    const nodes = blocks.flatMap(([title, items]) => items.map(item=>{
      const li=document.createElement("li"), label=v=>v==="right"?"오른쪽":"왼쪽";
      li.textContent=`${title} ${item.item} · ${item.goal==="reach"?"도착":"방류"} · 선택 ${label(item.side)} · 정답 ${label(item.answer)}`;
      return li;
    }));
    el("review").replaceChildren(...nodes);
  }
}

function selectGate(side) {
  selected = side;
  for (const s of ["left","right"]) el(s).setAttribute("aria-pressed",String(s===side));
  el("choose").disabled = side === null;
}

for (const slot of [3,2,1,4,null,0,5,6,7]) {
  const node = document.createElement(slot === null ? "span" : "button");
  if (slot !== null) {
    node.textContent = directions[slot]; node.dataset.slot = String(slot);
    node.addEventListener("click",()=>event("identify",slot));
  }
  el("direction-buttons").append(node);
}
el("start").onclick = ()=>send("/api/start",state.self_check ? {exposure:el("exposure").value} : {});
el("practice-next").onclick = ()=>event("continue");
el("train-begin").onclick = async()=>{
  const before = pauseCount;
  if (await event("begin") && before === pauseCount) resume();
};
el("pause").onclick = ()=>{ if (running) pause(); else resume(); };
for (const side of ["left","right"]) el(side).onclick=()=>selectGate(side);
el("choose").onclick=()=>{ if (selected !== null) event("choose",selected); };
el("gate-begin").onclick=()=>event("begin");
el("return-begin").onclick=()=>event("begin");
el("diagnostic-begin").onclick=()=>event("begin");
el("finish").onclick=()=>event("finish",el("note").value);
el("again").onclick=async()=>{ if (await send("/api/new",{})) el("note").value=""; };
el("download").onclick=()=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(state.result,null,2)],{type:"application/json"}));
  const link=document.createElement("a"); link.href=url;
  link.download=state.self_check ? "augneta-p1-self-check.json" : "augneta-p1-session.json"; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener("keydown",e=>{
  if (running && keys.has(e.code)) { e.preventDefault(); controls.set(e.code,keys.get(e.code)); paintPad(); }
});
window.addEventListener("keyup",e=>{ if (controls.delete(e.code)) paintPad(); });
for (const b of document.querySelectorAll(".pad button")) {
  b.onpointerdown=e=>{
    if (!running) return;
    e.preventDefault(); b.setPointerCapture(e.pointerId); controls.set(e.pointerId,b.dataset.key); paintPad();
  };
  b.onlostpointercapture=b.onpointerup=b.onpointercancel=e=>{ controls.delete(e.pointerId); paintPad(); };
}
window.addEventListener("blur",pause);
document.addEventListener("visibilitychange",()=>{ if (document.hidden) pause(); });
window.addEventListener("pagehide",pause);
try { state=await api("/api/session"); render(); }
catch { el("error").textContent="저장된 리허설을 열 수 없습니다. 연결을 확인한 뒤 새로고침해 주세요."; el("error").hidden=false; }
