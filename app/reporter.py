from __future__ import annotations

from datetime import date

from app.database import DailyReport, DailyPerformance, get_database
from app.paper_store import PaperStore
from app.trading import PaperPortfolio


def generate_daily_report(starting_value: float | None = None) -> dict:
    env, app, profiles = None, None, None
    from app.config import resolve_settings
    env, app, profiles = resolve_settings()
    portfolio = PaperStore().load(PaperPortfolio(
        env.paper_initial_capital,
        env.paper_slippage_bps,
        env.paper_commission_per_order,
    ))
    ending = portfolio.total_value({})
    starting = starting_value if starting_value is not None else env.paper_initial_capital
    daily_return = ((ending / starting) - 1) if starting else 0
    payload = {
        "report_date": date.today().isoformat(),
        "starting_portfolio_value": round(starting, 2),
        "ending_portfolio_value": round(ending, 2),
        "daily_return": round(daily_return, 6),
        "realized_pnl": round(portfolio.realized_pnl, 2),
        "cash_balance": round(portfolio.cash, 2),
        "holdings": portfolio.positions,
        "best_performer": None,
        "worst_performer": None,
        "purchases": [],
        "sales": [],
        "recommendations": [],
        "rejected_trades": [],
        "risk_events": [],
        "new_news": [],
        "agent_health": [],
    }
    _, session_factory = get_database()
    with session_factory() as session:
        existing = session.query(DailyReport).filter_by(report_date=payload["report_date"]).first()
        if existing:
            existing.payload = payload
        else:
            session.add(DailyReport(report_date=payload["report_date"], payload=payload))
        perf = session.query(DailyPerformance).filter_by(report_date=payload["report_date"]).first()
        unrealized = 0.0
        if perf is None:
            session.add(DailyPerformance(
                report_date=payload["report_date"],
                starting_value=starting,
                ending_value=ending,
                daily_return=daily_return,
                realized_pnl=portfolio.realized_pnl,
                unrealized_pnl=unrealized,
            ))
        session.commit()
    return payload


def generate_period_report(days: int) -> dict:
    _, session_factory = get_database()
    with session_factory() as session:
        rows = session.query(DailyReport).order_by(DailyReport.report_date.desc()).limit(days).all()
    payloads = [row.payload or {} for row in rows]
    if not payloads:
        return {"period_days": days, "status": "Insufficient evidence", "reports": []}
    values = [float(payload.get("ending_portfolio_value", 0)) for payload in reversed(payloads)]
    starting = float(payloads[-1].get("starting_portfolio_value", 0)) if payloads else 0
    ending = values[-1] if values else 0
    return {
        "period_days": days,
        "status": "complete" if len(payloads) == days else "partial",
        "available_reports": len(payloads),
        "starting_portfolio_value": starting,
        "ending_portfolio_value": ending,
        "period_return": ((ending / starting) - 1) if starting else 0,
        "reports": payloads,
    }
