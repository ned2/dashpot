# Run records

Reference for [dashpot-execute-issues](../SKILL.md). The arc's record lives
on GitHub, where the repository keeps its durable context, not in a private
notes file. Post it as comments on the **record Issue**:

- **Epic:** the epic itself.
- **List:** a tracking Issue you open at setup, titled after the arc's goal,
  whose body lists the arc's Issues and the Issues they unblock. Close it at
  close-out.

The record Issue's body opens with this line, which is how other leads find
every open arc in the repository:

```markdown
Tracking Issue for a `dashpot-execute-issues` arc over <the epic's sub-issues, or a list of Issues>.
```

Write it as the first line of a tracking Issue's body. For an epic, add it
at the top of the epic's body at setup, leaving the rest as it is.

Post with `gh issue comment <record-issue> --body-file <file>`, writing the
file with a script or a quoted heredoc. Each record is a new comment, so the
thread reads as the arc's timeline and survives a lost scratch directory: to
resume an arc, read the record Issue's comments.

The record is public wherever the repository is. Keep out of it local paths,
machine names, credentials, and anything the user said they want kept
private. Branch names, PR links and SHAs are fine. Record the user's
decisions as decisions, and ask before quoting them.

## The arc map

Posted once, at setup, before you create the first Worktree:

- the arc's Issues and its goal;
- the graph: each blocked-by edge with its gated slice, the critical path,
  and each Issue's float;
- the reservations, by Issue, and the spare;
- your share of the machine's cores, and how it splits between workers;
- the other open arcs you read, with the files, numbers and cores each
  holds, and how each file both arcs touch was settled;
- who holds merge authority for the arc;
- the waves you plan, which may change.

## A wave

Posted at dispatch:

- the wave's Issues, with their branches and base;
- each strategy used, and the hypothesis behind it (what it should save, and
  what would show it failed);
- the collision plan: owners of shared files, shared types, recorded
  evidence and who regenerates it.

## A merge

Posted when each PR lands. When merges come close together, the rest of the
record can wait for the wave's close-out, but the merge SHA and the SHA you
broadcast are posted at once: the next broadcast starts from the SHA you
broadcast.

The record holds:

- the PR, its merge SHA and time, and who merged it;
- how you checked that CI tested what lands, and any trial merge or new
  run it needed;
- the integration-branch SHA you broadcast, and every merge since the
  previous broadcast: the next broadcast lists what landed after it;
- the worker's wall-clock time, and its tool calls and tokens if the harness
  reports them;
- what worked, what it cost, and any follow-up it raised.

## A decision

Posted when the user decides something that changes the arc: what was
decided, by whom, and what it changes. A decision about one Issue's scope
also goes on that Issue.

## The close-out

Posted when the arc ends, or when a long arc pauses:

- a timeline table: dispatches, merges, decisions and close-outs, with
  times;
- each hypothesis, and whether it held;
- the lessons, ranked. File each lesson about the repository as an Issue
  against its agent instructions and link it here. List the lessons about
  this skill for the user, who decides whether to report them upstream.
- the follow-ups filed, and the Issues outside the arc that inherited
  deferred scope;
- each Worktree the user removed despite listed sub-agents: the user's
  instruction, and each check's result.
