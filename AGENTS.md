# CombineLLM project instructions

- Keep the application local and self-hostable. Use one backend process per SQLite
  database until shared generation ownership is implemented.
- At each completed phase, update README, the phase guide, roadmap, and changelog.
- Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`,
  `node --check app/static/app.js`, and `docker compose config --quiet` when applicable.
  Provider tests must use simulated responses and isolated databases.
- The user requests phase-wise Git commits and GitHub pushes. Commit each completed
  milestone, tag it `phase-N`, and push the branch and that tag to the configured
  GitHub remote after checks pass. Verify remote revisions. If no destination or
  connection is available, finish the local commit and report the missing prerequisite.
  Do not force-push, move existing tags, or overwrite remote history.
- Never commit `.env`, real credentials, local databases, backups, or virtual
  environments. Review staged files and avoid logging provider secrets.
- Do not treat a passing local test or configured key as proof of live provider
  availability. State whether cloud responses were actually verified.
- See `docs/CONTRIBUTING.md` for the history and release workflow.
