#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=services/backend
exec .venv/bin/python -m app.services.evaluation.benchmark.isolation -- .venv/bin/python -m app.services.evaluation.benchmark.runner "$@"
