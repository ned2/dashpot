---
status: research
date: 2026-10-06
---

# Harness support for leading an Arc of Issues

This note answers [Issue #641](https://github.com/ned2/dashpot/issues/641). It
asks what Claude Code, Codex and OpenCode each offer for landing an Arc of
Issues, and what their makers advise. It sets both against the bundled
[`dashpot-execute-issues` skill](../../src/dashpot/skills/dashpot-execute-issues/SKILL.md)
and its [harness reference](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md).

It builds on the Repository's records and does not repeat them:
- the Lead and Worker proposals: [prior art](../proposals/lead-worker-prior-art.md),
  [Claude Code evidence](../proposals/lead-worker-claude-code-evidence.md),
  [Codex evidence](../proposals/lead-worker-codex-evidence.md) and
  [OpenCode evidence](../proposals/lead-worker-opencode-evidence.md);
- the worker-mechanics experiments for
  [Claude Code](../spikes/claude-code-worker-mechanics-spike.md),
  [Codex](../spikes/codex-worker-mechanics-spike.md) and
  [OpenCode](../spikes/opencode-v2-worker-mechanics-spike.md);
- [ADR 0092](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md),
  [ADR 0093](../adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md),
  [ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md),
  [ADR 0124](../adr/0124-keep-sub-agent-workers-and-qualify-root-session-workers-per-harness.md),
  [ADR 0147](../adr/0147-keep-an-arcs-working-record-in-a-local-arc-ledger.md)
  and [ADR 0148](../adr/0148-let-workers-write-their-own-arc-ledger-files-and-commit-under-codexs-sandbox.md).

**How each claim is marked.**
- **Measured**: a linked experiment checked it.
- **Documented**: read from a harness's documentation, source at a named
  tag, release notes or `--help`, and not measured.
- **Observed**: seen in the Claude Code 2.1.291 session that wrote this
  note. That is not a pinned experiment.

Each finding about a harness also says whether it is **new**, **recorded**
(with a link), or **contradicts** a record. The gap analyses and the
cross-harness sections draw on those findings and carry no mark of their own
unless they add one.

## Releases researched

| Harness | Accepted ([README](../../README.md#supported-harnesses)) | Installed here | Latest upstream on 2026-10-06 |
| --- | --- | --- | --- |
| Claude Code | 2.1.287 | 2.1.291 | 2.1.291 ([changelog][cc-changelog]) |
| Codex | `codex-cli` 0.160.0 | 0.160.0 | 0.160.1 ([release][codex-01601]), a Windows MCP backport with nothing relevant here. 0.161 and 0.162 exist only as alphas ([releases][codex-releases]) |
| OpenCode | 2.0.22 | 2.0.22 | tag `v2.0.24`. v2 tags get no GitHub Release, so [`releases/latest`][oc-latest] is still v1.18.34 |

**What was read for each harness.**
- **Claude Code.**
  - The documentation pages at `code.claude.com/docs/en/<page>`, fetched on
    2026-10-06. They are unversioned and describe the latest release.
  - The `anthropics/claude-code` changelog, whose entries are tied to
    releases.
- **Codex.**
  - Source at tag [`rust-v0.160.0`][codex-tag].
  - The release notes, and `codex --help` from the installed 0.160.0.
  - The documentation at `learn.chatgpt.com`.
- **OpenCode.**
  - Source and documentation source at tag [`v2.0.24`][oc-tag].
  - The same files at `v2.0.22`, where a file differs between the two.
    `subagent.ts`, `file-access.ts`, `permissions.mdx` and `tools.mdx` are
    identical at both tags. Only `skills.mdx` changed, and it changed in
    `v2.0.23`: its copy there is identical to the one at `v2.0.24`.

## Summary

1. **No harness ships an Arc workflow that fits Dashpot's model.** These
   features all work around Issue Bindings, Issue Worktrees, or a person's
   merge:
   - Claude Code: agent teams, `/batch`, workflows and Projects;
   - Codex: managed worktrees and cloud tasks;
   - OpenCode: its worktree API.

   Sub-agent Workers in Dashpot Issue Worktrees remain the right shape, as
   [ADR 0124](../adr/0124-keep-sub-agent-workers-and-qualify-root-session-workers-per-harness.md)
   decided.
2. **Six harness-reference instructions differ from what each harness now
   does or from what was measured**, as the
   [table below](#stale-instructions-in-the-harness-reference) lists. The
   three that change how a Lead launches or invokes:
   - Claude Code's interactive fork mode removes the `run_in_background`
     parameter that the skill's launch line names.
   - Codex's `spawn_agent` defaults to a full-history fork. Every v2 Codex
     runner passed `fork_turns: "none"`, but the skill does not.
   - The OpenCode TUI's way to invoke a skill is now documented, and it
     changed in 2.0.23.
3. **Permission posture is the largest gap.** The skill says nothing about
   it.
   - **Claude Code.** Auto mode blocks these by default:
     - a Worker's force push;
     - a Lead's merge of a PR no human approved;
     - deleting a Remote Branch.

     Only the person can clear a block, and an approval must name the
     action.
   - **OpenCode.** OpenCode asks before any edit outside a session's
     location. A Worker's location is its Lead's checkout, so editing its own
     Issue Worktree raises an ask. The OpenCode experiment that showed
     Workers working in their Worktrees ran with every action allowed.
4. **A goal could keep a Lead going.**
   - Codex starts a new turn on an idle thread while a goal is active. That
     contradicts the skill's "Codex never starts a turn for an idle lead"
     for a Lead that sets a goal.
   - Claude Code's `/goal` is a session-scoped Stop hook.
   - Neither has been measured with Dashpot.
5. **Worker rules could be enforced by agent definition on every harness.**
   Only OpenCode does so today, and only for session moves.
6. **A Claude Code Lead isolated in a linked Worktree, and every Worker it
   launches, cannot run commands in the main checkout.** This is documented,
   and observed in this note's own session. It breaks the close-out's reflog
   check.
7. **The vendors' guidance mostly matches the skill.** Two points it lacks
   are a baseline check before a Worker's first edit, and the rule that a
   per-Worker model is chosen only on the user's direction.

## Claude Code

### Affordances and their limits

- **Fork mode removes `run_in_background`.**
  - Fork mode is on by default in interactive sessions from v2.1.232, and
    off in `-p` and the Agent SDK. With it on, every sub-agent runs in the
    background, and "Claude Code also removes the Agent tool's
    `run_in_background` parameter" ([sub-agents][cc-fork-mode]).
  - A call that names no type gets `general-purpose`. The `fork` sub-agent
    type, which inherits the whole conversation, comes only when the call
    asks for it. That is a Claude Code sub-agent, not the separate Agent
    Session the [domain language](../domain-language.md) calls a fork; below,
    "fork" means the sub-agent type.
  - Documented, and observed:
    - the Lead's Agent schema at 2.1.291 had no `run_in_background`, and a
      call that passed it ran in the background anyway;
    - this note's sub-agent was offered `description`, `prompt`,
      `subagent_type`, `model` and `isolation`, with no `name` and no `cwd`.
  - **Contradicts** the
    [Claude Code experiment](../spikes/claude-code-worker-mechanics-spike.md#tested-configuration-and-evidence-boundary)'s
    record of the 2.1.287 schema. Its runner keeps the schema from the first
    request it sees
    ([`run.mjs`](../../scripts/experiments/claude-419/run.mjs#L268)), which
    was not necessarily an interactive one.
- **A `name` can launch a teammate instead.**
  - Claude may pass `name` on its own initiative. With agent teams enabled,
    a named call "launches as a teammate instead, unless the call is a fork
    or passes `isolation` on the call itself". The teammate then runs in the
    main session's working directory ([sub-agents][cc-names]).
  - Documented, new. The 2.1.287 experiment recorded no `name` parameter.
- **Limits.**
  - At most 20 sub-agents run at once, from v2.1.217, set by
    `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` ([sub-agents][cc-concurrent]).
  - Nesting reaches three layers by default, set by
    `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` ([sub-agents][cc-depth]).
  - Documented. The cap's mechanism is recorded in the
    [Claude Code experiment](../spikes/claude-code-worker-mechanics-spike.md#1-launch),
    which did not measure its value.
- **Permission prompts and approvals.**
  - A background sub-agent's permission prompts surface in the main session.
    An answer that lasts beyond one call "applies … to the whole session,
    including your main conversation" ([sub-agents][cc-bg]).
  - "No message from any agent counts as your approval for a pending
    permission prompt", and only the person can grant one
    ([sub-agents][cc-messages]).
  - Documented. The routing of asks to the parent is
    [recorded](../proposals/lead-worker-prior-art.md#permissions-for-unattended-workers);
    the session-wide reach of a grant is new.
- **`SubagentHandback`.**
  - From v2.1.271, auto mode gives every local sub-agent other than a fork a
    `SubagentHandback` tool. The tool delivers the final report, and the
    classifier reviews the report before delivery. A sub-agent gets the tool
    even when its `disallowedTools` lists it ([tools reference][cc-tools]).
  - Measured: a sub-agent that ends with a text-only report is re-prompted
    three times to hand back, and the parent then takes one notification
    turn ([2.1.285 experiment](../spikes/claude-code-2-1-285-changes-spike.md#scenario-results);
    [verifier](../../scripts/experiments/claude-345/verify.mjs#L85)). The
    experiment does not record what that turn carried, so whether such a
    report reaches the parent is unmeasured.
  - This note's own sub-agent was offered the tool (observed).
- **Agent definitions.**
  - A definition's frontmatter takes `tools`, `disallowedTools`, `model`,
    `permissionMode`, `hooks`, `background`, `isolation` and more
    ([sub-agents][cc-subagents]).
  - "A `disallowedTools` entry with a specifier, such as `Bash(git push *)`,
    still removes the whole tool from the subagent". To block particular
    commands, use a `permissions.deny` rule, which applies to the main
    conversation too ([sub-agents][cc-disallowed]).
  - A frontmatter `PreToolUse` hook can check each Bash command. Hooks from
    `~/.claude/agents/` run without a trust step; a project agent's hooks
    need workspace trust ([sub-agents][cc-agent-hooks]).
  - In auto mode, "Any `permissionMode` in the subagent's frontmatter is
    ignored" ([permission modes][cc-pm-subagents]).
  - Documented, new.
- **Background commands have a time limit.**
  - In an unattended session, a Background Command stops after 30 minutes,
    or after the `timeout` passed with `run_in_background`, at most 2 hours.
    The limit "requires Claude Code v2.1.285 or later. Before v2.1.288, it
    applied in every session" ([tools reference][cc-bg-limit];
    [changelog][cc-changelog] 2.1.285 and 2.1.288).
  - So at the accepted 2.1.287, a Worker's background gate or `gh run watch`
    stops after 30 minutes unless it passes a longer `timeout`.
  - Separately, `Monitor` watches always have a deadline of at most 30
    minutes, and 10 in `-p` (changelog 2.1.271).
  - Documented. The limit is
    [recorded](../proposals/lead-worker-claude-code-evidence.md#risks-and-unknowns)
    for a Lead's own wait. The skill does not carry it, though the brief's
    gotcha "a background watch can exit early" matches it.
- **Worktree isolation.**
  - The isolation applies to a session that was started with `--worktree`,
    entered a worktree with `EnterWorktree`, or was resumed in one.
  - In such a session Claude Code blocks:
    - edits to files in the main checkout;
    - commands whose working directory is the main checkout;
    - git redirected into the main checkout, through `git -C`,
      `--git-dir`, `GIT_DIR` or a `cd`;
    - any command whose git use it cannot verify from the text. That check
      cannot be turned off.
  - "The same enforcement covers every subagent Claude spawns from the
    isolated session" ([worktrees][cc-isolation]).
  - Documented, new. A Bash `cd` to the main checkout is also reset ("Shell
    cwd was reset to …"), but that is Claude Code's general working-directory
    reset. It was
    [measured at 2.1.285](../agent-harness-server-client-reference.md#sub-agent-hooks-and-location-at-21285)
    for any `cd` outside the project, in a session with no isolation, and at
    2.1.286 in a session
    [launched in a linked Worktree](../agent-harness-server-client-reference.md#worktree-tools-between-issue-worktrees-at-21286).
    So it is not evidence for these checks.
  - Observed in this note's sub-agent, under an isolated Lead:
    - refused: `git rev-parse` in the main checkout, a `for` loop running
      `awk -v`, and a heredoc chained to a script run;
    - allowed: git in a sibling Issue Worktree, and plain separate commands.
- **`/goal`.**
  - `/goal` is "a session-scoped prompt-based Stop hook". The small fast
    model evaluates the transcript after each turn ([goal][cc-goal]).
  - The documentation lists "Working through a labeled issue backlog until
    the queue is empty" among its uses.
  - It does not change the permission mode, and its documentation says to
    run it in auto mode when unattended.
  - While a sub-agent or a Background Command runs, evaluation is skipped.
    The background work's result arrives as a new turn.
  - A check-in comes after 30 minutes of waiting, then at doubling
    intervals up to 2 hours. At most three idle check-ins run between
    prompts.
  - The goal is restored on resume. It is unavailable under
    `disableAllHooks` or in an untrusted workspace.
  - Documented, new.
- **Releases after the accepted one** ([changelog][cc-changelog]), all
  documented and new:
  - **2.1.288**: the background time limit applies only to unattended
    sessions, and `idle_prompt` no longer fires while background agents
    run.
  - **2.1.290**: fixes for background sub-agents "losing write and Bash
    access in their worktree after the main session enters or exits a
    different worktree", for resumed sub-agents losing their prompt cache
    after a message mid-run, and for plugin hooks reading an empty `answer`
    for a sub-agent that hands back in auto mode.

### Official guidance

- **Verification and review.**
  - "Give Claude a way to verify its work"
    ([best practices][cc-bp-verify]).
  - Add an adversarial review step whose reviewer flags "only gaps that
    affect correctness or the stated requirements"
    ([best practices][cc-bp-review]).
  - The skill's independent reviewer and its severity ranks
    ([reviewer prompt](../../src/dashpot/skills/dashpot-execute-issues/references/reviewer.md))
    already follow both.
- **Fan-out.** Pre-approve the tools a fan-out needs, with `--allowedTools`
  and `--permission-mode dontAsk`. "Refine your prompt based on what goes
  wrong with the first 2-3 files, then run on the full set"
  ([best practices][cc-bp-fanout]).
- **Agent teams.** "Start with 3-5 teammates", partition files between them,
  and expect that the team lead "can stop early … tell it to keep going"
  ([agent teams][cc-teams-size]).
  - The 3–5 ceiling is
    [recorded](../proposals/lead-worker-prior-art.md#human-limits-and-cost)
    and is in the skill's
    [set-up step 6](../../src/dashpot/skills/dashpot-execute-issues/SKILL.md#2-set-up).
- **Anthropic engineering.**
  - [Effective harnesses for long-running agents][eng-harness] (2025-11-26):
    - keep progress in a file, preferably JSON, which models "inappropriately
      change or overwrite" less than Markdown;
    - work on one feature at a time;
    - at the start of a session, run a basic test to catch undocumented
      bugs.
  - [Harness design for long-running apps][eng-design] (2026-03-24):
    - "Separating the agent doing the work from the agent judging it proves
      to be a strong lever";
    - "Every component in a harness encodes an assumption about what the
      model can't do on its own".
  - Both posts are documented guidance, new to the Repository's records.
  - The multi-agent research system and C compiler posts are
    [recorded](../proposals/lead-worker-prior-art.md#summary).

### Gap analysis

- **Launch.** The
  [Claude Code section](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#claude-code)
  says "`run_in_background: true`". In an interactive Lead the parameter is
  gone and is ignored. The section names no `subagent_type`, so an untyped
  call gets `general-purpose`, which is what the skill wants. Naming the
  type explicitly would guard against a model that picks the `fork` type,
  and leaving out `name` would guard against agent teams.
- **The hand-back.** The `{REPORTING}` text says "Your final message is your
  hand-back", and the brief template's final report says "Your last message"
  ([brief template](../../src/dashpot/skills/dashpot-execute-issues/references/brief-template.md#the-template)).
  In auto mode the hand-back is a `SubagentHandback` call, and the classifier
  reviews it.
- **Long commands.** Neither the skill nor the brief tells a Worker to give a
  long background gate or CI watch a `timeout` at 2.1.285–2.1.287.
- **Location.** The section says that whether a Worker's `EnterWorktree` or
  `ExitWorktree` can move a Lead already inside a linked Worktree was not
  measured. The documentation does not answer that, but it does document
  another limit on such a Lead, when Claude Code isolated it there:
  - An isolated Lead cannot run the close-out's reflog check on the main
    checkout
    ([close-out step 9](../../src/dashpot/skills/dashpot-execute-issues/SKILL.md#5-close-out)).
  - Neither the Lead nor its Workers can run any command there.
  - Isolation covers a session started with `--worktree`, entered with
    `EnterWorktree`, or resumed in a worktree. A Lead that bound in the main
    checkout is not isolated. The documentation does not list a session the
    user launched with plain `claude` in a linked Worktree. The working
    directory reset measured for such a session at 2.1.286 is the general
    reset [above](#affordances-and-their-limits), not these checks.
- **Permission posture.** See [below](#permission-posture-for-an-unattended-arc).

## Codex

### Affordances and their limits

- **`spawn_agent` (v2).**
  - It takes `message`, `task_name`, `agent_type`, `fork_turns`, `model`
    and `reasoning_effort` ([`multi_agents_spec.rs`][codex-spec]).
  - `fork_turns` "Defaults to `all`" ([`spawn.rs`][codex-spawn] falls back
    to `"all"`), so a Worker inherits the Lead's whole history unless the
    call passes `"none"` or a number.
  - The v2 tool description warns that `"none"` "may cause the agent to lack
    the context it needs to complete its task"
    ([`multi_agents_spec.rs`][codex-spec]). A Worker launched that way
    depends on a self-contained brief.
  - Documented. The parameters are
    [recorded](../spikes/codex-worker-mechanics-spike.md#1-launch); the `all`
    default and the warning are new.
  - Every v2 Codex runner passed `fork_turns: "none"`: codex-420 on its v2
    branch ([`run.mjs`](../../scripts/experiments/codex-420/run.mjs#L273)),
    [codex-448](../../scripts/experiments/codex-448/run.mjs#L220),
    [codex-460](../../scripts/experiments/codex-460/run.mjs#L250) and
    [codex-637](../../scripts/experiments/codex-637/run.mjs#L208). So the
    measured v2 Workers started without the Lead's history. The v1 runners,
    [codex-160](../../scripts/experiments/codex-160/run.mjs#L123) and
    [codex-161](../../scripts/experiments/codex-161/run.mjs#L181), pass only
    a `message`. v1 has no `fork_turns`, and its `fork_context` starts a
    Worker with only its prompt when omitted. The skill's v2 launch line
    does not pass `fork_turns`.
- **Model overrides.**
  - The multi-agent prompt says: "Full-history forks (`fork_turns` omitted
    or `"all"`) inherit the parent model and reasoning effort and do not
    accept overrides. Only set `model` or `reasoning_effort` when explicitly
    requested by the user, applicable `AGENTS.md` instructions, or skill
    instructions; when doing so, set `fork_turns` to `"none"` or a positive
    integer string." ([`multi_agent_instructions.rs`][codex-instr], line 8).
  - This note found no code that refuses an override:
    [`child_config.rs`][codex-child] applies the requested model before it
    looks at the fork mode. So the rule reads as a prompt instruction.
  - Documented, new.
- **The spawn tools' own guidance** differs between the two tool sets.
  - **v1.** `spawn_agent_tool_description` in
    [`multi_agents_spec.rs`][codex-spec], which only the v1 tool uses, says:
    - spawn only when the user, AGENTS.md or a skill asks;
    - give each delegated task a disjoint write set;
    - make subtasks "concrete, well-defined, and self-contained";
    - "Call wait_agent very sparingly".
  - **v2**, which the skill uses. Its tool description
    (`spawn_agent_tool_description_v2`) explains task names and the
    `fork_turns` warning above. The multi-agent instructions
    ([`multi_agent_instructions.rs`][codex-instr]) add:
    - "When calling `wait_agent`, prefer longer waits (minutes) to avoid
      busy polling";
    - "All agents share the same directory";
    - the model-override rule above.
  - Documented, new. The shared working directory is
    [measured](../spikes/codex-worker-mechanics-spike.md#6-location).
- **Concurrency.** The canonical key is
  `agents.max_concurrent_threads_per_session`, and `agents.max_threads` is a
  legacy alias ([`key_aliases.rs`][codex-alias];
  [subagents docs][codex-subagents]). Documented, and recorded in the
  [Codex experiment](../spikes/codex-worker-mechanics-spike.md#1-launch).
  The skill's "Raise the limit with `[agents] max_threads`" names the alias.
- **Custom agents.**
  - TOML files under `~/.codex/agents/` or `.codex/agents/` declare `name`,
    `description` and `developer_instructions`, and may override `model`,
    `model_reasoning_effort`, `sandbox_mode` and more
    ([subagents docs][codex-subagents]).
  - `spawn_agent`'s `agent_type` selects one. "The selected role applies
    regardless of how much parent history is inherited"
    ([`multi_agents_spec.rs`][codex-spec]), and
    [`child_config.rs`][codex-child] applies a v2 role to full-history forks
    too.
  - Documented, new.
- **Sandbox and approvals.** "Subagents inherit your current sandbox
  policy". In the CLI, "approval requests can surface from inactive agent
  threads" ([subagents docs][codex-subagents]).
  - Documented. The sandbox inheritance is
    [measured](../spikes/codex-workspace-write-workers-spike.md); approvals
    under other policies are open in
    [#639](https://github.com/ned2/dashpot/issues/639).
- **Goals.**
  - With a goal active, the goal extension's `on_thread_idle`
    ([`extension.rs`][codex-goal-ext]) calls `continue_if_idle`, which calls
    `start_turn_if_idle` with `turn_trigger: "goal"`. Codex therefore
    starts a new turn on an idle thread ([`runtime.rs`][codex-goal-runtime]).
  - The goal tool says: "Create a goal only when explicitly requested by the
    user or system/developer instructions" ([`spec.rs`][codex-goal-spec]).
  - A goal becomes `blocked` in two ways:
    - **The model sets it.** The tool tells the model to set `blocked` only
      after "the same blocking condition has recurred for at least three
      consecutive goal turns" ([`spec.rs`][codex-goal-spec]).
    - **The runtime sets it.** `stop_active_goal_for_turn` blocks the goal
      on a turn error, on repeated empty responses, and when execution is
      unavailable. A usage limit sets it `usage_limited` instead
      ([`runtime.rs`][codex-goal-runtime]). The 0.155 notes record the
      empty-response rule as "Block goals after three empty automatic
      continuation turns" (openai/codex#44320, [0.155.0][codex-0155]).
  - The continuation prompt counts a "verified wait", one that "polls a
    specific process, session, job, or tool handle confirmed live now", as
    progress, and asks for a completion audit
    ([`continuation.md`][codex-goal-cont]).
  - Release notes: 0.155 says "active goals can recover after daemon
    restarts" ([0.155.0][codex-0155]).
  - Documented, new.
  - This **contradicts**, for a Lead with a goal:
    - the [Codex experiment](../spikes/codex-worker-mechanics-spike.md)'s
      "Codex never starts a turn in an idle lead", which was measured
      without a goal;
    - the skill's "Stay in your turn".
- **Release notes after the records.**
  - 0.154 removed `codex mcp-server` and added experimental managed
    worktrees, `--worktree` and `/worktree` ([0.154.0][codex-0154]).
  - 0.156 enabled worktrees by default (openai/codex#44870,
    [0.156.0][codex-0156]).
  - `codex review --base <BRANCH>` reviews non-interactively (`codex review
    --help`, 0.160.0).
  - Documented. Managed worktrees are
    [recorded](../design-research/integration-frequency-and-parallel-branches.md#openai-codex);
    the `mcp-server` removal, the new default and `codex review` are new.

### Official guidance

- **Long-running work** ([long-running work][codex-long]):
  - state a goal as outcome, constraints and verification;
  - "Start a separate chat when another task can run independently";
  - "avoid letting two chats change the same files";
  - use Git worktrees for parallel coding chats.
- **Best practices** ([best practices][codex-bp]):
  - "Keep approval and sandboxing tight by default, then loosen permissions
    only for trusted repos or specific workflows once the need is clear";
  - run checks and review the work before accepting it;
  - use subagents "to offload bounded work from the main thread".
- **Subagents.** Be cautious with "parallel write-heavy workflows"
  ([subagents docs][codex-subagents]).

All documented. The write-heavy caution is
[recorded](../proposals/lead-worker-prior-art.md#mechanism-sub-agents-or-independent-sessions);
the rest is new. The skill already follows all of these: an Issue Worktree
per Worker, file ownership in the wave block, and gates and review before
the PR.

### Gap analysis

- **Launch** ([Codex section](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#codex)):
  "`spawn_agent` with a `task_name` and a `message`". By default each Worker
  forks the Lead's whole history.
  - That spends each Worker's context on the Lead's.
  - It contradicts the skill's "Spend your context on decisions. Workers
    read the code", and its self-contained briefs.
  - The prompt says full-history forks take no model override, so by
    instruction the default rules out a per-Worker model. No code enforces
    that ([above](#affordances-and-their-limits-1)).
  - It is not what the v2 Codex runners measured.
- **Capacity.** The section names the legacy alias `[agents] max_threads`.
- **Stay in your turn.** A goal is a candidate replacement for the wait-loop
  discipline, but four things about it are unmeasured:
  - how Dashpot's hooks see a `goal` turn;
  - whether a Lead waiting in `wait_agent` across goal turns is set
    `blocked`, by the model or by the runtime;
  - what an unloaded Lead does
    ([#492](https://github.com/ned2/dashpot/issues/492)). By source, a goal
    runs only in a loaded thread, so a goal is not a fix for #492;
  - whether a skill's instruction counts as the explicit request a goal
    needs ([below](#goals-that-keep-a-lead-going)).
- **Reviewer.** `codex review --base` from a Worker's shell would use no
  thread slot. It would, however, be its own Agent Session in the Worktree,
  like the `codex exec` case the section already describes. Not measured,
  and not proposed here.

## OpenCode

### Affordances and their limits

- **`subagent`.**
  - It takes `agent`, `description`, `prompt`, `model`, `sessionID` and
    `background` ([`subagent.ts`][oc-subagent]).
  - The `model` description reads "NEVER set this unless the user
    explicitly asks for a particular model or variant".
  - A background launch tells the parent "DO NOT sleep, poll for progress,
    ask the subagent for status, or duplicate this subagent's work; avoid
    working with the same files or topics it is using".
  - New children "start with fresh context".
  - Nesting is limited by `experimental.subagent_depth`, default 1.
  - Documented. Launch and depth are
    [measured](../spikes/opencode-v2-worker-mechanics-spike.md#1-launch-and-concurrency);
    the `model` input is new.
- **Default permissions** ([permissions][oc-permissions]).
  - Every agent starts from a base policy:
    - allow everything;
    - ask for `external_directory`;
    - ask for `.env` reads.
  - On top of the base policy:
    - the shipped `general` agent "Denies questions and launching
      subagents";
    - the `build` agent allows questions.
  - The `dashpot-worker` agent
    ([`dashpot-worker.md`](../../src/dashpot/agents/dashpot-worker.md))
    denies only `*session_move`, so it allows `question`.
  - Documented. The base policy is
    [recorded](../spikes/opencode-v2-background-permissions-spike.md#opencode-run-under-default-permissions);
    the comparison with `general` is new.
- **Paths outside a session.**
  - "A path outside both the active Location and its non-root project
    worktree needs `external_directory` approval". (OpenCode's location is
    its own term, not Dashpot's.) The shell also checks its
    working directory, and the directories its scanner infers from the
    command ([permissions][oc-permissions]; [`file-access.ts`][oc-fileaccess]).
  - A child session is created "at its parent's location"
    ([`session.ts` protocol][oc-session-api]).
  - So a Worker's edit in a sibling Issue Worktree, or its
    `cd <worktree> && …`, needs approval under the defaults.
  - Documented, new.
  - This **contradicts** the reading that the
    [OpenCode experiment](../spikes/opencode-v2-worker-mechanics-spike.md#6-location)
    covers default use. Its fixture configuration allowed every action
    ([`run.mjs`](../../scripts/experiments/opencode-421/run.mjs#L354)).
  - [#467's comment](https://github.com/ned2/dashpot/issues/467) asks the
    same question for a ledger write.
- **`opencode run`.**
  - Its own comment says "Subagents run in child sessions; their asks and
    questions belong to this run too". Without `--auto` it rejects each such
    ask and cancels each question ([`noninteractive.ts`][oc-run]).
  - Documented. This is
    [measured](../spikes/opencode-v2-background-permissions-spike.md#opencode-run-under-default-permissions),
    and it is in the skill.
  - [Recorded](../proposals/lead-worker-opencode-evidence.md#affordances-beyond-the-existing-experiments)
    but not in the skill: on the managed service it copies the caller's
    environment into the session it targets.
- **The session API.**
  - `session.synthetic`, which takes `delivery` `steer` or `queue`;
    `session.list` with `parentID`; and `session.interrupt`
    ([`session.ts` protocol][oc-session-api]).
  - Documented. Recorded and partly measured for root sessions in the
    [OpenCode evidence](../proposals/lead-worker-opencode-evidence.md#affordances-beyond-the-existing-experiments)
    and the [#479 experiment](../spikes/root-session-workers-spike.md#opencode-2022).
- **Skills.**
  - At 2.0.22 the docs list a `slash` field that "hide[s] the skill from
    interactive command catalogs" ([2.0.22][oc-skills-22]).
  - From 2.0.23 that field is gone, `disable-model-invocation` has "the same
    effect as `opencode/autoinvoke: false`", and "To load a skill yourself,
    mention it in your prompt as `@skill-id`" ([2.0.23][oc-skills-23]). The
    page is unchanged at [2.0.24][oc-skills-24].
  - Documented, new.
- **Shell.** "Set `workdir` instead of putting `cd` in the command". A
  foreground command times out after two minutes ([tools][oc-tools]).
  Documented. `workdir` is
  [measured](../spikes/opencode-v2-worker-mechanics-spike.md#6-location),
  and the timeout is in the skill; the advice to prefer `workdir` is new.
- **Worktree API.** `worktree.create` takes `from` (a source directory),
  `branch`, `directory` and `name`, and no base commit. By default it creates
  the worktree under the server's data directory, then runs the project's
  setup script ([`worktree.ts` schema][oc-worktree-schema];
  [`worktree.ts` protocol][oc-worktree-api]). Documented, new.

### Official guidance

The v2.0.24 documentation source has no guidance on working through a
backlog or an epic. Its tool-level guidance is this:

- background sub-agents for independent work, and no polling
  ([`subagent.ts`][oc-subagent]);
- a complete prompt for a new child;
- `workdir` rather than `cd`;
- Background Commands for long work ([tools][oc-tools]);
- narrow shell allow-lists rather than patterns ([permissions][oc-permissions]).

The research report's community sources (oh-my-opencode and its relatives)
are not cited here: they are not primary sources.

### Gap analysis

- **Worker asks**
  ([OpenCode section](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#opencode)).
  - The section warns that a report's `opencode run` rejects asks. It does
    not say that, under default permissions, a Worker's every edit in its
    Issue Worktree asks.
  - `dashpot-worker` allows `question`. A Worker's question waits for a
    person, and a running report cancels it. `general` denies it.
- **Invoke.** "How the TUI invokes a skill was not measured" is now
  documented:
  - from 2.0.23, by an `@dashpot-execute-issues` mention;
  - at 2.0.22, through the interactive command catalog that `slash` governs.
- **Working directory.** The skill's `cd <path> && …` rule is measured to
  work. OpenCode's own advice is `workdir`. Either way an outside directory
  needs `external_directory` approval.
- **Worker reports.** The environment copy into the Lead's session is
  recorded but not assessed in the skill.

## Across harnesses

### Permission posture for an unattended Arc

The skill never states a posture. Each harness's default makes some of the
Arc's actions wait for a person.

- **Claude Code auto mode**
  ([permission modes][cc-pm-blocked]; [auto mode config][cc-am-config]).
  Auto mode is the starting mode of an interactive terminal session
  ([recorded](../proposals/lead-worker-claude-code-evidence.md#permission-posture-and-the-commit-instruction)).
  - **Blocked by default.** "Force push", and "Merging a pull request no
    human has approved". The default Git Destructive rule also covers
    "deleting remote branches". All documented, new.
  - **What these hit in this Repository.** A Worker's force-push after the
    rebase [AGENTS.md](../../AGENTS.md#integration-and-rebase) authorises.
    A Lead's merge under merge authority. The close-out's
    `--delete-remote-branch`.
  - **Only the person can clear a block**
    ([approvals][cc-pm-approvals]).
    - An approval must "name the action and its specifics". It "covers the
      destructive action you named, so a later action is blocked again
      unless you granted the approval as standing". To stop approving a
      routine pattern one action at a time, the page points to
      `autoMode.allow`.
    - `autoMode` is read from `~/.claude/settings.json`, managed settings
      or `--settings`, never from a project's settings.
    - A boundary stated in conversation "can be lost if context compaction
      removes the message".
    - Three blocks in a row, or 20 in a session, pause auto mode.
  - **What the classifier sees.** It reads CLAUDE.md, so AGENTS.md's rebase
    authorisation reaches it through the import. Whether that clears a force
    push is unmeasured.
  - **Workers.** A Worker cannot be approved by its Lead. Its prompts
    surface in the Lead's session ([sub-agents][cc-bg]). The classifier
    checks a sub-agent at three points ([permission modes][cc-pm-subagents],
    "How auto mode handles subagents"):
    - "Before a subagent starts, the delegated task description is
      evaluated, so a dangerous-looking task is blocked at spawn time". A
      brief that tells a Worker to force-push or merge could be blocked at
      launch.
    - While it runs, each action goes through the same rules as in the
      parent.
    - When it finishes, the classifier reviews its work and report. A
      flagged report "is still delivered, prepended with a security
      warning".
  - All documented, new.
- **Codex.** Workers inherit the Lead's sandbox and approval policy, and an
  approval from a Worker surfaces in the CLI
  ([subagents docs][codex-subagents]). Recorded: the skill's sandbox check
  ([ADR 0148](../adr/0148-let-workers-write-their-own-arc-ledger-files-and-commit-under-codexs-sandbox.md))
  and [#639](https://github.com/ned2/dashpot/issues/639) cover it.
- **OpenCode.** `external_directory` asks for every Worker's Issue Worktree,
  as [above](#affordances-and-their-limits-2). An "always" reply saves a
  project-scoped rule ([permissions][oc-permissions]). Measured: such a rule
  also answered the Lead's asks at the main Worktree
  ([#479 experiment](../spikes/root-session-workers-spike.md#opencode-2022);
  recorded in the
  [OpenCode evidence](../proposals/lead-worker-opencode-evidence.md#affordances-beyond-the-existing-experiments)).

The vendors agree on a posture set before the work starts, rather than
answers given mid-run:
- Claude Code: pre-approved tools with `dontAsk`, or auto mode
  ([best practices][cc-bp-fanout]);
- Codex: "tight by default" ([best practices][codex-bp]).

### Workers inheriting the Lead's context

| Harness | What a Worker starts with | Source |
| --- | --- | --- |
| Claude Code | A `general-purpose` sub-agent gets only its prompt and the project's CLAUDE.md. The `fork` sub-agent type would inherit the whole conversation | [sub-agents][cc-fork-mode] |
| Codex | The whole history, unless `fork_turns` is `"none"` or a number | [`spawn.rs`][codex-spawn] |
| OpenCode | Fresh context, always | [`subagent.ts`][oc-subagent] |

Only Codex's default differs from the skill's intent, and only Codex's
measured configuration differs from the skill's launch instruction. Codex's
own tool description warns that a Worker launched without history "may
cause the agent to lack the context it needs"
([`multi_agents_spec.rs`][codex-spec]). On every harness, then, the brief
must carry everything a Worker needs, as the skill's self-contained brief
already intends.

### Enforcing Worker rules by agent definition

The brief's ground rule 2
([brief template](../../src/dashpot/skills/dashpot-execute-issues/references/brief-template.md#the-template))
leaves these to the Lead: "every Dashpot `work` command, harness integration
commands, creating or removing any Worktree or Branch, moving any agent
session, installing git hooks, and merging or enabling auto-merge". That is
prose.

- **OpenCode.** `dashpot-worker` enforces the session-move part
  ([ADR 0093](../adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)).
- **Claude Code.** A user-level agent could do the same. It could drop
  `EnterWorktree` and `ExitWorktree` with `disallowedTools`, and refuse
  `dashpot work`, `gh pr merge` or `worktree` commands with a frontmatter
  `PreToolUse` hook. Such a hook runs without a trust step
  ([sub-agents][cc-agent-hooks]).
- **Codex.** A `.codex/agents/` role could carry the rule in its
  `developer_instructions` and set `sandbox_mode`
  ([subagents docs][codex-subagents]).

Dashpot already refuses a Worker's `work start` elsewhere, but not its
`work stop` ([AGENTS.md](../../AGENTS.md#issue-work-lifecycle)).

[ADR 0093](../adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md#decision)
says Claude Code and Codex need no agent file, because "there is nothing to
deny". That holds for session moves, but not for the rest of ground rule 2.
New; documented only.

### Goals that keep a Lead going

- **Codex.** A goal starts turns on an idle thread (documented, above).
- **Claude Code.**
  - A Lead already gets a new turn when a background Worker finishes
    ([measured](../spikes/claude-code-worker-mechanics-spike.md#3-completion)).
  - What `/goal` adds is a check against stopping early, as the agent-teams
    documentation warns a team lead may.
  - Its evaluator is a Stop hook, and Dashpot records turn state from Stop.
    How the two interact is unmeasured.
- **Both harnesses.**
  - A goal's completion condition must match the skill's end, which is PRs
    open and green unless the user granted merge authority. Merged PRs would
    be the wrong condition.
  - Codex creates a goal only on explicit instruction. Whether a skill
    counts as that instruction is unmeasured.

### Stale instructions in the harness reference

| Instruction | Now | Status |
| --- | --- | --- |
| Claude Code launch with `run_in_background: true` | Removed in an interactive Lead by fork mode | Documented; observed |
| Claude Code "Your final message is your hand-back" | `SubagentHandback` in auto mode | Documented; measured |
| Codex launch without `fork_turns` | Full-history fork; the v2 runners measured `"none"` | Documented |
| Codex `[agents] max_threads` | Legacy alias of `max_concurrent_threads_per_session` | Documented; recorded |
| Codex "never starts a turn for an idle lead" | Contradicted by source with an active goal; unmeasured | Documented |
| OpenCode "How the TUI invokes a skill was not measured" | `@skill-id` documented from 2.0.23 | Documented |

[#438](https://github.com/ned2/dashpot/issues/438) carries the experiments'
findings into the general harness reference, not into the skill's.

### Baseline checks

- **The guidance.**
  - Anthropic's [long-running harness post][eng-harness] starts every
    session with a basic test, so that the agent finds bugs it did not
    cause.
  - Codex's [best practices][codex-bp] say to run the relevant checks
    before accepting work.
- **What the skill does.** The brief runs the gates only before a commit
  ([brief template](../../src/dashpot/skills/dashpot-execute-issues/references/brief-template.md#the-template)).
  A Worker that meets a failure cannot tell whether its base already had it,
  except through the flaky-check gotcha.
- **The option.** A cheap baseline gate at `{BASE}`, before the first edit,
  would settle that. Its cost is cores that sibling Workers share.
- New; documented guidance only.

### Per-Issue model choice

All three harnesses let a Lead choose a Worker's model:
- Claude Code: the Agent `model` parameter, observed;
- Codex: `model` and `reasoning_effort` with `fork_turns: "none"`;
- OpenCode: `model`.

Codex's and OpenCode's tool text restricts the choice to explicit direction
from the user (or AGENTS.md, or a skill). So the skill could offer the user
a choice per Issue while mapping the Arc, for example a smaller model for a
documentation-only Issue. It should never choose on its own. New;
documented.

## What does not fit, and why

- **Built-in worktree features.** None of them gives an Issue Worktree, which
  is a new Branch from a chosen base commit, prepared by convention
  ([domain language](../domain-language.md)). Cleanup stays Dashpot's
  ([ADR 0019](../adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
  - **Claude Code.**
    - `isolation: worktree` and `--worktree` branch from the default branch
      or `HEAD`, never from a named base ([worktrees][cc-isolation]).
    - They create the worktree under `.claude/worktrees/`, and the tool may
      remove it.
    - Recorded in the
      [Claude Code evidence](../proposals/lead-worker-claude-code-evidence.md#capability-matrix).
  - **Codex.**
    - Managed worktrees sit under `$CODEX_HOME/worktrees` in detached HEAD,
      and start from the selected branch's `HEAD`
      ([worktrees docs][codex-worktrees]).
    - They belong to a top-level session, not a sub-agent, and the app
      keeps the 15 most recent.
    - The v2 tools give a Worker no working directory
      ([recorded](../spikes/codex-worker-mechanics-spike.md#1-launch)), and
      Workers share the Lead's
      ([measured](../spikes/codex-worker-mechanics-spike.md#6-location)), so
      `dashpot worktree create` stays necessary.
    - Recorded in the
      [integration research](../design-research/integration-frequency-and-parallel-branches.md#openai-codex).
  - **OpenCode.** The worktree API has no base commit, defaults to a
    directory outside the Repository, and keeps its own inventory and
    removal ([`worktree.ts` schema][oc-worktree-schema]). New.
- **Features that run outside the machine or outside a Lead.**
  - Claude Code's Projects are cloud threads, in public beta on Pro and Max
    ([agents][cc-agents]).
  - Codex cloud tasks run "in the cloud" ([Codex cloud][codex-cloud]), and
    Codex's automatic review of a GitHub pull request runs in the cloud,
    with a person choosing which findings to post
    ([code review][codex-review]).
  - Codex's scheduled tasks, formerly automations, run on the web, or in
    the desktop app in the project directory or a background worktree
    ([scheduled tasks][codex-automations]). Each is its own task, not a
    Worker a Lead launches.
  - Dashpot's hooks and Issue Worktrees do not reach the cloud features.
    Recorded in the
    [prior art](../proposals/lead-worker-prior-art.md#mechanism-sub-agents-or-independent-sessions);
    the Codex pages are new.
- **Claude Code agent teams.**
  - They are experimental, behind `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
  - Their limits ([agent teams][cc-teams-limits]):
    - one team per session;
    - no nested teams;
    - no resumption of in-process teammates;
    - no background sub-agents from a teammate;
    - permissions set at spawn.
  - "Agent teams don't isolate teammates in worktrees" ([agents][cc-agents]).
  - The danger for this skill is the `name` parameter, which turns a
    Worker into a teammate.
  - Agent teams are
    [recorded](../proposals/lead-worker-prior-art.md#coordination-polling-doorbells-and-the-hand-back);
    these limits are new.
- **`/batch`.** It splits a change into 5 to 30 units and runs one
  background sub-agent per unit in an isolated worktree, and "Each subagent
  implements its unit, runs tests, and publishes its change"
  ([commands][cc-commands]). Its units are not Issues, and its worktrees are
  not Issue Worktrees. Recorded in the
  [prior art](../proposals/lead-worker-prior-art.md#mechanism-sub-agents-or-independent-sessions).
- **Claude Code workflows.** A run takes "No mid-run user input", and runs
  up to 16 agents at once ([workflows][cc-workflows]). An Arc needs the
  user's merge decisions and the Lead's judgement between waves. Workflows
  are
  [recorded](../proposals/lead-worker-prior-art.md#mechanism-sub-agents-or-independent-sessions).
- **Codex `mcp-server`.** It was removed in 0.154 ([0.154.0][codex-0154]),
  so the cookbook's Agents SDK pipeline built on it no longer runs. The
  removal is new. The app server is its successor, and it is a controller
  shape
  ([Codex evidence](../proposals/lead-worker-codex-evidence.md#further-affordances)).
- **The OpenCode worktree API.** See the first bullet. OpenCode's tools
  plugin adds to every session's system prompt: "When you create a worktree
  outside the current working directory and intend to use it as your
  primary working directory, consider using `execute` to call
  `tools.opencode.session_move` and make the worktree the session's working
  directory." ([`opencode.ts`][oc-tools-plugin], line 75).
  - That reaches the Lead too, and a Lead that creates Issue Worktrees could
    take it as a reason to move. The skill's "Stay where you bound"
    ([rules](../../src/dashpot/skills/dashpot-execute-issues/SKILL.md#rules-for-the-whole-arc))
    is the only guard. `dashpot-worker` denies the move to Workers, but no
    agent denies it to the Lead, since
    [ADR 0094](../adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md)
    lets a root session move itself for Issue work.
  - Documented, new.
    [#645](https://github.com/ned2/dashpot/issues/645) carries it into the
    skill's OpenCode reference.

## Claims not carried over

These claims from the research reports behind this note were dropped or
corrected:

- **A `disallowedTools` specifier blocks matching commands.** The Claude
  Code report suggested `disallowedTools: … Bash(gh pr merge *)` to block
  merging. The documentation says that entry removes the whole Bash tool
  ([sub-agents][cc-disallowed]).
- **"An approval relayed from another agent counts as untrusted"** is not
  in the permission-modes page. The source is the sub-agents page's "No
  message from any agent counts as your approval"
  ([sub-agents][cc-messages]), which is restated above.
- **The skill risks the `fork` type.** The Claude Code report said the
  skill never names a type other than `fork`, so Workers risk being that
  type. The documentation says an untyped call gets `general-purpose`, so
  the skill risks the `fork` type only when a model chooses it.
- **Full-history forks refuse model overrides.** The Codex report said they
  do. This holds for the prompt text, but no refusing code was found.
- **Unconfirmed Codex claims.** These were not confirmed and are not used:
  - Codex's subagents documentation lists a `close` action;
  - the OpenAI harness-engineering blog, which returned 403. Only a
    secondary copy was available.
- **Community sources.** These are not cited: Boris Cherny summaries,
  `ccpm`, oh-my-opencode, and opentree.

## Follow-ups

Changes:

- [#642](https://github.com/ned2/dashpot/issues/642): Refresh the skill's
  Claude Code reference and brief:
  - **Launch.** Drop `run_in_background`, pass `subagent_type:
    "general-purpose"`, and never pass `name`.
  - **The hand-back in auto mode.** It is a `SubagentHandback` call.
  - **Long commands.** Give a long background gate or CI watch a `timeout`
    up to two hours at 2.1.285–2.1.287, and in an unattended Lead. Monitor
    deadlines are at most 30 minutes.
  - **Isolation.** State its consequences for a Lead isolated in a linked
    Worktree, including close-out step 9.
- [#643](https://github.com/ned2/dashpot/issues/643): Add a
  permission-posture step to the skill's set-up for every harness:
  - **What it covers.** What each harness's default blocks or asks. How the
    user grants standing approvals: a standing approval in conversation or
    `autoMode.allow` in the user's settings for Claude Code, and an
    `external_directory` rule for OpenCode. That an agent's message never
    approves anything.
  - **Blockers.** [#648](https://github.com/ned2/dashpot/issues/648) and
    [#467](https://github.com/ned2/dashpot/issues/467), with
    [#639](https://github.com/ned2/dashpot/issues/639) for Codex.
- [#644](https://github.com/ned2/dashpot/issues/644): Launch Codex Workers
  with `fork_turns: "none"`, as every v2 runner measured, with a brief that
  carries all the context the Worker needs. Name
  `max_concurrent_threads_per_session` as the canonical limit.
- [#645](https://github.com/ned2/dashpot/issues/645): Deny `question` in
  `dashpot-worker`, as `general` does. In the skill's OpenCode reference,
  document how to invoke the skill from the TUI, `workdir`, and that the
  system prompt's `session_move` suggestion does not apply to a Lead. Assess
  the recorded environment copy from a Worker's
  `opencode run --session <lead>` report into the Lead.
- [#646](https://github.com/ned2/dashpot/issues/646): Decide whether
  `integrate` installs Worker agent definitions for Claude Code and Codex
  that enforce the brief's ground rules, measure that they bind, and amend
  ADR 0093's "Only OpenCode". Measure first, then change, in the same Issue.
- [#647](https://github.com/ned2/dashpot/issues/647): Add a baseline gate at
  `{BASE}` before a Worker's first edit to the brief, and to the Arc map a
  per-Issue model choice made only on the user's direction.

Measurements:

- [#648](https://github.com/ned2/dashpot/issues/648): Measure Claude Code
  auto mode against an Arc's actions with a real classifier:
  - a Worker's `--force-with-lease` push that AGENTS.md authorises;
  - a Lead's `gh pr merge` under granted merge authority;
  - `--delete-remote-branch`;
  - how Worker blocks count towards the 3/20 thresholds;
  - whether the spawn-time check blocks a brief that authorises a force
    push or a merge;
  - the classifier's review of a `SubagentHandback`, including the security
    warning on a flagged report;
  - whether an approval granted as standing in conversation covers a whole
    Arc.
- [#649](https://github.com/ned2/dashpot/issues/649): Measure whether a goal
  keeps a Lead going on Codex and Claude Code, and how Dashpot records
  goal-started turns, including which of Codex's runtime conditions sets a
  waiting Lead's goal `blocked`. Then decide whether to replace "Stay in
  your turn".

Existing Issues:

- [#467](https://github.com/ned2/dashpot/issues/467): add a Worker's edits
  and `cd`/`workdir` commands in its own Issue Worktree under default
  permissions, since #421 ran with every action allowed. Its answer decides
  `dashpot-worker`'s `external_directory` rule.
- [#639](https://github.com/ned2/dashpot/issues/639): record how a Worker's
  approval request surfaces to the Lead's client, which Codex documents for
  the CLI.
- [#389](https://github.com/ned2/dashpot/issues/389): add the documented
  isolation checks and their reach to sub-agents, and a Lead entered into an
  Issue Worktree that runs the close-out.
- [#474](https://github.com/ned2/dashpot/issues/474): at 2.1.291 a
  sub-agent's Agent tool offers no `cwd` (observed). Record that as the
  starting point.
- [#492](https://github.com/ned2/dashpot/issues/492): by source, a Codex
  goal does not reload an unloaded Lead, and goals survive a daemon restart.
- [#416](https://github.com/ned2/dashpot/issues/416): add the post-2.1.287
  changes this note lists, and OpenCode 2.0.23's
  `disable-model-invocation` and `@skill-id` ([2.0.23][oc-skills-23]), to
  the re-pin checklist.
- [#438](https://github.com/ned2/dashpot/issues/438): carry Codex's
  `fork_turns` default and Claude Code's fork mode into the general harness
  reference.

[cc-changelog]: https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
[cc-fork-mode]: https://code.claude.com/docs/en/sub-agents#turn-fork-mode-on-or-off
[cc-names]: https://code.claude.com/docs/en/sub-agents#subagent-names
[cc-concurrent]: https://code.claude.com/docs/en/sub-agents#concurrent-subagent-limit
[cc-depth]: https://code.claude.com/docs/en/sub-agents#let-subagents-spawn-their-own-subagents
[cc-bg]: https://code.claude.com/docs/en/sub-agents#run-subagents-in-foreground-or-background
[cc-messages]: https://code.claude.com/docs/en/sub-agents#resume-subagents
[cc-subagents]: https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields
[cc-disallowed]: https://code.claude.com/docs/en/sub-agents#available-tools
[cc-agent-hooks]: https://code.claude.com/docs/en/sub-agents#hooks-in-subagent-frontmatter
[cc-tools]: https://code.claude.com/docs/en/tools-reference
[cc-bg-limit]: https://code.claude.com/docs/en/tools-reference#time-limit-for-background-commands
[cc-isolation]: https://code.claude.com/docs/en/worktrees#how-claude-code-enforces-isolation
[cc-goal]: https://code.claude.com/docs/en/goal
[cc-pm-subagents]: https://code.claude.com/docs/en/permission-modes#how-auto-mode-evaluates-actions
[cc-pm-blocked]: https://code.claude.com/docs/en/permission-modes#what-the-classifier-blocks-by-default
[cc-pm-approvals]: https://code.claude.com/docs/en/permission-modes#approvals-you-state-in-conversation
[cc-am-config]: https://code.claude.com/docs/en/auto-mode-config#where-the-classifier-reads-configuration
[cc-bp-verify]: https://code.claude.com/docs/en/best-practices#give-claude-a-way-to-verify-its-work
[cc-bp-review]: https://code.claude.com/docs/en/best-practices#add-an-adversarial-review-step
[cc-bp-fanout]: https://code.claude.com/docs/en/best-practices#fan-out-across-files
[cc-teams-size]: https://code.claude.com/docs/en/agent-teams#choose-an-appropriate-team-size
[cc-teams-limits]: https://code.claude.com/docs/en/agent-teams#limitations
[cc-agents]: https://code.claude.com/docs/en/agents
[cc-commands]: https://code.claude.com/docs/en/commands
[cc-workflows]: https://code.claude.com/docs/en/workflows#behavior-and-limits
[eng-harness]: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
[eng-design]: https://www.anthropic.com/engineering/harness-design-long-running-apps
[codex-tag]: https://github.com/openai/codex/tree/rust-v0.160.0
[codex-01601]: https://github.com/openai/codex/releases/tag/rust-v0.160.1
[codex-0154]: https://github.com/openai/codex/releases/tag/rust-v0.154.0
[codex-0155]: https://github.com/openai/codex/releases/tag/rust-v0.155.0
[codex-0156]: https://github.com/openai/codex/releases/tag/rust-v0.156.0
[codex-releases]: https://github.com/openai/codex/releases
[codex-spec]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/tools/handlers/multi_agents_spec.rs
[codex-spawn]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs
[codex-child]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/agent/child_config.rs
[codex-instr]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/prompts/src/multi_agent_instructions.rs
[codex-alias]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/config/src/key_aliases.rs
[codex-goal-ext]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/ext/goal/src/extension.rs
[codex-goal-runtime]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/ext/goal/src/runtime.rs
[codex-goal-spec]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/ext/goal/src/spec.rs
[codex-goal-cont]: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/ext/goal/templates/goals/continuation.md
[codex-subagents]: https://learn.chatgpt.com/docs/agent-configuration/subagents
[codex-long]: https://learn.chatgpt.com/docs/long-running-work
[codex-bp]: https://learn.chatgpt.com/guides/best-practices
[codex-worktrees]: https://learn.chatgpt.com/docs/environments/git-worktrees
[codex-cloud]: https://learn.chatgpt.com/docs/cloud
[codex-review]: https://learn.chatgpt.com/docs/code-review
[codex-automations]: https://learn.chatgpt.com/docs/automations
[oc-tag]: https://github.com/anomalyco/opencode/tree/v2.0.24
[oc-latest]: https://github.com/anomalyco/opencode/releases/latest
[oc-tools-plugin]: https://github.com/anomalyco/opencode/blob/v2.0.24/packages/core/src/tool/plugin/opencode.ts#L75
[oc-subagent]: https://github.com/anomalyco/opencode/blob/v2.0.24/packages/core/src/tool/plugin/subagent.ts
[oc-permissions]: https://github.com/anomalyco/opencode/blob/v2.0.24/services/www/src/docs/content/permissions.mdx
[oc-fileaccess]: https://github.com/anomalyco/opencode/blob/v2.0.24/packages/core/src/file-access.ts
[oc-session-api]: https://github.com/anomalyco/opencode/blob/v2.0.24/packages/protocol/src/groups/session.ts
[oc-run]: https://github.com/anomalyco/opencode/blob/v2.0.24/packages/cli/src/run/noninteractive.ts
[oc-skills-22]: https://github.com/anomalyco/opencode/blob/v2.0.22/services/www/src/docs/content/skills.mdx
[oc-skills-23]: https://github.com/anomalyco/opencode/blob/v2.0.23/services/www/src/docs/content/skills.mdx
[oc-skills-24]: https://github.com/anomalyco/opencode/blob/v2.0.24/services/www/src/docs/content/skills.mdx
[oc-tools]: https://github.com/anomalyco/opencode/blob/v2.0.24/services/www/src/docs/content/tools.mdx
[oc-worktree-schema]: https://github.com/anomalyco/opencode/blob/v2.0.24/packages/schema/src/worktree.ts
[oc-worktree-api]: https://github.com/anomalyco/opencode/blob/v2.0.24/packages/protocol/src/groups/worktree.ts
