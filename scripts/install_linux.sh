#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="$(id -un)"

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run this installer as your normal laptop user, not as root."
  exit 1
fi

if [[ ! -d "${PROJECT_DIR}/.venv" ]]; then
  echo "Missing .venv. Run 'make setup' first."
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

sed \
  -e "s|/home/%u/LocalTradingAgent|${PROJECT_DIR}|g" \
  -e "s|%u|${SERVICE_USER}|g" \
  "${PROJECT_DIR}/systemd/local-trading-agent.service" > "${tmp_dir}/local-trading-agent.service"

sed \
  -e "s|/home/%u/LocalTradingAgent|${PROJECT_DIR}|g" \
  -e "s|%u|${SERVICE_USER}|g" \
  "${PROJECT_DIR}/systemd/local-trading-dashboard.service" > "${tmp_dir}/local-trading-dashboard.service"

sudo install -m 0644 "${tmp_dir}/local-trading-agent.service" /etc/systemd/system/local-trading-agent.service
sudo install -m 0644 "${tmp_dir}/local-trading-dashboard.service" /etc/systemd/system/local-trading-dashboard.service
sudo systemctl daemon-reload

sudo systemctl enable --now local-trading-agent.service
sudo systemctl enable --now local-trading-dashboard.service

echo "Installed and started:"
echo "  local-trading-agent.service"
echo "  local-trading-dashboard.service"
echo "Dashboard: http://127.0.0.1:8000"
