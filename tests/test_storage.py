from app.config import Settings
from app.storage import database_size_bytes, storage_status


def test_storage_limit_range_is_validated():
    for value in (10, 25, 100):
        settings = Settings(_env_file=None, data_storage_limit_gb=value)
        assert settings.data_storage_limit_gb == value


def test_storage_limit_below_range_rejected():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        Settings(_env_file=None, data_storage_limit_gb=9)


def test_storage_status_shape(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-only-password")
    status = storage_status(10)
    assert "database_size_gb" in status
    assert "within_limit" in status
    assert status["storage_limit_gb"] == 10
