# First hidden-flow experiment: methods

This is a software development experiment, not a participant-study protocol or a
physical feedback experiment. The estimator is a hand-written causal random-walk
Kalman baseline, not a learned world model. The only data source is the synthetic
simulator. No biological data, model service, or device is used.

## Dynamics and timing

All spatial quantities use arbitrary arena units. Force means acceleration in
units/s²; mass is one. Positive x is right/east; positive y is up/north.
Integer tick `k` corresponds to `t = k Δt` seconds. Defaults are in `Config`:

| Parameter | Default |
| --- | --- |
| Δt / trial length | 0.05 s / 600 steps (30 simulated seconds) |
| Arena | x and y in [−1, 1]; initial position and velocity (0, 0) |
| Control gain / linear drag | 2 units/s² per input unit / 1.2 s⁻¹ |
| Maximum speed | 1.5 units/s per axis |
| Flow strength A / period P | 0.65 units/s² / 9 s |
| Target radius R / period T | 0.5 units / 16 s |
| Sensor cadence / fixed delay | 4 ticks (200 ms) / 4 ticks (200 ms) |
| Sensor Gaussian noise σ / dropout | 0.18 units/s² per axis / 0.1 per sample |
| Feedback cadence | 4 ticks (200 ms), held between emissions |
| Evaluation window | state ticks 101…600, i.e. 5 < t ≤ 30 s |

The target is `r(t) = (R cos(2πt/T), 0.7 R sin(2πt/T))`.
Let `θ = 2πt/P`; draw four independent phases `(a,b,d,e)` uniformly on [0,2π)
from Python `random.Random(seed)`. The hidden, spatially uniform force is:

```text
f_x(t) = A [sin(θ + a) + 0.35 sin(0.43 θ + b)]
f_y(t) = A [cos(0.79 θ + d) + 0.35 sin(0.61 θ + e)]
v_next = clip(v + Δt [2 u + f(t) − 1.2 v], −1.5, 1.5)  # per axis
p_next = p + Δt v_next
```

The coefficients in the last two equations are configurable. If a position
exceeds an arena boundary, clamp that coordinate and zero its velocity. There
is no wrapping or hidden penalty. Inputs must be two finite numbers in [−1,1];
invalid inputs are rejected, not corrected. Arrow/WASD buttons generate −1, 0,
or 1 per axis; diagonal inputs can have norm √2. The exact accepted action is
applied and logged. No estimator or encoder can replace it in the interactive UI.

At tick k: apply scheduled component changes, deliver eligible observations,
update belief, possibly emit feedback, expose the restricted view, accept the
action, and integrate to k+1. Initial feedback is available before the first
action. Metrics use the post-action state. No sensor observation at k+1 is used
for the action at k. Trial-end presentation retains the last feedback packet.

The browser sends one action per request, with an expected tick to reject
duplicates. It never sends catch-up batches. Slow requests slow simulation time;
pausing or losing focus freezes simulation time and clears held input. One
already submitted action may finish during a pause. Simulation timestamps are
not display, device, skin, or perception timestamps. Request duration appears in
the UI but is not used to rescale physics or claim delivery latency.

## Sensor and causal estimator

Every sensor tick, an independent RNG seeded by `seed XOR 0xA617` draws a dropout
indicator and two Gaussian noise values. Noise is drawn even on dropout. A fixed
probe observes the global force: `z_s = f(s Δt) + ε`, with `ε ~ N(0,σ² I)`.
Only `sample_step`, `available_step = sample_step + delay`, `value`, and `dropped`
cross the sensor boundary. A dropout carries `value=null`. Non-sampling ticks
and not-yet-arrived samples are empty observation batches, not zero measurements.

The filter receives only these observations, the current tick, Δt, σ, and its
own version. It has no seed, world reference, flow parameters, target, or action.
Its two means share a scalar diagonal covariance. For process variance rate
`q=0.04` units²/s⁵ (`rw-kalman-v1`), zero initial mean and unit prior variance:

```text
P_prior(s) = P_previous + q (s − previous_sample_step) Δt
K = P_prior / (P_prior + σ²)
mean = mean + K (z_s − mean)
P_posterior(s) = (1 − K) P_prior(s)
P_present(k) = P_posterior(s) + q (k − s) Δt
```

The initial prior is referenced to tick zero. This is constant-mean prediction,
not a model of the simulator's sinusoids. Delayed samples update at their original
sample time, then uncertainty propagates to the present. Missing values never
update the mean; uncertainty grows. A full batch is validated before updating.
Future arrivals and backwards clocks are rejected. Samples older than or equal
to the last assimilated sample are ignored with `ignored_stale` counts; there is
no retrospective smoother. Status distinguishes `waiting`, `fresh`, `held`, and
`dropout`; the last arrival's dropout flag persists until the next accepted
arrival. Covariance is a model quantity, not a calibrated human confidence score.

## Information boundaries and feedback

```text
simulator truth ── sensor + noise + delay ── observations ── causal belief
       │                                                      │
       └── evaluator_only.jsonl                target-free encoder
                                                              │
                                                     one quantized packet
                                                      /              \
                                                 dashboard       code preview
```

The simulator necessarily uses truth to generate physics and measurements.
Only offline evaluation and an explicitly selected oracle diagnostic get its
separate truth export. Neither the filter nor the normal renderer receives it.
The renderer/policy view contains visible position, velocity, target, time,
condition, and permitted feedback. Raw observations and unquantized beliefs are
logged for offline analysis but are absent from the rendering API. These are
software interface boundaries, not a sandbox against a developer inspecting the
simulator source or local evaluator files.

`polar8-v1` accepts **only belief**. It rounds direction to eight bins, east=0,
counterclockwise; magnitude to levels 0…4 over [0,1.5] units/s²; and standard
deviation to 0.25-unit levels 0…8 (capped at 2). Rounding is `floor(x+0.5)`.
Magnitude saturates at 1.5. Zero magnitude has canonical direction zero and no
active channel, so it cannot carry an extra direction. A nonzero code activates
one of eight channels at `magnitude_level/4`. The meaning is **environmental
force direction**, never a target-specific correction or optimal action.

| Condition | Online additional information |
| --- | --- |
| `none` | None; feedback is null. The estimator runs with its output withheld. |
| `dashboard` | Quantized direction/magnitude arrow and uncertainty/status/age |
| `sensory_preview` | Screen-only channel ring plus the same numeric information |
| `oracle_diagnostic` | Explicit CLI-only diagnostic using truth with zero variance |

Dashboard and preview receive exactly the same packet, including quantization,
emission tick, last sample tick, sample age at emission, delay/dropout flags,
sensor status, component identities, and channel intensities. Both hold the same
packet between updates. The preview adds no unquantized data. Shape, brightness,
layout, and perceptual salience differ: these are two visual renderings, not an
information-matched physical haptic comparison. No psychophysical parity is
established. The oracle is marked at every run's metadata/view/summary and is
excluded from the three main conditions; `oracle-smoke` uses a separate directory.

## Version changes

`ChangeEvent(step, component, identity)` is a small Python API used in the tests.
Estimator and encoder events are independently logged with old/new identities
and state-transfer rules. `rw-kalman-v2` changes q to 0.12 and resets to the same
tick-zero prior; it consumes only subsequently delivered observations. It is a
test variant, with no claim of superior estimation. Keeping `polar8-v1` preserves
the mapping even when belief values change. `polar8-rotated-v1` deliberately
rotates channel indices by two for a separately identifiable remapping test.
Either event forces a common immediate feedback emission. No adaptive human
training or migration policy is implemented.

## Metric, logging, and replay

The predefined default window is `(100,600]` state ticks. With N=500 paired
position/target samples, `tracking_RMSE = sqrt(sum(||p_k − r_k||²)/N)` and
`normalized_tracking_RMSE = tracking_RMSE / (2√2 L)`, where L is arena half-width.
The denominator is the full arena diagonal (2.8284271247461903 by default).
No outlier trimming or post hoc window selection is performed. Incomplete trials,
missing/duplicate/out-of-order window samples, invalid vectors, and nonfinite
data produce no valid score (`null`, `incomplete_or_invalid`). Invalid metric
configuration raises an error. A completed trial is required even if its
evaluation window ends early. The metric is checked against a 3–4–5 example.

Each recording directory contains:

- `metadata.json`: run/session/trial IDs, seed, complete config and hash,
  package version, Python/platform, Git commit/dirty status, implementation
  content hash, condition, initial component identities, change schedule, policy
  identity, time units, and evidence labels.
- `trace.jsonl`: one flushed row per accepted action, before/after visible state,
  delivered observations, belief and covariance, exact feedback packet, submitted
  and applied actions, intended feedback, `output_acknowledgement=null`, and events.
- `evaluation_only.jsonl`: separately tagged hidden force used for each transition.
- `summary.json`: completion status, fixed-window metrics, and evidence labels;
  written on completion or explicit stop. A crash may leave no summary and cannot
  be mistaken for successful completion.

Replay re-executes recorded actions and version events from seed/config, comparing
all trace fields, evaluator truth, and summary exactly. Truth from the file is
never fed to a policy or filter. The implementation content hash and Python
version must match. Git commit/dirty metadata records provenance; the content hash
allows a pre-commit run to replay after committing identical code. IDs need not
repeat across fresh runs. This is deterministic verification, not cryptographic
tamper-proof provenance or a reconstruction of browser wall timing.

The CPU smoke policy (`visible-pd-v1`) uses only the public view:
`u = clip((5(target−position) − 2.4 velocity − decoded_feedback_force)/control_gain, −1,1)`.
It is not called by the UI. Dashboard and preview necessarily produce identical
synthetic actions in this check; their equality validates the information path,
not sensory usefulness. Results are descriptive technical checks with no
significance tests, participant inference, held-out learning, or transfer claim.

## Evidence and remaining scope

All scripted runs are `participant_kind=synthetic`, `human_evidence=false`.
An ordinary UI run is `participant_kind=developer`, also `human_evidence=false`:
functional inspection does not create an approved participant study. Every run
has `hardware_verified=false`, `output_mode=software_only`, and no output
acknowledgement. Requesting hardware fails before creating results. None of the
API inputs can promote these labels to participant evidence or physical success.

No device timing, skin-level stimulus, perception, human learning, embodiment,
sensory extension, neural change, or consciousness result is established. Future
work needs device verification, human usability and task-sensitivity work, and a
separately scoped participant protocol. Human inference must use participants,
not dense time samples, as the independent unit. Negative outcomes must remain
reportable. The local Flask development server is single-session tooling, not a
multi-user study platform or production deployment.
