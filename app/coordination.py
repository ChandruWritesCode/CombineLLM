"""Opt-in, bounded multi-model workflows for saved conversations."""

import asyncio
import re
from contextlib import aclosing

from fastapi import HTTPException

from app.model_api import build_provider
from app.policies import is_local
from app.providers.base import ProviderError, ProviderEvent
from app.schemas import ChatRequest, Coordination, Message

WORKFLOW_TIMEOUT_SECONDS = 180
MAX_CONTEXT_CHARS = 30000
MAX_INTERMEDIATE_CHARS = 8000


def _single_prompt(text, system, output_tokens):
    return ChatRequest(
        messages=[Message(role="user", content=text)],
        system=system or None,
        max_output_tokens=output_tokens,
    )


def _context(messages):
    return "\n\n".join(f"{message.role.title()}: {message.content}" for message in messages)


def _two_tasks(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 2:
        raise ProviderError("invalid_plan", "The planning model did not return two subtasks.")
    tasks = []
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(rf"{number}\.\s+(.{{1,500}})", line)
        if not match:
            raise ProviderError("invalid_plan", "The planning model did not return two subtasks.")
        tasks.append(match.group(1))
    return tasks


class CoordinatedProvider:
    def __init__(self, mode, providers):
        self.coordination_mode = mode
        self.providers = providers
        self.current = providers[0]
        self.model_id = providers[0].model_id
        self.max_output_tokens = providers[0].max_output_tokens
        self.system_prompt = providers[0].system_prompt
        self.attempt_group_id = providers[0].attempt_group_id
        for number, provider in enumerate(providers, 1):
            provider.attempt_group_id = self.attempt_group_id
            provider.attempt_number = number
            provider.source = f"coordination_{self.stages[number - 1]}"

    @property
    def stages(self):
        return (
            ["draft", "review", "revision"]
            if self.coordination_mode == "review"
            else ["plan", "subtask_1", "subtask_2", "synthesis"]
        )

    @property
    def name(self):
        return self.current.name

    @property
    def model(self):
        return self.current.model

    @property
    def response_model_id(self):
        return self.current.model_id

    async def _collect(self, provider, prompt):
        content = ""
        completed = False
        async with aclosing(provider.stream(prompt)) as events:
            async for event in events:
                if event.kind == "delta":
                    content += event.text
                    if len(content) > MAX_INTERMEDIATE_CHARS:
                        raise ProviderError(
                            "response_too_long", "An intermediate response was too long."
                        )
                elif event.kind == "done":
                    completed = True
                    break
        if not completed or not content.strip():
            raise ProviderError("incomplete_response", "An intermediate model returned no answer.")
        return content

    async def _stage(self, index, label, prompt):
        self.current = self.providers[index]
        yield ProviderEvent("stage", text=label)
        result = await self._collect(self.current, prompt)
        yield ProviderEvent("intermediate", text=result, finish_reason=self.stages[index])
        yield result

    async def _final(self, index, label, prompt):
        self.current = self.providers[index]
        yield ProviderEvent("stage", text=label)
        completed = False
        async with aclosing(self.current.stream(prompt)) as events:
            async for event in events:
                yield event
                if event.kind == "done":
                    completed = True
                    break
        if not completed:
            raise ProviderError("incomplete_response", "The final model response ended early.")

    async def stream(self, request):
        if len(_context(request.messages)) > MAX_CONTEXT_CHARS:
            raise ProviderError(
                "context_too_long",
                "Coordinated mode supports up to 30,000 characters of history.",
                422,
            )
        try:
            async with asyncio.timeout(WORKFLOW_TIMEOUT_SECONDS):
                if self.coordination_mode == "review":
                    draft_request = ChatRequest(
                        messages=[
                            *request.messages[:-1],
                            Message(
                                role="user",
                                content=request.messages[-1].content
                                + "\n\nFirst write a useful draft answer.",
                            ),
                        ],
                        system=request.system,
                        max_output_tokens=min(1024, self.providers[0].max_output_tokens),
                    )
                    async for result in self._stage(0, "Writing draft", draft_request):
                        if isinstance(result, ProviderEvent):
                            yield result
                        else:
                            draft = result
                    review_prompt = _single_prompt(
                        f"Original conversation:\n{_context(request.messages)}\n\n"
                        f"Draft answer:\n{draft}\n\nReview the draft for factual gaps, "
                        "missed requirements, and clarity. Give concise actionable feedback.",
                        self.providers[1].system_prompt,
                        min(768, self.providers[1].max_output_tokens),
                    )
                    async for result in self._stage(1, "Reviewing draft", review_prompt):
                        if isinstance(result, ProviderEvent):
                            yield result
                        else:
                            review = result
                    final_prompt = _single_prompt(
                        f"Original conversation:\n{_context(request.messages)}\n\n"
                        f"Draft answer:\n{draft}\n\nReview feedback:\n{review}\n\n"
                        "Write the final answer. Correct issues raised by the review, "
                        "and do not include the review process unless asked.",
                        self.providers[2].system_prompt,
                        min(request.max_output_tokens, self.providers[2].max_output_tokens),
                    )
                    async for event in self._final(2, "Writing final answer", final_prompt):
                        yield event
                else:
                    plan_request = _single_prompt(
                        f"Conversation:\n{_context(request.messages)}\n\n"
                        "Split the latest user request into exactly two useful, "
                        "non-overlapping subtasks. Return exactly two lines: "
                        "1. <subtask> and 2. <subtask>. No other text.",
                        self.providers[0].system_prompt,
                        min(256, self.providers[0].max_output_tokens),
                    )
                    async for result in self._stage(0, "Planning two subtasks", plan_request):
                        if isinstance(result, ProviderEvent):
                            yield result
                        else:
                            tasks = _two_tasks(result)
                    answers = []
                    for index in (1, 2):
                        worker = self.providers[index]
                        worker_request = _single_prompt(
                            f"Conversation:\n{_context(request.messages)}\n\n"
                            f"Work only on subtask {index}: {tasks[index - 1]}\n\n"
                            "Return findings that help answer the original request.",
                            worker.system_prompt,
                            min(1024, worker.max_output_tokens),
                        )
                        async for result in self._stage(
                            index, f"Working on subtask {index}", worker_request
                        ):
                            if isinstance(result, ProviderEvent):
                                yield result
                            else:
                                answers.append(result)
                    final_prompt = _single_prompt(
                        f"Conversation:\n{_context(request.messages)}\n\n"
                        f"Subtask 1 ({tasks[0]}):\n{answers[0]}\n\n"
                        f"Subtask 2 ({tasks[1]}):\n{answers[1]}\n\n"
                        "Synthesize one coherent final answer. Resolve overlap and "
                        "uncertainty; do not invent findings.",
                        self.providers[3].system_prompt,
                        min(request.max_output_tokens, self.providers[3].max_output_tokens),
                    )
                    async for event in self._final(3, "Synthesizing answer", final_prompt):
                        yield event
        except TimeoutError as exc:
            raise ProviderError("provider_timeout", "Coordinated workflow timed out.", 504) from exc


def build_coordinated_provider(app, primary, coordination: Coordination, local_only=False):
    collaborator_id = coordination.collaborator_model_id
    if collaborator_id == primary.model_id:
        raise HTTPException(422, "Choose a different model for collaboration.")
    config = app.state.connections.get(collaborator_id)
    if not config["enabled"]:
        raise HTTPException(422, "The collaborator model is disabled.")
    if local_only and not is_local(config):
        raise HTTPException(422, "Local-only mode rejects cloud collaborator endpoints.")
    collaborator = build_provider(app, collaborator_id, "saved_chat")
    if coordination.mode == "review":
        providers = [primary, collaborator, build_provider(app, primary.model_id, "saved_chat")]
    else:
        providers = [
            primary,
            build_provider(app, primary.model_id, "saved_chat"),
            collaborator,
            build_provider(app, primary.model_id, "saved_chat"),
        ]
    return CoordinatedProvider(coordination.mode, providers)
