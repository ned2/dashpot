---
status: superseded
date: 2026-10-02
superseded-by: 0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md
---

# Give an OpenCode command a claim only for its own bootstrap

Every OpenCode session in a backend runs its shell commands as children of
the same backend process, so ancestry cannot say which session a command
belongs to. The backend's environment is shared by all of them, and it may
also carry the claims of a harness that launched OpenCode: Codex's
`CODEX_THREAD_ID`, Claude Code's `CLAUDE_CODE_SESSION_ID`. The
[OpenCode design](../proposals/opencode-integration-design.md#corroborate-the-command-that-is-actually-executing)
proposed a command-local acknowledgment. The plugin clears inherited claims
on every shell command, then injects a claim only after that command's own
bootstrap has been accepted. The [#163 probe](../../scripts/experiments/opencode-163/run.mjs)
measured OpenCode 1.18.30's `shell.env` hook:

- It receives the session's ID and the tool call's ID for an agent's shell
  command.
- It receives no session ID for a terminal (PTY) the user opens.
- Setting an inherited variable to an empty value there hides it from the
  command.

## Decision

**The plugin's shell hook.** On every shell command, the plugin first blanks
every claim variable Dashpot reads: its own, `DASHPOT_AGENT_SESSION`, Codex's,
and Claude Code's. A command without a session ID gets no claim. Otherwise
it publishes a bootstrap for the command's session. That publication waits
in the session's ordered queue, and takes the next sequence. The hook
injects these variables only if the helper accepts that bootstrap and
echoes this call's ID, session and generation:

- `DASHPOT_OPENCODE_SESSION_ID`;
- `DASHPOT_OPENCODE_GENERATION`;
- `DASHPOT_OPENCODE_PID`, the backend's PID.

The helper acknowledges a claim for a root session only. A child session's
bootstrap is accepted as Sub-agent activity, with the reason
`delegated-session` and no claim. So a delegated OpenCode session cannot
start, switch, relocate or stop Issue work. Otherwise the hook sets
`DASHPOT_OPENCODE_UNCORROBORATED` to the reason, and a refused `work`
command repeats it.

**Validation.** Issue opt-in validates an OpenCode claim like any other
([ADR 0038](0038-isolate-native-agent-session-identities.md)): its freshest
hook record must exist, belong to OpenCode, and name the backend. Opt-in
also refuses the claim when:

- the claim's generation has retired, or no longer owns the backend's
  directory;
- OpenCode has deleted the session;
- the session's record names no process, which is the state retirement
  leaves.

An explicit `DASHPOT_AGENT_SESSION=opencode:<id>` carries no generation, so
it is refused. A shell prepared by a generation that retired must run its
command again.

**Ancestry.** An OpenCode backend is never claimed without a command-scoped
OpenCode claim. A Claude Code or Codex session launched below an `opencode`
process still finds its own Host Process first in its ancestry, so it
identifies its own session. A command under OpenCode that inherited another
harness's claim is refused. The plugin blanks that claim. And even when the
plugin does not, the nearest Host Process is the OpenCode backend, which
does not corroborate the inherited claim.

**Bounds.**

- A shell command waits at most 3 s, in total, for its metadata, queue and
  helper.
- Each helper runs under a 3 s publication deadline. The plugin kills it at
  that deadline. The helper also stops itself half a second later, with an
  interval timer that interrupts even a blocked lock wait.
- Metadata reads are bounded at 500 ms. Unknown parentage is never read as
  a root.
- A session's queue admits 16 publications. At most 8 helpers run at once,
  and a helper killed at its deadline counts until it exits.
- A failed or late acknowledgment leaves the command without a claim. It
  never fails the command.

## Departures from the proposal

- **No repository-wide coordination lock, and no reconfirmation under one.**
  Each publication locks its own publisher record, then the hook records it
  writes. Issue opt-in validates the claim once, before its Work Store write,
  as for the other harnesses. This leaves a narrow window: a retirement
  between validation and the write. It cannot transfer another session's
  work, and the run it starts reads unknown, as every retired generation's
  runs do.
- **The claim carries no location or parentage.** The helper accepts a
  publication only for a session in its instance's directory, and a claim
  only for a root. Validation then checks the generation and the hook
  record.
- **No durability barrier on a duplicate acknowledgment.** A bootstrap
  always takes a fresh sequence, so its acknowledgment is never a duplicate.

## Considered options

- **Identify the session by ancestry, as for Claude Code.** Rejected. One
  backend hosts every session.
- **A persisted receipt per command.** Rejected, as the proposal
  recommended. It needs storage limits and reclamation. The trust model is
  the installed plugin's honest environment, which a receipt would not
  strengthen against a same-user process.
- **The newest bootstrap as proof.** Rejected. Two overlapping commands in
  one session would invalidate each other.

## Consequences

- An agent's shell command in a root session can opt in. A child session's
  command and a terminal opened by the user cannot, and are told why.
- `dashpot work stop` needs the same claim, so it runs from an agent's shell
  in the root session. `work show` lists the Worktree's runs without one, and
  lists the session's own recent events only with one.
- Every shell command pays for one helper invocation, about 0.1–0.2 s on the
  measured machine.
