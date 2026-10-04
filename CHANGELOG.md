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
- Observe Codex and Claude Code through opt-in hooks, and OpenCode v2
  through an opt-in plugin. OpenCode is supported at 2.0.22 on Linux, the
  release its acceptance run passed on; the plugin warns on another 2.x
  release and refuses OpenCode v1. Declare Issue work through a
  Project-local Work Store and the bundled Issue-work skill.
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
- `dashpot integrate <harness>` installs, updates and removes every agent
  skill Dashpot bundles, and `--status` reports each one as installed,
  missing, or with an update available. A directory of a bundled skill's name
  that Dashpot did not write is reported and never overwritten or removed.
- `dashpot integrate opencode` also installs, updates, checks and removes the
  `dashpot-worker` OpenCode agent, whose permissions deny `*session_move` so
  that a worker Sub-agent the `dashpot-execute-issues` skill launches cannot
  move its lead's session by mistake. An agent file of that name that Dashpot
  did not write is reported and never overwritten or removed.
- Ship the user-invoked `dashpot-execute-issues` skill, which `integrate`
  installs for Claude Code, Codex and OpenCode. A lead session lands an arc
  of GitHub Issues through background workers, one Issue Worktree each,
  quoting the repository's own gates and review process into each worker's
  brief and recording the arc in Issue comments. It merges only when the
  user grants it, and bundles a reviewer prompt for repositories that name
  no review process.
- Keep an Agent Run whose session ended without `SessionEnd` listed as
  orphaned (`orphaned`, `hostRestarted` in JSON) rather than as a Diagnostic,
  and continue it when its Claude Code session resumes at the same Worktree.
- Carry a Codex session's Agent Run to the Worktree its next turn runs in,
  with its identity, `startedAt` and Issue Binding, when the same Codex
  process moved it; report a run left behind as `work-session-elsewhere`.
  Codex sub-agents hold their session running and block Worktree Cleanup
  like Claude Code's; rerun `dashpot integrate codex` to subscribe them.
  `dashpot work show` lists the sub-agents holding a run running, and it and
  the `sub-agent` blocker say one may have been interrupted without Codex
  reporting its stop, and how to end the session if none is still working.
- Support Codex `codex-cli` 0.160.0 on Linux in each measured hosting mode:
  the managed daemon a plain terminal starts, an App Server with attached
  clients, a standalone terminal, and `codex exec`. A real-harness acceptance
  run checks this support on a release bump.
- Keep a Codex Agent Run orphaned, recoverable with `dashpot work start`,
  when its managed daemon is stopped or restarted; an idle unload, a `codex
  exec` exit and a standalone `/exit` still end it.
- Read a Host Process's whole command line when its hooks inherit a narrow
  `COLUMNS`, which had cut a managed Codex daemon's `--managed-daemon` flag
  and could misclassify any Host Process whose adapter reads its arguments.

This release establishes the first compatibility baseline. Documented commands,
JSON key sets and semantics, Local Issue Markdown, and `.dashpot/config.json`
remain compatible within 0.1.x. Breaking changes require a new minor version and
release notes. Python internals and exact terminal layout are not extension
interfaces.

The release targets Linux x86-64 and Apple Silicon macOS, CPython 3.12–3.14,
Git 2.39+, and gh 2.100.0+ for GitHub-backed Projects. See
[installation and support](docs/installation.md) for the required host/harness
acceptance and [the release checklist](docs/releasing.md) for publication gates.
