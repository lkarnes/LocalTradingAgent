import pytest
from pydantic import ValidationError

from app.config import Settings
from app.news import fetch_finnhub


def test_paid_providers_rejected_under_cost_guard():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            cost_guard_enabled=True,
            allow_paid_providers=True,
        )


def test_cost_guard_blocks_paid_finnhub():
    assert fetch_finnhub("test-key", "AAPL", allow_paid=False) == []


def test_default_cost_guard_values():
    settings = Settings(_env_file=None)
    assert settings.cost_guard_enabled is True
    assert settings.allow_paid_providers is False
    assert settings.broker_provider == "none"
