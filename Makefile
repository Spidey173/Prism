.PHONY: up down logs migrate revision lint typecheck test eval db-local migrate-local dev-api dev-web audit-sample

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

lint:
	docker compose exec api ruff check .

typecheck:
	docker compose exec api mypy app

test:
	set -a; . ./.env; set +a; cd api && pytest

db-local:
	brew services start postgresql@17
	PATH="$$(brew --prefix postgresql@17)/bin:$$PATH" createdb -p 5433 auditor 2>/dev/null || true
	PATH="$$(brew --prefix postgresql@17)/bin:$$PATH" psql -p 5433 auditor -c "CREATE EXTENSION IF NOT EXISTS vector;"

migrate-local:
	set -a; . ./.env; set +a; cd api && alembic upgrade head

dev-api:
	set -a; . ./.env; set +a; cd api && uvicorn app.main:app --reload

dev-web:
	cd web && npm run dev

eval:
	python eval/run_eval.py

audit-sample:
	set -a; . ./.env; set +a; cd api && python -m app.scripts.audit_sample $(ARGS)
