# Augneta

Human–AI sensory augmentation and continuity of learned sensorimotor skills.

Augneta studies when information estimated by an external system can become a learnable, transferable sensory input for a human operator, and how learned skills can be preserved or improved when an estimator, sensor, or interface changes.

Augneta는 외부 계산이 제공하는 정보를 인간의 감각·행동 능력으로 학습하는 조건과, 인터페이스 변화 이후 그 능력이 이어지는 조건을 연구합니다.

## Current status

Research design and implementation instructions only. The first runnable experiment is planned; no software experiment, physical feedback, human learning, or neural result has been established in this repository.

The initial documents were prepared on 2026-10-14 from a protocol drafted on 2026-10-07. This repository is independent of Augnes and does not require its runtime or validation suites.

## Research tracks

| Track | Question |
| --- | --- |
| P1 — Learnable sensory input | Which information, encoding, and training support use in unfamiliar tasks? |
| P2 — Continuity through interface changes | How do stable meanings, abrupt remapping, and gradual transitions affect relearning and later performance? |
| P3 — Biological inputs and adaptation | How can actual EMG or neural signals support reliable inputs and selective recalibration? |

P3 is a parallel research track, not a prerequisite for P1 or P2. Additional motor degrees of freedom, artificial proprioception, and richer representations remain possible extensions.

## First implementation

Build one runnable hidden-flow tracking task: a human directly controls a point while a hidden force affects its motion. A causal estimator receives limited sensor observations. Compare no additional information with an information-matched visual display, and provide a clearly labelled development preview of a future sensory encoding.

The first implementation includes deterministic logging and replay, normalized tracking error, focused automated tests, and a CPU-only synthetic-policy smoke run. It does not require a paid model API or physical haptic device.

Environment preparation and document registration are setup work. The implementation deliverable is the running task and its verified behavior.

## Start here

| Document | Purpose |
| --- | --- |
| [Research protocol](docs/PROJECT_SELECTION_AND_PROTOCOL.md) | Research questions, comparators, evidence boundaries, evaluation, and later experiments; written in Korean |
| [First implementation task](docs/tasks/FIRST_IMPLEMENTATION.md) | End-to-end scope and acceptance criteria for the first implementation PR |
| [Cloud environment setup](docs/tasks/CLOUD_ENVIRONMENT_SETUP.md) | Instructions for preparing a dedicated Codex Cloud environment |
| [Agent instructions](AGENTS.md) | Repository workflow and research integrity requirements |

There is no application launch or test command yet. The first implementation PR must add dependency metadata, exact installation and launch instructions, the headless smoke command, and the actual test commands.

## Development and evidence

Changes after this initial documentation setup are proposed through branches and Draft PRs for review. A change should report what was implemented, what was actually run, failures, and remaining limitations.

Technical verification, synthetic-policy performance, offline biological data, physical output measurements, and human learning evidence are reported separately. A UI preview is not verified haptic delivery, and offline or simulated results are not evidence of human sensory learning.
