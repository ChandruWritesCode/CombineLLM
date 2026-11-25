# Phase 2: first model connection

This phase adds a Gemini adapter behind a provider-neutral interface, text chat,
streaming, input validation, timeouts, and sanitized provider errors. The API is
stateless: send the conversation history with each request. No automatic retries,
fallbacks, usage database, or budget enforcement are implemented yet.

## 1. Configure Gemini in VS Code

Open the root `.env` file. Keep your existing app settings and port, and add:

```dotenv
COMBINELLM_GEMINI_API_KEY=your-key-here
COMBINELLM_GEMINI_MODEL=your-text-model-id
COMBINELLM_PROVIDER_TIMEOUT_SECONDS=60
```

Replace both placeholders. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey)
and choose an available text model using the [official model catalog](https://ai.google.dev/gemini-api/docs/models).
Use the model ID without the `models/` prefix. Model availability and free allowances
depend on your account; the application does not guarantee that a request is free.
Check your provider's billing settings before sending prompts.

Keep the key in `.env`, which is ignored by Git and excluded from the Docker image.
Do not paste it into chat requests, screenshots, or source code. The backend sends
the key in a header to the fixed official Google API endpoint. It never returns
the key through its status API. Local `.env` storage is plaintext; an encrypted
credential store is not part of this phase.

Prompts and supplied history are sent to Google. Self-hosting the backend does not
make cloud inference local. Keep the application's localhost-only binding.

## 2. Restart the backend

From the VS Code terminal in the project root:

```bash
docker compose up --build -d --wait
```

Your current workspace uses port 8001. Open <http://localhost:8001/docs>.
If developing natively, restart the server or debugger after editing `.env` and
use port 8002 instead. A source-code reload does not reliably pick up `.env` edits.

Call `GET /api/v1/providers`. `configured: true` means both settings are present;
it does not verify that the key works or that the model has quota. No remote call
is made by this endpoint. To check the integration, send a short chat request.

## 3. Send a message

In the API docs, expand `POST /api/v1/chat`, select **Try it out**, and use:

```json
{
  "provider": "gemini",
  "messages": [{"role": "user", "content": "Say hello in one sentence."}],
  "max_output_tokens": 256,
  "stream": false
}
```

Or run:

```bash
curl --fail-with-body http://localhost:8001/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Say hello in one sentence."}],"max_output_tokens":256}'
```

The JSON response includes `provider`, `model`, `content`, `finish_reason`, and
`usage`. Usage contains provider-reported input, output, reasoning, and total
tokens; unavailable counts are `null`. These are not cost estimates. Total tokens
can include reasoning tokens as well as the displayed answer.

`STOP` means the model finished; `MAX_TOKENS` means the response hit the requested
limit and may be truncated. Thinking models can use output capacity for reasoning,
so a very small output allowance can produce no visible answer. Increase the limit
if you receive `incomplete_response` for an otherwise valid request.

## 4. Send conversation history

```json
{
  "system": "Use short, clear explanations.",
  "messages": [
    {"role": "user", "content": "What is FastAPI?"},
    {"role": "assistant", "content": "FastAPI is a Python framework for building APIs."},
    {"role": "user", "content": "How does it help this project?"}
  ]
}
```

History must alternate user and assistant messages, starting and ending with user.
The optional system instruction is separate. The server accepts up to 100 messages,
50,000 characters per message, and 100,000 characters of total input. Provider
context limits may be lower. Requested output is between 1 and 8,192 tokens.

## 5. Stream a response

Swagger's documentation page may buffer streaming output. Use a terminal to see
incremental events:

```bash
curl -N http://localhost:8001/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Explain API routing briefly."}],"stream":true}'
```

The response uses Server-Sent Events:

```text
event: delta
data: {"content": "API routing "}

event: delta
data: {"content": "directs requests to handlers."}

event: done
data: {"provider":"gemini","model":"configured-model","finish_reason":"STOP","usage":{"input_tokens":12,"output_tokens":8,"reasoning_tokens":0,"total_tokens":20}}
```

The sample above is illustrative, not a live model response. Concatenate `delta`
content in order. Only `done` confirms completion. If the provider fails after
streaming has started, an `error` event ends the stream without `done`; HTTP status
is already 200 at that point. Treat accumulated text as incomplete. A future web
frontend should use streaming `fetch` for this POST endpoint, not `EventSource`.

## Errors

Before streaming starts, errors return `{"error":{"code":"...","message":"..."}}`:

| HTTP status | Code | Action |
| --- | --- | --- |
| 503 | `provider_not_configured` | Set key and model, then restart |
| 502 | `provider_auth_error` | Check key permissions and model access |
| 429 | `provider_rate_limited` | Check quota or wait before retrying |
| 504 | `provider_timeout` | Retry later or adjust the timeout |
| 502 | `provider_request_rejected` | Check model ID and request limits |
| 502 | `provider_unavailable` | Check connectivity or provider status |
| 422 | `content_blocked` | Provider declined the request or response |
| 502 | `invalid_response` / `incomplete_response` | Provider returned unusable output |

Invalid local inputs return FastAPI's usual HTTP 422 `detail` response. Raw provider
error bodies and exception messages are not returned, to avoid leaking credentials
or request details. The adapter does not retry failed requests automatically.

## Validation

Tests use a simulated HTTP transport: no real API keys or paid calls are needed.
They cover request translation, history, usage, normal and streaming responses,
missing settings, validation, upstream errors, blocked and malformed results,
timeouts, incomplete streams, and upstream resource cleanup.

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
docker compose config --quiet
```

The integration follows the official [Gemini content generation API](https://ai.google.dev/api/generate-content).
