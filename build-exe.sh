#!/usr/bin/env bash
# Build a single-file executable for the PDF editor with PyInstaller.
# Usage: ./build-exe.sh   (output: dist/pdf-editor)
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=.venv/bin/python

if [ ! -x "$PYTHON" ]; then
  echo "Virtualenv not found. Run: python3 -m venv .venv && $PYTHON -m pip install -r requirements.txt" >&2
  exit 1
fi

if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller missing. Run: $PYTHON -m pip install -r requirements-dev.txt" >&2
  exit 1
fi

"$PYTHON" -m PyInstaller --noconfirm --clean \
  --onefile --windowed \
  --name pdf-editor \
  --collect-data app \
  run.py

echo
echo "Build complete: dist/pdf-editor"