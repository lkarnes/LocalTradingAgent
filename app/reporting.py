from __future__ import annotations

from datetime import date


def daily_report(portfolio, quotes: dict[str, float], recommendations: list[dict],
                 risk_events: list[dict], news: list[dict], health: list[dict]) -> dict:
    market_value = portfolio.market_value(quotes)
    total_value = portfolio.total_value(quotes)
    return {
        "report_date": date.today().isoformat(),
        "starting_portfolio_value": portfolio.initial_cash,
        "ending_portfolio_value": round(total_value, 2),
        "daily_return": 0.0,
        "realized_pnl": round(portfolio.realized_pnl, 2),
        "unrealized_pnl": round(market_value - sum(
            p["quantity"] * p["average_cost"] for p in portfolio.positions.values()
        ), 2),
        "cash_balance": round(portfolio.cash, 2),
        "holdings": portfolio.positions,
        "purchases": [],
        "sales": [],
        "recommendations": recommendations,
        "risk_events": risk_events,
        "new_news": news,
        "agent_health": health,
    }
