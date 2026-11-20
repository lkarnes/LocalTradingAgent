from __future__ import annotations

from typing import Protocol

from app.trading import Order


class UnsupportedBrokerError(RuntimeError):
    pass


class BrokerAdapter(Protocol):
    async def get_status(self) -> dict: ...
    async def get_positions(self) -> list[dict]: ...
    async def submit_order(self, order: Order) -> dict: ...
    async def cancel_order(self, broker_order_id: str) -> dict: ...


class UnconfiguredBroker:
    """Explicitly unavailable adapter; never silently substitutes paper behavior."""

    async def get_status(self) -> dict:
        return {"connected": False, "reason": "No broker configured"}

    async def get_positions(self) -> list[dict]:
        return []

    async def submit_order(self, order: Order) -> dict:
        raise UnsupportedBrokerError("Live broker is not configured")

    async def cancel_order(self, broker_order_id: str) -> dict:
        raise UnsupportedBrokerError("Live broker is not configured")
