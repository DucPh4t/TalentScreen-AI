.PHONY: help doctor bootstrap db-up db-down db-status dev-backend dev-web test-backend test lint clean

PYTHON = .venv/bin/python
PYTEST = .venv/bin/pytest
UVICORN = .venv/bin/uvicorn

help:
	@echo "TalentScreen AI — Development Commands:"
	@echo "  make doctor         Run environment diagnostic checks"
	@echo "  make bootstrap      Install backend (.venv) and frontend (npm) dependencies"
	@echo "  make db-up          Start local PostgreSQL + pgvector Docker container"
	@echo "  make db-down        Stop local Docker database container"
	@echo "  make db-status      Check status of database container"
	@echo "  make dev-backend    Start FastAPI backend development server (127.0.0.1:8000)"
	@echo "  make dev-web        Start Next.js frontend development server (localhost:2004)"
	@echo "  make test-backend   Run pytest test suite for backend"
	@echo "  make test           Run all automated tests"

doctor:
	@$(PYTHON) scripts/doctor.py

bootstrap:
	@echo "Setting up Python virtual environment with uv..."
	uv venv --python 3.12 .venv
	uv pip install -e "services/backend[dev]"
	@echo "Installing frontend dependencies..."
	cd apps/web && npm install
	@echo "Bootstrap completed."

db-up:
	docker compose up -d postgres
	@echo "Waiting for postgres to become healthy..."
	@docker compose ps

db-down:
	docker compose down

db-status:
	docker compose ps

dev-backend:
	cd services/backend && ../../$(UVICORN) app.main:app --host 127.0.0.1 --port 8000 --reload

dev-web:
	cd apps/web && npm run dev

test-backend:
	bash scripts/test_backend_isolated.sh

test: test-backend
	cd apps/web && npm run build
