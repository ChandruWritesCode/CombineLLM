"""Bounded, explicitly enabled ordered fallback for text generation."""

import asyncio
from contextlib import aclosing

from fastapi import HTTPException

from app.model_api import build_provider
from app.providers.base import ProviderError

RETRYABLE = {"provider_rate_limited", "provider_unavailable", "provider_timeout"}
CHAIN_TIMEOUT_SECONDS = 120


class FallbackProvider:
    def __init__(self, providers):
        self.providers = providers
        self.current = providers[0]
        self.model_id = self.current.model_id  # Keep the conversation's chosen primary.
        self.max_output_tokens = self.current.max_output_tokens
        self.system_prompt = self.current.system_prompt
        self.attempt_group_id = self.current.attempt_group_id
        for number, provider in enumerate(providers, 1):
            provider.attempt_group_id = self.attempt_group_id
            provider.attempt_number = number

    @property
    def name(self):
        return self.current.name

    @property
    def model(self):
        return self.current.model

    @property
    def response_model_id(self):
        return self.current.model_id

    async def stream(self, request):
        # A single instruction/context applies to the whole chain.
        request = request.model_copy(
            update={
                "system": request.system
                if request.system is not None
                else self.system_prompt or None
            }
        )
        try:
            async with asyncio.timeout(CHAIN_TIMEOUT_SECONDS):
                for index, provider in enumerate(self.providers):
                    self.current = provider
                    text_seen = False
                    attempt = request.model_copy(
                        update={
                            "max_output_tokens": min(
                                request.max_output_tokens, provider.max_output_tokens
                            ),
                            # Prevent each fallback from silently replacing the primary instruction.
                            "system": request.system if request.system is not None else "",
                        }
                    )
                    try:
                        async with aclosing(provider.stream(attempt)) as events:
                            async for event in events:
                                if event.kind == "delta" and event.text:
                                    text_seen = True
                                yield event
                                if event.kind == "done":
                                    return
                        raise ProviderError("incomplete_response", "Provider stream ended early.")
                    except ProviderError as exc:
                        if (
                            text_seen
                            or exc.code not in RETRYABLE
                            or index == len(self.providers) - 1
                        ):
                            raise
        except TimeoutError as exc:
            raise ProviderError("provider_timeout", "Fallback time limit reached.", 504) from exc


def select_provider(app, model_id, source, fallback=False):
    primary = build_provider(app, model_id, source)
    if not fallback:
        return primary
    ids = [
        mid
        for mid in app.state.connections.preferences().fallback_model_ids
        if mid != primary.model_id
    ]
    if not ids:
        raise HTTPException(422, "Configure at least one different fallback model in Settings.")
    # Validate the entire explicit chain before sending any prompt.
    providers = [primary] + [build_provider(app, mid, source) for mid in ids]
    return FallbackProvider(providers)
