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
- Refuse to remove a Worktree while a process the person can see has its
  working directory inside it, such as a sub-agent's command, a background
  command, or a shell. The `process` blocker names each process. The host
  is read through `/proc` on Linux and `lsof` on macOS. When the processes
  could not all be read, as inside a sandbox, a removable Worktree's
  preview and `worktree check` report say so, and their JSON carries it as
  `uncheckedProcesses`.
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
- `dashpot events --json` prints JSON Lines, one Runtime Event per line under
  its Event Log field names, rather than one `{directories, events,
  unreadable}` document. Unreadable lines and files are reported on standard
  error only, and `directories` is gone. This breaks the earlier `--json`
  shape before the first release. `dashpot events remove --json` still prints
  one document.
- See a running dashboard's own recent Runtime Events on the Runtime screen,
  opened with `e` or from the command palette: filter them by kind, level or
  errors, follow new events or read back through them, and see every field
  of one. Its Stats tab, on `s`, shows what the dashboard spends on GitHub
  and how its refreshes run.
- Install as an isolated Python application with `uv tool install dashpot`.
  Hook publishers work when their installation path contains spaces or shell
  metacharacters. `dashpot integrate` refuses to bind the hooks to a publisher
  inside a linked Worktree, whose removal would break every hook event, and
  `--status` warns about such a binding while its file still exists.
- The Issue-work skill has a root OpenCode session move itself into the
  Issue's Worktree with OpenCode's own session move, carrying a bound Agent
  Run, and back to the main Worktree when the work is done, freeing the
  Issue Worktree for Cleanup. It confirms each move in its next step and
  hands off to a fresh session when a move fails. `integrate --status` now
  reports an Agent Session identity whose freshest hook record is in another
  Worktree as `elsewhere`, not confirmed.
- `dashpot integrate opencode --status` names a confirmed session's Host
  Process mode: the shared service, a `--standalone` client's private
  server, or unknown. A session moves itself, and a `dashpot-execute-issues`
  lead launches workers, only on the shared service; a `--standalone`
  session hands off instead, and a `--standalone` lead stops before any
  worker. Issue work itself stays supported in both modes.
- Document why a session in a linked Worktree can lack the main checkout's
  credentials, such as a direnv-supplied `GH_TOKEN`, which environment each
  measured Codex and OpenCode hosting gives an agent's commands, and two
  operator-local options: a Worktree Root `.envrc` and a launcher wrapper
  through direnv. The Issue-work skill says when `gh` keeps working across a
  Codex resume or an OpenCode move, and where to run an OpenCode handoff.
- `dashpot integrate <harness>` installs, updates and removes every agent
  skill Dashpot bundles, and `--status` reports each one as installed,
  missing, or with an update available. A directory of a bundled skill's name
  that Dashpot did not write, or one it cannot inspect, is reported and never
  overwritten or removed. A manifest in each managed copy keeps it to exactly
  the files this Dashpot ships across updates, and lets `--remove` take every
  file an earlier release shipped and none the user added.
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
- A lead assigns each worker to the Issue it implements with `dashpot work
  assign <issue> --worker <id> --worktree <path>`, and the Issues pane shows
  that Issue running while the lead's hooks report the worker working,
  without binding another Agent Run or changing the lead's. `work unassign`
  ends an assignment, `work show` lists them, and they end with the lead's
  run. The `dashpot-execute-issues` skill assigns its workers on every
  harness.
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
- Resolve a command a Codex sub-agent runs to its root Agent Session, by the
  `CODEX_SESSION_ID` its shell carries beside its own thread: `dashpot work
  show` lists that session's recent events, and `work start`, `relocate`,
  `stop`, `assign` and `unassign` refuse it as `delegated-session`, naming
  the sub-agent and its session, instead of finding no session at all.

This release establishes the first compatibility baseline. Documented commands,
JSON key sets and semantics, Local Issue Markdown, and `.dashpot/config.json`
remain compatible within 0.1.x. Breaking changes require a new minor version and
release notes. Python internals and exact terminal layout are not extension
interfaces.

The release targets Linux x86-64 and Apple Silicon macOS, CPython 3.13–3.14,
Git 2.39+, and gh 2.100.0+ for GitHub-backed Projects. See
[installation and support](docs/installation.md) for the required host/harness
acceptance and [the release checklist](docs/releasing.md) for publication gates.
