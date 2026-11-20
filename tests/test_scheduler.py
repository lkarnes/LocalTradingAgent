import asyncio

import pytest

from app.scheduler import AgentScheduler


@pytest.mark.asyncio
async def test_scheduler_does_not_overlap():
    scheduler = AgentScheduler()
    release = asyncio.Event()
    async def slow():
        await release.wait()
        return "done"
    first = asyncio.create_task(scheduler.run_once("cycle", slow()))
    await asyncio.sleep(0)
    second = await scheduler.run_once("cycle", slow())
    assert second["status"] == "skipped"
    release.set()
    await first
