# First implementation: hidden-flow tracking

Status: planned; no implementation or experiment results yet.

Implement the first runnable experiment for Augneta in https://github.com/hynk-studio/augneta. Augneta is an independent human–AI sensory augmentation research project.

## Research intent

Build a system for asking whether model-inferred environmental information can become a learnable, transferable sensory input for a human operator. The first task uses a hidden force/flow that affects a user-controlled point tracking a visible moving target. Model-estimated flow is eventually conveyed through a physical haptic interface. The first PR must deliver a runnable task, not merely a registry, schemas, or an empty framework.

## Companion design

Read the repository-root AGENTS.md, README.md, and docs/PROJECT_SELECTION_AND_PROTOCOL.md. Preserve the distinctions between technical verification, synthetic-policy results, offline biological data, and actual human evidence.

## Workspace and permission

Inspect the repository root, branch, status, remotes, and project instructions before writing. Use a dedicated checkout or worktree of hynk-studio/augneta and branch from the current main. Preserve unrelated changes and keep all work within Augneta. The existing remote is the authorized destination: open a Draft PR against main with auto-merge disabled. If PR creation is unavailable, preserve the reviewable branch/change set and report the exact blocker and PR-body draft; do not report a PR as created.

## First PR objective

Deliver an end-to-end, locally runnable hidden-flow tracking task:

1. A deterministic simulation of a bounded user-controlled point and a visible target.
2. Hidden, controlled flow/force dynamics affecting the point.
3. A sensor-observation stream with configurable noise and delay.
4. A causal online estimator that uses only permitted current/past observations.
5. Direct user control; no autonomous AI action selection in the main conditions.
6. No-additional-information and information-matched visual-dashboard conditions.
7. A development-only preview of the sensory code, explicitly NOT verified physical haptics.
8. Trial/session logging, deterministic replay, and a basic tracking-error report.
9. Executable automated tests and a demonstrated synthetic-policy smoke run.

## Architecture guidance

Prefer a small maintainable implementation with a lightweight interactive local UI and a testable analysis core. Choose current supported library versions after inspecting their official documentation and the environment; do not guess exact APIs or fabricate a successful installation. A Python simulation/analysis core with a browser interface is a reasonable default. The first slice must support CPU-only headless execution without a model API or physical device. Add frontend tooling only where the implementation uses it, and keep dependency and lock files consistent with the selected stack.

The environment ground truth must be separated from the estimator's observation object. Only the evaluator and a conspicuously labelled oracle diagnostic may access hidden state. A baseline causal state-space estimator is sufficient for this slice; call it what it is. A learned world model can be added through the same interface later. Do not market a hand-written filter as a demonstrated cognitive world model.

Specify all equations, time units, clipping, boundaries, target trajectories, and flow parameters in a short methods document. Maintain one consistent interpretation of sensory direction: it reports the environmental force, not the action the user should take. In the main task the information encoder must not use the user's target or the optimal action. This supports later transfer to different goals.

## Comparators and information parity

The dashboard and sensory-code preview must receive the exact same estimated state, uncertainty, quantization, update timing, and dropout flags where applicable. A future sensory advantage cannot be attributed solely to access to extra information. A no-information baseline is useful but is not the only comparator.

Implement an explicit oracle mode only as a diagnostic and keep its outputs separate. Do not allow accidental use of ground truth in the estimated-state conditions. Delayed or shuffled feedback may be added as a causal diagnostic, but do not present such deliberately degraded conditions as the sole fair benchmark.

## Observation/log contract

Record at least: run/session/trial ID, seed, software/config identity, timestep or monotonic timestamp, condition, target and visible state, observed sensor values, estimator output and uncertainty, encoder identity, user or scripted action, intended feedback, available output acknowledgement, model/encoder change events, dropout/latency flags, and per-trial error summaries.

Do not place hidden ground truth in any public observation object provided to the estimator or user-facing renderer. If ground truth is logged for evaluation, keep it explicitly tagged and inaccessible to online decision components.

If physical output is absent, record hardware_verified=false. If the run uses a scripted policy, record human_evidence=false and participant_kind=synthetic. A UI preview is not a delivered haptic signal. A hardware acknowledgement alone is not verification of skin-level stimulus timing or perception.

## Metric

Implement normalized tracking RMSE over a predetermined evaluation window. Define the normalization constant and failure handling explicitly. Report component metrics separately rather than inventing a single embodiment or consciousness score. Do not claim statistical significance for synthetic runs or generalize a developer's trial to human participants.

## Future-update support without overbuilding

Permit estimator and encoder versions to be logged independently. Add a small deterministic test showing that an estimator version can change while the external semantic code remains fixed. Full co-adaptive optimization, human learning claims, and a longitudinal migration policy are not required in this first PR.

## Required tests

- Same seed/config/action sequence reproduces trajectories and metrics.
- The estimator cannot access hidden ground truth or future observations.
- Delayed data is processed according to its timestamp and missing observations are handled explicitly.
- Dashboard and sensory-code inputs are matched.
- Main conditions do not modify actions autonomously.
- Oracle diagnostics are labelled and separated from normal results.
- Synthetic/human and simulated/physical output labels cannot be silently promoted.
- Model updates and encoder changes are separately identifiable in replay.
- The error metric is checked against an independently calculated small example.
- Invalid config or unavailable hardware does not silently report success.

## Data, network, hardware, and safety

Use synthetic environment data in this PR. No paid API calls, account setup, credential creation, personal recording uploads, participant recruitment, external data collection, device purchase, or device stimulation is authorized. Do not invoke haptic/electrical hardware automatically. These are execution permissions for this slice, not permanent limits on the research program. Do not simulate public EEG/EMG results and report them as observations. The project will use separately reviewed public biological data and real human studies in later or independent slices.

Human-data collection features should not default to collecting identifiers. A developer running the local UI for functional inspection must not be described as an approved research participant. Keep participant-study recruitment, consent and formal data collection outside this first slice.

## Deliverables

- Runnable local demo with exact launch instructions.
- Headless synthetic-policy smoke run and result artifact.
- Tests and actual command outputs.
- Short methods/protocol document with information boundaries and metric definition.
- Limitations stating that no human learning, embodiment, sensory extension, physical feedback, or consciousness result has been established.
- PR or local PR draft stating what was implemented, what was run, what failed, and what remains unverified.

## Workflow

Environment preparation is documented separately in docs/tasks/CLOUD_ENVIRONMENT_SETUP.md. This task is complete only when the runnable slice and its verification are delivered.
Implement, test, and prepare the Draft PR for review. Preserve relevant failure results rather than silently rewriting them. Do not merge or enable auto-merge. Report actual repository/branch identity, changed paths, test counts and results, demo instructions, and the exact status of physical/human evidence. No claims of background completion or future results.
