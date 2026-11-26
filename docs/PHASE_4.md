# Phase 4: model connections, settings, and usage

Phase 4 adds manually selected model connections. There is no automatic fallback,
quota rotation, task splitting, or model routing.

## Setup

Open **Settings** from the chat sidebar and choose **Add model connection**. Enter a
label, provider, exact model ID available to your account, and API key. You can add
multiple models from the same provider, with separate credentials and options.
Select a workspace default or choose a model in chat before sending.

Supported text adapters: Gemini, OpenAI Chat Completions, Anthropic Messages,
OpenRouter, Ollama's OpenAI-compatible endpoint, and custom compatible endpoints.
Compatibility depends on the server/model; images, tools, audio and reasoning-only
responses are not supported. OpenAI models can require `max_completion_tokens`;
select that option in the model editor. Leave temperature unset for models that
reject it. Disable streaming usage reporting for compatible servers that reject
`stream_options`. A saved configuration does not prove provider availability.

**Test connection** sends a short real request and can consume quota or credits.
Failures have sanitized messages and are recorded in Usage. Automated tests instead
simulate providers; no live cloud generation or live account login was verified
for this release.

## Account login

OpenRouter connections offer **Connect account**, using its official PKCE flow.
The server exchanges the authorization code and stores the issued key. Configure
`COMBINELLM_PUBLIC_BASE_URL` to the exact browser origin (same hostname and port).
Compose sets this from `COMBINELLM_PORT`; native development on 8002 needs
`http://localhost:8002`. Start and finish in the same browser within ten minutes.
A restart expires pending logins. Access logs are disabled in supplied launch
commands so callback codes are not logged; configure reverse proxies similarly.

Other providers use API keys; their consumer website logins are not supported.
ChatGPT, Claude, Gemini and other website subscriptions do not automatically grant
API access. OpenRouter login does not guarantee free models or credits. Review
access and billing with the provider. The implementation follows the
[OpenRouter PKCE documentation](https://openrouter.ai/docs/guides/overview/auth/oauth).

## Local inference

For native Ollama use `http://localhost:11434/v1`. From Docker use
`http://host.docker.internal:11434/v1`; the host server must listen on an interface
reachable from Docker. Restrict access with your local firewall. Supply a model
already installed in Ollama. Local compatible services may omit credentials.
Public custom endpoints require HTTPS. A custom endpoint receives the selected
credential and conversation, so use a server you trust.

## Settings and chat behavior

Per-model options include enable/disable, model ID, timeout, output limit, system
prompt, optional temperature, usage reporting and output-token parameter name.
Workspace defaults include selected model, system prompt, and output limit for
newly created connections. Model system prompts override the workspace prompt.
A blank API key on edit retains the saved key; **Clear saved credential** removes
it. Changing provider or endpoint requires replacing or clearing the credential.

Each saved chat remembers its last selected model. Changing it sends completed
conversation history to the newly selected provider. Deleted or disabled models
require an explicit new selection; there is no silent fallback. Existing failed
or cancelled turns remain visible and are excluded from future context.

Existing Gemini `.env` configuration is imported once per database. After import,
edit the model in Settings; changing `.env` does not overwrite your saved settings.
Deleting a connection preserves chat history and usage. Revoking an issued key
requires doing so in the provider's account as well.

## Usage and privacy

The dedicated Usage page shows attempts, completions, failures, reported tokens,
unknown usage, per-model totals and the latest 100 attempts. Filter by UTC dates
and model; CSV export contains all matching attempts. Labels/model IDs are saved
at request time. Renaming a connection can produce separate historical groups.
Tests from Settings count as attempts too. Tracking starts with Phase 4; historical
Phase 3 messages are not backfilled. It covers requests through this installation,
not account-wide quota, other apps, actual bills or remaining free allowances.
Missing token counts remain unknown, never presented as known zero usage.

Credentials are encrypted with a local Fernet key next to the database. This helps
protect a database copied without its key, not an attacker with access to the
whole machine. Back up and restore both files together; see [Operations](OPERATIONS.md).
API responses never return saved keys. Keep the app bound to loopback; it has no
user authentication and is intended for one trusted local user. Use one backend
process per database. Cross-origin browser writes are rejected.

## API

- `GET/POST /api/v1/models`: list or add connections.
- `PUT/DELETE /api/v1/models/{id}`: replace configuration or delete.
- `POST /api/v1/models/{id}/test`: real connection test.
- `GET/PUT /api/v1/settings`: workspace defaults.
- `GET /api/v1/usage` and `/usage/export`: optional `start`, `end`, `model_id` filters.
- Chat requests accept `model_id`; saved chat requests otherwise reuse the chat's
  selection, then the workspace default. The legacy stateless `provider` field
  remains Gemini-only for compatibility; `model_id` determines the actual adapter.
- OpenRouter login: POST `/api/v1/oauth/openrouter/{id}/start`, then follow the
  returned URL in the same browser.

## Validation

Provider fixtures exercise streamed OpenAI-compatible, Ollama and Anthropic text;
existing Gemini and saved-chat tests remain in place. Registry tests cover secret
redaction, encrypted storage, endpoint changes, selection failures and multiple
connections. Other checks cover PKCE exchange/replay, usage filtering/export,
v1-to-v2 history migration, and backup restoration with the matching encryption key.
