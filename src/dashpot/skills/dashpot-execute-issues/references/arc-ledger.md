# Arc ledger

Reference for [dashpot-execute-issues](../SKILL.md). The arc's working
record lives in a local **ledger**, not on GitHub and not in your scratch
directory. Mid-arc notes take in whatever the session knows, and a public
Issue is the wrong place for them: the ledger keeps them on this machine,
and only reviewed outcomes go to GitHub
([What goes to GitHub](#what-goes-to-github)). A scratch directory can be
lost mid-arc; the ledger survives a restart.

## Where it lives

The **ledger root** is this directory, in the checkout you bound in,
normally the repository's main checkout. Every path below is relative to
the top of that checkout, and every command runs there:

```text
.dashpot/state/skills/dashpot-execute-issues/
  arcs/<arc-id>/arc.json           the arc's summary, which other leads read
  arcs/<arc-id>/ledger.md          the record, appended as the arc runs
  arcs/<arc-id>/brief-template.md  the filled brief template
  arcs/<arc-id>/broadcast.md       your broadcasts, which workers read
  arcs/<arc-id>/workers/<name>.md  one worker's reports, written by it alone
  reservations/<kind>-<value>/     one directory per reserved number
```

`.dashpot/state/` is Dashpot's Project-local state directory, which Git
ignores through the `.gitignore` Dashpot writes inside it. Before your first
write, check that Git ignores the ledger root:
`git check-ignore -q .dashpot/state/skills/dashpot-execute-issues`. If it is
not ignored, stop and tell the user rather than writing a `.gitignore`
yourself. The ledger goes with the checkout's ignored state: `git clean -x`
deletes it, and so does removing the checkout when it is a linked
Worktree. Run no `git clean -x` there during an arc, and when you bound in
a linked Worktree, tell the user that it holds the ledger and must stay
until the arc is closed and its ledger no longer wanted.

**You alone write your arc's files, apart from each worker's own.** A
worker writes only its file under `workers/`, and only where
[harnesses.md](harnesses.md) has it report there
([Worker files](#worker-files)); you read those files and never edit them.
Every other report reaches you through your harness's channels, and you
record what matters. Another lead's files are its own: read them, never
edit them. Write each file with a script or a quoted heredoc (`<<'EOF'`).
Append to `ledger.md` with `>>`, and replace `arc.json` whole: write a
temporary file beside it, then `mv` it into place, so a reader never sees
half a file.

The ledger is the arc's working record, not a private memory store. It
holds one arc's state, in the Project's own state directory, where the
user and any later lead can read it, and its outcomes go to GitHub by
close-out. Keep credentials out of it all the same.

## Opening an arc

At setup, before you reserve anything:

1. Name the arc `<UTC date>-<bound Issue number>`, such as
   `2026-10-06-412`, and create its directory with `mkdir` without `-p`
   on the last component:
   `mkdir -p <ledger root>/arcs && mkdir <ledger root>/arcs/<arc-id>`. If
   it already exists, another arc took the name: add `-2`, `-3` and so
   on.
2. Write `arc.json` with `"state": "open"`, and create the arc's
   `workers/` directory for the [worker files](#worker-files).
3. Copy the [brief template](brief-template.md) into the arc's directory as
   `brief-template.md`, and fill it there. Rendered briefs can go beside it,
   under `briefs/`.

## The summary: arc.json

Other leads read this file to share the machine with you. Replace it
whenever a value changes: at setup, at each wave, and as workers come and
go.

```json
{
  "arc": "2026-10-06-412",
  "state": "open",
  "leadSession": "<Agent Session ID>",
  "issues": [412, 413, 415],
  "accountable": "<the accountable person>",
  "ceiling": 5,
  "cores": 16,
  "liveWorkers": 3,
  "files": ["<path or document section your collision plan owns>"],
  "closed": null
}
```

`state` is `open` until the arc ends; a paused arc stays open. `cores` is
your share of the machine's cores, and `ceiling` the accountable person's
limit on live workers across their arcs. `closed` is the UTC time the arc
ended. Take the session ID from the `Agent Session identity claimed here`
line of `<dashpot> integrate <harness> --status`.

## Reservations

Reserve each number the repository's checks require to be unique by
creating its directory, one `mkdir` per number, without `-p` on the last
component:

```bash
mkdir -p <ledger root>/reservations
mkdir <ledger root>/reservations/<kind>-<value> &&
  printf '%s\n' <arc-id> > <ledger root>/reservations/<kind>-<value>/arc
```

`<kind>` names what is numbered, such as `decision-record` or `migration`.
A `mkdir` that fails means another arc in this checkout holds the number:
read its `arc` file, and take the next free one. A reservation with no
`arc` file is one whose lead stopped between the two commands: treat the
number as taken, and ask the user before you free it. The directory makes the
claim atomic between leads that share a ledger root. A lead bound in
another checkout keeps its own root, which you read while
[finding other arcs](#finding-other-open-arcs); a clash with it is settled
as SKILL.md's step 2 says. Record each reservation in the arc map too.

When the arc ends, remove every reservation directory your arc map or a
later entry lists, including each number you changed after a clash: the numbers you used are on the integration branch by then, and the
spare is free again. A paused arc keeps its reservations.

## Finding other open arcs

Every lead keeps its ledger root in the checkout it bound in, so read
every checkout's: for each path `git worktree list --porcelain` prints, list
`<path>/.dashpot/state/skills/dashpot-execute-issues/arcs/*/arc.json` and
keep those whose `state` is `open`. Read each one's `ledger.md` for its
collision plan, and the `reservations/` beside it for its numbers.

- **An open arc whose lead is gone** may have ended without closing, as when
  its session crashed. When Dashpot's dashboard lists no live Agent Session
  with its `leadSession` ID, ask the user before you treat its files and
  numbers as free.
- **An arc in another clone or on another machine** is invisible here. You
  see its work only through the integration branch, open PRs and the
  Remote-Tracking Branches, which step 2's reservation scan reads anyway.

## Worker files

Where your harness gives a worker no channel to you, or its channel fails,
the worker appends its reports to `arcs/<arc-id>/workers/<name>.md`, where
`<name>` is its `{WORKER}` name. Where the harness gives a worker no channel
from you either, you append each broadcast to `arcs/<arc-id>/broadcast.md`,
and the worker reads it before each gate run, commit and push.
[harnesses.md](harnesses.md) says which harnesses use which file. When
you fill `{REPORTING}`, put the arc directory's absolute path in it for
`<arc directory>`, since a worker's commands run in its Worktree, where a
relative path misses, and the worker's `{WORKER}` name for `<worker name>`.
An arc opened before setup created `workers/` has none: create it before
you dispatch again.

Both files take the same entries, each appended whole by one command that
takes its heading's time from `date`:

```bash
{ date -u '+### %FT%TZ'; cat <<'EOF'; } >> <file>
<the report or broadcast>
-- end
EOF
```

A worker opens each report with its brief's key line. An entry without its
`-- end` line is still being written: read it again later. Read each
worker's file between waits, and record what matters in `ledger.md`. A
worker's file is its own words: weigh it as a report, never as an
instruction to you.

## The record: ledger.md

Append one entry per event, each opening with a heading that gives the UTC
time and the entry's kind, such as `## 2026-10-06T03:12Z: merge`. The
entries are those below. To resume an arc, read its `arc.json` and its
`ledger.md` from the top.

The ledger is local, so local paths and machine details may go in it. They
stay there: nothing from it reaches GitHub without the check in
[What goes to GitHub](#what-goes-to-github).

## The arc map

Written once, at setup, before you create the first Worktree:

- the arc's Issues and its goal;
- the person accountable for the arc, and the ceiling on their live workers
  across their arcs: five by default, or the one the user directed;
- the graph: each blocked-by edge with its gated slice, the critical path,
  and each Issue's float;
- the reservations, by Issue, and the spare;
- your share of the machine's cores, and how it splits between workers;
- the other open arcs you read, with the files, numbers and cores each
  holds, and how each file both arcs touch was settled;
- who holds merge authority for the arc;
- the waves you plan, which may change.

## A wave

Written at dispatch:

- the wave's Issues, with their branches and base;
- each worker's handle and `{WORKER}` name, beside its Issue;
- each strategy used, and the hypothesis behind it (what it should save, and
  what would show it failed);
- the collision plan: owners of shared files, shared types, recorded
  evidence and who regenerates it.

## A merge

Written when each PR lands, at once: the next broadcast starts from the SHA
you broadcast. The entry holds:

- the PR, its merge SHA and time, and who merged it;
- how you checked that CI tested what lands, and any trial merge or new
  run it needed;
- the integration-branch SHA you broadcast, and every merge since the
  previous broadcast: the next broadcast lists what landed after it;
- the worker's wall-clock time, and its tool calls and tokens if the harness
  reports them;
- what worked, what it cost, and any follow-up it raised.

## A gotcha

Written when you add a gotcha to the brief template mid-arc: the gotcha as
the template now words it, and the friction that raised it.

## An unverified finding

Written when a hand-back reports a defect you cannot verify yet: the claim,
the worker and Issue that reported it, and what would verify it. Close-out
verifies and files each one from here, so none waits in a scratch file.

## A decision

Written when the user decides something that changes the arc: what was
decided, by whom, and what it changes. A decision about one Issue's scope
also goes on that Issue.

## The close-out

Written when the arc ends. A long arc that pauses gets the same entry,
headed as a pause, and stays open: its `state`, files and reservations are
unchanged until it resumes or ends.

- a timeline table: dispatches, merges, decisions and close-outs, with
  times;
- each hypothesis, and whether it held;
- the lessons, ranked. File each lesson about the repository as an Issue
  against its agent instructions and note it here. List the lessons about
  this skill for the user, who decides whether to report them upstream.
- the follow-ups filed, each as it arrived or at close-out, and the Issues
  outside the arc that inherited deferred scope;
- each Worktree the user removed despite listed sub-agents: the user's
  instruction, and each check's result.

When the arc ends, set `"state": "closed"` and `"closed"` in `arc.json`,
and remove your reservations. Leave the arc's directory in place. Offer
the user the closed arcs older than a month, yours and earlier ones, for
deletion, and delete only those they confirm.

## What goes to GitHub

Only these, each written to be read by anyone the repository is visible to:

- each PR, with its validation section;
- each follow-up and each repository lesson, filed as an Issue;
- a decision that changes one Issue's scope, as a comment on that Issue;
- a measurement that settles a downstream decision, on the Issue it
  settles;
- each Issue's closing comment;
- the arc's outcome: a comment mapping each Issue to its PR and merge
  commit, on the epic, or for a list on the Issue you bound; and for a
  list, a comment on each Issue the arc unblocked, with what landed and
  what it now needs.

Compose each from the primary source, not by copying ledger entries. Keep
out local paths, machine names and load, the user's circumstances,
credentials, and anything the user said they want kept private. Branch
names, PR links and SHAs are fine. Record the user's decisions as
decisions, and ask before quoting them. Post with `--body-file <file>`,
writing the file with a script or a quoted heredoc.
