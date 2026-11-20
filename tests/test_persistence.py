from app.paper_store import PaperStore
from app.trading import Order, OrderAction, PaperPortfolio


def test_paper_portfolio_persists_across_restart(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.yaml").write_text(
        "timezone: America/Los_Angeles\noperating_mode: paper\npaper_trading: true\n"
        "live_trading_enabled: false\nrequire_manual_approval: true\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "risk_profiles.yaml").write_text(
        "balanced:\n"
        "  max_position_percent: 5\n"
        "  max_deployed_capital_percent: 60\n"
        "  max_risk_per_trade_percent: 0.5\n"
        "  max_daily_loss_percent: 1\n"
        "  max_new_positions_per_day: 3\n"
        "  max_order_value: 250\n",
        encoding="utf-8",
    )
    portfolio = PaperPortfolio(5000)
    result = portfolio.submit(Order("AAPL", OrderAction.BUY, 1, 100, "persist-key"))
    assert result["status"] == "filled"
    PaperStore("test").save(portfolio)

    restarted = PaperStore("test").load(PaperPortfolio(5000))
    assert "AAPL" in restarted.positions
    assert restarted.cash < restarted.initial_cash


def test_rejected_fill_does_not_poison_retry_key():
    portfolio = PaperPortfolio(100)
    order = Order("AAPL", OrderAction.BUY, 10, 100, "retry-key")
    result = portfolio.submit(order)
    assert result["status"] == "rejected"
    assert "retry-key" not in portfolio.seen_keys
