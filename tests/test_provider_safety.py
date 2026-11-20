from datetime import datetime, timedelta, timezone

from app.market import MarketDataProvider


def test_stale_quote_is_blocked():
    provider = MarketDataProvider(max_quote_age_seconds=300)
    stale = {
        "retrieved_at": datetime.now(timezone.utc) - timedelta(minutes=10),
    }
    assert not provider.quote_is_fresh(stale)


def test_missing_quote_is_blocked():
    provider = MarketDataProvider(max_quote_age_seconds=300)
    assert not provider.quote_is_fresh(None)
