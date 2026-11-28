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
6. **Ordered fallback (implemented):** opt-in primary plus up to three fallback
   connections, transient pre-output failures only, 120-second total deadline,
   per-attempt accounting and accurate response attribution. Manual mode remains default.
7. **Routing controls (implemented):** persistent shared cooldowns, usage groups,
   fallback permissions, local endpoint restrictions and chat attempt history.
   Capability discovery and hard-budget reservations remain future work.
8. **Provider discovery and guided setup (implemented):** dated curated directory,
   free/trial/local classifications, official links and prefilled setup walkthroughs.
9. **Interface and usability refresh (implemented):** vibrant colors, responsive
   layouts, accessible navigation, reduced-motion support and copy actions.
10. **Coordinated models (implemented):** opt-in draft/review/revision and two-subtask
    synthesis, per-step usage and cost estimates, and saved answer ratings.
11. **Appearance themes (implemented):** five browser-side choices including the
    original vibrant palette, a light palette, and a system-following option.
12. **Usage-aware suggestions (implemented):** show model comparison from manual
    rates, recent local outcomes, advisory budgets, cooldowns and endpoint policy.
13. **Guarded automatic selection (implemented):** opt-in one-request model choice
    from the Phase 12 ranking, with clear attribution and no hidden provider calls.
14. **Spending guardrails (planned):** optional local request ceilings with clear
    limits, while preserving provider-side billing as the source of truth.

The scope was revised at the user's request: settings and basic usage moved into
Phase 4; ordered fallback and coordination are opt-in. Website subscriptions do
not automatically grant API access. See [Phase 4](PHASE_4.md), [the changelog](../CHANGELOG.md)
[Phase 5](PHASE_5.md), [Phase 6](PHASE_6.md) and [Git workflow](CONTRIBUTING.md). The user reported successful live Groq generation after Phase 6.
