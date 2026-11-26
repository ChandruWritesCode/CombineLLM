"""Text streaming adapters for OpenAI-compatible and Anthropic endpoints."""

import time

import httpx

from app.providers.base import ProviderError, ProviderEvent
from app.providers.gemini import GeminiProvider
from app.schemas import Usage


class APIProvider:
    def __init__(self, config, key, transport=None):
        self.config = config
        self.key = key
        self.name = config["kind"]
        self.model = config["model"]
        self.model_id = config["id"]
        self.label = config["name"]
        self.max_output_tokens = config["max_output_tokens"]
        self.system_prompt = config["system_prompt"]
        self.transport = transport

    async def stream(self, request):
        if not self.key and self.name not in {"ollama", "compatible"}:
            raise ProviderError("provider_not_configured", "Add a credential in Settings.", 503)
        anthropic = self.name == "anthropic"
        headers = (
            {"x-api-key": self.key, "anthropic-version": "2023-06-01"}
            if anthropic
            else ({"Authorization": f"Bearer {self.key}"} if self.key else {})
        )
        messages = [m.model_dump() for m in request.messages]
        body = {"model": self.model, "messages": messages, "stream": True}
        body["max_tokens" if anthropic else self.config["token_parameter"]] = (
            request.max_output_tokens
        )
        if request.system:
            if anthropic:
                body["system"] = request.system
            else:
                messages.insert(0, {"role": "system", "content": request.system})
        if self.config["temperature"] is not None:
            body["temperature"] = self.config["temperature"]
        if not anthropic and self.config["include_usage"]:
            body["stream_options"] = {"include_usage": True}
        timeout = self.config["timeout_seconds"]
        deadline = time.monotonic() + timeout
        url = self.config["base_url"] + ("/messages" if anthropic else "/chat/completions")
        usage = Usage()
        finish = ""
        text_seen = False
        ended = False
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=self.transport, follow_redirects=False
            ) as client:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    GeminiProvider._check_status(
                        response.status_code, response.headers.get("retry-after")
                    )
                    async for data in GeminiProvider._events(response, deadline):
                        if data.get("_done"):
                            ended = True
                            break
                        if data.get("error") or data.get("type") == "error":
                            raise ProviderError("provider_error", "Provider stream failed.")
                        if anthropic:
                            kind = data.get("type")
                            if kind == "message_start":
                                raw = data.get("message", {}).get("usage", {})
                                usage.input_tokens = raw.get("input_tokens")
                                usage.output_tokens = raw.get("output_tokens")
                            elif kind == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta" and delta.get("text"):
                                    text_seen = True
                                    yield ProviderEvent("delta", text=delta["text"])
                            elif kind == "message_delta":
                                finish = data.get("delta", {}).get("stop_reason") or finish
                                usage.output_tokens = data.get("usage", {}).get(
                                    "output_tokens", usage.output_tokens
                                )
                            elif kind == "message_stop":
                                ended = True
                        else:
                            raw = data.get("usage")
                            if raw:
                                usage = Usage(
                                    input_tokens=raw.get("prompt_tokens"),
                                    output_tokens=raw.get("completion_tokens"),
                                    total_tokens=raw.get("total_tokens"),
                                    reasoning_tokens=(
                                        raw.get("completion_tokens_details") or {}
                                    ).get("reasoning_tokens"),
                                )
                            choices = data.get("choices", [])
                            if not choices:
                                continue
                            choice = choices[0]
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
                            text = choice.get("delta", {}).get("content")
                            if text:
                                if not isinstance(text, str):
                                    raise ValueError("Non-text content")
                                text_seen = True
                                yield ProviderEvent("delta", text=text)
                    if not ended or not finish or not text_seen:
                        raise ProviderError(
                            "incomplete_response", "Provider returned an incomplete text answer."
                        )
                    if finish not in {"stop", "length", "end_turn", "max_tokens", "stop_sequence"}:
                        raise ProviderError(
                            "unsupported_response",
                            "Provider did not return a completed text answer.",
                        )
                    if (
                        anthropic
                        and usage.input_tokens is not None
                        and usage.output_tokens is not None
                    ):
                        usage.total_tokens = usage.input_tokens + usage.output_tokens
                    yield ProviderEvent(
                        "done",
                        finish_reason="MAX_TOKENS"
                        if finish in {"length", "max_tokens"}
                        else "STOP",
                        usage=usage,
                    )
        except httpx.TimeoutException as exc:
            raise ProviderError("provider_timeout", "Provider response timed out.", 504) from exc
        except TimeoutError as exc:
            raise ProviderError("provider_timeout", "Provider response timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise ProviderError("provider_unavailable", "Could not reach the provider.") from exc
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
            raise ProviderError(
                "invalid_response", "Provider returned an invalid response."
            ) from exc
