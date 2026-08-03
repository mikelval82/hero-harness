#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/.venv/Scripts/python.exe"
else
  PY="python3"
fi
"$PY" -m unittest discover -s "$ROOT/tests"
