# PR-02 preparation: actual verification

Date: 2026-10-14. This record covers the software preparation portion of
[PR-02](tasks/HAPTIC_OUTPUT_AND_CALIBRATION.md), not completed physical output or
perceptual calibration. All executed trials used synthetic data.

This is the historical eight-slot preparation record at `2dc691a`. Later six-slot
and calibration-UI checks are in [pre-arrival verification](VERIFICATION_PREARRIVAL.md).
Statements below about absent UI describe that earlier revision.

## Checkout and installation

- Fresh checkout of `hynk-studio/augneta`, current `main` at
  `67d7ce6953cb5c56ff14466b8490e2e261cd26be`.
- Task branch: `feat/haptic-output-preparation`. No pre-existing user changes.
- Working directory: `/workspace/scratch/3b700d20a46e/augneta-pr02`.
- Python 3.12.14, Git 2.51.1. Flask 3.1.3 and pytest 9.1.1 from the existing lock.
- `python -m venv .venv`: passed.
- `.venv/bin/python -m pip install -r requirements-dev.lock`: passed.
- `.venv/bin/python -m pip install --no-build-isolation --no-deps -e .`: passed.
- `.venv/bin/python -m pip check`: no broken requirements.
- Dependency declarations and lockfile unchanged. No vendor SDK was installed.

## Executed checks

| Command | Actual result |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_haptics.py tests/test_calibration.py` | Initial focused check: 50 passed in 0.14 s |
| `.venv/bin/python -m pytest -q` | After review added clock-rollback coverage: **157 passed in 1.09 s** (106 existing, 51 new) |
| `.venv/bin/python -m augneta haptic-smoke --out runs/verified-haptic --seed 7` | 600 steps; 150 mock commands; 150 exact shared-packet checks; final output stopped; original tracking replay verified |
| `.venv/bin/python -m augneta replay runs/verified-haptic/tracking` | 600-step original tracking replay verified |
| `.venv/bin/python -m augneta calibration-plan --out runs/verified-calibration --seed 7 --blocks 2` | 72 unadministered items: 64 nonzero codes and 8 zero catches; **0 responses collected** |

Final documentation checks resolved 22 local file links and confirmed the source
hash still matched the successful run. `git diff --cached --check` passed.

Coverage includes nonidentity actuator mapping, rotated encoders, invalid level
tables and nonfinite values, rejection of extra truth/target/action fields and
oracle packets, held-packet pulse extension, stale and future emissions, independent
sensor sample age, disconnection and explicit re-arming, obsolete session epochs,
invalid/rollback clocks, output expiry and mirror clearing, missing physical ACKs,
end-to-end use of real online packets, recording replay, and output overwrite
protection. `haptic-smoke --output hardware` is tested to fail before creating an
output directory; no hardware route is enabled.

Calibration tests check seeded ordering and per-block balance, zero catches,
hand-specified direction/level confusions, explicit unknown responses, missing
trials, false positives, empty response sets, duplicate/unknown IDs, changed plans
and profiles, and input types. Accuracy is descriptive; no learned skill or
perceptual pass threshold is inferred.

## Result provenance

The successful run records the base commit and `working_tree_dirty=true`, because
the implementation was tested before committing. Its exact implementation hash is
`454203e9c64f9657841fe59e8d95aedc2a56eae89e7b86fac292c5bdc33a4068`.
The mock profile hash is
`ec16ac6cc4aaea2bac46a9c8d797290ddacbca4903950c1ba5a31a7a2db2f852`;
the generated calibration plan hash is
`2648d48e1bfa5f41fc085dd2643e85587ac6254c3b3683c5cc315c3b59f8ca4e`.

Generated `runs/` files are ignored by Git and not published in this PR. Re-run
the documented commands with a new output directory to reproduce the checks.
Existing PR-01 recordings require their original source hash and Python version;
this PR does not weaken replay identity checks.

The synthetic policy still consumes the original held visual packet. Its tracking
RMSE is **not haptic-condition performance**. The `tracking/` replay verifies the
original experiment trace; it does not replay or physically validate the separate
`output_events.jsonl` stream. Both `human_evidence` and `hardware_verified` remain
false, with zero physical timing measurements.

## Failures and remaining work

No implementation test or installation command failed in this preparation run.
Malformed input, stale commands, unsupported hardware output, and existing output
directories were rejected in the intended negative tests.

The direct CLI `git push` attempt failed because this runtime has no HTTPS Git
credentials (`could not read Username`). This is a publication/authentication
limitation, not an implementation test failure.

- No device was connected, commanded, purchased, or measured.
- No participant-facing calibration UI or physical driver is implemented.
- No human responses, comfort levels, discrimination, learning, or transfer were measured.
- The mock uses explicit synthetic ticks; it is not a device watchdog, real-time
  latency measurement, or proof of host/browser-failure behavior.
- The existing dashboard has not been changed to the mock's pulse gate. Physical
  versus visual presentation timing and information matching remain to be integrated.
- No browser, BLE, Player, HTTPS-to-local connection, Sites redeployment, or Cloud
  environment republishing was performed for this PR. Existing web code is unchanged.
- The [device comparison](HAPTIC_DEVICE_OPTIONS.md) uses official sources consulted
  on the date above. The English JavaScript guide could not be retrieved by the
  search tool; its official Korean version and the official SDK repository were read.

Remaining physical acceptance steps and response-data handling are specified in
[output and calibration](HAPTIC_OUTPUT_AND_CALIBRATION.md). Completing this software
slice does not close the full PR-02 milestone.
