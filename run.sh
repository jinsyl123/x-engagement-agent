#!/bin/bash
set -e

# This script is the robust, cross-platform launcher for all Python-based workflow steps.
# It handles environment setup and intelligently finds the correct Python command.

# --- Environment and Command Detection ---

# Intelligently select python3 or python, making this script cross-platform.
PYTHON_CMD=python3
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD=python
fi

# Create a virtual environment if it doesn't exist.
if [ ! -d ".venv" ]; then
    echo "--- Virtual environment not found. Creating one... ---"
    $PYTHON_CMD -m venv .venv
fi

# Activate the virtual environment for this script's session.
source .venv/bin/activate

# Install/update dependencies quietly on each run to ensure consistency.
echo "--- Ensuring dependencies are up to date... ---"
$PYTHON_CMD -m pip install --quiet -r requirements.txt

# --- Execute the requested command ---
echo "--- Executing: $PYTHON_CMD $@ ---"
exec $PYTHON_CMD "$@"
