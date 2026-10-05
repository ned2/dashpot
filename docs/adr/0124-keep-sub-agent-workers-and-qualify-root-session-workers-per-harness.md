---
status: accepted
date: 2026-10-05
---

# Keep sub-agent Workers, and qualify root-session Workers one harness at a time

[ADR 0092](0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
ships a Lead that runs each Worker as a background Sub-agent of its own
Agent Session. [#479](https://github.com/ned2/dashpot/issues/479) asked
whether Workers should instead be root Agent Sessions of their harness,
linked to the Lead by a declaration. The
[Lead and Worker design](../proposals/lead-worker-design.md) proposes the
change. A [review](../reviews/lead-worker-design-review-2026-10-05.md)
checked its harness claims and ran the experiments it left as future work
([spike](../spikes/root-session-workers-spike.md)). This decision calls a
Worker run as its own root Agent Session a root-session Worker, pending the
vocabulary ruling of an adopting ADR.

The review found one reason sub-agent Workers cannot match by small fixes: a
root-session Worker's life does not depend on its Lead's. A closed terminal,
a `/exit` or an unloaded Codex daemon thread ends or strands today's
Workers, and a root session survives all three. Its state is observed
from its own hook records rather than inferred from its Lead's. The other
reasons are weaker than the design stated, and the cost differs by harness:

- **Cleanup.** [ADR 0112](0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)
  already lets a person remove a Worktree despite the Repository-wide
  `sub-agent` blocker
  ([ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)).
  Under root-session Workers each Worker's reviewer Sub-agent brings that
  blocker back while it runs, measured on Claude Code and OpenCode, so the
  gain is a partial reduction, not its removal. Narrowing the reviewer's
  blocker waits on observed placement, since a declaration cannot stand in
  for occupancy evidence.
- **Claude Code.** A `--bg` Worker works in the live run, with two hazards:
  it runs with the environment, credentials included, of whichever shell
  first started the supervisor, and a Worker the supervisor respawns after a
  SIGTERM has lost its Issue Binding.
- **Codex.** A detached `codex exec` Worker works only under four
  constraints: the Lead launches it from a full-access or escalated shell;
  `codex queue` carries messages Worker to Lead only, and only from an
  unsandboxed shell; the Lead reaches a Worker by `codex exec resume`,
  restating the sandbox flags; and a Worker is stopped with SIGINT, since a
  SIGTERM leaves an Orphaned Agent Run. Mail sent to a running `exec` is
  lost.
- **OpenCode.** A restarted service resumes cut-off turns the plugin does
  not observe, so their runs stay orphaned and `work start` is refused as
  stale, and an `always` answer saves a Project-wide rule.
- **The Lead link the design leaned to does not hold.** A link stored on the
  Worker's Agent Run is deleted by the Worker's own `work stop`.

## Decision

**Sub-agent Workers remain the shipped mechanism on every harness.**
Root-session Workers are considered and qualified one harness at a time. A
harness re-opens when its trigger is met:

| Harness | Re-opens when |
| --- | --- |
| Claude Code | the pilot below passes |
| Codex | `codex queue` works from `workspace-write`, or `exec` accepts mail while it runs |
| OpenCode | the plugin observes turns a restarted service resumes, and a pending ask survives a restart |
| Any | [#474](https://github.com/ned2/dashpot/issues/474) shows a Sub-agent can be placed in a Worktree, which could narrow ADR 0066's blocker with no root sessions |

**[#444](https://github.com/ned2/dashpot/issues/444),
[#477](https://github.com/ned2/dashpot/issues/477),
[#478](https://github.com/ned2/dashpot/issues/478) and
[#517](https://github.com/ned2/dashpot/issues/517) go ahead under sub-agent
Workers.** #444 takes these requirements, which hold under either
mechanism: a count of Workers waiting on a person that never folds away,
"unknown" where a harness cannot report an ask, the Issue and PR leading
each Worker's row, and the Lead shown as provenance.

**A Claude Code pilot is authorised, with its pass criteria fixed now.** A
`--bg` Worker launched by a Lead:

- (a) takes a real Issue to an open PR with green CI and this Repository's
  review evidence, without a person;
- (b) neither enters another Worktree nor parks at a commit;
- (c) can run `gh`;
- (d) blocks only its own Worktree outside its review windows;
- (e) is known complete by its Lead within a bounded delay;
- (f) leaves a state Dashpot reads correctly when evicted while idle.

The pass is judged under the posture the maintainer chooses. The pilot
counts how often `auto` parks and repeats under `dontAsk` with an allow-list
to inform that choice. If it passes, an adopting ADR makes
root-session Workers an opt-in mode on Claude Code. That ADR settles:

- **The Lead link.** The Lead declares it, by `work assign` generalised to
  root sessions
  ([ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)),
  and Dashpot validates the Worker against the Worker's own placed hook
  record. The declaration is kept as provenance that outlives both Agent
  Runs, for example as an Event Log record
  ([ADR 0059](0059-keep-an-append-only-event-log-in-each-checkout.md)). A
  `DASHPOT_LEAD` stamp in the Worker's environment is optional
  corroboration. The live assignment ending with the Lead's run is the
  signal that the Lead ended.
- **Credentials and permission posture,** as Worker contract items. The
  skill checks `gh auth status` inside a new Worker before giving it work,
  and the Lead passes what a Worker needs with `--settings` `env`. The
  posture is `auto`, where a parked Worker counts as needing a person, or
  `dontAsk` with an allow-list, a security choice for the maintainer that
  the pilot's results inform.
- **When the Lead ends first.** Workers continue, accountability is
  explicit, and Dashpot never cancels a Worker silently.
- **Teardown authority,** scoped to a Worker its Lead launched.
- **Vocabulary** for a root-session Worker.

A root-session Worker is attachable, as a contract item: a person can
attach to it and answer or redirect it, with tmux one route rather than a
dependency. Its Lead reads the Worker's own final output (`claude logs`,
Codex's `-o` file, the OpenCode session's messages) beside the skill's
status file, and Dashpot records none of it, keeping ADR 0059's rule against
raw payloads.

Under either mechanism, the skill's Arc record names one person accountable
for the Arc, and its wave sizing counts the three-to-five Worker ceiling per
person across their Arcs. Dashpot needs no person field for this.

## Considered options

- **Adopt root-session Workers on every harness now, as the design
  proposed.** Rejected: Codex works only under four constraints and loses
  mail sent to a running Worker, OpenCode's restart recovery is broken for
  Workers today, and the Cleanup gain is partial.
- **Adopt on Claude Code now, without a pilot.** Rejected: whether a real
  model in a `--bg` Worker follows the injected `EnterWorktree` and
  commit-approval instructions, how often `auto` parks, and how a Worker
  waiting on CI is evicted are unmeasured, and a fixture model cannot show
  them.
- **Keep sub-agent Workers and close the question.** Rejected: Lead-independent
  lifetime is real, Claude Code's mechanism works, and the triggers are
  concrete enough to re-open on.
- **Declare the link from the Worker side,** as the design leaned. Rejected,
  above: the link would not outlive the Worker's own `work stop`.
- **Run reviewers as placed, read-only root sessions,** which would remove
  the last Repository-wide blocker under root-session Workers. Deferred
  until after a pilot: it depends on
  [#518](https://github.com/ned2/dashpot/issues/518), since a `claude -p`
  exit publishes no `SessionEnd`.
- **A `--bg` Lead with sub-agent Workers** on Claude Code, which may give
  Lead-independent lifetime with no Dashpot change. Not decided: it is tried
  alongside the pilot, to learn whether a backgrounded Lead whose turn has
  ended is evicted while its Sub-agents run.

## Consequences

- The skill, the Sessions pane and the domain language keep one Worker
  shape until a harness qualifies. If Claude Code does, the skill carries
  two shapes as a standing hybrid, a cost ADR 0092 avoided by rejecting a
  Claude Code-only skill and one the adopting ADR must name.
- `work assign` keeps its Sub-agent meaning, and no `work workers` or
  `work wait` command is built until a pilot shows the need.
- The design note, its analysis and the review stay as the comparison and
  evidence behind this decision; the design note now describes the pilot's
  shape and records which of its open decisions this ADR answers.
- Amends [ADR 0092](0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md):
  its Workers stay background Sub-agents on every harness, with root-session
  Workers qualified one harness at a time, and each Arc names an accountable
  person against whom the Worker ceiling is counted.
