---
status: accepted
date: 2026-10-04
---

# Install an OpenCode worker agent that cannot move sessions

The `dashpot-execute-issues` skill
([#403](https://github.com/ned2/dashpot/issues/403)) has a lead session
launch a background Sub-agent, a worker, for each Issue it lands. Under
OpenCode v2 the [worker-mechanics experiment](../spikes/opencode-v2-worker-mechanics-spike.md#6-location)
for [#421](https://github.com/ned2/dashpot/issues/421) measured, on 2.0.22,
that a worker can call `opencode.session_move` with its lead's session ID.
That moved the lead, and Dashpot relocated the lead's Agent Run with it
([ADR 0090](0090-observe-opencode-v2-through-its-own-session-identity-and-event-order.md)).
The tool takes any session ID.

The same experiment measured where a permission rule
`{action: "*session_move", resource: "*", effect: "deny"}` takes the tool
away from a worker. A rule in the worker's own agent definition did, whether
that definition was in the global `opencode.json`, a global agent file, or a
project agent file. A rule on the lead's agent did not reach the lead's
workers, and the `subagent` tool takes no permissions. The maintainer
decided on [#422](https://github.com/ned2/dashpot/issues/422#issuecomment-5977174479)
that `integrate opencode` installs a worker agent with that deny.

## Decision

**The agent file.** `dashpot integrate opencode` installs one agent
definition, `agent/dashpot-worker.md`, in OpenCode's global configuration
directory, beside the managed plugin and skills of
[ADR 0079](0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md).
OpenCode names an agent file's agent after its path under `agent/`, so the
agent is `dashpot-worker`. Its frontmatter holds:

- a description saying that it is the agent the `dashpot-execute-issues`
  skill launches each worker as, and that it cannot move any session;
- `mode: subagent`, as #421's measured definition had it, so the agent is
  offered for Sub-agents only and never as a primary agent;
- `permissions` with the one deny of `*session_move`.

It sets no model, no tools, and no system prompt, so the user's model and
OpenCode's default prompt apply. The file has no body. OpenCode 2.0.22
decodes an agent file's trimmed body as the agent's `system`
([`config/plugin/agent.ts#L185`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/plugin/agent.ts#L185),
[`#L203`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/plugin/agent.ts#L203),
[`#L115`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/plugin/agent.ts#L115)).
A non-empty `system` replaces the model family's default prompt, and an
empty one keeps it, as two of OpenCode's own runner tests show
([`session-runner.test.ts#L1746-L1785`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/test/session-runner.test.ts#L1746-L1785)).

**The marker.** The frontmatter's first line is the YAML comment
`# dashpot-managed-agent: dashpot-worker`. OpenCode 2.0.22 parses an agent
file with `gray-matter`
([`config/markdown.ts#L6`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/markdown.ts#L6)),
whose YAML parser skips comments. Two other places were rejected:

- **A frontmatter key.** OpenCode knows only the native agent fields and
  `variant`
  ([`#L32`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/plugin/agent.ts#L32)).
  Any other key makes it decode the whole file as a v1 definition
  ([`#L186`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/plugin/agent.ts#L186),
  [`#L199`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/plugin/agent.ts#L199)),
  which was not what #421 measured the deny with.
- **A line in the body.** It would become the system prompt, and replace
  the default one.

A test checks that the shipped file has only native keys and no body.

**Ownership, repair and status.** The agent file follows the managed-marker
rule of ADR 0079 and the bundled skills:

- A file of that name without the marker is the user's own agent. `integrate`
  refuses to install over it, and `--remove` leaves it in place. The same
  holds for anything at that path that is not a file, such as a directory or
  a dangling symlink.
- Every skill's and agent's destination is checked before anything is
  written, so one refusal names every conflict and writes nothing.
- Rerunning `integrate` rewrites a managed file that differs from the shipped
  one, and leaves an identical one untouched.
- `--status` reports the agent as installed, update available, conflict, or
  not installed, as it reports each skill.
- `--remove` deletes the managed file, and leaves the `agent/` directory and
  every other file in it.
- Only that one path is checked. OpenCode also reads agents from `agents/`,
  `mode/` and `modes/`, from project `.opencode` directories, and from the
  `agents` map in
  `opencode.json`, and merges every definition of one name. A user's own
  `dashpot-worker` defined in one of those places is neither reported nor
  touched, and is merged with Dashpot's, which can undo the deny.

**Only OpenCode.** Claude Code and Codex install no agent file. Their
worker-mechanics experiments, for
[#419](https://github.com/ned2/dashpot/issues/419) and
[#420](https://github.com/ned2/dashpot/issues/420), found that a worker
cannot move its lead's session with any tool it is offered, so there is
nothing to deny.

**The consumer.** [ADR 0092](0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md) records the
`dashpot-execute-issues` skill, which launches every OpenCode worker as `agent: "dashpot-worker"` and says what to
do when the agent is not installed. The name is the contract between the
two.

## The deny's limit

The deny guards against a worker's mistake, not against a determined
process. It removes the tool from the model's tool path, and nothing else:

- a worker's shell can still move its lead through OpenCode's HTTP API
  (`POST /api/session/<lead>/move`), with the password any process of the
  user can read from the service registration;
- the same shell can run `opencode session delete`, or
  `opencode run --session <lead>` to ask the lead to act;
- the deny binds only a worker launched as `dashpot-worker`. Nothing makes
  the lead's model choose that agent. Enforcing it would take a `subagent`
  permission on the lead session, which the model cannot set without the
  HTTP API.

The agent file's comments say the same, so a user who reads it is not
misled.

## Considered options

- **The worker agent in the global `opencode.json` `agents` map.** It binds
  the worker, but `integrate` would edit a configuration file the user owns.
  ADR 0079 rejected that for the plugin, and a dedicated file can be owned
  and removed whole.
- **A deny in the global configuration's `permissions`.** Rejected: it
  would remove the tool from every session of the user, leads included.
- **A project agent file, `.opencode/agent/dashpot-worker.md`.** Rejected:
  it would have to be installed in every checkout and every Worktree, and
  `OPENCODE_DISABLE_PROJECT_CONFIG` hides it.
- **A deny on the lead's agent.** Rejected: measured not to reach the lead's
  workers.
- **Folding the agent into the bundled-skill registry.** Not adopted. A
  skill is a directory the integration owns whole, while an agent is one
  file in a directory OpenCode shares with the user's own agents, so what
  counts as vacant, what is removed and what is pruned all differ. The
  bundled agents are a second registry beside the skills instead. It shares
  their marker rule, their single check before anything is written, their
  status words, and an `agents=` keyword like `skills=`, and leaves the
  skill registry's shape unchanged.

## Consequences

- Upgrading Dashpot requires rerunning `dashpot integrate opencode`, which
  repairs the agent with the plugin and the skills.
- OpenCode 2.0.22 reloads its agents when a file under an agent directory
  changes
  ([`config/plugin/agent.ts#L66-L67`](https://github.com/anomalyco/opencode/blob/v2.0.22/packages/core/src/config/plugin/agent.ts#L66-L67)).
  #421's run never measured that directly. Its
  [retained trace](../spikes/measurements/issue-421-opencode-trace.jsonl#L491-L492)
  shows a running server listing an agent file written during the `guard`
  scenario, with no reload recorded in between. Where a server still lists a
  removed agent, `opencode reload` or a restart drops it.
- An edit to the managed file is undone by the next `integrate`, and
  `--status` reports it beforehand as an update available.
