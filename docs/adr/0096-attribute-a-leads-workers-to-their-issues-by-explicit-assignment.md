---
status: amended
date: 2026-10-04
amended-by: 0137-hold-only-what-was-published-last-in-the-observation-store.md
---

# Attribute a Lead's Workers to their Issues by explicit assignment

Amended by [ADR 0137](0137-hold-only-what-was-published-last-in-the-observation-store.md):
the rule that no Worker counts toward an Issue Identity more than one Project
observes held only in the snapshot Issue list, which is retired; the Issue
list is one Project's Query Page.

Amended in place for [#593](https://github.com/ned2/dashpot/issues/593):
the check that left an Agent Run bound to an Issue Identity more than one
Project observes unbound, and reported the Identity as an
`agent-issue-identity-conflict`, is retired from headless `observe`.
Dashpot observes one Project per run
([ADR 0004](0004-observe-one-project-per-run.md)), so no such Identity
occurs; a multi-Project run would need its own ADR, which decides the rule
afresh.

[ADR 0092](0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
ships the Lead/Worker workflow: a Lead holds the Arc's single Agent Run and
Issue Binding at the checkout where it starts, and dispatches Workers that each
take one Issue to an open PR in its own Issue Worktree. Workers have no Agent
Run or Issue Binding and run no `work` commands, because a Sub-agent's shell
resolves to its Lead's Agent Session and
[ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md) holds one
run per session. So the Issue list showed the Arc running while every Issue
actually under implementation showed nothing
([#243](https://github.com/ned2/dashpot/issues/243)). On 2026-09-17 a Claude
Code session at `main` held four Sub-agents working on four Issues in four
Worktrees, and none of those Issues showed a bound Agent Run.

[#215](https://github.com/ned2/dashpot/issues/215) asks whether a session can
bind more than one Issue and separates two cases. This decision is for its
second case: parallel Workers that work on different Issues **at the same
time**, in **different Worktrees**, as **Sub-agents of one Lead**, and open
**separate PRs**. It does not choose a model for #215's first case, where one
session rolls several Issues into one PR. That case has no Workers to tell
apart, and it remains with #215.

## Decision

A Lead declares which Issue each Worker it launched works on. Dashpot calls
that declaration a **Worker Assignment**. It is not an Agent Run or an Issue
Binding. An Issue's activity counts an assigned Worker only while its harness
reports the Worker working.

### Declaration

`dashpot work assign <reference> --worker <id> --worktree <path>`, run from
the Lead's own shell, records the assignment. It is refused, with nothing
written, unless each of these holds:

- **The Issue resolves** to exactly one fresh Issue of the Project, as `work
  start` resolves one.
- **The Lead is confirmed.** The command identifies the enclosing Agent Session
  exactly as `work start` does. That session must hold exactly one active
  Agent Run across the Repository's Worktrees, every Work Store record must be
  readable, and no other live or unobservable runtime may still own the run.
  A run still recorded under an earlier Host Process that is gone is an
  Orphaned Agent Run, whose Workers observation never reports, so it is
  refused too. A Claude Code Lead, or one whose relocation is pending,
  assigns once its session's next hook event has continued the run. Nothing
  continues an orphaned Codex or OpenCode run on its own, so that Lead
  recovers it with `work start`, which ends its assignments, and assigns
  each Worker again.
- **The Worker's identity is harness-native and its Lead's.** The `--worker`
  value is a Sub-agent identity as the harness's hooks publish it: the
  `agent_id` of `SubagentStart`. The Lead's own hook records must list it
  among the session's live Sub-agents
  ([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md),
  [ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md))
  by the rule [Observation](#observation) applies, so an accepted Worker is
  one observation would report. A mistyped identity, another session's
  Sub-agent, a Worker whose start has not been published yet, and one that
  already finished are refused. The Lead retries once the harness reports
  the start. The launch result supplies the identity:

  | Harness | Where the Lead reads the Worker's identity | Evidence |
  | --- | --- | --- |
  | Claude Code | the Agent tool's `agentId`, which is `SubagentStart`'s `agent_id` | [worker mechanics](../spikes/claude-code-worker-mechanics-spike.md) |
  | Codex, multi-agent v1 | `spawn_agent`'s `agent_id`, which is the Worker's thread | [worker mechanics](../spikes/codex-worker-mechanics-spike.md) |
  | Codex, multi-agent v2 | `spawn_agent` returns only a task name such as `/root/worker_a`, so the Worker reports its own `CODEX_THREAD_ID` | [worker mechanics](../spikes/codex-worker-mechanics-spike.md), [identity](../spikes/codex-identity-lifecycle-spike.md) |
  | OpenCode | the `subagent` tool's `sessionID`, which the plugin publishes as `agent_id` | [worker mechanics](../spikes/opencode-v2-worker-mechanics-spike.md) |

- **The Worktree is the Repository's.** `--worktree` must name one of the
  Repository's Worktrees. It records where the Lead intends the Worker's
  commands to run. It is a declaration, never evidence that the Worker is
  there: no hook reports where a Sub-agent's commands run, so nothing
  observed corroborates it.

The command never infers an assignment from a Branch, a Worktree name, a hook
`cwd`, or a shared Host Process. Assigning a Worker again to the same Issue
and Worktree changes nothing. Assigning it anywhere else replaces its
assignment and says so. `dashpot work unassign <id>` ends one assignment
without checking the Worker, so a Worker that finished, failed or was stopped
is unassigned the same way.

### Persistence and lifecycle

The assignment is held on the Lead's Agent Run in its Work Store record,
beside the Issue Binding it leaves unchanged, so it lasts exactly as long as
that run:

- **Unchanged by the run's own moves.** Assigning a Worker changes nothing
  about the run: not its identity, Issue Binding, Observation Location,
  relocation state, or `started_at`. A relocation
  ([ADR 0029](0029-preserve-agent-runs-through-declared-codex-relocation.md),
  Claude Code's `EnterWorktree`) and an Orphaned Agent Run's continuation
  carry the assignments with the run.
- **Ended with the run.** `work stop`, any `work start`, a graceful session
  end, and a settled deferred end each end the run, and its assignments with
  it. A `work start` on the run's own Issue restarts the run, so it ends them
  too. `work stop` and `work start` name the assignments they ended. A Lead
  that resumes after its run ended assigns its Workers again.

### Observation

Observation publishes each assignment on its Lead's Agent Run as
`AgentRun.workers`, with the Worker's state as the Lead's hook records report
it:

- **`running`** while the Lead's freshest hook record lists the Worker as a
  live Sub-agent, that record's Host Process is the run's, and it is live.
- **`unknown`** while that record lists it but its Host Process's liveness
  cannot be observed. It is also `unknown` when an ended record that kept
  its Sub-agents lists it
  ([ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)),
  whichever Host Process wrote that record. While the Lead's run lasts,
  that happens between a deferred end and its settlement.
- **Nothing** otherwise: the Worker finished, failed or was stopped, its
  start has not been published, the Lead's run is orphaned, or the only
  live or unknown record that lists it was written by another Host Process.

No harness reports a Worker's turn state, so a Worker is never `waiting`.
Reading only the freshest live or unknown record, and only when the run's
own Host Process wrote it, keeps a listing that a relocation or restart left
behind from counting as activity
([#427](https://github.com/ned2/dashpot/issues/427)). Cleanup is deliberately
wider: it counts every record's Sub-agents, since a missed one could lose
work (ADR 0066). `work show` and `work assign` read the hook records by this
rule without observation's pruning, so `show` reports a Worker as the Issue
list does.

### Issue activity

An Issue-list row's activity is the liveliest of its directly bound Agent
Runs and the Workers assigned to it, by the existing precedence: running,
then waiting, then orphaned, then unknown. A Worker counts toward the Issue it
is assigned to and never toward its Lead's. The Lead's own state is never
copied to its Workers' Issues. So when Worker B finishes, Issue B loses B's
`running` and keeps any other Worker's or bound run's activity, while Worker
C keeps Issue C running and the Lead may still be running on the Arc. An
assignment alone shows nothing. A Sub-agent no Lead assigned holds only its
own session's run running (ADR 0016) and gives no Issue of its own any
activity. An Issue Identity names one Issue of the one observed Project
([ADR 0004](0004-observe-one-project-per-run.md)), so bound runs and
assigned Workers count toward it alike; no rule refuses either for an
Identity more than one Project observes.

Each assigned Worker keeps its Lead's run identity, so a later Sessions-pane
design ([#444](https://github.com/ned2/dashpot/issues/444)) can show assigned
Workers under their Lead. This decision adds no Sessions-pane entries and no
listing of every Sub-agent.

### What an assignment is not

An assignment is attribution only. It does not prove that the Worker occupies
its Worktree. It does not show that the Worker drained or handed back
successfully. It gives no outside controller authority to move the Lead or a
Worker. Cleanup still blocks on any live Sub-agent, assigned or not
([ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md),
ADR 0095). A finished Worker may have opened a PR. That says nothing about
whether its Issue is closed.

## Support boundaries

What each harness reports bounds what Dashpot can claim:

- **A stop the harness never reports.** A Claude Code Worker stopped with
  `TaskStop`, a Codex child interrupted through its own thread
  ([#374](https://github.com/ned2/dashpot/issues/374)), and a Codex Worker
  whose lead was deleted publish no `SubagentStop`. Each Worker stays listed,
  so its Issue reads `running` until the Lead unassigns it or the Lead's run
  ends. The Lead that stopped it knows, and the bundled skill has it run `work
  unassign` then.
- **A Codex Lead unload.** The managed daemon unloads an idle Lead about 60 s
  after its last client leaves, which ends its run and its assignments while
  its Workers may still work (ADR 0095). From then until the Lead resumes and
  assigns again, those Workers' Issues show nothing.
- **A Lead's own `SessionStart`.** Claude Code and Codex publish one when
  they compact the Lead's context. Since
  [ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md)
  ([#448](https://github.com/ned2/dashpot/issues/448)), one from the Lead's
  own Host Process keeps its Workers listed, so their Issues stay `running`
  and `work assign` accepts them. One from another process, such as a
  `claude --resume`, or from a process the hook cannot name, starts with
  none. A Claude Code `/clear`, `/resume` or
  `/branch` ends the Lead's session, and its run and assignments with it.
- **Resumed and relaunched Workers.** A Claude Code `SendMessage` to a
  finished Worker resumes it under the same `agent_id`, which publishes
  `SubagentStart` again. Its assignment counts it running again. Codex v2's
  `followup_task` to a finished Worker was measured firing `SubagentStop`
  again with the same `agent_id`, and whether it fires `SubagentStart` too
  is unmeasured. Until it is, a followed-up Codex Worker may read as not
  working. A relaunched Worker is a new identity, so the Lead assigns it and
  unassigns the one it replaces.
- **OpenCode between executions.** An OpenCode Worker publishes
  `SubagentStart` and `SubagentStop` around each execution. Between them it
  reads as not working, as it is. An execution that finishes before the Lead
  assigns it cannot be assigned until the next one starts.

## Alternatives considered

- **Keep arc-only attribution.** This was ADR 0092's position: the Lead's
  binding stands for the whole Arc. It needs nothing new, but the Issues being
  worked on show no activity, and the Arc shows `running` for as long as any
  Worker runs, whichever one it is. A person cannot tell which Issues are
  moving.
- **Bind several Issues to the Lead's run.** The run would carry one binding
  for each Worker's Issue. Every bound Issue would then share the Lead's
  state, so one Worker's finish could not clear its own Issue while another
  Worker ran. A binding says nothing about which Worker is on which Issue or
  where its commands run. It would also change Agent Run membership for every
  reader, and #215's roll-in case may want a different model.
- **Concurrent Agent Runs per session.** Each Worker would get its own run.
  That reopens ADR 0009 and makes a Sub-agent independently bindable, though
  its shell, hooks and Host Process are its Lead's. Every per-run contract
  would have to learn which of a session's runs an event belongs to, including
  `work show`, relocation, orphaning, and the settler.
- **Infer the assignment.** A Worker could be matched to an Issue by Branch,
  Worktree name, hook `cwd` or prompt. None of these is evidence. Every
  measured hook carries the Lead's `cwd`, and names are conventions, not
  identities.
- **Accept an unconfirmed Worker identity.** Recording any identity the Lead
  passes would let a typo or a foreign Sub-agent attribute nothing to an
  Issue, silently. Requiring the Lead's hooks to list the Worker turns a
  launch-ordering race into a refusal the Lead can retry.

## Consequences

- An Issue shows `running` for the Worker that is actually working on it, and
  ADR 0092's attribution gap closes for every supported harness.
- `work assign` and `work unassign` join the management commands. They mutate
  only the invoking session's own Work Store record, on explicit invocation
  ([ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)),
  and record their outcomes in the Event Log.
- The Work Store record gains `workers`, an additive field read with a
  default, so the format's version is unchanged. The published `AgentRun`
  gains `workers` too.
- `work show` lists each assignment under its run, saying whether the
  Lead's records list the Worker as working, list it with unknown liveness,
  or do not list it.
- The bundled `dashpot-execute-issues` skill assigns each Worker after
  launching it and unassigns a Worker it stops or replaces. A Worker still runs
  no `work` command.
