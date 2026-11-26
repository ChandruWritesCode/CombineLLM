# Development and Git workflow

## Phase-based history

This repository was initialized during Phase 3, at the user's request. Phase 1 and
Phase 2 commits are reconstructed baselines of the earlier work, not commits made
at those original times. Phase 2 backend source was recovered from the previously
running container; supporting files and Phase 1 were reconstructed from the earlier
project versions. Phase 3 records the saved-chat implementation and documentation.

Use one clear milestone commit per completed phase. Additional fixes may have their
own focused commits; do not rewrite published history merely to preserve a count.
Tag completed milestones `phase-1`, `phase-2`, and `phase-3` for easy inspection.
The user has requested a GitHub push at every completed phase. Once `origin` is
configured, push the completed phase commit and its explicit milestone tag after
validation. Verify the remote revision; do not describe a local commit as published.
If access is unavailable, finish the local commit and report what remains unpushed.

```bash
git log --oneline --decorate
git show phase-2 --stat
git diff phase-2..phase-3 --stat
```

For a newly completed phase, after reviewing and committing the changes:

```bash
git tag phase-N
git push origin main
git push origin phase-N
```

Replace `N` with the phase number. Preserve existing tags and remote history; never
force-push as part of this workflow. Follow branch protection if the remote requires
a pull request instead of a direct push. Keep GitHub credentials out of remote URLs.

Avoid switching phases with a live server running. Back up data first: older phases
do not necessarily understand newer database schemas.

## Before a commit

1. Run the checks documented in the README.
2. Exercise the affected UI/API behavior, including errors.
3. Update the phase guide, roadmap, and changelog when behavior changes.
4. Review `git diff --cached` and `git status --short`.
5. Ensure `.env`, credentials, database files, backups, caches, and virtual
   environments are not staged. Do not use force-add on ignored runtime files.

Commit messages should describe the completed outcome, for example:
`feat(phase-3): persist conversations and add local chat workspace`.

## Testing without provider availability

Adapter tests use `httpx.MockTransport`. Saved-chat tests override the provider
with deterministic async events, including failures and delays for cancellation.
Tests use temporary SQLite files and must never touch a user's history or API key.
Real provider smoke tests require explicit configuration and can consume quota.

Changes to streaming must check success, failure before/after partial output,
resource cleanup, cancellation, and refresh/reconnect behavior. Database changes
must check migration from the preceding version and preservation of existing rows.
