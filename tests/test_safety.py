import pytest
from pydantic import ValidationError

from app.config import AppSettings, RiskProfile
from app.trading import ExecutionRouter, Order, OrderAction, PaperPortfolio, RiskManager


@pytest.fixture
def balanced_profile():
    return RiskProfile(
        max_position_percent=5,
        max_deployed_capital_percent=60,
        max_risk_per_trade_percent=0.5,
        max_daily_loss_percent=1,
        max_new_positions_per_day=3,
        max_order_value=250,
    )


def test_paper_router_never_calls_live_broker(balanced_profile):
    paper = PaperPortfolio(5000)
    app = AppSettings(paper_trading=True, operating_mode="paper")
    live_calls = []
    class Broker:
        def submit_order(self, order):
            live_calls.append(order)
            return {"status": "unexpected"}
    router = ExecutionRouter(app, paper, Broker())
    result = router.submit(
        Order("AAPL", OrderAction.BUY, 1, 100, "paper-key"),
        type("Risk", (), {"allowed": True, "reason": ""})(),
    )
    assert result["status"] == "filled"
    assert live_calls == []


def test_live_mode_requires_authorization():
    with pytest.raises(ValidationError):
        AppSettings(paper_trading=False, live_trading_enabled=False, operating_mode="live")


def test_oversized_order_blocked(balanced_profile):
    risk = RiskManager(balanced_profile, cash=5000)
    result = risk.evaluate(
        Order("AAPL", OrderAction.BUY, 10, 100, "oversized"),
        fresh_quote=True,
        quote_age_seconds=1,
        seen_keys=set(),
    )
    assert not result.allowed
    assert "maximum" in result.reason.lower()


def test_daily_loss_blocks_purchase(balanced_profile):
    risk = RiskManager(balanced_profile, cash=5000)
    risk.daily_loss_percent = 1
    result = risk.evaluate(
        Order("MSFT", OrderAction.BUY, 1, 100, "loss-lock"),
        fresh_quote=True,
        quote_age_seconds=1,
        seen_keys=set(),
    )
    assert not result.allowed


def test_protective_exit_remains_possible(balanced_profile):
    risk = RiskManager(balanced_profile, cash=5000)
    risk.kill_switch = True
    result = risk.evaluate(
        Order("AAPL", OrderAction.SELL, 1, 100, "exit", is_exit=True),
        fresh_quote=True,
        quote_age_seconds=1,
        seen_keys=set(),
    )
    assert result.allowed


def test_stale_quote_blocks_purchase(balanced_profile):
    risk = RiskManager(balanced_profile, cash=5000)
    result = risk.evaluate(
        Order("AAPL", OrderAction.BUY, 1, 100, "stale"),
        fresh_quote=False,
        quote_age_seconds=999,
        seen_keys=set(),
    )
    assert not result.allowed


def test_duplicate_order_blocked(balanced_profile):
    risk = RiskManager(balanced_profile, cash=5000)
    result = risk.evaluate(
        Order("AAPL", OrderAction.BUY, 1, 100, "duplicate"),
        fresh_quote=True,
        quote_age_seconds=1,
        seen_keys={"duplicate"},
    )
    assert not result.allowed


def test_paper_pnl_calculation():
    paper = PaperPortfolio(5000)
    buy = paper.submit(Order("AAPL", OrderAction.BUY, 10, 100, "buy"))
    assert buy["status"] == "filled"
    sell = paper.submit(Order("AAPL", OrderAction.SELL, 10, 120, "sell"))
    assert sell["status"] == "filled"
    assert paper.realized_pnl == pytest.approx(197.8, rel=1e-2)
    assert paper.cash == pytest.approx(5188.8, rel=1e-2)
