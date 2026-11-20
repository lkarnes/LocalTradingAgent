from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import resolve_settings
from app.database import (
    AgentHealth,
    AgentRun,
    AIRun,
    BenchmarkSnapshot,
    MarketData,
    NewsAnalysis,
    NewsArticle,
    get_database,
)


GIB = 1024 ** 3


def database_paths() -> list[Path]:
    env, _, _ = resolve_settings()
    url = env.database_url
    if not url.startswith("sqlite"):
        return []
    raw = url.removeprefix("sqlite:///")
    if raw.startswith("./"):
        raw = raw[2:]
    main = Path(raw)
    return [main, Path(str(main) + "-wal"), Path(str(main) + "-shm")]


def database_size_bytes() -> int:
    return sum(path.stat().st_size for path in database_paths() if path.exists())


def prune_database(storage_limit_gb: float | None = None) -> dict:
    env, _, _ = resolve_settings()
    limit_gb = storage_limit_gb if storage_limit_gb is not None else env.data_storage_limit_gb
    if not 10 <= limit_gb <= 100:
        raise ValueError("DATA_STORAGE_LIMIT_GB must be between 10 and 100")

    limit_bytes = int(limit_gb * GIB)
    _, session_factory = get_database()
    deleted = {}

    with session_factory() as session:
        prunable = [
            ("market_data", MarketData, MarketData.retrieved_at),
            ("news_analysis", NewsAnalysis, NewsAnalysis.created_at),
            ("news_articles", NewsArticle, NewsArticle.retrieved_at),
            ("ai_runs", AIRun, AIRun.created_at),
            ("agent_runs", AgentRun, AgentRun.started_at),
            ("agent_health", AgentHealth, AgentHealth.checked_at),
            ("benchmark_snapshots", BenchmarkSnapshot, BenchmarkSnapshot.id),
        ]

        for name, model, timestamp_column in prunable:
            if database_size_bytes() <= int(limit_bytes * 0.90):
                break
            rows = session.query(model).order_by(timestamp_column.asc()).limit(1000).all()
            if not rows:
                continue
            row_ids = [row.id for row in rows]
            count = session.query(model).filter(model.id.in_(row_ids)).delete(synchronize_session=False)
            deleted[name] = deleted.get(name, 0) + count
            session.commit()

    # SQLite can retain free pages after deletes. VACUUM is the only operation
    # that deterministically compacts and reports the storage actually released.
    engine, _ = get_database()
    if hasattr(engine, "raw_connection"):
        with engine.raw_connection() as connection:
            connection.cursor().execute("VACUUM")

    size = database_size_bytes()
    return {
        "storage_limit_gb": limit_gb,
        "database_size_gb": round(size / GIB, 4),
        "within_limit": size <= limit_bytes,
        "deleted_by_table": deleted,
    }


def storage_status(storage_limit_gb: float | None = None) -> dict:
    env, _, _ = resolve_settings()
    limit_gb = storage_limit_gb if storage_limit_gb is not None else env.data_storage_limit_gb
    size = database_size_bytes()
    return {
        "storage_limit_gb": limit_gb,
        "database_size_gb": round(size / GIB, 4),
        "remaining_gb": round(max(limit_gb - size / GIB, 0), 4),
        "within_limit": size <= limit_gb * GIB,
    }


def create_database_backup(retention_count: int = 30) -> dict:
    env, _, _ = resolve_settings()
    url = env.database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("Automatic backup currently supports SQLite only")
    raw = url.removeprefix("sqlite:///")
    if raw.startswith("./"):
        raw = raw[2:]
    source = Path(raw)
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")

    target_dir = Path("backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = target_dir / f"trading-{timestamp}.db"

    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)
    with sqlite3.connect(destination) as backup_db:
        check = backup_db.execute("PRAGMA integrity_check").fetchone()[0]
    if check != "ok":
        destination.unlink(missing_ok=True)
        raise RuntimeError("SQLite backup failed integrity check")

    backups = sorted(target_dir.glob("trading-*.db"), key=lambda path: path.stat().st_mtime)
    removed = []
    while len(backups) > retention_count:
        oldest = backups.pop(0)
        oldest.unlink()
        removed.append(str(oldest))
    return {"backup": str(destination), "removed": removed, "integrity": "ok"}
