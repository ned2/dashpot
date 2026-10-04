---
status: proposal
date: 2026-10-05
---

# Lead and Worker design

A working design for [Issue #479](https://github.com/ned2/dashpot/issues/479):
how a Lead could run its Workers, how they would talk, and how the Sessions
pane would show them. It is the target being iterated on, not a decision.
Nothing here is adopted until an ADR records it, and every choice still open
is listed under [open decisions](#open-decisions).

The evidence behind it:

- [Lead and Worker design analysis](lead-worker-design-analysis.md): what each
  mechanism costs, the comparison per harness that #479 asks for, how a Lead
  and its Workers could communicate, and the options for the Sessions pane.
- The harness evidence, one note each: [Claude Code](lead-worker-claude-code-evidence.md),
  [Codex](lead-worker-codex-evidence.md) and
  [OpenCode](lead-worker-opencode-evidence.md).
- [Prior art](lead-worker-prior-art.md): how other agent managers,
  orchestration protocols, practitioners and dashboards handle the same
  problems.

Today a Worker is a Sub-agent of its Lead
([ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md),
[ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)).
This design calls that a **sub-agent Worker**. A Worker run as its own root
Agent Session is a **root-session Worker**.

## Leading candidate

The candidate this design develops, pending
[open decision 1](#open-decisions), is to run each Worker as a root Agent
Session started in its Issue Worktree, linked to its Lead by an explicit
declaration, and shown in the Sessions pane as an ordinary session row
grouped under that Lead.

- **Why.** Most of the trouble sub-agent Workers cause comes from a Worker not
  being a session. It cannot be placed, so it blocks Cleanup Repository-wide.
  Its Issue is declared rather than bound. Its activity flickers. Its listing
  must follow the Lead through every move and restart. And the pane needs a
  separate presentation for it. A root-session Worker would be placed, bound
  and ended by machinery Dashpot already has
  ([analysis](lead-worker-design-analysis.md#what-sub-agent-workers-cost)).
- **What it costs.** Lost completion notices, a hand-back transport,
  unattended permission asks, lifecycle hazards, a teardown step, and a link
  to the Lead that no harness records
  ([analysis](lead-worker-design-analysis.md#what-root-session-workers-cost)).
  The rest of this design sketches how those costs could be paid.
- **Where it would stop.** A harness that cannot meet the
  [Worker contract](#the-worker-contract) would keep sub-agent Workers under
  ADR 0096. A Worker's own reviewers would stay Sub-agents, and
  Repository-wide Cleanup blocking would still apply to them while they run.

## The Worker contract

A harness could run root-session Workers when a Worker can do all of these:

1. **Launch** in a named Worktree with its own Agent Session Identity. Its
   hooks place it there, and it is not a Sub-agent of the Lead.
2. **Bind** by running `work start` itself, so its run is observed at that
   Worktree.
3. **Link** to its Lead by a declaration that survives the Lead's restart.
4. **Report** a durable hand-back (a status file or the PR) and an
   observable end, its `work stop`.
5. **Receive** a message from the Lead at its next turn boundary, or be
   resumed with one.
6. **Stop** with positive evidence of its end.
7. **Run unattended** under a declared permission posture, or route its asks
   to a person.
8. **Persist while idle** long enough, or come back to its Issue after an
   interruption: on Claude Code its Orphaned Agent Run continues when the
   session resumes
   ([ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md)),
   and on Codex and OpenCode it runs `work start` again, which binds a new
   run in place of the orphaned one.

A harness that cannot meet 1, 2 or 6 by any route would keep sub-agent
Workers. Items 5, 7 and 8, and item 6 on OpenCode, can be met by the skill's
own routes, at the costs the table below records.

Waking the Lead is deliberately not a contract item. Completion is read from
durable evidence, so a wake-up only shortens the Lead's wait
([communication](#communication)).

## Mechanism per harness

| | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Launch | The Lead's shell runs `cd <worktree> && claude --bg --name issue-<n> "<brief>"` | The Lead's shell starts a detached `codex exec -C <worktree> --json -o <file> "<brief>"`; for a person who wants to watch, a daemon-hosted TUI in a tmux window | `opencode api POST /api/session` with `location.directory` and the Lead in `metadata`, then `POST /api/session/<id>/prompt` |
| Worker wakes the Lead | `SendMessage` to the Lead | `codex queue --thread <lead>` | `POST /api/session/<lead>/synthetic` |
| Lead reaches a Worker | `SendMessage`; `notify_when_idle` for a one-shot notice | Unknown for a running `exec` Worker, which exits at the end of its turn; otherwise `codex exec resume` | `POST /api/session/<worker>/prompt` |
| Unattended asks | A posture that does not prompt, with the Lead and Workers sharing one permission class; bypass needs one interactive acceptance first, and the brief must allow commits, since a session in a Worktree it did not create asks before committing | Bypass, or `auto_review`, which forces the `workspace-write` sandbox | Set when the session is made, or listed and answered by the Lead through the permission API |
| Environment | The supervisor's, with only forwarded variables, so the Lead's identity probably does not reach the Worker (unmeasured) | Inherited from the Lead's shell; Codex sets fresh ids for the Worker's own shells, but its hooks see the Lead's (source) | The service's, not the Lead's; replaced wholesale with `PUT /api/session/<id>/environment`, and lost when the service restarts |
| Stop | `claude stop <id>`; a killed Worker is restarted by its supervisor | Process exit; a signal | `work stop`, then a move back to the main Worktree, or deletion |
| Contract items met at a cost | 7: an ask waits for a person to attach. 8: an idle Worker is retired after about 61 minutes with no hook, and its run continues when someone attaches | 5 and 8: each follow-up is an `exec resume`, which binds a new run, and a queued message is held after an interrupt. 7: no one to ask, so the posture decides | 6: a finished Worker stays live until its finish step or deletion. 8: a service stop orphans every Worker's run, and each binds a new one |

How well each cell is evidenced is in the
[analysis](lead-worker-design-analysis.md#the-harnesses-compared), with the
comparison of both mechanisms on each harness
[against #479's criteria](lead-worker-design-analysis.md#against-479s-criteria).
Running root-session Workers on all three harnesses looks feasible, but Codex
has the least evidence. Until its experiment reports, a fallback would be root
Workers on Claude Code and OpenCode and sub-agent Workers on Codex, with the
pane able to show both at once.

## The Lead link

No harness links a root session to the session that launched it, and
identity is never inferred
([ADR 0038](../adr/0038-isolate-native-agent-session-identities.md)), so the
link would be a declaration. There are two candidates:

- **Worker-side:** a new `work start <n> --lead <harness>:<session-id>`
  option, recorded on the Worker's run beside its binding provenance. It
  survives the Lead's restarts and moves, and the Worker's own shell confirms
  its identity. The Lead's identity is checked against a live hook record that
  holds a run.
- **Lead-side:** `work assign`, which today takes a Sub-agent's identity
  (`--worker <id> --worktree <path>`), extended to accept a root session's
  identity and kept on the Lead's run as Worker Assignments are. It ends
  whenever the Lead's run ends, including on any `work start` or a Codex
  unload.

The analysis leans to the Worker-side declaration, with the Lead-side one as
an optional confirming handshake. Either way the link only groups and
explains rows: it carries no activity and no occupancy. OpenCode's session
`metadata` could carry the same declaration natively, but Dashpot does not
read it today, any client can change it, and a Worker's own Sub-agents
inherit it unless their creator supplies their own.

## Communication

The design would keep one harness-neutral core for coordination, and would use
each harness's own channel only to wake the other party sooner
([options compared](lead-worker-design-analysis.md#how-a-lead-and-its-workers-communicate)).

- **Liveness and completion come from Dashpot.** The Lead runs read-only
  queries: `work workers` lists its linked Workers, and `work wait` blocks
  until one changes state. A Worker's `work stop`, its session ending, or its
  run becoming orphaned is its completion.
- **The hand-back travels in a status file** in the Worktree's git
  directory. Today the skill uses one only for reports while a Worker works,
  from Codex v1 Workers and as OpenCode's fallback. Every Worker hands back
  in its final message, which a root-session Worker no longer delivers to its
  Lead.
- **The PR is the authoritative "ready" signal:** open, with green checks.
- **Harness channels are only doorbells:** `SendMessage`, `codex queue`, or
  OpenCode's synthetic message. A lost doorbell only delays the Lead.

How a Lead waits differs. A Claude Code Lead can run `work wait` in a
background shell and be woken when it ends. A Codex Lead blocks inside its
turn. An OpenCode Lead is better off without long-lived waiting shells,
which the Lead's idle eviction can end
([#467](https://github.com/ned2/dashpot/issues/467)), so it would poll with
short `work workers` calls and rely on the synthetic doorbell.

Dashpot would keep no mailbox ([open decision 4](#open-decisions)). The
Lead's shell would launch every Worker, so Dashpot would stay a passive
observer with read-only queries
([ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)).
A Dashpot helper that dispatches or drives Workers would be a controller,
which would need its own ADR and the consent
[#148](https://github.com/ned2/dashpot/issues/148) has not given. Examples
are a Codex app-server client, or an OpenCode plugin tool that posts notices
and relays asks.

## What Dashpot would build

- **The Lead link**, as [above](#the-lead-link).
- **`work workers` and `work wait`.** Read-only queries. `work show` already
  reads hook stores across Worktrees, but only its own checkout's Work
  Store, so these need new reads of the Work Stores of other Worktrees.
  `work show` would add "Worker of <Lead> (declared)" in a Worker's
  Worktree, and list the linked Workers and their observed state in the
  Lead's.
- **A Cleanup explanation** that names "Worker of <Lead> on #N". The
  occupancy rules don't change.
- **The Sessions pane grouping** sketched [below](#sessions-pane).
- **The skill rewrite.** Each harness's section of the execute-issues
  references would cover launch, the doorbell, steering, permission posture,
  stop and teardown, resume and binding again, the status-file hand-back, and
  the Worker brief, which would now run `work start` and `work stop`. The
  analysis [nets](lead-worker-design-analysis.md#against-479s-criteria) what
  this removes against what it adds for each harness, which for Codex and
  OpenCode is a larger skill than today's.

## Sessions pane

This section is input to [#444](https://github.com/ned2/dashpot/issues/444),
which owns the Sessions pane's presentation of Workers; #479 itself needs
only each mechanism's story, which the
[analysis](lead-worker-design-analysis.md#which-mechanism-gives-the-more-truthful-pane)
gives. The analysis's
[option B](lead-worker-design-analysis.md#how-workers-could-appear-in-the-sessions-pane),
then option D, works with either mechanism:

- a Lead's row followed by its Workers' rows, sorted as one unit by its
  liveliest member, in a stable order inside the group;
- a frozen column beside `◈` naming the harness on a Lead's row and drawing
  `├ worker` / `└ worker` connectors on Worker rows. The mockups call it
  ROLE as a placeholder; an earlier draft's AGENT is one the domain language
  avoids for a harness, so the label is open;
- the Issue leading each Worker row;
- a `+N` count of Sub-agents that hold no Worker Assignment, and a Worker
  total in the pane title;
- for sub-agent Workers only, `⇢` on a declared location and `not listed`
  for a Worker no longer reported;
- a cursor that falls back to a sibling, then the Lead;
- visibility decided per group;
- later, collapsible Lead groups.

The analysis sets aside a Textual `Tree`, which loses the columns; a
separate pane or screen; and a master/detail view.

## Contracts that would change

- **ADR 0092** chose sub-agent Workers and says a Worker runs no `work`
  command; both would change.
- **ADR 0096**'s Worker Assignment would remain for sub-agent Workers and be
  either generalised or joined by the Worker-side link.
- **The domain language.** Worker, Lead and Worker Assignment would be
  redefined. The term "worker" would also need a ruling, since the domain
  language avoids it for Claude Code's supervised worker process, which a
  root-session Worker on Claude Code would be. So would the pane column's
  label, if it were to name both harnesses and Workers.
- **AGENTS.md and the Issue work skill** today forbid a Sub-agent's
  `work start` and `work stop`. A root-session Worker would run both, while a
  sub-agent Worker still must not; a Claude Code Sub-agent's `work stop`
  would end its Lead's run, since it shares the Lead's session.
- **[#215](https://github.com/ned2/dashpot/issues/215)'s remaining
  attribution scenario** would be revisited.
- **Unaffected:**
  [ADR 0009](../adr/0009-hold-one-agent-run-per-session-across-worktrees.md),
  since each Worker is its own session;
  [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md),
  which still covers reviewers; and ADR 0008.

## Experiments

One pinned experiment per harness would settle its unknowns. Each runs in a
disposable fixture outside every Dashpot Project, as AGENTS.md requires, and
the evidence notes give each one's scenarios. Each is a new runner, so that
no acceptance run's runner or trace changes.

| Harness | Experiment | Main questions |
| --- | --- | --- |
| Claude Code | New `scripts/experiments/claude-479/`, from `claude-162` | Does the Lead's session identity reach a Worker launched from its shell? Do messages reach an idle and a busy Lead? Does `notify_when_idle` deliver? What happens across permission classes? Is a Cleanup blocker scoped to one Worktree? Does a Worker ask before committing? |
| Codex | New `scripts/experiments/codex-479/`, from `codex-420` | Does `exec -C` from a Lead's shell bind cleanly? Do the Lead's ids reach the Worker's hooks? What is `codex queue`'s latency to an idle, a busy and an unloaded Lead? Does a message reach a running `exec` Worker? Resume and binding again? Signals? A daemon restart? A sandboxed Lead? |
| OpenCode | New `scripts/experiments/opencode-479/`, from `opencode-421` | Root sessions with metadata? Does the synthetic message wake an idle Lead and steer a busy one? Asks answered through the API? Delete and move under load? The finish step? A service restart? A standalone Lead? |

Two questions cut across harnesses: whether the Lead's identity reaches a
Worker launched from its shell, and how an unattended ask behaves.

## A possible sequence

If open decision 1 adopts the candidate, one order would be:

1. Run the three experiments, which are independent of each other. The
   grouped Sessions pane is #444's to schedule, and could be built on today's
   sub-agent data meanwhile.
2. Record the decision in an ADR that would amend ADR 0092 and ADR 0096, and
   update the domain language.
3. Build the Lead link, `work workers` and `work wait`.
4. Rewrite the skill, one harness at a time, in the order the experiments
   clear them.

## Effect on open Issues

- **Still needed under either mechanism.**
  [#476](https://github.com/ned2/dashpot/issues/476)'s part 1 and the
  Sub-agent stranding fixes
  ([#427](https://github.com/ned2/dashpot/issues/427),
  [#458](https://github.com/ned2/dashpot/issues/458),
  [#459](https://github.com/ned2/dashpot/issues/459),
  [#460](https://github.com/ned2/dashpot/issues/460)), because reviewers
  remain Sub-agents and a harness may keep sub-agent Workers.
- **Shrink once a harness moves.**
  - [#444](https://github.com/ned2/dashpot/issues/444) becomes grouping by
    the link. As written it excludes Workers with their own Agent Runs, so it
    would need rescoping.
  - [#475](https://github.com/ned2/dashpot/issues/475),
    [#477](https://github.com/ned2/dashpot/issues/477) and
    [#478](https://github.com/ned2/dashpot/issues/478) would matter only for
    reviewers and for harnesses that keep sub-agent Workers.
  - #476's part 2, a person's override of `sub-agent` blockers, would be
    needed only while reviewers or sub-agent Workers run.
  - [#474](https://github.com/ned2/dashpot/issues/474), giving a Claude Code
    Sub-agent its own directory, would matter only for reviewers.

  Re-prioritise all of these after the decision.
- **Grows.** [#473](https://github.com/ned2/dashpot/issues/473)'s presence
  filter, since live OpenCode Workers that have finished add rows.
- **Constrains.** [#454](https://github.com/ned2/dashpot/issues/454)'s
  restriction of OpenCode Worker leading to the shared service applies to root-session
  Workers too: a doorbell into a standalone Lead is the two-Host-Process
  case, so such a Lead would poll only.
- **Served.** The Lead link keeps
  [#243](https://github.com/ned2/dashpot/issues/243)'s Issue-list
  attribution able to name the Lead, and #148's consent question stays where
  it is, since Dashpot launches nothing.

## Open decisions

The mechanism:

1. Adopt root-session Workers, and on which harnesses first?
2. Who declares the Lead link: the Worker, the Lead, or both?
3. Should Dashpot ship `work workers` and `work wait`, or leave polling to the
   skill?
4. Confirm that Dashpot keeps no mailbox.
5. What permission posture do unattended Workers run under? This is a
   security call, and it may differ per harness.
6. Who may tear a Worker down, given that deleting an OpenCode session loses
   its history and that one session moving or deleting another is a new
   authority?
7. The vocabulary: what Worker means once it can be a root session, and how
   it is kept apart from Claude Code's supervised worker process.

The Sessions pane, for [#444](https://github.com/ned2/dashpot/issues/444) to
settle:

8. Are Lead groups expanded by default or collapsible, and on which key?
   `Enter` has no Sessions-pane action today.
9. Does a `not listed` sub-agent Worker stay until `work unassign` or the
   run ends, or drop out once no longer reported?
10. Should a sub-agent Worker's declared Worktree appear in the pane at all,
    or only in the Cleanup explanation
    ([#478](https://github.com/ned2/dashpot/issues/478))?
11. Does [#473](https://github.com/ned2/dashpot/issues/473)'s presence filter
    exempt bound or running sessions, which `--bg` Workers always are?
12. Does the Issues pane keep a "delegated" distinction once Workers hold
    their own Issue Binding?
13. What does the frozen role column say, given that the domain language
    avoids "agent" for a harness, and is it frozen for every row?
14. How does a Worker waiting on a person stay visible however the pane is
    grouped: a pane-level count, ordering groups by their most urgent member,
    or never folding such a Worker away? Agent UIs group by attention rather
    than by parent ([prior art](lead-worker-prior-art.md#presentation)).
15. Should the pane show each Lead's number of active Workers against the
    three to five per person that practitioners report as a ceiling?

Raised by the [prior art](lead-worker-prior-art.md#suggestions-for-the-design):

16. Should the Lead stamp its identity into each Worker's launch environment,
    so that `work start` can confirm the declared link? On Claude Code the
    stamp may not survive, since a `--bg` Worker receives only forwarded
    variables.
17. Is the hand-back keyed on Issue, PR, head commit and state, so that a
    lost or repeated doorbell is harmless?
18. Should Dashpot flag a lost completion by inconsistency (a PR open while
    the status says working, a session ended with no status, done with no
    PR), and show "quiet for N minutes" rather than calling a Worker stalled?
19. What is the Lead-ended policy: does a Worker whose Lead has ended keep
    running and get shown as such, unlike Temporal's default of ending the
    child? This is not an Orphaned Agent Run, whose session's Host Process is
    gone.
20. Should cancelled, rejected (the Issue is not actionable) and failed be
    distinct Worker outcomes?
