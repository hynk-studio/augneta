const $ = (id) => document.getElementById(id);
let profile, session = null, busy = false, timer = null, readyTimer = null, exportRecord = null;
let awaitingGap = false, visibilityEpoch = 0;
const gains = [], slots = [];
for (const side of ['left', 'right']) {
  for (let i = 0; i < 3; i++) {
    const name = `${side === 'left' ? 'L' : 'R'}${i}`;
    const label = document.createElement('label'); label.textContent = `${name} gain`;
    const input = document.createElement('input');
    input.type = 'number'; input.min = '0.05'; input.max = '1'; input.step = '0.05'; input.value = '1';
    label.append(input); $('gains').append(label); gains.push(input);
    const slot = document.createElement('div'); slot.className = 'slot'; slot.textContent = name;
    const value = document.createElement('span'); value.textContent = '0.00'; slot.append(value);
    $(`${side}-slots`).append(slot); slots.push({slot, value});
  }
}
function clearPreview() {
  clearTimeout(timer); timer = null;
  slots.forEach(({slot, value}) => { slot.classList.remove('active'); value.textContent = '0.00'; });
}
function setProfile(value) {
  profile = structuredClone(value);
  profile.gains.forEach((v, i) => { gains[i].value = v; });
  $('pulse').value = profile.pulse_ms; $('gap').value = profile.gap_ms;
  $('code-description').textContent = `${profile.spec.directions} direction meanings · ${profile.spec.levels} nonzero levels · 6 command slots`;
  $('response-direction').replaceChildren(); $('response-level').replaceChildren();
  for (let i = 0; i < profile.spec.directions; i++) {
    $('response-direction').add(new Option(`D${i} · ${Math.round(i * 360 / profile.spec.directions)}°`, i));
  }
  for (let i = 1; i <= profile.spec.levels; i++) $('response-level').add(new Option(String(i), i));
}
function editedProfile() {
  return {...structuredClone(profile), gains: gains.map(i => Number(i.value)),
    pulse_ms: Number($('pulse').value), gap_ms: Number($('gap').value)};
}
async function api(path, data) {
  const epoch = visibilityEpoch;
  const response = await fetch(path, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  if (data !== undefined && epoch !== visibilityEpoch && result.session_id) {
    // A start/present response may arrive after the page became hidden. Stop
    // that exact session; never let its late callback light the preview again.
    const stopped = await fetch('/api/calibration/stop', {method:'POST', keepalive:true,
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:result.session_id})});
    if (stopped.ok) await accept(await stopped.json());
    throw new Error('Rehearsal interrupted by leaving the page. The preview is cleared.');
  }
  return result;
}
function download(name, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type:'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function renderReports(reports) {
  $('reports').replaceChildren();
  for (const [name, report] of Object.entries(reports)) {
    const section = document.createElement('div'); section.dataset.report = name;
    const title = document.createElement('h3'); title.textContent = `${name === 'fit' ? 'Fit' : 'Held-out validation'}: ${report.joint_correct}/${report.answered} identified`;
    section.append(title);
    const table = document.createElement('table'), head = table.createTHead().insertRow();
    ['Expected / chosen', ...report.columns].forEach(v => { const th = document.createElement('th'); th.textContent = v; head.append(th); });
    report.direction_confusion.forEach((row, i) => {
      const tr = table.insertRow(); [report.rows[i], ...row].forEach(v => { tr.insertCell().textContent = v; });
    });
    section.append(table); $('reports').append(section);
  }
}
function refresh() {
  const state = session?.state;
  const terminal = !session || ['complete','stopped'].includes(state);
  $('profile-fields').disabled = busy || !(terminal || state === 'review');
  $('profile-file').disabled = busy || !terminal;
  $('start-cal').disabled = busy || !terminal || !profile;
  $('present').disabled = busy || state !== 'ready';
  $('response-fields').disabled = busy || awaitingGap || state !== 'awaiting_response';
  $('stop-cal').disabled = busy || terminal;
  $('freeze').hidden = state !== 'review'; $('freeze').disabled = busy;
  $('save-profile').disabled = busy || !profile;
  $('export-session').disabled = busy || !exportRecord;
  if (session) $('progress-label').textContent = `${session.phase === 'fit' ? 'Fit' : 'Validation'} · ${session.index}/${session.phase_total} responses · ${state.replaceAll('_',' ')}`;
}
async function run(action) {
  if (busy) return;
  busy = true; refresh();
  try { await action(); }
  catch (error) { clearPreview(); $('cal-status').textContent = error.message; }
  finally { busy = false; refresh(); }
}
async function accept(value) {
  session = value;
  renderReports(session.reports);
  if (['complete','stopped'].includes(session.state)) {
    exportRecord = await api(`/api/calibration/${session.session_id}/export`);
    $('cal-status').textContent = session.state === 'complete' ? 'Both blocks recorded. Export your session; the candidate is not hardware validated.' : 'Stopped. Completed responses and unfinished-block counts are preserved.';
  } else if (session.state === 'review') {
    $('cal-status').textContent = 'Fit block finished. Review the report, adjust gains or timing if needed, then freeze the profile for validation.';
  } else $('cal-status').textContent = 'Visual rehearsal only. Show the next pattern and record your response.';
}
const selection = () => ({session_id:session.session_id, expected_index:session.index});
$('start-cal').onclick = () => run(async () => {
  clearPreview(); clearTimeout(readyTimer); awaitingGap = false; exportRecord = null;
  const next = await api('/api/calibration/start', {profile:editedProfile(), seed:7});
  setProfile(next.profile); await accept(next);
});
$('present').onclick = () => run(async () => {
  clearPreview();
  const next = await api('/api/calibration/present', selection());
  await accept(next);
  awaitingGap = true;
  [...next.stimulus.left, ...next.stimulus.right].forEach((v, i) => {
    slots[i].slot.classList.toggle('active', v > 0); slots[i].value.textContent = v.toFixed(2);
  });
  timer = setTimeout(clearPreview, next.stimulus.pulse_ms);
  readyTimer = setTimeout(() => { awaitingGap = false; refresh(); }, next.stimulus.pulse_ms + next.stimulus.gap_ms);
});
function respond(response) {
  if (awaitingGap) return;
  return run(async () => {
    clearPreview(); await accept(await api('/api/calibration/respond', {...selection(), response}));
  });
}
$('respond').onclick = () => respond({kind:'identified', direction:Number($('response-direction').value), level:Number($('response-level').value)});
$('zero').onclick = () => respond({kind:'zero', direction:null, level:0});
$('unknown').onclick = () => respond({kind:'unknown', direction:null, level:null});
$('freeze').onclick = () => run(async () => {
  const next = await api('/api/calibration/freeze', {session_id:session.session_id, profile:editedProfile()});
  setProfile(next.profile); await accept(next);
});
$('stop-cal').onclick = () => run(async () => {
  clearPreview(); clearTimeout(readyTimer); awaitingGap = false;
  await accept(await api('/api/calibration/stop', {session_id:session.session_id}));
});
$('save-profile').onclick = () => run(async () => {
  const candidate = session && !['complete','stopped','review'].includes(session.state) ? session.profile : editedProfile();
  // Validate imported/edited data on the server before exporting a candidate.
  await api('/api/tactile-preview', {profile:candidate, direction:null, level:0});
  download('augneta-candidate-profile.json', {profile:candidate, profile_status:'unvalidated_hardware_candidate', hardware_verified:false, human_evidence:false});
});
$('export-session').onclick = () => download('augneta-calibration-rehearsal.json', exportRecord);
$('profile-file').onchange = () => run(async () => {
  const file = $('profile-file').files[0]; if (!file) return;
  if (file.size > 100000) throw new Error('Profile file is too large.');
  const data = JSON.parse(await file.text()); const candidate = data.profile || data;
  await api('/api/tactile-preview', {profile:candidate, direction:null, level:0});
  setProfile(candidate); $('cal-status').textContent = 'Candidate loaded. Start a new fit block to rehearse it.';
  $('profile-file').value = '';
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  visibilityEpoch += 1;
  clearPreview(); clearTimeout(readyTimer); awaitingGap = false;
  // No hardware is active. Stop any ongoing rehearsal without depending on a response callback.
  if (session && !['complete','stopped'].includes(session.state)) {
    const id = session.session_id;
    fetch('/api/calibration/stop', {method:'POST', keepalive:true,
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:id})})
      .then(r => r.json()).then(v => { if (session?.session_id === id && !v.error) return accept(v); })
      .catch(() => { $('cal-status').textContent = 'Preview cleared; server stop could not be confirmed. Use Stop before continuing.'; })
      .finally(refresh);
  }
});
run(async () => { const data = await api('/api/calibration/defaults'); setProfile(data.profile); $('cal-status').textContent = 'Ready for a visual rehearsal. No device is connected.'; });
