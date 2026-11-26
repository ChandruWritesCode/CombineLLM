# Phase 3 — saved conversations and local frontend

## Scope

The backend now serves a plain HTML/CSS/JavaScript chat UI at `/`. SQLite stores
conversations, user prompts, assistant responses, status, and provider-reported
usage. No frontend build tools or third-party assets are required.

The old stateless `POST /api/v1/chat` still works. Service metadata moved from `/`
to `GET /api/v1`; the root now serves the chat page.

## Using the workspace

1. Open the chat page and choose **New conversation**, or type your first prompt.
2. Press **Send message** or Enter. Shift+Enter adds a new line.
3. Watch the response appear. **Stop response** cancels the backend task.
4. Select a saved conversation to reopen it. Refreshing preserves history and
   reattaches to an in-progress response.
5. Use **Rename** to change a title. **Delete** confirms before removing the entire
   conversation, including its messages and any active generation.
6. After a failure, **Reuse prompt** copies the earlier prompt into the composer.
   Edit it if desired and send again. This creates a new turn, not a hidden retry.

The provider badge means settings are present; it is not a claim that Google is
reachable or quota is available. Provider errors appear directly under the saved
assistant message. Partial failed output is retained and clearly labeled.

Plain text is rendered using `textContent`, including code and Markdown. Rich
Markdown rendering, attachments, system-prompt editing, search, and pagination are
not included in this release. Text cannot inject HTML or scripts into the page.
The page never receives an API key.

## Conversation endpoints

All paths below start with `/api/v1/conversations`.

| Method and path | Purpose | Result |
| --- | --- | --- |
| `GET /` (without trailing slash preferred) | List conversations, newest activity first | 200 list |
| `POST /` | Create using `{"title":"Optional title"}` or `{}` | 201 conversation |
| `GET /{id}` | Get conversation and ordered messages | 200 conversation |
| `PATCH /{id}` | Rename with `{"title":"New name"}` | 200 conversation |
| `DELETE /{id}` | Cancel generation and delete with cascading messages | 204 |
| `POST /{id}/messages` | Start a saved turn | 202 task identifier |
| `GET /{id}/messages/{message_id}/events` | Observe persisted response snapshots | SSE |
| `POST /{id}/messages/{message_id}/cancel` | Stop response; safe to repeat | 200 message |

Create and send from a terminal:

```bash
curl http://localhost:8001/api/v1/conversations \
  -H 'Content-Type: application/json' -d '{"title":"My project"}'

# Replace CONVERSATION_ID with the id from the response.
curl http://localhost:8001/api/v1/conversations/CONVERSATION_ID/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"Help me plan a small project.","max_output_tokens":2048}'
```

The second call returns `message_id` and `conversation_id`. A 202 means the prompt
is saved and generation was scheduled, not that the provider succeeded. Inspect
the conversation or subscribe to its event endpoint to learn the final outcome.
One active generation per conversation is allowed; a second gets HTTP 409.

## Streaming and status

The saved-chat SSE endpoint emits `event: message` with the **full current message
snapshot**, not a token delta. Replace the displayed content; do not append snapshots.
It checks storage every 200 ms and sends only changed snapshots. `event: done`
reports the terminal status; success specifically requires `status: complete`.
`event: removed` indicates deletion. EventSource can reconnect safely because the
current snapshot is replayed. Closing the browser stream does not cancel the task;
use the explicit cancellation endpoint.

| Status | Meaning |
| --- | --- |
| `streaming` | Generation queued or in progress |
| `complete` | Provider emitted its completion event |
| `failed` | Provider or internal generation error; partial content may exist |
| `cancelled` | Explicit stop, deletion, or graceful backend shutdown |
| `interrupted` | Backend restarted with an unfinished stored response |

`MAX_TOKENS` is a completed provider call whose output may be truncated; the UI
labels it accordingly. Successful turn pairs form future model context. Failed,
cancelled, or interrupted pairs are excluded, but remain visible in history.
There is no hidden history summarization: once existing request limits are exceeded,
the request is rejected and the user should start a new conversation.

## Acceptance and limits

Automated tests cover persistence across app instances, rename/delete, cascading
deletion, failed history exclusion, cancellation, concurrent-turn rejection,
migration recovery, isolated test databases, SSE snapshots, and frontend delivery.
Adapter tests continue to use simulated provider responses. A live model answer
is not a prerequisite for saving chats or validating the application locally.

This is a single-user, single-process implementation. It does not include account
security, multi-worker coordination, provider fallback, cost budgets, or a full
usage ledger. Persisted usage is per successful saved answer, not total billing.
