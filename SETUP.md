# Linux Mint Setup From Scratch

This procedure creates a working research/paper-trading installation on a dedicated Linux Mint laptop. It does not enable live trading.

## 1. Confirm the target system

Use a Linux Mint release that provides Python 3.12 or can install it through its supported package/portable-Python method. Confirm:

```bash
lsb_release -a
python3.12 --version
uname -m
free -h
```

Expected:

- Linux Mint 64-bit
- Python 3.12
- At least 8 GB RAM
- At least 20 GB free disk space

Do not continue if `python3.12` is unavailable. Install Python 3.12 through your Linux Mint-supported package source or a version manager before running the project setup.

## 2. Install operating-system prerequisites

```bash
sudo apt update
sudo apt install -y curl git make python3.12 python3.12-venv python3.12-dev
sudo apt install -y build-essential pkg-config
```

If the `python3.12` packages are not present, use your release's supported Python installation instructions. Do not install arbitrary binary packages from untrusted repositories.

## 3. Clone or copy the repository

```bash
cd ~
git clone https://github.com/lkarnes/LocalTradingAgent.git
cd LocalTradingAgent
```

If the project was copied on a USB drive instead of cloned, enter the copied directory and skip `git clone`.

## 4. Create the environment and install dependencies

```bash
make setup
```

This:

- creates `.venv`
- upgrades pip
- installs the project dependencies
- creates `.env` from `.env.example` if `.env` does not exist

Verify:

```bash
.venv/bin/python --version
test -f .env && echo ".env created"
```

## 5. Install Ollama

```bash
make install-ollama
ollama serve
```

In another terminal, verify Ollama:

```bash
curl http://127.0.0.1:11434/api/tags
```

Pull the initial model:

```bash
make model
```

Check whether it fits the laptop's currently available memory:

```bash
make model-check
```

For an 8 GB laptop, start with `qwen3:1.7b` if memory use or inference is poor:

```bash
ollama pull qwen3:1.7b
```

Then set `OLLAMA_MODEL=qwen3:1.7b` in `.env`.

Check actual memory use while the model runs:

```bash
ollama ps
free -h
```

## 6. Configure secrets and operating mode

Copy the example manually if setup did not:

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

The required safe starting values are:

```dotenv
APP_HOST=127.0.0.1
APP_PORT=8000
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=<generate-a-long-random-password>

PAPER_TRADING=true
LIVE_TRADING_ENABLED=false
TRADING_MODE=research

PAPER_INITIAL_CAPITAL=5000
RISK_PROFILE=balanced
OLLAMA_MODEL=qwen3:4b
```

Generate a dashboard password without printing it to shell history:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Paste the generated value into `.env`.

For paper trading, also set:

```dotenv
PAPER_TRADING=true
LIVE_TRADING_ENABLED=false
REQUIRE_MANUAL_APPROVAL=true
TRADING_MODE=paper
```

Do not set `LIVE_TRADING_ENABLED=true` unless you intend to complete a separate, fully verified live-broker activation.

## 7. Configure watchlist and providers

Edit the watchlist:

```bash
nano config/watchlist.yaml
```

Optional Finnhub news:

```dotenv
NEWS_PROVIDER=finnhub
FINNHUB_API_KEY=<provider-key>
```

Leave Finnhub empty and use RSS for an installation that should start without optional credentials.

Set a real identifying contact for SEC requests:

```dotenv
SEC_USER_AGENT=LocalTradingAgent your-email@example.com
```

Never place credentials in YAML, Git, screenshots, or source code.

## 8. Validate the installation

```bash
make configure
make doctor
make status
make live-readiness
```

Expected before the laptop is unattended:

- configuration is valid
- SQLite database is healthy
- Ollama is available
- the selected model is installed
- paper trading is enabled
- live trading is disabled
- live readiness reports `ready: false`

## 9. Start the dashboard manually

```bash
make dashboard
```

Open `http://127.0.0.1:8000` on the laptop.

Sign in with `DASHBOARD_USER` and `DASHBOARD_PASSWORD`. Stop the manual dashboard with `Ctrl+C`.

## 10. Start 24/7 services

First prevent suspend:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Disable laptop lid suspension with the Mint desktop power settings as well.

Install and start both services:

```bash
scripts/install_linux.sh
```

The installer creates separate dashboard and scheduler services. Both services use the normal
login user account, restart automatically after failure or reboot, and have no public network binding.

The script requires the normal user account to use `sudo`. It creates systemd units using the repository's actual absolute path, then starts:

- `local-trading-agent.service`
- `local-trading-dashboard.service`

They are separate by design: the dashboard does not start a second scheduler.

Verify:

```bash
sudo systemctl status local-trading-agent.service
sudo systemctl status local-trading-dashboard.service
sudo journalctl -u local-trading-agent.service -f
sudo journalctl -u local-trading-dashboard.service -f
```

After reboot, verify both services return automatically:

```bash
sudo systemctl is-enabled local-trading-agent.service
sudo systemctl is-enabled local-trading-dashboard.service
sudo systemctl is-active local-trading-agent.service
sudo systemctl is-active local-trading-dashboard.service
```

## 11. Optional private remote access

Install and connect Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4
```

On another authorized device in the same Tailnet, open:

```text
http://<laptop-tailscale-ip>:8000
```

Do not expose port 8000 to the public internet. Do not forward it through a router or cloud reverse proxy without external-authentication and TLS controls.

## 12. First paper-trading workflow

```bash
make paper-start
make status
make run-once
make paper-status
make backup
```

Before leaving it unattended:

1. Confirm research or paper mode.
2. Confirm paper capital and risk profile.
3. Confirm Ollama and news-provider health.
4. Confirm there are no live credentials or live flags enabled.
5. Activate the scheduler service.
6. Back up `data/trading.db`.

## 13. Backups and recovery

Create a backup:

```bash
make backup
ls -lh backups/
```

Restore only into a stopped application:

```bash
sudo systemctl stop local-trading-agent.service local-trading-dashboard.service
make restore BACKUP=/absolute/path/to/trading.db
sudo systemctl start local-trading-agent.service local-trading-dashboard.service
```

Keep a copy of `.env` in a secure local password/backup system, not in Git.

Set the SQLite storage ceiling in `.env`:

```dotenv
DATA_STORAGE_LIMIT_GB=10
```

Allowed range: 10-100 GiB. Check and prune storage with:

```bash
make storage-status
make storage-prune
```

## 14. Live-trading activation

Live trading is not available until an official broker adapter is verified. Do not infer that paper performance or 30 days of paper trading authorizes live mode.

Before any live activation:

1. Verify the official broker MCP documentation and tool schemas.
2. Complete read-only account and reconciliation testing.
3. Store OAuth credentials in protected local storage.
4. Set `PAPER_TRADING=false`.
5. Set `LIVE_TRADING_ENABLED=true`.
6. Set `TRADING_MODE=approval` for the first live attempt.
7. Run `make live-readiness`.
8. Complete approval-mode testing.
9. Only then consider `TRADING_MODE=live`.

The execution engine must reject live submission on missing reconciliation, stale data, broker outage, account mismatch, or any failed risk check.
