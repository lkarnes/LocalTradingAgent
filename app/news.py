from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import feedparser
import httpx


def deduplicate(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output = []
    for item in items:
        basis = f"{item.get('title', '')}|{item.get('url', '')}".strip().lower()
        digest = hashlib.sha256(basis.encode()).hexdigest()
        if digest not in seen:
            seen.add(digest)
            item["content_hash"] = digest
            output.append(item)
    return output


def fetch_rss(url: str, symbol: str | None = None, max_age_hours: int = 48) -> list[dict]:
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items = []
    for entry in feed.entries:
        published = getattr(entry, "published_parsed", None)
        dt = datetime(*published[:6], tzinfo=timezone.utc) if published else datetime.now(timezone.utc)
        if dt < cutoff:
            continue
        items.append({
            "symbol": symbol,
            "source": "rss",
            "url": getattr(entry, "link", ""),
            "title": getattr(entry, "title", ""),
            "published_at": dt,
        })
    return deduplicate(items)


def fetch_finnhub(api_key: str, symbol: str, allow_paid: bool = False) -> list[dict]:
    if not allow_paid:
        return []
    if not api_key:
        return []
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=7)
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "token": api_key},
            )
            response.raise_for_status()
            return deduplicate([
                {
                    "symbol": symbol,
                    "source": "finnhub",
                    "url": item.get("url", ""),
                    "title": item.get("headline", ""),
                    "published_at": datetime.fromtimestamp(item["datetime"], tz=timezone.utc)
                    if item.get("datetime") else datetime.now(timezone.utc),
                }
                for item in response.json()
            ])
    except httpx.HTTPError:
        return []
