# Pre-arrival software verification

Verified on 2026-10-15 in the Linux ChatGPT Work cloud workspace. This is a
software workflow check, not physical calibration or a participant study.

## Source and runtime

- Base `main`: `67d7ce6953cb5c56ff14466b8490e2e261cd26be`.
- Retained PR #2 preparation: `2dc691a4333b4baf2b2d50c7ab3578e9bf5e19ce`.
- Integrated plan commit: `4cf8c8cf9091bb49cba1b8a0b82b5b6fd6da3ce3`.
- Checked source digest, as recorded by `software_identity()`:
  `3189a1090a05744c36242c017ed1669591a57c125a256ef357536e1dd9371cb3`.
- Python 3.12.14. Existing lock-installed dependencies from the prior preparation
  checkout were reused; `PYTHONPATH=src` selected this implementation's source.
  No dependencies, lockfiles, SDKs, or environment settings were changed. A fresh
  Windows/macOS installation was not performed.

The runs occurred before committing, so their Git metadata correctly records
the PR #2 parent and `working_tree_dirty=true`; the source digest identifies the
tested implementation. Documentation-only changes do not alter that digest.
The prior [PR #2 verification](VERIFICATION_PR02.md) remains a historical record.

## Commands and results

From `/workspace/scratch/3b700d20a46e/augneta-prearrival`, using the existing
interpreter `/workspace/scratch/3b700d20a46e/augneta-pr02/.venv/bin/python`:

| Check | Actual result |
| --- | --- |
| `PYTHONPATH=src <python> -m pytest -q tests/test_tactile_preparation.py` | 23 passed in 0.34 s |
| `PYTHONPATH=src <python> -m pytest -q` | 180 passed in 1.46 s |
| `node --check src/augneta/static/calibration.js` | Passed |
| `PYTHONPATH=src AUGNETA_TEST_PYTHON=<python> node tools/check_calibration_ui.mjs` | Passed: 28 responses through the actual Flask API, fit/review/freeze/validation, JSON export/import, stop, and a delayed presentation response after the page becomes hidden |
| `PYTHONPATH=src <python> -m augneta smoke --out runs/prearrival-final-smoke --seed 7` | Three complete 600-step trials; all three exact tracking replays verified |
| `PYTHONPATH=src <python> -m augneta haptic-smoke --out runs/prearrival-final-haptic-smoke --seed 7` | Legacy eight-slot check: 600 steps, 150 commands/shared-packet checks, final output stopped, exact tracking replay verified |
| Local Markdown file/fragment check | 61 links across 15 Markdown files passed |
| `git diff --check` | Passed |

The DOM harness uses a small in-memory DOM and a controlled clock with a real
temporary Flask HTTP server. It runs the actual page JavaScript and checks HTML
IDs, but **is not a browser engine, screenshot/layout check, or real-time timing
measurement**. Its server, responses and files are temporary; it stops cleanly.
The Python tests include static asset/API requests as well as the session model.

The final legacy tracking normalized RMSE values were `0.05808011850785609`
(none) and `0.045378297228523795` (both matched feedback views), unchanged from
the earlier baseline. They are synthetic tracking results, not six-motor or
tactile performance. All generated records remain outside Git.

## Behavior covered

- Independent semantic category count and six command slots, including explicit
  four- and eight-direction profiles; rejection of aliased or malformed patterns.
- Zero-direction erasure, strict meaning/profile identity, per-motor gain changes
  that preserve the matched visual meaning, and causal estimator-belief encoding.
- No target/action/evaluator-truth fields accepted by the new rendering contract.
- Separate randomized fit/validation blocks, manual profile freeze, immutable
  meaning during validation, and descriptive direction/magnitude confusion tables.
- Unknown versus zero responses; duplicate/stale/early responses; incomplete
  session preservation; candidate profile import/export and provenance labels.
- Invalid new-session requests preserve the existing session; old session IDs
  cannot mutate its replacement; requests cannot promote hardware/human evidence.
- Existing origin/content-type restrictions also cover the new routes.
- Clearing the visual output and rejecting a late presentation after page hiding.

## Remaining checks and limits

No new automated failures remain in the checks above. A supported real browser
was not available here; actual rendering, browser event timing, human usability,
and local Windows/macOS installation remain unverified. No browser was installed
as a substitute for the available environment's supported preview workflow.

There is no physical adapter, Player/SDK connection, BLE test, skin-level onset
measurement, perceptual calibration, or tactile learning result. The 6-direction,
2-level, 28-response defaults are software test choices, not established human
capacity, trial counts, or comfortable stimulation settings. Profiles remain
`unvalidated_hardware_candidate`; `hardware_verified=false` and
`human_evidence=false`. Synthetic and developer visual responses have distinct
provenance labels.

The new six-slot path is not yet connected to the tracking task's presentation
schedule. Uncertainty/age/dropout remain in the original task. Selective
calibration algorithms, task sensitivity/transfer support, and physical/human
studies are later work in the [plan](tasks/TACTSLEEVE_INTEGRATION.md).

The existing ChatGPT Site was inspected as v1 and was not modified or published.
The reusable Codex Cloud environment was not edited or republished, and no
separate Codex Cloud task or user PC process was launched. See the
[execution guide](PREARRIVAL_PREPARATION.md) for the new local rehearsal route.
