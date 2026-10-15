# Plan 5.0-3 verification and independent implementation review

2026-10-15 (KST), `/workspace/augneta` in the managed Augneta Linux environment.
This report concerns the final task branch, not the earlier 180-test preparation
or the interrupted attempt's 204-test summary.

## Base, checkpoint, and review decision

Remote main was rechecked as `67d7ce6953cb5c56ff14466b8490e2e261cd26be`.
[PR #2](https://github.com/hynk-studio/augneta/pull/2) remained open/Draft,
`feat/haptic-output-preparation` at
`411f72fada76df3b37226c54e975b78a2f4579e6`, auto-merge null. The task branch
`feat/task-sensitivity-transfer` was created from main and fast-forwarded to
that dependency. The new Draft PR targets that branch, not main; neither PR is
merged or configured for auto-merge.

Before rewriting, all modified files, new implementation/tests/method note,
scratch files, original diagnostic data and failed browser artifacts were saved
under `/workspace/work/augneta-5.0-3-checkpoint/`. `before-review.tar.gz` has SHA-256
`8b20a433d170e6a28a90d117e9b4f24ec99c37ae317d28d2aa610c8a1bca984d`;
`tracked.patch` and `manifest.json` record the branch, parent and file list.
The archive can be extracted into a separate directory for inspection/recovery.
No user work, PR #2 preparation, Site deployment, or environment definition was reset.

Review retained the square geometry, right-endpoint metrics, causal pipeline,
physics, and fixed PD coefficients: their behavior was coherent and testable.
A complete rewrite would not improve those contracts. It instead revised:

- Task UI/configuration: load server defaults, use task-specific headings,
  legend/instructions and summaries, hide the tracking target in the safe-zone
  public view, hide unused settings, and clear stale trial step state on restart.
- Compatibility: preserve the positional Config seed and permit prior small
  tracking arenas regardless of the unused default safe-zone width.
- Diagnostic audit: freeze settings/provenance on disk before either split,
  persist development before check, verify complete information/action/sensor
  traces by digest instead of equating a single final score, and report action
  saturation, arena-boundary occupancy, and outside-occupancy ceiling flags.
- Tests: post-evaluation interruption, malformed/missing/duplicate windows,
  task/size/score tampering, actual benchmark policy inputs, unequal packet
  timing despite equal final scores, task switching, and real browser control.

No seeds, dynamics, safe-zone size, policy coefficients, or delay/grid values
were tuned after observing check results. The final settings hash equals the
initial attempt's hash. The check split is disjoint from development but has
already been seen; this rerun is reproducibility evidence, not a new holdout.

## Runtime and final source

Python 3.12.14; Flask and test dependencies from unchanged
`requirements-dev.lock`; Chromium 154.0.8037.57 (Debian 13), Playwright 1.64.0.
The initially missing `.venv` was repaired in this checkout using:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pip check
```

No dependency/lock changes were needed. pip warned that its user cache was not
writable and disabled caching; installation succeeded and `pip check` reported
no broken requirements. The reusable environment was not republished.

Final tested `software_identity().source_sha256`:
`778b8f5bfdf535dcce6660a05f16f3ea3d25e11649610c1ad32e8ba70124826d`.
Runs occurred before committing, so they correctly record parent `411f72f…`
and `working_tree_dirty=true`. The digest covers package Python/JS/HTML/CSS and
identifies the tested implementation independently of later documentation commits.

## Actual final commands and results

Commands were executed from `/workspace/augneta`; generated paths below are
ignored by Git. Existing directories are never overwritten.

| Executed command/check | Observed result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | **221 passed in 7.85 s**, complete suite once after final source changes |
| `.venv/bin/python -m pip check` | No broken requirements |
| `node --check src/augneta/static/app.js` | Passed |
| `.venv/bin/python -m augneta smoke --out runs/reviewed-tracking-smoke --seed 7` | All 3 conditions complete, 600 ticks each, exact replays passed |
| `.venv/bin/python -m augneta smoke --config runs/safe-config.json --out runs/reviewed-safe-smoke --seed 7` | All 3 safe-zone conditions complete, 600 ticks each, exact replays passed; config was `{"task":"safe_zone","flow_strength":1.8}` |
| `.venv/bin/python -m augneta replay runs/reviewed-safe-smoke/dashboard` | Exact replay verified; outside 10.25 s / 0.410, normalized outside distance 0.06919818019140113 |
| `.venv/bin/python -m augneta sensitivity --out runs/sensitivity-reviewed` | All **36 split/task/grid cells**, **108 paired seed cases**, **324 trials**; input/trajectory/sensor matching verified |
| `.venv/bin/python tools/browser_check.py --out artifacts/task-browser-verified --chromium /usr/bin/chromium` | Actual headless Chromium + Flask; 6 complete runs and 2 interrupted runs, all 8 exact replays; no console errors |
| `AUGNETA_TEST_PYTHON=.venv/bin/python node tools/check_calibration_ui.mjs` | Real Flask API + **mock DOM harness**: 28 responses, freeze, export/import, stop, late presentation after hide; this is not a Chromium calibration check |
| `git diff --check` and local Markdown file-link check | Passed; 68 local file links resolve across 16 documents (external URLs/fragments not revalidated) |
| Baseline source extraction, smoke and byte comparison below | All 3 tracking trace files and evaluator files exactly identical to PR #2 |

For the baseline comparison, the existing checkout was preserved:

```sh
mkdir -p work/pr2-baseline
git archive 411f72fada76df3b37226c54e975b78a2f4579e6 src | tar -x -C work/pr2-baseline
PYTHONPATH=work/pr2-baseline/src .venv/bin/python -m augneta smoke --out work/pr2-baseline-smoke --seed 7
```

A Python byte comparison checked `trace.jsonl` and `evaluation_only.jsonl` in
all three baseline/current directories. This compares actions, physical state,
observations, beliefs, packet timing/content, and evaluator truth, not just the
score. Default tracking normalized RMSE remains 0.05808011850785609 (`none`)
and 0.045378297228523795 (both feedback views). Safe-zone high-flow smoke yielded
outside fractions 0.866 (`none`) and 0.410 (both feedback views).

The final diagnostic's **324 seed-level condition scores exactly reproduce the
initial raw scores**, independently compared from the two JSON files. All
no-feedback trajectory digests are invariant across sensor delay for each
fixed task/seed/flow strength. Source/reporting changed; experimental settings
and numerical behavior did not.

The real browser check loads server task/size/seed defaults, selects both tasks
and all three feedback conditions, checks actual canvas pixels for the green
square boundary and absence/presence of the orange target, sends arrow/W and
on-screen pointer controls, checks pause/resume, dispatches a blur event, stops
both tasks, checks task-specific scores and mobile overflow, and replays all
records. Screenshots were saved; the safe-zone desktop screenshot was inspected.
The blur event is programmatically dispatched in the browser, not a measured
real operating-system tab switch. These checks do not establish human usability
or physical latency. The browser uses a shortened 100-tick technical fixture,
not the diagnostic's 600-tick evaluation protocol.

## Diagnostic results (all configured cells)

Settings SHA-256:
`d894a2a9404a29a6340283af0af446b863a4c022657d6264e26c4f978a44fc2b`.
See [method](TASK_SENSITIVITY.md) for geometry, windows, denominator and controller.
Development seeds are 7/19/31; check seeds 101/113/127. Below is the mean of the
three **paired per-seed feedback-minus-none differences** in each split.
Negative means less error. `dashboard` and `sensory_preview` have exactly equal
policy input and trajectory digests in every paired case, so one column per
split represents both. Full per-seed summaries/contrasts, saturation and ceiling
flags are in `runs/sensitivity-reviewed/results.json`, with separate frozen
design/development/check JSON files. No grid cell or failed comparison is omitted.

| Task / primary metric | Flow strength | Sensor delay (s) | Development Δ | Check Δ |
| --- | ---: | ---: | ---: | ---: |
| tracking | 0 | 0 | -0.000509 | +0.000111 |
| tracking | 0 | 0.2 | -0.000492 | +0.000031 |
| tracking | 0 | 1.2 | -0.000246 | -0.000230 |
| tracking | 0.65 | 0 | -0.016293 | -0.013575 |
| tracking | 0.65 | 0.2 | -0.014916 | -0.012163 |
| tracking | 0.65 | 1.2 | -0.002058 | +0.001460 |
| tracking | 1.8 | 0 | -0.064366 | -0.062757 |
| tracking | 1.8 | 0.2 | -0.054852 | -0.055610 |
| tracking | 1.8 | 1.2 | +0.002886 | +0.003221 |
| safe_zone | 0 | 0 | +0.000000 | +0.000000 |
| safe_zone | 0 | 0.2 | +0.000000 | +0.000000 |
| safe_zone | 0 | 1.2 | +0.000000 | +0.000000 |
| safe_zone | 0.65 | 0 | +0.000000 | +0.000000 |
| safe_zone | 0.65 | 0.2 | +0.000000 | +0.000000 |
| safe_zone | 0.65 | 1.2 | +0.000000 | +0.000000 |
| safe_zone | 1.8 | 0 | -0.113189 | -0.133711 |
| safe_zone | 1.8 | 0.2 | -0.112308 | -0.127057 |
| safe_zone | 1.8 | 1.2 | -0.000422 | +0.007121 |

Tracking uses normalized tracking RMSE; safe_zone uses normalized outside
region distance. Their magnitudes must not be compared as the same outcome.

- **Floor/degenerate cases:** safe_zone at flow 0 and 0.65 has zero outside time
  and distance for all six seeds, every delay and all three conditions. These
  settings cannot distinguish the tested policies using the selected metrics.
  Zero flow has no useful hidden force; noisy feedback still produces small
  positive or negative tracking differences, which must not be treated as
  evidence that the task needs that information.
- **Information and delay sensitivity:** at flow 0.65, tracking check mean Δ is
  -0.012163 with 0.2 s sensor delay, but +0.001460 with 1.2 s. At flow 1.8,
  safe_zone check Δ is -0.127057 at 0.2 s and +0.007121 at 1.2 s. This is useful
  software sensitivity at some settings, with a genuine negative finding at
  long delay. No claim requires each delay increment to hurt every seed.
- **Per-seed variation:** tracking flow 0.65/1.2 s check Δ values are
  -0.006434 (101), +0.009201 (113), +0.001612 (127). Safe-zone flow 1.8/1.2 s
  values are +0.015138, +0.009652, -0.003428. A mean does not describe each seed.
- **Difficulty/ceiling:** no primary metric reaches the descriptive 0.95
  near-ceiling threshold. Nevertheless, check seed 127 at safe-zone flow 1.8/
  1.2 s is outside for 96.8% of the window and saturates at least one action
  component on 76.2% of ticks with feedback. This shows a difficult near-ceiling
  occupancy case even though normalized distance is far below 1. Its no-feedback
  outside fraction is 92.4%; the other check seeds are outside 87.2%/88.0% with
  long-delay feedback. These are limitations of this fixed policy/task pairing,
  not established human difficulty thresholds.
- **Matched views:** equality is expected because the scripted policy decodes
  the shared packet; it says nothing about perceptual or tactile superiority.
  The normal no-feedback and matched feedback comparisons are present alongside
  the deliberately delayed diagnostic, which is not the sole comparator.

## Failures, corrections, and limits

The inherited browser attempt failed before creating a server with
`PermissionError: socket operation not permitted`. Running the supported local
server/browser with the tool's network permission enabled resolved that setup
issue; no network-policy bypass or environment republish was used.

The resumed focused test run initially had one obsolete assertion expecting an
unused safe-zone width to invalidate a tracking configuration. It was corrected
to test the safe_zone case and a separate small-arena tracking regression test
was added. The first real browser review then found a stale `data-step` value
from the previous interrupted trial: the harness could mistake it for the next
trial and dispatch blur before the new trial was active. Clearing the stale
state on setup/start fixed the problem. The subsequent actual browser runs
passed; final-source checks above are the reported evidence. Earlier counts
are historical, not substituted for these executions.

All scripted records retain `participant_kind=synthetic`, `human_evidence=false`,
`hardware_verified=false`. There is no learned policy, participant inference,
trained-to-new-task transfer experiment, tactile learning, embodiment result,
physical timing measurement, or verified device. The fixed center-seeking
safe-zone policy does not adapt to zone width; the low-flow floor is documented,
not tuned away using the observed check seeds. Only six seed realizations and a
small fixed grid were exercised; correlated ticks do not enlarge that sample.

Calibration browser layout/perception, real user task usability, Windows/macOS
installation, Player/SDK/BLE, and real skin-level output remain unverified.
The six-motor calibration rehearsal remains distinct from the original task's
eight-direction software feedback preview. No Site or environment was published,
no physical device was operated, and no existing PR was merged.
