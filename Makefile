.PHONY: dev dev-backend dev-frontend test test-unit test-integration \
        migrate lint typecheck clean logs

# Start full local stack
dev:
	docker compose -f infra/docker-compose.yml up

# Start only backend services (DB, Redis, Ollama) + FastAPI with hot-reload
dev-backend:
	docker compose -f infra/docker-compose.yml up -d db redis ollama
	cd backend && source .venv/bin/activate && \
	  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start only Next.js dev server
dev-frontend:
	cd frontend && npm run dev

# Run all tests
test:
	make test-unit && make test-integration

# Unit tests only (no Docker required)
test-unit:
	cd backend && source .venv/bin/activate && \
	  pytest tests/unit -m unit -v

# Integration tests (requires running DB + Redis)
test-integration:
	docker compose -f infra/docker-compose.test.yml up -d
	cd backend && source .venv/bin/activate && \
	  TEST_DATABASE_URL=postgresql://stocklens:test@localhost:5433/stocklens_test \
	  pytest tests/integration -m integration -v
	docker compose -f infra/docker-compose.test.yml down

# Database migration
migrate:
	cd backend && source .venv/bin/activate && alembic upgrade head

# Linting
lint:
	cd backend && source .venv/bin/activate && ruff check app tests
	cd frontend && npx eslint .

# Type checking
typecheck:
	cd backend && source .venv/bin/activate && mypy app --strict
	cd frontend && npx tsc --noEmit

# Tail logs for all services
logs:
	docker compose -f infra/docker-compose.yml logs -f api frontend

# Remove all containers, volumes, and build artifacts
clean:
	docker compose -f infra/docker-compose.yml down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	cd frontend && rm -rf .next node_modules
