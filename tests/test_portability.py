"""Portable transcripts use isolated storage and never export credentials."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import now


class Model:
    name = "compatible"
    model = "sample-model"
    model_id = None
    max_output_tokens = 512


def test_json_and_text_export_round_trip_without_credentials_or_usage():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        configured = client.post(
            "/api/v1/models",
            json={
                "name": "Private model",
                "kind": "compatible",
                "model": "sample-model",
                "base_url": "http://localhost:9999/v1",
                "api_key": "secret-credential",
            },
        ).json()
        model = Model()
        model.model_id = configured["id"]
        store = client.app.state.store
        cid = store.create("Portable chat")["id"]
        first, _ = store.begin(cid, "First question", 512, model)
        store.attribute_answer(first, model)
        store.save_answer(first, "First answer", "complete")
        second, _ = store.begin(cid, "Second question", 512, model)
        store.attribute_answer(second, model)
        store.save_answer(second, "Partial", "failed", error="Unavailable")

        result = client.get(f"/api/v1/conversations/{cid}/export")
        assert result.status_code == 200
        assert "attachment" in result.headers["content-disposition"]
        archive = result.json()
        assert archive["format"] == "combinellm-conversation"
        assert archive["version"] == 1
        assert [message["status"] for message in archive["messages"]] == [
            "complete",
            "complete",
            "complete",
            "failed",
        ]
        assert "secret-credential" not in result.text
        assert "model_id" not in result.text
        assert "usage_events" not in result.text
        text = client.get(f"/api/v1/conversations/{cid}/export?format=text")
        assert text.status_code == 200
        assert text.headers["content-type"].startswith("text/plain")
        assert "First question" in text.text
        assert "First answer" in text.text

        imported = client.post("/api/v1/conversations/import", json=archive)
        assert imported.status_code == 201
        copy = imported.json()
        assert copy["id"] != cid
        assert copy["title"] == "Portable chat"
        assert [message["content"] for message in copy["messages"]] == [
            "First question",
            "First answer",
            "Second question",
            "Partial",
        ]
        assert all(message["model_id"] is None for message in copy["messages"])
        assert not any(message["attempts"] for message in copy["messages"])
        assert client.get("/api/v1/usage").json()["requests"] == 0
        _, resumed = store.begin(copy["id"], "Follow-up", 512, model)
        assert [message.content for message in resumed.messages] == [
            "First question",
            "First answer",
            "Follow-up",
        ]


def test_invalid_archives_are_rejected_without_creating_chats():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        valid = {
            "format": "combinellm-conversation",
            "version": 1,
            "title": "Test",
            "messages": [
                {"role": "user", "content": "Hi", "status": "complete", "created_at": now()},
                {
                    "role": "assistant",
                    "content": "Hello",
                    "status": "complete",
                    "created_at": now(),
                },
            ],
        }
        cases = [
            {**valid, "version": 2},
            {**valid, "api_key": "must not import"},
            {**valid, "messages": valid["messages"][:1]},
            {**valid, "messages": [valid["messages"][0], {**valid["messages"][1], "role": "user"}]},
            {
                **valid,
                "messages": [{**valid["messages"][0], "status": "streaming"}, valid["messages"][1]],
            },
            {**valid, "messages": [{**valid["messages"][0], "content": " "}, valid["messages"][1]]},
        ]
        for archive in cases:
            assert client.post("/api/v1/conversations/import", json=archive).status_code == 422
        assert client.get("/api/v1/conversations").json() == []


def test_running_chat_cannot_be_exported():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        store = client.app.state.store
        cid = store.create("Busy")["id"]
        mid, _ = store.begin(cid, "Question", 512, Model())
        assert client.get(f"/api/v1/conversations/{cid}/export").status_code == 409
        store.save_answer(mid, "", "cancelled")
        assert client.get(f"/api/v1/conversations/{cid}/export").status_code == 200
