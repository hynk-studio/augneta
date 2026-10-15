// Shared finite browser lease for both software views; no physical output.
const $ = id => document.getElementById(id);
export const isSix = condition => ['six_slot_dashboard', 'six_slot_preview'].includes(condition);
let expiry = null, currentKey = null, retiredKey = null, deadline = 0;
export function clearSix(reason = 'cleared') {
  clearTimeout(expiry); expiry = null;
  if (currentKey !== null) retiredKey = currentKey;
  const canvas = $('feedback');
  canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
  canvas.dataset.phase = reason; delete canvas.dataset.code;
  $('telemetry').hidden = true;
  for (const id of ['uncertainty', 'sensor', 'age', 'emitted']) $(id).textContent = '—';
  $('feedback-value').textContent = `Presentation cleared · ${reason}`;
}
export function showSix(state, requestStarted, allowed) {
  $('feedback').closest('.feedback-panel').classList.add('six-slot-layout');
  const packet = state?.feedback;
  const preview = state?.condition === 'six_slot_preview';
  $('feedback-title').textContent = preview ? '6-slot command preview · software rehearsal' : '6-direction dashboard · software rehearsal';
  $('feedback-description').textContent = 'Both views share pulse/gap and visual uncertainty/sensor status. Command gains do not change the meaning vector.';
  $('preview-note').hidden = false;
  $('preview-note').textContent = 'Screen only. Status is a shared visual aid, not a vibration code. Slot locations are schematic; no device or skin timing is verified.';
  if (!allowed || !packet || packet.phase !== 'pulse') { clearSix(allowed ? packet?.phase || 'ready' : 'inactive'); return; }
  const key = `${state.trial_id}/${packet.epoch}/${packet.cycle}`;
  if (key !== currentKey) {
    clearSix('new pulse'); currentKey = key;
    deadline = requestStarted + packet.remaining_pulse_ms;
  }
  const remaining = deadline - performance.now();
  if (key === retiredKey || remaining <= 0) { clearSix('expired or late response'); return; }
  clearTimeout(expiry);
  expiry = setTimeout(() => clearSix('pulse expired'), remaining);
  const canvas = $('feedback'), ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height); canvas.dataset.phase = 'pulse';
  const p = packet.payload, code = p.semantic_state, status = p.status;
  canvas.dataset.code = code ? `${code.direction}/${code.level}` : 'suppressed';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.font = '12px system-ui';
  if (preview) {
    [...p.command.left, ...p.command.right].forEach((v, i) => {
      const x = i < 3 ? 105 : 255, y = 65 + (i % 3) * 75;
      ctx.fillStyle = v ? `rgba(21,122,110,${.25 + .75 * v})` : '#e7eddf';
      ctx.beginPath(); ctx.arc(x, y, 23, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#20352f'; ctx.fillText(`${i < 3 ? 'L' : 'R'}${i % 3} · ${v.toFixed(2)}`, x, y);
    });
  } else {
    ctx.strokeStyle = '#d9e0d1'; ctx.beginPath(); ctx.arc(180, 150, 90, 0, Math.PI * 2); ctx.stroke();
    for (let i = 0; i < 6; i++) {
      const a = i * Math.PI / 3; ctx.fillStyle = '#65765f';
      ctx.fillText(`D${i}`, 180 + 115 * Math.cos(a), 150 - 115 * Math.sin(a));
    }
    if (code?.level) {
      const [x, y] = p.visual.force, angle = Math.atan2(y, x), length = 85 * Math.hypot(x, y) / 1.5;
      ctx.save(); ctx.translate(180, 150); ctx.rotate(-angle);
      ctx.strokeStyle = ctx.fillStyle = '#157a6e'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(length, 0); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(length, 0); ctx.lineTo(length - 12, -6); ctx.lineTo(length - 12, 6); ctx.closePath(); ctx.fill(); ctx.restore();
    }
  }
  $('feedback-value').textContent = p.suppression ? `Estimate suppressed: ${p.suppression}`
    : `${code.direction === null ? 'No direction' : `D${code.direction} · ${code.direction * 60}°`} · magnitude ${code.level} / 2`;
  $('telemetry').hidden = false;
  $('uncertainty').textContent = `${(status.uncertainty_level * .25).toFixed(2)}${status.uncertainty_level === 8 ? '+' : ''} units/s²`;
  $('sensor').textContent = `${status.sensor_status} / ${status.dropped ? 'dropped' : 'no dropout'} / ${status.stale ? 'stale' : 'within age limit'}`;
  $('age').textContent = status.age_steps === null ? 'No sample yet' : `${(status.age_steps * state.dt_s * 1000).toFixed(0)} ms${status.delayed ? ' · delayed' : ''}`;
  $('emitted').textContent = `${(status.emitted_step * state.dt_s).toFixed(2)} s · simulation time`;
}
