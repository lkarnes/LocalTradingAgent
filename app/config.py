from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class AppSettings(BaseModel):
    timezone: str = "America/Los_Angeles"
    operating_mode: Literal["research", "paper", "approval", "live"] = "research"
    paper_trading: bool = True
    live_trading_enabled: bool = False
    require_manual_approval: bool = True
    initial_paper_capital: float = Field(default=5000, gt=0)
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_live_authorization(self):
        if self.paper_trading:
            if self.operating_mode == "live":
                raise ValueError("PAPER_TRADING=true conflicts with TRADING_MODE=live")
        elif self.operating_mode == "live" and not self.live_trading_enabled:
            raise ValueError("LIVE_TRADING_ENABLED=true is required for live mode")
        elif self.operating_mode not in ("research", "paper", "approval", "live"):
            raise ValueError("Invalid operating mode")
        if self.live_trading_enabled and self.operating_mode not in ("approval", "live"):
            raise ValueError("LIVE_TRADING_ENABLED=true requires approval or live mode")
        return self


class RiskProfile(BaseModel):
    max_position_percent: float = Field(gt=0, le=100)
    max_deployed_capital_percent: float = Field(gt=0, le=100)
    max_risk_per_trade_percent: float = Field(gt=0, le=100)
    max_daily_loss_percent: float = Field(gt=0, le=100)
    max_new_positions_per_day: int = Field(gt=0, le=10)
    max_order_value: float = Field(gt=0)
    max_drawdown_percent: float = Field(default=5, gt=0, le=100)
    min_stock_price: float = Field(default=5, ge=0)
    min_average_daily_dollar_volume: float = Field(default=5_000_000, ge=0)
    max_open_positions: int = Field(default=20, gt=0)
    max_sector_concentration_percent: float = Field(default=25, gt=0, le=100)
    max_slippage_bps: float = Field(default=25, ge=0)
    max_quote_age_seconds: int = Field(default=300, gt=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_timezone: str = "America/Los_Angeles"
    dashboard_user: str = "admin"
    dashboard_password: str = ""
    database_url: str = "sqlite:///./data/trading.db"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_lightweight_model: str = "qwen3:1.7b"
    ollama_context_size: int = 4096
    ollama_temperature: float = 0
    ollama_timeout: int = 300
    ollama_num_parallel: int = 1
    ollama_keep_alive: str = "24h"
    ollama_max_loaded_models: int = 1
    paper_trading: bool = True
    live_trading_enabled: bool = False
    require_manual_approval: bool = True
    trading_mode: Literal["research", "paper", "approval", "live"] = "research"
    paper_initial_capital: float = 5000
    paper_commission_per_order: float = 0
    paper_slippage_bps: int = 10
    paper_minimum_days: int = 30
    paper_require_minimum_trades: int = 20
    broker_provider: str = "none"
    finnhub_api_key: str = ""
    news_provider: str = "rss"
    market_data_provider: str = "yfinance"
    sec_user_agent: str = "LocalTradingAgent contact@example.com"
    risk_profile: str = "balanced"
    notifications_enabled: bool = False
    data_storage_limit_gb: float = Field(default=10, ge=10, le=100)
    max_ai_calls_per_scan: int = Field(default=2, ge=0, le=10)
    ai_review_cache_minutes: int = Field(default=30, ge=1, le=1440)
    cost_guard_enabled: bool = True
    allow_paid_providers: bool = False

    @model_validator(mode="after")
    def enforce_free_default(self):
        if self.dashboard_password == "CHANGE_ME_BEFORE_FIRST_RUN":
            raise ValueError("Replace DASHBOARD_PASSWORD before starting the application")
        if self.cost_guard_enabled and self.allow_paid_providers:
            raise ValueError("ALLOW_PAID_PROVIDERS must be false when COST_GUARD_ENABLED=true")
        if self.cost_guard_enabled and self.market_data_provider not in {"yfinance", "yahoo"}:
            raise ValueError("Cost guard only permits the default yfinance market-data provider")
        if self.cost_guard_enabled and self.news_provider not in {"rss", "none"}:
            raise ValueError("Cost guard only permits the free RSS/news provider")
        return self


class StrategySettings(BaseModel):
    intraday_enabled: bool = True
    premarket_enabled: bool = True
    stop_loss_percent: float = Field(default=8.0, gt=0, le=25)
    catalyst_freshness_hours: int = Field(default=48, gt=0, le=168)
    minimum_reward_risk_ratio: float = Field(default=1.5, gt=0)
    max_positions_reviewed_per_scan: int = Field(default=5, ge=1, le=20)
    max_entries_per_scan: int = Field(default=1, ge=0, le=10)
    max_exits_per_scan: int = Field(default=3, ge=0, le=20)
    cooldown_minutes_after_close: int = Field(default=120, ge=0)
    require_manual_approval: bool = True


def load_yaml(name: str) -> dict:
    path = ROOT / "config" / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_strategy() -> StrategySettings:
    return StrategySettings.model_validate(load_yaml("strategy.yaml"))


def resolve_settings() -> tuple[Settings, AppSettings, dict[str, RiskProfile]]:
    env = Settings()
    app_data = load_yaml("app.yaml")
    app_data.update({
        "timezone": env.app_timezone,
        "host": env.app_host,
        "port": env.app_port,
        "initial_paper_capital": env.paper_initial_capital,
        "operating_mode": env.trading_mode,
        "paper_trading": env.paper_trading,
        "live_trading_enabled": env.live_trading_enabled,
        "require_manual_approval": env.require_manual_approval,
    })
    app = AppSettings.model_validate(app_data)
    if app.paper_trading:
        if app.operating_mode == "live":
            raise ValueError("PAPER_TRADING=true conflicts with TRADING_MODE=live")
    elif app.operating_mode == "live" and not app.live_trading_enabled:
        raise ValueError("LIVE_TRADING_ENABLED=true is required for live mode")

    data = load_yaml("risk_profiles.yaml")
    profiles = {name: RiskProfile.model_validate(values) for name, values in data.items()}
    if env.risk_profile not in profiles:
        raise ValueError(f"Unknown RISK_PROFILE: {env.risk_profile}")
    return env, app, profiles

