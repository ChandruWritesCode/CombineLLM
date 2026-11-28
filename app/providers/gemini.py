"""Gemini REST adapter. Credentials are sent only to the fixed official endpoint."""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.config import Settings
from app.policies import retry_delay
from app.providers.base import ProviderError, ProviderEvent
from app.quota import parse_headers
from app.schemas import ChatRequest, Usage


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.model = settings.gemini_model
        self._key = settings.gemini_api_key.get_secret_value().strip()
        self._timeout = settings.provider_timeout_seconds
        self._transport = transport
        self.last_quota = None

    async def stream(self, request: ChatRequest) -> AsyncIterator[ProviderEvent]:
        if not self._key or not self.model:
            raise ProviderError(
                "provider_not_configured",
                "Set COMBINELLM_GEMINI_API_KEY and COMBINELLM_GEMINI_MODEL in .env, then restart.",
                503,
            )
        body = {
            "contents": [
                {
                    "role": "model" if message.role == "assistant" else "user",
                    "parts": [{"text": message.content}],
                }
                for message in request.messages
            ],
            "generationConfig": {"maxOutputTokens": request.max_output_tokens},
        }
        if getattr(self, "temperature", None) is not None:
            body["generationConfig"]["temperature"] = self.temperature
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:streamGenerateContent?alt=sse"
        )
        deadline = time.monotonic() + self._timeout
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=min(10, self._timeout)),
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST", url, headers={"x-goog-api-key": self._key}, json=body
                ) as response:
                    self.last_quota = parse_headers(response.headers)
                    self._check_status(response.status_code, response.headers.get("retry-after"))
                    usage = Usage()
                    finish = ""
                    has_text = False
                    async for data in self._events(response, deadline):
                        if data.get("error"):
                            raise ProviderError("provider_error", "Provider stream failed.")
                        if data.get("promptFeedback", {}).get("blockReason"):
                            raise ProviderError(
                                "content_blocked", "Provider blocked this request.", 422
                            )
                        if "usageMetadata" in data:
                            raw = data["usageMetadata"]
                            usage = Usage(
                                input_tokens=raw.get("promptTokenCount"),
                                output_tokens=raw.get("candidatesTokenCount"),
                                reasoning_tokens=raw.get("thoughtsTokenCount"),
                                total_tokens=raw.get("totalTokenCount"),
                            )
                        candidates = data.get("candidates", [])
                        if not candidates:
                            continue
                        candidate = candidates[0]
                        reason = candidate.get("finishReason")
                        if reason and reason not in {"STOP", "MAX_TOKENS"}:
                            raise ProviderError(
                                "content_blocked", "Provider could not complete this response.", 422
                            )
                        for part in candidate.get("content", {}).get("parts", []):
                            # Thinking parts are not user-facing answer text.
                            if part.get("text") and not part.get("thought"):
                                has_text = True
                                yield ProviderEvent("delta", text=part["text"])
                        if reason:
                            finish = reason
                    if not finish or not has_text:
                        raise ProviderError(
                            "incomplete_response",
                            "Provider returned an empty or incomplete answer.",
                        )
                    yield ProviderEvent("done", finish_reason=finish, usage=usage)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderError("provider_timeout", "Provider response timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                "provider_unavailable", "Could not reach the provider.", 502
            ) from exc
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
            raise ProviderError(
                "invalid_response", "Provider returned an invalid response."
            ) from exc

    @staticmethod
    def _check_status(status: int, retry_after=None) -> None:
        if 200 <= status < 300:
            return
        if status in {401, 403}:
            raise ProviderError(
                "provider_auth_error",
                "Authentication failed: check the API key and account/model permissions.",
                502,
            )
        if status == 429:
            raise ProviderError(
                "provider_rate_limited",
                "Provider quota or rate limit reached. A shared cooldown now applies.",
                429,
                retry_after=retry_delay(retry_after),
            )
        if status in {400, 404}:
            raise ProviderError(
                "provider_request_rejected",
                "Request rejected: check the model ID, supported parameters and account access.",
                502,
            )
        raise ProviderError("provider_unavailable", "Provider is temporarily unavailable.", 502)

    @staticmethod
    async def _events(response: httpx.Response, deadline: float) -> AsyncIterator[dict]:
        lines: list[str] = []
        iterator = response.aiter_lines().__aiter__()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                line = await asyncio.wait_for(anext(iterator), timeout=remaining)
            except StopAsyncIteration:
                break
            if not line:
                if lines:
                    yield (
                        {"_done": True}
                        if "\n".join(lines) == "[DONE]"
                        else json.loads("\n".join(lines))
                    )
                    lines = []
            elif line.startswith("data:"):
                lines.append(line[5:].lstrip(" "))
        if lines:
            yield {"_done": True} if "\n".join(lines) == "[DONE]" else json.loads("\n".join(lines))
