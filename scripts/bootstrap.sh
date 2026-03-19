#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv || true
source .venv/bin/activate
python -m pip install -U pip
if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
fi
