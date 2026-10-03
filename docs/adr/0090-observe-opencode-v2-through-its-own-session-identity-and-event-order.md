---
status: proposed
date: 2026-10-02
---

# Observe OpenCode v2 through its own session identity and event order

Dashpot's OpenCode integration was designed for 1.18.30, across ADRs 0077 to
0081:

- one Publisher Generation per backend and directory owns publication there
  ([ADR 0077](0077-observe-opencode-through-one-publisher-generation-per-plugin-instance.md));
- a shell command gets a claim only once its own bootstrap is acknowledged
  ([ADR 0078](0078-give-an-opencode-command-a-claim-only-for-its-own-bootstrap.md));
- a retired generation's sessions keep their backend
  ([ADR 0080](0080-keep-a-retired-opencode-generations-backend-on-its-sessions.md));
- the TUI is its own backend, and a session never leaves the directory it was
  created in ([ADR 0081](0081-support-opencode-1-18-30-on-linux.md)).

OpenCode 2.0 replaced its server, its plugin interface and its event model.
[#393](https://github.com/ned2/dashpot/issues/393) chose to support v2 only,
and to refuse v1 rather than degrade on it. Its
[experiment](../spikes/opencode-v2-spike.md) measured OpenCode 2.0.22 on
Linux. Where it did not reach, the 2.0.22 source is cited, and named as the
source:

- **Hosting, measured.** The first client spawns one detached
  `opencode serve --service` per user, in `$HOME`. The service outlives that
  client, reparented to pid 1, and runs every session's shells as its direct
  children. It is named `opencode` under the curl install and `opencode.exe`
  under the npm one. No TUI is a shell's ancestor; only `--standalone` gives a
  client a private server of its own, `opencode serve --stdio`. A TUI of
  another release replaces the running service, and the replacement resumes
  its sessions
  ([experiment](../spikes/opencode-v2-spike.md#the-shared-service-and-its-plugin-instances)).
- **Plugin instances, measured.** A server sets up one plugin instance per
  OpenCode location, when work there first needs it, and every instance
  receives every event of the whole server. The execution events and
  `session.deleted` carry no location. An instance's cleanup is not a
  reliable signal:
  - evicting a busy location through OpenCode's debug route never cleaned its
    instance up;
  - SIGKILL runs nothing;
  - the hour's idle eviction cleaned one instance up before its own session's
    interruption reached it, while the other instances received it.

  See the [instance lifecycle](../spikes/opencode-v2-spike.md#plugin-instance-lifecycle)
  and the [idle eviction](../spikes/opencode-v2-spike.md#idle-eviction).
- **Event order, from the source.** Every event carries an id. Every event
  this ADR translates is durable, with the session's own sequence in its
  envelope
  ([`event.ts`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/schema/src/event.ts#L60-L71),
  [`session-event.ts`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/schema/src/session-event.ts#L45-L50)).
  Streaming deltas and `session.tool.progress` are ephemeral and carry none.
- **Shell identity.** Measured: for a shell the model runs, OpenCode sets
  `OPENCODE_SESSION_ID` to the session and `OPENCODE` to `1` after every
  plugin hook. From the source: the plugin's `create.before` hook is given
  the command and its environment, but no session
  ([`shell.ts`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/shell.ts#L255-L275),
  [shell tool](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/tool/plugin/shell.ts#L200-L214)).
  Measured: a user shell, run through the API route that the source says
  the TUI's `!` uses, runs that hook and keeps what it inherited; a terminal
  (PTY) runs no hook. `OPENCODE_PID` is gone
  ([shell identity](../spikes/opencode-v2-spike.md#shell-identity)).
- **Activity, measured.** `session.status` is gone.
  `session.execution.started` begins an execution, and `succeeded`, `failed`
  or `interrupted` ends it. The interruption reasons `user`, `shutdown` and
  `inactivity` were seen; the source adds `superseded`. After a running
  parent is deleted, a stray `started` for it can follow its
  `session.deleted`. A background child runs after its parent's execution has
  succeeded ([Sub-agents](../spikes/opencode-v2-spike.md#sub-agents)).
- **Moves.** Measured: `session.moved` keeps the session's id and its
  server, and changes where its later shells run. The model's move tool and
  the API move a session, and the source says a TUI changing directory does
  too ([moves](../spikes/opencode-v2-spike.md#moves)).
- **Forks, from the source.** A fork publishes `session.forked`, not
  `session.created`, and has no `parentID`: the session it was forked from is
  only its fork source
  ([projector](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/session/projector.ts#L147-L152)).
- **Idle eviction, measured.** When no session event has carried an OpenCode
  location for 60 minutes, OpenCode interrupts that location's executions
  with the reason `inactivity` and shuts the location down. A running shell
  does not renew the location, whether it prints or not, so its command is
  killed at about 61 minutes
  ([idle eviction](../spikes/opencode-v2-spike.md#idle-eviction)).
- **Deletion, measured.** `opencode session delete` goes through the
  service. No plugin loads in the CLI, and every live instance receives the
  deletion ([instance lifecycle](../spikes/opencode-v2-spike.md#plugin-instance-lifecycle)).

## Decision

### OpenCode v2 only

Dashpot supports OpenCode 2.0.22 on Linux once the acceptance run of
[#407](https://github.com/ned2/dashpot/issues/407) passes on it. Until then
OpenCode is unsupported, as
[ADR 0079](0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md)
kept it before 1.18.30's acceptance. v1 is refused, not observed:

- `dashpot integrate opencode` refuses to install while the `opencode` on
  PATH reports a 1.x release, and `--status` reports such a release as
  refused. v1 prints a bare `1.18.30`; v2 prints `opencode v2.0.22`.
- The managed plugin module also carries a v1 entry. It publishes nothing
  and gives every shell the reason that OpenCode v1 is refused, so a v1
  installed after `integrate` makes `work start` say so instead of failing
  silently.
- The v2 entry does nothing, neither publishing nor preparing shells, on a
  release whose major version, read from `ctx.app.version`, is not 2.
- The helper accepts only the v2 protocol. A 1.18.30 backend's sessions read
  gone once it exits, and a bound run on it is an Orphaned Agent Run, ended
  with `dashpot work stop --session`.
- Another 2.0.x release is installed and observed, and `integrate` and
  `--status` warn about it, as for the other harnesses' unaccepted releases.
  Because a TUI of another release replaces the service, `--status` also
  reports the running service's release, from its registration in
  `$XDG_STATE_HOME/opencode/service.json`, beside the release on PATH.

### The Host Process

An OpenCode session's Host Process is the server that runs its shells: the
shared service, or a `--standalone` client's private server. The adapter
recognises it as the nearest process in a command's ancestry named
`opencode` or `opencode.exe`. A client, the TUI included, is never recorded.

The Host Process is not exclusive to one session, and is never continued by
[ADR 0053](0053-continue-an-orphaned-agent-run-when-its-session-resumes.md),
as [ADR 0072](0072-keep-every-codex-host-process-non-exclusive.md) keeps
Codex. Its exit never ends a session. When it is replaced or stopped, its
bound runs are left orphaned, as a stopped or restarted Codex daemon's are
([ADR 0086](0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)).
The session recovers its Issue work with `work start` once it runs on the new
Host Process.

### The claim

On every shell, the plugin's `create.before` hook:

- deletes `OPENCODE_SESSION_ID` and `OPENCODE`, and blanks the claims
  ADR 0078 blanked: `DASHPOT_AGENT_SESSION`, Codex's and Claude Code's;
- sets `DASHPOT_OPENCODE_PID` to its own Host Process's pid;
- waits, at most 3 s, until the publications its Host Process has already
  admitted are written, so that a session's first command finds the
  session's record.

A command's OpenCode claim is its `OPENCODE_SESSION_ID`. It exists only when
`OPENCODE` is `1` and `DASHPOT_OPENCODE_PID` is set as well. Since the plugin
deleted both OpenCode variables, only OpenCode's own step for a model's shell
can have set them again. The pid must name the command's nearest OpenCode
Host Process, so variables inherited from another server never corroborate a
claim.

Issue opt-in validates the claim as
[ADR 0038](0038-isolate-native-agent-session-identities.md) does: the
identity's freshest hook record must exist, belong to OpenCode, and name that
Host Process. Opt-in also refuses:

- a child session's claim, with the reason `delegated-session`, because the
  helper records each child with its root;
- a session OpenCode has deleted.

ADR 0080's marker no longer refuses a claim. The claim is OpenCode's own,
not a generation's, and the record and Host Process already validate it.

There is no per-command bootstrap, no acknowledgment, and no generation in
the claim. Other shells are refused:

- A user shell keeps the pid but loses both OpenCode variables. It is refused
  as a shell the user ran rather than the agent.
- A terminal has none of the plugin's variables. It is refused as no agent's
  command.
- An inherited `OPENCODE_SESSION_ID` is never a claim, and an explicit
  `DASHPOT_AGENT_SESSION=opencode:<id>` stays refused.

### Publication

The plugin publishes OpenCode's own events, in OpenCode's own order:

- **Admission.** Each instance subscribes to its Host Process's events. The
  instances of one Host Process share a process-wide registry in the plugin.
  The registry admits each event once, by its id, from whichever instance
  receives it first. It also keeps each session's OpenCode location and
  parent. So any live instance publishes every session, and an instance's
  cleanup loses no event another instance receives.
- **Location and parent.** A session's OpenCode location and parent come
  from `session.created`, `session.forked` and `session.moved`; a shell
  event cannot say, since `create.before` names no session (measured by
  [#405](../spikes/opencode-v2-plugin-protocol-spike.md#findings)). A
  `session.forked` names a fork with no parent: its `parentID` field is the
  fork's source, never read as a parent. Failing those, the plugin reads the
  session with `ctx.session.get`, bounded at 500 ms, when its publication's
  turn comes. Unknown parentage is never read as a root, as before.
- **One root at a time.** The registry sends a root's publications, and
  those of the children it routes to that root, to the helper one at a time,
  in order, so no two of a session's writes ever overlap, even in different
  stores, and a child's event never overtakes its root's move. ADR 0078's
  bounds carry over: each root's queue admits 16 publications, a helper runs
  under a 3 s deadline, and at most 8 helpers run at once, for different
  roots. An
  event that a full queue refuses is lost, and the session's next accepted
  publication corrects its state.
- **Routing.** A publication goes to the hook store of the Worktree that
  holds the session's OpenCode location. A location outside
  every Project is not published, except for the move below.
- **Order.** The helper orders a session's publications by the session's
  durable sequence. The Publisher Record of a hook store keeps the highest
  sequence it accepted for each session, and the sessions OpenCode deleted.
  A publication at or below that sequence is stale or a duplicate, and
  writes nothing. This replaces ADR 0077's per-generation sequence and its
  active-generation fence.

### Translation

| OpenCode | Root session | Child session (`parentID`) |
| --- | --- | --- |
| `session.created`, `session.forked` | `SessionStart` | nothing |
| `session.execution.started` | `UserPromptSubmit` | `SubagentStart` on its root |
| `session.execution.succeeded`, `failed`, `interrupted` | `Stop` | `SubagentStop` on its root |
| `session.moved` | the location event the adapter designates | nothing |
| `session.deleted` | `SessionEnd` | `SubagentStop` on its root |

- **Forks.** A fork has no `parentID`, so it is a new root session and
  inherits no run, as under ADR 0077.
- **Incarnations.** A root's publication, or a child's on its root, writes
  `SessionStart` first when the store it is written to holds no record of the
  root, or holds one that names another Host Process: the session has begun
  there, or resumed in a new server. `session.moved` never writes
  `SessionStart`, and a child's `SubagentStop` writes nothing to a store
  with no record of its root. A move within one
  Git Repository is written at the new location's store before any later
  event of the session, so a reload, an eviction and such a move each begin
  no incarnation. A move to another Repository does: the session's first
  event in the new store writes `SessionStart`.
- **Deletion.** `session.deleted` records the deletion in its store's
  Publisher Record, and every later publication for the session is refused,
  the stray `execution.started` included.
- **Background children.** A background child holds its root running through
  its own execution events after the root's execution has succeeded
  ([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md)).
  The root's later execution is an ordinary turn.
- **Interruptions.** An interruption reads as waiting, whatever its reason,
  and the reason is kept in the hook's Event Log record. An `inactivity`
  interruption is reported the same way: Dashpot reports a turn's state, not
  its outcome (ADR 0077).

### Moves

The adapter designates a root's `session.moved` as location evidence, and
#405 names the hook event it is written as.

- **Within one Git Repository,** the helper writes the move at the new
  location's store, as the root's event, from the Host Process that served
  it. A bound run is carried there under
  [ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)'s
  eight conditions.
- **Anywhere else,** in another Repository or outside every Project, the
  helper writes the move at the old location's store, naming the new
  location. The session then no longer reads as at the old Worktree, and a
  bound run left there is reported as `work-session-elsewhere`. The
  session's later events go to the new location's store, or nowhere.

Who may trigger a move stays [#148](https://github.com/ned2/dashpot/issues/148)'s
decision. OpenCode is a candidate for its cooperative relocation, since
OpenCode's API moves an idle session without any client.

### Publisher Generations

A Publisher Generation still names one plugin instance, drawn when the
instance is set up. It no longer owns publication:

- **Registration.** Every instance's registration is accepted, and none is
  refused because a predecessor is still active.
- **Cleanup.** A generation's cleanup changes no session record unless the
  registry then holds no live instance of its Host Process. In that case,
  the root sessions recorded on that Host Process as running, or as holding
  Sub-agents, gain ADR 0080's marker and read unknown, in every store the
  registry routed them to. Nothing observes them
  any more, and the end of their execution may have reached no instance.
- **Clearing the marker.** Any accepted publication for a marked root, from
  its recorded Host Process, clears the marker, and forgets the Sub-agents
  the record held, since their ends may have been lost too. A live child's
  next event adds it again. So when a reload cleans every instance up before
  setting any up, its running sessions read unknown only until their next
  event.
- **Recovery on registration.** When a generation registers, the helper
  returns the root sessions recorded on its Host Process in the store of the
  registering instance's OpenCode location, with their recorded Sub-agents.
  The plugin reads each one with `ctx.session.get`. Only a definite answer
  that OpenCode has no such session is evidence: the plugin then publishes
  that session's deletion. A timeout or an error is never read as deletion
  (ADR 0067). This repairs a deletion that arrived while no instance was
  live. The session's running state is not recovered this way, because
  OpenCode's session record does not hold it.
- **Liveness.** A Host Process proven gone reads gone, as ADR 0080 decided.
  A live one never ends a session.

### Leaving a Worktree

Quitting a client no longer ends or moves anything. Cleanup's
`agent-session` blocker for OpenCode therefore names three ways out:

- move the session to another location;
- delete the session, with `opencode session delete <id>`;
- stop its Host Process, with `opencode service stop` or by quitting a
  `--standalone` client, which leaves every bound run on it orphaned.

### Deleting a bound session

Deletion is now published by the run's own Host Process, so
`opencode session delete` ends a bound run through the existing `SessionEnd`
reconciliation, run from any directory. This resolves
[#378](https://github.com/ned2/dashpot/issues/378), which closes as
superseded once [#405](https://github.com/ned2/dashpot/issues/405) delivers
it.

## Considered options

- **Support v1 and v2 together.** Rejected by the maintainer in #393. Only
  the maintainer uses Dashpot, so a clean break costs nothing.
- **Filter by location: each instance publishes only its own location's
  sessions,** as ADR 0077's pairing of backend and directory did. Rejected:
  - the execution events carry no location;
  - the idle eviction cleaned an instance up before its own session's
    interruption reached it, so that end would be lost;
  - the debug eviction of a busy location left two instances for one
    location.
- **Keep the generation fence, with the newest registration winning.**
  Rejected. OpenCode's durable sequence already orders one session across
  instances, generations and Host Processes, and a fence would only drop true
  events that a superseded instance still receives.
- **Retire a generation at its cleanup, as ADR 0077 does.** Rejected.
  Cleanup is unreliable, and every reload would mark all its sessions
  unknown while other instances still observe them.
- **Keep a per-command bootstrap claim.** Rejected:
  - `create.before` is given no session, and OpenCode sets
    `OPENCODE_SESSION_ID` only after the hook, so a bootstrap could not name
    the command's session;
  - every shell would pay for a helper call, for a claim OpenCode now gives
    itself.
- **Accept a user shell's or a terminal's inherited `OPENCODE_SESSION_ID`.**
  Rejected. An inherited value can name any session: the experiment's
  service passed a leaked one to every session created through the API, and
  to every Sub-agent. ADR 0038 requires a confirmed identity.
- **Refuse every 2.0.x release but the pinned one,** at installation or at
  runtime. Rejected:
  - when a TUI of another release replaces the service, every session would
    go unobserved in the middle of its work;
  - a patch release of OpenCode would make `integrate` refuse until Dashpot
    re-pinned;
  - the other harnesses warn about an unaccepted release rather than refuse
    it, and v1 is refused because the plugin cannot speak its protocol.
- **Recover a session's running state on registration.** Rejected.
  OpenCode's session record does not project `execution.started`, and a
  `shutdown` interruption sets no outcome, so "finished" could not be told
  from "never recorded".
- **Treat the idle eviction as the session's end, like a Codex unload.**
  Rejected:
  - shutting down an idle session's location publishes nothing about the
    session;
  - a reload shuts every location down the same way;
  - the session resumes at its next prompt, from any client.

## Consequences

- **Supersessions.** This ADR supersedes ADR 0078 and ADR 0081, and amends:
  - ADR 0077: generations no longer fence publication; OpenCode's sequence
    orders it; the Publisher Record is per hook store; the translation
    changes; and `session.moved` replaces the rule that a session stays in
    its instance's directory;
  - ADR 0079: the plugin is a `{id, setup}` default export with a v1 entry
    that refuses, and `integrate` and `--status` refuse v1 and report the
    running service's release;
  - ADR 0080: only the Host Process's last live instance sets the marker,
    any publication clears it, and it no longer refuses a claim; the way out
    of a Worktree changes; and the deletion limitation is answered.
- **Delivery.** Proposed here means decided but not yet delivered.
  - #405 marks ADR 0078 superseded, adds this ADR to ADR 0077's
    `amended-by`, and marks ADRs 0079 and 0080 amended.
  - [#406](https://github.com/ned2/dashpot/issues/406) marks ADR 0081
    superseded.
  - #407 marks this ADR accepted, and lists the modes its acceptance run
    passes.
  - Until #407, no document claims OpenCode support.
  - #405's and #406's bodies predate this ADR. Where they differ, this ADR
    rules: the claim carries no generation, and `integrate` warns, rather
    than refuses, on a 2.0.x release other than the pinned one.
  - The domain language describes 1.18.30 and v2 side by side until then.
    #405 and #406 remove the 1.18.30 rules from each entry.
- **Lost from 1.18.30.**
  - A command run with the TUI's `!` can no longer opt in.
  - Quitting the TUI no longer frees a Worktree.
- **The hour's limit.** OpenCode kills an agent's command that runs for
  more than about an hour with no session event at its OpenCode location.
  The hosting modes document must say so, since a long validation gate can
  reach it.
- **Lost signals.**
  - A session's running state is lost when its end reaches no live
    instance, or a full queue refuses it. It reads unknown when the last
    instance went, and otherwise stays as last published, until the
    session's next event.
  - A move a full queue refuses is not carried: the session's next event
    writes `SessionStart` at the new store, and a bound run stays behind as
    `work-session-elsewhere`.
  - A deletion a full queue refuses leaves the session as last published
    while its Host Process lives, until a generation registering at that
    store recovers it.
  - Clearing the marker forgets a background child that is still working,
    so its root can read waiting, and Cleanup's Sub-agent blocker
    ([ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md))
    misses the child, until the child's next event adds it again.
- **Cost.** A shell command no longer pays for a helper call. A server
  event costs at most one.
- **Measured by #405 before it is relied on.**
  - Instances share the process-wide registry. If they do not, each instance
    publishes every event, and the helper's sequence refuses the duplicates
    at the cost of one helper call per instance; the last-instance rule then
    needs another trigger, and a follow-up ADR.
  - A plugin's subscription carries the event id and the durable envelope.
  - `ctx.session.get`, and recovery on registration.
  - One plugin module can carry the v2 `{id, setup}` default export and a
    v1 entry that 1.18.30 loads, without either loader rejecting it. #406
    names the variable that carries the v1 refusal reason to a shell.
  - A fork reads as a new root session.
  - The TUI's change of directory is a `session.moved`.
  - A session moved to another Git Repository, or outside every Project.
- **Still unsupported,** as [#379](https://github.com/ned2/dashpot/issues/379)
  records:
  - the web, desktop and ACP clients;
  - `--server <url>`, and workspaces;
  - two Host Processes serving one session at once;
  - every operating system other than Linux.
