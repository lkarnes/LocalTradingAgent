from __future__ import annotations

import secrets
import hmac
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import yaml

from app.config import resolve_settings
from app.market import MarketDataProvider
from app.trading import Order, OrderAction, RiskManager
from app.paper_store import PaperStore
from app.database import (DailyReport, NewsArticle, TradeDecision, AgentHealth,
                          DailyPerformance, SimulatedOrder, StrategyScan, get_database)

security = HTTPBasic(auto_error=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def dashboard_auth(credentials: HTTPBasicCredentials | None = Depends(security)):
    env, _, _ = resolve_settings()
    if not env.dashboard_password:
        raise HTTPException(status_code=503, detail="Set DASHBOARD_PASSWORD before remote or local dashboard use")
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required",
                            headers={"WWW-Authenticate": "Basic"})
    if not (hmac.compare_digest(credentials.username, env.dashboard_user)
            and hmac.compare_digest(credentials.password, env.dashboard_password)):
        raise HTTPException(status_code=401, detail="Invalid credentials",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials


def register_dashboard(app: FastAPI, paper_portfolio):
    @app.get("/", response_class=HTMLResponse)
    async def overview(request: Request, credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        env, app_settings, profiles = resolve_settings()
        quotes = {}
        active_profile = profiles[env.risk_profile]
        portfolio_value = paper_portfolio.total_value(quotes)
        return templates.TemplateResponse(request=request, name="overview.html", context={
            "app": app_settings,
            "env": env,
            "profile": active_profile,
            "paper": paper_portfolio,
            "portfolio_value": portfolio_value,
            "holdings": paper_portfolio.positions,
            "cash": paper_portfolio.cash,
            "open_orders": [],
            "kill_switch": getattr(app.state, "kill_switch", False),
        })

    @app.post("/kill-switch")
    async def kill_switch(request: Request, credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        data = await request.json()
        enabled = bool(data.get("enabled", True))
        app.state.kill_switch = enabled
        flag = Path("data/kill-switch")
        if enabled:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("enabled\n", encoding="utf-8")
        elif flag.exists():
            flag.unlink()
        return {"kill_switch": app.state.kill_switch}

    @app.get("/api/status")
    async def status(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        env, app_settings, profiles = resolve_settings()
        return {
            "operating_mode": app_settings.operating_mode,
            "paper_trading": app_settings.paper_trading,
            "live_trading_enabled": app_settings.live_trading_enabled,
            "kill_switch": getattr(app.state, "kill_switch", False),
            "paper": paper_portfolio.to_state(),
            "active_risk_profile": env.risk_profile,
            "cost_guard": env.cost_guard_enabled,
            "paid_providers_allowed": env.allow_paid_providers,
        }

    @app.get("/portfolio")
    async def portfolio(request: Request, credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        quotes = {}
        for symbol in paper_portfolio.positions:
            quote = MarketDataProvider().quote(symbol)
            if quote:
                quotes[symbol] = quote["price"]
        return templates.TemplateResponse(request=request, name="portfolio.html", context={
            "paper": paper_portfolio,
            "quotes": quotes,
            "market_value": paper_portfolio.market_value(quotes),
            "total_value": paper_portfolio.total_value(quotes),
        })

    @app.get("/watchlist")
    async def watchlist(request: Request, credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        env, app_settings, profiles = resolve_settings()
        import yaml
        watchlist = yaml.safe_load((Path("config/watchlist.yaml")).read_text()) or {}
        symbols = watchlist.get("symbols", [])
        provider = MarketDataProvider()
        quotes = {symbol: provider.quote(symbol) for symbol in symbols}
        return templates.TemplateResponse(request=request, name="watchlist.html", context={
            "symbols": symbols,
            "quotes": quotes,
        })

    @app.post("/paper/order")
    async def paper_order(request: Request, credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        data = await request.json()
        symbol = str(data["symbol"]).strip().upper()
        side = str(data["side"]).upper()
        quantity = float(data["quantity"])
        if getattr(app.state, "kill_switch", False) and side != "SELL":
            return {"status": "rejected", "reason": "Emergency kill switch active"}
        if side not in {"BUY", "SELL"}:
            return {"status": "rejected", "reason": "Invalid side"}
        quote = MarketDataProvider().quote(symbol)
        if not quote or not MarketDataProvider().quote_is_fresh(quote):
            return {"status": "rejected", "reason": "Stale or unavailable quote"}
        env, app_settings, profiles = resolve_settings()
        profile = profiles[env.risk_profile]
        risk = RiskManager(profile, paper_portfolio.cash)
        is_exit = side == "SELL"
        order = Order(
            symbol=symbol,
            side=OrderAction(side),
            quantity=quantity,
            quote_price=quote["price"],
            idempotency_key=str(data.get("idempotency_key",
                                        f"{symbol}:{side}:{quantity}:{quote['price']}")),
            is_exit=is_exit,
        )
        result = risk.evaluate(order, True, 0, paper_portfolio.seen_keys)
        if not result.allowed:
            return {"status": "rejected", "reason": result.reason}
        filled = paper_portfolio.submit(order)
        PaperStore().record_order(symbol, side, quantity, filled, order.idempotency_key)
        PaperStore().save(paper_portfolio)
        return filled

    @app.get("/api/news")
    async def news(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        _, session_factory = get_database()
        with session_factory() as session:
            rows = session.query(NewsArticle).order_by(NewsArticle.retrieved_at.desc()).limit(100).all()
            return [{
                "symbol": row.symbol,
                "source": row.source,
                "headline": row.headline,
                "url": row.url,
                "published_at": row.published_at.isoformat() if row.published_at else None,
            } for row in rows]

    @app.get("/api/recommendations")
    async def recommendations(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        _, session_factory = get_database()
        with session_factory() as session:
            rows = session.query(TradeDecision).order_by(TradeDecision.created_at.desc()).limit(100).all()
            return [{
                "symbol": row.symbol,
                "action": row.action,
                "confidence": row.confidence,
                "reasoning": row.reasoning,
                "approval_status": row.approval_status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            } for row in rows]

    @app.get("/api/reports")
    async def reports(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        _, session_factory = get_database()
        with session_factory() as session:
            rows = session.query(DailyReport).order_by(DailyReport.report_date.desc()).limit(90).all()
            return [{"report_date": row.report_date, "payload": row.payload} for row in rows]

    @app.get("/api/health")
    async def health_details(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        _, session_factory = get_database()
        with session_factory() as session:
            rows = session.query(AgentHealth).order_by(AgentHealth.checked_at.desc()).limit(100).all()
            return [{
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
                "component": row.component,
                "status": row.status,
                "detail": row.detail,
            } for row in rows]

    @app.post("/api/config")
    async def update_config(request: Request, credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        data = await request.json()
        allowed = {
            "APP_HOST", "APP_PORT", "APP_TIMEZONE", "OLLAMA_BASE_URL", "OLLAMA_MODEL",
            "OLLAMA_CONTEXT_SIZE", "OLLAMA_TEMPERATURE", "OLLAMA_TIMEOUT",
            "PAPER_TRADING", "LIVE_TRADING_ENABLED", "REQUIRE_MANUAL_APPROVAL",
            "TRADING_MODE", "PAPER_INITIAL_CAPITAL", "PAPER_SLIPPAGE_BPS",
            "RISK_PROFILE", "NEWS_INTERVAL_MINUTES", "ANALYSIS_INTERVAL_MINUTES",
            "TRADE_EVALUATION_INTERVAL_MINUTES",
            "DATA_STORAGE_LIMIT_GB",
            "OLLAMA_LIGHTWEIGHT_MODEL",
            "MAX_AI_CALLS_PER_SCAN",
            "AI_REVIEW_CACHE_MINUTES",
            "COST_GUARD_ENABLED",
            "ALLOW_PAID_PROVIDERS",
        }
        unknown = set(data) - allowed
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unsupported configuration keys: {sorted(unknown)}")

        env_path = Path(".env")
        existing = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    existing[key.strip()] = value.strip()
        effective = existing | {str(key): str(value) for key, value in data.items()}

        try:
            from app.config import Settings
            Settings(_env_file=None, **{
                key.lower(): value for key, value in effective.items()
                if hasattr(Settings.model_fields, "__contains__") and key.lower() in Settings.model_fields
            })
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Configuration validation failed: {exc}") from exc
        paper = effective.get("PAPER_TRADING", "true").lower() == "true"
        live = effective.get("LIVE_TRADING_ENABLED", "false").lower() == "true"
        mode = effective.get("TRADING_MODE", "research").lower()
        if paper and mode == "live":
            raise HTTPException(status_code=400, detail="PAPER_TRADING=true conflicts with TRADING_MODE=live")
        if mode == "live" and not live:
            raise HTTPException(status_code=400, detail="LIVE_TRADING_ENABLED=true is required for live mode")
        if live and mode not in {"approval", "live"}:
            raise HTTPException(status_code=400, detail="LIVE_TRADING_ENABLED=true requires approval or live mode")

        env_path.parent.mkdir(parents=True, exist_ok=True)
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        changed = set(data)
        updated = []
        for line in lines:
            key = line.split("=", 1)[0] if "=" in line else ""
            if key in changed:
                updated.append(f"{key}={data[key]}")
                changed.remove(key)
            else:
                updated.append(line)
        updated.extend(f"{key}={data[key]}" for key in sorted(changed))
        env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
        env_path.chmod(0o600)
        return {"status": "saved", "changed": sorted(data)}

    @app.get("/api/prompts")
    async def list_prompts(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        prompt_root = Path("prompts")
        return [
            str(path.relative_to(prompt_root)).replace("\\", "/")
            for path in sorted(prompt_root.rglob("*.md"))
        ]

    @app.post("/api/prompts/{relative_path:path}")
    async def save_prompt(relative_path: str, request: Request,
                          credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        root = Path("prompts").resolve()
        target = (root / relative_path).resolve()
        if root not in target.parents or target.suffix != ".md":
            raise HTTPException(status_code=400, detail="Invalid prompt path")
        data = await request.json()
        content = str(data.get("content", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"status": "saved", "prompt": relative_path}

    @app.get("/api/analytics")
    async def analytics(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        _, session_factory = get_database()
        with session_factory() as session:
            rows = session.query(DailyPerformance).order_by(DailyPerformance.report_date).all()
            returns = [row.daily_return or 0 for row in rows]
            completed_trades = session.query(SimulatedOrder).filter(
                SimulatedOrder.status == "filled"
            ).count()
        from app.analytics import performance_metrics, paper_evaluation
        metrics = performance_metrics(returns)
        evaluation = paper_evaluation(len(rows), completed_trades)
        return {"metrics": metrics, "evaluation": evaluation}

    @app.get("/api/storage")
    async def storage(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        from app.storage import storage_status
        return storage_status()

    @app.post("/api/storage/prune")
    async def prune_storage(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        from app.storage import prune_database
        return prune_database()

    @app.post("/api/scans/run")
    async def run_active_scan(request: Request,
                              credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        data = await request.json()
        scan_name = str(data.get("scan_name", "manual"))
        from app.active_scan import ActivePositionScan
        try:
            return ActivePositionScan(paper_portfolio).run(scan_name)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/scans")
    async def list_active_scans(credentials: HTTPBasicCredentials = Depends(dashboard_auth)):
        _, session_factory = get_database()
        with session_factory() as session:
            rows = session.query(StrategyScan).order_by(
                StrategyScan.started_at.desc()
            ).limit(100).all()
            return [{
                "scan_name": row.scan_name,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "payload": row.payload,
            } for row in rows]
