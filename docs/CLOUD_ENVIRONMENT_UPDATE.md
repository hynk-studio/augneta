# Reusable Cloud environment update after merge

The implementation was developed in the user's attached `augneta` Cloud runtime,
from current main `2cd9fb15d1322fbc75dda51f3bedc35288028727`, using a dedicated
implementation branch. The initial checkout was clean. Runtime instance:
`ccarenv_b64_Y2NhcmVudl8yMGExYjkzNTQwNGM4MTkxYjAxYWVjOWRkYWQwYzYzZA`.
Observed source configuration version:
`c49ce108-4832-489c-aa72-5a96608fe3af~cecfgver_6acf8a62c740819f9058d8551b7751d2`.

The current workspace's virtual environment has been installed and exercised.
**No reusable environment configuration was changed or republished by this PR.**
After merge, update the reusable configuration to the following commands against
the new main checkout and use the environment builder's normal publish flow.
These scripts intentionally do not fetch/reset branches or discard workspace edits.

## Install command

```bash
set -eu
cd /workspace/augneta
test -f pyproject.toml
test -f requirements-dev.lock
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pip check
```

This installs the actual locked Flask runtime, build backend, pytest, and
Playwright tool package. It has no GPU, API-key, npm, dataset, or device dependency.
Running it again is safe; it reuses `.venv` and reinstalls the editable project.
The exact locked installation was repeated during verification.

## Resume/start preparation command

Use this nonblocking command for the environment's start/resume hook; it checks
the saved runtime without creating duplicate servers:

```bash
set -eu
cd /workspace/augneta
test -x .venv/bin/python
.venv/bin/python -m pip check
.venv/bin/python -c 'import augneta, flask; print("augneta", augneta.__version__, "ready")'
```

If dependencies are not persisted between workspaces, run the install command in
that hook before these checks. A missing virtual environment must fail visibly.

## Start the demo and verify the updated environment

Launch the demo explicitly in a terminal:

```bash
cd /workspace/augneta
.venv/bin/python -m augneta serve --port 8000
```

Open the executor's loopback port 8000 through an available Cloud port preview or
forwarder, or use a browser on the same machine. No public deployment is created.
The server runs in the foreground; Ctrl+C stops it. To inspect its response:

```bash
curl --fail http://127.0.0.1:8000/api/health
```

Run acceptance checks separately, choosing fresh result directories on every run:

```bash
cd /workspace/augneta
.venv/bin/python -m pytest -q
.venv/bin/python -m augneta smoke --out runs/cloud-check --seed 7
.venv/bin/python -m augneta replay runs/cloud-check/dashboard
.venv/bin/python tools/browser_check.py --out artifacts/cloud-browser --chromium /usr/bin/chromium
```

The selected published runtime already had `/usr/bin/chromium` (154.0.8037.57).
If a future runtime lacks Chromium, install a Playwright-managed browser with
`.venv/bin/python -m playwright install chromium`, plus its documented OS
dependencies if required, and omit `--chromium`. This browser installation is
optional for core tests and synthetic smoke; an ordinary local browser can use
the demo. Do not label a skipped browser check as passed.

## Runtime and network observations

Python 3.12.14, Git 2.52.0, Node 24.19.0, npm 11.9.0, and GitHub CLI 2.46.0
were present. There is no frontend build, and the installed Playwright package
provides its own driver. The startup policy snapshot reported unrestricted HTTP,
VPN false; the status tool reported network policy state `unknown`, not confirmed
enforcement. Actual HTTPS requests to GitHub, its API, PyPI, and npm succeeded.
Package downloads and Git fetch were successful through inherited networking.

Installation needs PyPI (`pypi.org`, `files.pythonhosted.org`); repository work
needs GitHub/API access. Official source documentation was read on
`raw.githubusercontent.com`; rendered Flask/pytest/packaging sites returned 403.
Playwright documentation was accessible. Browser downloads, if needed, require
the hosts used by the official Playwright installer. No network is needed by the
running simulation beyond local browser/server traffic. No secrets were added.
