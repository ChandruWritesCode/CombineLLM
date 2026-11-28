# Phase 19: release readiness

**Settings → Local status** reports whether the local database passes a quick
integrity check, plus saved conversation and model counts, credential-key presence
and active replies. **Check again** refreshes it. A local copy of the Operations
guide is available from Settings, including in Docker. This is local diagnostics only;
it does not test provider credentials, quotas or cloud availability. The API route
is `GET /api/v1/diagnostics` and returns no secret values or filesystem paths.

The backup utility still makes a consistent SQLite copy and copies the matching
`.key` file. The new restore command verifies SQLite integrity, checks the
supported schema and tests whether that key can decrypt saved credentials. Given
only a backup path, it verifies without writing. Given a second, new destination
path, it copies both files there with private permissions. It refuses existing
destinations and never replaces the active database. For a live recovery, stop the
backend and follow [Operations](OPERATIONS.md) to switch to the restored pair.

```bash
uv run python -m scripts.restore backups/chat-backup.sqlite3
uv run python -m scripts.restore backups/chat-backup.sqlite3 data/restored.sqlite3
```

Treat backups as private; they contain conversation text and encrypted credentials.
Only restore backups you trust. See [Operations](OPERATIONS.md) for Docker commands
and recovery precautions.

## Validation

Isolated tests cover local diagnostics, a restored chat and credential, refusal
to overwrite, wrong-key rejection and invalid database rejection. All 105 tests
passed. Ruff lint and format, JavaScript syntax, and Docker Compose configuration
passed. The saved pre-migration backup verified with its matching key. The rebuilt
container became healthy, and browser review confirmed the Local status panel and
bundled recovery guide. No live cloud request was made for this phase.
