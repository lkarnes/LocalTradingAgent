from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
import yfinance as yf
import exchange_calendars as xcals


class MarketDataProvider:
    def __init__(self, max_quote_age_seconds: int = 300):
        self.max_quote_age_seconds = max_quote_age_seconds

    def quote(self, symbol: str) -> dict | None:
        ticker = yf.Ticker(symbol)
        fast = ticker.fast_info
        price = getattr(fast, "last_price", None)
        if price is None:
            return None
        return {
            "symbol": symbol,
            "price": float(price),
            "source": "yfinance",
            "source_timestamp": datetime.now(timezone.utc),
            "retrieved_at": datetime.now(timezone.utc),
            "data_type": "quote",
        }

    def history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        return yf.Ticker(symbol).history(period=period, auto_adjust=True)

    def quote_is_fresh(self, quote: dict | None) -> bool:
        if not quote:
            return False
        retrieved = quote["retrieved_at"]
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - retrieved).total_seconds()
        return 0 <= age <= self.max_quote_age_seconds


def is_nyse_open(now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    calendar = xcals.get_calendar("XNYS")
    local = now.astimezone(calendar.tz)
    return bool(calendar.is_open_on_minute(local, True, False)), "XNYS"


def is_nyse_session_day(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    calendar = xcals.get_calendar("XNYS")
    local = now.astimezone(calendar.tz)
    return bool(calendar.is_session(local.date()))

