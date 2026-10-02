---
status: accepted
date: 2026-10-02
---

# Orphan the runs of a stopped or restarted managed Codex daemon

[ADR 0015](0015-reconcile-the-agent-run-at-session-end.md) ends a
session's Agent Run at its graceful `SessionEnd`, and
[ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)
takes `SessionEnd` as the positive evidence that ends Codex and Claude Code
work. For a thread on the managed Codex daemon, that evidence has two causes.
The daemon unloads a thread about 60 s after its last client leaves, and it
ends every thread it holds when `codex app-server daemon restart` or `stop`
replaces or stops it. The first is the conversation ending. The second is the
runtime going away under a conversation that may still be under way: a restart
reloads every loaded thread into the replacement daemon, with no
`SessionStart`, and the agent's Issue work carries on there.
[#375](https://github.com/ned2/dashpot/issues/375) found that both publish the
same `SessionEnd`, so Dashpot ended the run of every bound thread a restart
reloaded. [#356](https://github.com/ned2/dashpot/issues/356) asked whether
those runs should survive, and on 2026-10-02 the maintainer chose to list them
as Orphaned Agent Runs, recoverable with `work start`, rather than end or
continue them.

#356 measured `codex-cli` 0.160.0 on Linux, with stand-in hooks and then with
Dashpot's real publisher. The result is recorded in the
[harness reference](../agent-harness-server-client-reference.md#managed-daemon-restart-and-stop-at-01600)
and its [trace](../spikes/measurements/issue-356-codex-trace.jsonl):

- The `SessionEnd` payload is identical for an unload, a restart and a stop:
  the same keys, with `reason: "other"`.
- The daemon waits for its `SessionEnd` hooks before it exits, then exits
  within about 0.1 s of the last one. Codex kills a `SessionEnd` hook at about
  3 s, although the hook configuration names 30 s, so the daemon is gone
  within about 3 s of the hooks beginning. The hooks of concurrent threads
  run in parallel.
- A stop with a turn running first lets the turn finish, which took 20 s in
  the measurement, and only then runs every loaded thread's `SessionEnd`,
  an idle thread's as well as the busy one's. A restart with a turn running
  was not measured.
- A process the hook starts in a session of its own survives both the hook's
  kill and the daemon's exit. On a restart it sees the daemon exit about
  0.4 s after the hook began, and on a stop whose hooks held until Codex
  killed them, about 3 s after; on an unload it sees the daemon still running
  15 s later.
- An `exec` exit and a standalone terminal's `/exit` also end their Host
  Process right after `SessionEnd`, so the host's exit alone cannot tell a
  restart from those graceful ends. Only the host's argument vector can: the
  daemon runs as `codex app-server … --managed-daemon`.

So the hook cannot wait to see what happens to the daemon, because the daemon
is waiting on the hook. Something that outlives the hook has to decide.

## Decision

A `SessionEnd` whose Host Process is the managed Codex daemon no longer ends
its runs itself. The hook still writes the record as ended and removes the
session's records as before. It then hands the runs that `SessionEnd` would
have ended to a **settler**: a process started in a session of its own, with
none of the hook's streams, so that Codex neither waits for it nor kills it.
The hook's outcome reports the Work Store change as `deferred`. A thread with
no run starts no settler.

The settler watches the daemon for 10 s and decides by its Session Liveness:

- **Gone** at any point: the daemon was stopped or restarted. The runs stay,
  and observation lists them as Orphaned Agent Runs under the gone daemon.
  The session recovers with `work start` from the resumed or reloaded thread,
  which starts a new run on the new Host Process, as for a killed daemon.
- **Live** at the deadline: the daemon unloaded the thread. The runs end
  through the Work Store's compare-and-delete, under the same match ADR 0015
  uses: the session's identity, the ending Host Process, and no run started
  after the `SessionEnd`.
- **Unknown** at the deadline: nothing ends. Unknown is never evidence that a
  process ended (ADR 0067), nor that it lived on.

The settler records its own Event Log process, of kind
`hook:codex:SessionEnd`, whose `hook.outcome` reports `ended` or `unchanged`.

Every other `SessionEnd` ends its runs at once, as before: an `exec` exit, a
standalone `/exit`, an unmanaged `codex app-server --listen`, Claude Code, and
an end whose Host Process was not observed. A run carrying a Relocation Intent
is still preserved, and an orphan of another Host Process is still continued
first where ADR 0075 applies, which it never does for Codex.

Nothing is continued or adopted. The settler only ends or leaves a run, and a
reloaded thread's next hook binds nothing. Continuing a run across a restart
is [#380](https://github.com/ned2/dashpot/issues/380).

### The argument vector chooses only between ending and waiting

[ADR 0072](0072-keep-every-codex-host-process-non-exclusive.md) refused to
read continuation evidence from a Codex argument vector, because the same
launch can be standalone or daemon-hosted. That decision stands: Codex stays
non-exclusive in every mode. This decision reads the argument vector for a
narrower question, and the difference is what makes it acceptable:

- The vector is the Host Process's own, observed by the hook from that
  process, and `--managed-daemon` is a flag Codex passes only when it starts
  its own daemon, whether by autostart or by `codex app-server daemon start`.
  It is not a launch shape a person chooses, unlike a terminal's
  `--disable daemon_auto_start`.
- It does not decide the outcome. It decides only whether to end the runs now
  or wait for the daemon's liveness, and liveness, a pid and start time proved
  gone or live, decides.
- Misreading it costs only a visible, recoverable run. A daemon misread as
  anything else ends its runs at once, as before this decision. A graceful end
  misread as a daemon's leaves its run orphaned once the host exits. Neither
  error binds a run to a process or carries one across a boundary.

## Considered options

- **Keep ending every `SessionEnd`'s runs.** Rejected by the maintainer. A
  restart would end every bound run the daemon held, while the agents in
  those threads continue working on their Issues, unobserved. A restart the
  daemon's updater starts after installing a release would presumably do the
  same, but the measurement turned the updater off and did not see one.
- **Continue the runs into the replacement daemon.** Deferred to #380. A
  reloaded thread publishes nothing until its next turn, and continuing a run
  from a shared Host Process is what ADR 0053 and ADR 0072 refuse.
- **Wait inside the hook.** Rejected. The daemon exits only after its hooks
  end, and Codex kills the hook at about 3 s, so a hook that waits for the
  daemon's exit sees it alive and is killed.
- **Defer every Codex `SessionEnd` by host exit.** Rejected. An `exec` exit
  and a standalone `/exit` end their host just as a restart does, so they
  would orphan runs that ended gracefully.
- **Leave every daemon `SessionEnd`'s runs for observation.** Rejected. An
  unload is the conversation ending, and its run would then stay bound to a
  live daemon until someone stopped it.

## Consequences

- Amends ADR 0015: a managed Codex daemon's `SessionEnd` ends its runs only
  once the daemon is seen to outlive it, and leaves them orphaned when the
  daemon is stopped or restarted.
- Amends ADR 0067: for the managed daemon, the positive evidence that ends a
  run is a `SessionEnd` followed by the daemon still running 10 s later. A
  daemon-hosted terminal's `/exit` still ends nothing until the unload.
- ADR 0072 is unchanged: Codex continues no run in any mode, and a restart's
  orphans recover through `work start` like a killed daemon's.
- An unloaded thread's run ends about 10 s after its `SessionEnd`, so it is
  listed for that long after the session record has ended. A thread resumed
  on the same daemon inside that window can find the run still bound to its
  Host Process, and look bound or carry it by Live Relocation, until the
  settler ends it.
- The settler relies on a daemon that is stopping running no `SessionEnd`
  until its turns have drained. Were a stop or restart to run an idle
  thread's `SessionEnd` while another turn held the daemon open past 10 s,
  that idle thread's run would end rather than be orphaned. The measured
  stop did not, and a restart with a running turn was not measured.
- A run the settler leaves is shown without a last activity time. Its ended
  hook record is removed at the `SessionEnd`, as ADR 0015 requires, and the
  replacement daemon's reloaded thread publishes nothing until its next turn.
- An unload followed within 10 s by a stop or restart reads as a stop, and
  its run is orphaned rather than ended.
- A settler that never runs, or dies before deciding, leaves the run as it
  was: orphaned once the daemon is gone, and otherwise listed against a live
  daemon until `work stop` ends it.
- A `work start` or `work stop` during the window wins. The settler ends only
  a run it can still compare unchanged, and a restarted run is newer than the
  `SessionEnd`.
- A thread the replacement daemon reloaded and no client holds unloads about
  60 s after the restart. Its `SessionEnd` from the replacement ends nothing
  of the orphan, which names the old daemon, and starts no settler.
- Another Codex release needs the measurement again before it is supported,
  through the [acceptance run](../../scripts/experiments/codex-356/run.mjs).
