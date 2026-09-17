---
status: research
date: 2026-09-12
---

# Cleanup session handoff feasibility

Read-only investigation for Issue #148. Installed CLI help reports Codex
0.154.0 and Claude Code 2.1.261. No live session, terminal pane, Worktree, Git
metadata, or Issue Binding was changed. No private transcripts or credentials
were inspected. The mechanisms below are documented capabilities or proposed
integration designs, not claims of completed disposable acceptance.

## Finding

Conversation-preserving movement has useful harness primitives. There is no
established end-to-end mechanism in Dashpot that can cooperatively control every
currently observed occupant, prove background work has drained, move it, and
preserve an active Agent Run. Arbitrary observed sessions must remain blocked
unless a concrete control capability is registered and verified. Neither a
successful launch command nor a waiting lifecycle observation establishes this.

The most promising experiment is a deliberately opted-in controller:

- Codex: a controller attached to the app-server that owns the thread, with
  ownership of the terminal client lifecycle if sequential resume is retained.
- Claude Code: an opted-in channel delivering a handoff request to a session
  that can return to the disclosed original directory with `ExitWorktree`.

These are narrower support arrangements than all existing terminal sessions.

## Codex evidence and limitations

The official app-server interface provides `thread/resume`, `turn/start`,
`turn/steer`, and turn completion notifications. A new turn can override `cwd`
and sandbox policy, and those overrides persist for later turns. `turn/steer`
cannot change cwd. The server also exposes experimental background-terminal
inventory and control. Its transports include stdio and Unix sockets;
WebSocket transport is explicitly experimental/unsupported. The TUI can
connect to a separately started server with `codex --remote`.
[Official app-server documentation](https://developers.openai.com/codex/app-server)

Inference: a launcher which already owns the server connection can coordinate
a future turn at a destination; this does not prove that another arbitrary CLI
instance accepts third-party control, that its old terminal has exited, or that
all background children are idle. Generating the installed protocol schema is
a useful next step in a disposable prototype. No live control socket was
connected to during this investigation.

Installed `codex resume --help` explicitly supports a session ID and `-C/--cd`
working root. The repository's established route is sequential resume:
declare `work relocate`, exit the original client, resume the same identity at
the destination, and verify fresh target hooks. A live app-server cwd change
would be a new lifecycle contract; it cannot be treated as a transparent
implementation of the existing sequential-resume rule.

## Claude Code evidence and limitations

`ExitWorktree` returns to the original directory, and is unavailable to a
subagent with its own pinned working directory. `EnterWorktree(path=...)`
supports adopting existing Worktrees; from an already-isolated session or a
pinned subagent the target is restricted to `.claude/worktrees/` in that
Repository. First entry outside that location requires approval.
[Official tools reference](https://code.claude.com/docs/en/tools-reference)

`/cd` preserves conversation, applies destination project configuration, and
can require workspace trust. Crucially, the documentation expressly says that
`Cd` is not model-invocable: a model cannot call it. Therefore injecting a
natural-language request to run `/cd` is not a deterministic control mechanism.
Its configuration change also retains environment variables from the previous
directory's settings; implementation must validate permissions and environment
behavior rather than assuming a pristine destination.
[Official permissions documentation](https://code.claude.com/docs/en/permissions#move-the-session-to-another-directory)

Resuming an isolated Worktree session, including a non-interactive or SDK
resume, normally returns to its recorded Worktree. Merely starting `claude
--resume <id>` in the destination does not establish movement. `--fork-session`
uses the launch directory but changes the session identity. The documented
deleted-Worktree fallback cannot be used because Cleanup must verify handoff
before deleting the source.
[Official Worktree documentation](https://code.claude.com/docs/en/worktrees#resume-a-worktree-session)

Channels provide supported event delivery into an already-running opted-in
session. They require launch-time enablement and an approved plugin or explicit
development opt-in; they are a research preview. An ordinary configured MCP
server alone cannot push events. A Dashpot channel could request cooperative
drain and `ExitWorktree` for a compatible session, then collect an acknowledgment,
but acknowledgment would still need corroboration from hooks and process state.
This is an integration proposal requiring disposable acceptance.
[Official channels documentation](https://code.claude.com/docs/en/channels)

The public shell management surface supports listing, attaching, stopping,
and restarting background sessions. `claude agents --json` is the supported
external status interface; its private job files are explicitly unstable.
`--resume <full-id> --bg` can reuse identity when the old session is stopped,
but may instead copy a running session and report that fact. It is not a
safe shortcut for moving an arbitrary live occupant. Agent view can send input
interactively; the documented shell command table does not establish a general
external input or cwd-change RPC.
[Official agent-view documentation](https://code.claude.com/docs/en/agent-view#manage-sessions-from-the-shell)

Cross-session messaging is exposed to Claude through `ListAgents` and
`SendMessage`; the official documentation directs external event sources to
channels. This does not establish a Dashpot-owned external sending endpoint.
[Official cross-session messaging documentation](https://code.claude.com/docs/en/cross-session-messaging)

## Repository gaps

- `src/dashpot/sessions/work.py` identifies the calling session, accepts Codex only,
  and requires an active Agent Run. It cannot be invoked by the dashboard as
  authority over an arbitrary occupant. An unbound session has no suitable
  record on which to declare the existing Relocation Intent.
- `src/dashpot/sessions/hook_records.py` completes only Codex relocation. Its target
  evidence and competing-client checks should remain authoritative.
- `src/dashpot/sessions/work.py` starts/switches Issue work. Calling it after a Claude
  move recreates the run with a new start time; that cannot satisfy #148's
  preservation of Agent Run identity and start time.
- `src/dashpot/cleanup.py` uses Worktree occupancy as a blocker. Management
  needs a separately testable handoff prerequisite, never a blanket exemption
  from the existing occupancy check.
- Resolved: dialog Remote Fetch now separates idle-preview reservations from
  confirmed mutations in `src/dashpot/app.py`, as recorded in
  [ADR 0036](adr/0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md).

These are static findings in the checkout examined during this investigation.

## Disposable acceptance needed before enabling automatic removal

1. Create explicitly disposable sessions through the proposed controller and
   establish exact session identity, origin, destination, and control ownership.
2. Test each harness with an active Agent Run and with no Issue Binding. Preserve
   identity, start time, and binding in the first case; create no run in the second.
3. Drain real background commands and subagents. Ensure a waiting turn with a
   background process cannot pass preflight. Test unknown liveness as blocking.
4. Verify the same conversation with a harmless conversation canary, destination
   working root, effective permissions, and fresh destination hooks. For Codex
   sequential resume, independently verify original-client exit first.
5. Cover unsupported direct-launch sessions, pinned Claude subagents, a Claude
   session whose original directory differs from the selected destination,
   concurrent Codex clients, missing hooks, and unavailable controller channels.
6. Inject refusal, timeout, controller restart, cancellation, and partial moves
   among multiple occupants. Recovery may report completed moves but must never
   resume deletion after cancellation or blindly issue another resume.
7. Reinspect source contents, Branch tips, occupants, destination, and optional
   Branch eligibility before unforced removal, then remove only explicitly
   selected targets in the disposable fixture.

The fetch-in-dialog and fixed-primary-preview components do not depend on
successful harness acceptance. They are implemented with the current occupancy
gate intact in [ADR 0036](adr/0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md).
Automatic session handoff remains unverified, so #148 is only partly complete.
