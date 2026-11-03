---
status: accepted
date: 2026-11-03
---

# Observe a Codex Sub-agent's follow-up turn from the call that starts it

Dashpot lists a Sub-agent as working from its `SubagentStart` until its
`SubagentStop`
([ADR 0016](0016-hold-a-session-running-while-its-sub-agents-work.md),
[ADR 0067](0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)).
A Codex Sub-agent that has finished a turn can be given another. Its parent
thread calls `followup_task` under multi-agent v2, or `send_input` under v1.
That turn publishes a `SubagentStop` when it ends but no `SubagentStart` when
it begins. This was measured on 0.160.0 and 0.162.0
([#664 spike](../spikes/codex-worker-mail-eviction-spike.md)), and again on
0.166.0, where it held for a Sub-agent that was resident, unloaded, or
restored from disk
([#674 spike](../spikes/codex-followup-tool-hooks-spike.md#5-the-follow-up-turns-start)).
While such a turn runs, Dashpot does not list the Sub-agent, so:

- the Sub-agent does not hold its session running;
- Cleanup's `sub-agent` blocker does not cover it
  ([ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md));
- an Issue the Sub-agent is assigned to as a Worker does not read `running`
  ([ADR 0096](0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)).

The bundled `dashpot-execute-issues` skill lists this under its
[Known Dashpot gaps](../../src/dashpot/skills/dashpot-execute-issues/SKILL.md#known-dashpot-gaps)
([#674](https://github.com/ned2/dashpot/issues/674)).

On 2026-11-03 the maintainer decided on two directions. Dashpot infers the
follow-up from the parent's tool hooks, once a measurement shows what those
hooks carry, and the gap is reported upstream in parallel. This ADR decides
how far that inference widens what Dashpot observes. The measurement ran on
codex-cli 0.166.0 against a loopback model
([spike](../spikes/codex-followup-tool-hooks-spike.md),
[trace](../spikes/measurements/issue-674-codex-trace.jsonl)). It found:

- **The parent's hooks fire.** Each call fires `PreToolUse` on the calling
  thread. The `tool_name` is flattened with its namespace:
  `collaborationfollowup_task` or `multi_agent_v1send_input`. The
  `tool_input` is `{target, message}`, and `tool_use_id` pairs the call's
  two events.
- **`PostToolUse` fires only for an accepted call.** It comes once the task
  is queued, before the Sub-agent's turn ends: 43 to 61 ms after
  `PreToolUse` in the measurement. A call that failed fires `PreToolUse` and
  nothing more, and no later hook of the call or of its target reports the
  failure. The measured failures were:
  - for `followup_task`, an unknown path, an unknown ID, and the
    running-turn limit, reached in one setup only
    ([failed calls](../spikes/codex-followup-tool-hooks-spike.md#3-a-failed-followup_task));
  - for `send_input`, an unknown ID, a target that is not an ID, and a
    closed Sub-agent
    ([v1](../spikes/codex-followup-tool-hooks-spike.md#4-v1-send_input)).
- **Only an ID target identifies the Sub-agent in a hook.** A target that
  parses as a thread ID is used as one, and it equals the Sub-agent's
  `agent_id`. `send_input` accepts only an ID. Any other `followup_task`
  target is an agent path, such as `/root/worker_a` or `worker_a`, and no
  hook payload pairs a path with an ID. The only place Dashpot could read
  that pairing is the first line of the Sub-agent's transcript, Codex's
  `session_meta`
  ([target to `agent_id`](../spikes/codex-followup-tool-hooks-spike.md#2-from-target-to-agent_id)).
- **Matchers compare the flattened name.** The exact matchers
  `followup_task` and `send_input` selected nothing.
  `collaborationfollowup_task` and `multi_agent_v1send_input`, each
  subscribed on its own, selected exactly the calls of their tool. That a
  `|` joins exact names into one set is from Codex's source, not measured
  ([matchers](../spikes/codex-followup-tool-hooks-spike.md#6-matchers)).

## Decision

An accepted follow-up call whose target is a thread ID adds its target to
the session's live Sub-agents. Dashpot reads that from the calling thread's
hook payload and from nothing else.

- **One matched subscription.** The Codex integration adds `PostToolUse`
  with the exact matcher
  `collaborationfollowup_task|multi_agent_v1send_input`. This is the kind of
  matched subscription
  [ADR 0009](0009-hold-one-agent-run-per-session-across-worktrees.md)
  introduced for Claude Code's worktree tools. The publisher runs once for
  each accepted follow-up, not once per tool call, so the cost that
  [ADR 0006](0006-observe-agent-activity-at-turn-boundaries.md) declined
  does not arise. `PreToolUse` is not subscribed.
- **Two fields, used and not kept.** Of the event's tool fields, the
  publisher uses `tool_name` and `tool_input.target`. It never uses or
  records the follow-up's `message` or the call's `tool_response`.
- **An ID target adds a Sub-agent.** When the target parses as a thread ID,
  as Codex itself parses it, the store adds that ID to the session's live
  Sub-agents, run by the event's Host Process, as it adds a starting
  Sub-agent
  ([ADR 0107](0107-keep-a-sub-agent-listed-while-the-host-process-that-runs-it-lives.md)).
  - A Sub-agent already listed keeps its entry and its Host Process. This
    is the case of a follow-up that joins a turn already running, whose one
    `SubagentStop` ends both.
  - As a guard, not a measured case, a target naming the session's own
    thread changes nothing.
  - The hook record gains no field: the live set and its Host Process tags
    already hold all of this.
- **The listing ends as every Sub-agent's does:** at its `SubagentStop`,
  once its Host Process is gone, or by `dashpot work forget-subagents` on
  an ended record
  ([ADR 0095](0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md),
  [ADR 0097](0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md),
  ADR 0107).
- **A path target changes nothing.** Dashpot does not resolve a path to an
  ID through any of these:
  - the Sub-agent's transcript;
  - `spawn_agent`'s `task_name`;
  - the order of events.

  A follow-up addressed by path stays unobserved until Codex publishes the
  turn's start, or a path beside its ID, in a hook payload.
- **Otherwise an ordinary event of its session.** A follow-up from the root
  thread carries no `agent_id`, so it is a session-scoped event of the
  turn it falls in. Like any other session-scoped event in a running turn,
  it records the session as running, refreshes its last activity, and takes
  the publisher's usual routes for the session's Agent Run. It is not
  location evidence: a Codex session's only designated location evidence
  stays its `UserPromptSubmit`.
- **A follow-up from a Sub-agent.** Codex's source lets a Sub-agent follow
  up a Sub-agent of its own; this was not measured. Such a call's events
  carry the caller's `agent_id`. Its ID target joins the session's live set
  where the session already has a record. That includes an ended record
  kept for its Sub-agents (ADR 0095): there the call counts as a boundary,
  as a `SubagentStart` does, since a Sub-agent may outlive its session and
  still follow up its own. Otherwise the event stays child-scoped
  (ADR 0067).
- **v1 by the same rule.** A `send_input` is handled exactly like an
  ID-addressed `followup_task`. A v1 Sub-agent's own `UserPromptSubmit`
  stays a child-scoped event and is not made a boundary.
- **The bundled Lead addresses follow-ups by ID.** The
  `dashpot-execute-issues` skill already has each v2 Worker report its own
  `CODEX_THREAD_ID`, and its Lead assigns the Worker by that ID. The skill
  will tell the Lead to give `followup_task` that ID as the target, rather
  than the Worker's path. Its Known Dashpot gap then narrows to follow-ups
  addressed by path.
  - The 0.166.0 measurement first sent its follow-ups to an unloaded and to
    a restored Worker by path only. The change that implemented this ADR
    measured the ID-addressed case before the skill relied on it: an ID
    reached an evicted Worker and one restored from disk, as a path does
    ([unloaded Workers by ID](../spikes/codex-followup-tool-hooks-spike.md#7-dashpots-subscription)).

The change that implemented this ADR measured the subscription too, through
Dashpot's real publisher on 0.166.0: the joined exact names selected each
accepted follow-up's `PostToolUse` and nothing else, and the store listed
each ID-addressed Worker from that event until its `SubagentStop` and no
path-addressed one
([Dashpot's subscription](../spikes/codex-followup-tool-hooks-spike.md#7-dashpots-subscription)).
In the same change it amended ADR 0016, whose two boundaries gain this
third way of adding a Sub-agent, and updated the execute-issues skill and
its Known Dashpot gap.

## Considered options

- **Count the Sub-agent from `PreToolUse` until its `SubagentStop`, or
  until `PostToolUse` reports a failed call.** This is the rule the
  maintainer set out on 2026-11-03, before the measurement. Rejected: no
  `PostToolUse` reports a failed call. Every failed follow-up, such as a
  mistyped ID or one refused at the running-turn limit, would leave its
  target listed. Like a `SubagentStop` the harness never delivers, it would
  stay listed until its Host Process exits or a person runs
  `forget-subagents` on an ended record (ADR 0095, ADR 0107). Until then it
  would hold the session running and block Cleanup.
- **Count it from `PreToolUse`, and drop it when no `PostToolUse` with the
  same `tool_use_id` arrives within a timeout.** Rejected:
  - it needs a clock and a store of pending calls;
  - it shows a failed call as working until the timeout;
  - ADR 0016 declined to time a Sub-agent out on a clock.

  Starting at the accepted call costs only the interval between the two
  events, 43 to 61 ms in the measurement.
- **Resolve a path target from the first line of the Sub-agent's
  transcript.** `SubagentStart` and `SubagentStop` name the transcript, and
  its `session_meta` line pairs the ID with `agent_path`. Rejected on
  observation scope:
  - Dashpot observes hook payloads, processes, Git and its own stores. The
    transcript is Codex's private record of the conversation, not a
    published contract, and its format can change in any release.
  - Reading it would open a file that holds the conversation itself.
  - Dashpot would also have to keep a path map for Sub-agents that are no
    longer live, since a follow-up addresses a Sub-agent that has stopped.

  The bundled Lead already holds each Worker's ID, so addressing by ID
  covers the workflow Dashpot ships without any of this. The option is
  worth revisiting if Codex publishes `agent_path` in a hook payload.
- **Pair `spawn_agent`'s `task_name` with the `SubagentStart` that
  follows.** Rejected: matching by order is a guess, and concurrent spawns
  break it.
- **The matcher `followup_task$|send_input$`.** It would survive a rename
  of the namespace, and it was measured selecting exactly these calls.
  Rejected: it is unanchored at the front, so it would also match any tool
  whose name ends that way, such as an MCP server's, and that tool's target
  could be read as a Sub-agent. The exact set fails closed: a rename
  returns to today's gap and never adds a wrong Sub-agent.
- **`PostToolUse` with no matcher.** Rejected: it runs on every tool call,
  at the cost ADR 0006 measured.
- **Take a v1 Sub-agent's child-scoped `UserPromptSubmit` as its start.**
  Rejected as redundant: `send_input`'s target is always an ID, so one rule
  covers both versions. It would also add a third kind of boundary that
  only v1 publishes.
- **Wait for upstream alone.** Rejected by the maintainer's decision, which
  runs both directions. The request to Codex, which the maintainer posts,
  is what would cover follow-ups addressed by path.

## Consequences

- **What becomes visible.** A follow-up addressed by ID, and every
  `send_input`, lists its Sub-agent as working from the accepted call until
  its `SubagentStop`. In that time:
  - it holds the session running (ADR 0016);
  - the `sub-agent` blocker covers it (ADR 0066);
  - an assigned Worker's Issue reads `running` (ADR 0096).
- **What stays invisible.** A follow-up addressed by path is not observed.
  The skill's Known Dashpot gap keeps naming it until Codex publishes what
  this needs.
- **Re-running `integrate`.** Existing Codex installations report
  `PostToolUse(collaborationfollowup_task|multi_agent_v1send_input)` as
  missing in `dashpot integrate codex --status` until `integrate` is
  re-run. `--installed` reports that installation as partial. As with any
  new Codex hook, Codex asks the person to trust the new hook first
  ([installation](../installation.md#observe-agent-sessions)).
- **Ordering.** The listing depends on the accepted call's `PostToolUse`
  landing before the Sub-agent's `SubagentStop`.
  - Codex queues the task before firing `PostToolUse`, and the measurement
    saw `PostToolUse` first every time, but the source does not promise
    that order. The store applies boundaries in the order their writes
    land.
  - A stop that lands first would leave the Sub-agent listed, as an
    undelivered `SubagentStop` does: until its Host Process exits, or until
    `forget-subagents` on an ended record.
  - No guard is added. For a follow-up that starts a turn, the Sub-agent's
    whole turn, including a model request, would have to finish within one
    publisher run.
  - A follow-up that joins a turn already running could meet that turn's
    end sooner. How Codex schedules the joined task within the turn was not
    measured.
- **A rename or a changed contract.** Suppose a Codex release renames
  either tool or its namespace, stops firing `PostToolUse` for it, or
  changes how a target is parsed. Follow-ups then fall back to today's gap,
  and nothing is wrongly listed. Nothing checks for this automatically.
  Rerunning the
  [`codex-674` experiment](../../scripts/experiments/codex-674/run.mjs)
  and its verifier on the new release shows it.
