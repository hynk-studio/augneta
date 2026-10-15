# Plan 5.0-3: task sensitivity and safe-zone transfer support

This is executable software preparation, not a transfer study. Tracking remains
`Config.task="tracking"` by default. `safe_zone` changes the control objective,
not the physics, observations, estimator, encoder, or direct human action path.

## Geometry and evaluation (declared before result interpretation)

The arena is `[-A,A]²`, A=`arena_half_width`; the safe region is the closed,
axis-aligned central square `[-h,h]²`, h=`safe_zone_half_width` (default 0.2).
For safe_zone, configuration requires finite `0<h<A`. An unused safe-zone size
does not restrict the tracking arena; both the zone size and other numeric fields
are still validated for type and finiteness. Boundary points are inside. The UI draws
this square and hides the moving tracking target for this task. The simulator
retains its legacy target field in offline trace states for replay compatibility;
`Trial.view()` removes it for safe_zone, so the renderer and scripted policy
receive no moving target for this task. The safe-zone metric never uses it. A new task is not evidence of learned transfer.

For both tasks evaluate right endpoints `start < step <= end`, by default
steps 101..600 (500 samples, simulation times 5.05..30.00 s). Each sample represents
one `dt_s=0.05` interval: the occupancy denominator is 25 simulated seconds.
This is tick occupancy, not sub-tick crossing-time interpolation. A completed
trial and the full ordered window are required; stop, missing, duplicate, or
invalid samples receive null complete metrics, even after the window ends.
Pause adds no simulation samples; stop retains the partial recording.

Safe-zone distance at position `(x,y)` is
`sqrt(max(|x|-h,0)^2 + max(|y|-h,0)^2)`. Report:

- `outside_time_s = outside_sample_count * dt_s`;
- `outside_fraction = outside_sample_count / window_sample_count`;
- `normalized_outside_distance = mean(distance over ALL window samples) /
  (sqrt(2)*(A-h))`. The denominator is the largest possible distance inside the
  arena, at a corner; clipped world positions give values in [0,1].

Tracking retains its RMSE / arena diagonal. Neither metric is renamed a human
transfer score. Recordings retain the full task configuration and exact replay.
The source digest changes with implementation; old source recordings still
require their corresponding source version, as before.

## Frozen diagnostic v1

Settings are fixed in `src/augneta/sensitivity.py` before reporting either split.
The initial attempt already exposed these check results before the resumed
review. The final run retains every experimental setting and all seeds; it is a
reproduction, **not a new unseen holdout**. No check-driven tuning was performed.
The settings hash remains
`d894a2a9404a29a6340283af0af446b863a4c022657d6264e26c4f978a44fc2b`. Development seeds: **7,19,31**;
disjoint check seeds: **101,113,127**. Run every combination of both tasks,
flow strengths **0,0.65,1.8**, sensor delays **0,4,24 ticks** (0,0.2,1.2 s), and
`none`, `dashboard`, `sensory_preview`. All other fields are Config defaults:
600 ticks, the window above, same noise/dropout and feedback update cadence. Config and
policy coefficients remain the initial attempt's values; center seeking is a
fixed reference controller, not a learned policy or a zone-size-adaptive policy.
Thus 36 split/task/grid cells, 108 seed pairs, 324 trials, CPU only.

Delay here is sensor observation availability delay. It is separate from feedback
update cadence, network latency, and physical stimulus latency (unmeasured).
The matched views share exactly the same packet, timing, quantization,
uncertainty and dropout. The no-feedback condition receives no packet.

`visible-pd-v2` is the existing smoke PD controller extended with a fixed origin
reference for safe_zone: `clip((5*(reference-position)-2.4*velocity-decoded_force) /
control_gain, -1,1)` per axis. It uses only visible position/velocity, the visible
tracking target or fixed center, and the feedback packet. It receives no truth,
raw sensor observations, seed, or future data. Both matched views use the same
policy and decode the same force; equal software performance is expected. The
web UI continues to apply only direct user input; this policy is CLI/test only.
Estimator identity is `rw-kalman-v1`; encoder identity is `polar8-v1`. Changing
objectives cannot alter the meaning of a given estimated flow.

Each JSON cell includes every seed's configuration, complete task summary,
feedback-minus-none differences (negative is better), and matched-view equality.
Safe-zone contrasts include outside fraction/time as well as distance. The
matched audit compares SHA-256 digests of every policy input (including feedback
timestamps), action/state trajectory, and sensor stream; equal scores alone do
not suffice. All three conditions must share the same sensor stream. Full traces
are retained by `smoke`; the bounded diagnostic saves summaries and digests.
Floor is metric <=1e-12; near-ceiling is metric >=0.95. Zero-flow cells are marked
degenerate even when sensor noise creates nonzero feedback. These thresholds are
descriptive flags, not validated human difficulty bounds. The output additionally
reports each seed/condition's action-saturation and arena-boundary fractions over
the same window, and a safe-zone occupancy ceiling flag when outside fraction
is >=0.95. Tracking RMSE need not approach 1 with an interior target; the absence
of a near-ceiling RMSE flag does not establish useful difficulty. Seed summaries are kept
separate from the correlated simulation ticks. There are no significance claims
and no requirement that every delay increment worsen performance.

```sh
.venv/bin/python -m augneta sensitivity --out runs/sensitivity-v1
.venv/bin/python -m augneta serve --port 8000
```

Choose **Target tracking** or **Safe-zone maintenance** and its square half-width
in the UI. Server `serve --config` task/size/seed defaults are loaded into the
form; tracking stays the default without overrides. WASD, arrows, on-screen controls, pause, and stop work in both tasks.
For CLI smoke/replay of safe_zone, save `{"task":"safe_zone"}` as
`runs/safe-config.json`, then:

```sh
.venv/bin/python -m augneta smoke --config runs/safe-config.json --out runs/safe-smoke --seed 7
.venv/bin/python -m augneta replay runs/safe-smoke/dashboard
```

The CLI writes `design.json` with settings/source provenance before running
either split, then `development.json` before executing check seeds, then
`check.json` and combined `results.json`. Report schema 2 adds audits; experiment
settings remain v1. Output paths must be new. Runs stay outside Git. JSON records include frozen
design/configuration, seeds/splits, window, policy/component identities, source
provenance, and `participant_kind=synthetic`, `human_evidence=false`,
`hardware_verified=false`. New seeds and a scripted controller demonstrate
software properties, not tactile learning, embodiment, or learned human transfer.
Actual results and remaining limits are in [verification](VERIFICATION_TASK_SENSITIVITY.md).
