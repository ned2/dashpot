---
status: research
date: 2026-09-14
---

# Chat-centric coding agents versus team-oriented software development

- **Researched:** 2026-09-14
- **Question:** Are people writing about the mismatch between coding tools that
  make a private chat/session the unit of work and software teams that organize
  durable work around repositories, issues, branches, pull requests, review,
  CI, and shared ownership?

## Bottom line

Yes. The exact vocabulary is not settled, but the tension is explicit in
product writing, practitioner projects, upstream feature requests, and recent
software-engineering research.

The clearest statement comes from Linear co-founder Karri Saarinen. He writes
that coding agents are still “mostly individual productivity tools, useful to
one person at a time,” whereas building a product is team work whose decisions
and reasoning form shared context. Linear's response is deliberately
issue-centric: a coding session starts from an issue, carries its surrounding
context, opens a pull request, is visible and steerable by the team, and
“belongs to the organisation rather than to the person who started it.” That
is almost exactly the alternative ownership model in the research question.

GitHub is converging on a similar shape. It still exposes agent sessions, but
now nests their status beneath issue assignees and shows attached sessions in
Projects; repository-level agent views link sessions to the resulting pull
requests. The session remains an execution record, while repository, issue,
project item, and pull request remain the shared coordination objects.

GitHub's own product writing makes the contrast unusually explicit: it
describes the traditional assistant as working in an isolated IDE session,
then presents the coding agent's PR-native workflow as visible, logged, and
open to team input. This is vendor positioning, but it confirms that GitHub
sees the collaboration boundary in the same place as the research question.

Early empirical evidence also supports the concern that current agent adoption
is individual rather than team-shaped. In a study of 25,264 agentic pull
requests across 2,361 popular GitHub repositories, one person both reviewed and
modified the agent's contribution in 78.9% of PRs; all single-human patterns
accounted for 88.7%, while multi-human patterns accounted for 11.3%. This does
**not** prove chat-centric UI caused the pattern, but it shows that “AI teammate”
adoption currently tends to collapse into one developer privately supervising
an agent.

Sources: [Linear, “Now Linear writes the code, too”](https://linear.app/now/coding-sessions-for-linear-agent),
[GitHub, “Copilot coding agent 101”](https://github.blog/ai-and-ml/github-copilot/github-copilot-coding-agent-101-getting-started-with-agentic-workflows-on-github/),
[GitHub agent activity in Issues and Projects](https://github.blog/changelog/2026-03-26-agent-activity-in-github-issues-and-projects/),
and [Raida and Hou, *Early Adoption of Agentic Coding Tools by GitHub Projects*](https://arxiv.org/abs/2607.14037).

## The chat-centric baseline

OpenAI's current documentation confirms that the observed ownership model is
deliberate rather than an accidental sidebar layout. A project groups related
chats, the recommended workflow is a separate chat for each distinct outcome,
and every chat retains its own transcript and recorded working directory.
Worktrees are introduced as a way to run multiple independent chats, and a
managed worktree is typically dedicated to one chat. The durable guidance that
must cross chats is explicitly pushed into `AGENTS.md` or checked-in project
documentation.

That is a coherent model for one developer running several isolated workers:

```text
project -> chat/outcome -> managed worktree -> changes
```

It is also the precise source of the tension. The chat owns the execution
environment and continuity, while an external issue, team owner, or delivery
object is optional context rather than the parent identity of the work.

Sources: [OpenAI, “Projects and chats”](https://learn.chatgpt.com/docs/projects)
and [OpenAI, “Worktrees”](https://learn.chatgpt.com/docs/environments/git-worktrees).

## The tension people identify

### A transcript is local interaction state, not durable team state

The practitioner-authored Agent Handoff project states the criticism directly:
chat history is insufficient when multiple humans and agents work across
sessions, tools, branches, and pull requests. It locates durable state in the
systems that already encode team work:

- GitHub for issues, PRs, reviews, checks, labels, comments, and ownership;
- Git for branches, commits, diffs, tags, and history; and
- small repository-local artifacts for compact agent context and protocols.

Its comparison calls chat memory tool-specific and session-bound. This is a
small community project rather than established practice, but its rationale is
a precise articulation of the ownership problem.

Source: [Agent Handoff README](https://github.com/artyomboyko/Agent_Handoff#why-this-exists).

Steve Yegge's Beads essay reaches the same conclusion from the agent-memory
side. Long engineering work outlives context compactions and individual
sessions, while nested and newly discovered tasks become hard to reconstruct
from plans and transcripts. His response is to move planning into a
dependency-linked issue graph and make sessions disposable: a new agent can
recover the current work from the graph rather than inheriting the old chat.
Beads is an opinionated personal system, not evidence that one tracker model is
universally right, but it is a prominent example of demoting the session below
durable work identity.

A July 2026 preprint makes a parallel argument about engineering memory. It
starts from the observation that rationale is trapped in assistant transcripts
that vanish with sessions and proposes binding retained memory to Git, so it
inherits commit grounding, merge-time verification, review, and repository
history. It addresses rationale retrieval rather than project management, but
supports the same separation: a transcript is raw execution history; durable
team knowledge should attach to the artifacts the team already versions and
reviews.

Sources: [Steve Yegge, “Introducing Beads”](https://yegge.ai/essays/introducing-beads-a-coding-agent-memory-system/)
and [Frank Guo, *Why Git Is the Memory Solution for the Agentic Development Lifecycle*](https://arxiv.org/abs/2607.14390).

Nimbalyst's founders make a related interface critique. They distinguish
IDE-centric tools, which make non-code artifacts second class, from chat-centric
tools, which lack the structured project management needed when several agents
operate across a codebase. Their proposed workspace joins tasks, specifications,
files, diffs, and sessions rather than treating the transcript as the complete
working context. This is also product-positioning material, so it is best read
as evidence that builders perceive the gap, not as independent proof that their
solution is correct.

Source: [Karl Wirth, “Open sourcing Nimbalyst”](https://nimbalyst.com/blog/open-sourcing-nimbalyst/).

### Single-developer orchestration is not team-level engineering

A 2026 software-engineering research roadmap draws a useful boundary between:

- **1-to-N:** one developer collaborating with many agents; and
- **N-to-N:** a human team collectively collaborating with a shared fleet of
  agents.

The authors argue that team-level software engineering adds multi-role
governance, evidence-based review, and cross-functional consultation. They call
for a shared command environment and structured, auditable artifacts rather
than assuming that more agent instances in one developer's interface constitute
a team workflow. That distinction maps directly to the concern here: a personal
chat list can be an excellent 1-to-N console while remaining largely blind to
N-to-N work.

Source: [Hassan et al., *Agentic Software Engineering: Foundational Pillars and a Research Roadmap*, section 4.3](https://leo-lihao.github.io/files/P8.pdf).

The Raida and Hou study supplies an early real-world baseline. Its 25,264 PRs
were drawn from popular open-source repositories and only from May–July 2025,
so the findings should not be generalized uncritically to private commercial
teams or newer products. Within that scope, however, the predominance of
single-human oversight is stark. The authors conclude that sustainable adoption
depends on review practices, accountability, and project governance, not just
agent capability.

Source: [Raida and Hou, results and limitations](https://arxiv.org/abs/2607.14037).

## Two competing responses

### 1. Make the session multiplayer

One response accepts the session as the primary object and makes it shared:
multiple people can observe, steer, and take over the same agent run. This fixes
important failures of private chat—visibility, handoff, and shared control—but
does not by itself give the work a durable identity outside that run. The team
must still connect the session to intent, ownership, branch/PR state, review,
and delivery.

The demand is visible in Claude Code issue reports. Users ask to adopt already
running independent sessions into an agent team because the need to collaborate
often appears only after each session has accumulated context. Another detailed
report says independently launched sessions across one repository have no
first-party coordination story and asks at minimum for a registry of live
sessions with their working directories and branches. These are firsthand user
reports, not Anthropic product commitments.

Sources: [Claude Code issue #48105](https://github.com/anthropics/claude-code/issues/48105)
and [Claude Code issue #76727](https://github.com/anthropics/claude-code/issues/76727).

### 2. Attach sessions to the team's existing work graph

The other response makes the issue or change the durable object and treats an
agent session as an activity attached to it. Linear's current model is unusually
explicit:

- the human assignee remains responsible when work is delegated to an agent;
- the session starts with issue discussion, product decisions, customer signals,
  and related work already attached;
- anyone on the team can follow, contribute, redirect, or take over; and
- the resulting review sits beside the issue and discussion that caused the
  change.

This preserves a distinction between **accountability** (the human/team-owned
issue) and **execution** (the agent session). Linear naturally has an incentive
to cast its tracker as the shared context layer, but the ownership semantics are
concrete and directly relevant.

Sources: [Linear coding sessions](https://linear.app/now/coding-sessions-for-linear-agent),
[Linear issue assignment and delegation](https://linear.app/docs/assigning-issues),
and [Linear's internal bug-fix workflow](https://linear.app/now/linear-agent-bug-fix).

GitHub's implementation is less philosophically explicit but structurally
similar. Agent sessions appear below the agent assigned to an issue, carry live
status in Issues and Projects, and link to draft PRs and session logs. GitHub
also permits Copilot, Claude, and Codex to be assigned from issues or pull
requests, with review and iteration remaining in the PR workflow. This makes
agent activity visible through the repository's normal team surfaces rather
than only through the initiating developer's private client.

Sources: [GitHub agent activity in Issues and Projects](https://github.blog/changelog/2026-03-26-agent-activity-in-github-issues-and-projects/),
[GitHub's repository Agents tab](https://github.blog/changelog/2026-01-26-introducing-the-agents-tab-in-your-repository/),
and [Claude and Codex on GitHub](https://github.blog/changelog/2026-02-04-claude-and-codex-are-now-available-in-public-preview-on-github/).

GitButler takes a branch-first variant of this response. It attaches the AI
session to a branch view and makes generated changes, commits, diffs, and
parallel work visible through the version-control workflow. It does not solve
issue ownership by itself, but it reverses the top-level UI relationship:
session activity becomes a clickable property of a Git branch rather than the
branch being an implementation detail hidden behind a conversation.

Source: [GitButler, “Getting Started With GitButler Agents”](https://blog.gitbutler.com/gitbutler-agent-assist).

## This predates coding agents

The discomfort also has a deeper software-engineering lineage. A 2010 CSCW
study of four software teams found that issue trackers functioned not merely as
bug databases but as knowledge repositories, collaboration hubs, and channels
through which stakeholders negotiated and monitored work. That does not prove
issues must always be the top-level object, but it explains why replacing their
shared, role-spanning view with each developer's private transcript feels like
a regression: the tracker has long carried social coordination semantics that
a chat log does not.

Source: [Bertram et al., *Communication, Collaboration, and Bugs: The Social Nature of Issue Tracking in Small, Collocated Teams*](https://amy.voida.com/wp-content/uploads/2013/04/issueTracking-cscw10.pdf).

## OpenAI/Codex-specific signs of the same fault line

OpenAI has not published a comparable essay arguing that chat ownership is the
wrong abstraction. Public Codex issues nevertheless show users encountering
the boundary:

- A unified-desktop report says Chat and Work tasks can appear in the same
  Project while remaining unable to reference each other's task context. It
  proposes project-owned task titles, status, decisions, constraints, and
  explicit handoff artifacts rather than implicit transcript sharing.
- A Codex discussion asks for a task board and cross-thread routing because
  users are already treating threads as durable work items. This represents the
  opposite response: add task semantics on top of threads rather than attach
  threads to an external issue/change graph.
- A request for persistent teams and shared channels says isolated threads do
  not provide a durable project workspace for coordination.

These are community proposals, not confirmed roadmap items, but together they
show that the product's thread-centric boundaries become visible as soon as
work must span contexts, agents, or people.

Sources: [Codex issue #33942](https://github.com/openai/codex/issues/33942),
[Codex discussion #26148](https://github.com/openai/codex/discussions/26148),
and [Codex issue #36472](https://github.com/openai/codex/issues/36472).

## Synthesis

The user's discomfort is not idiosyncratic. There is an emerging design split:

```text
Personal-agent model
Project -> my session/chat -> agent(s) -> checkout -> patch

Team-work model
Repository/project -> issue/change -> accountable owner(s)
                   -> agent session(s) -> branch/PR -> review/CI/merge
```

The strongest team-shaped products do not eliminate conversation. They demote
it from **the identity of the work** to **a shared execution log and control
surface attached to the work**. The issue records intent and ownership; Git and
the PR record the proposed change and reviewable history; CI records evidence;
the session records how an agent attempted the work.

There is one important qualification: adopting issue-shaped UI cannot by itself
create collaboration. The empirical evidence shows agent PRs can still be
privately supervised by one developer even when they end in a shared GitHub PR.
Team-shaped agent development also needs explicit human ownership, independent
review rules, shared context, and visibility into active work. But a private
chat as the top-level durable object makes those properties harder to express
and easier to omit.
