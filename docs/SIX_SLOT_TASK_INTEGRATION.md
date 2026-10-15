# Six-slot task integration: software preparation for plan 5.3

Design written before implementation, 2026-10-15. This connects the existing
calibration rehearsal to both direct-control tasks. It does not complete physical
steps 5.1/5.2/5.3 or replace the frozen 5.0-3/5.0-4 diagnostics.

## Contract and completion criteria

- Opt-in `six_slot_dashboard` and `six_slot_preview` conditions use a candidate
  explicitly exported/imported by the operator. Existing eight-direction
  conditions, configuration and deterministic trace contents stay unchanged.
- Reuse `CodeSpec`/`TactileProfile`; this task path accepts the nominal six-direction,
  two-level code, including its magnitude scale. Valid distinct six-slot patterns,
  gains and pulse/gap remain configurable within existing software bounds.
  A versioned candidate envelope includes profile/code hashes and unvalidated
  software evidence labels. Legacy hashless exports need re-export through the
  rehearsal. Hashes detect inconsistent content, not a malicious author's identity.
- Validate and copy the selected candidate at trial start. No in-trial profile,
  semantic code or estimator change in this slice. Synthetic simulation results
  are never discovered or selected automatically. Export does not certify a
  perceptually calibrated profile or that a response block was completed.
- Causal belief alone enters `six-slot-belief-v1`: shared semantic direction/level
  feeds both matched visual vector and rendered command. Motor gain changes the
  command, never the semantic vector. Task/target/action/truth never enter encoding.
- One `six-slot-pulse-v1` simulation scheduler samples belief at cycle starts,
  latches it during pulse, and blanks **all** estimate values during gap. Pulse
  and gap round up separately to whole simulation ticks; their effective lengths
  are recorded. The legacy feedback period does not schedule this opt-in path.
- Both views share visual status: quantized uncertainty (SD in .25 units, capped
  at 2+), sample age at emission, dropout, waiting/held/fresh, and staleness.
  No valid sample, dropout, or age above .5 simulated seconds suppresses vector
  and commands during that pulse; status remains visible in both views. During
  gap it is blank too. Status is latched, not a continuously updated side channel.
  These quantities are not encoded as physical vibration by `TactileProfile`.
- Browser presentation is a separate, conservative finite lease, bounded by
  remaining simulated pulse time and the original profile pulse duration, starting
  at request send time. A slow response can miss the pulse entirely. Repeated
  packets cannot renew the same pulse. Both views clear together on expiry,
  pause, stop, complete, hidden/page exit or error. Lifecycle generations reject
  late callbacks; resume begins a new cycle without reviving cached output.
  Timer scheduling is best effort, not a real-time/skin-onset guarantee.
- Explicit server pause/resume/stop transitions prevent stale steps. Partial runs
  remain incomplete and unscored. Record the frozen import, independent component
  IDs, deterministic presentation packets and lifecycle events. Host request/event
  timing is separate from simulation ticks; replay verifies deterministic content,
  not actual browser rendering or physical timing.
- Direct keyboard/pointer actions remain unchanged. All records are software-only,
  `hardware_verified=false`, `human_evidence=false`; automated browser input is
  synthetic, actual developer inspection has separate provenance.

## Acceptance checks

Focused tests exercise permitted inputs, frozen imports, paired packets/schedules,
gaps/dropout/staleness, lifecycle/stale requests, completed and partial replay,
malformed imports and exact legacy trace comparisons captured at PR #5's head.
Real Chromium completes calibration fit/validation, exports a candidate, imports
it into both tasks and both new views, and checks controls, pause/resume/stop,
late responses, page exit, mobile overflow and console errors. This is automated
software behavior evidence. The final fast Python suite runs once after source
changes; no new performance grid or human experiment is included.

Dependencies: main → #2 (incorporating plan #3) → #4 → #5 → this integration.
All were unmerged at start; the integration branches from #5 `19e8673…`.
The existing Site and reusable Cloud deployment are unchanged.

## Use the connected workflow

1. Run `.venv/bin/python -m augneta serve --port 8000` and open `/calibration`.
   Complete the fit block, review the candidate, freeze it and complete validation.
   **Export candidate** saves a versioned, hashed software candidate. Session
   records are a separate export. A hashless older candidate can be loaded into
   calibration and re-exported; a task rejects it until then.
2. Return to `/`, choose **6-direction dashboard — software rehearsal** or
   **6-slot commands — software rehearsal**, and explicitly select the candidate
   file. The UI shows its full hash. Select target tracking or safe-zone maintenance.
   Import does not select a winning simulation profile or establish calibration.
3. Start the trial. Profile import, task and condition controls are locked until
   the run ends. WASD/arrows/pointer controls act directly. Pause clears both
   feedback representations and freezes simulation steps; Resume requests a new
   epoch/cycle. Stop saves an incomplete run without a complete score.
4. The UI displays the local recording path. Reconstruct it with
   `.venv/bin/python -m augneta replay <recording-directory>` using the matching
   package source and Python version. A finished/stopped run has metadata, trace,
   evaluator-only truth, lifecycle, server transport observations and summary.

`metadata.json` schema 2 records the frozen candidate, encoder/code/scheduler IDs,
profile hash/status, estimator ID and software provenance. `trace.jsonl` includes
before/after presentation packets. `lifecycle.jsonl` deterministically replays
pause/resume/stop at their simulation steps. `transport.jsonl` separately logs
server monotonic elapsed time at request handling; browser render and measured
skin onset fields are explicitly null. Replay does not reproduce these host
observations. Pause/stop endpoint ordering is serialized; stale epochs cannot
advance. A client-generated start UUID allows page exit to cancel a pending
start before or after server creation. Network loss/process kill can prevent a
stop acknowledgement; existing traces persist, while a finalized summary requires
normal stop, replacement or server cleanup. A browser timer is not a physical
stop guarantee.

Legacy conditions retain schema 1 and their original eight-direction packets.
The source-version replay guard remains strict: previously saved records are
replayed with their recorded implementation, not silently migrated. Six legacy
trace/truth hashes and summaries captured from PR #5 are checked unchanged by the
new implementation. The large earlier diagnostic grids remain preserved and are
not rerun by this integration.

Actual checks and remaining limits are in
[verification](VERIFICATION_SIX_SLOT_TASK_INTEGRATION.md).
