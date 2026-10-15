# Six-slot task integration: executed verification

2026-10-15 UTC, actual Augneta Cloud checkout `/workspace/augneta`.
This is software preparation for plan 5.3, not completion of physical 5.1/5.2/5.3.
No tactile perception, learning, human usability or performance advantage is claimed.

## Provenance and scope

The clean starting checkout was PR #5 at
`19e8673ffb98e2d1aab428b7bd86e470926c8c06`. Main remained
`67d7ce6953cb5c56ff14466b8490e2e261cd26be`; PR #2 (`411f72f…`), plan #3
(`4cf8c8c…`), #4 (`519b5d3…`) and #5 were all open Drafts. The user explicitly
allowed a stacked branch from #5. `feat/six-slot-task-integration` targets
`feat/selective-calibration-simulation`, preserving all prior branches and results.
No new worktree, merge, force push, auto-merge, Site publish, environment republish,
SDK/Player/BLE install, device operation, credential change or model API was used.

The [integration design](SIX_SLOT_TASK_INTEGRATION.md) was written before code
changes. Existing `CodeSpec`, `TactileProfile`, calibration responses, world,
estimator and direct-action semantics were reused. A separate scheduler and
versioned candidate envelope connect them without reusing the legacy encoder ID.
The 5.0-3 and 5.0-4 settings, negative findings and large runs remain preserved.
Neither the 324-trial sensitivity grid nor the 24-case calibration comparison was
rerun; no new virtual performance contest was added.

Final tested package source SHA-256:
`10b27287dbe17dd723e71a5d495fc14d921baaeefd574cf3d0f9981712cdc89e`.
Python 3.12.14 and existing locked `.venv`; no dependency or lockfile changes.
Recorded Git metadata correctly shows parent `19e8673…` and a dirty tree during
pre-commit verification. New and legacy final browser recordings have this exact
source hash. Subsequent documentation changes do not change the package digest.

## Final commands and observed results

All commands below ran from the repository root, with the existing environment.
Generated files stay in ignored `runs/` and `work/`.

| Command | Actual result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | **280 passed in 11.78 s**, once after the final application-source change |
| `.venv/bin/python tools/six_slot_browser_check.py --out runs/six-slot-browser-final-04 --chromium /usr/bin/chromium` | **13 checks, 12 exact task replays**, all final assertions passed |
| `.venv/bin/python tools/browser_check.py --out runs/six-slot-legacy-browser-final --chromium /usr/bin/chromium` | **9 checks, 8 exact replays** for existing conditions; no console errors |
| `.venv/bin/python -m pip check` | No broken requirements; existing unwritable pip-cache warning only |
| `node --check src/augneta/static/app.js` | Passed |
| `node --check src/augneta/static/six_slot.js` | Passed |
| `node --check src/augneta/static/calibration.js` | Passed |
| Documentation/patch consistency | 47 local Markdown file targets exist; final browser/source hashes match; `git diff --check` passed |
| `.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir work/six-slot/wheels-final .` | Built successfully; wheel archive contents match final presentation Python/JS/HTML/CSS source |

Thirty focused integration cases are included in the 280-test total. Early
focused runs passed 27, then 29 tests; a related API/recording run passed 66 tests.
A first full suite passed **280 in 10.93 s** before the final UI layout correction.
That earlier pass and wheel build were not treated as a final browser pass.
The final full suite was repeated because application JS/CSS changed to correct
an observed pointer risk, not merely because the harness was edited.

## What the real Chromium check establishes

The new checker uses real headless `/usr/bin/chromium`, Playwright and a real
threaded local Flask server labelled **synthetic**. It completes 14 fit and 14
validation responses in the actual calibration UI, freezes the candidate, and
downloads both candidate and session JSON. This is distinct from the earlier
real-Flask/mock-DOM calibration check in `VERIFICATION_PREARRIVAL.md`.

The exported candidate is explicitly imported into both target tracking and
safe-zone maintenance, with both new dashboard/command-preview conditions. Four
runs complete; eight runs are partial (explicit stops, delay/error cases and
navigation). Each recording reconstructs exactly. Candidate hash/provenance are
checked in all metadata. No partial run receives a completed-trial score.

Each complete run accepts an arrow input, W input and pointer-down input:
**12 confirmed input observations**. The checker scrolls the pointer button into
view, hovers it, checks bounding-box center against viewport dimensions and
`elementFromPoint`, then holds the input until a matching successful step response
arrives (2 s bound), releasing it in `finally`. The response must advance its
expected step by exactly one. Afterward, the raw recording must contain each
expected action with **`action == applied_action`**. This assertion was never
removed or relaxed. The artifact records input requests, boxes and hit targets.

Checks also cover common pulse/gap blanking (including the canvas raster and
hidden telemetry), a fixed control-button position across pulse/gap, profile
controls locked during trial, pause/resume, completion/stop clear, delayed replies
across lifecycle epochs, slow-response suppression, a deliberately injected HTTP
503, actual navigation during pending start and active trial, and 390 px mobile
overflow. Desktop command-preview and mobile screenshots were visually inspected.
There were **no unexpected console errors or page exceptions** in the final run.
The injected 503 produced its expected single console network-error entry; no
stale-step 400 occurred in that final run. The harness also verifies and separately
records any exact `stale presentation epoch` rejection if a pause overtakes a
sent step, rather than ignoring arbitrary HTTP errors.

The existing eight-direction checker passed before the last layout correction
and again on final source. It covers both objectives and all three legacy
conditions, direct keyboard/pointer inputs, pause/resume, complete/partial runs,
canvas objective rendering, mobile overflow and exact replays.

## Failures, diagnosis and corrections

Failed attempts remain under ignored run/log directories and are **not** final
passes, regardless of earlier successful phases:

- `six-slot-browser-01`: the harness used a string predicate requiring CSP
  `unsafe-eval`. It now supplies function predicates; the application's CSP was
  not weakened.
- `six-slot-browser-02` / `-03`: changing intercepted routes while a delayed
  request was still pending caused `Route is already handled` and, in another
  attempt, invalidated the intended slow-response check. A single persistent
  routing handler now controls deliberate delays and waits for pending handlers.
- `six-slot-browser-04`, `six-slot-browser-final-02` and `-03`: final raw-action
  checks failed with `AssertionError: [0.0, -1.0]`. Scrolling alone and a fixed
  130 ms hold did not establish that the pointer hit the intended button.
  A separate actual Chromium probe measured button document positions
  **1185.40625 px during pulse and 1052.40625 px during gap**, a **133 px shift**.
  The app now reserves the status area's height while hiding its contents, plus
  the semantic-caption height. The final checker asserts stable position, actual
  viewport/hit target and acknowledged input before releasing. It still checks
  the original applied-action records.
- `six-slot-browser-final`: a strict zero-console-entry assertion treated an
  intended stale-epoch HTTP 400 after pause as an unexplained error. The final
  checker permits only the exact rejected endpoint/body and the deliberately
  injected 503, records them separately, and fails on every other error.
- Two local edit-helper attempts had a Python syntax error before applying their
  proposed changes; these were corrected. One unchanged-source browser retry
  therefore reproduced the existing pointer failure instead of validating a fix.

Code review also addressed resume while an old response is outstanding, pending
start cancellation before/after server creation, and completion overtaking pause.
These are covered by final API/browser checks. No failed browser attempt was
promoted to a human response result or successful final verification.

## Information, lifecycle and replay boundaries

Only causal `Belief` reaches the six-slot scheduler. Tests compare packets under
different task objectives/actions, compare the two new views exactly, and check
that profile gain changes commands without changing semantic vectors. Strict
import validation rejects modified hash/code/evidence labels, missing/extra fields,
incompatible code specs and attempted in-trial overrides. Profile dataclasses are
immutable; start copies the selected envelope. Invalid starts preserve the active
trial. No simulation winner is automatically imported.

Status is quantized/latched at the same cycle start in both views. No sample,
dropout or sample age over .5 simulated seconds suppresses vector/command; gap
removes the whole payload. Uncertainty/age/dropout/staleness are **shared visual
status**, not verified tactile encoding. Tests cover these suppression cases,
whole-tick pulse/gap, stale lifecycle/step rejection, profile freeze and completed
or partial replay, including altered packet/lifecycle rejection.

Six trace/truth hashes and summaries captured from PR #5 before implementation
remain exactly equal under the new code (both tasks × three legacy conditions).
The version guard for replay remains strict: historical runs still require their
recorded source/Python version. This change does not silently migrate or overwrite
them. New schema 2 reconstructs candidate, presentation and lifecycle; separate
server elapsed-time observations are not reproduced as browser or physical onset.

## Remaining limits and device steps

This is a screen rehearsal with finite best-effort browser expiry, not a hard
real-time controller, verified physical stop, or skin-onset measurement. The
simulation schedule is deterministic; HTTP/render scheduling can suppress a
pulse and wall time can exceed simulation time. Browser render and measured
onset timestamps are explicitly unmeasured in product logs. Lost network or process
termination can prevent stop acknowledgement/final summary; existing partial
traces remain, and normal stop/replacement/server cleanup finalizes them.

All tested browser inputs are automated synthetic inputs. Developer visual
responses/direct controls have separate provenance when the server is launched
in its normal developer mode. Neither is participant-study evidence. Candidate
hashes detect inconsistency, not authorship; exports do not certify completed
validation or perceptual calibration. No human usability, tactile discrimination,
learning, transfer, physical timing or real response savings is established.

To resume physical steps, first provide the actual left/right device configuration,
PC/OS (Windows first, Apple Silicon alternative), and confirm Python/Player/SDK
versions and pairing locally. Then verify each motor index/mounting location,
finite output and stop/disconnect behavior, comfortable identifiable settings,
and separate calibration/held-out responses before a fixed-profile task pilot.
App credentials belong only in scoped local configuration. Those steps remain
unperformed; main, the existing Site and the reusable Cloud deployment are unchanged.
