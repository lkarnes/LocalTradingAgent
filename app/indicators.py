from __future__ import annotations

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator


def calculate_indicators(history: pd.DataFrame) -> dict:
    close = history["Close"].dropna()
    if len(close) < 20:
        return {"status": "insufficient_history"}
    rsi = RSIIndicator(close, window=14).rsi().iloc[-1]
    macd = MACD(close).macd().iloc[-1]
    sma20 = SMAIndicator(close, window=20).sma_indicator().iloc[-1]
    sma50 = SMAIndicator(close, window=50).sma_indicator().iloc[-1] if len(close) >= 50 else None
    sma200 = SMAIndicator(close, window=200).sma_indicator().iloc[-1] if len(close) >= 200 else None
    latest = float(close.iloc[-1])
    peak = float(close.iloc[-100:].max())
    drawdown = (latest - peak) / peak
    return {
        "price": latest,
        "rsi": float(rsi),
        "macd": float(macd),
        "sma20": float(sma20),
        "sma50": float(sma50) if sma50 is not None else None,
        "sma200": float(sma200) if sma200 is not None else None,
        "drawdown": float(drawdown),
        "trend": "bullish" if sma20 is not None and latest > sma20 else "bearish",
    }
