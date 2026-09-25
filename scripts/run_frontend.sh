#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
pip install -q -r frontend/requirements-frontend.txt
exec streamlit run frontend/app.py --server.port "${STREAMLIT_PORT:-8501}" --server.address 127.0.0.1
