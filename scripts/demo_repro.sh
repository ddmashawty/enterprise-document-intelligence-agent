#!/usr/bin/env bash
# Reproducible local demo: ingest controllable docs → unit tests → smokes → optional API.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt -r requirements-dev.txt
pip install -q -r requirements-embedding.txt || true

export PYTHONPATH=src
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from example — fill LLM_API_KEY before chat smokes."
fi

python scripts/ingest_demo.py
python -m pytest -q
python scripts/perf_baseline.py || true

if grep -qE '^LLM_API_KEY=.+' .env && ! grep -q 'your-deepseek' .env; then
  python scripts/smoke_chat.py
  python scripts/smoke_phase4.py
else
  echo "Skip LLM smokes (LLM_API_KEY not set)."
fi

echo
echo "Start API:"
echo "  PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000"
echo "Docs: http://127.0.0.1:8000/docs"
