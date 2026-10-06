---
status: accepted
date: 2026-10-06
---

# Keep an Arc's working record in a local Arc Ledger

[ADR 0092](0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
decided **Run records on Issues**. A Lead posts its Arc's record as
comments on the epic, or on a tracking Issue it opens for a list: the arc
map, each Wave, each merge, each decision and the close-out. It chose GitHub
because AGENTS.md forbids a private notes file, and because comments survive
a lost scratch directory. Two Arcs run since then showed what that costs
([#636](https://github.com/ned2/dashpot/issues/636)):

- **A public Issue became the Lead's scratchpad.** Mid-arc notes are written
  quickly, from a live session, and take in whatever the session knows:
  machine load, local failures, the operator's circumstances, tool
  behaviour. Several record comments from those two Arcs had to be deleted
  for oversharing. A rule asking the Lead to be careful does not change what
  the channel invites.
- **Point-in-time operational state sat on the durable ledger.** Wave plans,
  hypotheses and broadcast drafts matter while an Arc runs and are noise
  afterwards. Issues are this Project's durable record of plans and
  follow-ups.
- **A Lead read back text anyone could write.** A Lead found other Arcs, and
  resumed its own, by searching Issue bodies and reading their comments, with
  no filter on who wrote them.

The reason for leaving the scratch directory still holds: a restart lost a
Lead's scratch directory mid-arc, and
[#603](https://github.com/ned2/dashpot/issues/603) made the brief template
recoverable from the record.

## Decision

**An Arc Ledger in the Lead's checkout.** The Lead keeps its Arc's working
record in a local **Arc Ledger** under
`.dashpot/state/skills/dashpot-execute-issues/` in the checkout it bound
in, normally the main checkout. `.dashpot/state/` is the Project-local
state directory of
[ADR 0003](0003-prefer-project-local-dashpot-state.md). It is ignored by
the `.gitignore` Dashpot writes inside it, and it survives a restart. The
skill's
[arc-ledger.md](../../src/dashpot/skills/dashpot-execute-issues/references/arc-ledger.md)
defines the layout:

- `arcs/<arc-id>/arc.json`: the summary other Leads read while sharing
  the machine, whose fields the reference lists;
- `arcs/<arc-id>/ledger.md`: the record, appended as the Arc runs, with the
  same entries the comments held;
- the filled brief template;
- `reservations/<kind>-<value>/`: one directory per reserved number.

**Naming.** `skills/` separates what a skill's agents write from the
stores Dashpot's own code keeps beside it (`events`, `github-issues`,
`sessions`, `work`), so it never collides with a store Dashpot adds later.
The skill's exact name ties the directory to the skill that defines it.

**Rules.**

- **Writes.** The Lead alone writes its Arc's files. Workers report through
  their harness. The Lead appends to `ledger.md` and replaces `arc.json` by
  renaming a temporary file, so neither needs `flock`, which macOS lacks.
- **Reservations.** A reservation is a `mkdir`, which fails when another
  Lead sharing that ledger root holds the number. Leads in different
  checkouts read each other's reservations, and the clash rules ADR 0092's
  skill already had settle a clash between them.
- **Discovery.** Another open Arc is found by listing every checkout's
  `arcs/*/arc.json`, with no search of GitHub. The Lead checks that Git
  ignores the ledger root before its first write, and stops if it does not.
- **Retention.** The end of an Arc marks it closed and releases its
  reservations; a paused Arc stays open and keeps them. Nothing is deleted
  automatically: the Lead offers closed Arcs older than a month for
  deletion, and deletes only those the user confirms.

**What goes to GitHub.** Only reviewed outcomes:

- PRs with their validation sections;
- follow-up Issues and repository lessons, filed as Issues;
- a decision that changes an Issue's scope, as a comment on that Issue;
- a measurement that settles a downstream decision;
- each Issue's closing comment;
- the Arc's outcome: an Issue → PR → merge-commit mapping, on the epic or,
  for a list, on the Issue the Lead bound; and for a list, a comment on
  each Issue the Arc unblocks.

A list Arc no longer opens a tracking Issue. Its Lead already binds to the
list's critical-path root, which carries the mapping, so a tracking Issue
would only duplicate it.

**Not a private memory store.** AGENTS.md forbids a private agent memory
store. The Arc Ledger is not one: it holds one Arc's working state, only
that Arc's Lead writes it, it sits in the Project's own state directory
where the user can read it, it is closed with the Arc, and the Arc's
outcomes go to GitHub.

## Considered options

- **Keep run records on Issues.** Rejected for the three costs above.
- **Git refs, `git notes` or an orphan Branch** in the repository's own
  object store. Rejected. Custom refs travel with `git push --mirror`, and
  a mirror fetch with pruning deletes them. `git notes` loses one of two
  concurrent writes without an error. An orphan Branch is pushed by an
  ordinary `git push --all`. Each risks publishing the record or losing it.
- **A gist, a private repository or another hosted location.** Rejected:
  the record would still leave the machine, which is the cost this decision
  removes.
- **A directory under the user's home, outside every checkout.** Rejected.
  Codex's `workspace-write` sandbox cannot write there, it holds the state
  of every repository in one place, and it separates the record from the
  Project it describes.
- **A ledger only in the main checkout, shared by every Lead.** Rejected:
  a Codex Lead bound in a linked Worktree cannot write the main checkout
  under `workspace-write`. Keeping the ledger root in the Lead's own
  checkout costs Leads in different checkouts the `mkdir` arbitration, but
  the clash rules already cover them.
- **`.dashpot/state/agent-issue-execution/`.** Rejected: it names neither the
  skill nor a domain term, and every skill's state is for agents; `skills/`
  says that once for all of them.
- **A `dashpot arc` command** to list, prune and reserve. Deferred until the
  ledger's shape has run for an Arc or two.

## Consequences

- Amends
  [ADR 0092](0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md):
  its **Run records on Issues** no longer holds, and the rest of it stands.
- The bundled `dashpot-execute-issues` skill replaces
  `references/run-records.md` with `references/arc-ledger.md`. `integrate`'s
  skill manifest removes the old file from an updated copy.
- The skill's own shipped text still carries nothing of this repository.
  Its ledger root names only the skill and Dashpot's state directory.
- An Arc's working record is lost with the machine, with a `git clean -x`
  of the Lead's checkout, or with that checkout's removal when it is a
  linked Worktree, which the skill tells the user to keep until the Arc is
  closed. Its outcomes are on GitHub by close-out, which is what later
  readers need.
- A Lead sees other Arcs only in this clone. An Arc run from another clone
  or another machine shows only through the integration Branch, open PRs
  and Remote-Tracking Branches, which the reservation scan reads anyway.
- AGENTS.md's ADR-number reservation scan reads open Arc Ledgers in place of
  record Issues, and the domain language gains **Arc Ledger**.
- The status and broadcast files the skill's harness notes put in a
  Worktree's Git directory are a separate defect under Codex's sandbox
  ([#637](https://github.com/ned2/dashpot/issues/637)).
