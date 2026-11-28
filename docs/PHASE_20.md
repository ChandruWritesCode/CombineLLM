# Phase 20: compact routing and profiles

The **Model & routing** section in chat now starts folded and remembers whether
you open it in this browser. Its summary shows the selected model or automatic
profile. Open it to change model, task focus, local-only mode, fallback, and
coordination. **Compare my models** remains a separate foldable section.

## Routing profiles

In **Settings → Routing profiles**, save up to eight named profiles. Choose a
workflow, ranking priority, maximum calls, and optional maximum **estimated**
cost in USD. The fixed workflows are one model (1 call), draft/review/revise
(3 calls), and plan/two subtasks/synthesis (4 calls). The call maximum must
cover the selected workflow. The split workflow asks the first model for exactly
two bounded subtasks, sends them to the chosen models, then asks the first model
for one final answer. Each step appears in Usage and may consume quota or credits.

In chat, enable **Choose a model automatically**, select a profile, and review
the preview. It shows chosen models, planned call count, and a cost estimate if
both input and output prices are entered. The plan is checked again when the
message is sent, using the full saved conversation. A profile with a cost limit
is rejected before any model call if a required rate is missing or the estimate
exceeds its limit. This is a preflight estimate from user-entered prices and
approximate token counts; provider billing, hidden tokens, and pricing changes
can differ. Individual monthly request ceilings may stop later calls in a
multi-step workflow. There is no automatic retry or fallback in a profile.
Profile turns use the configured model output limits; a per-turn output override
is rejected so the estimate and plan stay consistent.

`GET /api/v1/routing/preview` is read-only. The profile's name is sent with
`routing_profile` and `auto_select: true` on saved-chat turns. `PUT /api/v1/settings`
stores profiles with workspace preferences. Older settings remain compatible.

## Provider quota signals

Usage shows the last observed remaining-request and remaining-token headers,
plus a provider-supplied reset duration when available. The app stores only
parsed counts and times, never raw headers or credentials. It flags a recent
reported zero-request balance in model comparison but treats the observation
as advisory; providers define different windows, and a prior response cannot
prove current account balance. Missing headers mean unknown. Existing 429
cooldowns still apply. Groq's documented response headers are one example:
[Groq rate limits](https://console.groq.com/docs/rate-limits).

All data remains in the local SQLite database. Run one backend process for each
database. No new migration is required because profiles use workspace settings
and quota observations use existing preference storage.

## Validation

Simulated provider tests verify header sanitization, saved quota observations,
read-only previews, four-call split generation, and cost-limit rejection before
provider use. All 108 isolated tests passed. Ruff lint and format, JavaScript
syntax, and Docker Compose configuration passed. The rebuilt container became
healthy, and browser review confirmed the compact chat controls, profile form,
and quota panel. No live cloud response was verified in this phase.
