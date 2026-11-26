# Phase 6: opt-in ordered fallback

Phase 6 completes the ordered-fallback feature. Model coordination and task
splitting are separate future phases. Manual selection remains the default.

## Configure and use

1. Open **Settings → Workspace defaults → Optional fallback order**.
2. Choose up to three distinct enabled connections, in order, and save defaults.
3. In chat, select the primary model and explicitly check **Enable configured
   fallback for this chat session**. The page lists the fallback destinations.
4. Send a message. The primary is tried first; each remaining configured model is
   tried at most once. A primary also listed in the fallback order is skipped there.

The checkbox starts off, resets when switching conversations and resets on page
reload. Saving an order alone does not enable automatic requests. Connection tests
in Settings always test only the chosen connection. Existing connections and
workspace defaults are not automatically enrolled in fallback.

Enabling fallback authorizes the same conversation history and instruction to be
sent to the configured providers. Each attempt can consume credits or free quota.
**Phase 5 budgets remain advisory and do not cap spending.** Zero entered prices do
not establish provider free-tier eligibility. Local-to-cloud fallback happens only
if you explicitly configure cloud connections and enable this option.

## Exact policy

- Retryable failures: provider rate limit, availability/network failure, or timeout.
- Fallback is allowed only before any nonempty answer text is emitted.
- No fallback for authentication/configuration errors, rejected requests, content
  blocks, malformed/incomplete responses, or unsupported outputs.
- No retry of the same connection, recursive chains, or delay/cooldown loops.
- At most four attempts (primary plus three configured fallbacks), with an overall
  120-second deadline as well as each adapter's own timeout. A primary consuming
  the whole deadline leaves no time for fallback.
- Stop/cancellation closes the active stream and never starts another attempt.
- Exhaustion returns the final provider error. Partial output remains visible and
  is never spliced together with another provider's output.
- All configured destinations are validated before the first attempt. A disabled
  destination rejects the request until you update Settings; no silent skipping.
  Deleting a model removes it from the saved fallback order.
- Configurations/credentials are snapshotted at request admission; changes in another
  tab apply to subsequent requests. Stop an active response to cancel its chain.

All supported adapters are text-only for this phase. The primary's effective
system instruction and completed history are reused across attempts. A fallback's
output limit can lower, but not raise, the request's limit. The answer identifies
the provider/model that actually responded. The conversation keeps the user's
chosen primary for subsequent requests.

## Usage and API

Every actual attempt has its own usage/cost row. Related rows share
`attempt_group_id` and have sequential `attempt_number` values, visible in recent
usage and CSV. Counts on Usage are attempts, not unique prompts. Unknown usage from
failed attempts stays unknown; only known costs are summed. Prices are snapshotted
per connection and Phase 5 accounting rules are unchanged.

Both `POST /api/v1/chat` and saved-chat message creation accept `fallback: true`.
Omitting it keeps manual behavior. Configure the ordered `fallback_model_ids` list
through `PUT /api/v1/settings`. Stateless streamed completion events report the
actual responding model, as do saved answers. SQLite schema 4 adds nullable attempt
group/number columns without rewriting earlier usage or costs.

## Validation and limits

Simulated tests cover successful fallback, manual default, final model attribution,
full-chain failure, no fallback after partial output or nontransient errors,
cancellation, overall deadline, settings validation and schema 3 migration.
Provider availability is still external; passing tests does not establish a working
cloud account. No live requests are needed for this regression suite.

Hard spending caps, provider-wide quota pools, cooldowns, capability discovery,
intelligent routing, draft/review and multi-model task synthesis remain outside this
completed phase. Do not use advisory budgets as a substitute for provider-side
spending controls.

Release verification: 74 tests passed, including the new fallback and migration
cases. Ruff lint/format, JavaScript syntax and Compose checks passed. An isolated
browser preview confirmed fallback from a simulated rate limit to a successful
second model, correct attribution, shared attempt groups and reset to manual mode
after reload. The production database/key were backed up before migration and the
rebuilt Docker container is healthy. No live cloud requests were repeated.
