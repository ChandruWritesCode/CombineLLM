import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.config import Settings
from app.connections import Connection
from app.main import create_app


def test_catalog_presets_and_official_links():
    entries = json.loads(Path("app/static/provider-catalog.json").read_text())
    assert len({entry["id"] for entry in entries}) == len(entries) == 9
    for entry in entries:
        assert urlsplit(entry["source"]).scheme == "https"
        assert urlsplit(entry["signup"]).scheme == "https"
        assert entry["guide"] and entry["checked"]
        Connection(
            name=entry["name"],
            kind=entry["kind"],
            model=entry["model"] or "example-model",
            base_url=entry["base_url"].replace("ACCOUNT_ID", "testaccount"),
        )


def test_discovery_page_and_save_do_not_call_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Saving must not construct a provider")

    monkeypatch.setattr("app.model_api.build_provider", forbidden)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/discover").status_code == 200
        catalog = client.get("/static/provider-catalog.json").json()
        item = next(i for i in catalog if i["id"] == "groq")
        before = client.get("/api/v1/settings").json()
        response = client.post(
            "/api/v1/models",
            json={
                "name": item["name"],
                "model": item["model"],
                "kind": item["kind"],
                "base_url": item["base_url"],
                "api_key": "fake-test-key",
            },
        )
        assert response.status_code == 201
        assert response.json()["has_key"]
        assert "fake-test-key" not in response.text
        assert client.get("/api/v1/settings").json() == before
        assert client.get("/api/v1/usage").json()["requests"] == 0
