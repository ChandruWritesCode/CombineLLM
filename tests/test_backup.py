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
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    with pytest.raises(FileExistsError):
        main()
