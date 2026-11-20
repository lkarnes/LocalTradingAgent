from __future__ import annotations

import asyncio
import json
import shutil
import sys
import getpass
from pathlib import Path

from app.config import resolve_settings
from app.database import get_database
from app.ai import OllamaClient


def usage() -> None:
    print("""usage: trading-agent <command>
commands: setup configure doctor status run-once paper-status paper-reset
          backup restore report-daily report-weekly report-monthly
          export-trades live-readiness kill-switch storage-status storage-prune""")


def main() -> None:
    if len(sys.argv) < 2:
        usage()
        return
    command = sys.argv[1]
    if command in {"setup", "configure"}:
        setup()
    elif command == "doctor":
        print(json.dumps(doctor(), indent=2))
    elif command == "status":
        print(json.dumps(status(), indent=2))
    elif command == "backup":
        backup()
    elif command == "restore":
        restore(sys.argv[2] if len(sys.argv) > 2 else "")
    elif command == "kill-switch":
        Path("data").mkdir(exist_ok=True)
        Path("data/kill-switch").write_text("enabled\n", encoding="utf-8")
        print("Kill switch enabled")
    elif command == "export-trades":
        export_trades()
    elif command == "paper-status":
        print(json.dumps(paper_status(), indent=2))
    elif command == "paper-reset":
        env, _, _ = resolve_settings()
        from app.paper_store import PaperStore
        PaperStore().reset(env.paper_initial_capital)
        print("Paper account reset")
    elif command == "report-daily":
        from app.reporter import generate_daily_report
        print(json.dumps(generate_daily_report(), indent=2))
    elif command == "report-weekly":
        from app.reporter import generate_period_report
        print(json.dumps(generate_period_report(7), indent=2))
    elif command == "report-monthly":
        from app.reporter import generate_period_report
        print(json.dumps(generate_period_report(30), indent=2))
    elif command == "analytics":
        from app.database import DailyPerformance, SimulatedOrder, get_database
        from app.analytics import performance_metrics, paper_evaluation
        _, session_factory = get_database()
        with session_factory() as session:
            rows = session.query(DailyPerformance).order_by(DailyPerformance.report_date).all()
            returns = [row.daily_return or 0 for row in rows]
            trades = session.query(SimulatedOrder).filter(SimulatedOrder.status == "filled").count()
        print(json.dumps({
            "metrics": performance_metrics(returns),
            "evaluation": paper_evaluation(len(rows), trades),
        }, indent=2))
    elif command == "run-once":
        from app.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        print(json.dumps({
            "market": pipeline.collect_market_data(),
            "news": pipeline.collect_news(),
            "analysis": pipeline.analyze_watchlist(),
        }, indent=2, default=str))
    elif command == "live-readiness":
        print(json.dumps(live_readiness(), indent=2))
    elif command == "storage-status":
        from app.storage import storage_status
        print(json.dumps(storage_status(), indent=2))
    elif command == "storage-prune":
        from app.storage import prune_database
        print(json.dumps(prune_database(), indent=2))
    else:
        usage()


def setup() -> None:
    print("Local AI Trading Agent setup")
    if not Path(".env").exists():
        shutil.copy(".env.example", ".env")
        print("Created .env from safe defaults")
    mode = input("Initial mode [research/paper/approval/live] (research): ").strip().lower() or "research"
    if mode not in {"research", "paper", "approval", "live"}:
        raise ValueError("Invalid operating mode")
    if mode == "live":
        confirm = input("Live trading is blocked unless explicitly verified. Enable live authorization? [no]: ").strip().lower()
        if confirm != "yes":
            mode = "approval"
            print("Live mode kept disabled; selected approval mode.")
    timezone = input("Timezone (America/Los_Angeles): ").strip() or "America/Los_Angeles"
    model = input("Ollama model (qwen3:4b): ").strip() or "qwen3:4b"
    lightweight_model = input("Lightweight Ollama model (qwen3:1.7b): ").strip() or "qwen3:1.7b"
    risk = input("Risk profile [conservative/balanced/aggressive] (balanced): ").strip() or "balanced"
    if risk not in {"conservative", "balanced", "aggressive"}:
        raise ValueError("Invalid risk profile")
    initial = input("Initial paper capital (5000): ").strip() or "5000"
    float(initial)
    cost_guard = input("Enforce no paid providers (yes/no) (yes): ").strip().lower() or "yes"
    if cost_guard not in {"yes", "no"}:
        raise ValueError("Cost guard must be yes or no")
    storage_limit = input("Maximum SQLite storage in GiB [10-100] (10): ").strip() or "10"
    storage_limit_value = float(storage_limit)
    if not 10 <= storage_limit_value <= 100:
        raise ValueError("Storage limit must be between 10 and 100 GiB")
    watchlist = input("Comma-separated watchlist (AAPL,MSFT,NVDA): ").strip() or "AAPL,MSFT,NVDA"
    env_path = Path(".env")
    lines = env_path.read_text(encoding="utf-8").splitlines()
    values = {
        "APP_TIMEZONE": timezone,
        "OLLAMA_MODEL": model,
        "OLLAMA_LIGHTWEIGHT_MODEL": lightweight_model,
        "RISK_PROFILE": risk,
        "PAPER_INITIAL_CAPITAL": initial,
        "DATA_STORAGE_LIMIT_GB": str(int(storage_limit_value)) if storage_limit_value.is_integer() else str(storage_limit_value),
        "COST_GUARD_ENABLED": "true" if cost_guard == "yes" else "false",
        "ALLOW_PAID_PROVIDERS": "false" if cost_guard == "yes" else "true",
        "TRADING_MODE": mode,
        "PAPER_TRADING": "true" if mode in {"research", "paper"} else "false",
        "LIVE_TRADING_ENABLED": "false",
        "REQUIRE_MANUAL_APPROVAL": "true",
    }
    if mode == "approval":
        values["PAPER_TRADING"] = "false"
    if mode == "live":
        values["PAPER_TRADING"] = "false"
        values["LIVE_TRADING_ENABLED"] = "false"
        values["TRADING_MODE"] = "approval"
    keys = set(values)
    updated = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in keys:
            updated.append(f"{key}={values[key]}")
            keys.remove(key)
        else:
            updated.append(line)
    updated.extend(f"{key}={values[key]}" for key in sorted(keys))
    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    env_path.chmod(0o600)
    watch_path = Path("config/watchlist.yaml")
    symbols = [item.strip().upper() for item in watchlist.split(",") if item.strip()]
    watch_path.write_text("symbols: [" + ", ".join(symbols) + "]\n", encoding="utf-8")
    print("Configuration written. Run 'make doctor' to validate it.")


def doctor() -> dict:
    try:
        env, app, profiles = resolve_settings()
    except Exception as exc:
        return {"status": "error", "configuration": str(exc)}
    try:
        get_database()
        database_ok = True
    except Exception as exc:
        database_ok = False
    async def check():
        primary = await OllamaClient(
            env.ollama_base_url,
            env.ollama_model,
            env.ollama_timeout,
            env.ollama_keep_alive,
            env.ollama_context_size,
            env.ollama_temperature,
            env.ollama_num_parallel,
        ).availability()
        lightweight = await OllamaClient(
            env.ollama_base_url,
            env.ollama_lightweight_model,
            env.ollama_timeout,
            env.ollama_keep_alive,
            min(env.ollama_context_size, 2048),
            0,
            1,
        ).availability()
        return primary, lightweight
    (ollama_ok, ollama_detail), (lightweight_ok, lightweight_detail) = asyncio.run(check())
    return {
        "status": "healthy" if database_ok and ollama_ok else "degraded",
        "configuration": "valid",
        "database": "healthy" if database_ok else "unavailable",
        "ollama": ollama_detail,
        "ollama_lightweight": lightweight_detail,
        "lightweight_model_available": lightweight_ok,
        "mode": app.operating_mode,
        "paper_trading": app.paper_trading,
        "live_trading_enabled": app.live_trading_enabled,
        "cost_guard": "enabled" if env.cost_guard_enabled else "disabled",
        "paid_providers": "allowed" if env.allow_paid_providers else "blocked",
        "broker_provider": env.broker_provider,
    }


def status() -> dict:
    env, app, profiles = resolve_settings()
    return {"mode": app.operating_mode, "paper_trading": app.paper_trading,
            "live_trading_enabled": app.live_trading_enabled,
            "model": env.ollama_model, "risk_profile": env.risk_profile,
            "cost_guard": env.cost_guard_enabled,
            "paid_providers_allowed": env.allow_paid_providers,
            "broker_provider": env.broker_provider}


def backup() -> None:
    from app.storage import create_database_backup
    print(create_database_backup()["backup"])


def restore(path: str) -> None:
    import sqlite3
    source = Path(path)
    if not path or not source.is_file():
        print("Restore failed: provide an existing backup database with trading-agent restore /path/to/trading.db")
        return
    env, _, _ = resolve_settings()
    destination = Path(env.database_url.replace("sqlite:///./", ""))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db:
        if source_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            print("Restore failed: backup database failed integrity check")
            return
    destination.unlink(missing_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as dest_db:
        source_db.backup(dest_db)
    print(f"Restored database to {destination}")


def export_trades() -> None:
    engine, session_factory = get_database()
    from app.database import SimulatedOrder
    import csv
    with session_factory() as session:
        rows = session.query(SimulatedOrder).all()
    Path("reports").mkdir(exist_ok=True)
    output = Path("reports/trades.csv")
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "created_at", "symbol", "side", "quantity", "status", "filled_quantity", "average_fill"])
        for row in rows:
            writer.writerow([row.id, row.created_at, row.symbol, row.side, row.quantity,
                             row.status, row.filled_quantity, row.average_fill])
    print(output)


def live_readiness() -> dict:
    env, app, profiles = resolve_settings()
    missing = []
    if app.paper_trading:
        missing.append("PAPER_TRADING must be false")
    if not env.live_trading_enabled:
        missing.append("LIVE_TRADING_ENABLED=true is required")
    if app.operating_mode not in ("approval", "live"):
        missing.append("TRADING_MODE must be approval or live")
    if env.broker_provider in ("", "none"):
        missing.append("A supported broker provider is required")
    if app.require_manual_approval is False and app.operating_mode == "approval":
        missing.append("Approval mode requires REQUIRE_MANUAL_APPROVAL=true")
    return {"ready": not missing, "checks": missing,
            "broker_submission": "disabled until official supported credentials and adapter verification"}


def paper_status() -> dict:
    env, _, _ = resolve_settings()
    from app.paper_store import PaperStore
    from app.trading import PaperPortfolio
    portfolio = PaperStore().load(PaperPortfolio(
        env.paper_initial_capital,
        env.paper_slippage_bps,
        env.paper_commission_per_order,
    ))
    return portfolio.to_state()


if __name__ == "__main__":
    main()
