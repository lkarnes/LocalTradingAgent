# Local AI Trading Agent

A self-hosted, local AI-assisted research and paper-trading platform for Linux Mint. The application uses Python 3.12, FastAPI, Jinja2/HTMX, SQLite, SQLAlchemy/Alembic, APScheduler, Ollama, and modular provider adapters.

## Safety model

The AI researches and recommends. Python enforces risk, data freshness, operating mode, approvals, duplicate prevention, and execution permissions. The broker/router is a separate final boundary.

- Research mode performs no orders.
- Paper mode sends every order only to the simulated portfolio.
- Approval mode prepares live orders but requires explicit approval.
- Live mode is disabled until all live authorization checks pass.
- `PAPER_TRADING=true` always routes orders to paper, even if the configured mode is changed incorrectly.
- The AI cannot edit or bypass risk profiles or hard execution ceilings.

This project does not provide financial advice or guarantee investment returns. Backtests and paper results are not evidence of future profitability.

## Hardware and target deployment

- Linux Mint
- 8 GB RAM
- Python 3.12
- Ollama with `qwen3:4b` or lower-resource `qwen3:1.7b`
- Dedicated laptop, ideally 24/7

## Quick start

The short path for a Linux Mint laptop is:

```bash
sudo apt update
sudo apt install -y curl git make python3.12 python3.12-venv python3.12-dev build-essential pkg-config
git clone https://github.com/lkarnes/LocalTradingAgent.git
cd LocalTradingAgent
make setup
make install-ollama
ollama pull qwen3:4b
make model-check
cp -n .env.example .env
chmod 600 .env
nano .env
make doctor
make dashboard
```

If `make model-check` reports too much memory pressure, pull the smaller model and update `.env`:

```bash
ollama pull qwen3:1.7b
OLLAMA_MODEL=qwen3:1.7b make model-check
```

Then set `OLLAMA_MODEL=qwen3:1.7b` in `.env`.

The check compares the Ollama model size with Linux `MemAvailable`, adds a conservative 25% runtime/context estimate, and reports whether it is likely too large. This is a capacity warning, not an absolute guarantee; monitor `free -h` and `ollama ps` while the model is running.

Before the first dashboard run, set at least:

```dotenv
PAPER_TRADING=true
LIVE_TRADING_ENABLED=false
TRADING_MODE=research
DASHBOARD_PASSWORD=<generate-a-long-random-password>
```

Use `qwen3:1.7b` instead of `qwen3:4b` if the 4B model is too slow or memory constrained, and update `OLLAMA_MODEL` in `.env`.

## Ollama stability policy

The application uses one active Ollama model request at a time:

- `OLLAMA_MODEL=qwen3:4b` for final structured research decisions.
- `OLLAMA_LIGHTWEIGHT_MODEL=qwen3:1.7b` for compact position-quality reviews.
- `OLLAMA_NUM_PARALLEL=1`.
- `OLLAMA_MAX_LOADED_MODELS=1`.
- `MAX_AI_CALLS_PER_SCAN=2`.
- `AI_REVIEW_CACHE_MINUTES=30`.

Python performs all stop audits, quote freshness checks, indicators, account reconciliation, risk checks, and order permissions. Ollama receives compact structured evidence and must return strict JSON. Malformed or extra-field responses are rejected.

If Ollama is unavailable:

- No new entries are authorized.
- Existing protective paper stops remain active.
- Risk-reducing protective exits remain allowed.
- The agent records a degraded Ollama health state and resumes normal entry analysis after recovery.

## Linux Mint installation

For the complete copy/paste procedure, including Python installation, environment configuration, Ollama, systemd, suspend settings, remote access, backups, and live-trading gates, see [SETUP.md](SETUP.md).

```bash
sudo apt update
sudo apt install -y make curl git python3.12 python3.12-venv python3.12-dev
git clone https://github.com/lkarnes/LocalTradingAgent.git
cd LocalTradingAgent
make setup
make install-ollama
make model
```

If `qwen3:4b` exceeds available memory, install a smaller compatible model and set `OLLAMA_MODEL=qwen3:1.7b` in `.env`.

Review [`.env.example`](.env.example) and create `.env`:

```bash
cp .env.example .env
chmod 600 .env
```

Set at least:

```dotenv
PAPER_TRADING=true
LIVE_TRADING_ENABLED=false
TRADING_MODE=research
DASHBOARD_PASSWORD=choose-a-long-random-password
```

Never commit `.env`, OAuth credentials, databases, backups, logs, or reports.

A private `.env` has been created from safe paper-only defaults. Before starting:

1. Replace `DASHBOARD_PASSWORD=CHANGE_ME_BEFORE_FIRST_RUN`.
2. Leave broker credentials and provider credentials empty for the paper trial.
3. Keep `PAPER_TRADING=true`, `LIVE_TRADING_ENABLED=false`, and `BROKER_PROVIDER=none`.
4. Run `make doctor`.

## Zero-cost paper mode

The default configuration is designed for zero paper-trading charges:

- Ollama runs locally.
- Yahoo Finance/yfinance is used only for research quotes and historical data.
- RSS news is free and no API key is used.
- Finnhub calls are blocked unless paid providers are explicitly enabled.
- No broker adapter is configured.
- Paper fills do not place real broker orders.

Keep these values:

```dotenv
COST_GUARD_ENABLED=true
ALLOW_PAID_PROVIDERS=false
BROKER_PROVIDER=none
PAPER_TRADING=true
LIVE_TRADING_ENABLED=false
FINNHUB_API_KEY=
```

`make doctor` reports the cost guard and broker state. It cannot guarantee that an external internet provider, Robinhood account, or future software terms have no fee; it prevents paid provider credentials and live broker submission paths from being enabled by default.

## First run

```bash
make configure
make doctor
make dashboard
```

Open `http://127.0.0.1:8000`. The dashboard requires HTTP Basic authentication using `DASHBOARD_USER` and `DASHBOARD_PASSWORD`.

Use the systemd scheduler and dashboard separately:

```bash
make install-service
sudo systemctl enable --now local-trading-dashboard
sudo systemctl enable --now local-trading-agent
```

The dashboard must not start the scheduler. It starts no second scheduler.

## Linux laptop operation

Disable suspend/sleep for reliable 24/7 operation:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Verify Ollama:

```bash
ollama list
curl http://127.0.0.1:11434/api/tags
```

## Configuration

General settings use `config/*.yaml`; secrets and deployment settings use `.env`. Effective values are validated with Pydantic. Precedence is built-in defaults, selected profile, local configuration, then environment overrides.

Initial profile values and schedules are in:

- `config/app.yaml`
- `config/ai.yaml`
- `config/risk_profiles.yaml`
- `config/schedule.yaml`
- `config/watchlist.yaml`

## Providers

### Market data

The initial adapter is Yahoo Finance/yfinance for research and historical testing. It is not assumed to be authoritative real-time data. Live orders require a provider that supplies a fresh, documented quote and will remain blocked otherwise.

### News

RSS and optional Finnhub company-news adapters are included. Finnhub requires `FINNHUB_API_KEY`. External article content is untrusted and cannot alter prompts or risk rules.

### SEC EDGAR

Set a truthful SEC-identifying `SEC_USER_AGENT` per SEC requirements. The code currently provides provider boundaries and RSS/Finnhub collection; SEC-specific filing ingestion should be enabled only after confirming the current SEC API/user-agent policy.

### Robinhood MCP

Robinhood live trading is not enabled because official MCP documentation, tool schemas, and account/OAuth capabilities must be verified for the deployment. The broker adapter boundary is explicit: when unconfigured, live submission raises `UnsupportedBrokerError`. Paper/research functionality remains available.

Before any live integration:

1. Verify the official Robinhood MCP endpoint and tools.
2. Verify the exact OAuth flow and scope.
3. Store tokens in OS keyring/protected storage, never in Git or logs.
4. Implement and test read-only portfolio operations.
5. Implement a no-network test double.
6. Run `make live-readiness`.

## Commands

```bash
make setup
make install-ollama
make model
make configure
make doctor
make dashboard
make robinhood-auth
make run-once
make scheduler
make status
make stop
make paper-start
make paper-status
make paper-report
make paper-reset
make backtest
make analytics
make report-daily
make report-weekly
make report-monthly
make export-trades
make backup
make restore BACKUP=backups/trading-YYYYMMDD-HHMMSS.db
make risk-profile PROFILE=balanced
make test
make test-integration
make install-service
make live-readiness
```

Every command must be run in the project virtual environment. `make setup` creates `.venv` and installs the project.

## Paper trading

Paper accounts maintain separate cash and holdings. Trades use configured slippage and commission, and persist through the database. The minimum paper period and trade count are evaluation checkpoints, never guarantees or automatic live-trading authorization.

Resetting paper data is destructive and requires explicit confirmation:

```bash
make paper-reset
```

## Testing

```bash
make test
make test-integration
```

No test submits a real brokerage order. Mocked brokers and stale/offline provider states are required for integration safety tests.

## Backups

```bash
make backup
make restore BACKUP=/absolute/path/to/trading.db
```

The database is stored in `data/trading.db` by default. Add a local encrypted/cloud backup procedure for the device if required.

## SQLite storage limit

Set a configurable database-size limit from 10 to 100 GiB:

```dotenv
DATA_STORAGE_LIMIT_GB=10
```

Check usage:

```bash
make storage-status
```

Prune the oldest cached market data, news, AI runs, health history, and benchmark snapshots, then compact SQLite:

```bash
make storage-prune
```

Audited paper/live trades and trade decisions are not part of the automatic cache-pruning list. The scheduler runs pruning daily at `03:00` by default.

## Remote access

Bind locally by default. For remote access, use Tailscale or a VPN/private network. Do not expose port 8000 or `.env` credentials directly to the public internet.

## Dashboard

The initial dashboard provides overview status, paper/live state, portfolio summary, risk profile, and an emergency kill switch. Provider health, research, approvals, reports, and prompt/config editors can be added through the modular route/template structure.

## Troubleshooting

- Run `make doctor` for configuration, database, and Ollama checks.
- Check logs with `journalctl -u local-trading-agent -f` and `journalctl -u local-trading-dashboard -f`.
- Check Ollama with `ollama ps` and `ollama list`.
- If memory is insufficient, use `qwen3:1.7b` and lower `OLLAMA_CONTEXT_SIZE`.
- If providers fail, the application reports degraded health and blocks new orders.
