from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.config import load_yaml, resolve_settings
from app.database import AgentRun, AgentHealth, MarketData, NewsArticle, get_database
from app.market import MarketDataProvider, is_nyse_open
from app.news import fetch_finnhub, fetch_rss
from app.indicators import calculate_indicators


class ResearchPipeline:
    def __init__(self):
        env, app, profiles = resolve_settings()
        self.env = env
        self.app = app
        self.market = MarketDataProvider(300)

    def watchlist(self) -> list[str]:
        data = yaml.safe_load((Path("config/watchlist.yaml")).read_text(encoding="utf-8")) or {}
        return [str(symbol).upper() for symbol in data.get("symbols", [])]

    def collect_market_data(self) -> dict:
        engine, session_factory = get_database()
        results = []
        failures = []
        with session_factory() as session:
            for symbol in self.watchlist():
                try:
                    quote = self.market.quote(symbol)
                    if quote:
                        session.add(MarketData(
                            symbol=symbol,
                            data_type="quote",
                            source=quote["source"],
                            source_timestamp=quote["source_timestamp"],
                            payload=quote,
                        ))
                        results.append(symbol)
                except Exception as exc:
                    failures.append({"symbol": symbol, "error": exc.__class__.__name__})
            session.commit()
        return {"collected": results, "failures": failures}

    def collect_news(self) -> dict:
        _, session_factory = get_database()
        items = []
        schedule = yaml.safe_load((Path("config/schedule.yaml")).read_text(encoding="utf-8")) or {}
        news_schedule = schedule.get("news", {})
        if not news_schedule.get("fetch_weekends", False):
            weekday = datetime.now(timezone.utc).weekday()
            if weekday >= 5:
                return {"received": 0, "stored": 0, "status": "skipped_weekend"}
        for symbol in self.watchlist():
            if self.env.news_provider == "finnhub":
                items.extend(fetch_finnhub(
                    self.env.finnhub_api_key,
                    symbol,
                    allow_paid=(not self.env.cost_guard_enabled and self.env.allow_paid_providers),
                ))
            elif self.env.news_provider == "rss":
                rss_url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={}&region=US&lang=en-US"
                items.extend(fetch_rss(rss_url.format(symbol), symbol))
        stored = 0
        with session_factory() as session:
            for item in items:
                if not item.get("content_hash"):
                    continue
                exists = session.query(NewsArticle).filter_by(content_hash=item["content_hash"]).first()
                if exists:
                    continue
                session.add(NewsArticle(
                    symbol=item.get("symbol"),
                    source=item.get("source", "rss"),
                    url=item.get("url"),
                    headline=item.get("title"),
                    published_at=item.get("published_at"),
                    content_hash=item["content_hash"],
                ))
                stored += 1
            session.commit()
        return {"received": len(items), "stored": stored}

    def analyze_watchlist(self) -> dict:
        schedule = yaml.safe_load((Path("config/schedule.yaml")).read_text(encoding="utf-8")) or {}
        analysis_schedule = schedule.get("analysis", {})
        if analysis_schedule.get("analyze_only_when_market_open", False):
            is_open, _ = is_nyse_open()
            if not is_open:
                return {"status": "skipped_market_closed", "analyses": {}, "failures": []}
        analyses = {}
        failures = []
        for symbol in self.watchlist():
            try:
                history = self.market.history(symbol)
                analyses[symbol] = calculate_indicators(history)
            except Exception as exc:
                failures.append({"symbol": symbol, "error": exc.__class__.__name__})
        return {"analyses": analyses, "failures": failures}

    def record_health(self, component: str, status: str, detail: str) -> None:
        _, session_factory = get_database()
        with session_factory() as session:
            session.add(AgentHealth(component=component, status=status, detail=detail))
            session.commit()

    def record_run(self, cycle: str, status: str) -> None:
        _, session_factory = get_database()
        with session_factory() as session:
            session.add(AgentRun(cycle=cycle, status=status))
            session.commit()
