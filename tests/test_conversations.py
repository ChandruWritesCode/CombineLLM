import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.chat import get_provider
from app.config import Settings
from app.main import create_app
from app.providers.base import ProviderError, ProviderEvent
from app.schemas import Usage
from app.storage import Store


class FakeProvider:
    name = "gemini"
    model = "test-model"

    def __init__(self, mode="success"):
        self.mode = mode
        self.requests = []
        self.closed = False

    async def stream(self, request):
        self.requests.append(request)
        try:
            yield ProviderEvent("delta", text="Hello ")
            if self.mode == "slow":
                await asyncio.sleep(30)
            if self.mode == "failure":
                raise ProviderError("provider_unavailable", "Provider is temporarily unavailable.")
            yield ProviderEvent("delta", text="world")
            yield ProviderEvent("done", finish_reason="STOP", usage=Usage(total_tokens=12))
        finally:
            self.closed = True


def app_with(provider):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_provider] = lambda: provider
    return app


def create(client):
    response = client.post("/api/v1/conversations", json={})
    assert response.status_code == 201
    return response.json()["id"]


def wait_for_answer(client, cid):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        data = client.get(f"/api/v1/conversations/{cid}").json()
        if data["messages"][-1]["status"] != "streaming":
            return data
        time.sleep(0.01)
    pytest.fail("Generation did not finish")


def test_saved_chat_history_and_persistence():
    provider = FakeProvider()
    app = app_with(provider)
    with TestClient(app) as client:
        cid = create(client)
        path = f"/api/v1/conversations/{cid}"
        response = client.post(path + "/messages", json={"content": "First question"})
        assert response.status_code == 202
        chat = wait_for_answer(client, cid)
        assert chat["title"] == "First question"
        assert chat["messages"][-1]["content"] == "Hello world"
        assert chat["messages"][-1]["usage"]["total_tokens"] == 12
        client.post(path + "/messages", json={"content": "Follow-up"})
        wait_for_answer(client, cid)
        assert [m.content for m in provider.requests[1].messages] == [
            "First question",
            "Hello world",
            "Follow-up",
        ]
        assert client.patch(path, json={"title": "Renamed"}).status_code == 200
    with TestClient(app_with(FakeProvider())) as client:
        assert client.get(path).json()["title"] == "Renamed"
        assert len(client.get(path).json()["messages"]) == 4
        assert client.delete(path).status_code == 204
        assert client.get(path).status_code == 404
        with app.state.store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_failed_turn_is_preserved_but_excluded_from_context():
    provider = FakeProvider("failure")
    with TestClient(app_with(provider)) as client:
        cid = create(client)
        path = f"/api/v1/conversations/{cid}"
        client.post(path + "/messages", json={"content": "Failed question"})
        chat = wait_for_answer(client, cid)
        assert chat["messages"][-1]["status"] == "failed"
        assert chat["messages"][-1]["content"] == "Hello "
        assert "temporarily unavailable" in chat["messages"][-1]["error"]
        provider.mode = "success"
        client.post(path + "/messages", json={"content": "Try this"})
        wait_for_answer(client, cid)
        assert [m.content for m in provider.requests[-1].messages] == ["Try this"]


def test_cancel_and_concurrent_turn_rejection():
    provider = FakeProvider("slow")
    with TestClient(app_with(provider)) as client:
        cid = create(client)
        path = f"/api/v1/conversations/{cid}"
        mid = client.post(path + "/messages", json={"content": "Question"}).json()["message_id"]
        assert client.post(path + "/messages", json={"content": "Other"}).status_code == 409
        response = client.post(path + f"/messages/{mid}/cancel")
        assert response.json()["status"] == "cancelled"
        assert provider.closed
        assert client.post(path + f"/messages/{mid}/cancel").json()["status"] == "cancelled"
        assert len(client.get(path).json()["messages"]) == 2


def test_delete_running_chat_cancels_generation():
    provider = FakeProvider("slow")
    app = app_with(provider)
    with TestClient(app) as client:
        cid = create(client)
        path = f"/api/v1/conversations/{cid}"
        client.post(path + "/messages", json={"content": "Question"})
        assert client.delete(path).status_code == 204
        assert provider.closed
        assert not app.state.generations.tasks


def test_migrations_and_interrupted_recovery(tmp_path):
    path = str(tmp_path / "database.sqlite3")
    db = Store(path)
    cid = db.create("Test")["id"]
    mid, _ = db.begin(cid, "Question", 100, FakeProvider())
    restored = Store(path)
    assert restored.message(cid, mid)["status"] == "interrupted"
    assert Store(path).get(cid)["title"] == "Test"
    with db.connect() as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="newer"):
        Store(path)


def test_event_snapshots_and_frontend():
    with TestClient(app_with(FakeProvider())) as client:
        assert "CombineLLM" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200
        cid = create(client)
        path = f"/api/v1/conversations/{cid}"
        mid = client.post(path + "/messages", json={"content": "Question"}).json()["message_id"]
        wait_for_answer(client, cid)
        events = client.get(path + f"/messages/{mid}/events")
        assert events.headers["content-type"].startswith("text/event-stream")
        assert "Hello world" in events.text
        assert "event: done" in events.text
        other = create(client)
        assert (
            client.post(f"/api/v1/conversations/{other}/messages/{mid}/cancel").status_code == 404
        )


def test_invalid_saved_turn_is_atomic():
    with TestClient(app_with(FakeProvider())) as client:
        cid = create(client)
        path = f"/api/v1/conversations/{cid}"
        assert client.post(path + "/messages", json={"content": " "}).status_code == 422
        assert client.get(path).json()["messages"] == []
        assert client.post("/api/v1/conversations", json={"title": " "}).status_code == 422
        assert (
            client.post(
                "/api/v1/conversations/missing/messages", json={"content": "Hello"}
            ).status_code
            == 404
        )
