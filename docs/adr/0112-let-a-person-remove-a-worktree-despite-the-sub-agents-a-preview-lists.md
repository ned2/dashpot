---
status: accepted
date: 2026-10-05
---

# Let a person remove a Worktree despite the sub-agents a preview lists

[ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md) blocks
the removal of every Worktree of a Repository while any of its Agent Sessions
lists a live sub-agent, because no hook says which Worktree a sub-agent works
in. The block is right as evidence goes, but it has no end a person can
reach: a session that dispatches one sub-agent per Issue Worktree freezes
Cleanup of the whole Repository for as long as any of them works, including
the Worktree of an Issue that finished hours earlier
([#476](https://github.com/ned2/dashpot/issues/476), Part 2). The person
often knows what Dashpot cannot: which Worktree each sub-agent was sent to.

[ADR 0104](0104-block-worktree-removal-while-a-process-runs-inside-it.md)
added the evidence that makes such knowledge safe to act on. A sub-agent's
command, while it runs, is a process inside the Worktree it works in, and a
`process` blocker names it. What remains unplaced is a sub-agent between
commands.

The closer precedent is `dashpot work forget-subagents`
([ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)):
a person asserting what no hook reports. `--delete-ignored` is not one. It
acknowledges a loss the preview discloses and the person can inspect, where
this is an assertion about where sub-agents work.

## Decision

A confirmed Cleanup may remove a Worktree despite its `sub-agent` blockers,
for exactly the sub-agents the preview lists, on a person's explicit
acknowledgement.

- **The `sub-agent` blocker names what can be acknowledged.** Each one
  carries its session's ID, its harness, and the IDs of its listed
  sub-agents, as `sessionId`, `harness` and `agents` in the Cleanup JSON.
  Every other blocker carries `null`, `null` and `[]`. Its existing
  explanation is unchanged.
- **Offered only where nothing else stands.** A Worktree preview offers the
  acknowledgement when `sub-agent` blockers are all that hold the Worktree,
  the preview has no refusal, and the processes inside the Worktree were all
  checked. A scan that fell short cannot show that no sub-agent's command
  runs there, so it is not offered then, and an acknowledgement given anyway
  is refused. No other blocker is ever lifted: `agent-session`, `agent-run`,
  `process`, a dirty Worktree, a lock, protection, integration, and the rest
  stand as before. A Branch blocked only because it is checked out in the
  acknowledged Worktree becomes selectable with it, and is never selected
  for the person.
- **Exactly the listed set.** The acknowledgement names each session and
  every one of its listed sub-agents. On the command line it is
  `dashpot worktree remove <path> --despite-subagents <session-id>:<id>,<id>`,
  one flag per session. A set that is not exactly the one the preview lists
  removes nothing. The text preview, and a refused `worktree remove`, print
  the exact flag value beneath the Worktree, as a person's option. The flag
  spells only IDs that are identifiers without `:`: an ID holding `,` or `:`
  would read back as another set, and one holding a space or a shell
  character would not survive a paste into a shell, so for such a set the
  preview points to the dashboard instead. In the
  dashboard, the Cleanup dialog names each session and its count of
  sub-agents beside a toggle, built from `MarkedCheckbox`, that reads "I have
  checked that none of these sub-agents works in this Worktree". It starts
  off and is never focused for the person, so a stray Enter cannot tick it.
  Confirming without it removes nothing and says what is missing.
- **Inspected again on confirmation and before each step.** The
  re-inspection on confirmation compares the listed sub-agents with the
  acknowledged ones, and refuses a different set. When the set listed now
  differs from the one the confirmed preview listed, whether one started,
  one stopped, or a session appeared, it refuses as a changed preview, with
  the revised preview; an acknowledgement that names another set than an
  unchanged preview listed is refused as a mistake, without calling the
  preview changed, even where another blocker kept the preview from
  offering the override. Before each destructive step up to the Worktree's
  removal, the Worktree's occupants and the processes inside it are
  inspected again, with the same occupancy and process checks the preview
  runs. Any occupant but the acknowledged sub-agents, a
  changed set, a process inside the Worktree, or a scan that fell short
  refuses that step, and the steps after it are not attempted. A Worktree
  already removed needs no acknowledgement, so the Branch step after it is
  not rechecked.
- **Recorded in the Event Log.** A performed Cleanup that carried an
  acknowledgement records one `cleanup.subagents_acknowledged` event per
  acknowledged session and harness. Its envelope names the session, its
  harness and the Worktree; its body lists the acknowledged sub-agent IDs as
  `dashpot.sub_agent.ids` and the Worktree's outcome as
  `dashpot.cleanup.outcome`, under the field names
  [ADR 0064](0064-publish-runtime-events-under-their-event-log-field-names.md)
  publishes. It carries identifiers only, as
  [ADR 0059](0059-keep-an-append-only-event-log-in-each-checkout.md)
  requires: an agent ID that is not an identifier is left out of the event
  rather than failing a Cleanup that has already removed the Worktree, so
  the list is empty when none of a session's IDs is one. A dry
  run or a refused confirmation records nothing.
- **A person's assertion, never an agent's.** The bundled
  `dashpot-issue-work` and `dashpot-execute-issues` skills forbid an agent
  from passing the flag or ticking the toggle. An agent reading the preview
  could otherwise copy the IDs straight into the flag, and the assertion
  would rest on nothing.

## Considered options

- **Treat a Worker Assignment's Worktree as its location**
  ([ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)):
  rejected. An assignment is where a Lead intends a Worker's commands to run,
  not observed occupancy, and a Lead's declaration must not stand in for a
  person's confirmation.
- **Let a sub-agent declare its own location from its shell:** rejected. A
  Claude Code sub-agent's shell carries its session's ID and no agent ID, so
  its claim cannot be told apart from its Lead's.
- **Parse tool inputs for paths or `cd` targets:** rejected, as ADR 0066
  rejected it. It is guesswork, adds per-tool-call hook cost, and retains
  command text.
- **Remove the Worktree automatically once it is free:** rejected. It would
  mutate without a person's confirmation
  ([ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md),
  [ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)).
- **Acknowledge the sub-agents with one flag for every session, or without
  naming them:** rejected. A blanket flag would also acknowledge a sub-agent
  that started after the person last looked.
- **Make the acknowledgement part of the preview and its fingerprint:**
  rejected. The fingerprint is the evidence a person confirms against; the
  acknowledgement is what the person says about it, compared with that
  evidence on confirmation.

## Consequences

- An arc that dispatches one sub-agent per Worktree no longer freezes
  Cleanup of the whole Repository: a person who knows a Worktree's Worker is
  done can remove it while the others work.
- The flag's guarantee is the person's, bounded by what Dashpot can still
  see. A sub-agent the person misplaced, idle between commands in the
  Worktree, loses it. The dirty-Worktree refusal and the unforced
  `git worktree remove` still keep uncommitted work, as ADR 0066 relies on.
- With `--delete-remote-branch`, the Branch at the remote is deleted
  before the Worktree is removed, as ADR 0019's order has it. Each step is
  checked first, so a sub-agent set that changes or a process that appears
  after the remote deletion refuses the Worktree's removal and leaves the
  remote deletion done, with its recovery command reported.
- `CleanupBlocker` gains three published keys, so a client that pinned the
  blocker's key set sees `sessionId`, `harness` and `agents`.
- The Runtime Event vocabulary gains `cleanup.subagents_acknowledged`,
  recorded by the command line and the dashboard alike.
