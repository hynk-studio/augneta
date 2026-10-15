# 5.0-4: selective calibration simulation, v1

This pre-arrival diagnostic compares response allocation under explicit virtual
receiver assumptions. It does not estimate human calibration time, tactile
perception, learning, or real transfer. PR #4 supplies the six-slot preparation
and task context; the legacy eight-direction task preview remains separate.

## Frozen experiment, before evaluation

The complete executable design is
[`selective_calibration_v1.json`](../src/augneta/data/selective_calibration_v1.json).
It fixes budgets **78 and 156**, development individual seeds **17,29,43**, and
disjoint check seeds **211,227,241**; 4 scenarios × 2 budgets × 2 splits.
The frozen design hash is
`8946de7a0291f3c4781257976c6ee900433c0fb4dc19907851bfeeefb8ca55f1`.
All results, including losses, are reported without searching for favorable seeds.
Every final profile is evaluated on **32 independent repetitions of each of 13
codes** (six directions × two nonzero levels, plus zero). These are correlated
responses within a virtual individual, not independent people.

Keep default `CodeSpec`, one-hot six-slot patterns, intensities (0,.25,.5), and
150 ms pulse/gap unchanged. Probe gains are **1,.75,.5**, all inside existing
software bounds. A candidate probe has the same gain in all slots; because each
stimulus uses one slot, the shared fitter can compose six independently selected
gains (at most 3^6 resulting profiles). This is a small factored parameterization,
not a semantic remapping. Default profiles and real rehearsal settings are never
changed. These numeric bounds are not verified hardware-safe limits.

## Response model and information boundary

The receiver gets the **rendered command**, not the intended label or method.
For each slot it computes `max(0, command*latent_multiplier + Gaussian(0,.025))`.
A 4% lapse produces unknown; otherwise peak < .12 produces zero; a top-two gap
< .04 produces unknown; otherwise the largest slot gives the direction and peak
< .375 gives level 1, else level 2. Zero commands can therefore yield unknown or
noise-driven false positives; nonzero commands can yield zero or unknown. The
receiver assumes the nominal codebook was learned already; it does not simulate
or establish that learning. Pulse/gap are fixed and not a model of human timing.

Virtual scenarios, with independently seeded per-slot multipliers:

| Scenario | Multipliers | Meaning |
| --- | --- | --- |
| stable | all uniform in [.95,1.05] | No imposed change needing correction |
| localized | one seeded slot in [1.8,2.2], others [.95,1.05] | Local amplification that reduced gain may correct |
| broad | all [1.35,1.9] | Widespread amplification |
| attenuated | all [.18,.25] | Uncorrectable attenuation: candidates cannot raise gain above 1 |

The allocation/fitting module cannot see these parameters. It accepts only an
immutable candidate catalogue and prior issued labels/commands/responses (plus
remaining budget for selection). No receiver, RNG, seed, scenario, evaluation
record or latent/confusion table crosses that boundary. The runner/evaluator
owns private model data. This is a program data-flow boundary, not a malicious
Python-code sandbox.

## Same-budget comparison

- **No recalibration:** default profile, **zero** calibration responses; report
  as a distinct cost reference, not an equal-budget method.
- **Uniform:** cycle through direction/candidate/level combinations evenly.
- **Selective:** first issue each of the 36 nonzero combinations once. Then
  choose the direction maximizing baseline-gain posterior joint error divided by
  the square root of its total nonzero query count; within that direction choose
  the least-sampled gain and then least-sampled level. It targets apparent
  baseline difficulty with declining priority as samples accumulate. It does
  not know whether the disturbance is correctable.

For both calibrated methods, **every 13th response is a zero catch trial** at the
base profile. Warm-up and all catches count toward the budget: 78 responses =
72 nonzero + 6 catches; 156 = 144 + 12. Minimum exploration gives every
candidate/level in every direction an observation before selective allocation.
Direction ties use ascending index, gain ties prefer 1 then .75 then .5, and
level ties prefer 1. Fitting uses exact rational posterior errors to preserve
mathematical ties; direction priorities use a square root. Uniform and selective use exactly the same fitter:
minimize per-direction mean posterior joint error across levels, with Beta(1,1)
smoothing separately for each candidate/level. Catches do not identify gains
because all gains render zero identically; they remain costed and reported.
No shared-gain algorithm is added in this small slice.

## Randomness, freezing and outcome

Each local `random.Random` is seeded by SHA-256 of canonical JSON keys. Latent
keys use version/individual seed/scenario/latent. Calibration keys add phase,
direction, level, candidate index and occurrence of that exact query. Thus the
same nth query shares draws across methods; adaptive order does not change or
expose the response stream. Budget 78 is a prefix of the corresponding
156-response history; budgets are repeated measurements, not independent data. Evaluation uses a separate phase, direction, level
and repetition, **excluding gain, method and budget**. Each call consumes one
uniform lapse draw and six Gaussian draws, even when a lapse occurs. Held-out
evaluation stimuli/draws are therefore matched across all profiles, while
calibration responses remain independent of evaluation. This coupling is a
variance-control assumption, not a model of responses over human time.

All methods/budgets freeze profiles before evaluation begins for that
individual/scenario. The primary outcome is the mean of the 13 per-code joint
error rates; a correct nonzero answer requires both direction and level, zero
is correct only for zero, and unknown is always incorrect. Every code is
included, regardless of calibration allocation. Report full per-code confusion,
allocation/cost, profile hashes, and per-seed paired differences. Split-level
mean/SD/range and win/tie/loss counts describe only the three virtual seeds in
that split. No significance or human sample-size claims are made.

## Execute and reconstruct

```sh
.venv/bin/python -m augneta calibration-sim --out runs/calibration-v1
.venv/bin/python -m augneta calibration-replay runs/calibration-v1
```

The output directory must be new. It contains frozen design/source metadata,
private model parameters, calibration traces, frozen synthetic candidate
profiles, held-out evaluation records and summaries. All carry synthetic,
non-human/non-hardware evidence labels; profiles are unvalidated candidates.
A per-case reconstruction checks commands, queries, keyed responses, fitted
profiles and metrics using the matching source/Python version. Generated runs
stay outside Git. Nothing is installed in the manual calibration UI.

Actual results, executed checks, failures and limits are recorded separately in
[verification](VERIFICATION_SELECTIVE_CALIBRATION.md).
