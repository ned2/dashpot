# Changelog

## 0.1.0 — First release (not yet published)

Dashpot's first alpha release provides a terminal view of declared Issue work,
Git Repository state, Pull Requests, and active coding-agent sessions.

- Observe GitHub Issues or Local Issue Markdown, with complete profiles,
  freshness, and actionable Diagnostics.
- List the Ready Issues — open, with no blocker still open — from the Issue
  lifecycle selector or `dashpot issue list --state ready`, and see what each
  open Issue waits on in the `WAITING ON` column, with waiting rows dimmed.
- Inspect Worktrees, local and Remote-Tracking Branches, integration state,
  and GitHub Pull Requests. Fetch explicitly; preview and confirm Cleanup.
- Observe Codex and Claude Code through opt-in hooks, and declare Issue work
  through a Project-local Work Store and the bundled Issue-work skill.
- Read the Event Log with `dashpot events`, merged across a Repository's
  Worktrees and filtered by Agent Session, Issue, Project, time or level; see
  an Agent Session's recent outcomes in `dashpot work show`; and remove old
  Event Log files with `dashpot events remove --before DATE`. The dashboard
  warns with an `event-log-large` Diagnostic past 200 MB.
- Install as an isolated Python application with `uv tool install dashpot`.
  Hook publishers work when their installation path contains spaces or shell
  metacharacters. `dashpot integrate` refuses to bind the hooks to a publisher
  inside a linked Worktree, whose removal would break every hook event, and
  `--status` warns about such a binding while its file still exists.
- Keep an Agent Run whose session ended without `SessionEnd` listed as
  orphaned (`orphaned`, `hostRestarted` in JSON) rather than as a Diagnostic,
  and continue it when its Claude Code session resumes at the same Worktree.

This release establishes the first compatibility baseline. Documented commands,
JSON key sets and semantics, Local Issue Markdown, and `.dashpot/config.json`
remain compatible within 0.1.x. Breaking changes require a new minor version and
release notes. Python internals and exact terminal layout are not extension
interfaces.

The release targets Linux x86-64 and Apple Silicon macOS, CPython 3.12–3.14,
Git 2.39+, and gh 2.100.0+ for GitHub-backed Projects. See
[installation and support](docs/installation.md) for the required host/harness
acceptance and [the release checklist](docs/releasing.md) for publication gates.
