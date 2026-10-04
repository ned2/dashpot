---
status: accepted
date: 2026-10-05
---

# Keep OpenCode self-move and leading Workers on the shared service

[ADR 0090](0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md)
supports Issue work under OpenCode v2 in two hosting modes: the shared
per-user service, `opencode serve --service`, and a `--standalone` client's
private `opencode serve --stdio`, each the Host Process of the sessions it
serves. The OpenCode acceptance run binds an Agent Run with `work start` from
a `--standalone` TUI and from `opencode run --standalone`, and orphans it when
the client quits.

Two skill flows added since were measured on the shared service only:

- **Self-move.** [ADR 0094](0094-let-a-root-opencode-session-move-itself-for-issue-work.md)
  lets a root session move itself into its Issue Worktree, and back to the
  main Worktree, with OpenCode's `session_move`. The acceptance run for
  [#423](https://github.com/ned2/dashpot/issues/423) lists `--standalone` as
  not measured.
- **Leading Workers.** [ADR 0092](0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
  has an OpenCode Lead's Workers report mid-flight with
  `opencode run --session <lead>`, with a status file as the fallback, and
  the worker-mechanics experiment for
  [#421](https://github.com/ned2/dashpot/issues/421) lists a `--standalone`
  Lead as not measured.

The report is the risky part. A plain `opencode run` is a client of the
shared service, while a `--standalone` Lead's Host Process is its client's
private server, and the two share one session database. By the 2.0.22
source the report would have the shared service run the Lead's session
while the private server also serves it: two Host Processes serving one
Agent Session, which no supported arrangement allows
([OpenCode hosting modes](../agent-sessions.md#opencode-hosting-modes)) and
[#379](https://github.com/ned2/dashpot/issues/379) closed without
measuring. A report through OpenCode's HTTP API reads the shared service's
password from its registration, so it cannot reach a private server either.

Neither skill could tell which mode its session ran in: the adapter takes
any `opencode` server as the Host Process, and `integrate opencode --status`
did not say which kind it was. [#454](https://github.com/ned2/dashpot/issues/454)
asked for the restriction and the check.

## Decision

**Report the mode.** When `dashpot integrate opencode --status` confirms the
Agent Session Identity a command claims, it adds an `OpenCode Host Process
mode` line. The mode is read from the argument vector of the process
`DASHPOT_OPENCODE_PID` names, the server that ran the command:

| Mode | Its server's command line, measured at 2.0.22 |
| --- | --- |
| `shared-service` | `<install>/opencode serve --service` |
| `standalone` | `<install>/opencode serve --stdio --port 0` |
| `unknown` | Anything else: a process that could not be observed or has exited, one whose arguments could not be read, and an `opencode serve` a person started for `--server <url>` |

The mode is a closed `Literal` with one reader, the status line. A
non-shared mode's line also says that the session moves itself and leads
Workers only on the shared service. The line is reported only beside a
confirmed identity, since an unconfirmed claim's pid names no session's
server.

**Restrict the two flows to the shared service.** Any mode other than
`shared-service`, `unknown` included, keeps both flows off:

- **Self-move.** The `dashpot-issue-work` skill moves a session only when
  its status reads `shared-service`. Otherwise it hands off at dispatch as
  it does after a declined or unconfirmed move: the plain
  `opencode <worktree> --prompt …` it gives the person starts the new
  session on the shared service. At finish, it tells the person what holds
  the Worktree, as after a failed move back. This amends ADR 0094's
  authority, which now covers a session on the shared service only.
- **Leading Workers.** The `dashpot-execute-issues` skill reads the mode
  while it sets up, before it binds, and launches Workers only when it
  reads `shared-service`. Otherwise it stops before any launch and tells the
  person to start the Lead again with a plain `opencode`, without
  `--standalone`. This amends ADR 0092's OpenCode column, which now holds
  for a Lead on the shared service only.

**Leave binding alone.** `work start` and every other `work` command behave
as before in a `--standalone` session, since refusing there would remove
measured support. When the `dashpot-issue-work` skill binds in a session
whose status reads `standalone`, it tells the person once that quitting
that client stops its server and orphans the run.

## Considered options

- **Refuse `work start` in a `--standalone` session.** Rejected: the
  acceptance run measured binding there, and the risk is in the two skill
  flows, not in binding.
- **Treat `unknown` as permitted.** Rejected: an unobservable server, or one
  started some other way, is no more measured than a `--standalone` one, and
  a skill that cannot tell should take the measured path.
- **Let each skill read the process tree itself.** Rejected: identifying the
  Host Process is the Harness Adapter's job, and one status line gives both
  skills, and the arrangements #455 may add, a single answer to read.

## Consequences

- A `--standalone` session still does Issue work, and does it in the
  Worktree it was started in; dispatch to another Worktree is a fresh
  session on the shared service.
- A `--standalone` Lead stops before any Worker runs, so no supported
  arrangement makes two Host Processes serve one Agent Session.
- A later measurement of a `--standalone` self-move, or of a `--standalone`
  Lead with Worker reports, such as
  [#467](https://github.com/ned2/dashpot/issues/467)'s, can lift the matching
  restriction. [#455](https://github.com/ned2/dashpot/issues/455) decides,
  for each server arrangement it adds, whether the flows extend there, and
  builds on this mode report.
- [ADR 0093](0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)'s
  worker agent is unchanged: it guards a shared-service Lead's Workers.
