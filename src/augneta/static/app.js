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

async function post(path, data) {
  const response = await fetch(path, {
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
    ctx.fillStyle = "#62715f"; ctx.textAlign = "center"; ctx.font = "18px system-ui";
    ctx.fillText("Start a trial to explore the flow", w / 2, h / 2);
    return;
  }
  const [tx, ty] = point(state.visible.target);
  const [px, py] = point(state.visible.position);
  ctx.beginPath(); ctx.arc(tx, ty, 15, 0, Math.PI * 2); ctx.strokeStyle = "#ce673d"; ctx.lineWidth = 3; ctx.stroke();
  ctx.beginPath(); ctx.arc(tx, ty, 3, 0, Math.PI * 2); ctx.fillStyle = "#ce673d"; ctx.fill();
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
  const preview = condition === "sensory_preview";
  $("feedback-title").textContent = condition === "none" ? "No additional information" : preview ? "Sensory code preview" : "Estimated environmental force";
  $("feedback-description").textContent = condition === "none" ? "Track using the visible target and your point’s motion."
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
  if (!state) { showCondition($("condition").value, null); return; }
  showCondition(state.condition, state.feedback);
  $("clock").textContent = `${state.visible.time_s.toFixed(2)} / ${(state.total_steps * state.dt_s).toFixed(2)} s`;
  $("progress").max = state.total_steps; $("progress").value = state.visible.step;
  $("motion").textContent = `Position ${state.visible.position.map(v => v.toFixed(2)).join(", ")} · Velocity ${state.visible.velocity.map(v => v.toFixed(2)).join(", ")}`;
  $("log-location").textContent = `Local recording: ${state.recording}`;
  $("participant-label").textContent = state.participant_kind === "synthetic" ? "synthetic browser check" : "developer inspection";
}

function controls() {
  $("start").disabled = running;
  $("condition").disabled = running;
  $("seed").disabled = running;
  $("pause").disabled = !running;
  $("stop").disabled = !running;
  $("pause").textContent = paused ? "Resume" : "Pause";
}

function showResult(summary) {
  $("result").hidden = false;
  const score = summary.normalized_tracking_rmse;
  $("score").textContent = score === null ? "Incomplete" : score.toFixed(4);
  $("result-detail").textContent = score === null
    ? "Trial stopped before completion. No valid tracking score is reported. The partial trace is retained."
    : `RMSE / arena diagonal, using ${summary.samples} fixed-window samples. Lower is closer tracking. This development result is not human learning evidence.`;
}

function action() {
  const down = (...names) => Number(names.some(k => keys.has(k)));
  return [down("ArrowRight", "d") - down("ArrowLeft", "a"), down("ArrowUp", "w") - down("ArrowDown", "s")];
}

async function tick() {
  if (!running || paused || inFlight) return;
  inFlight = true;
  const started = performance.now();
  try {
    state = await post("/api/step", { trial_id: state.trial_id, expected_step: state.visible.step, action: action() });
    render();
    if (state.complete) {
      running = false; keys.clear(); controls(); showResult(state.summary);
      $("status").textContent = "Trial complete. Recording saved locally. Choose another condition to start again.";
    } else if (!paused) {
      const elapsed = performance.now() - started;
      $("status").textContent = `Direct control active · last request ${elapsed.toFixed(0)} ms · simulation tick ${(state.dt_s * 1000).toFixed(0)} ms`;
    }
  } catch (error) {
    paused = true; keys.clear(); controls();
    $("status").textContent = `Paused after error: ${error.message}. Stop this trial before restarting.`;
  } finally {
    inFlight = false;
    if (running && !paused) timer = setTimeout(tick, Math.max(0, state.dt_s * 1000 - (performance.now() - started)));
  }
}

function togglePause(force = false) {
  if (!running) return;
  paused = force || !paused;
  keys.clear(); clearTimeout(timer); controls();
  $("status").textContent = paused ? "Paused. Simulation time is frozen; press Resume when ready." : "Resuming direct control.";
  if (!paused) tick();
}

$("setup").addEventListener("submit", async event => {
  event.preventDefault();
  if (running) return;
  $("start").disabled = true;
  try {
    state = await post("/api/trials", { condition: $("condition").value, seed: Number($("seed").value) });
    running = true; paused = false; keys.clear(); $("result").hidden = true;
    $("start").blur(); controls(); render(); tick();
  } catch (error) { $("status").textContent = error.message; controls(); }
});

$("condition").addEventListener("change", () => { if (!running) showCondition($("condition").value, null); });
$("pause").addEventListener("click", () => { $("pause").blur(); togglePause(); });
$("stop").addEventListener("click", async () => {
  togglePause(true);
  // An in-flight action is allowed to finish before closing its recording.
  while (inFlight) await new Promise(resolve => setTimeout(resolve, 10));
  try {
    const result = await post("/api/stop", { trial_id: state.trial_id });
    running = false; controls(); showResult(result.summary);
    $("status").textContent = "Trial stopped. Partial recording retained; start a new trial to continue.";
  } catch (error) { $("status").textContent = `Stop failed: ${error.message}`; }
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
render();
