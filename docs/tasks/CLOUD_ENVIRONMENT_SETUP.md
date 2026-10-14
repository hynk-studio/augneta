# Codex Cloud environment setup

Status: setup instructions; this document does not establish that a Cloud environment has been created or published.

Select `hynk-studio/augneta` when creating the environment. Use the following prompt in its setup conversation. Read the current repository first: dependency metadata may have been added after this document.

```text
Prepare a dedicated Codex Cloud development environment named augneta for https://github.com/hynk-studio/augneta, using the current main branch.

This task prepares and validates the environment. The first implementation task will be started separately after the environment is ready.

Project context
Augneta is an independent research project on human–AI sensory augmentation and continuity of learned sensorimotor skills. Its first implementation will be a CPU-only hidden-flow tracking simulation with a lightweight browser UI, causal state estimation, information-matched feedback conditions, logging/replay, normalized tracking error, and synthetic-policy tests.

Read first
- AGENTS.md
- README.md
- docs/PROJECT_SELECTION_AND_PROTOCOL.md
- docs/tasks/FIRST_IMPLEMENTATION.md
- docs/tasks/CLOUD_ENVIRONMENT_SETUP.md

Repository and environment
1. Confirm the remote is hynk-studio/augneta, inspect current main, and record its commit SHA. Work in a dedicated Augneta checkout.
2. Configure the environment for Augneta alone. Choose tools from its actual requirements rather than copying Augnes-specific dependencies or validation gates.
3. Use the files present in the repository as the authority for installation and checks. At initial setup the repository may contain only documentation. Report that state explicitly.
4. Ensure Git and a supported Python 3 runtime are usable. Prepare Node.js only if the chosen frontend or browser test tooling requires it. Do not require a GPU, paid model API, external model service, haptic device, or biological dataset for this environment.
5. Configure network access for the package registries and official documentation actually needed by the selected tools. Request repository access only if the current connection lacks it. Do not place credentials in repository files or logs.

Installation and repeatability
6. If dependency manifests and lockfiles exist, use their package manager and locked installation workflow. Check tool documentation as needed.
7. If manifests are absent, do not guess application dependencies or fabricate package files solely to make setup look complete. Prepare the base runtime and report application dependency installation as pending the first implementation.
8. Make the environment's install and resume/start configuration idempotent: use actual project metadata, fail clearly on real installation errors, and distinguish a documentation-only repository from an installation failure.
9. Validate the configured preparation twice if the environment builder supports it, or otherwise report which repeatability check was possible. Record versions and actual outcomes.

Validation and handoff
10. Verify repository identity, access to the design/task documents, runtime availability, and that no unrelated files were modified.
11. Run only test and smoke commands that actually exist. When code and tests are absent, report "not present yet"; do not label the environment as having passed the experiment's acceptance tests.
12. If reusable repository setup changes are necessary, make them on a branch and open a Draft PR against main, with auto-merge disabled. Do not invent a workflow or framework just to create a PR.
13. Return the environment name/ID or URL when available, repository and verified main SHA, installed runtime versions, install/start configuration, checks actually run, and any remaining access or setup blocker.
14. Leave the environment ready to start the first implementation task. If the interface requires a final Publish action by the user, identify that exact remaining step. Do not claim the environment is published unless the interface confirms it.

The next coding task will be: implement docs/tasks/FIRST_IMPLEMENTATION.md, deliver the runnable experiment with its actual verification results, and open a Draft PR for review.
```
