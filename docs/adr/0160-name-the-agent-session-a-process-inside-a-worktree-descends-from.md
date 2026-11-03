---
status: accepted
date: 2026-11-03
---

# Name the Agent Session a process inside a Worktree descends from

[ADR 0104](0104-block-worktree-removal-while-a-process-runs-inside-it.md)
refuses to remove a Worktree while a process the person can see works inside
it, and names each such process by pid, command, and working directory. That
is enough for a shell or a dev server a person started. It is not enough
for a process an Agent Session started and then left behind.

[Issue #695](https://github.com/ned2/dashpot/issues/695) records one. A
Claude Code session entered its Issue Worktree with `EnterWorktree`, edited
Python there, and left with `ExitWorktree` `action: "keep"`, as the bundled
`dashpot-issue-work` skill says to. Claude Code had started
`pyright-langserver` for its `pyright` LSP plugin when the session first
edited Python, in the directory the session was in at the time. Leaving did
not stop the server or move it. Cleanup then refused the Worktree:
`pid 25459 (pyright-langser)`. The session's own `claude` process was the
server's parent and worked in the main checkout, but nothing in the refusal
said so. A person could not tell which session the process belonged to, or
that ending it alone would free the Worktree.

The scan of ADR 0104 already reads every visible process's parent, so it can
trace a process inside the Worktree to its ancestors, wherever they work.
The hook records of the Repository's Agent Sessions name each session's
Host Process, and the liveness probe says which of those processes are
still running.

## Decision

A `process` blocker names, beside each process it lists, the live Agent
Session that process belongs to, when it belongs to one.

- **Traced through the whole scan.** `processes_inside` traces each process
  it finds through every process the scan read, inside the Worktree or not,
  and reports that ancestry, nearest parent first, with the process. It
  stops at a parent the scan did not read, a loop, or the existing bound of
  64 parents.
- **Only a live session's Host Process.** The sessions named are those whose
  hook records in the Repository's reachable stores are `live`: the probe
  found their Host Process running, keyed by pid and start time. Their pids
  are then those processes now, not reused ones. A session whose Host
  Process is gone, or whose liveness is unknown, names nothing.
- **Nearest Host Process wins.** A process that is itself a Host Process is
  named as "the Host Process of" its sessions. A process descended from one
  is named as "started under the Host Process (pid N) of" the sessions of
  its nearest such ancestor. A Host Process that holds several live
  sessions, as an OpenCode server does, names them all, since the process
  table cannot tell which of them started the child.
- **Say what clears it.** A process is left behind when it descends from a
  live session's Host Process and that Host Process is not itself inside the
  Worktree. When any listed process is left behind, the detail ends with a
  sentence. It says a live Agent Session started those pids and may have
  left the Worktree without them, and that ending them leaves the session
  running. It says that this frees the Worktree only when those processes
  are all that is inside it. Otherwise it says the other processes still
  hold the Worktree. When every such session is a Claude Code session, the
  sentence cites the language server as the example. A Host Process inside
  the Worktree, and every process under it, gets no such sentence: that
  session is still here, and the `agent-session` blocker reports it.
- **Ending the session is not offered.** The sentence names only ending
  the process. A harness need not end its children when its session ends,
  and whether Claude Code always does is not yet measured
  ([#697](https://github.com/ned2/dashpot/issues/697)). The skill's recovery
  reference, which speaks for one harness, mentions ending the session too.
- **Narration, not a gate.** The attribution is part of the blocker's
  `detail`, which a preview's fingerprint already leaves out. The blocker's
  kind, and so whether the Worktree is removable, is unchanged. Dashpot
  still never deletes a directory a live process works in and never ends a
  process itself.
- **The skill checks after leaving.** The Claude Code finish step of
  `dashpot-issue-work` runs `dashpot worktree check` on the Worktree after
  `ExitWorktree`. If a `process` blocker names the session, the agent tells
  the user what it is and how to end it, and does not end it itself.

The hook-store read happens only when the scan found a process inside the
Worktree, so a Worktree with none pays nothing more. `worktree check`, the
Cleanup preview, the dashboard's Cleanup details, and the re-inspection on
confirmation all carry the attribution, since they share
`assess_processes_inside`.

## Considered options

- **Leave the refusal as it was and document the language server only:**
  rejected. The refusal is where a person or agent meets the problem.
  Guidance in one skill reaches only sessions that load it, and only for one
  harness.
- **A separate blocker kind for a session's child process:** rejected. ADR
  0104 keeps one `process` blocker per Worktree so the preview's blockers do
  not change as processes come and go. A second kind would bring that churn
  back, and it would gate nothing the existing kind does not.
- **Name the session from a record whose liveness is unknown:** rejected. A
  pid that may have been reused could pin the process on the wrong session.
- **Stop the language server from Dashpot, or from the skill:** rejected.
  Dashpot never ends a process
  ([ADR 0104](0104-block-worktree-removal-while-a-process-runs-inside-it.md)),
  and in #695 Claude Code's auto-mode classifier refused the session's own
  `kill` of its language server. Ending it stays a person's choice.
- **Name a sub-agent's own Host Process too:** deferred. A Claude Code
  sub-agent runs in its session's Host Process, which is already named. A
  Codex sub-agent whose own process runs it can be added when a case calls
  for it.

## Consequences

- A refusal like the one in #695 now names the Claude Code session and its
  Host Process, and says that ending the language server alone frees the
  Worktree.
- An agent following `dashpot-issue-work` checks for a leftover process when
  it leaves a Worktree, rather than finding it later in a Cleanup refusal.
- A process that outlives its session, such as a background command whose
  session ended, is reparented and no longer descends from a Host Process.
  It is named by pid and command alone, as before.
- Which Claude Code tool calls start a language server, whether ending the
  session always ends it, and how other LSP plugins behave are not settled
  here. They are left to a spike on a pinned release
  ([#697](https://github.com/ned2/dashpot/issues/697)).
