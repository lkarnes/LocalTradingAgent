from app.active_scan import ActivePositionScan
from app.trading import Order, OrderAction, PaperPortfolio


def test_paper_active_scan_creates_missing_stop(monkeypatch, tmp_path):
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
    (tmp_path / "config" / "strategy.yaml").write_text(
        "intraday_enabled: true\npremarket_enabled: true\nstop_loss_percent: 8\n"
        "catalyst_freshness_hours: 48\nminimum_reward_risk_ratio: 1.5\n"
        "max_positions_reviewed_per_scan: 5\nmax_entries_per_scan: 1\n"
        "max_exits_per_scan: 3\ncooldown_minutes_after_close: 120\n"
        "require_manual_approval: true\n",
        encoding="utf-8",
    )

    paper = PaperPortfolio(5000)
    paper.submit(Order("AAPL", OrderAction.BUY, 1, 100, "setup-key"))
    scan = ActivePositionScan(paper)

    monkeypatch.setattr(scan.market, "quote", lambda symbol: {
        "symbol": symbol,
        "price": 99,
        "source": "test",
        "retrieved_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
    })
    monkeypatch.setattr(scan.market, "quote_is_fresh", lambda quote: True)

    result = scan.run("test_scan")
    assert any(audit["stop_status"] == "placed" for audit in result["audits"])
    assert "AAPL" in paper.stop_orders
