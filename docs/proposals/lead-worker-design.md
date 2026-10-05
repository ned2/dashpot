---
status: proposal
date: 2026-10-05
---

# Lead and Worker design

A design for [Issue #479](https://github.com/ned2/dashpot/issues/479): how a
Lead could run its Workers as root Agent Sessions, how they would talk, and
how the Sessions pane would show them.

**Decided on 2026-10-05 by
[ADR 0124](../adr/0124-keep-sub-agent-workers-and-qualify-root-session-workers-per-harness.md).**
Sub-agent Workers stay the mechanism on every harness. The root-session
design below is the shape a Claude Code pilot takes, and Codex and OpenCode
wait for their [re-open triggers](#the-decision-and-the-pilot). This
revision records the recommendations of the
[2026-10-05 review](../reviews/lead-worker-design-review-2026-10-05.md),
all of which the maintainer accepted. Nothing here is adopted on a harness
until an ADR written after its pilot passes says so.

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

Today a Worker is a Sub-agent of its Lead
([ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md),
[ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)).
This design calls that a **sub-agent Worker**. A Worker run as its own root
Agent Session is a **root-session Worker**. That second term is this
document's only: the [domain language](../domain-language.md#observation)
avoids calling such a session a Worker until an adopting ADR rules on the
[vocabulary](#for-the-adopting-adr).

## The decision and the pilot

- **Sub-agent Workers remain the shipped mechanism on every harness.**
  ADR 0124 amends ADR 0092 to record root-session Workers as considered and
  qualified one harness at a time.
- **Claude Code is qualified first, through a pilot** whose pass criteria
  ADR 0124 fixed in advance. A `--bg` Worker launched by a Lead, under the
  postures of [contract item 7](#the-worker-contract):
  - (a) takes a real Issue to an open PR with green CI and this
    Repository's review evidence, without a person;
  - (b) neither enters another Worktree nor parks at a commit;
  - (c) can run `gh`;
  - (d) blocks only its own Worktree outside its review windows;
  - (e) is known complete by its Lead within a bounded delay;
  - (f) leaves a state Dashpot reads correctly when evicted while idle.

  The pass is judged under the posture the maintainer chooses; the pilot
  counts how often `auto` parks and repeats under `dontAsk` to inform that
  choice. A pass leads to an adopting ADR that makes root-session Workers
  an opt-in mode on Claude Code and settles the [Lead link](#the-lead-link), contract
  items 7 and 9, and the decisions [left to it](#for-the-adopting-adr).
- **Each harness re-opens on its own trigger:**
  - Claude Code: its pilot passes.
  - Codex: `codex queue` works from `workspace-write`, or `exec` accepts
    mail while it runs.
  - OpenCode: the plugin observes the turns a restarted service resumes, and
    a pending ask survives a restart.
  - Any harness: [#474](https://github.com/ned2/dashpot/issues/474) shows a
    Sub-agent can be placed, which could let
    [ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md)
    narrow its blocker with no root sessions ([N3](#experiments)).
- **The cost of a standing hybrid.** ADR 0092 rejected a Claude Code-only
  skill, so if Claude Code qualifies alone, the adopting ADR names the cost
  of two Worker shapes in the skill, the pane and the domain language.

### Why root-session Workers at all

- **Lifetime.** A root-session Worker's life does not depend on its Lead's.
  A closed terminal, a `/exit` or an unloaded Codex daemon thread ends or
  strands a sub-agent Worker, and a root session survives all three. No
  small fix to sub-agent Workers reaches this, and prior art agrees the case
  rests on lifetime and observability, not on write safety, since vendors
  ship Sub-agents that write in their own Worktrees
  ([prior art](lead-worker-prior-art.md#summary)).
- **Observed state.** A root session is placed, bound and ended by machinery
  Dashpot already has: its hooks place it at its Worktree, its own Issue
  Binding attributes it, and its `waiting` is its own rather than read
  through its Lead's Sub-agent listing
  ([analysis](lead-worker-design-analysis.md#what-sub-agent-workers-cost)).
- **Cleanup, partly.** A root-session Worker blocks only its own Worktree,
  but each Worker's reviewer Sub-agent re-imposes the Repository-wide
  `sub-agent` blocker (ADR 0066) while it runs (measured on Claude Code and
  OpenCode, #479), and every Worker reviews. One local estimate puts the
  reviewer windows at 14–36 % of an Arc, about 22 % at the median, so the
  Repository-wide block would shrink by roughly two thirds to five sixths,
  not to zero (inference; [method](../reviews/lead-worker-design-review-2026-10-05.md#method)).
  [ADR 0112](../adr/0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)'s
  Sub-agent Override already lets a person remove a Worktree despite the
  `sub-agent` blockers its preview lists; no agent gives it, so a Lead's own
  close-out still waits. Narrowing the reviewer's blocker waits on observed
  placement, since a declaration cannot stand in for occupancy evidence
  (ADR 0112).
- **What it costs.** Lost completion notices, a hand-back transport,
  unattended asks, credentials, lifecycle hazards, teardown, and a Lead link
  ([analysis](lead-worker-design-analysis.md#what-root-session-workers-cost)).
  Reviewers stay Sub-agents in every variant, so root-session Workers add a
  second fix backlog rather than replacing the first.

## The Worker contract

A harness qualifies for root-session Workers when a Worker can do all of
these:

1. **Launch** in a named Worktree with its own Agent Session Identity. Its
   hooks place it there, and it is not a Sub-agent of the Lead.
2. **Bind** by running `work start` itself, so its run is observed at that
   Worktree.
3. **Link** to its Lead by the Lead's declaration, kept as provenance that
   outlives both Agent Runs ([the Lead link](#the-lead-link)).
4. **Report** a durable hand-back keyed on Worker, Issue, PR and head
   commit, and an observable end, its `work stop`
   ([communication](#communication)).
5. **Receive** a message from the Lead at its next turn boundary, or be
   resumed with one.
6. **Stop** with positive evidence of its end.
7. **Run under a declared permission posture** on launch and on every
   resume, or route its asks to a person:
   - Claude Code: `auto`, where a Worker parked on an ask counts as waiting
     on a person, or `dontAsk` with an allow-list, where a denied action is
     reported in the hand-back rather than waited on. The choice between them
     is a security decision for the maintainer, recorded in the adopting
     ADR; the pilot runs both and counts how often `auto` parks. The Lead
     and its Workers share one permission class, since a message across
     classes is held.
   - Codex: an escalated or full-access launch, and every resume restates
     `-s`, since a bare resume runs at the configured default.
   - OpenCode: never `always`, which saves a Project-wide rule that also
     answers the Lead's asks.
8. **Persist while idle** long enough, or come back to its Issue after an
   interruption. On Claude Code its Orphaned Agent Run continues when the
   session resumes
   ([ADR 0053](../adr/0053-continue-an-orphaned-agent-run-when-its-session-resumes.md),
   [ADR 0075](../adr/0075-end-an-orphaned-run-at-its-replacements-session-end.md)),
   except after a SIGTERM respawn, whose `SessionEnd` has already ended the
   run, so the Worker runs `work start` again (measured, #479), as it does on
   Codex after a resume and on OpenCode after a fresh prompt. A turn
   OpenCode's restarted service resumes by itself has its `work start`
   refused as stale until a fresh prompt arrives (measured, #479).
9. **Hold its credentials,** so it can push its Branch and open its PR. The
   skill checks `gh auth status` inside a new Worker before giving it work.
   On Claude Code the Lead passes what a Worker needs with `--settings`
   `env`, since a `--bg` Worker otherwise runs with the environment of
   whichever shell first started the supervisor.
10. **Be attachable:** a person can attach to it and answer or redirect it,
    by `claude attach` or agent view, `codex resume` on a daemon thread, or
    an OpenCode client on the service. A terminal multiplexer is one route,
    not a requirement: the pane's [attention count](#sessions-pane), not a
    window per Worker, tells a person a Worker needs them.

A harness that cannot meet 1, 2 or 6 by any route keeps sub-agent Workers.
Items 5, 7 to 10, and item 6 on OpenCode, are met by the skill's own routes,
at the costs the table below records. Items 3 and 4 depend on no harness
route, but today's code meets neither: item 3 needs the Lead link built, and
item 4's status file is deleted with the Worktree, so the Lead copies what
it needs first.

Waking the Lead is deliberately not a contract item. Completion is read from
durable evidence, so a wake-up only shortens the Lead's wait.

The contract keeps four states apart, since none implies another:

- **Execution state:** what Dashpot observes of the Worker's session:
  running, waiting, orphaned or ended. An
  [Orphaned Agent Run](../domain-language.md#observation) is unfinished work
  whose process is gone, not a completion.
- **Declared outcome:** what the Worker's hand-back says it achieved.
- **PR readiness:** an open PR with green CI and this Repository's review
  and validation evidence ([communication](#communication)).
- **Cleanup eligibility:** whether the Worktree's blockers let Cleanup
  remove it. A finished `--bg` Worker occupies its Worktree until it is
  stopped or evicted.

## Mechanism per harness

| | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Launch | The Lead's shell runs `(cd <worktree> && claude --bg --name issue-<n> "<brief>")` in a subshell: an un-subshelled `cd` in a Lead whose added directories hold the Worktree moves the Lead's own session there, and a `dontAsk` Lead needs `permissions.additionalDirectories` and allow rules to dispatch at all (measured, #479). `--bg` prints an 8-character short id and ignores `--session-id`; the full session id comes from `claude agents --json --cwd <worktree>` (measured, #479) | From a full-access or escalated shell only, a detached `codex exec -C <worktree> --json -o <file> "<brief>"`, whose first `--json` event, `thread.started`, gives the Worker's id; launched from a sandboxed shell, it dies with that command (measured, #479). For a person who wants to watch, a daemon-hosted TUI in a tmux window | `opencode api POST /api/session` with `location.directory` and the Lead in `metadata`, then `POST /api/session/<id>/prompt`; until prompted it reads waiting ([ADR 0106](../adr/0106-record-a-session-waiting-after-a-session-start-that-begins-no-turn.md)). The `dashpot-worker` agent is accepted on a root session (measured, #479) |
| Worker wakes the Lead | `SendMessage` to the Lead: an idle Lead gets a new turn, and a busy one receives it inside its running turn, after the current tool call, with no `Stop` between (measured, #479) | `codex queue --thread <lead>`, from an unsandboxed shell only; a sandboxed Worker falls back to a status file or the Lead's reading of `-o` and `--json` (measured, #479) | `POST /api/session/<lead>/synthetic`, which wakes an idle Lead and steers a busy one (measured, #479) |
| Lead reaches a Worker | `SendMessage`, which lands inside a busy Worker's running turn (measured, #479); `notify_when_idle` for a one-shot notice, which quotes the Worker's final text (measured, #479) | Mail queued to a running `exec` Worker is lost (measured, #479); once it has exited, `codex exec -C <worktree> <posture> resume <id> "<message>"`, restating the sandbox flags, which a bare resume drops | `POST /api/session/<worker>/prompt` |
| Unattended asks | A posture that does not prompt, with the Lead and Workers sharing one permission class: bypass, or prompting (manual, `dontAsk` and auto); across classes a message is held, and a `-p` receiver drops it after five minutes (measured, #479). Auto, the default permission mode since 2.1.283, and `dontAsk` work with `--bg`; only bypass needs one interactive acceptance first; auto falls back to prompting after 3 blocks in a row or 20 in total (documented). A Worker blocked on an ask lists in `claude agents --json` as `blocked`, waiting for a permission prompt, while Dashpot reads its run as `running` (measured, #479). The brief must allow commits, since a `--bg` session is instructed to ask before committing in a Worktree it did not enter itself; the instruction is in the system prompt, not a permission gate, and `--settings '{"worktree":{"bgIsolation":"none"}}'` removes it (measured, #479) | No one to ask: full access; `--approve-for-me`, which sets `auto_review`, `on-request` and the `workspace-write` sandbox, and so cannot queue; or `-c approvals_reviewer=auto_review`, which forces no sandbox. An `auto_review` approval is a model's, not a person's consent. Every resume restates the posture | Set when the session is made (unmeasured), or listed and answered by the Lead through the permission API (measured, #479): `reject` cancels every pending ask in the session and ends the turn unless it carries a `message`, and `always` saves a Project-wide rule that also answers the Lead's asks |
| Environment | The supervisor's whole environment, inherited from the shell that first started it, for every Worker of every Lead; a dispatch's own shell variables, credentials included, never reach its Worker. The Worker's identity variables are its own, so the Lead's identity does not reach it, and a `--settings` `env` reaches only its own Worker (measured, #479) | Inherited from the Lead's shell; Codex sets fresh ids for the Worker's own shells, so its `work start` makes a root claim, but its hooks see the Lead's (measured, #479) | The service's, not the Lead's: `GH_TOKEN` exported in the Lead's shell was absent (measured, #479); replaced wholesale with `PUT /api/session/<id>/environment`, and lost when the service restarts |
| Stop | `claude stop <id>`, which publishes `SessionEnd` and frees the Worktree (measured, #479). After SIGTERM the supervisor resumes the same session in a new process about 10.5 seconds later, but the killed process's `SessionEnd` has ended its run, so the Worker must `work start` again (measured, #479) | Exit at the end of its turn, or SIGINT, which publishes `Interrupt` and `SessionEnd`; SIGTERM and SIGKILL publish nothing and orphan the run (measured, #479) | `work stop`, then a move back to the main Worktree, or deletion; the `dashpot-worker` agent's move denial holds on a root session (measured, #479), so a Worker on it would be deleted, which [open decision 6](#for-the-adopting-adr) weighs |
| Contract items met at a cost | 7: an ask waits for a person to attach (several clients attached to one `--bg` session are unmeasured, [#370](https://github.com/ned2/dashpot/issues/370)), and Dashpot reads the asking Worker as `running` (measured, #479). 8: an idle Worker is retired after about 61 minutes with no hook, and its run continues when someone attaches; a SIGTERM respawn needs a new `work start` (measured, #479). 9: `--settings` `env` per Worker | 5 and 8: each follow-up is an `exec resume` with its posture restated, which binds a new run; mail to a running Worker is lost. 7: no one to ask, so the posture decides | 6: a finished Worker stays live until its finish step or deletion. 8: a service stop orphans every Worker's run; the restarted service resumes cut-off turns unseen by Dashpot, and a Worker binds a new run only after a fresh prompt. Pending asks are lost at a stop. 9: the session's environment, lost at a restart |

How well each cell is evidenced is in the
[analysis](lead-worker-design-analysis.md#the-harnesses-compared), with the
comparison of both mechanisms on each harness
[against #479's criteria](lead-worker-design-analysis.md#against-479s-criteria).
Claude Code works in the live run at 2.1.287 and 2.1.289
([experiment](../spikes/root-session-workers-spike.md#claude-code-21289)),
so it is the pilot. Its two hazards are met by dispatching in a subshell
with `--settings`, whose `env` carries the Worker's credentials and the
optional `DASHPOT_LEAD` stamp and whose `worktree` sets `bgIsolation`, and
by binding again after a SIGTERM respawn. Codex is a constrained batch mode
whose running `exec` Worker cannot be redirected, and OpenCode's restart
recovery is broken for Workers, so both wait for their triggers.

## The Lead link

No harness links a root session to the session that launched it in a record
Dashpot reads, and identity is never inferred
([ADR 0038](../adr/0038-isolate-native-agent-session-identities.md)), so the
link is a declaration. ADR 0124 sets its direction for the adopting ADR:

- **The Lead declares it,** with `work assign` generalised to accept a root
  session's identity beside a Sub-agent's. Dashpot validates the named
  Worker against the Worker's own placed hook record, rather than the
  Lead's, which lists only Sub-agents. Authority stays where ADR 0096 put
  it.
- **The live assignment** is held on the Lead's Agent Run, as Worker
  Assignments are, and ends with it. That end is the Lead-ended signal
  [decision 19](#for-the-adopting-adr) needs.
- **A provenance record** of the declaration outlives both Agent Runs, for
  example an Event Log record
  ([ADR 0059](../adr/0059-keep-an-append-only-event-log-in-each-checkout.md)),
  so a Worker's completion and a Cleanup explanation can still name its Lead
  after either run has ended.
- **A Worker-side `DASHPOT_LEAD` stamp** is optional corroboration. On
  Claude Code it is carried by `--settings` `env`, which reaches only its own
  Worker's shells and hooks and survives a respawn, while a stamp in the
  launch shell's environment reaches every Worker of the supervisor but its
  own (measured, #479). On Codex a stamp on the launch command reaches the
  Worker's shells and hooks (measured, #479).

The link only groups and explains rows: it carries no activity and no
occupancy. Claude Code's hidden `--parent-session-id` reaches no known hook,
Warp's `parent_run_id` is outside the harnesses Dashpot supports
([prior art](lead-worker-prior-art.md#the-link-between-a-lead-and-its-workers)),
and OpenCode's session `metadata`, which Dashpot does not read, any client
can change and a Worker's Sub-agents and forks inherit (measured, #479).

What today's code does, which ruled out the Worker-side link an earlier
revision leaned to and which the Lead-side link has to handle:

- **A Worker-side link ends with the Worker's run.** `work stop` and a
  `SessionEnd` delete the Worker's Work Store record
  ([`work_store.py`](../../src/dashpot/sessions/work_store.py),
  `stop_current` and `end_session_runs`), so a link stored on that run
  vanishes at the completion it is meant to explain.
- **A `work start` without `--lead` would drop it.** Every `work start`
  writes a fresh record, so a Codex resume follow-up or an OpenCode recovery
  that binds again without the option would lose the link.
- **The Lead's identity has no check to reuse.** `validate_session_claim`
  refuses an OpenCode claim without the plugin's pid
  ([`hook_claims.py`](../../src/dashpot/sessions/hook_claims.py)), so an
  OpenCode Lead named by a Worker would be refused, and requiring a Lead that
  holds a run refuses linking after a Codex Lead unloads.
- **A Conversation Switch changes the Lead's session id**
  ([ADR 0101](../adr/0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)),
  so a link recorded as `<harness>:<session-id>` then names a session that no
  longer runs. The provenance record keeps the identity the Lead had when it
  declared, as history rather than a live Lead.
- **`work assign` validates a Sub-agent.** It accepts a Worker only when the
  Lead's own hook record lists it, so the generalised assignment needs the
  second validation path above. Unlike a Worker-side link, an assignment
  survives the Worker's own `work stop`; it ends with the Lead's run,
  including on any `work start` or a Codex unload
  ([#492](https://github.com/ned2/dashpot/issues/492)), which is why the
  provenance record is kept apart.

## Communication

Durable state is the truth, and each harness's own channel only wakes the
other party sooner
([options compared](lead-worker-design-analysis.md#how-a-lead-and-its-workers-communicate)).
Prior art agrees.

- **Liveness and completion come from observation.** A Worker's `work stop`
  or its session ending is the end of its Issue work. Its run becoming
  orphaned is not: the Lead treats an Orphaned Agent Run as needing
  attention, which a resume or a new `work start` continues. Neither end
  says whether the work succeeded. A pilot Lead reads a Worker's run with
  `work show` in the Worker's Worktree, which lists every run there, beside
  `claude agents --json`.
- **The hand-back travels in a status file** in the Worktree's git
  directory, keyed on Worker, Issue, PR and head commit
  ([decision 17](#decided)), so a lost or repeated doorbell is harmless.
  The skill's `execute-issues-status` file already serves Codex v1 Workers
  and OpenCode's fallback. It is removed with the Worktree, so the Lead
  copies what it needs before Cleanup. A root-session Worker's final
  message no longer reaches its Lead.
- **The Lead reads the Worker's own final output** beside the status file:
  `claude logs`, Codex's `-o` file, or the OpenCode session's outcome and
  messages. Dashpot records none of it: keeping a `Stop` payload's
  `last_assistant_message`, for example, would break ADR 0059's rule against
  recording prompts and raw payloads.
- **A green PR alone is not "ready".** PR readiness is an open PR with green
  checks and this Repository's review and validation evidence recorded
  ([independent review](../../AGENTS.md#independent-review-before-integration)),
  which is where an agent's work ends
  ([ADR 0089](../adr/0089-leave-the-pr-merge-to-the-operator.md)).
- **Harness channels are only doorbells:** `SendMessage`, `codex queue`, or
  OpenCode's synthetic message. A lost doorbell only delays the Lead. No
  doorbell measured interrupts a tool call in flight, though not every one
  waits for the end of a turn
  ([prior art](lead-worker-prior-art.md#coordination-polling-doorbells-and-the-hand-back)
  suggests it should). Measured so far (#479): OpenCode's `steer` arrives at
  a busy Lead's next step and `queue` after its last planned step, and
  `codex queue` starts a turn on an idle Lead and waits out a busy one.
  Claude Code's `SendMessage` starts a turn on an idle Lead, but reaches a
  busy one inside its running turn, after the current tool call, with no
  `Stop` between.

A future `work wait` would meet Leads that wait differently: a `-p` or
Agent SDK Lead's background command is cut at 30 minutes by default and 2
hours at most (documented), a Codex Lead blocks inside its turn, and an
OpenCode Lead's waiting shell may be ended by idle eviction (unmeasured,
[#467](https://github.com/ned2/dashpot/issues/467)).

Dashpot keeps no mailbox (decision 4). The Lead's shell launches every
Worker, so Dashpot stays a passive observer
([ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)).
A Dashpot helper that dispatches or drives Workers would be a controller,
needing its own ADR and the consent
[#148](https://github.com/ned2/dashpot/issues/148) has not given.

## What Dashpot would build

A Claude Code root-session Worker needs at most two things from Dashpot:
the Lead-side link with its provenance record, as [above](#the-lead-link),
and a Cleanup explanation that names "Worker of <Lead> on #N", with the
occupancy rules unchanged. ADR 0124 keeps `work assign`'s Sub-agent meaning
and leaves the link to the adopting ADR, so both are built for adoption; a
pilot that needs them sooner says so in its own Issue.

`work workers` and `work wait` are deferred until a pilot shows the need and
their semantics are specified: the baseline a wait compares against, its
timeout, what a vanished Worker reports, and what unreadable state reports.
`work workers` would also need explicit session identities, which the
published `AgentRun` excludes today. The pane's presentation is #444's
([below](#sessions-pane)).

**The skill.** The pilot changes only the skill's Claude Code route: launch
in a subshell with `--settings`, the posture, the `gh auth status` check, a
brief that runs `work start` and `work stop` and binds again after a
respawn, the keyed status-file hand-back, and `claude stop` for a Worker its
Lead launched. Wave sizing, which today a harness's Sub-agent cap bounds,
also follows the per-person ceiling ([U5](#decided)). The
Codex and OpenCode routes are unchanged until their triggers. The analysis
[nets](lead-worker-design-analysis.md#against-479s-criteria) what a move
removes against what it adds for each harness, which for Codex and OpenCode
is a larger skill than today's.

## Sessions pane

[#444](https://github.com/ned2/dashpot/issues/444) owns the Sessions pane's
presentation of Workers and goes ahead under sub-agent Workers. ADR 0124
gives it these requirements, which hold under either mechanism:

- a count of Workers waiting on a person, which never folds away;
- "unknown" wherever a harness cannot report an ask;
- the Issue and PR leading each Worker's row;
- the Lead shown as provenance.

The model has no "needs input" state, and an asking Worker reads `running`
on Claude Code and OpenCode today. On Claude Code its `Notification` hook
fires and `claude agents` reports `waitingFor` `permission prompt`; on
OpenCode no observer publishes a pending ask. A truthful
count needs that evidence published. A Worker its harness's permission
system has stopped, such as Claude Code's auto mode or Codex's auto-review
after repeated denials, is waiting on a person too
([prior art](lead-worker-prior-art.md#state-vocabulary-and-attention)).

The analysis gives [each mechanism's pane story](lead-worker-design-analysis.md#which-mechanism-gives-the-more-truthful-pane)
and [layouts](lead-worker-design-analysis.md#how-workers-could-appear-in-the-sessions-pane)
for #444 that work with either.

## Contracts an adopting ADR would change

On a pass, the ADR adopting root-session Workers on a harness would change:

- **ADR 0092**, which says a Worker runs no `work` command, and its rules
  that the Lead stays where it bound while any Worker runs and removes
  Worktrees only once no Worker is live.
- **ADR 0096**'s Worker Assignment, generalised to root sessions as
  [above](#the-lead-link), with its provenance record.
- **[ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md)**:
  a Lead whose root-session Workers work, none of them its Sub-agents, would
  read `waiting`, as would its Arc's Issue, unless something else holds it.
- **The domain language:** Worker, Lead and Worker Assignment
  ([decision 7](#for-the-adopting-adr)).
- **AGENTS.md and the Issue work skill,** which forbid a Sub-agent's
  `work start` and `work stop`. A root-session Worker would run both, while
  a sub-agent Worker still must not.
- **[#215](https://github.com/ned2/dashpot/issues/215)'s scenario 2**, one
  session leading several Issues, which ADR 0096 decided.
- **OpenCode only, when it re-opens:**
  [ADR 0093](../adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)'s
  `dashpot-worker` agent, whose move denial holds on a root session
  (measured, #479), so either the finish step or the agent would change, and
  with it [#437](https://github.com/ned2/dashpot/issues/437); and
  [ADR 0108](../adr/0108-keep-opencode-self-move-and-leading-workers-on-the-shared-service.md),
  under which a standalone OpenCode Lead leads no Workers.

Unaffected: [ADR 0009](../adr/0009-hold-one-agent-run-per-session-across-worktrees.md),
ADR 0066, which still covers reviewers,
[ADR 0104](../adr/0104-block-worktree-removal-while-a-process-runs-inside-it.md)'s
`process` blocker, ADR 0112's Sub-agent Override and ADR 0008.

## Experiments

The pinned experiment for each harness has run: the
[root-session Workers experiment](../spikes/root-session-workers-spike.md)
reports them, and the revised
[Claude Code](lead-worker-claude-code-evidence.md#the-479-experiment),
[Codex](lead-worker-codex-evidence.md#the-479-experiment) and
[OpenCode](lead-worker-opencode-evidence.md#the-479-experiment) notes carry
their answers. What comes next, as ADR 0124 records it:

- **N1, a `--bg` Lead with sub-agent Workers** on Claude Code, is tried
  alongside the pilot. It may give Lead-independent lifetime with no Dashpot
  change, keeping asks, notices and the environment in one session. Unknown:
  whether a backgrounded Lead whose turn has ended is evicted while its
  Sub-agents run.
- **N2, reviewers as placed, read-only root sessions** in the Worker's
  Worktree, is deferred until after a pilot. It would remove the last
  Repository-wide blocker under root-session Workers, and depends on
  [#518](https://github.com/ned2/dashpot/issues/518), since a `claude -p`
  exit publishes no `SessionEnd`.
- **N3, Sub-agent placement through #474,** is pursued as an input to
  re-opening: `isolation: "worktree"` places hooks under
  `.claude/worktrees/`, and the undocumented plugin `agent.spawn` hook can
  set `cwd`.

The review's remaining unknowns, with their cheapest tests:

| Unknown | Cheapest test |
| --- | --- |
| When a supervisor takes a new environment, and so which credentials a Worker started from the user's real configuration holds. | Read the user's supervisor's `/proc/<pid>/environ` names only, and restart it from a known shell in a disposable configuration. |
| Whether a real model in a `--bg` Worker follows the injected "use `EnterWorktree`" and "ask before committing" instructions, with and without `bgIsolation: "none"` and a brief that authorises commits. A fixture model cannot show this. | One real-model `--bg` Worker on a throwaway Issue in a disposable repository. |
| How often `auto` parks during a normal Issue. | The same run, counting `waitingFor: permission prompt`, then repeated under `dontAsk`. |
| SIGKILL and a crash of a `--bg` Worker, as opposed to the SIGTERM measured. | A rerun of the respawn scenario with SIGKILL. |
| Idle eviction of a Worker waiting on CI, and of a `--bg` Lead whose Sub-agents still run (N1). | A `--bg` session holding a background `sleep`, observed past an hour, with a variant running a background Sub-agent. |
| The reviewer-window estimate. | Recompute it from Dashpot's own `SubagentStart` and `SubagentStop` records for one recorded Arc. |

The review's Codex and OpenCode unknowns wait until those harnesses re-open.

## Sequence

1. **Decide.** Done: ADR 0124 keeps sub-agent Workers and qualifies
   root-session Workers per harness.
2. **[#444](https://github.com/ned2/dashpot/issues/444),
   [#477](https://github.com/ned2/dashpot/issues/477),
   [#478](https://github.com/ned2/dashpot/issues/478) and
   [#517](https://github.com/ned2/dashpot/issues/517) proceed under
   sub-agent Workers,** as arc
   [#498](https://github.com/ned2/dashpot/issues/498) waited for. #444 takes
   the [Sessions pane requirements](#sessions-pane). #517's display of a
   Claude Code session waiting on a Background Command ships, and so do the
   fixes [still needed](#effect-on-open-issues) below.
3. **Run the Claude Code pilot** against criteria (a)–(f), under `auto` and
   under `dontAsk` with an allow-list, with N1 alongside it.
4. **Write an adopting ADR only on a pass.** It makes root-session Workers an
   opt-in mode on Claude Code, amends ADR 0092 and ADR 0096, and updates the
   domain language. Codex and OpenCode follow only when their triggers fire.

Until a pass, the rest of this design is the shape a harness would take,
not planned work.

## Effect on open Issues

The Issues and ADRs that landed while #479 was open are listed in the
[review](../reviews/lead-worker-design-review-2026-10-05.md#applied-in-this-revision).

- **Proceed now under sub-agent Workers:** #444, #477 (blocked by #474),
  #478 and #517, as the [sequence](#sequence) says.
- **Needed under either mechanism,** because reviewers remain Sub-agents:
  [#519](https://github.com/ned2/dashpot/issues/519), a Claude Code session
  that enters another Worktree leaving a running record in the first;
  [#520](https://github.com/ned2/dashpot/issues/520), ADR 0107's tags in
  OpenCode recovery; #518, a `claude -p` exit that publishes no
  `SessionEnd`, which bears on any `-p` route and on N2;
  [#472](https://github.com/ned2/dashpot/issues/472), a Claude Code
  Sub-agent's interim stop while its own background work runs; and
  [#475](https://github.com/ned2/dashpot/issues/475).
- **An input to re-opening:** #474, which re-measures whether a Claude Code
  Sub-agent can be placed: the Agent tool's `cwd`, which the binary omits
  from the model's schema at 2.1.287 and 2.1.289, and `meta.json` parentage
  (N3).
- **Changed only if a harness adopts root-session Workers:**
  - #444 would group by the link; as written it excludes Workers with their
    own Agent Runs, so it would need rescoping.
  - #475, #477 and #478 would matter only for reviewers and for harnesses
    that keep sub-agent Workers.
  - #492, an unloaded Codex Lead ending its Workers' assignments, would no
    longer end a root-session Worker's Issue work, which its own run holds
    (inference).
  - [#473](https://github.com/ned2/dashpot/issues/473)'s presence filter
    grows, since live OpenCode Workers that have finished add rows, and its
    boundary that no Worker gains an Agent Run would need editing.
  - #148's premise that Workers remain Sub-agents would need editing; one
    session stopping another is its authority question.
  - [#481](https://github.com/ned2/dashpot/issues/481): every hook runs the
    main checkout's publisher, while a root-session Worker's
    `uv run dashpot work start` runs its own Worktree's Dashpot, so the two
    can differ in version.

## Open decisions

The numbers are those of earlier revisions and the review; decision 13 was
merged into 7, and 16 into 2.

### Decided

- **1. Adopt, and where.** ADR 0124: sub-agent Workers stay on every
  harness, and root-session Workers are qualified per harness, Claude Code
  first through its pilot, each harness re-opening on its
  [trigger](#the-decision-and-the-pilot).
- **2 and 16. Who declares the link.** The Lead, by `work assign`
  generalised to root sessions and validated against the Worker's own placed
  hook record, with a provenance record that outlives both Agent Runs; a
  Worker-side `DASHPOT_LEAD` stamp is optional corroboration
  ([the Lead link](#the-lead-link)).
- **4. No mailbox.** Confirmed by ADR 0008.
- **9.** Answered by ADR 0096: an assignment holds until `work unassign` or
  the Lead's run ends. Whether the pane keeps a row for a `not listed`
  sub-agent Worker is #444's.
- **11.** Answered by #473, which keeps bound, orphaned, running and
  uncertain observations conspicuous.
- **12.** Moot: the Issues pane's activity column has no "delegated"
  distinction today.
- **17. The hand-back keyed on Worker, Issue, PR and head commit.**
  Adopted at skill level, under either mechanism, in the bundled skill by
  #534: the [brief template](../../src/dashpot/skills/dashpot-execute-issues/references/brief-template.md) has each
  Worker open its hand-back, and every report before it, with that key, and
  the Lead [reads each hand-back against it](../../src/dashpot/skills/dashpot-execute-issues/SKILL.md#4-handle-each-hand-back).
  The pilot's hand-back uses it ([communication](#communication)).
- **U5. An accountable person per Arc,** a direction for the skill under
  either mechanism, adopted in the bundled skill by #534: the skill's Arc
  record (the record Issue's [arc map](../../src/dashpot/skills/dashpot-execute-issues/references/run-records.md#the-arc-map))
  names the person accountable for the Arc, and
  [wave sizing](../../src/dashpot/skills/dashpot-execute-issues/SKILL.md#2-set-up) counts the three-to-five Worker
  ceiling ([prior art](lead-worker-prior-art.md#suggestions-for-the-design))
  per person across all of their Arcs, with five as the default ceiling the
  user's explicit direction can change. Dashpot needs no person field for
  this.

### For the adopting ADR

The pilot answers credentials and permission posture provisionally, through
contract items 7 and 9 and the skill's launch route, since no pilot runs
without them; the adopting ADR records the answers.

- **Credentials.** How each Worker gets what it needs to push and open its
  PR ([contract item 9](#the-worker-contract)).
- **5. Permission posture.** `auto` or `dontAsk` with an allow-list on
  Claude Code, a security decision the pilot's counts inform
  ([contract item 7](#the-worker-contract)).
- **19. The Lead-ended policy.** The direction is fixed: Workers continue,
  accountability is explicit, and Dashpot never cancels them silently. The
  live assignment's end is the signal. Warp likewise leaves children running, where Temporal and Claude
  Projects stop them. A Worker whose Lead has ended is not an Orphaned Agent
  Run, whose session's Host Process is gone.
- **6. Teardown authority,** scoped to a Worker its Lead launched. A
  finished `--bg` Worker occupies its Worktree until it is stopped or
  evicted, so the question is whether its Lead may `claude stop` it. A
  Codex `exec` Worker needs no teardown, since its exit frees its Worktree
  (measured, #479); OpenCode's, where a root session may move only itself
  ([ADR 0094](../adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md))
  and deletion loses history, waits for OpenCode to re-open.
- **7 and 13. The vocabulary:** what Worker means once it can be a root
  session, how it is kept apart from Claude Code's supervised worker
  process, and what the pane's frozen role column says, given that the
  domain language avoids "agent" for a harness.

### Deferred

To [#444](https://github.com/ned2/dashpot/issues/444) or later work:

- **3.** Whether Dashpot ships `work workers` and `work wait`, until a pilot
  shows the need and their semantics are specified
  ([what Dashpot would build](#what-dashpot-would-build)).
- **8.** Whether Lead groups are expanded by default or collapsible, and on
  which key; `Enter` has no Sessions-pane action today.
- **10.** Whether a sub-agent Worker's declared Worktree appears in the pane
  at all, or only in the Cleanup explanation (#478).
- **14.** How a Worker waiting on a person stays visible however the pane is
  grouped, now a requirement of #444 ([Sessions pane](#sessions-pane)).
- **15.** Whether the pane shows each Lead's number of active Workers
  against the three to five per person prior art reports.
- **18.** Whether Dashpot flags a lost completion by inconsistency (a PR
  open while the status says working, a session ended with no status, done
  with no PR), and shows "quiet for N minutes" rather than calling a Worker
  stalled.
- **20.** Whether cancelled, rejected (the Issue is not actionable) and
  failed are distinct Worker outcomes.
