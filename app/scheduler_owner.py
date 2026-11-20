from __future__ import annotations

import asyncio
from datetime import datetime

from app.config import resolve_settings
from app.scheduler import AgentScheduler
from app.pipeline import ResearchPipeline
from app.reporter import generate_daily_report
from app.storage import create_database_backup, prune_database
from app.active_scan import ActivePositionScan
from app.market import is_nyse_session_day
from zoneinfo import ZoneInfo


async def main():
    env, app, profiles = resolve_settings()
    agent_scheduler = AgentScheduler(env.app_timezone)
    pipeline = ResearchPipeline()

    schedule = __import__("yaml").safe_load(open("config/schedule.yaml", encoding="utf-8")) or {}
    news_minutes = int(schedule.get("news", {}).get("interval_minutes", 15))
    market_minutes = int(schedule.get("market_data", {}).get("interval_minutes", 15))
    analysis_minutes = int(schedule.get("analysis", {}).get("interval_minutes", 60))
    maintenance = schedule.get("maintenance", {})
    report_hour, report_minute = (maintenance.get("daily_report_time", "16:15").split(":") + ["0"])[:2]
    backup_hour, backup_minute = (maintenance.get("database_backup_time", "02:00").split(":") + ["0"])[:2]
    storage_hour, storage_minute = (maintenance.get("storage_prune_time", "03:00").split(":") + ["0"])[:2]

    async def market_collection_job():
        market = await agent_scheduler.run_once("market", asyncio.to_thread(pipeline.collect_market_data))
        failures = market.get("failures", []) if isinstance(market, dict) else []
        pipeline.record_health("market_data", "degraded" if failures else "healthy", str(market))

    async def news_collection_job():
        news = await agent_scheduler.run_once("news", asyncio.to_thread(pipeline.collect_news))
        pipeline.record_health("news", "healthy", str(news))

    async def analysis_job():
        result = await agent_scheduler.run_once("analysis", asyncio.to_thread(pipeline.analyze_watchlist))
        pipeline.record_run("analysis", "completed")
        pipeline.record_health("ollama", "unknown", "Ollama analysis is separate from Python screening")

    async def report_job():
        generate_daily_report()
        pipeline.record_run("daily_report", "completed")

    async def storage_job():
        prune_database()
        pipeline.record_run("storage_prune", "completed")

    async def backup_job():
        create_database_backup()
        pipeline.record_run("database_backup", "completed")

    async def intraday_scan_job(scan_name: str):
        if not is_nyse_session_day():
            pipeline.record_run(f"scan:{scan_name}", "skipped_non_trading_day")
            return
        await agent_scheduler.run_once(
            f"intraday:{scan_name}",
            asyncio.to_thread(ActivePositionScan().run, scan_name),
        )

    timezone_name = schedule.get("timezone", env.app_timezone)
    agent_scheduler.scheduler.configure(timezone=timezone_name)
    intraday = schedule.get("intraday", {})
    if intraday.get("enabled", False):
        nyse_zone = ZoneInfo("America/New_York")
        local_zone = ZoneInfo(timezone_name)
        for index, hhmm in enumerate(intraday.get("scans", [])):
            hour_text, minute_text = hhmm.split(":")
            nyse_time = datetime.now(nyse_zone).replace(
                hour=int(hour_text),
                minute=int(minute_text),
                second=0,
                microsecond=0,
            )
            local_time = nyse_time.astimezone(local_zone)
            scan_name = "premarket" if hhmm == "08:15" else f"scan_{index + 1}_{hhmm}"
            agent_scheduler.scheduler.add_job(
                intraday_scan_job,
                "cron",
                args=[scan_name],
                hour=local_time.hour,
                minute=local_time.minute,
                id=f"intraday_{scan_name}",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
    agent_scheduler.scheduler.add_job(market_collection_job, "interval", minutes=market_minutes,
                                     id="market_collection", max_instances=1, coalesce=True,
                                     misfire_grace_time=300, next_run_time=datetime.now())
    agent_scheduler.scheduler.add_job(news_collection_job, "interval", minutes=news_minutes,
                                     id="news_collection", max_instances=1, coalesce=True,
                                     misfire_grace_time=300, next_run_time=datetime.now())
    agent_scheduler.scheduler.add_job(analysis_job, "interval", minutes=analysis_minutes,
                                     id="analysis", max_instances=1, coalesce=True,
                                     misfire_grace_time=300, next_run_time=datetime.now())
    agent_scheduler.scheduler.add_job(report_job, "cron", hour=int(report_hour), minute=int(report_minute),
                                     id="daily_report", max_instances=1, coalesce=True,
                                     misfire_grace_time=3600)
    agent_scheduler.scheduler.add_job(storage_job, "cron", hour=int(storage_hour), minute=int(storage_minute),
                                     id="storage_prune", max_instances=1, coalesce=True,
                                     misfire_grace_time=3600)
    agent_scheduler.scheduler.add_job(backup_job, "cron", hour=int(backup_hour), minute=int(backup_minute),
                                     id="database_backup", max_instances=1, coalesce=True,
                                     misfire_grace_time=3600)
    agent_scheduler.start()
    print("Scheduler started; dashboard should not start a second scheduler")
    try:
        await asyncio.Event().wait()
    finally:
        agent_scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
