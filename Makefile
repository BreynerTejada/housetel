# Housetel — common commands (everything runs through Docker Compose).
# Usage: make <target>   ·   extra pytest args: make test-back ARGS="apps/core -k tenancy"

COMPOSE ?= docker compose
BACKEND_SERVICES := db redis mailpit backend worker beat
TEST_DB_ENV := $(if $(TEST_DB_NAME),-e TEST_DB_NAME=$(TEST_DB_NAME),)

.PHONY: help up up-back down logs ps migrate makemigrations seed reset test test-back test-front \
	lint lint-back lint-front format shell check check-data smoke

help: ## List the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

up: ## Build and start every service (app at http://localhost:5173)
	$(COMPOSE) up -d --build

up-back: ## Build and start only the backend services (db, redis, mailpit, backend, worker, beat)
	$(COMPOSE) up -d --build $(BACKEND_SERVICES)

down: ## Stop every service
	$(COMPOSE) down

logs: ## Follow the logs of every service
	$(COMPOSE) logs -f --tail=200

ps: ## Show the services
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(COMPOSE) run --rm backend python manage.py migrate --noinput

makemigrations: ## Create migrations (optionally for one app: make makemigrations APP=inventory)
	$(COMPOSE) run --rm backend python manage.py makemigrations $(APP)

seed: ## Load the demo data (idempotent)
	$(COMPOSE) run --rm backend python manage.py seed_demo

reset: ## Wipe the database volume and recreate everything with fresh demo data
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build db redis mailpit
	$(COMPOSE) run --rm backend python manage.py migrate --noinput
	$(COMPOSE) run --rm backend python manage.py seed_demo --reset
	$(COMPOSE) up -d --build

test: test-back test-front ## Run every test suite

test-back: ## Backend tests (optional: TEST_DB_NAME=test_x ARGS="apps/core")
	$(COMPOSE) run --rm $(TEST_DB_ENV) backend pytest -q $(ARGS)

test-front: ## Frontend tests
	$(COMPOSE) run --rm frontend npm run test

lint: lint-back lint-front ## Lint backend and frontend

lint-back: ## ruff check (backend)
	$(COMPOSE) run --rm backend ruff check .

lint-front: ## eslint (frontend)
	$(COMPOSE) run --rm frontend npm run lint

format: ## ruff format (backend)
	$(COMPOSE) run --rm backend ruff format .

check: ## Django system checks + pending migrations + OpenAPI schema without warnings
	$(COMPOSE) run --rm backend sh -c "python manage.py check && python manage.py makemigrations --check --dry-run \
		&& python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yaml && echo 'OpenAPI schema OK'"

check-data: ## Read-only invariants of inventory and money (run it after `make seed`)
	$(COMPOSE) run --rm backend python manage.py check_integrity

smoke: ## End-to-end API smoke through the Vite proxy (needs `make up` + seed; leaves one test reservation)
	python3 backend/scripts/smoke_proxy.py http://localhost:5173

shell: ## Django shell
	$(COMPOSE) run --rm backend python manage.py shell
