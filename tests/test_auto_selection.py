"""Automatic choice makes one simulated provider request per saved turn."""

import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.policies import cool_down
from app.providers.base import ProviderEvent
from app.schemas import Usage
from app.storage import Store


class FakeModel:
    calls = []

    def __init__(self, config, key):
        self.name = "compatible"
        self.model = config["model"]

    async def stream(self, request):
        self.calls.append(self.model)
        yield ProviderEvent("delta", text=self.model + " answered")
        yield ProviderEvent("done", finish_reason="STOP", usage=Usage(total_tokens=12))


def wait_for_answer(client, cid):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        answer = client.get(f"/api/v1/conversations/{cid}").json()["messages"][-1]
        if answer["status"] != "streaming":
            return answer
        time.sleep(0.01)
    raise AssertionError("Answer did not finish")


def test_auto_choice_is_one_request_and_attributed(monkeypatch):
    FakeModel.calls = []
    monkeypatch.setattr("app.model_api.APIProvider", FakeModel)
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        ids = {}
        for name, rate in (("expensive", "10"), ("cheap", "1")):
            response = client.post(
                "/api/v1/models",
                json={
                    "name": name,
                    "kind": "compatible",
                    "model": name,
                    "base_url": "http://localhost:9999/v1",
                    "input_price_per_million": rate,
                    "output_price_per_million": rate,
                },
            )
            ids[name] = response.json()["id"]
        client.put("/api/v1/settings", json={"default_model_id": ids["expensive"]})
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        path = f"/api/v1/conversations/{cid}/messages"
        response = client.post(path, json={"content": "Question", "auto_select": True})
        assert response.status_code == 202
        answer = wait_for_answer(client, cid)
        assert answer["content"] == "cheap answered"
        assert answer["model_id"] == ids["cheap"]
        assert answer["selection_mode"] == "automatic"
        assert "Provider quota" in answer["selection_reason"]
        assert client.get(f"/api/v1/conversations/{cid}").json()["model_id"] == ids["cheap"]
        assert FakeModel.calls == ["cheap"]
        assert client.get("/api/v1/usage").json()["requests"] == 1
        assert len(answer["attempts"]) == 1


def test_auto_preflight_rejects_conflicts_and_no_eligible_model(monkeypatch):
    FakeModel.calls = []
    monkeypatch.setattr("app.model_api.APIProvider", FakeModel)
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        mid = client.post(
            "/api/v1/models",
            json={
                "name": "Cloud",
                "kind": "compatible",
                "model": "cloud",
                "base_url": "https://example.com/v1",
            },
        ).json()["id"]
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        path = f"/api/v1/conversations/{cid}/messages"
        for body in [
            {"model_id": mid},
            {"fallback": True},
            {"coordination": {"mode": "review", "collaborator_model_id": mid}},
        ]:
            assert (
                client.post(
                    path,
                    json={
                        "content": "Question",
                        "auto_select": True,
                        **body,
                    },
                ).status_code
                == 422
            )
        assert (
            client.post(
                path,
                json={
                    "content": "Question",
                    "auto_select": True,
                    "local_only": True,
                },
            ).status_code
            == 422
        )
        cool_down(client.app.state.store, "model:" + mid, 60)
        assert (
            client.post(
                path,
                json={
                    "content": "Question",
                    "auto_select": True,
                },
            ).status_code
            == 422
        )
        assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
        assert client.get("/api/v1/usage").json()["requests"] == 0
        assert FakeModel.calls == []


def test_schema_seven_preserves_conversations(tmp_path):
    path = str(tmp_path / "migration.sqlite3")
    store = Store(path)
    cid = store.create("Keep this")["id"]
    with store.connect() as db:
        db.execute("ALTER TABLE messages DROP COLUMN selection_mode")
        db.execute("ALTER TABLE messages DROP COLUMN selection_reason")
        db.execute("PRAGMA user_version=6")
    upgraded = Store(path)
    assert upgraded.get(cid)["title"] == "Keep this"
    with upgraded.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
