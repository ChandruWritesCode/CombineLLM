# CombineLLM development phases

Each phase should leave the application runnable.

1. **Backend and Docker foundation (complete):** FastAPI, configuration, health endpoint,
   API documentation, tests, local development, and a non-root Docker image.
   Complete when tests pass and the container reports healthy.
2. **First model connection:**
   provider adapter interface, Gemini official REST API integration,
   server-side credentials, a chat endpoint, streaming, timeouts, and clear errors.
3. **Saved chat and basic frontend:** SQLite, migrations, conversations/messages,
   a simple HTML/CSS/JS chat page, and cancellation.
4. **Multiple providers and fallback:** more adapters, optional Ollama, model selection,
   ordered fallback, capability checks, cooldowns, and explicit free-only policies.
5. **Usage and budgets:** per-attempt usage ledger, estimated versus reported costs,
   shared quota pools, budget reservations, and a dashboard.
6. **Coordinated models:** task-based routing, draft/review, bounded task splitting,
   synthesis, and quality/cost evaluations.

Phase 2 has no database or chat UI. Credentials are configured server-side in `.env`.
Introduce storage with Phase 3. Cloud APIs send prompts off the machine;
local-only inference will be a separate enforced policy. Website subscriptions do
not automatically grant API access.
