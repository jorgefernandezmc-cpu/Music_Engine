#!/bin/bash
cd "$(dirname "$0")/.."
if [ -f ".venv/bin/python3" ]; then
    PYTHON_BIN=".venv/bin/python3"
else
    PYTHON_BIN="python3"
fi
echo "Running engine with $PYTHON_BIN..."
$PYTHON_BIN main.py run
read -p 'Press Enter to exit...'
