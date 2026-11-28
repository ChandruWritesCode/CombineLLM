"""User-entered model capabilities survive settings edits without credential exposure."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_capability_hints_round_trip_and_validate():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        body = {
            "name": "Assistant",
            "kind": "compatible",
            "model": "sample",
            "base_url": "http://localhost:9999/v1",
            "api_key": "private-key",
            "context_limit_chars": 24000,
            "task_tags": ["code", "analysis"],
        }
        created = client.post("/api/v1/models", json=body)
        assert created.status_code == 201
        model = created.json()
        assert model["context_limit_chars"] == 24000
        assert model["task_tags"] == ["code", "analysis"]
        assert "private-key" not in created.text
        assert "private-key" not in client.get("/api/v1/models").text

        model_id = model["id"]
        changed = client.put(
            f"/api/v1/models/{model_id}",
            json={**body, "api_key": None, "task_tags": ["writing"]},
        )
        assert changed.status_code == 200
        assert changed.json()["task_tags"] == ["writing"]
        assert changed.json()["has_key"] is True

        for invalid in (
            {**body, "task_tags": ["code", "code"]},
            {**body, "task_tags": ["search"]},
            {**body, "context_limit_chars": 999},
        ):
            assert client.post("/api/v1/models", json=invalid).status_code == 422
