# First implementation: actual verification

All results below are software checks using synthetic data. No participant study,
human learning, physical output, skin-level timing, embodiment, sensory extension,
neural change, or consciousness result is claimed.

## Repository and environment

- Repository: `https://github.com/hynk-studio/augneta`; initial branch `work`, clean
  working tree. No unrelated changes were present or discarded.
- Fetched main: `2cd9fb15d1322fbc75dda51f3bedc35288028727`; created
  `feat/first-hidden-flow-experiment` from `origin/main` before editing.
- Attached Cloud runtime and exact post-merge commands are recorded in
  [Cloud environment update](CLOUD_ENVIRONMENT_UPDATE.md). It was not republished.
- Python 3.12.14; Flask 3.1.3; pytest 9.1.1; Playwright 1.64.0; system Chromium
  154.0.8037.57. The complete installed dependency set is pinned in
  `requirements-dev.lock`.

## Commands and observed results

Commands were run from `/workspace/augneta` unless otherwise stated.

| Actual command | Observed result |
| --- | --- |
| `python -m venv .venv` | Created the project virtual environment |
| `.venv/bin/python -m pip install -r requirements-dev.lock` | Success; repeated locked install succeeded |
| `.venv/bin/python -m pip install --no-build-isolation --no-deps -e .` | Editable installation succeeded, including repetition |
| `.venv/bin/python -m pip check` | `No broken requirements found.` |
| `.venv/bin/python -m pytest -q` | **70 passed in 2.21s** on the final core implementation |
| `.venv/bin/python -m augneta smoke --out runs/verified-smoke --seed 7` | Three complete 600-step trials, 500 evaluation samples each; all exact replays verified |
| `.venv/bin/python -m augneta replay runs/verified-smoke/dashboard` | `replay_verified=true`, 600 steps, complete |
| `.venv/bin/python -m augneta oracle-smoke --out runs/verified-oracle --seed 7` | Separate labelled diagnostic; 600 steps, exact replay verified |
| `.venv/bin/python tools/browser_check.py --out artifacts/browser-final --chromium /usr/bin/chromium` | Three complete interactive synthetic trials and one incomplete stop; all four replayed; zero browser console errors |
| `node --check src/augneta/static/app.js` | Exit 0 |
| `git diff --check` | Exit 0 |
| `.venv/bin/python -m pip wheel --no-build-isolation --no-deps --wheel-dir /tmp/augneta-wheel .` | Built `augneta-0.1.0-py3-none-any.whl` |

The pytest checks cover seed/config/action determinism; physics bounds and exact
action application; limited observations and absent truth/target references;
future-data rejection before mutation; timestamp-correct delayed Kalman updates;
explicit dropout and stale-data handling; packet equality and held update timing;
environmental direction and quantization; estimator replacement with a fixed
semantic code; independently replayable encoder changes; oracle separation;
evidence-label and trace tampering; no device acknowledgements; invalid config,
actions, vector shapes, and unavailable hardware; an independent metric example;
incomplete trials; log overwrite protection; and HTTP lifecycle/input boundaries.

The ordinary server command was also launched and exercised:

```bash
.venv/bin/python -m augneta serve --port 8000 --participant-kind synthetic --log-dir runs/launch-check
curl --fail --silent http://127.0.0.1:8000/api/health
```

The health endpoint returned `status=ready`, `participant_kind=synthetic`,
`human_evidence=false`, `hardware_verified=false`. A Python HTTP client started
a dashboard trial, applied ten `[1,0]` actions, stopped it, and verified replay.
The retained incomplete run correctly had `normalized_tracking_rmse=null`.

A fresh environment also installed the locked dependencies and built wheel:

```bash
python -m venv /tmp/augneta-install-check
/tmp/augneta-install-check/bin/python -m pip install -r requirements-dev.lock
/tmp/augneta-install-check/bin/python -m pip install --no-deps /tmp/augneta-wheel/augneta-0.1.0-py3-none-any.whl
/tmp/augneta-install-check/bin/python -m pip check
```

From `/tmp`, the installed wheel imported from its own site-packages. Its HTML,
JavaScript, CSS, and health routes each returned 200 via Flask's test client.
This command also verified the source checkout's 600-step recording using the
installed wheel, confirming that runtime assets and implementation content match:

```bash
/tmp/augneta-install-check/bin/python -m augneta replay /workspace/augneta/runs/verified-smoke/dashboard
```

## Synthetic result artifact

The compact committed [result artifact](results/first-smoke.json) contains the
complete config, code content hash, software provenance, policy identity,
evidence labels, and all three result summaries. Full traces remain in the
ignored local `runs/verified-smoke/` directory and can be regenerated with the
documented command. The run was made before committing, so its Git provenance
honestly records the base commit and a dirty worktree; the implementation SHA-256
identifies the actual tested code independently of that commit.

| Main condition | Normalized tracking RMSE | Replay |
| --- | ---: | --- |
| No additional information | 0.05808011850785609 | Exact, 600 steps |
| Matched visual dashboard | 0.045378297228523795 | Exact, 600 steps |
| Sensory-code development preview | 0.045378297228523795 | Exact, 600 steps |

These are one seed and one scripted policy, not human evidence or a statistical
comparison. Dashboard/preview equality is expected because the policy decodes
the identical packet. The separately recorded oracle diagnostic produced
0.0438476737061161; it uses truth and must not be pooled with normal conditions.

## Browser inspection and failures retained

Headless Chromium was available and used for actual clicks, arrow/WASD key
events, pause/resume, condition selection, completion, early stopping, and a
390-pixel viewport overflow check. The browser script runs with
`participant_kind=synthetic`. It verifies that both the initial right-arrow input
and W after resume reach the logged physics actions. All recordings replayed.
The UI completion/stop metrics and preview labels were checked. Screenshots were
generated and visually inspected for the main conditions; the final images and
machine-readable results are under ignored `artifacts/browser-final/`.

Earlier failures are not counted as passing checks:

- Rendered Flask, pytest, and packaging documentation hosts returned HTTP 403.
  Their official source documentation on GitHub was accessible; package
  installation and GitHub operations worked through inherited networking.
- The first browser run failed because Playwright evaluated a string predicate
  under the page's CSP. Predicates were changed to functions, without weakening
  the CSP. It also exposed a missing favicon; an inline icon removed that 404.
- Inspection of keyboard handling identified focus retained by Pause/Resume.
  The UI now releases that button's focus; a browser assertion confirms that
  post-resume W input reaches physics.
- A later browser rerun failed its right-key assertion: the harness had accepted
  the previous trial's step-100 frame while a new start was pending. It now waits
  for the new active trial before holding a key. The final rerun passed all
  assertions. Failed-run artifacts were retained locally rather than overwritten.

No person performed usability validation or a participant trial. Screenshots and
headless interactions establish only the exercised software behavior. Browser
render scheduling and physical stimulus timing were not measured. The two-second
browser check uses an explicitly shortened config, while the CPU smoke and
documented demo use the full 30-second default.

## Remaining limitations

- A single global force, fixed-delay probe, and simple baseline filter; no learned
  model, spatial sensor deployment, co-adaptation, or held-out human transfer.
- Screen-only sensory preview; no hardware operation or acknowledgement, and no
  physical or perceptual matching claim.
- A single-session local development server and local JSONL logs; no participant
  identifiers, recruitment, consent workflow, or approved study collection.
- Simulation time may run slower than wall time. Replay verifies physics and
  information flow, not displayed frame timing. Exact replay requires matching
  implementation content and Python version.
- The reusable Cloud environment still needs the documented post-merge
  install/start configuration update and publication through its normal workflow.
