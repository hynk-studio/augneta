import {isSix, clearSix, showSix} from './six_slot.js';
const $ = (id) => document.getElementById(id);
const arena = $("arena");
const feedbackCanvas = $("feedback");
const keys = new Set();
const directions = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"];
let state = null;
let running = false;
let paused = false;
let inFlight = false;
let timer = null;
let ready = false;
let starting = false;
let arenaHalfWidth = 1;
let candidate = null, generation = 0, presentationRequestStarted = 0, pendingStartId = null;
let controlQueue = Promise.resolve(), controlPending = 0, stopping = false, mustStop = false;

function describeTask(task, halfWidth) {
  const safe = task === "safe_zone";
  $("task-heading").textContent = safe ? "HIDDEN-FLOW SAFE ZONE" : "HIDDEN-FLOW TRACKING";
  $("task-title").textContent = safe ? "Stay inside the safe region." : "Follow the target. Explore the unseen force.";
  $("task-description").textContent = safe
    ? "Keep the center of your teal point inside the green square. The boundary counts as inside. You control every action; feedback describes the flow."
    : "Steer the teal point toward the moving orange ring. You control every action; feedback describes the flow.";
  $("objective").textContent = safe
    ? `Safe-zone maintenance: centered square, half-width ${halfWidth}; arena half-width ${arenaHalfWidth}. Stay inside, including the boundary.`
    : "Target tracking: follow the moving orange ring.";
  $("target-legend").hidden = safe;
  $("zone-legend").hidden = !safe;
  arena.setAttribute("aria-label", safe ? "Safe-zone arena: keep your point inside the green square" : "Tracking arena: follow the orange ring");
}

function setupChanged() {
  $("zone-setting").hidden = $("task").value !== "safe_zone";
  $("candidate-setting").hidden = !isSix($("condition").value);
  controls();
  if (!running && !starting) {
    state = null;
    $("result").hidden = true;
    describeTask($("task").value, Number($("zone-size").value));
    render();
  }
}

async function post(path, data) {
  const response = await fetch(path, {
    signal: AbortSignal.timeout(5000),
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

function drawArena() {
  const ctx = arena.getContext("2d");
  const { width: w, height: h } = arena;
  ctx.clearRect(0, 0, w, h);
  const side = Math.min(w - 72, h - 40);
  const left = (w - side) / 2;
  const top = (h - side) / 2;
  const half = state?.arena_half_width || 1;
  const point = (p) => [left + (p[0] / half + 1) * side / 2, top + (1 - p[1] / half) * side / 2];
  ctx.fillStyle = "#f4f5ec";
  ctx.fillRect(left, top, side, side);
  ctx.strokeStyle = "#e1e6d8";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 8; i++) {
    const offset = side * i / 8;
    ctx.beginPath(); ctx.moveTo(left + offset, top); ctx.lineTo(left + offset, top + side); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(left, top + offset); ctx.lineTo(left + side, top + offset); ctx.stroke();
  }
  ctx.strokeStyle = "#bccbb6"; ctx.strokeRect(left, top, side, side);
  if (!state) {
    delete arena.dataset.step;
    ctx.fillStyle = "#62715f"; ctx.textAlign = "center"; ctx.font = "18px system-ui";
    ctx.fillText("Start a trial to explore the flow", w / 2, h / 2);
    return;
  }
  if (state.task === "safe_zone") {
    const z = state.objective.half_width;
    const [x, y] = point([-z, z]);
    const size = z / half * side;
    ctx.fillStyle = "#157a6e22"; ctx.fillRect(x, y, size, size);
    ctx.strokeStyle = "#157a6e"; ctx.lineWidth = 3; ctx.strokeRect(x, y, size, size);
  }
  const [px, py] = point(state.visible.position);
  if (state.task === "tracking") {
    const [tx, ty] = point(state.visible.target);
    ctx.beginPath(); ctx.arc(tx, ty, 15, 0, Math.PI * 2); ctx.strokeStyle = "#ce673d"; ctx.lineWidth = 3; ctx.stroke();
    ctx.beginPath(); ctx.arc(tx, ty, 3, 0, Math.PI * 2); ctx.fillStyle = "#ce673d"; ctx.fill();
  }
  ctx.beginPath(); ctx.arc(px, py, 11, 0, Math.PI * 2); ctx.fillStyle = "#157a6e"; ctx.fill();
  ctx.beginPath(); ctx.arc(px, py, 20, 0, Math.PI * 2); ctx.strokeStyle = "#157a6e33"; ctx.lineWidth = 6; ctx.stroke();
  arena.dataset.step = String(state.visible.step);
}

function drawFeedback(packet, condition) {
  const ctx = feedbackCanvas.getContext("2d");
  ctx.clearRect(0, 0, feedbackCanvas.width, feedbackCanvas.height);
  const cx = 180, cy = 150, radius = 96;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.strokeStyle = "#d9e0d1"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.stroke();
  if (!packet) {
    ctx.fillStyle = "#a1ac9b"; ctx.font = "28px system-ui"; ctx.fillText("—", cx, cy);
    return;
  }
  for (let i = 0; i < 8; i++) {
    const a = i * Math.PI / 4;
    const x = cx + radius * Math.cos(a), y = cy - radius * Math.sin(a);
    if (condition === "sensory_preview") {
      const value = packet.channels[i];
      ctx.beginPath(); ctx.arc(x, y, 12 + value * 7, 0, Math.PI * 2);
      ctx.fillStyle = value > 0 ? `rgba(21,122,110,${0.25 + 0.75 * value})` : "#e7eddf";
      ctx.fill();
    }
    ctx.fillStyle = "#65765f"; ctx.font = "11px system-ui";
    // The legend accounts for the explicitly versioned channel permutation.
    const meaning = condition === "sensory_preview" ? (i - packet.channel_offset + 8) % 8 : i;
    ctx.fillText(directions[meaning], cx + (radius + 29) * Math.cos(a), cy - (radius + 29) * Math.sin(a));
  }
  if (condition === "dashboard" && packet.magnitude_level > 0) {
    const a = packet.direction_bin * Math.PI / 4;
    const length = 20 + packet.magnitude_level / 4 * 61;
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(-a); ctx.strokeStyle = "#157a6e"; ctx.fillStyle = "#157a6e"; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(length - 9, 0); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(length, 0); ctx.lineTo(length - 14, -7); ctx.lineTo(length - 14, 7); ctx.closePath(); ctx.fill(); ctx.restore();
  } else {
    ctx.fillStyle = "#20352f"; ctx.font = "20px system-ui";
    ctx.fillText(`${packet.magnitude_level} / 4`, cx, cy);
  }
}

function showCondition(condition, packet) {
  feedbackCanvas.closest('.feedback-panel').classList.remove('six-slot-layout');
  const preview = condition === "sensory_preview";
  $("feedback-title").textContent = condition === "none" ? "No additional information" : preview ? "Sensory code preview" : "Estimated environmental force";
  $("feedback-description").textContent = condition === "none" ? "Use your point’s motion and the selected objective."
    : preview ? "Eight intended channels encode the same quantized estimate as the visual dashboard."
      : "Eight directions and four intensity levels. This is a causal estimate, not hidden truth.";
  $("preview-note").hidden = !preview;
  $("telemetry").hidden = !packet;
  $("feedback-value").textContent = !packet ? "No force estimate is displayed."
    : `${packet.magnitude_level ? directions[packet.direction_bin] : "No direction"} · magnitude ${packet.magnitude_level} / 4`;
  if (packet) {
    $("uncertainty").textContent = `${(packet.uncertainty_level * 0.25).toFixed(2)}${packet.uncertainty_level === 8 ? "+" : ""} units/s²`;
    $("sensor").textContent = `${packet.sensor_status} / ${packet.dropped ? "dropped" : "no dropout"}`;
    $("age").textContent = packet.age_steps === null ? "No sample yet" : `${(packet.age_steps * state.dt_s * 1000).toFixed(0)} ms${packet.delayed ? " · delayed" : ""}`;
    $("emitted").textContent = `${(packet.emitted_step * state.dt_s).toFixed(2)} s`;
  }
  drawFeedback(packet, condition);
}

function render() {
  drawArena();
  if (!state) {
    if (isSix($("condition").value)) showSix({condition:$("condition").value}, 0, false);
    else showCondition($("condition").value, null);
    return;
  }
  if (isSix(state.condition)) showSix(state, presentationRequestStarted, running && !paused && !document.hidden && !state.complete);
  else showCondition(state.condition, state.feedback);
  describeTask(state.task, state.objective.half_width);
  $("clock").textContent = `${state.visible.time_s.toFixed(2)} / ${(state.total_steps * state.dt_s).toFixed(2)} s`;
  $("progress").max = state.total_steps; $("progress").value = state.visible.step;
  $("motion").textContent = `Position ${state.visible.position.map(v => v.toFixed(2)).join(", ")} · Velocity ${state.visible.velocity.map(v => v.toFixed(2)).join(", ")}`;
  $("log-location").textContent = `Local recording: ${state.recording}`;
  $("participant-label").textContent = state.participant_kind === "synthetic" ? "synthetic browser check" : "developer inspection";
}

function controls() {
  const locked = running || starting || !ready || controlPending > 0;
  $("start").disabled = locked || (isSix($("condition").value) && !candidate);
  $("candidate-file").disabled = locked;
  $("condition").disabled = locked;
  $("seed").disabled = locked;
  $("task").disabled = locked;
  $("zone-size").disabled = locked || $("task").value !== "safe_zone";
  $("pause").disabled = !running || controlPending > 0 || stopping || mustStop;
  $("stop").disabled = !running || stopping;
  $("pause").textContent = paused ? "Resume" : "Pause";
}

function showResult(summary) {
  $("result").hidden = false;
  const safe = summary.task === "safe_zone";
  $("metric-label").textContent = safe ? "NORMALIZED OUTSIDE DISTANCE" : "NORMALIZED TRACKING RMSE";
  const score = safe ? summary.normalized_outside_distance : summary.normalized_tracking_rmse;
  $("score").textContent = score === null ? "Incomplete" : score.toFixed(4);
  $("result-detail").textContent = score === null
    ? "Trial stopped before completion. No valid complete score is reported. The partial trace is retained."
    : safe ? `Outside ${summary.outside_time_s.toFixed(2)} s (${(summary.outside_fraction * 100).toFixed(1)}%); distance averaged over all ${summary.samples} window ticks / farthest corner distance. Synthetic/developer result, not human transfer evidence.`
    : `RMSE / arena diagonal, using ${summary.samples} fixed-window samples. Lower is closer tracking. This development result is not human learning evidence.`;
}

function action() {
  const down = (...names) => Number(names.some(k => keys.has(k)));
  return [down("ArrowRight", "d") - down("ArrowLeft", "a"), down("ArrowUp", "w") - down("ArrowDown", "s")];
}

async function tick() {
  if (!running || paused || inFlight || controlPending) return;
  const requestToken = {}; inFlight = requestToken;
  const token = generation, id = state.trial_id, started = performance.now();
  try {
    const data = {trial_id:id, expected_step:state.visible.step, action:action()};
    if (isSix(state.condition)) data.presentation_epoch = state.feedback.epoch;
    const next = await post('/api/step', data);
    if (token !== generation || id !== state?.trial_id || !running) return;
    state = next; presentationRequestStarted = started;
    if (state.complete) {
      running = false; keys.clear(); controls(); showResult(state.summary);
      $('status').textContent = 'Trial complete. Recording saved locally. Choose another condition to start again.';
    } else if (!paused) $('status').textContent = `Direct control active · last request ${(performance.now() - started).toFixed(0)} ms · simulation tick ${(state.dt_s * 1000).toFixed(0)} ms`;
    render();
  } catch (error) {
    if (token !== generation) return;
    paused = true; mustStop = true; generation++; keys.clear();
    if (isSix(state.condition)) clearSix('request error');
    controls(); $('status').textContent = `Paused after error: ${error.message}. Stop this trial before restarting.`;
  } finally {
    if (inFlight === requestToken) {
      inFlight = false;
      // Resume may have happened while this older response was in flight.
      // Request fresh state under the current epoch; never render the old reply.
      if (running && !paused && !controlPending && !mustStop)
        timer = setTimeout(tick, token === generation ? Math.max(0, state.dt_s * 1000 - (performance.now() - started)) : 0);
    }
  }
}

function togglePause(force = false) {
  if (starting) { generation++; if (isSix($('condition').value)) clearSix('start interrupted'); return; }
  if (!running || stopping || mustStop) return;
  paused = force || !paused;
  keys.clear(); clearTimeout(timer);
  if (!isSix(state.condition)) {
    controls(); $('status').textContent = paused ? 'Paused. Simulation time is frozen; press Resume when ready.' : 'Resuming direct control.';
    if (!paused) tick(); return;
  }
  const token = ++generation, desiredPause = paused, id = state.trial_id;
  clearSix(desiredPause ? 'paused' : 'resuming');
  controlPending++; controls();
  controlQueue = controlQueue.then(async () => {
    const alreadyPaused = state.feedback.phase === 'paused';
    if (desiredPause !== alreadyPaused) {
      const started = performance.now();
      const next = await post('/api/presentation-lifecycle', {trial_id:id,
        action:desiredPause ? 'pause' : 'resume', expected_epoch:state.feedback.epoch});
      if (state?.trial_id === id) { state = next; presentationRequestStarted = started; }
    }
    if (token === generation && state.complete) {
      running = false; render(); showResult(state.summary);
      $('status').textContent = 'Trial complete. Recording saved locally.';
    } else if (token === generation) {
      render(); $('status').textContent = desiredPause ? 'Paused. Simulation time is frozen; press Resume when ready.' : 'Resuming direct control.';
    }
  }).catch(error => {
    paused = true; mustStop = true; clearSix('lifecycle error');
    $('status').textContent = `Lifecycle failed: ${error.message}. Stop before restarting.`;
  }).finally(() => {
    controlPending--; controls();
    if (token === generation && running && !paused && !mustStop) tick();
  });
}

$('setup').addEventListener('submit', async event => {
  event.preventDefault();
  if (running || starting || !ready || controlPending) return;
  const settings = {condition:$('condition').value, seed:Number($('seed').value), task:$('task').value};
  if (settings.task === 'safe_zone') settings.safe_zone_half_width = Number($('zone-size').value);
  if (isSix(settings.condition)) { settings.candidate = candidate; pendingStartId = crypto.randomUUID(); settings.start_id = pendingStartId; }
  const token = ++generation, started = performance.now();
  starting = true; state = null; inFlight = false; mustStop = false; controls(); render();
  try {
    const next = await post('/api/trials', settings);
    if (token !== generation || document.hidden) {
      await post('/api/stop', {trial_id:next.trial_id});
      $('status').textContent = 'Start interrupted by leaving the page. Partial recording preserved.';
      return;
    }
    state = next; presentationRequestStarted = started;
    running = true; paused = false; keys.clear(); $('result').hidden = true;
    $('start').blur(); controls(); render(); tick();
  } catch (error) { cancelPendingStart(); $('status').textContent = error.message; }
  finally { starting = false; pendingStartId = null; controls(); }
});
$('candidate-file').addEventListener('change', async () => {
  candidate = null; controls();
  try {
    const file = $('candidate-file').files[0]; if (!file) return;
    if (file.size > 8000) throw new Error('Candidate exceeds supported file size.');
    const value = JSON.parse(await file.text());
    const accepted = await post('/api/candidate-import', {candidate:value});
    candidate = value;
    $('candidate-status').textContent = `Selected unvalidated candidate · ${accepted.profile_sha256}. Frozen at start; meaning ${accepted.code_id}.`;
  } catch (error) { $('candidate-status').textContent = `Import rejected: ${error.message}`; }
  finally { $('candidate-file').value = ''; controls(); }
});
$('condition').addEventListener('change', setupChanged);
$('task').addEventListener('change', setupChanged);
$('zone-size').addEventListener('input', setupChanged);
$('pause').addEventListener('click', () => { $('pause').blur(); togglePause(); });
$('stop').addEventListener('click', async () => {
  if (!running || stopping) return;
  stopping = true; paused = true; generation++; keys.clear(); clearTimeout(timer);
  if (isSix(state.condition)) clearSix('stopped');
  controls();
  try {
    await controlQueue;
    const result = await post('/api/stop', {trial_id:state.trial_id});
    running = false; showResult(result.summary);
    $('status').textContent = 'Trial stopped. Partial recording retained; start a new trial to continue.';
  } catch (error) { mustStop = true; $('status').textContent = `Stop failed: ${error.message}`; }
  finally { stopping = false; controls(); }
});
function cancelPendingStart() {
  if (pendingStartId) fetch('/api/cancel-start', {method:'POST', keepalive:true,
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({start_id:pendingStartId})}).catch(() => {});
}
window.addEventListener('pagehide', () => {
  cancelPendingStart();
  generation++; paused = true; keys.clear(); clearTimeout(timer);
  if (isSix(state?.condition || $('condition').value)) clearSix('page exit');
  if (running && state) fetch('/api/stop', {method:'POST', keepalive:true,
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({trial_id:state.trial_id})}).catch(() => {});
  running = false; controls();
});

const validKeys = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "w", "a", "s", "d"]);
document.addEventListener("keydown", event => {
  if (!running || ["INPUT", "SELECT", "BUTTON"].includes(event.target.tagName)) return;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  if (key === " ") { event.preventDefault(); if (!event.repeat) togglePause(); }
  else if (validKeys.has(key)) { event.preventDefault(); if (!paused) keys.add(key); }
});
document.addEventListener("keyup", event => keys.delete(event.key.length === 1 ? event.key.toLowerCase() : event.key));
window.addEventListener("blur", () => togglePause(true));
document.addEventListener("visibilitychange", () => { if (document.hidden) togglePause(true); });
document.querySelectorAll("[data-key]").forEach(button => {
  button.addEventListener("pointerdown", event => {
    event.preventDefault(); if (!running || paused) return;
    button.setPointerCapture(event.pointerId); keys.add(button.dataset.key);
  });
  for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) button.addEventListener(event, () => keys.delete(button.dataset.key));
});
async function initialize() {
  controls(); render();
  try {
    const response = await fetch("/api/trial-defaults");
    if (!response.ok) throw new Error("Cannot load task settings; reload to retry.");
    const settings = await response.json();
    $("task").value = settings.task;
    $("seed").value = settings.seed;
    $("zone-size").value = settings.safe_zone_half_width;
    arenaHalfWidth = settings.arena_half_width;
    ready = true; setupChanged();
  } catch (error) { $("status").textContent = error.message; }
}
initialize();
