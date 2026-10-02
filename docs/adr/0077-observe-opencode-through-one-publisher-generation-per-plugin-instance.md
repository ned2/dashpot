---
status: amended
date: 2026-10-02
amended-by: 0080-keep-a-retired-opencode-generations-backend-on-its-sessions.md
---

# Observe OpenCode through one publisher generation per plugin instance

One OpenCode backend serves every session of every directory it has an
instance for, and outlives each of them. It loads a plugin once per instance,
and replaces that instance, plugin included, when it reloads or disposes of
it, without ending the backend or its sessions
([ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)).
The [OpenCode design](../proposals/opencode-integration-design.md#track-publisher-lifetime-without-redefining-agent-session)
proposed a publisher generation per plugin instance, with registration,
retirement and per-session ordering. [#163](https://github.com/ned2/dashpot/issues/163)
implements it. Its [probe](../../scripts/experiments/opencode-163/run.mjs)
measured OpenCode 1.18.30 on Linux in disposable configuration with a mock
model, through Dashpot's real helper:

- `opencode serve` is one process named `opencode`. Every plugin helper and
  every shell command it runs is its direct child.
- The plugin in `$XDG_CONFIG_HOME/opencode/plugins/` is discovered without
  configuration. An instance, and its plugin, starts at the first request
  that names its directory.
- `session.status` repeats `busy` at every step of a turn, and reports
  `retry`. It has no error status: a turn the provider refuses outright
  ends with `idle`, like any other turn. A child session carries
  `parentID`; a fork does not.
  `session.deleted` is delivered.
- On `/instance/dispose`, the replacement instance initialises, and
  registers, **before** the disposed instance's `dispose` hook runs.
- The helper's own work takes 25–37 ms. Starting the interpreter takes
  about 0.12 s.

## Decision

**The adapter.** `opencode` is a harness. Its Host Process is the backend,
the process named `opencode`. That process is not exclusive to one session,
and its exit never proves that a session ended. The adapter designates no
location evidence, so Live Relocation of an OpenCode session is
unsupported. Its identity claim is the command-scoped claim of
[ADR 0078](0078-give-an-opencode-command-a-claim-only-for-its-own-bootstrap.md).

**Publisher records.** Each plugin instance draws a random publisher
generation before its first publication. A publisher record exists for each
pairing of backend (PID and start time) and instance directory. It sits in
the `opencode/` directory of the hook store that the directory's sessions
publish to. It holds:

- the active generation;
- tombstones for the generations retired from the pairing;
- a watermark per session (generation, sequence, last accepted status, and
  whether the session is a root);
- tombstones for the sessions OpenCode deleted.

The tombstone and watermark lists are bounded. Each publication runs under
the record's lock, and only a helper that the backend started itself may
publish. The plugin passes its PID, and the helper corroborates it as the
nearest OpenCode process in its own ancestry.

**Registration and retirement.**

- **Registration** is accepted only while no generation is active. A
  registration by the active generation is a duplicate. A retired
  generation's registration is refused for good.
- **A conflict** goes back to the plugin. It retries with bounded backoff
  within the publication's deadline. Its first attempt, at initialisation,
  does not wait, because OpenCode holds the instance until the plugin
  initialises.
- **Retirement** is the plugin's `dispose` hook. After a 1 s drain of
  publications already admitted, it tombstones the generation, even one that
  never registered, and clears it if it was active. It also takes the
  generation's root sessions off their Host Process: their records name no
  process, with the reason `opencode-publisher-retired`. Their activity then
  reads unknown, rather than the retired generation's last status, until a
  successor publishes them.
- **Reclamation.** Each accepted registration removes the publisher records
  of backends proven gone. A backend that cannot be observed keeps its
  record.

**Translation.** The helper translates each accepted publication into
Dashpot's shared hook events for the root session, through the one publisher
seam that owns hook records and the Work Store:

| OpenCode | Root session | Child session (`parentID`) |
| --- | --- | --- |
| `busy`, `retry` | `UserPromptSubmit` | `SubagentStart` on its root |
| `idle` | `Stop` | `SubagentStop` on its root |
| a shell command's bootstrap | `PreToolUse` | `SubagentStart` on its root |
| `session.deleted` | `SessionEnd` | `SubagentStop` on its root |

- **Errors.** A failed turn reads as waiting, through its `idle`. Dashpot
  reports turn state, not a turn's outcome.
- **Status.** A status equal to the last one accepted is a duplicate, and
  writes nothing. A sequence at or below the watermark is stale.
- **Children.** A child is a Sub-agent of its root, at any depth
  ([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)).
  It is never an Agent Session of its own. A fork has no `parentID`, so it
  is a new session, and inherits no run. The child rules of
  [ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)
  hold without help: the first word below makes a root's record before any
  child event reaches it, deletion refuses a child's late word before it
  reaches the store, and the helper writes one backend's events in turn under
  its publisher record's lock, so a child event is never stamped before an
  event already written.
- **A generation's first word.** A generation's first publication for a root
  writes `SessionStart` first. The record then names the backend again, and
  forgets the Sub-agents that a retired generation last saw.
- **Location.** A session whose native directory is not its instance's is
  refused.
- **Deletion.** It ends that session's Agent Run through the existing
  `SessionEnd` reconciliation, and refuses every later publication for the
  session.

**Restart.** A backend restart leaves its bound runs orphaned. A resumed
session continues Issue work only through an explicit `work start` under the
new backend, the agreed policy. There is no ADR 0053 continuation for
OpenCode.

## Departures from the proposal

- **No registration revision.** The proposal compared a read revision so
  that two registrations racing for an empty slot could not both win. The
  record's lock already serialises them, and the second one finds an active
  generation. The revision would also have wrongly refused the measured
  ordering, where the replacement reads before its predecessor retires. The
  plugin's conflict retry handles that ordering instead.
- **Retirement marks the session records.** Observation does not consult the
  publisher record. A retired generation's sessions read unknown because
  their records no longer name a process.
- **Duplicates are by status.** There is no request digest. A duplicate
  status advances the watermark, writes nothing, and does not reset the
  activity clock.
- **No pending deletion effect.** Deletion reuses `SessionEnd`, whose
  reconciliation already removes only the exact run of that identity and
  backend.

## Considered options

- **Take over from an active predecessor after a timeout.** Rejected.
  Silence does not prove retirement, and a delayed predecessor would publish
  over its successor. A predecessor that never retires leaves its directory
  unobserved until the backend restarts, as the proposal recommended.
- **A record per generation.** Rejected. Ownership is a property of the
  pairing, and one locked document keeps registration, retirement and
  ordering in one replacement.
- **Keep the retired generation's last status.** Rejected. Nothing observes
  those sessions any more, and unknown is the honest reading.

## Consequences

- Two OpenCode sessions in one backend have separate records, activity and
  Agent Runs.
- Reloading OpenCode's configuration loses observation briefly, and never
  ends a session or its Issue work.
- A lost `dispose` while the backend lives leaves that directory unobserved
  until an operator restarts the backend.
- `dashpot work stop --session` ends an orphaned OpenCode run, as it does
  for the other harnesses.
- What the OpenCode acceptance run has not yet measured: the local TUI's
  process shape, and resume through
  `opencode <dir> --session`. Until it passes,
  [ADR 0079](0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md)
  keeps OpenCode unsupported.
