import pytest


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Never read or change the developer's chat database during tests."""
    monkeypatch.setenv("COMBINELLM_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
