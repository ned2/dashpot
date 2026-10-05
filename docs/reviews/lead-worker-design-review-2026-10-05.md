---
status: research
date: 2026-10-05
---

# Lead and Worker design review (2026-10-05)

A point-in-time review of the [Lead and Worker design](../proposals/lead-worker-design.md)
for [Issue #479](https://github.com/ned2/dashpot/issues/479), its
[analysis](../proposals/lead-worker-design-analysis.md), and the research
notes behind them, at `c8069ac` (`origin/main` was `4110b53`). The proposal
asks whether a Lead's Workers should stay its Sub-agents or become root
Agent Sessions of their harness, linked to the Lead by a declaration.

The review checked every harness claim the design rests on, ran the
experiments the design had left as future work, brought the documents up to
date with the Issues and ADRs that landed since they were written, and then
reviewed the design critically. The factual fixes are already applied to
the documents. The changes that would alter the design are listed under
[candidate uplifts](#candidate-uplifts) for the maintainer to decide.

## Verdict

**Rework.** The direction holds for one reason that sub-agent Workers
cannot reach by small fixes: a root-session Worker's life does not depend on
its Lead's. A closed terminal, a `/exit` or an unloaded Codex daemon thread
ends or strands today's Workers, and a root session survives all three. The
rest of the case is weaker than the design states:

- **Cleanup.** [ADR 0112](../adr/0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)
  already gives a person an override for the Repository-wide `sub-agent`
  blocker, and under root Workers each Worker's reviewer Sub-agent brings
  that blocker back while it runs (measured on OpenCode). One local
  estimate puts the reviewer windows at 14–36 % of an Arc, about 22 % at the
  median, so root Workers cut the Repository-wide block by roughly two
  thirds to five sixths, not to zero (inference from transcript timestamps;
  see [method](#method)).
- **Per harness, the costs differ by an order of magnitude.** Codex root
  Workers work only under four measured constraints, and OpenCode's restart
  recovery is broken for them today. Claude Code is the one harness where
  the mechanism works cleanly in the live run, with two hazards the design
  had not seen: every `--bg` Worker inherits the environment, credentials
  included, of whichever shell first started the supervisor, and a Worker
  the supervisor respawns after a SIGTERM has lost its Issue Binding.
- **The Lead link the design leans to does not survive.** A Worker-side link
  is stored on the Worker's Agent Run, which its own `work stop` deletes.

Both independent critical reviews reached the same shape: keep sub-agent
Workers as the shipped mechanism for now, qualify root-session Workers per
harness, starting with Claude Code, and decide only what that requires.
They differ on whether the result is a gated pilot with sub-agents as the
default, or an opt-in mode that ships once a harness qualifies. The
[minimum viable decision](#minimum-viable-decision) below covers both.

## Method

- **Desk checks.** Three agents checked every harness claim in the design,
  the analysis, the three evidence notes and the prior-art note against
  vendor documentation, the binaries' strings (Claude Code 2.1.287 and
  2.1.289), source at the pinned tags (Codex `rust-v0.160.0`, OpenCode
  2.0.22) and the repository's own traces.
- **Code and record checks.** One agent read the code paths the design
  touches (the Work Store, claim validation, Cleanup blockers, the skill).
  Another audited every Issue and ADR the design names or should name.
- **Research checks.** One agent re-verified and extended the prior art.
  Another surveyed the human-factors and multi-agent design literature.
- **Live probes.** Pinned runs of each harness in disposable fixtures, as
  the [agent guidance](../../AGENTS.md#leading-parallel-issue-work)
  requires, recorded in the
  [root-session Workers experiment](../spikes/root-session-workers-spike.md).
- **Critical review.** A fresh adversarial reviewer, and an independent
  second opinion from Codex (another model family), each gave the design's
  parts keep, rework or reject verdicts. Their material claims about the
  repository were checked against the code before being used here.
- **The reviewer-window estimate** reads only `spawnDepth`, `parentAgentId`
  and first and last timestamps from the local Claude Code Sub-agent
  metadata of the five largest Lead sessions, taking depth-2 agents as
  reviewers. Depth 2 includes other helpers, and a transcript's span only
  approximates liveness.

## Claim validation

About 185 claims were graded. Most were confirmed; the ones that were wrong
mattered.

| Harness | Graded | Wrong or misgraded that changed the design |
| --- | --- | --- |
| Claude Code | about 67, plus the live run | `--bg` prints only an 8-character id; the full id comes from `claude agents --json --cwd`. A bound `--bg` Worker's exact occupancy was graded _measured_ (#162) but was never measured: #162 ran no `worktree check` on one. `auto` (the default since 2.1.283) and `dontAsk` work with `--bg`; only bypass needs a person's acceptance, so the experiment's all-bypass premise was unnecessary. `auto` falls back to prompting after 3 blocks in a row or 20 in total. A `-p` or SDK Lead's background command is limited to 30 minutes by default, 2 hours at most, so `work wait` in a background shell is conditionally refuted for it. `claude -p` publishes no `SessionEnd` at 2.1.289 (#518). The live run refuted two more: a `--bg` Worker does not receive "only the forwarded variables" but the whole environment of the shell that started the supervisor, and ADR 0053 does not carry a Worker's run across a supervisor respawn after a SIGTERM. |
| Codex | about 50, plus the live run | `auto_review` does not force `workspace-write`; only `--approve-for-me` does. A sandboxed shell cannot reach the daemon (its directory is masked and seccomp refuses every Unix-socket connect), which the notes had left open. N6 was wrong for `codex exec`, which is its own Host Process. The live run refuted "a Lead can follow up an idle Worker" (mail queued to a running `exec` Worker is lost) and "a root ends with `Interrupt` and `SessionEnd`" (only SIGINT does). |
| OpenCode | about 68, plus the live run | "A service restart orphans every Worker's run and nothing resumes them" is wrong: the restarted service resumes the turns it cut off, unseen by Dashpot's plugin. "Whether a plugin may create or prompt sessions is unverified" is wrong: `ctx.session` exposes both. A pending ask is cancelled by a service stop, not preserved. |
| Prior art | re-read in full | Two unconfirmed details were dropped. Claude Projects, Warp's multi-agent runs, workmux's coordinator, Agent Orchestrator, CAID and MCP's Tasks extension were added. Claude Projects is the closest precedent: separate sessions per thread, each with its own branch and PR, asks kept in the thread, auto mode, and an overview grouped by state. |

The [Claude Code](../proposals/lead-worker-claude-code-evidence.md),
[Codex](../proposals/lead-worker-codex-evidence.md),
[OpenCode](../proposals/lead-worker-opencode-evidence.md) and
[prior-art](../proposals/lead-worker-prior-art.md) notes now carry the
corrections, each graded by its source.

## What the probes found

The [experiment](../spikes/root-session-workers-spike.md) has the receipts.

- **Codex 0.160.0: works under four constraints.**
  - The Lead launches from a full-access or escalated shell. A launch from a
    `workspace-write` shell dies with the sandboxed command.
  - `codex queue` carries messages Worker to Lead only, and only from an
    unsandboxed shell.
  - The Lead reaches a Worker by `codex exec -C <worktree> resume`,
    restating the sandbox flags. A bare resume runs at the configured
    default, which silently escalates a sandboxed Worker.
  - Workers are stopped with SIGINT. SIGTERM and SIGKILL publish nothing
    and leave an Orphaned Agent Run blocking the Worktree.

  Each Worker binds as a root and occupies only its own Worktree.
- **OpenCode 2.0.22: works, except after a restart.**
  - Root Workers bind as ordinary roots.
  - The `/synthetic` doorbell wakes or steers the Lead.
  - The `dashpot-worker` agent is accepted on a root session.
  - A restarted service resumes cut-off turns that Dashpot's plugin never
    sees start, so their runs stay orphaned and `work start` is refused as
    stale until a fresh prompt. Pending asks are cancelled.
  - `always` saves a Project-wide rule that also answers the Lead's asks.
  - Forks copy the Lead link.
  - A Worker's environment is the service's, so `GH_TOKEN` exported in the
    Lead's shell is absent.
- **Claude Code 2.1.289 (and 2.1.287): works, with two hazards.**
  - Each `--bg` Worker binds as a root and blocks only its own Worktree; a
    reviewer Sub-agent brings back the Repository-wide blocker while it
    runs. `claude stop` ends a Worker cleanly.
  - `SendMessage` reaches an idle session as a new turn and a busy one
    inside its running turn. `notify_when_idle` wakes the Lead with the
    Worker's final reply. Messages pass only between sessions of one
    permission class (bypass, or the prompting modes); across classes they
    are held, and a `-p` Lead drops a held message after 300 s.
  - **Environment.** Every Worker gets the environment of the shell that
    first started the configuration directory's supervisor, from any Lead.
    A per-dispatch stamp never reaches its own Worker and leaks into the
    others; an `env` given with `--settings` reaches only its Worker.
    Which credentials a Worker holds therefore depends on which shell, in
    which checkout, started the supervisor (inference for the user's real
    supervisor).
  - **Respawn.** After a SIGTERM the supervisor resumes the same session in
    a new process about 10 s later, but the killed process's `SessionEnd`
    has already ended the Agent Run, so the Worker must bind again.
  - A Worker waiting on a permission prompt reads `running` in Dashpot,
    while `claude agents` lists it `blocked`.
  - The ask-before-committing line is a model instruction that
    `worktree.bgIsolation: "none"` removes; a `dontAsk` Lead's
    `cd <worktree> && claude --bg` moves the Lead itself unless run in a
    subshell.

## Applied in this revision

These fix facts or add no-regrets material and change no lean,
recommendation, contract item or phasing.

- **Staleness.** Landed work moved out of "still needed": #427, #458, #460
  (ADR 0107), #459, #476 (ADRs 0104 and 0112), #454 (ADR 0108), #466
  (ADR 0113, display in #517) and #243.
  - The Issues the design omitted were added: #498, #517, #518, #519, #520,
    #492, #481, #472, #437 and #370.
  - The ADRs it omitted were added: 0016, 0075, 0089, 0093, 0094, 0104, 0106
    and 0112.
  - #148 moved to "Constrains". #474 became an input to decision 1.
  - The sequence no longer builds #444 meanwhile, which #498 defers.
- **Mechanism.** Every Codex and OpenCode row now follows the measured
  behaviour. N6 was corrected for `codex exec`, and N3 for `claude -p`
  (#518). Claude Code rows follow the live run: the environment, the
  respawn, the subshell dispatch, mid-turn delivery and the stamp.
- **Code facts.** The design now states what today's code does to a Lead
  link, under [the Lead link](../proposals/lead-worker-design.md#the-lead-link):
  - `work stop` and `SessionEnd` delete the Worker's record;
  - a `work start` without `--lead` drops the link;
  - `validate_session_claim` refuses a pid-less OpenCode claim;
  - a Conversation Switch changes the Lead's session id.
- **Inconsistencies.**
  - Contract items 3 and 4 are now stated as unmet by today's code.
  - Duplicate decisions 13 and 16 are merged into 7 and 2.
  - Decisions 6, 9, 11 and 12 record what the evidence has already answered.
  - An Orphaned Agent Run is no longer counted as a Worker's completion; by
    the [domain language](../domain-language.md#observation) it is unfinished
    work whose process is gone.
- **Additions.**
  - [If sub-agent Workers stay](../proposals/lead-worker-design.md#if-sub-agent-workers-stay),
    a non-adoption branch.
  - The doorbell-at-a-turn-boundary rule.
  - A harness permission-system stop counted as waiting on a person.
  - Warp and Claude Projects cited for the Lead-ended policy.
  - "Lifetime and observability, not write safety" as what prior art says.
  - The claim "no harness links a child to its parent" qualified.

## Critical review

Verdicts from the two critical reviews, reconciled. Where they differ, the
difference is stated.

| Part | Verdict | Reason |
| --- | --- | --- |
| Leading candidate | Rework | Uniform adoption on three harnesses is not supported. Qualify per harness; Claude Code first. |
| The Why | Rework | Lead with lifetime and observed state (`waiting`, placement). State the Cleanup gain as a partial, measured reduction, since ADR 0112 and the reviewer's blocker both stand. |
| Worker contract | Keep as a per-harness gate; rework items | Add credentials (the Worker can push and open its PR), the permission posture on launch and on resume, how a person attaches and redirects, and what a parked or denied Worker reads as. Separate execution state, declared outcome, PR readiness and Cleanup eligibility. |
| Mechanism per harness | Keep as evidence | Claude Code: works; dispatch with `--settings` for the stamp, the environment and `bgIsolation`, in a subshell. Codex: a constrained batch mode at best; it cannot be redirected while it runs. OpenCode: defer until restart rebinding is fixed. Claude Code: pending the live run. |
| The Lead link | Rework | Neither candidate survives as written. The reviews differ on the fix: a Lead-side `work assign` generalised to root sessions, or a provenance record kept apart from both Agent Runs. [U1](#candidate-uplifts) combines them. |
| Communication | Keep the principle | Durable state is the truth and harness channels are doorbells; prior art agrees. Key the hand-back to Worker, Issue, PR and head commit. A status file in the Worktree is deleted at Cleanup, so the Lead copies what it needs first. A green PR is not this Repository's "ready": review and validation evidence are part of it. |
| What Dashpot would build | Shrink | A pilot needs at most the link and the Cleanup explanation naming the Lead. Defer `work wait` until its semantics are specified (baseline, timeout, a vanished Worker, unreadable state) and a pilot shows the need. |
| Sessions pane | Hand to #444 | #479 needs only each mechanism's pane story. The attention requirements stand under either mechanism. The model has no "needs input" state, and an OpenCode pending ask reads `running`, so a truthful count needs evidence the observers do not yet publish. |
| Sequence | Rework | Decide first, pilot second, write the adopting ADR only on a pass. |
| Open decisions | Re-rank | See [below](#open-decisions-re-ranked). |

Points the two reviews raised that neither the design nor this review's
earlier candidates had:

- **`work show` lists every run at a Worktree.** It reports checkout
  inventory, not the caller's own binding (`show_issue_work` in
  `src/dashpot/sessions/work.py`). So the OpenCode probe's "a Worker's
  `work show` reports the Lead's run" is expected behaviour, not a defect.
  A `work workers` query would need explicit session identities, which the
  published `AgentRun` excludes today.
- **Duplicate Workers.** A launch that times out and is retried, or an
  OpenCode fork, can put two writers in one Worktree. `work start` enforces
  ownership per session, not per Worktree (inference).
- **Passive observation must not poll a harness API.** Even an OpenCode
  `GET` through `opencode api` can start the service, which then resumes
  cut-off turns.
- **Reviewers stay Sub-agents in every variant,** so most of the sub-agent
  fix backlog (#472, #475, #477, #478, #519, #520) is needed either way.
  Root Workers add a second backlog; they do not replace the first.

## Candidate uplifts

These would change the design materially, so none is applied. Each has a
recommendation for the maintainer to accept, adapt or reject.

| # | Uplift | Recommendation |
| --- | --- | --- |
| U1 | **A durable Lead link.** The Lead declares the link, by `work assign` generalised to root sessions, and Dashpot validates the Worker against the Worker's own placed hook record. The declaration is kept as provenance that outlives both Agent Runs, for example as an Event Log record ([ADR 0059](../adr/0059-keep-an-append-only-event-log-in-each-checkout.md)). The Worker-side `DASHPOT_LEAD` stamp stays optional corroboration. | Adopt. It reverses the design's Worker-side lean, avoids each failure the [Lead link](../proposals/lead-worker-design.md#the-lead-link) lists, and keeps authority where ADR 0096 put it. The live Lead-side assignment ending with the Lead's run is the Lead-ended signal decision 19 needs. |
| U2 | **Permission posture and credentials as contract items.** Each harness has a stated default. Claude Code uses `auto`, a parked Worker counting as needing a person, or `dontAsk` with an allow-list. A Codex launch is escalated or full-access, and every resume restates `-s`. OpenCode never uses `always`. The skill checks `gh auth status` inside a new Worker before giving it work. On Claude Code the Lead passes what a Worker needs with `--settings` `env`, since a Worker otherwise runs with the supervisor's environment. | Adopt. Without credentials no Worker opens its PR. Choosing between `auto`, which can park, and `dontAsk`, which denies, is a security decision for the maintainer. |
| U3 | **Phase by harness.** Claude Code is qualified first. Codex stays on sub-agent Workers until `codex queue` works from `workspace-write` or `exec` accepts mail. OpenCode stays until the plugin observes resumed turns and asks survive a restart. | Adopt, accepting a standing hybrid. ADR 0092 rejected a Claude Code-only skill, so two Worker shapes in the skill, pane and domain language is a cost the decision must name. |
| U4 | **Attention first in the Sessions pane.** A count of Workers waiting on a person that never folds away. Issue and PR lead each row, and the Lead is shown as provenance. | Adapt: make these requirements of #444 under either mechanism, with "unknown" shown where a harness cannot report an ask. |
| U5 | **An accountable person per Arc,** with the 3–5 ceiling counted per person across their Arcs. | Adapt: record it in the skill's Arc record and wave sizing. Dashpot itself has no person field and does not need one for this decision. |
| U6 | **Attachable Workers.** A person can attach to a root Worker and answer or redirect it: `claude attach` or agent view, `codex resume` on a daemon thread, or an OpenCode client on the service. | Adapt from "TUIs in tmux" to "attachable" as a contract item. Tmux is one route, not a dependency, and watching N windows is the monitoring load the human-factors evidence warns against. |
| U7 | **Reframe the Why.** Lead with lifetime and observed state, and state the Cleanup gain as measured. | Adopt. Narrowing the reviewer's blocker waits on observed placement: a declaration cannot stand in for occupancy evidence (ADR 0112). |
| U8 | **Record the non-adoption outcome and a minimum decision.** | Adopt. The branch now exists in the design; the decision below makes it actionable. |
| U9 | **Harness-native hand-back.** The Lead reads the Worker's own final output (`claude logs`, Codex's `-o` file, the OpenCode session's outcome and messages) beside the structured status file. | Adapt: the Lead reads these, not Dashpot. Keeping a Stop payload's `last_assistant_message` would break ADR 0059's rule against recording prompts and raw payloads. |
| N1 | **A `--bg` Lead with sub-agent Workers** (Claude Code). It may give Lead-independent lifetime with no Dashpot change, keeping asks, notices and the environment in one session. | Try alongside the pilot. Unknown: whether a backgrounded Lead whose turn has ended is evicted while its Sub-agents run. |
| N2 | **Reviewers as placed, read-only root sessions** in the Worker's Worktree. That removes the last Repository-wide blocker under root Workers. | Defer to after a pilot. It depends on #518, since a `claude -p` exit publishes no `SessionEnd`. |
| N3 | **Sub-agent placement through #474.** `isolation: "worktree"` places hooks under `.claude/worktrees/`, and the undocumented plugin `agent.spawn` hook can set `cwd`. | Pursue as an input to decision 1. If a Sub-agent can be placed, ADR 0066 could narrow its blocker, which recovers most of the Cleanup gain with no root sessions. |

## Candidate Issues

Found by the review and not filed. Check each against the open Issues
before filing.

- **OpenCode: the plugin misses turns a restarted service resumes.** Their
  runs stay orphaned and `work start` is refused as stale until a fresh
  prompt. This affects any session cut off mid-turn, not only Workers.
- **OpenCode: a pending ask reads `running`.** No observer reports a session
  waiting on a person, which U4 needs.
- **OpenCode: a repeated `/synthetic` message id starts an empty
  execution,** which can flicker a Lead's state. This may be upstream's.
- **Codex: a SIGTERM'd `exec` leaves an Orphaned Agent Run blocking its
  Worktree.** Cleanup already names it. The fix is documentation (stop with
  SIGINT) unless Dashpot should read a gone `exec` Host Process as ended.
- **Claude Code: a supervisor respawn loses a Worker's Issue Binding.**
  The killed process's `SessionEnd` ends the run before the same session
  resumes at the same Worktree. Dashpot could keep or continue the run when
  the same session id starts again with `source` `resume` (measured,
  #479), as ADR 0053 does for an orphaned run.
- **Claude Code: an asking `--bg` Worker reads `running`.** Its
  `Notification` hook fires and `claude agents` reports `waitingFor`
  `permission prompt`. With the OpenCode case above, this is the evidence
  U4's count needs.
- **Claude Code: the supervisor's environment.** Document that `--bg`
  sessions share the environment of the shell that started the supervisor,
  in the [harness reference](../agent-harness-server-client-reference.md)
  and the skill.
- **Stale statements outside the design.**
  - `docs/agent-sessions.md` says a `claude -p` exit publishes
    `SessionEnd` (#518), and its OpenCode recovery steps assume a resumed
    turn can bind.
  - [ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)'s
    gap table maps the Codex unload gap to closed #431 rather than #492.
  - A comment in `src/dashpot/sessions/harnesses.py` calls
    `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID` undocumented; both are now
    documented.

## Open decisions re-ranked

| Rank | Decision | Status |
| --- | --- | --- |
| 1 | 1. Adopt, and where | Load-bearing. Answer now (below). |
| 2 | New: Worker credentials | Load-bearing for any pilot (U2). |
| 3 | 5. Permission posture | Load-bearing for any pilot; a security call. |
| 4 | 19. Lead-ended policy | Load-bearing. Both reviews: Workers continue, accountability is explicit, and Dashpot never cancels them silently. |
| 5 | 6. Teardown authority | Load-bearing. A finished `--bg` Worker occupies its Worktree until it is stopped or evicted. The pilot can scope the authority to a Worker its Lead launched. |
| 6 | 2 and 16. Who declares the link | Answered by U1 if adopted. |
| 7 | 17. A keyed hand-back | Skill-level; adopt whenever. |
| 8 | 3. `work workers` and `work wait` | Deferred until a pilot shows the need. |
| 9 | 14. Needs-input visibility | Deferred to #444, as a requirement. |
| 10 | 7 and 13. Vocabulary | Deferred to the adopting ADR. |
| 11 | 4. No mailbox | Pre-answered by ADR 0008; confirm in one line. |
| 12 | 9, 11, 12 | Pre-answered or moot: 9 by ADR 0096, 11 by #473, and 12 has no current distinction. |
| 13 | 8, 10, 15, 18, 20 | Deferred to #444 or later presentation work. |

## Minimum viable decision

1. **Sub-agent Workers remain the shipped mechanism on every harness.**
   ADR 0092, or a short ADR amending it, records root-session Workers as
   considered and qualified per harness. It gives the measured reasons and
   the trigger that re-opens each harness:
   - Claude Code: its pilot passes.
   - Codex: `codex queue` works from `workspace-write`, or `exec` accepts
     mail while it runs.
   - OpenCode: the plugin observes resumed turns, and asks survive a
     restart.
   - Any harness: #474 shows a Sub-agent can be placed.
2. **#444, #477, #478 and #517 go ahead under sub-agent Workers,** as #498
   waits for. #444 takes U4's requirements.
3. **A Claude Code pilot is authorised, with pass criteria fixed in
   advance.** A `--bg` Worker, under the chosen posture:
   - takes a real Issue to an open PR with green CI and this Repository's
     review evidence, without a person;
   - neither enters another Worktree nor parks at a commit;
   - can run `gh`;
   - blocks only its own Worktree outside review windows;
   - is known complete by its Lead within a bounded delay;
   - leaves a state Dashpot reads correctly when evicted while idle.

   If it passes, an adopting ADR makes root-session Workers an opt-in mode
   on Claude Code, with U1 and U2.

This defers the link's implementation, `work workers` and `work wait`, pane
grouping, the vocabulary ruling, and every Codex and OpenCode change. It
meets #479's outcome: the comparison exists, the experiments ran, and the
decision is recorded either way.

## Remaining unknowns

| Unknown | Cheapest test |
| --- | --- |
| When a supervisor takes a new environment, and so which credentials a Worker started from the user's real configuration holds. | Read the user's supervisor's `/proc/<pid>/environ` names only, and restart it from a known shell in a disposable configuration. |
| Whether a real model in a `--bg` Worker follows the injected "use `EnterWorktree`" and "ask before committing" instructions, with and without `bgIsolation: "none"` and a brief that authorises commits. A fixture model cannot show this. | One real-model `--bg` Worker on a throwaway Issue in a disposable repository. |
| How often `auto` parks during a normal Issue. | The same run, counting `waitingFor: permission prompt`, then repeated under `dontAsk`. |
| SIGKILL and a crash of a `--bg` Worker, as opposed to the SIGTERM measured. | A rerun of the respawn scenario with SIGKILL. |
| Idle eviction of a Worker waiting on CI, and of a `--bg` Lead whose Sub-agents still run (N1). | A `--bg` session holding a background `sleep`, observed past an hour, with a variant running a background Sub-agent. |
| The reviewer-window estimate. | Recompute it from Dashpot's own `SubagentStart` and `SubagentStop` records for one recorded Arc. |
| Codex: a person approving an escalated launch in the terminal client, and `gh` under the sandbox's Unix-socket refusal. | Deferred until Codex re-opens. |
| OpenCode: whether a real model repeats a push after "the server restarted". | Deferred until OpenCode re-opens. |
