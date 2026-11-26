# Phase 7: cooldowns, shared groups and routing controls

Phase 7 extends opt-in fallback without changing advisory budgets.

## Configure

In Settings, edit a connection to set **Shared usage group**. Use exactly the same
label for connections sharing a provider account/quota. Leaving it blank isolates
cooldowns to that connection. Group labels are user declarations, not provider quota
introspection. The Usage page shows all-time group totals and remaining cooldowns,
independent of date filters. Each usage row snapshots the group at request time.

**Allow as a fallback destination** controls whether an opted-in chain can use the
connection. It does not disable manually selecting that model. An order containing
a prohibited destination is rejected before sending any prompts.

Chat has a **Local endpoints only for this session** checkbox. It checks the primary
and every fallback destination before starting. Only Ollama/compatible endpoints
using localhost, host.docker.internal or literal private/loopback IP addresses are
accepted. Redirects are disabled. This is an endpoint restriction, not an offline
firewall: a trusted local gateway can itself forward requests externally. The option
resets on page reload and is sent explicitly on every request; existing chats do
not acquire a permanent privacy policy.

## Cooldown policy

A provider 429 starts a persistent cooldown for its connection or shared group.
Retry-After seconds and HTTP dates are recognized; invalid/missing values use 60
seconds. Delays are bounded to 1–86,400 seconds. A longer existing cooldown is not
shortened by another rate-limit response. Restarting the app preserves cooldowns.

Subsequent attempts during the cooldown are recorded as **skipped**, with no
upstream request. Opted-in fallback can continue to a different eligible connection;
connections in the same group are also skipped. Manual requests receive a clear
cooldown error. No waiting loops or automatic background retries are introduced.
Changing a group does not revoke in-flight requests; configure actual quota sharing
correctly rather than rotating labels to bypass limits. Simultaneous requests that
started before the first rate-limit response cannot be recalled.

## Attempts and diagnostics

Expand **Model attempts** under an answer to inspect ordered connections, statuses
and sanitized error reasons. The selected primary and actual responding model remain
separate. Attempt records are linked to messages by the chain ID. Legacy messages
without IDs have no reconstructed attempt history.

Authentication failures, rejected model/parameter requests, quota/rate limits,
cooldowns, timeouts and provider availability failures have distinct diagnostic
codes. Providers sometimes combine exhausted quota and transient rate limits under
429, or invalid model/parameters under 400/404; CombineLLM does not pretend to know
more than that status establishes. Raw response bodies and credentials are not
exposed. An unavailable service is not proof that the app itself is broken.

Usage includes skipped rows separately. Unknown token/cost data remains unknown;
shared groups do not estimate remaining free credits or implement hard spending caps.

## API, storage and validation

Connections add `usage_group` and `allow_fallback`. Chat requests add `local_only`.
`GET /api/v1/usage-groups` returns all-time group totals and current cooldown seconds.
SQLite schema 5 adds persistent cooldowns, group snapshots and message-to-attempt
links. Back up the database and matching key before upgrading.

Tests use isolated databases and simulated providers, including shared cooldown
persistence, zero network calls when skipped, retry timing and routing preflight.
Existing migration, cancellation, fallback and cost tests remain covered. The user
reported a successful live Groq response before this phase; no live paid calls are
required for Phase 7 validation. Hard budgets, capability discovery and coordinated
model tasks remain future work.

Release validation: the 77-test suite passed, followed by one new targeted
integration test for saved attempt details and shared-group totals (78 passing
cases in total). Required lint, format, JavaScript syntax and Compose checks passed.
The database and key were backed up before migration; the rebuilt container is
healthy. No live cloud requests were made for this phase.
