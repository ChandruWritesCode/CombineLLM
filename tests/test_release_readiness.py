"""Local diagnostics and verified, non-overwriting restore use isolated data."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.connections import Connection, Connections
from app.main import create_app
from app.storage import Store
from scripts.backup import main as backup_main
from scripts.restore import restore_backup, verify_backup


def test_diagnostics_report_local_state_without_secrets():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        model = client.post(
            "/api/v1/models",
            json={
                "name": "Private",
                "kind": "openai",
                "model": "example-model",
                "api_key": "secret-key",
            },
        )
        assert model.status_code == 201
        client.post("/api/v1/conversations", json={"title": "Saved"})
        report = client.get("/api/v1/diagnostics")
        assert report.status_code == 200
        assert report.json() == {
            "storage": "ready",
            "schema_version": 8,
            "conversations": 1,
            "model_connections": 1,
            "enabled_models": 1,
            "credential_key_present": True,
            "active_generations": 0,
            "cloud_availability": "not_checked",
        }
        assert "secret-key" not in report.text
        assert "test.sqlite3" not in report.text
        assert client.get("/api/v1/usage").json()["requests"] == 0
        guide = client.get("/guide/operations")
        assert guide.status_code == 200
        assert "matching key" in guide.text


def test_restore_verifies_key_and_never_overwrites(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "saved.sqlite3"
    destination = tmp_path / "restored.sqlite3"
    registry = Connections(Store(str(source)))
    model = registry.save(
        Connection(name="Private", kind="openai", model="example", api_key="secret")
    )
    registry.store.create("Keep me")
    monkeypatch.setenv("COMBINELLM_DATABASE_PATH", str(source))
    monkeypatch.setattr("sys.argv", ["backup", str(backup)])
    backup_main()
    assert verify_backup(backup) == {"schema_version": 8, "credential_key_present": True}
    assert restore_backup(backup, destination)["schema_version"] == 8
    restored = Connections(Store(str(destination)))
    assert restored.secret(model["id"]) == "secret"
    assert restored.store.list()[0]["title"] == "Keep me"
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.with_suffix(".key").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        restore_backup(backup, destination)

    backup.with_suffix(".key").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="does not match"):
        restore_backup(backup, tmp_path / "not-created.sqlite3")
    assert not (tmp_path / "not-created.sqlite3").exists()


def test_restore_rejects_non_database(tmp_path):
    fake = tmp_path / "fake.sqlite3"
    fake.write_text("not sqlite")
    with pytest.raises(ValueError, match="readable"):
        restore_backup(fake, tmp_path / "destination.sqlite3")
    assert not (tmp_path / "destination.sqlite3").exists()
