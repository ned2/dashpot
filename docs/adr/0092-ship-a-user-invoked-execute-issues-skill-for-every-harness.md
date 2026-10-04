---
status: accepted
date: 2026-10-04
---

# Ship a user-invoked execute-issues skill for every harness

[#403](https://github.com/ned2/dashpot/issues/403) asked Dashpot to ship a
second agent skill beside `dashpot-issue-work`: one that lands an **arc** of
Issues, an epic's sub-issues or a list chosen to unblock a goal, through
background Sub-agents that each take one Issue to an open PR in its own
Issue Worktree. Its starting point was the maintainer's personal
`execute-issues` skill, refined over a 22-PR arc. That draft relied on
Claude Code's mechanics alone, kept a private notes file per arc, carried a
profile of this repository's gates and gotchas, and required the
separately installed `code-review` skill.

[#418](https://github.com/ned2/dashpot/issues/418) made `integrate`
install every skill in its `BUNDLED_SKILLS` registry, each under its own
marker ([ADR 0079](0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md)
records the per-harness copies). Three experiments then measured what a
lead can rely on in each harness, against the same eight questions:

- [Claude Code 2.1.287](../spikes/claude-code-worker-mechanics-spike.md)
  ([#419](https://github.com/ned2/dashpot/issues/419));
- [Codex 0.160.0](../spikes/codex-worker-mechanics-spike.md)
  ([#420](https://github.com/ned2/dashpot/issues/420));
- [OpenCode 2.0.22](../spikes/opencode-v2-worker-mechanics-spike.md)
  ([#421](https://github.com/ned2/dashpot/issues/421)).

The maintainer settled the open questions in
[#403's decisions](https://github.com/ned2/dashpot/issues/403#issuecomment-5953159286)
and, for OpenCode, in
[#422's](https://github.com/ned2/dashpot/issues/422#issuecomment-5977174479).
This ADR records them as built in
[#422](https://github.com/ned2/dashpot/issues/422).

## Decision

**The name** is `dashpot-execute-issues`, matching `dashpot-issue-work`'s
prefix. The maintainer's personal `execute-issues` retires once this one is
installed, so the two never collide in a skill directory.

**User-invoked only.** The skill runs a long, mutating workflow, so the
model never chooses it. Its `SKILL.md` frontmatter sets Claude Code's
`disable-model-invocation: true` and OpenCode's
`metadata: {opencode/autoinvoke: false}`, and an `agents/openai.yaml`
beside it sets Codex's `policy: allow_implicit_invocation: false`. Each
experiment measured its own harness's flag hiding a skill from the model.
`integrate` copies the same files to every harness, so each parser must
accept the others' keys, and the released sources show they do:

- Codex 0.160.0's frontmatter struct ignores unknown keys, and reads from
  `metadata` only a `short-description`;
- Claude Code 2.1.287 lists `metadata` among its known frontmatter keys and
  keeps it as an object;
- OpenCode 2.0.22 ignores unknown keys, so it lists a skill with Claude
  Code's flag, as its experiment measured.

OpenCode's `skill` tool can still load a hidden skill by name, so the skill's
first line tells a model that loaded it unasked to stop.

**Every harness, with fallbacks.** The skill is written for Claude Code,
Codex and OpenCode v2, with a section per harness in
`references/harnesses.md` where the mechanics differ:

| | Claude Code | Codex | OpenCode v2 |
| --- | --- | --- | --- |
| Launch | background `Agent`, addressed by agentId | `spawn_agent`, addressed by task path | `subagent` with `background: true` and `agent: "dashpot-worker"` |
| Capacity | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | 3 workers by default, `[agents] max_threads` | no cap |
| Worker reports | `SendMessage` to `main` | `send_message` to `/root` (v2) | `opencode run --session <lead>` from a background shell |
| Lead learns of completion | a `<task-notification>` wakes it | it stays in its turn looping `wait_agent`, because Codex never wakes an idle lead | a `<subagent>` message wakes it |
| Resume | `SendMessage` to the agentId | `followup_task` | `subagent` with the `sessionID` |
| Worker's reviewer | the worker's own sub-agent | the worker's own spawn, within the limit | the lead dispatches it: nesting depth defaults to 1 |

The fallbacks the skill names:

- **Codex v1.** A lead on a model without multi-agent v2 polls with
  `wait_agent`, and its workers, which have no message tool, write
  mid-flight reports to a status file in their Worktree's Git directory.
  v1 holds 6 workers by default. The skill tells the lead to run on a
  catalog-v2 model.
- **Codex mail to a running worker.** The experiment measured `send_message`
  only toward the lead and toward a finished worker, so a Codex lead also
  writes each broadcast to a file in the worker's Worktree Git directory,
  which the worker reads before each gate run, commit and push.
- **A busy OpenCode lead.** A worker's `opencode run --session` blocks
  until the lead's turn ends, so it runs in a background shell, with the
  status file as the fallback.
- **A worker that cannot launch its reviewer** (OpenCode by default, Codex
  v1, or a full Codex session). The lead dispatches the reviewer as a
  separate worker, and only failing that does the worker review inline,
  saying so in its PR.
- **A missing `dashpot-worker` agent.** ADR 0093 has `integrate opencode`
  install that agent, whose deny of `*session_move` keeps a worker from
  moving its lead by mistake but not through OpenCode's HTTP API. When it is
  missing, the lead asks the user to rerun `integrate`, launches workers as
  `general` with a brief that forbids moving any session, and checks its own
  location with `work show` after each worker ends.
- **Endings that are not completions.** A worker stopped, killed, failed,
  cancelled or silent after an interruption is a blocker hand-back, and the
  lead resumes it or relaunches it on its brief. The lead avoids Claude
  Code's `TaskStop` and Codex's `interrupt_agent` mid-command, which publish
  no stop, and at a Claude Code `/exit` chooses "Exit and stop tasks" or
  "Stay".

**One Agent Session, one binding.** Every experiment measured that Dashpot
attributes a worker to its lead's Agent Session. The lead alone binds the
arc's Issue, through `dashpot-issue-work`, at the checkout it starts in, and
stays there while any worker runs. It alone creates Issue Worktrees with
`dashpot worktree create` and removes them with `dashpot worktree remove`,
and only once no worker is live, since
[ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)'s
`sub-agent` blocker refuses removal while any runs. Workers run no `work`
command: a Claude Code worker's `work start` at the lead's Worktree would
switch the session's Issue work. The domain language names the two roles
Lead and Worker.

**Run records on Issues.** The arc's record goes in comments on the epic,
or on a tracking Issue the lead opens for a list, in a shape
`references/run-records.md` defines: the arc map, each wave with its
strategies and hypotheses, each merge, each decision, and a close-out with
the timeline and ranked lessons. Lessons about the target repository are
filed as Issues against its agent instructions; lessons about the skill go
to the user. There is no private notes file, as
[AGENTS.md](../../AGENTS.md#tracking-and-notes) requires here and as a
shipped skill should not impose elsewhere. The comments also survive a lost
scratch directory.

**Self-contained.** The skill works in any GitHub repository configured as
a Dashpot Project. It depends only on `dashpot`, the `dashpot-issue-work`
skill `integrate` installs beside it, `git` and `gh`. Everything
repository-specific, the gates, review process, merge rules, unique
numbers and gotchas, the lead reads from the target repository's own
`AGENTS.md`, `CLAUDE.md`, README or `CONTRIBUTING` and quotes into each
worker's brief. The draft's profile of this repository does not ship. What
this repository's contributors still need from it moved to
[AGENTS.md](../../AGENTS.md#leading-parallel-issue-work). The skill names no
ADR, Issue, path or command of this repository: it states the behaviour
instead, and a test fails on any of them, on a link out of the skill's
directory, and on a skill `integrate` does not install.

**Known Dashpot gaps by name.** Four open Dashpot defects shape what the
lead must avoid. The skill names each by its behaviour, not its Issue, so
its workaround can be dropped once the installed Dashpot fixes it. A
harness's own behaviour behind a gap, such as Claude Code's `TaskStop`
publishing no stop, stays in `references/harnesses.md` after the gap
closes:

| Named in the skill | Issue | Workaround |
| --- | --- | --- |
| A relocated lead keeps a finished worker listed | [#427](https://github.com/ned2/dashpot/issues/427) | never move the lead while a worker runs |
| A Codex worker's shell names no session | [#428](https://github.com/ned2/dashpot/issues/428) | workers run no `work` command |
| A stopped Claude Code worker's wording | [#429](https://github.com/ned2/dashpot/issues/429) | read the interrupted-sub-agent wording as covering a stopped worker |
| An unloaded Codex lead drops its workers' blocker | [#431](https://github.com/ned2/dashpot/issues/431) | keep a client attached to the lead |

**Merge authority.** The lead merges only when the user grants merge
authority for the arc and the target repository's instructions do not
reserve merging for a person. Otherwise each worker's work ends with its
PR open, its validation recorded and CI green, and the user merges. The
lead never enables auto-merge. In this repository
[ADR 0089](0089-leave-the-pr-merge-to-the-operator.md) leaves the merge to
the operator, so a lead here merges only on the operator's grant for the
arc, which AGENTS.md records.

**A bundled reviewer.** Each worker gets an independent review before its
PR. When the target repository names a review process, the brief quotes
it. Otherwise the brief uses `references/reviewer.md`, a read-only prompt
reviewing the Spec and Standards axes against the Issue, the fixed review
base and the validation evidence, run by a fresh sub-agent of the worker
or by the lead as described above.

**No version line of its own.** `dashpot-issue-work` states the Dashpot
release it is written for and stops on a mismatch. The lead's first Dashpot
step is that skill's "Establish the workflow", and `integrate` installs and
updates both skills together, so its check also guards every command this
skill uses. A second version line would add two more places to bump each
release, and a second check that could only agree with the first.

## Considered options

- **Claude Code only.** Rejected by the maintainer: each harness has a
  usable mechanism or a named fallback, as the experiments measured.
- **A per-repository profile the skill reads by path**, as `code-review`
  reads `docs/agents/`. Rejected: the target repository's own instructions
  already hold its gates and gotchas, and a second file would drift from
  them.
- **Depending on the `code-review` skill.** Rejected: `integrate` does not
  install it, so the skill would fail in most repositories.
- **A private notes file**, kept beside the skill. Rejected: it is the
  private store AGENTS.md forbids here, it is lost with a machine, and no
  one else can read it.
- **Naming each gap by its Issue number.** Rejected: the skill ships to
  other repositories, where `#427` names something else.
- **A version line and check of its own.** Rejected, as above.

## Consequences

- `integrate` installs, updates, checks and removes the skill for every
  harness with `dashpot-issue-work`, as the registry does for any bundled
  skill, and reports it as the "Issue arc skill".
- The skill's per-harness facts are dated by the releases the experiments
  pinned. A re-pin that changes a mechanism updates
  `references/harnesses.md`, and a fix to one of the four gaps drops its
  entry from the skill and from the test that lists them.
- A change to `dashpot-issue-work`'s "Establish the workflow" or "Finish the
  engagement" headings must update this skill, which names them.
- ADR 0093 records the OpenCode worker agent this skill launches.
