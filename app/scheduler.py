from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler


class AgentScheduler:
    def __init__(self, timezone: str = "America/Los_Angeles"):
        self.scheduler = AsyncIOScheduler(timezone=timezone)
        self._locks: set[str] = set()

    async def run_once(self, name: str, coroutine):
        if name in self._locks:
            close = getattr(coroutine, "close", None)
            if close:
                close()
            return {"status": "skipped", "reason": "cycle already running"}
        self._locks.add(name)
        try:
            return await coroutine
        finally:
            self._locks.remove(name)

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
