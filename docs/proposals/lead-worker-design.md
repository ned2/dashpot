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
- The [root-session Workers experiment](../spikes/root-session-workers-spike.md),
  which ran the pinned [experiments](#experiments) below.
- [Prior art](lead-worker-prior-art.md): how other agent managers,
  orchestration protocols, practitioners and dashboards handle the same
  problems.

This revision corrects the facts the
[2026-10-05 review](../reviews/lead-worker-design-review-2026-10-05.md)
found stale or wrong, and brings the mechanism in line with the revised
evidence notes. It changes no lean, recommendation or contract item; where a
corrected fact bears on one, the text says so and leaves the choice to that
review.

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
- **Facts that bear on the Why.** Since
  [ADR 0112](../adr/0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md),
  a person can remove a Worktree despite the `sub-agent` blockers its
  preview lists, with a Sub-agent Override (`--despite-subagents`), so the
  Repository-wide block no longer freezes Cleanup for a person; no agent
  gives the override, so a Lead's own close-out still waits for every
  Worker. And under root-session Workers, each Worker's reviewer Sub-agent
  re-imposes the Repository-wide `sub-agent` blocker
  ([ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md))
  while it runs (measured on Claude Code and OpenCode, #479), and every
  Worker reviews. Both
  weaken the first reason above; see the 2026-10-05 review.
- **What prior art says.** Vendors ship Sub-agents that write in their own
  Worktrees, so the case for root sessions rests on lifetime and
  observability, not on write safety
  ([prior art](lead-worker-prior-art.md#summary)).
- **What it costs.** Lost completion notices, a hand-back transport,
  unattended permission asks, lifecycle hazards, a teardown step, and a link
  to the Lead that no harness records where Dashpot reads it
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
   ([ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md),
   and [ADR 0075](../adr/0075-end-an-orphaned-run-at-its-replacements-session-end.md)
   for a replacement the supervisor starts), but that continuation does not
   cover a Worker its supervisor resumes after SIGTERM: the killed process's
   `SessionEnd` has already ended the run, so the Worker runs `work start`
   again (measured, #479). On Codex it runs `work start`
   again after a resume, and on OpenCode after a fresh prompt, which binds a
   new run in place of the orphaned one. A turn OpenCode's restarted service
   resumes by itself cannot do so: its `work start` is refused as stale
   until a fresh prompt arrives (measured, #479).

A harness that cannot meet 1, 2 or 6 by any route would keep sub-agent
Workers. Items 5, 7 and 8, and item 6 on OpenCode, can be met by the skill's
own routes, at the costs the table below records. Items 3 and 4 depend on no
harness route, but neither is met yet. Item 3 needs a link that today's code
would not keep: a Worker-side link ends with the Worker's run, and a Lead
whose session id changes is no longer named by it
([the Lead link](#the-lead-link)). Item 4's status file is deleted with the
Worktree, so it is durable only until Cleanup, and the Lead keeps what it
needs from it first.

Waking the Lead is deliberately not a contract item. Completion is read from
durable evidence, so a wake-up only shortens the Lead's wait
([communication](#communication)).

## Mechanism per harness

| | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Launch | The Lead's shell runs `(cd <worktree> && claude --bg --name issue-<n> "<brief>")` in a subshell: an un-subshelled `cd` in a Lead whose added directories hold the Worktree moves the Lead's own session there, and a `dontAsk` Lead needs `permissions.additionalDirectories` and allow rules to dispatch at all (measured, #479). `--bg` prints an 8-character short id and ignores `--session-id`; the full session id comes from `claude agents --json --cwd <worktree>` (measured, #479) | From a full-access or escalated shell only, a detached `codex exec -C <worktree> --json -o <file> "<brief>"`, whose first `--json` event, `thread.started`, gives the Worker's id; launched from a sandboxed shell, it dies with that command (measured, #479). For a person who wants to watch, a daemon-hosted TUI in a tmux window | `opencode api POST /api/session` with `location.directory` and the Lead in `metadata`, then `POST /api/session/<id>/prompt`; until prompted it reads waiting ([ADR 0106](../adr/0106-record-a-session-waiting-after-a-session-start-that-begins-no-turn.md)). The `dashpot-worker` agent is accepted on a root session (measured, #479) |
| Worker wakes the Lead | `SendMessage` to the Lead: an idle Lead gets a new turn, and a busy one receives it inside its running turn, after the current tool call, with no `Stop` between (measured, #479) | `codex queue --thread <lead>`, from an unsandboxed shell only; a sandboxed Worker falls back to a status file or the Lead's reading of `-o` and `--json` (measured, #479) | `POST /api/session/<lead>/synthetic`, which wakes an idle Lead and steers a busy one (measured, #479) |
| Lead reaches a Worker | `SendMessage`, which lands inside a busy Worker's running turn (measured, #479); `notify_when_idle` for a one-shot notice, which quotes the Worker's final text (measured, #479) | Mail queued to a running `exec` Worker is lost (measured, #479); once it has exited, `codex exec -C <worktree> <posture> resume <id> "<message>"`, restating the sandbox flags, which a bare resume drops | `POST /api/session/<worker>/prompt` |
| Unattended asks | A posture that does not prompt, with the Lead and Workers sharing one permission class: bypass, or prompting (manual, `dontAsk` and auto); across classes a message is held, and a `-p` receiver drops it after five minutes (measured, #479). Auto, the default permission mode since 2.1.283, and `dontAsk` work with `--bg`; only bypass needs one interactive acceptance first; auto falls back to prompting after 3 blocks in a row or 20 in total (documented). A Worker blocked on an ask lists in `claude agents --json` as `blocked`, waiting for a permission prompt, while Dashpot reads its run as `running` (measured, #479). The brief must allow commits, since a `--bg` session is instructed to ask before committing in a Worktree it did not enter itself; the instruction is in the system prompt, not a permission gate, and `--settings '{"worktree":{"bgIsolation":"none"}}'` removes it (measured, #479) | No one to ask: full access; `--approve-for-me`, which sets `auto_review`, `on-request` and the `workspace-write` sandbox, and so cannot queue; or `-c approvals_reviewer=auto_review`, which forces no sandbox. An `auto_review` approval is a model's, not a person's consent. Every resume restates the posture | Set when the session is made (unmeasured), or listed and answered by the Lead through the permission API (measured, #479): `reject` cancels every pending ask in the session and ends the turn unless it carries a `message`, and `always` saves a Project-wide rule that also answers the Lead's asks |
| Environment | The supervisor's whole environment, inherited from the shell that first started it, for every Worker of every Lead; a dispatch's own shell variables, credentials included, never reach its Worker. The Worker's identity variables are its own, so the Lead's identity does not reach it, and a `--settings` `env` reaches only its own Worker (measured, #479) | Inherited from the Lead's shell; Codex sets fresh ids for the Worker's own shells, so its `work start` makes a root claim, but its hooks see the Lead's (measured, #479) | The service's, not the Lead's: `GH_TOKEN` exported in the Lead's shell was absent (measured, #479); replaced wholesale with `PUT /api/session/<id>/environment`, and lost when the service restarts |
| Stop | `claude stop <id>`, which publishes `SessionEnd` and frees the Worktree (measured, #479). After SIGTERM the supervisor resumes the same session in a new process about 10.5 seconds later, but the killed process's `SessionEnd` has ended its run, so the Worker must `work start` again (measured, #479) | Exit at the end of its turn, or SIGINT, which publishes `Interrupt` and `SessionEnd`; SIGTERM and SIGKILL publish nothing and orphan the run (measured, #479) | `work stop`, then a move back to the main Worktree, or deletion; the `dashpot-worker` agent's move denial holds on a root session (measured, #479), so a Worker on it would be deleted, which [open decision 6](#open-decisions) weighs |
| Contract items met at a cost | 7: an ask waits for a person to attach (several clients attached to one `--bg` session are unmeasured, [#370](https://github.com/ned2/dashpot/issues/370)), and Dashpot reads the asking Worker as `running` (measured, #479). 8: an idle Worker is retired after about 61 minutes with no hook, and its run continues when someone attaches; a SIGTERM respawn needs a new `work start` (measured, #479) | 5 and 8: each follow-up is an `exec resume` with its posture restated, which binds a new run; mail to a running Worker is lost. 7: no one to ask, so the posture decides | 6: a finished Worker stays live until its finish step or deletion. 8: a service stop orphans every Worker's run; the restarted service resumes cut-off turns unseen by Dashpot, and a Worker binds a new run only after a fresh prompt. Pending asks are lost at a stop |

How well each cell is evidenced is in the
[analysis](lead-worker-design-analysis.md#the-harnesses-compared), with the
comparison of both mechanisms on each harness
[against #479's criteria](lead-worker-design-analysis.md#against-479s-criteria).
When this design was first written, running root-session Workers on all three
harnesses looked feasible but Codex had the least evidence, and a fallback
until its experiment reported would be root Workers on Claude Code and
OpenCode and sub-agent Workers on Codex, with the pane able to show both at
once. All three experiments have since reported
([experiment](../spikes/root-session-workers-spike.md)). Codex root Workers
worked under four constraints: launch from a full-access or escalated shell,
`codex queue` only from Worker to Lead, stop with SIGINT, and resume with
the posture restated. That bears on the fallback; see the 2026-10-05 review.
Claude Code root Workers worked at 2.1.287 and 2.1.289
([experiment](../spikes/root-session-workers-spike.md#claude-code-21289)),
with each Worker's environment, credentials included, set by whichever shell
first started the supervisor rather than by its Lead. That bears on
[open decision 5](#open-decisions); see the 2026-10-05 review.

## The Lead link

No harness links a root session to the session that launched it in a record
Dashpot reads, and identity is never inferred
([ADR 0038](../adr/0038-isolate-native-agent-session-identities.md)), so the
link would be a declaration. Two near misses: Claude Code launches agent-teams
split-pane teammates with a hidden `--parent-session-id` option, "Parent
session ID for analytics correlation", which no hook is known to carry and no
`--bg` launch has been measured with; and Warp, outside the harnesses Dashpot
supports, records a child run's `parent_run_id`
([prior art](lead-worker-prior-art.md#the-link-between-a-lead-and-its-workers)).
There are two candidates:

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
inherit it unless their creator supplies their own; a fork of a Worker
copies it too (measured, #479).

What today's code does, which either candidate has to handle (facts, not a
choice between them; they bear on [open decision 2](#open-decisions)):

- **A Worker-side link ends with the Worker's run.** `work stop` and a
  `SessionEnd` delete the Worker's Work Store record
  ([`work_store.py`](../../src/dashpot/sessions/work_store.py),
  `stop_current` and `end_session_runs`), so a link stored on that run
  vanishes at the completion it is meant to explain. A Worker still live
  after its `work stop` is then an unbound, unlinked session.
- **A `work start` without `--lead` drops it.** Every `work start` writes a
  fresh record, so a Codex resume follow-up or an OpenCode recovery that
  binds again without the option loses the link.
- **The Lead's identity has no check to reuse.** `validate_session_claim`
  refuses an OpenCode claim without the plugin's pid
  ([`hook_claims.py`](../../src/dashpot/sessions/hook_claims.py)), so an
  OpenCode Lead named in `--lead` would be refused, and requiring a Lead that
  holds a run refuses linking after a Codex Lead unloads.
- **A Conversation Switch changes the Lead's session id**
  ([ADR 0101](../adr/0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)),
  so a link recorded as `<harness>:<session-id>` then names a session that no
  longer runs.
- **`work assign` validates a Sub-agent.** It accepts a Worker only when the
  Lead's own hook record lists it, so a Lead-side link to a root session
  needs a second validation path. Unlike the Worker-side link, an assignment
  survives the Worker's own `work stop`.

## Communication

The design would keep one harness-neutral core for coordination, and would use
each harness's own channel only to wake the other party sooner
([options compared](lead-worker-design-analysis.md#how-a-lead-and-its-workers-communicate)).

- **Liveness and completion come from Dashpot.** The Lead runs read-only
  queries: `work workers` lists its linked Workers, and `work wait` blocks
  until one changes state. A Worker's `work stop` or its session ending is
  the end of its Issue work. Its run becoming orphaned is not: an
  [Orphaned Agent Run](../domain-language.md#observation) is Issue
  work whose process is gone before it ended, which a resume or a new
  `work start` continues, so the Lead treats it as needing attention. Neither
  end says whether the work succeeded; the hand-back and the PR say that.
- **The hand-back travels in a status file** in the Worktree's git
  directory. Today the skill uses one, `execute-issues-status`, for a
  Worker's reports from Codex v1 Workers and as OpenCode's fallback, and a
  second, `execute-issues-lead`, for the Lead's broadcasts to every Codex
  Worker. Both are removed with the Worktree. Every Worker hands back in its
  final message, which a root-session Worker no longer delivers to its Lead.
- **The PR is the authoritative "ready" signal:** open, with green checks,
  which is where an agent's work ends
  ([ADR 0089](../adr/0089-leave-the-pr-merge-to-the-operator.md)).
- **Harness channels are only doorbells:** `SendMessage`, `codex queue`, or
  OpenCode's synthetic message. A lost doorbell only delays the Lead. No
  doorbell measured interrupts a tool call in flight, though not every one
  waits for the end of a turn
  ([prior art](lead-worker-prior-art.md#coordination-polling-doorbells-and-the-hand-back)
  suggests it should). Measured so far (#479): OpenCode's `steer` arrives at a busy Lead's next
  step and `queue` after its last planned step, and `codex queue` starts a
  turn on an idle Lead and waits out a busy one. Claude Code's `SendMessage`
  starts a turn on an idle Lead, but reaches a busy one inside its running
  turn, after the current tool call, with no `Stop` between.

How a Lead waits differs. An interactive Claude Code Lead can run
`work wait` in a background shell and be woken when it ends. A `-p` or
Agent SDK Lead's background command is limited to 30 minutes by default and
2 hours at most, and a `-p` run's end stops it (documented), so its
`work wait` is cut short; whether a `--bg` Lead counts as unattended for
that limit is unmeasured. A Codex Lead blocks inside its
turn. An OpenCode Lead is better off without long-lived waiting shells,
which the Lead's idle eviction can end (unmeasured,
[#467](https://github.com/ned2/dashpot/issues/467)), so it would poll with
short `work workers` calls and rely on the synthetic doorbell. A blocking
`opencode api POST /api/experimental/session/<id>/wait` held for 330 seconds
without being cut (measured, #479).

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
  Store. `work start`, `work assign` and `work stop` already read the Work
  Stores of every Worktree, so these would reuse those reads. `work show`
  would add "Worker of <Lead> (declared)" in a Worker's Worktree, and list
  the linked Workers and their observed state in the Lead's.
- **A Cleanup explanation** that names "Worker of <Lead> on #N". The
  occupancy rules don't change.
- **The Sessions pane grouping** sketched [below](#sessions-pane).
- **The skill rewrite.** Each harness's section of the execute-issues
  references would cover launch, the doorbell, steering, permission posture,
  stop and teardown, resume and binding again, the status-file hand-back, and
  the Worker brief, which would now run `work start` and `work stop`. The
  arc rules would change too: who binds, staying where the Lead bound, and
  removing Worktrees only when no Worker is live. So would wave sizing,
  which today a harness's Sub-agent cap bounds, and the Worker's `gh`
  credentials, which a root Worker may not inherit (measured absent on
  OpenCode, #479; on Claude Code they come from whichever shell first
  started the supervisor, measured, #479). The analysis
  [nets](lead-worker-design-analysis.md#against-479s-criteria) what this
  removes against what it adds for each harness, which for Codex and
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
  command; both would change. So would its rules that the Lead stays where
  it bound while any Worker runs, and removes Worktrees only once no Worker
  is live.
- **ADR 0096**'s Worker Assignment would remain for sub-agent Workers and be
  either generalised or joined by the Worker-side link.
- **[ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md)**
  holds a session running while its Sub-agents work. Root-session Workers
  are not the Lead's Sub-agents, so a Lead whose Workers work would read
  `waiting`, as would its Arc's Issue, unless something else holds it.
- **[ADR 0093](../adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)**'s
  `dashpot-worker` agent is accepted on a root session, and its move denial
  holds there (measured, #479), so a root Worker on it cannot make the finish
  step's move back. Either the finish step or the agent would change, and
  with it [#437](https://github.com/ned2/dashpot/issues/437), which reports
  other definitions of that agent.
- **The domain language.** Worker, Lead and Worker Assignment would be
  redefined. The term "worker" would also need a ruling, since the domain
  language avoids it for Claude Code's supervised worker process, which a
  root-session Worker on Claude Code would be. So would the pane column's
  label, if it were to name both harnesses and Workers.
- **AGENTS.md and the Issue work skill** today forbid a Sub-agent's
  `work start` and `work stop`. A root-session Worker would run both, while a
  sub-agent Worker still must not; a Claude Code Sub-agent's `work stop`
  would end its Lead's run, since it shares the Lead's session.
- **[#215](https://github.com/ned2/dashpot/issues/215)'s scenario 2**, one
  session leading several Issues, which ADR 0096 decided, would be revisited,
  as #215 itself says. Its open scenario 1, several Issues in one PR, is
  unaffected.
- **Unaffected:**
  [ADR 0009](../adr/0009-hold-one-agent-run-per-session-across-worktrees.md),
  since each Worker is its own session;
  [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md),
  which still covers reviewers, whose Repository-wide blocker each Worker's
  reviewer re-imposes while it runs (measured on Claude Code and OpenCode,
  #479);
  [ADR 0104](../adr/0104-block-worktree-removal-while-a-process-runs-inside-it.md)'s
  `process` blocker and ADR 0112's Sub-agent Override, which still apply; and
  ADR 0008.

## Experiments

One pinned experiment per harness was to settle its unknowns. Each runs in a
disposable fixture outside every Dashpot Project, as AGENTS.md requires, and
the evidence notes give each one's scenarios. Each is a new runner, so that
no acceptance run's runner or trace changes.

All three experiments have run. The
[root-session Workers experiment](../spikes/root-session-workers-spike.md)
reports them, the Claude Code run under
[Claude Code 2.1.289](../spikes/root-session-workers-spike.md#claude-code-21289),
and the revised [Claude Code](lead-worker-claude-code-evidence.md#the-479-experiment),
[Codex](lead-worker-codex-evidence.md#the-479-experiment) and
[OpenCode](lead-worker-opencode-evidence.md#the-479-experiment) notes and
the mechanism table above carry their answers. The questions they set out to
answer:

| Harness | Experiment | Main questions |
| --- | --- | --- |
| Claude Code | New `scripts/experiments/claude-479/`, from `claude-162` | Does the Lead's session identity reach a Worker launched from its shell? Do messages reach an idle and a busy Lead? Does `notify_when_idle` deliver? What happens across permission classes? Is a Cleanup blocker scoped to one Worktree? Does a Worker ask before committing? |
| Codex | New `scripts/experiments/codex-479/`, from `codex-420` | Does `exec -C` from a Lead's shell bind cleanly? Do the Lead's ids reach the Worker's hooks? What is `codex queue`'s latency to an idle, a busy and an unloaded Lead? Does a message reach a running `exec` Worker? Resume and binding again? Signals? A daemon restart? A sandboxed Lead? |
| OpenCode | New `scripts/experiments/opencode-479/`, from `opencode-421` | Root sessions with metadata? Does the synthetic message wake an idle Lead and steer a busy one? Asks answered through the API? Delete and move under load? The finish step? A service restart? A standalone Lead? |

Two questions cut across harnesses: whether the Lead's identity reaches a
Worker launched from its shell, and how an unattended ask behaves.

## A possible sequence

If open decision 1 adopts the candidate, one order would be:

1. Run the three experiments, which are independent of each other; all
   three have run. The grouped Sessions pane is #444's to schedule,
   and arc [#498](https://github.com/ned2/dashpot/issues/498) defers #444,
   and #478, until #479 decides.
2. Record the decision in an ADR that would amend ADR 0092 and ADR 0096, and
   update the domain language.
3. Build the Lead link, `work workers` and `work wait`.
4. Rewrite the skill, one harness at a time, in the order the experiments
   clear them.

### If sub-agent Workers stay

If open decision 1 keeps sub-agent Workers, #479's outcome has ADR 0092
record this alternative and why it was rejected. Then:

- #444, #477 and #478 resume under the sub-agent mechanism, no longer
  deferred by #498.
- [#517](https://github.com/ned2/dashpot/issues/517)'s display of a Claude
  Code session waiting on a Background Command still ships, since only this
  decision blocks it, and so do the fixes listed as still needed
  [below](#effect-on-open-issues).
- The Worker contract, the Lead link, `work workers` and `work wait`, the
  skill rewrite and the contract changes above are moot, as are open
  decisions 2 to 7, 11, 16 and 19. Decisions 8 to 10, 12 to 15, 17, 18 and
  20 remain.

## Effect on open Issues

- **Already landed.**
  [#427](https://github.com/ned2/dashpot/issues/427)
  ([ADR 0102](../adr/0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md)),
  [#458](https://github.com/ned2/dashpot/issues/458) (ADR 0101),
  [#460](https://github.com/ned2/dashpot/issues/460) (ADR 0107) and
  [#459](https://github.com/ned2/dashpot/issues/459) (ADR 0109), the last
  two on `main` after this branch's base;
  [#476](https://github.com/ned2/dashpot/issues/476) (ADR 0104's `process`
  blocker and ADR 0112's Sub-agent Override);
  [#454](https://github.com/ned2/dashpot/issues/454)
  ([ADR 0108](../adr/0108-keep-opencode-self-move-and-leading-workers-on-the-shared-service.md));
  [#466](https://github.com/ned2/dashpot/issues/466)
  ([ADR 0113](../adr/0113-name-a-background-command-by-its-process-and-show-it-on-a-waiting-claude-code-session.md)),
  whose display moved to #517; and
  [#243](https://github.com/ned2/dashpot/issues/243) (ADR 0096).
- **Still needed under either mechanism**, because reviewers remain
  Sub-agents and a harness may keep sub-agent Workers:
  - [#519](https://github.com/ned2/dashpot/issues/519), a Claude Code
    session that enters another Worktree leaving a running record in the
    first, which a Lead or Worker moving with `EnterWorktree` meets;
  - [#520](https://github.com/ned2/dashpot/issues/520), ADR 0107's tags in
    OpenCode recovery, for reviewers on OpenCode;
  - #517, blocked by #479, whose display covers a Worker's `gh run watch`
    and a Claude Code Lead's background `work wait`;
  - [#518](https://github.com/ned2/dashpot/issues/518): a `claude -p` that
    exits publishes no `SessionEnd` at 2.1.289, which bears on any `-p`
    route a Lead uses.
- **Shrink once a harness moves.**
  - [#444](https://github.com/ned2/dashpot/issues/444) becomes grouping by
    the link. As written it excludes Workers with their own Agent Runs and
    asks to avoid independent Worker Agent Runs, so it would need rescoping.
  - [#475](https://github.com/ned2/dashpot/issues/475),
    [#477](https://github.com/ned2/dashpot/issues/477) (blocked by #474) and
    [#478](https://github.com/ned2/dashpot/issues/478) would matter only for
    reviewers and for harnesses that keep sub-agent Workers.
  - [#472](https://github.com/ned2/dashpot/issues/472), a Claude Code
    Sub-agent's interim stop while its own background work runs, would
    matter only for reviewers.
  - [#492](https://github.com/ned2/dashpot/issues/492), an unloaded Codex
    Lead ending its Workers' assignments, would no longer end a root
    Worker's Issue work, which its own run holds (inference).
  - ADR 0112's Sub-agent Override, already shipped, would be needed only
    while reviewers or sub-agent Workers run.

  Re-prioritise all of these after the decision.
- **An input to the decision.**
  [#474](https://github.com/ned2/dashpot/issues/474) re-measures whether a
  Claude Code Sub-agent can be placed: the Agent tool's `cwd`, which the
  binary omits from the model's schema at 2.1.287 and 2.1.289, and
  `meta.json` parentage. Its result bears on open decision 1, not only on
  reviewers.
- **Grows.** [#473](https://github.com/ned2/dashpot/issues/473)'s presence
  filter, since live OpenCode Workers that have finished add rows. Its
  boundary that no Worker gains an independent Agent Run or Issue Binding
  would need editing.
- **Constrains.**
  - ADR 0108 lets an OpenCode Lead lead Workers only on the shared service:
    a standalone Lead leads none. The #479 experiment measured why: a
    Worker's notice ran a standalone Lead's session on the shared service
    while its private server was mid-turn. Root-session Workers under a
    standalone Lead would mean amending ADR 0108.
  - [#148](https://github.com/ned2/dashpot/issues/148)'s consent question
    stays where it is, since Dashpot launches nothing. But one session
    stopping, moving or deleting another, as teardown would, is its authority
    question, and its body's premise that Workers remain Sub-agents would
    need editing.
  - [#481](https://github.com/ned2/dashpot/issues/481): every hook runs the
    main checkout's publisher, while a root Worker's `uv run dashpot
    work start` and `work stop` would run its own Worktree's Dashpot, so the
    two can differ in version.
- **Served.** #243, closed by ADR 0096, gave Issue-list rows their Workers'
  activity through assignments. Under root-session Workers each Worker's own
  Issue Binding gives it, and the link keeps the Lead nameable.

## Open decisions

The mechanism:

1. Adopt root-session Workers, and on which harnesses first? #474's result,
   whether a Claude Code Sub-agent can be placed, is an input.
2. Who declares the Lead link: the Worker, the Lead, or both? This includes
   decision 16, whether the Lead stamps its identity into each Worker's
   launch environment so that `work start` can confirm the declared link.
   On Codex a `DASHPOT_LEAD` stamp on the launch command reaches the
   Worker's shells and hooks (measured, #479). On Claude Code a stamp in
   the launch shell's environment fails and misattributes: every `--bg`
   Worker carried the stamp of the dispatch that first started the
   supervisor, not its own, a second Lead's Workers included; a
   `--settings '{"env":{…}}'` stamp reaches only its own Worker's shells and
   hooks, and survives a respawn (measured, #479). The facts under
   [the Lead link](#the-lead-link) bear on this decision.
3. Should Dashpot ship `work workers` and `work wait`, or leave polling to the
   skill?
4. Confirm that Dashpot keeps no mailbox.
5. What permission posture do unattended Workers run under? This is a
   security call, and it may differ per harness.
6. Who may tear a Worker down, given that deleting an OpenCode session loses
   its history and that one session moving or deleting another is a new
   authority? Partly answered: a Codex `exec` Worker needs no teardown, since
   its exit frees its Worktree (measured, #479); a root OpenCode session may
   move only itself
   ([ADR 0094](../adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md)),
   and moving another is #148's question; ADR 0093's agent cannot move at
   all. Still open: whether a Lead may stop or delete a Worker, by
   `claude stop` or OpenCode deletion.
7. The vocabulary: what Worker means once it can be a root session, and how
   it is kept apart from Claude Code's supervised worker process. This
   includes decision 13: what the frozen role column says, given that the
   domain language avoids "agent" for a harness, and whether it is frozen
   for every row.

The Sessions pane, for [#444](https://github.com/ned2/dashpot/issues/444) to
settle:

8. Are Lead groups expanded by default or collapsible, and on which key?
   `Enter` has no Sessions-pane action today.
9. Does a `not listed` sub-agent Worker stay until `work unassign` or the
   run ends, or drop out once no longer reported? ADR 0096 already answers
   how long the assignment holds: until `work unassign` or the Lead's run
   ends. Still open: whether the pane keeps a row for it once its Sub-agent
   is no longer reported.
10. Should a sub-agent Worker's declared Worktree appear in the pane at all,
    or only in the Cleanup explanation
    ([#478](https://github.com/ned2/dashpot/issues/478))?
11. Does [#473](https://github.com/ned2/dashpot/issues/473)'s presence filter
    exempt bound or running sessions, which `--bg` Workers always are?
    #473 already requires bound, orphaned, running and uncertain
    observations to stay conspicuous, which answers it for bound and running
    sessions. Still open: #473's boundary that no Worker gains an Agent Run,
    which root-session Workers would contradict.
12. Does the Issues pane keep a "delegated" distinction once Workers hold
    their own Issue Binding? There is none today: the Issues pane's
    activity column merges an Issue's bound runs and its assigned working
    Workers into one Glyph. Still open: whether it should tell a Worker's own
    binding from its Lead's.
13. Merged into decision 7.
14. How does a Worker waiting on a person stay visible however the pane is
    grouped: a pane-level count, ordering groups by their most urgent member,
    or never folding such a Worker away? Agent UIs group by attention rather
    than by parent ([prior art](lead-worker-prior-art.md#presentation)). A
    Worker its harness's permission system has stopped, such as Claude Code's
    auto mode or Codex's auto-review after repeated denials, is waiting on a
    person too
    ([prior art](lead-worker-prior-art.md#state-vocabulary-and-attention)).
15. Should the pane show each Lead's number of active Workers against the
    three to five per person that prior art reports as a comfort level?

Raised by the [prior art](lead-worker-prior-art.md#suggestions-for-the-design):

16. Merged into decision 2.
17. Is the hand-back keyed on Issue, PR, head commit and state, so that a
    lost or repeated doorbell is harmless?
18. Should Dashpot flag a lost completion by inconsistency (a PR open while
    the status says working, a session ended with no status, done with no
    PR), and show "quiet for N minutes" rather than calling a Worker stalled?
19. What is the Lead-ended policy: does a Worker whose Lead has ended keep
    running and get shown as such? Both precedents exist: Temporal ends a
    child by default and Claude Projects' Pause and Archive stop every
    thread, while Warp leaves children running on purpose. This is not an
    Orphaned Agent Run, whose session's Host Process is gone.
20. Should cancelled, rejected (the Issue is not actionable) and failed be
    distinct Worker outcomes?
