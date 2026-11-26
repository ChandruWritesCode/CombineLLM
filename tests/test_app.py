import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_health_and_documented_contract():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        schema = client.get("/openapi.json").json()
        assert "/api/v1/health" in schema["paths"]
        assert client.get("/docs").status_code == 200


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("COMBINELLM_APP_NAME", "My local workspace")
    monkeypatch.setenv("COMBINELLM_ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1").json()["name"] == "My local workspace"
    assert settings.environment == "test"


def test_invalid_environment_fails_early(monkeypatch):
    monkeypatch.setenv("COMBINELLM_ENVIRONMENT", "typo")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
