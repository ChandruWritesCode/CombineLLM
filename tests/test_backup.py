import sqlite3

import pytest

from app.storage import Store
from scripts.backup import main


def test_backup_contains_committed_data_and_refuses_overwrite(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "backup.sqlite3"
    store = Store(str(source))
    store.create("Keep this conversation")
    monkeypatch.setenv("COMBINELLM_DATABASE_PATH", str(source))
    monkeypatch.setattr("sys.argv", ["backup", str(destination)])
    main()
    with sqlite3.connect(destination) as db:
        assert (
            db.execute("SELECT title FROM conversations").fetchone()[0] == "Keep this conversation"
        )
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
    with pytest.raises(FileExistsError):
        main()


def test_backup_restores_encrypted_credentials(tmp_path, monkeypatch):
    from app.connections import Connection, Connections

    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "backup.sqlite3"
    registry = Connections(Store(str(source)))
    model = registry.save(Connection(name="Test", kind="openai", model="test", api_key="secret"))
    monkeypatch.setenv("COMBINELLM_DATABASE_PATH", str(source))
    monkeypatch.setattr("sys.argv", ["backup", str(destination)])
    main()
    restored = Connections(Store(str(destination)))
    assert restored.secret(model["id"]) == "secret"
    assert destination.with_suffix(".key").stat().st_mode & 0o777 == 0o600
