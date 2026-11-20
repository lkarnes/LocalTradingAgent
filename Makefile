.PHONY: setup install-ollama model model-check configure doctor dashboard run-once scheduler status stop paper-start paper-status paper-report paper-reset backtest analytics report-daily report-weekly report-monthly export-trades backup restore storage-status storage-prune test test-integration install-service live-readiness robinhood-auth risk-profile

PYTHON ?= python3.12
VENV ?=.venv

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -e .
	$(VENV)/bin/trading-agent setup

install-ollama:
	curl -fsSL https://ollama.com/install.sh | sh

model:
	ollama pull qwen3:4b

model-check:
	python3 scripts/check_model_memory.py $${OLLAMA_MODEL:-qwen3:4b}

configure:
	$(VENV)/bin/trading-agent configure

doctor:
	$(VENV)/bin/trading-agent doctor

robinhood-auth:
	@echo "No live Robinhood OAuth credentials or supported MCP schema are assumed."
	@echo "Configure an official supported broker adapter only after reviewing the provider documentation."

dashboard:
	$(VENV)/bin/uvicorn app.main:app --host $${APP_HOST:-127.0.0.1} --port $${APP_PORT:-8000}

run-once:
	$(VENV)/bin/trading-agent run-once

scheduler:
	$(VENV)/bin/python -m app.scheduler_owner

status:
	$(VENV)/bin/trading-agent status

stop:
	sudo systemctl stop local-trading-agent local-trading-dashboard

paper-start:
	@grep -q '^PAPER_TRADING=true' .env || (echo 'PAPER_TRADING=true is required' && exit 1)
	@echo "Paper mode: use 'make dashboard' or 'make scheduler'"

paper-status:
	$(VENV)/bin/trading-agent paper-status

paper-report:
	$(VENV)/bin/trading-agent report-daily

paper-reset:
	@read -p "Reset paper account? type RESET: " answer; test "$$answer" = RESET
	$(VENV)/bin/python -c "from app.paper_store import PaperStore; import os; from dotenv import load_dotenv; load_dotenv(); PaperStore().reset(float(os.getenv('PAPER_INITIAL_CAPITAL','5000')))"; echo "Paper account reset"

backtest:
	$(VENV)/bin/python -m app.backtest

analytics:
	$(VENV)/bin/trading-agent analytics

report-daily:
	$(VENV)/bin/trading-agent report-daily

report-weekly:
	$(VENV)/bin/trading-agent report-weekly

report-monthly:
	$(VENV)/bin/trading-agent report-monthly

export-trades:
	$(VENV)/bin/trading-agent export-trades

backup:
	$(VENV)/bin/trading-agent backup

restore:
	@if [ -z "$(BACKUP)" ]; then echo "Set BACKUP=/path/to/trading.db"; exit 1; fi
	$(VENV)/bin/trading-agent restore "$(BACKUP)"

storage-status:
	$(VENV)/bin/trading-agent storage-status

storage-prune:
	$(VENV)/bin/trading-agent storage-prune

risk-profile:
	@if [ -z "$(PROFILE)" ]; then echo "Set PROFILE=conservative|balanced|aggressive|custom"; exit 1; fi
	@python3 -c 'import yaml,sys; p=sys.argv[1]; d=yaml.safe_load(open("config/risk_profiles.yaml")); sys.exit(0 if p in d or p=="custom" else 1)' "$(PROFILE)"
	@sed -i 's/^RISK_PROFILE=.*/RISK_PROFILE=$(PROFILE)/' .env 2>/dev/null || echo 'RISK_PROFILE=$(PROFILE)' >> .env

test:
	$(VENV)/bin/pytest -q

test-integration:
	$(VENV)/bin/pytest -q tests/integration

install-service:
	bash scripts/install_linux.sh

live-readiness:
	$(VENV)/bin/trading-agent live-readiness
