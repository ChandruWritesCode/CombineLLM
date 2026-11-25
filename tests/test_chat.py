import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.chat import get_provider
from app.config import Settings
from app.main import create_app
from app.providers.gemini import GeminiProvider
from app.schemas import ChatRequest

SECRET = "test-secret-never-return"
REQUEST = {"messages": [{"role": "user", "content": "Hello"}]}


def packet(text=None, finish=None, usage=None):
    candidate = {"content": {"parts": [{"text": text}] if text else []}}
    if finish:
        candidate["finishReason"] = finish
    data = {"candidates": [candidate]}
    if usage:
        data["usageMetadata"] = usage
    return "data: " + json.dumps(data) + "\n\n"


def client_for(handler):
    settings = Settings(
        _env_file=None,
        gemini_api_key=SECRET,
        gemini_model="test-model",
        provider_timeout_seconds=1,
    )
    app = create_app(settings)
    app.dependency_overrides[get_provider] = lambda: GeminiProvider(
        settings, httpx.MockTransport(handler)
    )
    return TestClient(app)


def test_request_translation_and_usage():
    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert SECRET not in str(request.url)
        assert request.headers["x-goog-api-key"] == SECRET
        body = json.loads(request.content)
        assert [m["role"] for m in body["contents"]] == ["user", "model", "user"]
        assert body["systemInstruction"] == {"parts": [{"text": "Be brief"}]}
        assert body["generationConfig"]["maxOutputTokens"] == 42
        return httpx.Response(
            200,
            text=packet("Hello ")
            + packet(
                "world",
                "STOP",
                {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 2,
                    "thoughtsTokenCount": 3,
                    "totalTokenCount": 15,
                },
            ),
        )

    with client_for(handler) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "messages": [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello"},
                    {"role": "user", "content": "Continue"},
                ],
                "system": "Be brief",
                "max_output_tokens": 42,
            },
        )
    assert response.status_code == 200
    assert response.json() == {
        "provider": "gemini",
        "model": "test-model",
        "content": "Hello world",
        "finish_reason": "STOP",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 2,
            "reasoning_tokens": 3,
            "total_tokens": 15,
        },
    }


def test_streaming_events():
    with client_for(
        lambda _: httpx.Response(200, text=packet("Hello\n") + packet("world", "MAX_TOKENS"))
    ) as client:
        response = client.post("/api/v1/chat", json={**REQUEST, "stream": True})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count("event: delta") == 2
    assert response.text.count("event: done") == 1
    assert '"finish_reason": "MAX_TOKENS"' in response.text
    assert "event: error" not in response.text


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "status,expected,code",
    [
        (401, 502, "provider_auth_error"),
        (403, 502, "provider_auth_error"),
        (429, 429, "provider_rate_limited"),
        (500, 502, "provider_unavailable"),
        (404, 502, "provider_request_rejected"),
    ],
)
def test_upstream_errors_are_sanitized(stream, status, expected, code):
    with client_for(lambda _: httpx.Response(status, text=SECRET)) as client:
        response = client.post("/api/v1/chat", json={**REQUEST, "stream": stream})
    assert response.status_code == expected
    assert response.json()["error"]["code"] == code
    assert SECRET not in response.text


def test_missing_configuration_and_secret_free_status():
    app = create_app(Settings(_env_file=None, gemini_api_key="", gemini_model=""))
    with TestClient(app) as client:
        assert client.get("/api/v1/providers").json() == [
            {"provider": "gemini", "configured": False, "model": None}
        ]
        assert client.post("/api/v1/chat", json=REQUEST).status_code == 503
    with client_for(lambda _: pytest.fail("Status must not call provider")) as client:
        response = client.get("/api/v1/providers")
        assert response.json()[0]["configured"] is True
        assert SECRET not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {"messages": [{"role": "user", "content": " "}]},
        {"messages": [{"role": "system", "content": "Hi"}]},
        {"messages": [{"role": "assistant", "content": "Hi"}]},
        {**REQUEST, "max_output_tokens": 0},
        {**REQUEST, "provider": "unknown"},
        {**REQUEST, "api_key": "do-not-accept-credentials"},
        {"messages": REQUEST["messages"] * 2},
    ],
)
def test_invalid_requests_do_not_call_provider(body):
    with client_for(lambda _: pytest.fail("Invalid request reached provider")) as client:
        assert client.post("/api/v1/chat", json=body).status_code == 422


@pytest.mark.parametrize(
    "exception,code,status",
    [
        (httpx.ReadTimeout(SECRET), "provider_timeout", 504),
        (httpx.ConnectError(SECRET), "provider_unavailable", 502),
    ],
)
def test_network_failures(exception, code, status):
    def handler(_):
        raise exception

    with client_for(handler) as client:
        response = client.post("/api/v1/chat", json=REQUEST)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert SECRET not in response.text


@pytest.mark.parametrize(
    "wire,code",
    [
        ('data: {"promptFeedback":{"blockReason":"SAFETY"}}\n\n', "content_blocked"),
        ("data: broken\n\n", "invalid_response"),
        ("", "incomplete_response"),
        (packet(finish="STOP"), "incomplete_response"),
    ],
)
def test_invalid_or_blocked_response(wire, code):
    with client_for(lambda _: httpx.Response(200, text=wire)) as client:
        response = client.post("/api/v1/chat", json=REQUEST)
    assert response.json()["error"]["code"] == code


def test_partial_failure_is_error_not_done():
    with client_for(lambda _: httpx.Response(200, text=packet("Partial"))) as client:
        response = client.post("/api/v1/chat", json={**REQUEST, "stream": True})
    assert response.status_code == 200
    assert "event: delta" in response.text
    assert "event: error" in response.text
    assert "event: done" not in response.text


class SlowStream(httpx.AsyncByteStream):
    closed = False

    async def __aiter__(self):
        yield packet("Starting").encode()
        await asyncio.sleep(2)
        yield packet("Finished", "STOP").encode()

    async def aclose(self):
        self.closed = True


def test_total_timeout_after_stream_starts_closes_upstream():
    upstream = SlowStream()
    with client_for(lambda _: httpx.Response(200, stream=upstream)) as client:
        response = client.post("/api/v1/chat", json={**REQUEST, "stream": True})
    assert "provider_timeout" in response.text
    assert "event: done" not in response.text
    assert upstream.closed


def test_thought_parts_are_not_exposed():
    wire = (
        "data: "
        + json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "private", "thought": True}, {"text": "Answer"}]
                        },
                        "finishReason": "STOP",
                    }
                ]
            }
        )
        + "\n\n"
    )
    with client_for(lambda _: httpx.Response(200, text=wire)) as client:
        response = client.post("/api/v1/chat", json=REQUEST)
    assert response.json()["content"] == "Answer"


def test_cancelling_consumer_closes_provider_stream():
    upstream = SlowStream()

    async def consume():
        provider = GeminiProvider(
            Settings(_env_file=None, gemini_api_key=SECRET, gemini_model="test-model"),
            httpx.MockTransport(lambda _: httpx.Response(200, stream=upstream)),
        )
        events = provider.stream(ChatRequest.model_validate(REQUEST))
        assert (await anext(events)).text == "Starting"
        pending = asyncio.create_task(anext(events))
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await events.aclose()

    asyncio.run(consume())
    assert upstream.closed


def test_fragmented_sse_and_missing_final_blank_line():
    class Fragments(httpx.AsyncByteStream):
        async def __aiter__(self):
            wire = (": keepalive\n\n" + packet("Hello", "STOP").rstrip()).encode()
            for index in range(0, len(wire), 3):
                yield wire[index : index + 3]

    with client_for(lambda _: httpx.Response(200, stream=Fragments())) as client:
        response = client.post("/api/v1/chat", json=REQUEST)
    assert response.status_code == 200
    assert response.json()["content"] == "Hello"
