from __future__ import annotations

import math
from statistics import mean, pstdev


def performance_metrics(daily_returns: list[float], benchmark_returns: list[float] | None = None) -> dict:
    returns = [float(value) for value in daily_returns]
    if not returns:
        return {
            "total_return": 0,
            "annualized_volatility": 0,
            "sharpe_ratio": 0,
            "maximum_drawdown": 0,
        }
    equity = 1.0
    peak = equity
    max_drawdown = 0.0
    for daily in returns:
        equity *= 1 + daily
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
    volatility = pstdev(returns) * math.sqrt(252) if len(returns) > 1 else 0
    average = mean(returns)
    sharpe = (average * 252) / volatility if volatility else 0
    return {
        "total_return": equity - 1,
        "annualized_volatility": volatility,
        "sharpe_ratio": sharpe,
        "maximum_drawdown": max_drawdown,
    }


def paper_evaluation(trading_days: int, completed_trades: int) -> dict:
    if trading_days < 30:
        return {"outcome": "Insufficient evidence", "reason": "30-day paper review not reached"}
    if completed_trades < 20:
        return {"outcome": "Insufficient evidence", "reason": "Minimum 20 paper trades not reached"}
    return {
        "outcome": "Needs improvement",
        "reason": "This evaluation requires human review; no live authorization is automatic",
    }


def calculate_trade_metrics(trades: list[dict]) -> dict:
    wins = [float(trade["pnl"]) for trade in trades if float(trade["pnl"]) > 0]
    losses = [float(trade["pnl"]) for trade in trades if float(trade["pnl"]) < 0]
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    return {
        "completed_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "average_win": gross_wins / len(wins) if wins else 0,
        "average_loss": -(gross_losses / len(losses)) if losses else 0,
        "profit_factor": gross_wins / gross_losses if gross_losses else (1 if gross_wins else 0),
        "realized_pnl": sum(float(trade["pnl"]) for trade in trades),
    }
