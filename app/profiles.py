"""Explicit routing profiles and bounded multi-model preflight."""

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.recommendations import compare_models

router = APIRouter(prefix="/api/v1", tags=["routing"])
CALLS = {"single": 1, "review": 3, "split": 4}


def find_profile(registry, name):
    profile = next(
        (
            p
            for p in registry.preferences().routing_profiles
            if p.name.casefold() == name.casefold()
        ),
        None,
    )
    if profile is None:
        raise HTTPException(422, "This routing profile is no longer configured")
    return profile


def _estimate_cost(configs, mode, input_chars):
    output_caps = (
        [configs[0]["max_output_tokens"]]
        if mode == "single"
        else [1024, 768, configs[0]["max_output_tokens"]]
        if mode == "review"
        else [256, 1024, 1024, configs[0]["max_output_tokens"]]
    )
    total = Decimal(0)
    for index, config in enumerate(configs):
        input_rate = config.get("input_price_per_million")
        output_rate = config.get("output_price_per_million")
        if input_rate is None or output_rate is None:
            return None
        # Approximation only: provider tokenization, hidden tokens and fees may differ.
        estimated_input = input_chars + 1000 + index * 8000
        output_tokens = min(output_caps[index], config["max_output_tokens"])
        total += (
            Decimal(estimated_input) * Decimal(str(input_rate))
            + Decimal(output_tokens) * Decimal(str(output_rate))
        ) / Decimal(1_000_000)
    return total


def prepare_profile(app, name, conversation_id, content, task_hint=None, local_only=False):
    registry = app.state.connections
    profile = find_profile(registry, name)
    if conversation_id:
        registry.store.get(conversation_id)
        input_chars = registry.store.context_chars(conversation_id, content)
    else:
        input_chars = len(content)
    if profile.mode != "single" and input_chars > 30000:
        raise HTTPException(422, "Coordinated profiles support up to 30,000 characters of input")
    comparison = compare_models(
        app,
        local_only=local_only,
        task_hint=task_hint,
        input_chars=input_chars,
        priority=profile.priority,
    )
    eligible = [item for item in comparison["models"] if item["eligible"]]
    if not eligible:
        raise HTTPException(422, "No eligible model is available for this routing profile")
    primary = eligible[0]
    collaborator = next(
        (item for item in eligible[1:] if item["model_id"] != primary["model_id"]), None
    )
    if profile.mode != "single" and collaborator is None:
        raise HTTPException(422, "A coordinated profile needs two eligible model connections")
    by_id = {config["id"]: config for config in registry.list()}
    first = by_id[primary["model_id"]]
    second = by_id[collaborator["model_id"]] if collaborator else None
    configs = (
        [first]
        if profile.mode == "single"
        else [first, second, first]
        if profile.mode == "review"
        else [first, first, second, first]
    )
    estimate = _estimate_cost(configs, profile.mode, input_chars)
    cap = profile.max_estimated_cost_usd
    if cap is not None and estimate is None:
        raise HTTPException(
            422, "Set input and output prices for all planned models to use this cost limit"
        )
    if cap is not None and estimate > cap:
        raise HTTPException(422, "The planned cost estimate exceeds this profile's limit")
    return {
        "profile": profile.name,
        "mode": profile.mode,
        "priority": profile.priority,
        "calls": CALLS[profile.mode],
        "max_calls": profile.max_calls,
        "primary_model_id": primary["model_id"],
        "primary_name": primary["name"],
        "collaborator_model_id": collaborator["model_id"] if collaborator else None,
        "collaborator_name": collaborator["name"] if collaborator else None,
        "estimated_cost_usd": str(estimate) if estimate is not None else None,
        "max_estimated_cost_usd": str(cap) if cap is not None else None,
        "input_chars": input_chars,
        "warnings": [
            "Cost is an estimate from entered prices and approximate tokens; "
            "provider billing may differ.",
            "Each planned call can consume quota or credits.",
        ],
    }


@router.get("/routing/preview")
async def preview(
    request: Request,
    profile: str,
    conversation_id: str | None = None,
    input_chars: int = Query(default=0, ge=0, le=50000),
    task_hint: Literal["general", "code", "writing", "analysis"] | None = None,
    local_only: bool = False,
):
    return prepare_profile(
        request.app,
        profile,
        conversation_id,
        "x" * input_chars,
        task_hint,
        local_only,
    )
