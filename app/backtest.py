from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.indicators import calculate_indicators


@dataclass
class BacktestResult:
    starting_value: float
    ending_value: float
    fees: float
    slippage: float
    trades: int
    return_percent: float


def run_simple_backtest(history: pd.DataFrame, starting_cash: float = 10_000,
                        commission: float = 0, slippage_bps: float = 10) -> BacktestResult:
    if "Close" not in history or len(history) < 2:
        return BacktestResult(starting_cash, starting_cash, 0, 0, 0, 0)
    close = history["Close"].dropna()
    shares = 0.0
    cash = starting_cash
    trades = 0
    fees = 0.0
    slippage_cost = 0.0
    position = False
    sma20 = close.rolling(20).mean()
    for i in range(20, len(close)):
        price = float(close.iloc[i])
        if not position and price > float(sma20.iloc[i]):
            fill = price * (1 + slippage_bps / 10_000)
            shares = (cash - commission) / fill
            cash = 0
            fees += commission
            slippage_cost += shares * (fill - price)
            trades += 1
            position = True
        elif position and price < float(sma20.iloc[i]):
            fill = price * (1 - slippage_bps / 10_000)
            cash = shares * fill - commission
            fees += commission
            slippage_cost += shares * (price - fill)
            shares = 0
            trades += 1
            position = False
    ending = cash + shares * float(close.iloc[-1])
    return BacktestResult(
        starting_cash,
        round(ending, 2),
        round(fees, 2),
        round(slippage_cost, 2),
        trades,
        round((ending / starting_cash - 1) * 100, 4),
    )


def main() -> None:
    from app.market import MarketDataProvider
    history = MarketDataProvider().history("SPY", period="2y")
    result = run_simple_backtest(history)
    print({
        "symbol": "SPY",
        "starting_value": result.starting_value,
        "ending_value": result.ending_value,
        "fees": result.fees,
        "slippage": result.slippage,
        "trades": result.trades,
        "return_percent": result.return_percent,
        "disclaimer": "Historical backtest; not evidence of future profitability.",
    })


if __name__ == "__main__":
    main()
