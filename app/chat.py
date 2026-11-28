import json
from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.coordination import build_coordinated_provider
from app.profiles import prepare_profile
from app.providers.base import ChatProvider, ProviderError
from app.recommendations import compare_models
from app.routing import select_provider
from app.schemas import ChatRequest, ChatResponse, Coordination, ProviderStatus, Usage

router = APIRouter(prefix="/api/v1", tags=["chat"])


async def get_provider(request: Request) -> ChatProvider:
    body = await request.json()
    model_id = body.get("model_id") if isinstance(body, dict) else None
    conversation_id = request.path_params.get("conversation_id")
    if not model_id and conversation_id:
        model_id = request.app.state.store.get(conversation_id).get("model_id")
    auto_selected = bool(
        conversation_id and isinstance(body, dict) and body.get("auto_select") is True
    )
    plan = None
    if auto_selected:
        content = body.get("content")
        if not isinstance(content, str):
            raise HTTPException(422, "Message content must be text.")
        profile_name = body.get("routing_profile")
        if profile_name is not None and not isinstance(profile_name, str):
            raise HTTPException(422, "Routing profile must be a name")
        if profile_name:
            plan = prepare_profile(
                request.app,
                profile_name,
                conversation_id,
                content,
                task_hint=body.get("task_hint"),
                local_only=body.get("local_only") is True,
            )
            model_id = plan["primary_model_id"]
        else:
            input_chars = request.app.state.store.context_chars(conversation_id, content)
            comparison = compare_models(
                request.app,
                local_only=body.get("local_only") is True,
                task_hint=body.get("task_hint"),
                input_chars=input_chars,
            )
            model_id = comparison["suggested_model_id"]
        if not model_id:
            raise HTTPException(422, "No eligible model is available for automatic selection.")
    provider = select_provider(
        request.app,
        model_id,
        "saved_chat" if conversation_id else "stateless_chat",
        fallback=isinstance(body, dict)
        and body.get("fallback") is True
        and not body.get("coordination")
        and not auto_selected,
        local_only=isinstance(body, dict) and body.get("local_only") is True,
    )
    if plan and plan["mode"] != "single":
        provider = build_coordinated_provider(
            request.app,
            provider,
            Coordination(
                mode=plan["mode"],
                collaborator_model_id=plan["collaborator_model_id"],
            ),
            local_only=body.get("local_only") is True,
        )
    if auto_selected:
        provider.selection_mode = "automatic"
        task = body.get("task_hint")
        provider.selection_reason = (
            f"Profile {plan['profile']} selected {plan['calls']} calls "
            f"for {task or 'general use'}; "
            "provider quotas are advisory and cost is estimated."
            if plan
            else f"Chosen for {task or 'general use'} using user-entered task/context hints, "
            "local prices, recent outcomes, budgets and cooldowns. "
            "Provider quota signals are historical; live availability was not checked."
        )
    return provider


@router.get("/providers", response_model=list[ProviderStatus])
async def provider_status(request: Request):
    """Configuration status only; does not contact the provider or validate credentials."""
    settings = request.app.state.settings
    return [
        ProviderStatus(
            provider="gemini",
            configured=bool(
                settings.gemini_api_key.get_secret_value().strip() and settings.gemini_model
            ),
            model=settings.gemini_model or None,
        )
    ]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat(body: ChatRequest, provider: ChatProvider = Depends(get_provider)):
    """Text chat. Set stream=true for delta, done, or error SSE events.

    Send conversation history on every request; history is not saved yet.
    Errors after streaming begins arrive as an error event, not an HTTP status change.
    """
    events = provider.stream(body)
    if not body.stream:
        chunks = []
        async with aclosing(events):
            async for event in events:
                if event.kind == "delta":
                    chunks.append(event.text)
                else:
                    return ChatResponse(
                        provider=provider.name,
                        model=provider.model,
                        content="".join(chunks),
                        finish_reason=event.finish_reason,
                        usage=event.usage or Usage(),
                    )
        raise ProviderError("incomplete_response", "Provider did not complete the response.")

    # Read the first event before sending HTTP headers so early failures keep their status.
    try:
        first = await anext(events)
    except StopAsyncIteration as exc:
        await events.aclose()
        raise ProviderError("incomplete_response", "Provider returned no response.") from exc
    except BaseException:
        await events.aclose()
        raise

    async def stream():
        async with aclosing(events):
            try:
                event = first
                while True:
                    if event.kind == "delta":
                        yield sse("delta", {"content": event.text})
                    else:
                        yield sse(
                            "done",
                            {
                                "provider": provider.name,
                                "model": provider.model,
                                "finish_reason": event.finish_reason,
                                "usage": (event.usage or Usage()).model_dump(),
                            },
                        )
                        return
                    event = await anext(events)
            except StopAsyncIteration:
                yield sse(
                    "error",
                    {"code": "incomplete_response", "message": "Provider stream ended early."},
                )
            except ProviderError as exc:
                yield sse("error", exc.payload())

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
