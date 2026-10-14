# Augneta agent instructions

## Read and scope

- Confirm that the checkout belongs to `hynk-studio/augneta`; inspect branch, status, and remotes before changes.
- Read `README.md`, the relevant sections of `docs/PROJECT_SELECTION_AND_PROTOCOL.md`, and the assigned task.
- The first implementation is specified in `docs/tasks/FIRST_IMPLEMENTATION.md`. Cloud setup is a separate task in `docs/tasks/CLOUD_ENVIRONMENT_SETUP.md`.
- Augneta is independent of Augnes. Its runtime, authority system, test suites, and release gates are not requirements here.
- The first software implementation and its verification are documented in `README.md`, `docs/METHODS.md`, and `docs/VERIFICATION.md`. Use the actual dependency metadata and executable checks; do not infer human or physical results from software tests or design documents.

## Workflow

- Use a task branch from current `main`, preserve unrelated changes, and open a Draft PR with auto-merge disabled. Merge only when the user requests it.
- Make routine, reversible implementation choices within the assigned task without repeatedly requesting confirmation.
- Keep changes and dependencies proportional to the experiment. A setup or documentation task must not silently become a full implementation.
- Update the relevant documentation when implemented behavior or verified status changes. Task-specific restrictions apply to that task; they are not permanent limits on the research program.
- Report actual commands, results, failures, and unverified claims. Never invent a passing test, an environment, a PR, or a completed experiment.

## Research integrity

- Keep hidden environment truth separate from the observations available to online estimators and user-facing displays. Only the evaluator and explicit oracle diagnostics may use it.
- Online estimators use permitted present/past observations, never future data.
- In the initial main conditions, the human's action is not replaced or modified by autonomous control.
- Sensory encoding communicates environmental state, not a target-specific optimal action. Keep target and optimal-action information out of the encoder.
- Information-matched conditions share the estimated state, uncertainty, quantization, update timing, and dropout indicators. Document unavoidable differences.
- Log estimator and encoder identities independently, together with seeds, time units, configuration, and change events needed for replay.
- Label technical tests, synthetic policies, offline biological recordings, physical delivery, and human observations separately. A scripted run has `participant_kind=synthetic` and `human_evidence=false`. Absent physical verification means `hardware_verified=false`.
- An output command or device acknowledgement alone does not establish skin-level stimulus timing, perception, learning, embodiment, or neural change.
- Preserve negative findings. Use participant-level inference for human studies; dense time samples do not create independent participants.

## Verification

- Choose checks for the changed behavior and concrete remaining risks. Documentation edits need link and consistency checks, not a full experiment suite.
- The implementation task defines the meaningful tests for the first experiment. Add runnable commands and dependency metadata with the implementation.
- Distinguish automated UI checks from human usability inspection and actual participant studies.
- Keep generated logs, local credentials, participant records, and large datasets out of commits unless an explicitly reviewed task calls for suitable publication. Use small synthetic fixtures for automated verification.
- Public data use must record the source, version, and applicable terms. Device operation, participant collection, paid services, and external transfer of private recordings require an appropriately scoped task.
