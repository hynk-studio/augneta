# 5.0-4 selective calibration: executed verification and findings

2026-10-15 (UTC), `/workspace/augneta` in the existing Augneta Cloud environment.
The primary conclusion is mixed software performance under assumed virtual
receiver models. This does not demonstrate human response savings or physical
calibration.

## Provenance and scope

Rechecked main: `67d7ce6953cb5c56ff14466b8490e2e261cd26be`.
PR #2 remained open/Draft at `411f72fada76df3b37226c54e975b78a2f4579e6`.
[PR #4](https://github.com/hynk-studio/augneta/pull/4) remained open/Draft at
`519b5d3639a79811a57621be40e83c6f2fa7c059`, on `feat/task-sensitivity-transfer`.
The new branch `feat/selective-calibration-simulation` was created from current
main and fast-forwarded to the exact PR #4 head. Its separate Draft PR targets
that dependency branch. No existing PR is merged, force-pushed or auto-merged.

The checkout was clean at start; earlier ignored runs and checkpoints were
preserved. Existing manual calibration, task physics/encoding/control, and the
5.0-3 design/results were not changed. The independently reported 100-test PR #4
review happened in another Work checkout; it is not a new run in this Cloud
workspace and is not counted below.

Python 3.12.14, existing lock-installed `.venv`; no dependency installs or lock
changes were needed. `pip check` passed. Package metadata adds only the frozen
JSON resource to wheel data. The environment and existing Site were not
republished, and no model API, GPU, device driver, Player, BLE or physical
stimulus was used.

Final tested package source SHA-256:
`fb00db66026361cb0e6332205469db82c408c31efc959134c08361cdb16f751d`.
The source identity routine covers Python/JS/HTML/CSS; the new JSON experiment
design has its own checked hash:
`8946de7a0291f3c4781257976c6ee900433c0fb4dc19907851bfeeefb8ca55f1`.
Both are persisted in the run manifest. Runs occurred before committing and
correctly record parent `519b5d3…`, `working_tree_dirty=true`.

## Design choices and information boundary

The [method](SELECTIVE_CALIBRATION.md) and versioned JSON were written **before
any development/check evaluation**. Gains 1/.75/.5, existing one-hot patterns,
78/156 budgets, three development and three disjoint check seeds, all four
scenarios, receiver noise/thresholds, tie rules and evaluation repetitions stayed
fixed. Focused engineering fixtures used seeds 998/999/1000 outside these splits.
There was no search for favorable results or check-driven tuning.

The selective policy targets directions with high observed baseline error,
reducing priority as observations accumulate. Both calibrated methods have the
same candidate catalogue and exact-rational Beta(1,1) balanced-error fitter.
Every 13th trial is a costed zero catch; 36 nonzero warm-up probes prevent
candidate/level starvation. The no-recalibration reference costs zero and is
reported separately. A shared-gain algorithm was omitted to keep this slice
focused on response allocation.

The pure allocator/fitter module receives immutable catalogue/history values,
not generator capabilities. The history contains only issued query, six command
values, and response; the selector additionally receives remaining budget and
its method identity. A runtime spy checks the actual runner's boundary, and a
counterfactual test gives different private seeds/scenarios identical permitted
responses and confirms identical queries/profiles. Model parameters, random keys
and evaluation records are retained only in the runner's artifacts. The receiver
responds to rendered commands without receiving expected labels. Evaluation
begins only after all method/budget profiles for a case have been frozen.

## Actual executed verification

| Command/check | Observed result |
| --- | --- |
| `.venv/bin/python -m pip check` | No broken requirements |
| `.venv/bin/python -m pytest -q tests/test_selective_calibration.py` | Initial 26 passed in 1.15 s; after reconstruction/tie tests, 29 passed in 1.98 s |
| `.venv/bin/python -m pytest -q` | **250 passed in 10.42 s**, complete fast suite once after final source changes |
| `.venv/bin/python -m augneta calibration-sim --out runs/selective-calibration-v1` | All **24 individual/scenario cases**, **16 split/scenario/budget cells**, 120 frozen profile evaluations completed |
| `.venv/bin/python -m augneta calibration-replay runs/selective-calibration-v1` | All 24 cases reconstructed exactly: calibration queries/commands/responses, selected profiles, held-out records, split summaries and complete summary |
| `.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir work/selective/wheels .` | Wheel built; zip inspection confirmed the exact frozen design JSON is included |
| Final documentation/artifact consistency | All 16 table rows match the persisted summary; 37 local Markdown targets exist; package source/design hashes match the executed run; `git diff --check` passed |

Concrete tests cover exact budgets including catches/warm-up, minimum exploration,
shared fitting, deterministic query order and method-order invariance, budget
prefixes, matched evaluation draw keys and independent phase namespaces, every
code in the metric, unknown/zero handling, immutable profiles, freeze-before-
evaluate ordering, tampered persisted responses/scores, malformed inputs, a
zero-cost reference, deterministic tie fallback, and uncorrectable negative
cases. No test requires selective calibration to win.

The actual CLI run used **11,232 calibration responses** and **49,920 held-out
responses**. These are not independent subjects: the unit is each virtual seed
within a scenario, with paired methods and repeated budgets. Source/design and
full traces occupy approximately 80 MB under ignored `runs/`, not Git.
`manifest.json` was written before simulation. Development summaries were
persisted before check evaluation. Reconstruction reuses the same exposed seeds
and is a reproducibility check, not a second unseen holdout.

No UI was changed, so the prior browser matrix and 324-trial task grid were not
repeated. The existing task/recording/replay and manual-calibration Flask tests
ran in the full suite. There was **no new Chromium or mock-DOM browser check**
in this step; prior browser evidence belongs to PR #4. Runtime failures in the
reported checks: none. pip printed its existing unwritable-cache warning and
disabled caching; the wheel build and dependency check succeeded.

## Complete cell summary

Balanced held-out joint error is lower-is-better. Each row averages **three
virtual seeds**, not the 416 responses within each profile evaluation. Δ is
selective minus uniform; negative favors selective. W/T/L counts per-seed lower,
equal, or higher error. Reference cost is 0; uniform/selective each pay the
listed budget (including zero catches). The same reference evaluation is reused
across budgets. All per-seed errors, profile hashes and contrasts are in
`summary.json`; all-code confusion and response allocation are in each case file.

| Split | Scenario | Budget | Reference error | Uniform error | Selective error | Mean Δ | SD of Δ | W/T/L |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| development | stable | 78 | 0.044071 | 0.044071 | 0.044071 | +0.000000 | 0.000000 | 0/3/0 |
| development | stable | 156 | 0.044071 | 0.044071 | 0.044071 | +0.000000 | 0.000000 | 0/3/0 |
| development | localized | 78 | 0.129006 | 0.055288 | 0.055288 | +0.000000 | 0.000000 | 0/3/0 |
| development | localized | 156 | 0.129006 | 0.055288 | 0.055288 | +0.000000 | 0.000000 | 0/3/0 |
| development | broad | 78 | 0.335737 | 0.058494 | 0.055288 | -0.003205 | 0.005551 | 1/2/0 |
| development | broad | 156 | 0.335737 | 0.053686 | 0.057692 | +0.004006 | 0.006939 | 0/2/1 |
| development | attenuated | 78 | 0.927885 | 0.927885 | 0.927885 | +0.000000 | 0.000000 | 0/3/0 |
| development | attenuated | 156 | 0.927885 | 0.927885 | 0.927885 | +0.000000 | 0.000000 | 0/3/0 |
| check | stable | 78 | 0.037660 | 0.045673 | 0.045673 | +0.000000 | 0.000000 | 0/3/0 |
| check | stable | 156 | 0.037660 | 0.048077 | 0.037660 | -0.010417 | 0.018042 | 1/2/0 |
| check | localized | 78 | 0.106571 | 0.037660 | 0.037660 | +0.000000 | 0.000000 | 0/3/0 |
| check | localized | 156 | 0.106571 | 0.053686 | 0.042468 | -0.011218 | 0.019430 | 1/2/0 |
| check | broad | 78 | 0.362179 | 0.087340 | 0.093750 | +0.006410 | 0.011103 | 0/2/1 |
| check | broad | 156 | 0.362179 | 0.075321 | 0.072917 | -0.002404 | 0.004164 | 1/2/0 |
| check | attenuated | 78 | 0.922276 | 0.922276 | 0.922276 | +0.000000 | 0.000000 | 0/3/0 |
| check | attenuated | 156 | 0.922276 | 0.922276 | 0.922276 | +0.000000 | 0.000000 | 0/3/0 |

## Interpretation, losses and limits

- **Stable/no-change:** development results tie the zero-cost reference. On
  check seeds, both calibrated methods at budget 78 have error 0.045673 versus
  0.037660 without recalibration. Calibration can harm an already suitable
  profile. At budget 156, selective ties the reference on average, while uniform
  is worse (0.048077); the selective-uniform difference comes from only seed 241
  (Δ -0.031250), with two ties.
- **Localized disturbance:** both methods at 78 reduce check error from 0.106571
  to 0.037660. At 156, errors increase to 0.053686 uniform and 0.042468 selective.
  More responses do not guarantee a better chosen profile on every stochastic
  realization. The higher-budget selective advantage again comes from one seed
  (211, Δ -0.033654); seeds 227/241 tie.
- **Broad disturbance:** development favors selective at 78 (Δ -0.003205) but
  uniform at 156 (Δ +0.004006). Check reverses that pattern: at 78 selective is
  worse (0.093750 versus 0.087340; Δ +0.006410), with seed 227 losing by 0.019231;
  at 156 it is slightly better (Δ -0.002404), driven by seed 241 (-0.007212).
  Uniform exploration can be preferable when many directions require attention.
- **Uncorrectable attenuation:** both calibrated methods tie the reference at
  both budgets. Check error is 0.922276, near the `12/13` error of a receiver
  answering zero for every stimulus. Questions cannot recover signals when all
  allowed candidates only reduce gain. Direction-selective allocation does not
  know which errors are correctable.

These results support a working harness and show limited, mixed allocation
effects. They do **not** establish a general reduction in response requirements;
in the localized case the two methods already tie at the smaller budget, while
other cells include losses and unnecessary recalibration. Budget 78 and 156 use
nested common-random-number histories, not independent replications. Only three
seeds per split/scenario were used; SD/ranges describe this small synthetic set.
No significance tests or human confidence intervals are reported.

The virtual receiver assumes an already-known nominal codebook, independent
Gaussian amplitude noise, fixed thresholds, and a 4% lapse rate. It omits human
learning/fatigue, temporal order effects, inter-motor perceptual interactions,
real amplitude transfer, skin dynamics and realistic response time. Matched
random draws reduce comparison noise but are an explicit modeling choice.
Good fit under these assumptions is not evidence of tactile calibration,
perceptual superiority, embodiment, or learned human transfer. No synthetic
winner is automatically applied to the rehearsal UI or tracking task.

All records retain `participant_kind=synthetic`, `human_evidence=false`,
`hardware_verified=false`, `profile_status=unvalidated_hardware_candidate`.
Physical/human validation remains device-dependent future work. Site deployment,
reusable Cloud configuration, existing PRs and manual WASD behavior are preserved.
