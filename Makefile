# Convenience targets. Everything here also works as a plain command; nothing
# in the project requires make.

.DEFAULT_GOAL := help
VENV ?= .venv
PY   ?= $(VENV)/bin/python

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: up
up: ## Start the full stack (Postgres + API + web) with Docker Compose
	docker compose up --build

.PHONY: down
down: ## Stop the stack
	docker compose down

.PHONY: clean
clean: ## Stop the stack and delete the database volume
	docker compose down -v

.PHONY: venv
venv: ## Create the backend virtualenv and install dev dependencies
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r backend/requirements-dev.txt

.PHONY: api
api: ## Run the API locally with reload (needs a reachable Postgres, or set DATABASE_URL)
	cd backend && PYTHONPATH=. ../$(VENV)/bin/uvicorn app.main:app --reload --port 8000

.PHONY: web
web: ## Run the Next.js dev server
	cd frontend && npm run dev

.PHONY: test
test: ## Run the backend test suite
	cd backend && PYTHONPATH=. ../$(VENV)/bin/python -m pytest -q

.PHONY: coverage
coverage: ## Run tests with a coverage report
	cd backend && PYTHONPATH=. ../$(VENV)/bin/python -m pytest --cov=app --cov-report=term-missing

.PHONY: lint
lint: ## Lint and type-check both halves of the project
	$(VENV)/bin/ruff check backend/app backend/tests
	$(VENV)/bin/ruff format --check backend/app backend/tests
	cd frontend && npm run typecheck && npm run lint

.PHONY: format
format: ## Auto-format the Python code
	$(VENV)/bin/ruff check --fix backend/app backend/tests
	$(VENV)/bin/ruff format backend/app backend/tests

.PHONY: seed
seed: ## Reset and reload the demo dataset (destructive)
	cd backend && PYTHONPATH=. ../$(VENV)/bin/python -m app.db.seed

.PHONY: demo
demo: ## Score the acceptance-test example and print the result
	cd backend && PYTHONPATH=. ../$(VENV)/bin/python -m app.cli demo
