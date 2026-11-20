from pathlib import Path
import shutil

from app.database import get_database


def test_database_backup_and_restore_copy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / ".env").write_text(
        "DATABASE_URL=sqlite:///./data/trading.db\n",
        encoding="utf-8",
    )
    engine, session_factory = get_database()
    engine.dispose()
    source = tmp_path / "data" / "trading.db"
    assert source.exists()
    backup = tmp_path / "backup.db"
    shutil.copy2(source, backup)
    source.unlink()
    shutil.copy2(backup, source)
    assert source.exists()
