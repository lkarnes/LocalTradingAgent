from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import resolve_settings
from app.trading import PaperPortfolio
from app.dashboard import register_dashboard
from app.paper_store import PaperStore
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI):
    env, app_settings, profiles = resolve_settings()
    app.state.paper_portfolio = PaperPortfolio(
        env.paper_initial_capital,
        env.paper_slippage_bps,
        env.paper_commission_per_order,
    )
    PaperStore().load(app.state.paper_portfolio)
    app.state.kill_switch = Path("data/kill-switch").exists()
    yield


app = FastAPI(title="Local Trading Agent", lifespan=lifespan)
env, app_settings, _ = resolve_settings()
app.state.paper_portfolio = PaperPortfolio(
    env.paper_initial_capital,
    env.paper_slippage_bps,
    env.paper_commission_per_order,
)
PaperStore().load(app.state.paper_portfolio)
app.state.kill_switch = Path("data/kill-switch").exists()
register_dashboard(app, app.state.paper_portfolio)


@app.get("/health")
async def health():
    env, app_settings, _ = resolve_settings()
    return {
        "status": "healthy",
        "mode": app_settings.operating_mode,
        "paper_trading": app_settings.paper_trading,
        "live_trading_enabled": app_settings.live_trading_enabled,
        "kill_switch": getattr(app.state, "kill_switch", False),
    }
