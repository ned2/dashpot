---
status: accepted
date: 2026-08-30
---

# Identify sandboxed Agent Sessions by Agent Session Identity

Issue work opt-in identified the enclosing Agent Session by walking from the
`dashpot work start` command to the harness process and keying the Work Store
record by that process's PID and start time. From inside a sandbox's isolated
PID namespace — Codex's `codex-linux-sandbox`, and the bubblewrap sandbox
Claude Code uses on Linux — the walk reaches PID 1 of the namespace, which is
the sandbox helper, and stops: the harness is on the host and invisible. The
session's lifecycle hooks, which run on the host, were meanwhile publishing a
healthy record carrying the harness's own `session_id`. Observation joined the
two only through the host process, so a sandboxed session could never bind an
Issue ([#53](https://github.com/ned2/dashpot/issues/53)).

Dashpot now identifies a session through one harness-neutral seam with a
Harness Adapter per harness. The process route stays primary and unchanged.
When it cannot be observed, the adapter reads the Agent Session Identity the
harness exposes to commands, and opt-in accepts it only when exactly one hook
record of the same harness at this Worktree confirms it and still describes a
session that is not ended or gone. The record is then keyed by the host
process that hook published, so one session has one record whichever route
found it, and liveness and orphan detection keep following the host process.

## Considered options

- **Hard-code the harness environment variables as the identity:** rejected.
  Neither `CODEX_THREAD_ID` nor `CLAUDE_CODE_SESSION_ID` is documented as a
  stable contract. They are read inside their adapter as a claim, and the hook
  record — which the harness did publish, through its documented hook input —
  is what the identity is validated against. A renamed variable degrades to
  an actionable refusal, never to a wrong binding.
- **A Codex-only exception:** rejected. Claude Code's sandbox hides the host
  process the same way, and the gap is structurally about identity, not one
  harness; `bwrap` is now recognised as an isolating init beside
  `codex-linux-sandbox`.
- **Have the hook publish the identity into the session's environment:**
  not adopted. Neither harness documents a way for a hook to persist
  environment into later commands. `DASHPOT_AGENT_SESSION=<harness>:<id>` is
  Dashpot's own explicit claim instead, validated like the native ones, and is
  the disambiguator when the environment names live sessions of both harnesses.
- **Key sandboxed records by the identity's digest always:** rejected, because
  a session whose commands are sometimes sandboxed would then hold two
  records. Keying by the hook-published host process keeps one record per
  session; the digest key is only for a record whose hook saw no host process.
- **Trust the identity without a hook record:** rejected. Without the record
  there is no evidence the session exists at this Worktree, and a binding is
  a durable claim on declared work.

## Consequences

- `dashpot work start`, switching Issues, and `stop` work from a sandboxed
  shell of either harness once its hooks are installed and have published the
  session here; the bound Issue gains its `◈` glyph and the Sessions pane shows
  the binding exactly as for a host-visible session.
- A sandbox helper is never taken for the host harness, and a missing, stale,
  cross-harness, mismatched, or ambiguous identity writes no binding.
- Work Store records gain an optional `sessionId`; records without one and
  process-based identification continue to work, and a legacy record is
  adopted by the same session's next `start` rather than duplicated.
- Observation correlates a Work Store record to its hook record by Agent
  Session Identity first and host process second, and lists each session once.
- `dashpot integrate <harness> --status` reports the identity the current
  environment claims and whether the Worktree's hook record confirms it.
