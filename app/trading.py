from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Protocol

from app.config import RiskProfile


class OrderAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Order:
    symbol: str
    side: OrderAction
    quantity: float
    quote_price: float
    idempotency_key: str
    is_exit: bool = False


@dataclass
class RiskResult:
    allowed: bool
    reason: str = ""
    effects: dict | None = None


class BrokerAdapter(Protocol):
    def submit_order(self, order: Order) -> dict: ...
    def cancel_order(self, broker_order_id: str) -> dict: ...


class RiskManager:
    def __init__(self, profile: RiskProfile, cash: float, kill_switch: bool = False):
        self.profile = profile
        self.cash = cash
        self.kill_switch = kill_switch
        self.pending_by_symbol: dict[str, float] = {}
        self.daily_purchases = 0
        self.daily_purchase_value = 0.0
        self.new_positions = 0
        self.daily_loss_percent = 0.0
        self.open_positions = 0

    def evaluate(self, order: Order, fresh_quote: bool,
                 quote_age_seconds: int, seen_keys: set[str]) -> RiskResult:
        if order.is_exit:
            if not fresh_quote:
                return RiskResult(False, "Quote unavailable for protective exit")
            return RiskResult(True)
        if self.kill_switch:
            return RiskResult(False, "Emergency kill switch active")
        if not fresh_quote:
            return RiskResult(False, "Market data is stale or unavailable")
        if quote_age_seconds > self.profile.max_quote_age_seconds:
            return RiskResult(False, "Quote freshness limit exceeded")
        if order.idempotency_key in seen_keys:
            return RiskResult(False, "Duplicate order")
        if order.quantity <= 0 or order.quote_price <= 0:
            return RiskResult(False, "Invalid quantity or price")
        if order.quote_price < self.profile.min_stock_price:
            return RiskResult(False, "Stock price below safety minimum")
        value = order.quantity * order.quote_price
        if value > self.profile.max_order_value:
            return RiskResult(False, "Order exceeds maximum order value")
        if value > self.profile.max_position_percent / 100 * (self.cash + value):
            return RiskResult(False, "Order exceeds maximum position size")
        if self.daily_purchases >= self.profile.max_new_positions_per_day:
            return RiskResult(False, "Daily new-position limit reached")
        if self.daily_loss_percent >= self.profile.max_daily_loss_percent:
            return RiskResult(False, "Daily loss limit reached")
        if self.pending_by_symbol.get(order.symbol, 0) + value > self.profile.max_order_value:
            return RiskResult(False, "Pending orders exceed order limit")
        if value > self.cash:
            return RiskResult(False, "Insufficient buying power")
        if self.open_positions >= self.profile.max_open_positions:
            return RiskResult(False, "Maximum open positions reached")
        return RiskResult(True)


class PaperPortfolio:
    def __init__(self, initial_cash: float, slippage_bps: int = 10, commission: float = 0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, dict] = {}
        self.slippage_bps = slippage_bps
        self.commission = commission
        self.seen_keys: set[str] = set()
        self.realized_pnl = 0.0
        self.stop_orders: dict[str, dict] = {}

    def submit(self, order: Order) -> dict:
        if order.idempotency_key in self.seen_keys:
            return {"status": "rejected", "reason": "duplicate_order"}
        slippage = order.quote_price * self.slippage_bps / 10_000
        fill = order.quote_price + slippage if order.side == OrderAction.BUY else order.quote_price - slippage
        value = fill * order.quantity
        if order.side == OrderAction.BUY:
            if value + self.commission > self.cash:
                return {"status": "rejected", "reason": "insufficient_cash"}
            self.seen_keys.add(order.idempotency_key)
            self.cash -= value + self.commission
            pos = self.positions.setdefault(order.symbol, {"quantity": 0.0, "average_cost": 0.0})
            old_quantity = pos["quantity"]
            pos["average_cost"] = ((pos["average_cost"] * old_quantity) + value) / (old_quantity + order.quantity)
            pos["quantity"] += order.quantity
        else:
            pos = self.positions.get(order.symbol)
            if not pos or pos["quantity"] + 1e-9 < order.quantity:
                return {"status": "rejected", "reason": "insufficient_shares"}
            self.seen_keys.add(order.idempotency_key)
            proceeds = value - self.commission
            self.realized_pnl += proceeds - (pos["average_cost"] * order.quantity)
            pos["quantity"] -= order.quantity
            self.cash += proceeds
            if pos["quantity"] < 1e-9:
                del self.positions[order.symbol]
        return {"status": "filled", "symbol": order.symbol, "quantity": order.quantity,
                "average_fill": round(fill, 6), "timestamp": datetime.now(timezone.utc).isoformat()}

    def market_value(self, quotes: dict[str, float]) -> float:
        return sum(position["quantity"] * quotes.get(symbol, position["average_cost"])
                   for symbol, position in self.positions.items())

    def total_value(self, quotes: dict[str, float]) -> float:
        return self.cash + self.market_value(quotes)

    def to_state(self) -> dict:
        return {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "positions": self.positions,
            "slippage_bps": self.slippage_bps,
            "commission": self.commission,
            "seen_keys": sorted(self.seen_keys),
            "realized_pnl": self.realized_pnl,
            "stop_orders": self.stop_orders,
        }

    def restore_state(self, state: dict) -> None:
        self.initial_cash = float(state.get("initial_cash", self.initial_cash))
        self.cash = float(state.get("cash", self.initial_cash))
        self.positions = dict(state.get("positions", {}))
        self.slippage_bps = int(state.get("slippage_bps", self.slippage_bps))
        self.commission = float(state.get("commission", self.commission))
        self.seen_keys = set(state.get("seen_keys", []))
        self.realized_pnl = float(state.get("realized_pnl", 0))
        self.stop_orders = dict(state.get("stop_orders", {}))

    def place_stop(self, symbol: str, stop_price: float) -> dict:
        position = self.positions.get(symbol)
        if not position:
            return {"status": "rejected", "reason": "No paper position"}
        stop = {
            "symbol": symbol,
            "quantity": position["quantity"],
            "stop_price": round(stop_price, 6),
            "status": "open",
        }
        self.stop_orders[symbol] = stop
        return {"status": "placed", **stop}

    def audit_stops(self) -> list[dict]:
        audits = []
        for symbol, position in list(self.positions.items()):
            stop = self.stop_orders.get(symbol)
            if stop is None:
                audits.append({"symbol": symbol, "status": "missing"})
            elif stop["quantity"] != position["quantity"]:
                audits.append({"symbol": symbol, "status": "quantity_mismatch",
                               "stop": stop["quantity"], "position": position["quantity"]})
            else:
                audits.append({"symbol": symbol, "status": "confirmed",
                               "stop_price": stop["stop_price"]})
        return audits


class ExecutionRouter:
    def __init__(self, app, paper: PaperPortfolio, live_broker: BrokerAdapter | None = None):
        self.app = app
        self.paper = paper
        self.live_broker = live_broker

    def submit(self, order: Order, risk: RiskResult) -> dict:
        if not risk.allowed:
            return {"status": "rejected", "reason": risk.reason}
        if self.app.paper_trading:
            return self.paper.submit(order)
        if not self.app.live_trading_enabled:
            raise RuntimeError("Live execution is disabled")
        if self.app.operating_mode != "live":
            raise RuntimeError("Approval or research mode cannot submit live orders")
        if not self.live_broker:
            raise RuntimeError("No live broker adapter is configured")
        return self.live_broker.submit_order(order)
