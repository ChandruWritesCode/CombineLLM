# Operations and troubleshooting

## Start, inspect, and stop

```bash
docker compose up --build -d --wait
docker compose ps
docker compose logs --tail=100 backend
docker compose down
```

Normal shutdown/rebuild preserves the named `chat_data` volume. **`docker compose
down -v` deletes that volume and its conversations.** Native development instead
uses `data/combinellm.sqlite3`, or the configured database path.

## Backups

Backups contain private conversations and encrypted provider credentials. They are ignored by Git; keep them in a
location you control. Use a unique filename for every backup.

For native development, from the project root:

```bash
uv run python -m scripts.backup backups/chat-backup.sqlite3
```

For Docker (the utility is included in the image):

```bash
docker compose exec backend python -m scripts.backup /srv/combinellm/data/backup.sqlite3
docker compose cp backend:/srv/combinellm/data/backup.sqlite3 ./backups/chat-backup.sqlite3
```

Create `backups/` on the host first if needed. The backup utility uses SQLite's
online backup API to include committed WAL data. It refuses to overwrite an
existing destination. Backing up a running generation may capture it midway; on
restore that response becomes interrupted and can be sent again.

The utility also copies the adjacent `.key` file when present, using the backup
basename. Copy that file out of Docker as well, for example
`docker compose cp backend:/srv/combinellm/data/backup.key ./backups/chat-backup.key`.
Store it securely with its database; losing it makes credentials unreadable.

## Restore

Stop all processes using the target database first. Preserve the current database
and its `-wal` and `-shm` files together in a separate recovery directory. Do not
leave old sidecars beside the restored database. Copy the backup into the configured
database path and restore its matching `.key` file at the same basename. Ensure
the runtime user can write the directory and files; keep key permissions at 0600.
For Docker, use a one-off container with the existing named volume to perform this
copy, preserving UID 10001 ownership. Restart the backend and verify conversations
before deleting the recovery copy. Do not restore an untrusted database or an older
application over a newer schema. Ask for help if unsure which volume is active.

## Provider unavailable

`GET /api/v1/health` only confirms the backend process is alive. A configured badge
only confirms a key and model were supplied. Neither proves Google can answer.

Previously observed provider errors during this project's development:

- `gemini-2.5-flash` appeared in Google's model list, but generation returned 404
  explaining that it was unavailable to new users.
- Google's suggested `gemini-3.8-flash` returned 503 high demand.
- `gemini-3.1-flash-lite` also returned 503 high demand during testing.

These are observations, not permanent model availability claims. Consult Google
AI Studio for current access, billing, and quotas. This project does not bypass
limits or automatically rotate keys. It does not retry requests automatically.
Use **Reuse prompt** after the service recovers. Repeated requests may consume quota.

See [Phase 2 errors](PHASE_2.md#errors) for other cases. A live response remains
unverified if Google keeps returning errors; local simulated tests verify backend
behavior without claiming the cloud service is available.

## Other common issues

- **Settings unchanged:** edit saved models on the Settings page; environment Gemini
  credentials are imported only once. For server settings, restart the native server,
  or run `docker compose up -d`
  to recreate the container with updated environment values. Browser refresh alone
  does not reload server settings.
- **Port occupied:** change `COMBINELLM_PORT` for Docker; native development uses
  port 8002 in the supplied commands and debugger.
- **Different history in native/Docker:** they deliberately use different databases.
- **Backend restarted mid-answer:** partial text remains with cancelled/interrupted
  status. Reuse the prompt to start a new turn.
- **Conversation too large:** start a new conversation; context summarization is not
  implemented. A rejected turn is not partially inserted into storage.
- **Stream connection lost:** the browser reconnects to persisted snapshots. The
  backend task continues. Use Stop response to explicitly stop it.
- **Database permission error:** the container runs as UID 10001. Custom mounts must
  be writable by that user. Default named volumes are initialized by Docker.
- **Test warning about httpx:** upstream Starlette emits a deprecation warning for
  its test-client transport. Tests still pass; it does not affect provider requests.
