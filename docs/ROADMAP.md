# CombineLLM development phases

Each phase should leave the application runnable.

1. **Backend and Docker foundation (complete):** FastAPI, configuration, health endpoint,
   API documentation, tests, local development, and a non-root Docker image.
   Complete when tests pass and the container reports healthy.
2. **First model connection (implemented; live generation blocked by provider availability):**
   provider adapter interface, Gemini official REST API integration,
   server-side credentials, a chat endpoint, streaming, timeouts, and clear errors.
3. **Saved chat and basic frontend (implemented):** SQLite, migrations, conversations/messages,
   a simple HTML/CSS/JS chat page, and cancellation.
4. **Model connections and usage (implemented):** unlimited configured connections,
   manual chat selection, dedicated Settings and Usage pages, encrypted credentials,
   OpenRouter PKCE login and text adapters. Automatic routing is deliberately deferred.
5. **Manual budgets and cost estimates (implemented; user-confirmed scope):** user-entered
   prices, estimated costs, explicit manual monthly budgets and usage warnings.
   Keep model selection manual; estimates are not provider bills or quota guarantees.
6. **Routing and coordinated models (future):** ordered fallback, capability checks,
   cooldowns, shared quota pools, budget reservations, draft/review and bounded task
   splitting. Requires explicit policies and evaluations before automatic spending.

The scope was revised at the user's request: settings and basic usage moved into
Phase 4; automatic model management remains deferred. Website subscriptions do
not automatically grant API access. See [Phase 4](PHASE_4.md), [the changelog](../CHANGELOG.md)
[Phase 5](PHASE_5.md) and [Git workflow](CONTRIBUTING.md). Live cloud success remains unverified.
