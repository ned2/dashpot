---
status: research
date: 2026-10-05
---

# Prior art for Lead and Worker coordination

How other systems run a lead agent's workers, coordinate them, and show them
to a person, and what that suggests for the
[Lead and Worker design](lead-worker-design.md). It covers four kinds of
prior art:

- tools that run many coding agents in parallel;
- orchestration frameworks and protocols;
- practitioners' and labs' writing on parallel coding agents;
- dashboards and agent UIs that show grouped or parent and child rows.

It was made for [Issue #479](https://github.com/ned2/dashpot/issues/479) on
2026-10-05, from published documentation, source, issue trackers and
articles, each read on that date. A point is _documented_ when a project's own
documentation or source states it, _reported_ when it comes from someone's
account of running a system, and _inference_ when it is this note's reading.
A vendor's claim about its own results is marked as such.

Lowercase lead, worker and sub-agent describe other systems in their own
general sense. Capitalised, Lead, Worker and Sub-agent are Dashpot's terms
from the [domain language](../domain-language.md).

## Summary

Prior art mostly supports the design's leading candidate, with three
qualifications.

- **For Workers that each write to an Issue and end in a PR, systems use
  independent sessions; they keep sub-agents for reading and review.**
  OpenAI's Symphony, Anthropic's parallel compiler experiment, Gas Town, and
  Claude Code's own agent view all run one session per task. The sources
  that favour sub-agents describe research or fresh-context review.
- **Durable state is the truth, and messages are hints.** Protocols tell
  their clients to poll a task record and treat notifications as optional.
  The tools whose bugs cluster most are the ones that push nudges between
  sessions.
- **The qualifications.** First, every hierarchical framework sends a
  worker's permission prompts to its parent, and root-session Workers lose
  that. Second, agent UIs organise by what needs a person, not by parent, so
  a grouped pane must never hide a Worker waiting for input. Third, mature
  orchestrators end child tasks with their parent by default, so letting a
  Worker outlive its Lead has to be a stated choice.

## Mechanism: sub-agents or independent sessions

- **Write-heavy, Issue-scoped work uses independent sessions.**
  - [Symphony](https://github.com/openai/symphony) (OpenAI, 2026-04-28)
    runs one Codex agent and one workspace per tracker Issue (documented).
  - Nicholas Carlini's
    [C compiler experiment](https://www.anthropic.com/engineering/building-c-compiler)
    (Anthropic, 2026-02-05) ran 16 independent Claude sessions coordinated
    by lock files (reported).
  - [Gas Town](https://github.com/gastownhall/gastown) (2026) runs each
    agent as a tmux session in its own Worktree (documented).
  - Claude Code's [agent view](https://code.claude.com/docs/en/agent-view)
    lists background sessions and does not list Sub-agents as rows
    (documented).
- **Sub-agents suit reading and review.**
  - Anthropic's
    [multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
    (2025-06-13) uses sub-agents for parallel reading; they write results to
    files and return references (reported).
  - Cognition's
    [Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents)
    (2025-06-12) argues that agents writing in parallel make conflicting
    implicit decisions. Its follow-up,
    [Multi-Agents: What's Actually Working](https://cognition.com/blog/multi-agents-working)
    (2026-04-22), reports that fresh-context review agents work and that a
    manager's children do not report back by default.
  - LangChain's
    [How and when to build multi-agent systems](https://www.langchain.com/blog/how-and-when-to-build-multi-agent-systems)
    (2025-06-16) reconciles the two: reading parallelises, writing does not.
  - So a Worker's reviewer stays a Sub-agent under this design.
- **A sub-agent makes its parent's "idle" wrong.**
  - In [Vibe Kanban #2783](https://github.com/BloopAI/vibe-kanban/issues/2783),
    Claude Code's `Stop` fired while the parent waited on Sub-agents, so the
    task was marked idle and a stray commit was made.
  - [agent-deck #2473](https://github.com/asheshgoplani/agent-deck/issues/2473)
    is the same class.
  - This is the gap [#472](https://github.com/ned2/dashpot/issues/472)
    records.
- **Not everyone uses Worktrees.**
  - Peter Steinberger's [Just talk to it](https://steipete.me/posts/just-talk-to-it)
    (2025-10) runs several agents in one folder, relying on atomic commits.
  - Simon Willison's
    [parallel coding agent lifestyle](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)
    (2025-10-05) uses fresh checkouts.
  - Conductor recommends several agents in one workspace when they share a
    branch.
  - These choices are about workspaces, and they leave the one Issue, one
    Worktree, one PR model untouched.

## Coordination: polling, doorbells and the hand-back

- **Protocols make polling the truth.**
  - [MCP Tasks](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks)
    (2025-11-25, experimental) says requestors "MUST NOT rely on" status
    notifications and must poll `tasks/get` (documented).
  - [A2A](https://a2a-protocol.org/latest/topics/streaming-and-async/) tells
    clients to fetch the task again after a push (documented); its
    specification gives push no delivery guarantee.
  - Symphony polls its tracker every 30 seconds and reconciles running work
    against it, persisting no scheduler state (documented).
  - Conductor's [API](https://www.conductor.build/docs/api) cookbook polls a
    session's status about every 15 seconds (documented).
- **Pushing nudges between sessions is where bugs accumulate.**
  [agent-deck](https://github.com/asheshgoplani/agent-deck), the tool
  closest to this design, has explicit parents, a persistent conductor and
  nudges on state change. Its tracker records:
  - a heartbeat that answered a question on the user's behalf and wiped
    their draft ([#1981](https://github.com/asheshgoplani/agent-deck/issues/1981));
  - a heartbeat that re-read an 885,000-token context on every tick
    ([#2348](https://github.com/asheshgoplani/agent-deck/issues/2348));
  - a restart that re-sent every child's transition;
  - sub-agent completions flooding the parent;
  - a child's death never delivered;
  - duplicate entries measured at 49% over a week
    ([#2481](https://github.com/asheshgoplani/agent-deck/issues/2481)).

  [Claude Squad #266](https://github.com/smtg-ai/claude-squad/issues/266)
  lost a prompt typed before the agent was ready. The lessons, by inference:
  - never type into a Lead that is busy or waiting;
  - deliver at most one doorbell per transition;
  - make handling idempotent, so a lost doorbell costs only latency.
- **A hand-back must be idempotent.**
  - OpenCode's own Sub-agent notice carries a stable id
    ([OpenCode evidence](lead-worker-opencode-evidence.md#affordances-beyond-the-existing-experiments)).
  - LangGraph re-runs a node on resume and requires the side effects before
    an [interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts)
    to be idempotent (documented).
  - By inference, a Lead keys a hand-back on the Issue, PR, head commit and
    state.
- **Lost completions are found by inconsistency, not by waiting.**
  - Gas Town's
    [polecat lifecycle design](https://github.com/gastownhall/gastown/blob/main/docs/design/polecat-lifecycle-patrol.md)
    calls this "discover, don't track". Its monitors derive state from what
    they can observe, so a lost completion message heals itself (documented).
  - Dashpot's equivalents, by inference:
    - a PR open while the Worker's status still says working;
    - a session ended with no status;
    - a status of done with no PR.
- **Neither the end of a turn nor a process exiting means done.**
  - [Vibe Kanban #2495](https://github.com/BloopAI/vibe-kanban/issues/2495):
    Claude Code in stream-JSON mode never exits, so runs read running
    forever.
  - Conductor warns that a session reads idle before its brief is delivered.
  - Claude Code's [agent teams](https://code.claude.com/docs/en/agent-teams)
    document that "task status can lag".
  - Completion belongs to durable state: the Worker's `work stop`, its status
    file, or its PR.
- **The PR is the usual completion surface.**
  - GitHub's
    [Copilot coding agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)
    reports through a draft PR and session logs, one PR per task
    (documented).
  - Agent view's "Ready for review" group is sessions with an open PR
    (documented).
- **Briefs and results travel as files.**
  - Anthropic's research system gives each delegate an objective, an output
    format, tools and boundaries, and takes results back as files
    (reported).
  - Jesse Vincent's
    [September 2025 workflow](https://blog.fsck.com/2025/10/05/how-im-using-coding-agents-in-september-2025/)
    hands off through written plan files (reported).
  - Cognition warns that a manager that doesn't know the code over-prescribes
    to its children.
- **No common protocol covers the harnesses.**
  - The [Agent Client Protocol](https://agentclientprotocol.com/overview/agents)
    is native in OpenCode and Gemini CLI, and reaches Claude Code and Codex
    only through adapters.
  - Its model is one client driving one agent's session, not peers
    coordinating.
  - Vibe Kanban speaks each harness's own protocol: Claude Code's stream-JSON
    with a permission tool, Codex's app server, an OpenCode server per run,
    and ACP only for Gemini and Qwen (source).
  - This supports a harness-neutral core built on durable state rather than
    on any one protocol.

## The link between a Lead and its Workers

- **Mature systems record the parent at launch.**
  - Temporal records a
    [child workflow](https://docs.temporal.io/child-workflows) in its
    parent's history when it starts.
  - Erlang/OTP links a child to its
    [supervisor](https://www.erlang.org/doc/system/sup_princ.html) with
    `start_link`.
  - A2A has only grouping (`contextId`) and references, with no hierarchy
    (documented).
- **agent-deck links a child automatically through an environment variable.**
  A child started with `AGENT_DECK_SESSION_ID` set takes that session as its
  parent (documented). When the link was lost, its children showed flat
  ([#2450](https://github.com/asheshgoplani/agent-deck/issues/2450)).
- **Superset scopes globally installed hooks to its own sessions.** Its
  [hooks investigation](https://github.com/superset-sh/superset/blob/main/HOOKS_INVESTIGATION.md)
  found that hooks merged into the user's global configuration fired in every
  session on the machine. The fix was to require an environment variable that
  only its launcher sets (source).
- **For Dashpot**, by inference: a Lead could stamp its identity into a
  Worker's launch environment, so the Worker's `work start` can confirm the
  declared link rather than take it on trust. The Claude Code and Codex
  evidence notes record how each harness forwards a launching shell's
  environment, which decides whether the stamp survives.

## State vocabulary and attention

- **"Waiting on a person" is a state of its own.**
  - A2A's `input-required` and `auth-required`, MCP's `input_required`, and
    agent view's "Needs input" each name it, and in each the worker reports
    it rather than it being guessed from silence (documented).
  - Agent view also keeps Idle apart from Completed, Failed and Stopped, and
    shows process liveness on a separate glyph (documented).
- **Cancelled, rejected and failed differ.**
  - The ACP [prompt turn](https://agentclientprotocol.com/protocol/prompt-turn)
    must report `cancelled` apart from errors.
  - A2A adds `rejected`, for an agent that declines the task (documented).
  - A Worker that finds its Issue not actionable is not one that crashed.
- **A terminal state is permanent.**
  - In MCP a cancelled task stays cancelled even if it later finishes.
  - In A2A further work on a closed task is a new task in the same context
    (documented).
  - Dashpot already ends an Agent Run and starts another; follow-up work
    after a Worker's PR is a new run.
- **Calling a Worker stalled is risky.**
  - Gas Town records a bug in which aggressive timeouts killed agents that
    were thinking, not hung (reported).
  - Symphony measures a stall from the last event and retries with backoff
    (documented).
  - By inference, a passive dashboard shows "quiet for N minutes" and leaves
    the verdict to a person or the Lead.

## Presentation

- **A tree inside a column, sorted among siblings, is the closest
  precedent.**
  - [htop](https://htop.dev/)'s tree view sorts each process's direct
    children only, and marks a collapsed subtree with `+`.
  - btop can auto-collapse a parent with many children (documented).
  - This supports drawing connectors in a frozen leading column (the
    design's placeholder ROLE).
- **Agent UIs group by attention, not by parent.**
  - Agent view's groups are Pinned, Ready for review, Needs input, Working
    and Completed, and rows move between them as state changes
    (documented).
  - Cursor's agents window can group by status into "Needs Attention", and
    VS Code's sessions view badges sessions waiting for input or with
    failing CI (documented).
  - Grouping under a Lead can bury a waiting Worker, which argues for a
    pane-level attention signal alongside the grouping.
- **Collapsing never hides urgency.**
  - Claude Code's agent-teams panel folds more than three idle teammates
    into one "N idle agents" row, while working and failed teammates always
    keep their own rows (documented).
  - k9s's xray view adds a child count to each parent (source), and Temporal
    can hide child workflows behind a count (documented).
  - So a collapsed Lead would show its most urgent Worker's state, or refuse
    to fold a Worker that needs input (inference).
  - Web tables such as Grafana's nested tables start collapsed, but here
    Workers are the point, so groups would start expanded (inference).
- **A declared but missing reference gets a named state.** k9s marks a
  reference to a missing resource as `TOAST_REF`, beside its colour
  (source). This supports `⇢` and `not listed` as explicit states.
- **A child's state copied from its parent's record goes stale.** Temporal's
  relationships tab showed a completed child as running, a confirmed issue
  ([community thread](https://community.temporal.io/t/13106)). A Worker row's
  state must come from observing that Worker, which root-session Workers
  allow.
- **Mature tables keep the hierarchy out of the main list.**
  - k9s's resource tables are flat, with a jump-to-owner key and a separate
    tree view that drops the columns.
  - Lens shows a "Controlled By" column (documented).
  - These tools list hundreds of rows where Dashpot lists a handful, but a
    Lead column or a jump-to-Lead key is a fallback if grouping proves
    awkward.
- **Narrow screens fold settled rows first.**
  - Agent view compacts its Completed group and adds an "N more" row on a
    short terminal, while working, waiting and failed rows stay
    (documented).
  - Buildkite shows parallel groups ungrouped when a build's jobs are
    truncated (documented).
  - With two visible rows at 80×24, folding idle Workers comes before giving
    width to connectors.
- **Textual has no tree-table** to borrow; connectors drawn in a frozen cell
  are the realistic route (inference, from a search of Textual's issues and
  community widgets).
- **Keys.** tmux's `choose-tree` expands and collapses with `+` and `-`, a
  precedent for collapsible groups (documented).

## Permissions for unattended Workers

- **Hierarchical frameworks route a worker's asks to its parent.**
  - Claude Code's agent teams show teammates' permission prompts in the lead
    (documented).
  - The OpenAI Agents SDK surfaces a nested tool's
    [approval](https://openai.github.io/openai-agents-python/human_in_the_loop/)
    on the outer run (documented).
  - A root-session Worker's ask stays in the Worker, and a message from
    another session cannot approve it, so Dashpot's view becomes the main way
    a person finds it.
- **No tool solves unattended asks by observing them.** The approaches in
  use:
  - keypresses sent blind (Claude Squad's `--autoyes`, uzi's `auto`);
  - a model that classifies the ask (ccmanager, experimental);
  - approvals relayed over the harness's protocol (Vibe Kanban);
  - a sandbox that removes the need to ask (Copilot coding agent,
    container-use).
- **Symphony's specification** says a run "MUST NOT stall indefinitely
  waiting for user input" (documented). The design's open decision on
  permission posture is therefore a choice among setting a posture at
  launch, routing asks through a harness API, or accepting parked Workers
  that Dashpot makes visible.

## Lifecycle, ended leads and Cleanup

- **What happens to workers whose lead ends is explicit elsewhere.**
  - Temporal's
    [parent close policy](https://docs.temporal.io/parent-close-policy)
    defaults to terminating a child when its parent closes. Abandoning the
    child, so that it runs on, is an option for asynchronous children
    (documented).
  - A Worker driving a PR fits abandonment, but Dashpot never ends a session
    itself. So the design would show a Worker whose Lead has ended as such,
    rather than hide it, and say so deliberately.
- **Root sessions survive restarts where in-process workers do not.**
  - Agent teams document that in-process teammates are not restored on
    resume.
  - Agent view's supervisor restarts crashed sessions and leaves them
    resumable after a reboot (documented).
- **Workspaces are kept until the work is finished.**
  - Symphony cleans a workspace only when its Issue reaches a terminal state,
    and Gas Town keeps the sandbox until merge (documented).
  - The Codex app keeps fifteen Worktrees, protects running and pinned ones,
    and snapshots one before deleting it (documented).
  - agent-deck separates archiving from deletion, with an undo window
    (documented).
  - [Vibe Kanban #1571](https://github.com/BloopAI/vibe-kanban/issues/1571)
    left a run reading running after its Worktree was removed.
  - All of this matches Dashpot's confirmed, preview-first Cleanup
    ([ADR 0019](../adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)),
    which refuses while a session occupies the Worktree.

## Human limits and cost

- **About three to five active Workers per person.** The evidence:
  - OpenAI reports engineers managing three to five sessions before
    Symphony (vendor claim).
  - Addy Osmani's [parallel agent limit](https://addyosmani.com/blog/cognitive-parallel-agents/)
    (2026-04-07) is three or four.
  - Willison reports reviewing one significant change at a time.
  - Agent teams' documentation suggests starting with three to five.
  - Mitchell Hashimoto's
    [AI adoption journey](https://mitchellh.com/writing/my-ai-adoption-journey)
    (2026-02-05) runs one background agent, and advises turning off agent
    notifications because context switches are expensive.
  - Armin Ronacher runs fewer in parallel than he did
    ([Pragmatic Engineer](https://blog.pragmaticengineer.com/new-trend-programming-by-kicking-off-parallel-ai-agents/),
    2025-10-30).
  - Gas Town's ten or more agents depend on automated merging and several
    subscriptions ([Welcome to Gas Town](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html),
    reported).
- **Overlapping Issues defeat parallelism.** Carlini's agents collapsed into
  overwriting each other once they all hit the same bug (reported). A Lead
  that checks Issues for overlapping files before dispatch avoids this; a
  dashboard could flag Worker Branches that touch the same files
  (inference).
- **Cost scales with sessions.** Anthropic reports multi-agent runs using
  about fifteen times a chat's tokens. Root-session Workers on one
  subscription share its rate limits, and Claude Code documents that a
  `--bg` session's agent fails at a usage limit rather than waiting
  (documented).
- **Many tools in this space have shut down or changed name in 2026**,
  including Vibe Kanban's company, Terragon and Crystal. Their designs are
  evidence, not endorsements.

## Suggestions for the design

Each of these is reflected in the design rather than adopted: suggestion 1
is part of its [leading candidate](lead-worker-design.md#leading-candidate),
suggestion 2 shapes its
[communication core](lead-worker-design.md#communication), and the rest
appear among its
[open decisions](lead-worker-design.md#open-decisions):

1. Keep Workers that write as root sessions and reviewers as Sub-agents.
2. Derive a Worker's state from durable evidence, and treat every harness
   message as a hint that costs only latency when lost or repeated.
3. Make the hand-back idempotent, keyed on Issue, PR, head commit and state.
4. Find lost completions by inconsistency between the Worker's status, its
   session and its PR.
5. Show "quiet for N minutes" rather than calling a Worker stalled.
6. Stamp the Lead's identity into a Worker's launch environment, so the
   declared link can be confirmed.
7. Treat needs-input as a first-class state, and keep it visible whatever the
   grouping: as a pane-level count or ordering, and never folded away.
8. Start groups expanded, and fold idle or finished Workers first when space
   runs out.
9. Decide explicitly what happens to a Worker whose Lead has ended, and
   show it.
10. Show the number of active Workers per Lead, since three to five per
    person is the reported ceiling.
