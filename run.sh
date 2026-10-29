#!/usr/bin/env bash
# Launcher: makes a local .venv on first use, keeps requirements installed,
# then runs the given Python arguments inside it.
#   ./run.sh -m scripts.check_skip
#   ./run.sh -m scripts.output_pr --session-data-file session-output.json --finalize
set -euo pipefail
cd "$(dirname "$0")"

PY=$(command -v python3 || command -v python)
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
exec .venv/bin/python "$@"
