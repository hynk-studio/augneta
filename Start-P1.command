#!/bin/sh
# Open the two-visit P1 self-check on this computer.
set -eu
umask 077
cd "$(dirname "$0")"
project_dir=$(pwd -P)
runtime="$project_dir/.venv/bin/python"
if [ ! -x "$runtime" ]; then
    for candidate in python3.12 python3 python3.13 python3.14; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
            "$candidate" -m venv .venv
            break
        fi
    done
fi
if [ ! -x "$runtime" ] || ! "$runtime" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
    echo "Python 3.12 이상이 필요합니다. 설치한 후 이 파일을 다시 실행하세요." >&2
    exit 1
fi

# Install only runtime dependencies, using the checkout's pinned versions.
"$runtime" - <<'PY'
import subprocess
import sys
import tomllib

with open("pyproject.toml", "rb") as manifest:
    requirements = tomllib.load(manifest)["project"]["dependencies"]
subprocess.run([sys.executable, "-m", "pip", "--disable-pip-version-check", "install", "-q",
                "-c", "requirements-dev.lock", *requirements], check=True)
PY

case "$(uname -s)" in
    Darwin) data_dir="$HOME/Library/Application Support/Augneta" ;;
    *) data_dir="${XDG_STATE_HOME:-$HOME/.local/state}/augneta" ;;
esac
export PYTHONPATH="$project_dir/src"
exec "$runtime" research/p1-gates/pilot/app.py serve --self-check --open --db "$data_dir/p1-self-v1.sqlite3" "$@"
