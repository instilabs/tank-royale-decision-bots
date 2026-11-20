#!/bin/sh
cd "$(dirname "$0")"
# Prefer a project .venv (repo root or this bot dir); fall back to system python3.
if [ -x "../.venv/bin/python3" ]; then
  PY="../.venv/bin/python3"
elif [ -x ".venv/bin/python3" ]; then
  PY=".venv/bin/python3"
else
  PY="python3"
fi
exec "$PY" OllayaWinnow.py
