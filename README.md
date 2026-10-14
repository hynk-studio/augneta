# Augneta

Human–AI sensory augmentation and continuity of learned sensorimotor skills.

Augneta studies when information estimated by an external system can become a learnable, transferable sensory input for a human operator, and how learned skills can be preserved or improved when an estimator, sensor, or interface changes.

Augneta는 외부 계산이 제공하는 정보를 인간의 감각·행동 능력으로 학습하는 조건과, 인터페이스 변화 이후 그 능력이 이어지는 조건을 연구합니다.

## Current status

The first runnable software experiment is implemented: deterministic hidden-flow tracking, direct keyboard control, a causal estimator, matched feedback views, recording/replay, and CPU-only synthetic checks. [Verification results](docs/VERIFICATION.md) distinguish automated software checks from human and physical evidence.

PR-02 preparation adds a packet-to-actuator contract, bounded mock output, and reproducible code-identification plans with confusion scoring. [Output and calibration](docs/HAPTIC_OUTPUT_AND_CALIBRATION.md) explains what runs now and what still requires a selected physical device. This is the software portion of PR-02; physical delivery and perceptual calibration remain unverified.

No human learning, embodiment, sensory extension, physical feedback, neural, or consciousness result has been established. The sensory-code display is a development preview, not haptic delivery.

The initial documents were prepared on 2026-10-14 from a protocol drafted on 2026-10-07. This repository is independent of Augnes and does not require its runtime or validation suites.

## Research tracks

| Track | Question |
| --- | --- |
| P1 — Learnable sensory input | Which information, encoding, and training support use in unfamiliar tasks? |
| P2 — Continuity through interface changes | How do stable meanings, abrupt remapping, and gradual transitions affect relearning and later performance? |
| P3 — Biological inputs and adaptation | How can actual EMG or neural signals support reliable inputs and selective recalibration? |

P3 is a parallel research track, not a prerequisite for P1 or P2. Additional motor degrees of freedom, artificial proprioception, and richer representations remain possible extensions.

## First implementation

Steer a point toward a moving target while an unseen force affects its motion. A baseline random-walk Kalman filter receives sampled, noisy, delayed observations. Select no additional information, a matched visual dashboard, or a clearly labelled sensory-code preview. The main UI applies your action directly; it has no autopilot.

The first implementation includes deterministic logging and replay, normalized tracking error, focused automated tests, and a CPU-only synthetic-policy smoke run. It does not require a paid model API or physical haptic device.

The simulation and analysis use Python's standard library; Flask serves a local browser UI with plain JavaScript. No model API, GPU, npm build, external data, or device is required.

## Install and launch

Python 3.12+ is required; verified on Python 3.12.14. From the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pip check
.venv/bin/python -m augneta serve --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). On a remote Cloud executor, use its localhost port preview/forwarding if available; `127.0.0.1` refers to the executor. The development server binds to loopback, with debug mode off. Stop it with Ctrl+C.

For a known preview that terminates HTTPS and forwards HTTP to the app, explicitly configure its external browser origin:

```bash
.venv/bin/python -m augneta serve --port 8000 --public-origin https://preview.example
```

Replace the example with the preview's actual origin (`scheme://host[:port]`, without a path, credentials, query, or fragment). This permits that one origin in addition to direct access; unrelated origins and cross-site browser requests remain rejected. `Forwarded` and `X-Forwarded-*` headers are never trusted. Host case and default ports are normalized to browser origin serialization; non-default ports must match exactly. Omit the option for ordinary localhost use. The option neither creates a preview route nor changes the loopback binding. See [Cloud route verification](docs/VERIFICATION.md#previewproxy-follow-up) for what was actually available and tested.

Choose a condition and seed, then **Start trial**. Use arrow keys, WASD, or the on-screen buttons. Space or **Pause** freezes simulation time. Leaving the tab pauses and clears held keys. A default trial lasts 30 simulated seconds; slow requests can extend wall time. **Stop trial** preserves an incomplete recording without awarding a score. No participant identifiers are requested.

## Verify and replay

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m augneta smoke --out runs/smoke --seed 7
.venv/bin/python -m augneta replay runs/smoke/dashboard
```

Smoke executes all three main conditions using an explicitly synthetic PD policy and checks every replay. Results are in `runs/smoke/results.json`; each condition has metadata, trace, a separate evaluator-only truth file, and a metric summary. Output directories must be new: use another name to rerun. UI recordings are under `runs/ui/`; all generated runs are ignored by Git.

An explicit diagnostic is available separately:

```bash
.venv/bin/python -m augneta oracle-smoke --out runs/oracle --seed 7
```

It uses hidden truth, is labelled `oracle_diagnostic`, and is excluded from the main smoke results and UI. It is not a fair estimated-state comparator.

For automated browser interaction in the published Cloud runtime:

```bash
.venv/bin/python tools/browser_check.py --out artifacts/browser --chromium /usr/bin/chromium
```

If system Chromium is unavailable, install a Playwright browser with `.venv/bin/python -m playwright install chromium` (OS libraries may also be needed), then omit `--chromium`. Browser tooling is a development dependency; the demo itself only needs an ordinary browser. Automated keyboard checks and screenshots are not human usability validation.

Noise, delay, dropout, duration, and the evaluation window can be configured with a JSON object of [Config fields](src/augneta/config.py), supplied to `smoke --config file.json` or `serve --config file.json`. `--seed` overrides a smoke config seed; the UI uses its seed input. Invalid configurations and requests for `--output hardware` fail explicitly.

## Start here

| Document | Purpose |
| --- | --- |
| [Research protocol](docs/PROJECT_SELECTION_AND_PROTOCOL.md) | Research questions, comparators, evidence boundaries, evaluation, and later experiments; written in Korean |
| [First implementation task](docs/tasks/FIRST_IMPLEMENTATION.md) | End-to-end scope and acceptance criteria for the first implementation PR |
| [PR-02 task](docs/tasks/HAPTIC_OUTPUT_AND_CALIBRATION.md) | Physical-output roadmap and the current preparation slice |
| [Output and calibration](docs/HAPTIC_OUTPUT_AND_CALIBRATION.md) | Executable mock, timing contract, identification plans, and physical acceptance procedure |
| [Device options](docs/HAPTIC_DEVICE_OPTIONS.md) | Official-source device and browser connection comparison |
| [Cloud environment setup](docs/tasks/CLOUD_ENVIRONMENT_SETUP.md) | Instructions for preparing a dedicated Codex Cloud environment |
| [Methods](docs/METHODS.md) | Equations, timing, information boundaries, encoding, metric, and replay contract |
| [Verification](docs/VERIFICATION.md) | Commands actually run, outcomes, failures, and limits |
| [PR-02 preparation verification](docs/VERIFICATION_PR02.md) | Actual checks for the output contract and calibration tools |
| [Cloud environment update](docs/CLOUD_ENVIRONMENT_UPDATE.md) | Exact reusable install/start commands for after merge |
| [Agent instructions](AGENTS.md) | Repository workflow and research integrity requirements |

Dependency metadata is in `pyproject.toml`; `requirements-dev.lock` pins the tested runtime, build, and development dependencies. Replay requires matching implementation content and Python version. It verifies actions, observations, component changes, feedback, evaluator truth, and summaries; it does not reproduce screen presentation timing.

## Development and evidence

Changes after this initial documentation setup are proposed through branches and Draft PRs for review. A change should report what was implemented, what was actually run, failures, and remaining limitations.

Technical verification, synthetic-policy performance, offline biological data, physical output measurements, and human learning evidence are reported separately. A UI preview is not verified haptic delivery, and offline or simulated results are not evidence of human sensory learning.
