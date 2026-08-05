# nornyx-lab — one command per thing you might want to do.
#
# `make setup` is the only one you need to start.

UV := uv
PY := .venv/bin/python
ifeq ($(OS),Windows_NT)
	PY := .venv/Scripts/python.exe
endif

.DEFAULT_GOAL := help
.PHONY: help setup setup-min contracts check test lint fmt notebooks clean reset

help:  ## Show this help
	@echo ""
	@echo "  nornyx-lab"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  New here?  make setup  &&  nornyx-lab"
	@echo ""

setup:  ## Install everything (including CrewAI + LangGraph) and build contracts
	$(UV) venv
	$(UV) pip install -e ".[dev,crewai,langgraph,notebooks]"
	$(PY) scripts/build_contracts.py
	$(PY) -m nornyx_lab.cli doctor

setup-min:  ## Install without the framework extras (labs 18-20 will skip)
	$(UV) venv
	$(UV) pip install -e ".[dev]"
	$(PY) scripts/build_contracts.py
	$(PY) -m nornyx_lab.cli doctor

contracts:  ## Rebuild every contract: seal, check, generate, lock
	$(PY) scripts/build_contracts.py

check:  ## Verify the committed contract artifacts have not drifted
	$(PY) scripts/build_contracts.py --verify

test:  ## Run every lab's concept checks (-rs shows any skip and why)
	$(PY) -m pytest labs tests -q -rs

lint:  ## Lint and format-check
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

fmt:  ## Auto-format
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

notebooks:  ## Regenerate the notebook companion for every lab
	$(PY) scripts/build_notebooks.py

clean:  ## Remove generated scratch output (keeps committed artifacts)
	$(PY) scripts/clean.py

reset:  ## Clear your lab progress
	$(PY) -m nornyx_lab.cli reset --yes
