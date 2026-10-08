#!/usr/bin/env bash
set -euo pipefail

# Use a throwaway database. Never run pytest against the application's .env DB.
container_name="talentscreen-test-$$"
cleanup() {
  docker stop "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --rm --name "$container_name" \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=talentscreen_test \
  -p 127.0.0.1::5432 \
  -d pgvector/pgvector:pg16 >/dev/null

for attempt in {1..30}; do
  if docker exec "$container_name" pg_isready -U postgres -d talentscreen_test >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == 30 ]]; then
    echo "Isolated test database did not become ready" >&2
    exit 1
  fi
  sleep 1
done

test_port="$(docker port "$container_name" 5432/tcp | awk -F: 'NR==1 {print $NF}')"
if [[ ! "$test_port" =~ ^[0-9]+$ ]]; then
  echo "Could not determine isolated test database port" >&2
  exit 1
fi

docker exec "$container_name" psql -U postgres -d talentscreen_test -c 'CREATE EXTENSION IF NOT EXISTS vector' >/dev/null
docker exec "$container_name" psql -U postgres -d talentscreen_test -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' >/dev/null

export TALENTSCREEN_TEST_DB_ISOLATED=1
export APP_ENV=sandbox
export PILOT_STAGE=
export LLM_PROVIDER=mock
export DEEPSEEK_API_KEY=
# Keep a locally configured secondary provider or hybrid mode out of generic regression runs.
export JEV_MODE=off
export JEV_API_KEY=
export RAG_MODE=full_text_baseline
# Generic tests must never inherit cloud telemetry credentials.
export LANGSMITH_TRACING=false
export LANGCHAIN_TRACING_V2=false
export LANGSMITH_API_KEY=
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:${test_port}/talentscreen_test"
export DATABASE_SYNC_URL="postgresql://postgres:postgres@127.0.0.1:${test_port}/talentscreen_test"
export PYTHONPATH=services/backend

.venv/bin/alembic upgrade head
.venv/bin/python -m pytest "${@:-services/backend/tests}" -q
