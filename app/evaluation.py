from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.analytics import performance_metrics
from app.database import (
    AgentHealth,
    AgentRun,
    BenchmarkSnapshot,
    DailyPerformance,
    DailyReport,
    Execution,
    PaperEvaluation,
    RiskEvent,
    SimulatedOrder,
    StrategyScan,
    get_database,
)
from app.paper_store import PaperStore
from app.trading import PaperPortfolio
from app.config import resolve_settings
from app.market import MarketDataProvider


def benchmark_return(symbol: str, start: datetime, end: datetime) -> dict:
    try:
        provider = MarketDataProvider()
        history = provider.history(symbol, period="1y")
        if history.empty or "Close" not in history:
            return {"symbol": symbol, "status": "unavailable"}
        closes = history["Close"].dropna()
        local_dates = getattr(closes.index, "tz_localize", None)
        first = float(closes.iloc[0])
        last = float(closes.iloc[-1])
        if first <= 0:
            return {"symbol": symbol, "status": "unavailable"}
        return {
            "symbol": symbol,
            "status": "available",
            "starting_close": first,
            "ending_close": last,
            "return": (last / first) - 1,
            "source": "yfinance",
        }
    except Exception as exc:
        return {"symbol": symbol, "status": "unavailable", "reason": exc.__class__.__name__}


def start_paper_evaluation(initial_value: float | None = None) -> dict:
    env, app, _ = resolve_settings()
    if not app.paper_trading:
        raise RuntimeError("Paper evaluation requires PAPER_TRADING=true")
    _, session_factory = get_database()
    starting = float(initial_value or env.paper_initial_capital)
    key = f"paper-30d-{datetime.now(timezone.utc).date().isoformat()}"
    with session_factory() as session:
        existing = session.query(PaperEvaluation).filter_by(evaluation_key=key).first()
        if existing is not None:
            return {"status": existing.status, "evaluation_key": key, "payload": existing.payload}
        row = PaperEvaluation(
            evaluation_key=key,
            status="running",
            starting_value=starting,
            payload={
                "paper_trading": True,
                "live_trading_enabled": False,
                "minimum_days": env.paper_minimum_days,
                "minimum_trades": env.paper_require_minimum_trades,
                "starting_value": starting,
            },
        )
        session.add(row)
        session.commit()
    return {"status": "running", "evaluation_key": key}


def generate_paper_evaluation(days: int = 30) -> dict:
    env, app, _ = resolve_settings()
    if not app.paper_trading:
        raise RuntimeError("Paper evaluation requires PAPER_TRADING=true")

    _, session_factory = get_database()
    with session_factory() as session:
        performance = session.query(DailyPerformance).order_by(
            DailyPerformance.report_date.asc()
        ).all()
        daily_reports = session.query(DailyReport).order_by(
            DailyReport.report_date.asc()
        ).all()
        executions = session.query(Execution).order_by(Execution.timestamp.asc()).all()
        orders = session.query(SimulatedOrder).order_by(SimulatedOrder.created_at.asc()).all()
        risk_events = session.query(RiskEvent).order_by(RiskEvent.created_at.asc()).all()
        health = session.query(AgentHealth).order_by(AgentHealth.checked_at.desc()).limit(200).all()
        scans = session.query(StrategyScan).order_by(StrategyScan.started_at.asc()).all()

        recent_performance = performance[-days:]
        returns = [row.daily_return or 0 for row in recent_performance]
        metrics = performance_metrics(returns)

        filled = [order for order in orders if order.status == "filled"]
        rejected = [order for order in orders if order.status == "rejected"]

        portfolio = PaperStore().load(PaperPortfolio(
            env.paper_initial_capital,
            env.paper_slippage_bps,
            env.paper_commission_per_order,
        ))
        ending_value = portfolio.total_value({})
        starting_value = (
            recent_performance[0].starting_value
            if recent_performance
            else env.paper_initial_capital
        )
        now = datetime.now(timezone.utc)
        period_start = (
            recent_performance[0].report_date
            if recent_performance
            else (now - timedelta(days=days)).date().isoformat()
        )

        benchmark_start = now - timedelta(days=365)
        benchmarks = {
            "VTI": benchmark_return("VTI", benchmark_start, now),
            "SPY": benchmark_return("SPY", benchmark_start, now),
            "cash": {
                "symbol": "CASH",
                "status": "available",
                "return": 0,
                "source": "zero-return baseline",
            },
        }

        completed_trades = len(filled)
        evidence_status = (
            "Ready for further evaluation"
            if len(recent_performance) >= days and completed_trades >= env.paper_require_minimum_trades
            else "Insufficient evidence"
        )

        payload = {
            "test_type": "paper",
            "evaluation_date": now.isoformat(),
            "period": {
                "start": period_start,
                "calendar_days": days,
                "daily_reports": len(recent_performance),
            },
            "paper_trading": True,
            "live_trading_enabled": False,
            "live_authorization": "not granted",
            "starting_value": round(starting_value, 2),
            "ending_value": round(ending_value, 2),
            "cash": round(portfolio.cash, 2),
            "holdings": portfolio.positions,
            "realized_pnl": round(portfolio.realized_pnl, 2),
            "metrics": metrics,
            "completed_trades": completed_trades,
            "rejected_trades": len(rejected),
            "risk_events": len(risk_events),
            "intraday_scans": len(scans),
            "provider_health": [
                {
                    "checked_at": row.checked_at.isoformat() if row.checked_at else None,
                    "component": row.component,
                    "status": row.status,
                }
                for row in health[:50]
            ],
            "benchmarks": benchmarks,
            "outcome": evidence_status,
            "recommendations": [
                "Keep PAPER_TRADING=true until this report is manually reviewed.",
                "Do not enable live trading based only on paper performance.",
                "Review rejected trades, stop audits, stale quotes, and provider outages.",
                "Adjust strategy and risk config from the evidence, then restart a new paper period.",
            ],
        }

        key = f"paper-30d-{now.date().isoformat()}"
        row = session.query(PaperEvaluation).filter_by(evaluation_key=key).first()
        if row is None:
            row = PaperEvaluation(
                evaluation_key=key,
                status="completed",
                starting_value=starting_value,
                ending_value=ending_value,
                payload=payload,
            )
            session.add(row)
        else:
            row.status = "completed"
            row.completed_at = now
            row.ending_value = ending_value
            row.payload = payload
        session.commit()

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"paper-evaluation-{now.date().isoformat()}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_path = reports_dir / f"paper-evaluation-{now.date().isoformat()}-orders.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["created_at", "symbol", "side", "quantity", "status", "filled_quantity", "average_fill"])
        for order in orders:
            writer.writerow([
                order.created_at.isoformat() if order.created_at else "",
                order.symbol,
                order.side,
                order.quantity,
                order.status,
                order.filled_quantity,
                order.average_fill,
            ])
    payload["export"] = {
        "json": str(json_path),
        "orders_csv": str(csv_path),
    }
    return payload
