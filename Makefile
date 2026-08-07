# Developer and operator shortcuts. Learners use the browser, never these.

UV := uv
PY := $(UV) run --frozen python
NPM := npm --prefix frontend

.DEFAULT_GOAL := help
.PHONY: help setup dev build serve contracts check test test-backend test-frontend e2e lint fmt notebooks clean reset docker

help:  ## Show this help
	@echo ""
	@echo "  Nornyx Academy — developer commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Learner deployment:  docker compose up --build"
	@echo ""

setup:  ## Sync exact Python and browser dependencies
	$(UV) sync --frozen --extra dev --extra crewai --extra langgraph --extra live
	$(NPM) ci --ignore-scripts
	$(PY) scripts/build_contracts.py --verify

dev:  ## Start the FastAPI service (run `npm --prefix frontend run dev` separately)
	$(UV) run --frozen uvicorn nornyx_lab.academy.app:app --reload --host 127.0.0.1 --port 8000

build:  ## Build the production browser application
	$(NPM) run build

serve: build  ## Serve the production-style academy at http://127.0.0.1:8000
	$(UV) run --frozen nornyx-academy --host 127.0.0.1 --port 8000

contracts:  ## Rebuild every contract: seal, check, generate, lock
	$(PY) scripts/build_contracts.py

check:  ## Verify the committed contract artifacts have not drifted
	$(PY) scripts/build_contracts.py --verify

test:  ## Run every lab's concept checks (-rs shows any skip and why)
	$(PY) -m pytest labs tests -q -rs

test-backend:  ## Run academy service/domain tests only
	$(PY) -m pytest tests/academy -q

test-frontend:  ## Run browser component tests
	$(NPM) test

e2e: build  ## Run the fresh-learner browser and accessibility journey
	$(NPM) run test:e2e

lint:  ## Lint and format-check
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(NPM) run build

fmt:  ## Auto-format
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

notebooks:  ## Regenerate the notebook companion for every lab
	$(PY) scripts/build_notebooks.py

clean:  ## Remove generated scratch output (keeps committed artifacts)
	$(PY) scripts/clean.py

reset:  ## Clear your lab progress
	$(PY) -c "from nornyx_lab.academy.progress import SQLiteLearnerRecordRepository; SQLiteLearnerRecordRepository('.nornyx-lab/academy.db').reset()"

docker:  ## Build the production container image
	docker build --pull --tag nornyx-academy:2.0.0 .
