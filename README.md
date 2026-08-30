# Dashpot

_Useful damping for agent-driven projects._

Dashpot is a passive terminal view of declared work, repository state, and active
coding-agent runs. It makes the small but important project-management pause
visible before another prompt or agent adds more motion.

Like its [mechanical namesake](https://en.wikipedia.org/wiki/Dashpot), Dashpot is
intended to reduce oscillation without stopping progress. Observation never
mutates: the view, every refresh, and `dashpot --json` never assign or edit
Issues, change the Git Repository, or control agent sessions. Dashpot's named
management commands — `init`, `integrate`, `work start` and `stop` — mutate
only what their name says, on explicit invocation, and report what they
changed ([ADR 0008](docs/adr/0008-let-management-commands-mutate-on-explicit-invocation.md)).

> [!NOTE]
> Dashpot is an early implementation extracted from a successful research spike.
> Its interfaces and packaging are not yet stable.

## What it observes

Everything below is read, never changed: observation's only writes are the
housekeeping of Dashpot's own ignored state, such as pruning the hook record of
a session that has ended.

- Projects with either GitHub Issues or Dashpot's Local Issue Markdown
- git Branches, Remote-Tracking Branches, worktrees, HEAD, and dirty state
- Codex and Claude Code lifecycle records published through opt-in hooks
- source freshness, failures, and last-good state
- durable Agent Run bindings through opaque Issue Identity

Each source remains independent in the read model. A failed Issue refresh, for
example, does not erase the last good Issue collection or hide repository facts.

## Usage

Open the TUI for a Project — Dashpot observes exactly one Project per run:

```bash
cd /path/to/configured/project
uv run dashpot

uv run dashpot --workspace personal=/path/to/project
uv run dashpot --workspace personal=/path/first-clone \
  --workspace personal=/path/second-clone
```

Without arguments, Dashpot observes the current directory when it contains
`.dashpot/config.json`. Outside a configured Project it loads explicit Repository
Anchors from Dashpot's `~/.config/dashpot/workspaces.json`. Explicit
`--workspace` arguments each name one anchor and take precedence; repeat the
same Workspace name to include independent clones of the same Project. Anchors
that resolve to more than one Project are refused with a message naming them
(see [ADR 0004](docs/adr/0004-observe-one-project-per-run.md)). Use `--config`
to select a different Workspace inventory.

The Header's title is `Dashpot` and its sub-title is the observed Project's
Repository Anchor path, or `passive workspace view` until the first
observation lands. The default 15-second polling period refreshes the
observed Project and can be changed with `--refresh-seconds`; zero disables
polling. `--timeout` bounds every external `git` and `gh` command (default 10
seconds), `--state-dir` overrides where session records land outside a
configured Project (the flag form of `DASHPOT_STATE_DIR`), and `--version`
prints the installed version. `dashpot --help` describes every command and
option, and each command has its own `--help`; an option belongs to the
command it follows, so the timeout for `init` is given as `dashpot init
--timeout 5`, not before `init`. Invalid input fails with a one-line
`dashpot: ...` diagnostic on stderr and exit code 2, the same as a startup
error.

### Keys

| Key | Action |
|---|---|
| `r` | Refresh the observed Project; `R` refreshes every observation in the Workspace, which is the same Project in a one-Project run |
| `1` `2` `3` `4` | Focus the Issues, Sessions, Branches, or Worktrees list; `Tab` / `Shift+Tab` cycle through them in that order |
| `/` | Focus the Issue search |
| `o` | Cycle the Issue table between open, closed, and all Issues (the `Open` / `Closed` / `All` selector beside the search does the same) |
| `s` / `S` | Sort by the next sortable column / reverse the current sort; clicking a column header sorts by it too |
| `c` | Open the column editor: toggle the visible Issue columns and reorder them with `Ctrl+Up` / `Ctrl+Down`; `Escape` cancels |
| Arrow keys | Move the row cursor in the focused list |
| `Enter` | On an Issue, read it full-screen (`Escape` returns); on a Session with an Issue Binding, highlight that Issue in the table |
| `q` | Quit |

The search box takes whitespace- or quote-separated terms matched against the
Issue's number, title, labels, Project, assignees, author, milestone, and
type, plus one `sort:` term — `sort:created`, `sort:updated`, or either with
an `-asc` / `-desc` suffix (`-desc` is the default) — which overrides the
column sort while it is present. A search the parser cannot read is reported
as a `Search:` error in Diagnostics rather than silently ignored. The count
beside the search box (`6 issues`) is the number of Issues matching every
active filter, never an `M of N` total. The Issue table's columns are `◉`
(Issue state) and `◈` (agent state), which are unsortable, then `#`, `TITLE`,
`LABELS`, `PROJECT`, `PRI`, `ASSIGNEES`, `AUTHOR`, `MILESTONE`, `TYPE`,
`COMMENTS`, `CREATED`, and `LAST ACTION`; `PRI` is read from a
`priority/p0`, `priority/p1`, or `priority/p2` label.

A Workspace inventory stores named groupings of anchor paths for one Project —
independent clones, never discovered or persisted worktree paths:

```json
{
  "workspaces": [
    {
      "name": "personal",
      "anchors": [
        "/home/me/projects/dashpot",
        "/home/me/independent-clones/dashpot"
      ]
    }
  ]
}
```

Relative anchor paths are resolved relative to the inventory file. Every anchor
is validated independently, and clones with the same Project Identity and
Repository Identity are presented as one Project. Anchor order is significant:
the first valid anchor for a Project supplies its display label and is the
authoritative checkout used for Issue collection.

On every refresh, Dashpot asks Git for the main and linked worktrees reachable
from every configured anchor. These runtime Observation Targets are deduplicated
by path and report branch or detached state, HEAD, dirty state, availability,
elapsed time, and target-specific diagnostics. Locked, prunable, missing, and
inaccessible targets remain visible without degrading the Project's Issue
Source. A Worktree locked by a running process is a coding agent working in
it, which is the steady state and is reported as nothing at all; the lock is
diagnosed once the process it names has exited, because that lock outlives its
session and keeps the Worktree from being pruned. Target inventory is never persisted, and Project-level Issues are still
collected exactly once from the authoritative anchor.

The same collector has a headless JSON interface:

```bash
uv run dashpot --workspace my-project=/path/to/project --json
```

The TUI uses each Project's mutable display label. Headless snapshots also
include its durable `projectId` and `repositoryId`, along with Workspace names
and Repository Anchors, so automation and diagnostics do not depend on labels or
paths for identity.

## Domain language

Dashpot uses the following terms consistently across its interface, code, and
documentation. The _Avoid_ notes distinguish similar concepts; they are usage
guidance rather than a conformance standard.

### Declared work

**Project**:
A durable body of work rooted in exactly one Git Repository. It remains the same
Project across checkout moves, clones, branches, and worktrees.

**Git Repository**:
The single logical Git repository that roots a Project. Its hosting location and
local checkouts may change without changing the Project.
_Avoid_: Repository when referring to a checkout path

**Repository Identity**:
A stable opaque identity for a Git Repository, independent of remote URLs and
local checkouts.

**Issue**:
A declared unit of Project work conforming to Dashpot's source-neutral Issue
model. An Issue may be represented on GitHub or in local Markdown.
_Avoid_: Task, work item

**Issue Profile**:
The source-neutral set of facts every Issue Source must provide for an Issue. A
profile is complete; unavailable source facts are observation failures rather
than ambiguous Issue values.

**Issue Provenance**:
Source-specific evidence identifying the representation from which an Issue was
observed. Provenance does not participate in semantic equivalence.

**GitHub Issue**:
The GitHub Issues representation of an Issue.

**Local Issue**:
The local Markdown representation of an Issue.

**Issue Source**:
The authoritative representation through which a Project declares its Issues.
A Project has exactly one active Issue Source.

**Project Identity**:
A stable opaque identity for a Project, independent of repository hosting and
local filesystem location.

**Project Display Label**:
A mutable, human-readable label for a Project. It helps people recognize a
Project but never participates in identity.
_Avoid_: Project name when identity is intended

**Issue Identity**:
A stable opaque identity for an Issue, globally unique within Dashpot's Issue
universe and independent of its Project membership, reference, and location.

**Issue Number**:
A positive Project-local integer used as an Issue's compact human label, such
as `#16`. It may change with Project membership and never participates in Issue
identity.

**Issue Reference**:
A mutable, human-readable shorthand for an Issue, such as `ned2/dashpot#9` or a
local slug.

**Issue Location**:
An actionable, mutable locator for an Issue, such as a GitHub URL or a Markdown
file and line number.

### Observation

**Workspace**:
The named set of Repository Anchors that resolves to the one Project a Dashpot
run observes. It owns no Project configuration or work state and never
participates in Project or Issue identity; anchors resolving to more than one
Project are refused before observation starts.

**Repository Anchor**:
A configured local checkout through which Dashpot locates a Project and asks Git
for its linked worktrees. It is also the authoritative checkout for Local Issues.

**Worktree**:
A local working tree of a Project's Git Repository, including its main working
tree and any Git-linked working trees.

**Observation Target**:
A Worktree Dashpot discovered and refreshes at runtime. It is observed state,
not persisted Workspace membership or durable identity.

**Branch**:
A named line of development of a Project's Git Repository, observed as a
local ref (`refs/heads/*`) and as any Remote-Tracking Branches of the same
name. Identity is the full refname; a branch name that is only local or only
remote is a fact about the branch, not a different kind of record.

**Remote-Tracking Branch**:
The Repository's local copy of a remote's branch (`refs/remotes/<remote>/*`),
as of the last `git fetch`. Dashpot reads it and reports its age; it never
fetches.
_Avoid_: remote branch for the local copy, which may be behind the remote

**Observation Location**:
Where an agent session is executing, such as a branch, Worktree, or working
directory. It is evidence about execution, never Project or Issue identity.

**Agent Session**:
The lifetime of one harness conversation or process, such as a single Codex
run. A session is never permanently bound to an Issue; its lifecycle state
(running, waiting, or unknown) and activity age (how long the current turn
has run, or how long it has been idle) are observations of the session
itself, taken at turn boundaries.

**Agent Run**:
A time-bounded period during one Agent Session when it is explicitly working
on exactly one Issue. Starting, switching, or stopping Issue work begins or
ends Agent Runs without ending or restarting the session. A live Agent
Session holds at most one active Agent Run across the linked Worktrees of one
Git Repository: a session that has moved to another Worktree of the same
Repository and starts work there switches its run rather than adding one
([ADR 0009](docs/adr/0009-hold-one-agent-run-per-session-across-worktrees.md)).
_Avoid_: Agent Run as a synonym for the whole session; a second run at
another Worktree for a session that has relocated

**Agent Session Identity**:
The stable, opaque identity a harness gives one Agent Session, as its
lifecycle hooks publish it. It identifies the session where its host process
cannot be observed, such as from a sandbox's isolated process namespace, and
is only ever accepted when the harness's own hook record confirms it.
_Avoid_: session key, which is the Work Store's record name, and process
identity, which is evidence of Session Liveness

**Harness Adapter**:
The per-harness contract through which Dashpot identifies an Agent Session
from a command running inside it: which host process is the harness itself
(never a sandbox helper) and what Agent Session Identity the command can see.
Work Store and observation code speak to the adapters and never to one
harness's internals.

**Session Liveness**:
An observation of whether an Agent Session's recorded host process is live,
gone, or unknown. Unknown means the process could not be observed and is never
evidence that the session ended.

**Orphaned Agent Run**:
An active Work Store record whose Agent Session is gone. It is actionable
because it affects declared Issue work; a gone session without one is only
stale observation state.
_Avoid_: orphaned session for a gone unbound session

**Work Store**:
The versioned, Project-local record of active Agent Runs. Each record is
stored beneath the Worktree its run is at (`.dashpot/state/`), and the records
at all linked Worktrees of one Git Repository are jointly the sole authority
for which sessions are working on which Issues in that Repository
([ADR 0009](docs/adr/0009-hold-one-agent-run-per-session-across-worktrees.md)).
Independent clones keep distinct Work Stores
([ADR 0003](docs/adr/0003-prefer-project-local-configuration-and-work-state.md)).
_Avoid_: treating one Worktree's records as the whole authority for a session
that may have moved to another Worktree of the same Repository

**Issue Binding**:
A durable association between an Agent Run and an Issue by Issue Identity,
created by an explicit opt-in from the running session and stored in the Work
Store. It survives changes to Project membership, Issue Reference, and Issue
Location and is observed relationship state rather than part of the Issue
entity.

**Issue Hint**:
A mutable Issue Reference used only to establish an Issue Binding at opt-in
time. A hint never becomes identity and must resolve unambiguously within the
observed Project.

## Development setup

Dashpot requires Python 3.11 or newer and uses
[uv](https://docs.astral.sh/uv/) for its locked development environment.

```bash
uv sync --locked --group dev
uv run pre-commit install
uv run pytest -q
```

### Quality gates

[`.pre-commit-config.yaml`](.pre-commit-config.yaml) is the shared quality
gate. `uv run pre-commit install` enables two sets of hooks for the checkout:

- **On commit**: repository hygiene checks (whitespace, line endings, YAML,
  TOML and JSON syntax, merge-conflict markers, stray debug statements, private
  keys, large files), then [Ruff](https://docs.astral.sh/ruff/) lint with safe
  fixes, then `ruff-format`, then [ty](https://docs.astral.sh/ty/) static type
  checking. Ruff's rule selection and ty's rule levels live in
  [`pyproject.toml`](pyproject.toml).
- **On push**: the full local gate in
  [`scripts/check_quality.py`](scripts/check_quality.py), which verifies the
  lockfile, Ruff lint and formatting, ty, the test suite, and the distribution
  build for the exact revision being pushed, in a temporary detached worktree.

Run the commit hooks across every tracked file:

```bash
uv run pre-commit run --all-files
```

Run the full gate directly against the working tree:

```bash
uv run python scripts/check_quality.py
```

Ruff fixes and formatting are idempotent: a second `--all-files` run after the
first has fixed something is clean. Hook revisions are pinned to frozen commit
SHAs; refresh them with

```bash
uv run pre-commit autoupdate --freeze
```

and bump the matching `ruff` and `ty` versions in `uv.lock` (`uv lock
--upgrade-package ruff --upgrade-package ty`) so the hooks and `uv run` agree.
First-time hook setup downloads the pinned hook environments, so it needs
network access.

### Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pull requests
targeting `main`, pushes to `main`, and manual dispatch. It runs the all-files
pre-commit quality gate once on Ubuntu, tests the locked environment on Ubuntu
and macOS under Python 3.11 and 3.14, and builds the package once per run. No
credentials are provided and no live GitHub collection happens in CI; the test
suite exercises Issue collection against fakes.

Every CI verification step has an exact local equivalent:

```bash
# Verify uv.lock matches pyproject.toml
uv lock --check

# Install the locked development environment
uv sync --locked --group dev

# Run the all-files quality gate
uv run pre-commit run --all-files

# Run the full test suite
uv run pytest -q

# Build the wheel and source distribution into dist/
uv build
```

## Project configuration

Configure a repository as a Dashpot Project with `dashpot init`, run from
anywhere inside its worktree. With a GitHub `origin` remote it asks nothing:
the Issue Source defaults to GitHub Issues and the durable repository identity
is resolved through the authenticated `gh` CLI. Without one, declare a Local
Issue Markdown source instead:

```bash
dashpot init
dashpot init --markdown issues
```

`dashpot init` never overwrites an existing configuration, and running
`dashpot` in an unconfigured repository never writes anything; it reports how
to proceed.

Every Repository Anchor has a tracked `.dashpot/config.json` containing stable
Project and Repository identities, a mutable display label, and the active
Issue Source. The `.dashpot/state/` directory holds ignored local runtime
state; add it to your repository's `.gitignore` so it never dirties the
worktree or gets committed:

```gitignore
.dashpot/state/
```

A GitHub-backed Project looks like this:

```json
{
  "projectId": "project:01947e42-3f67-7c38-a41c-218df18a169b",
  "displayLabel": "Dashpot",
  "repositoryId": "R_kgDOUEerrg",
  "issueSource": {
    "kind": "github"
  }
}
```

The Repository Anchor must have a GitHub `origin`; collection uses the
authenticated `gh` CLI. A Local Issue Markdown Project selects a repository-
relative file or directory:

```json
{
  "projectId": "project:01947e42-3f67-7c38-a41c-218df18a169b",
  "displayLabel": "Dashpot",
  "repositoryId": "repository:01947e42-4f18-74d1-b25f-329ef29b270c",
  "issueSource": {
    "kind": "markdown",
    "path": "issues"
  }
}
```

The owned file grammar is documented in
[`conformance/issue/local-markdown.md`](conformance/issue/local-markdown.md).
Both adapters collect the complete source inventory, including open and
closed Issues; source collection does not apply a lifecycle filter. The TUI
defaults its Work list to open Issues. Both adapters are currently read-only.

## Agent session observation

Installing Dashpot provides the no-stdout `dashpot-codex-hook` and
`dashpot-claude-code-hook` publishers. Nothing is installed into a harness
automatically; register the lifecycle hooks once per user with:

```bash
dashpot integrate codex                 # hooks in ~/.codex/hooks.json
dashpot integrate claude-code           # hooks in ~/.claude/settings.json
dashpot integrate <harness> --status    # diagnose config, publisher, records
dashpot integrate <harness> --remove    # remove exactly the Dashpot hooks
```

Installation performs a surgical merge of the harness's user-level hook file:
existing hooks and unrelated settings are preserved, the registered command is
the absolute path of this environment's publisher (so hook and observer
versions stay in lock-step), and rerunning `integrate` is idempotent and
repairs stale paths. Removal deletes only the Dashpot handlers. If Codex hooks
are also defined inline in `~/.codex/config.toml`, Dashpot leaves that file
alone and points out that Codex merges both layers.
[`examples/codex-hooks.json`](examples/codex-hooks.json) shows the equivalent
manual Codex configuration.

The hooks report session lifecycle only: which agent sessions are alive at a
worktree and whether they are running or waiting. Codex registers
`SessionStart`, `UserPromptSubmit`, `Stop`, `Interrupt`, and `SessionEnd`;
Claude Code the same set without `Interrupt`, plus `PostToolUse` matched to
its `EnterWorktree` tool alone, so a session that moves to another Worktree
is placed there as soon as it arrives — one hook invocation per relocation,
never per tool call
([ADR 0009](docs/adr/0009-hold-one-agent-run-per-session-across-worktrees.md)).
A session that has not
declared an Issue is not listed as Work; it is listed in the Sessions pane
with `no active Issue work` until it opts in with `dashpot work start`. Codex and Claude
Code sessions are observed side by side with distinct identities, and both may
work on the same Issue as separate Agent Runs. One user-level installation per
harness covers every configured repository, including linked worktrees: each
observation is routed to the checkout the session runs in, landing in that
worktree's ignored `.dashpot/state/sessions/`. Sessions outside any
Dashpot-configured checkout fall back to the platform's normal
application-state location; set `DASHPOT_STATE_DIR` to override that fallback.

Each refresh checks that a session's recorded process is still the one that
published the record. A graceful `SessionEnd` removes the session's record. A
session that was killed, or whose `SessionEnd` hook never ran, is dropped
quietly and its stale record and lock file are cleaned up; it only becomes a Diagnostics
warning when it leaves an orphaned Agent Run behind (see below). When the
process cannot be observed at all (for example from inside a sandboxed process
namespace) the session is shown with `unknown` state rather than assumed to
have exited. `dashpot integrate <harness> --status` classifies every session
record as live, unknown, stale, or unreadable and lists the stale ones, which
is where to look when lifecycle events seem not to be delivered.

Every hook record carries the harness's own Agent Session Identity (its hook
`session_id`) beside the host process the hook observed from outside any
sandbox. Observation joins a Work Store record to its hook record by that
identity when the record carries one, and by host process identity otherwise,
so a run opted in from a sandbox adopts the same running/waiting state, and
is listed once in the Sessions pane, as one opted in from a plain shell.
Liveness and orphan detection still follow the host process: a session's
hooks always run on the host, so its record names the harness process even
when the session's own commands cannot see it.

## Issue work opt-in

An agent session declares which Issue it is working on from inside the
session, at the worktree where the work happens:

```bash
dashpot work start 123         # a bare Issue Number
dashpot work start '#123'      # the same Issue, # quoted for the shell
dashpot work start owner/repository#123   # or a full Issue Reference
dashpot work show              # list active Issue work at this worktree
dashpot work stop              # end this session's run; the session stays alive
dashpot work stop --session KEY  # end the orphaned run of a session that is gone
```

A bare number and its `#`-prefixed form resolve to the same Issue; Local
Issue Markdown Projects also accept the Issue's slug.

`dashpot work start` resolves the Reference against the Project configured at
that worktree, requires it to identify exactly one currently observed Issue,
and atomically records the resulting durable Issue Identity in the Project-local
Work Store (`.dashpot/state/work/`). Running `start` again switches the session
to a new Issue. A session holds one active run across the linked Worktrees of
its Git Repository
([ADR 0009](docs/adr/0009-hold-one-agent-run-per-session-across-worktrees.md)),
and its own hooks say where it is: the freshest hook record for the session
across the stores of every Worktree `git worktree list` reports, plus the
global store. When that record places the session at the Worktree where
`start` runs, a run it still holds at another Worktree is a relocation (a
Claude Code `EnterWorktree`): `start` ends it and reports
`switched from <ref> at <old Worktree> to <ref> at <new Worktree>`. When it
places the session elsewhere, the command is running where the session is
not — a tool call that changed directory, or a sub-agent's shell — and
`start` refuses, names that Worktree, and writes nothing. `stop` ends the
session's run wherever in the Repository it is recorded. A session with no
hook record anywhere starts where it runs, as before, so the invariant is
enforced only once the harness hooks are installed; runs recorded by an older
Dashpot, or across independent clones, keep the `work-session-conflict`
warning. Once recorded, the binding survives
repository renames, Issue Reference edits, Local Issue moves, and transfers
between configured Projects.
The ordinary TUI continues to show current References; raw identities remain in
headless output and diagnostics.

### How the session is identified

`dashpot work start` and `stop` identify the enclosing Agent Session through
one harness-neutral seam with a [Harness Adapter](#domain-language) per
supported harness (`src/dashpot/harnesses.py`), by two routes:

1. **Host process ancestry.** The command walks up its parent processes to
   the nearest Codex or Claude Code process, as it always has. A sandbox
   helper such as `codex-linux-sandbox` or `bwrap` is never taken for the
   harness. This route is authoritative whenever it works; the record is keyed
   by that process, and the harness's Agent Session Identity is recorded
   beside it when the environment names one that the hook record corroborates.
2. **Agent Session Identity.** When the ancestry is hidden — Codex's
   `codex-linux-sandbox` and Claude Code's bubblewrap sandbox each run the
   command as PID 2 of a fresh PID namespace — each adapter reads the identity
   its harness exposes to commands (Codex its thread identifier, Claude Code
   its session identifier and host PID). Neither harness documents these as
   stable, so a claim is never trusted on its own: its freshest lifecycle
   hook record for the same harness across the Repository's hook stores
   (each Worktree's `.dashpot/state/sessions/` and the global store) must
   still describe a live or unknown session, and for Claude Code the record's
   host PID must agree; a stale record left at a Worktree the session moved
   away from never confirms a `start` there. The record
   is then keyed by the host process the hook published, so the same session
   gets the same record whether or not its commands are sandboxed, and
   liveness and orphan detection work as before; a record whose hook never saw
   a host process is keyed by the identity's digest instead. `start`, switching
   Issues, and `stop` all resolve the session the same way, and a record
   written before this identity existed is adopted by the same session rather
   than duplicated.

A missing, unreadable, ended, gone, cross-harness, or PID-mismatched hook
record refuses the opt-in with a message naming the record and the
`dashpot integrate <harness> --status` check to run, and writes nothing. When
the environment names live sessions of both harnesses — a Codex session
started from inside a Claude Code shell inherits both — the opt-in is refused
as ambiguous until `DASHPOT_AGENT_SESSION=<harness>:<session id>` states which
session the command belongs to; that explicit claim is validated like any
other. `dashpot integrate <harness> --status` reports the identity the
current environment claims for that harness and whether its hook record here
confirms or rejects it, which is the first thing to check when a sandboxed
`work start` is refused.

The Work Store is the sole authority for Issue association. Collection
correlates each recorded run with the hook's lifecycle observations by Agent
Session Identity or process identity (see
[Agent session observation](#agent-session-observation)); a hook record
that carries a global Issue binding (the retired
`DASHPOT_ISSUE_ID`/`DASHPOT_ISSUE_REF` environment convention) is rejected with
a diagnostic pointing at `dashpot work start`, never silently combined. When a
session is gone but its Work Store record remains, that record is an orphaned
Agent Run: it is excluded from the listed runs and reported once as an
actionable `work-session-orphaned` diagnostic naming the Issue and the
`dashpot work stop --session <key>` command that ends it. Dashpot never stops
or reassigns Issue work on its own.

## Design

Observation is scheduled per key rather than as one refresh: the Project's
Issue Source and its worktree topology are observed independently, and Agent
Runs are observed once per Workspace whenever the Project has been published. An
[`ObservationCoordinator`](src/dashpot/collect.py) tracks a generation per key
so a superseded observation can never overwrite a newer one, retains the last
good result per key when a refresh fails, and composes each Project from its
latest accepted halves. The Textual interface publishes every accepted
observation into a process-local `WorkspaceObservationStore` as soon as it
lands, then re-queries source-neutral Issue-list read models carrying a store
revision; a slow GitHub call therefore never delays branch or dirty state.
`r` refreshes the observed Project and `R` fans out to every key in the
Workspace; with one Project per run the two coincide. Exceptional state is summarized in a
one-line alert above Diagnostics that takes no space while everything is
healthy: refresh failures and unavailable Projects are errors, unavailable or
stale worktrees and stale Issue Sources are warnings, and a refresh that has
been running longer than a moment is shown as information. The alert is
derived from current observations and clears itself on recovery; toasts are
reserved for manual-refresh failures and their recovery, and Diagnostics keeps
the durable detail: the box takes no space while it is empty and is coloured
by the most severe line it holds. Headless JSON runs a coordinated barrier
over every key and serializes the store's `checkpoint()`, so it remains one
complete snapshot. Collection happens off the UI thread, and the table is
reconciled by stable row keys.

The main screen is a single pane of glass: the Header sub-titles `Dashpot`
with the observed Project's Repository Anchor path, and below it
the full-width `SESSIONS`, `BRANCHES` and `WORKTREES` panes stack above the
full-width `ISSUES` table. Nothing is switched to: every active Agent
Session, every observed Worktree and every Branch is listed in its pane, with
the count in the pane title and an honest one-line empty state. The panes are
sized to their content rather than sharing the flex height: each asks for the
rows it has up to a cap of eight and scrolls beyond it, the smallest wish is
granted first so an empty pane costs three lines, and the caps shrink before
the Issue table would drop below its minimum height, so the panes only ever
cost the Issue table what they actually use. `Tab` and `Shift+Tab` cycle focus
Issues → Sessions → Branches → Worktrees, `1`, `2`, `3` and `4` jump to a
list and `/` to the Issue search. The row cursor in the Sessions, Branches
and Worktrees panes is for scrolling, copying and refresh scope (`r`); only
the Issue table drives the Issue selection, `Enter`
on an Issue opens it in the full-screen Issue view (its location on the left
of the heading line, `opened 3d ago by ned2` on the right, and both panes'
borders in the Issue's state colour), and `Enter` on a session with an Issue
Binding highlights that Issue in the Issue table. The Sessions pane is its own read model
([`session_list.py`](src/dashpot/session_list.py), queried through
`WorkspaceObservationStore.query_sessions`): every active Agent Session of the
observed Project exactly once, sorted running → waiting → unknown and then by
most recent activity, with any bound Issue joined from the Work Store's
accepted bindings, an `outside Project` marker in place of a target the
observed Project does not own, an intentional `no active Issue work` value
when unbound, its working directory relative to its Observation Target, and
long paths, branches and titles clipped with an ellipsis. Its columns are
`STATE`, `HARNESS`, `TARGET`, `BRANCH`, `ISSUE`, `DIRECTORY`, and
`ACTIVITY`. `TARGET` is dropped
altogether while every listed session shares one Observation Target, which is
the usual shape of a Project with no linked Worktrees; it returns as soon as a
session sits in another Worktree or outside the Project. Exactly one column
names the Target, so while `TARGET` is dropped the working directory is shown
in full (`~`-abbreviated) rather than relative to a Target the pane no longer
displays. `ACTIVITY` names the age it is showing rather than leaving one
number to mean two things: `running 14m` is how long the current turn has
been going, `idle 14m` is how long the session has been quiet since its last
observed event, and `started 3d ago` is a run nothing has observed yet, whose
Work Store start time is reported as the different fact it is. Activity is
observed at turn boundaries and not within a turn, which is a measured
decision rather than an omission
([ADR 0006](docs/adr/0006-observe-agent-activity-at-turn-boundaries.md)). The Worktrees pane
is likewise its own read model ([`worktree_list.py`](src/dashpot/worktree_list.py),
`WorkspaceObservationStore.query_worktrees`): every observed Observation
Target of the Project, identified by `(Project Identity, target path)`
and sorted main before linked, then path, with the Git
topology role `git worktree list` reported beside the path, whether the path is a configured Repository Anchor,
and exceptional `stale` or `unavailable` state. Its four columns are `PATH`,
`BRANCH`, `TREE`, and `SESSIONS`: normal Branches omit HEAD, detached checkouts
include their short HEAD, the working tree remains clean/dirty/unknown, and
the last column counts the active Agent Sessions located there. Healthy rows
do not repeat `available`. Target-specific diagnostics stay in Diagnostics
and the alert line; the row only points there. The
Branches pane ([`branch_list.py`](src/dashpot/branch_list.py),
`WorkspaceObservationStore.query_branches`) joins the local ref and the
Remote-Tracking Branches of one branch name into one row, so a branch is
never listed twice and never needs a second pane: `WHERE` says where it exists
(`local`, `local · origin`, or `origin` alone for a branch pushed from
elsewhere), `SYNC` is the local ref's relation to its upstream (`✓` in sync,
`↑2 ↓1`, `○` unpushed, or `✗` upstream gone), then the Worktree it is checked out
in, the active sessions on it, and the age of its last commit. Rows are sorted checked-out first, then most recent commit. The
refs are read with `git for-each-ref` from the first answering Repository
Anchor; Dashpot never runs `git fetch`, so the lower-right pane border carries
the age of the last fetch (`remote last fetched 3h ago`, or
`remote never fetched`) as the honest freshness of everything remote
([ADR 0005](docs/adr/0005-observe-branches-without-fetching.md)). See
[`docs/textual-implementation-notes.md`](docs/textual-implementation-notes.md) for
the framework research behind the current implementation.

## Contributing

Every change lands on `main` the same way, whether a human or an agent makes
it:

1. Branch from `main` for the change.
2. Commit with the commit hooks installed. A commit message line `Closes #N`
   is what closes the Issue on GitHub once the commit reaches `main`.
3. Fast-forward `main` onto the branch and `git push origin main`. The
   pre-push hook runs the full gate in
   [`scripts/check_quality.py`](scripts/check_quality.py) against the pushed
   revision in a detached worktree, so a red gate stops the push.
4. Watch CI to completion with `gh run watch <id> --exit-status`; the change
   is done when the run is green.

Agent sessions additionally declare the Issue they are working on with
`dashpot work start` (see [Issue work opt-in](#issue-work-opt-in)); the
expectations on agents themselves are in [`AGENTS.md`](AGENTS.md).

## Documentation map

The [domain language](#domain-language) defines the terms used in the interface,
code, and documentation, including phrasings to avoid.
[`docs/adr/`](docs/adr/) records architectural decisions, one ADR per
decision. The other files in [`docs/`](docs/) are research, audits, and active
proposals that inform decisions and implementation. The proposed agent worktree
protocol is under review in
[`docs/proposed-agent-worktree-protocol.md`](docs/proposed-agent-worktree-protocol.md);
[`docs/textual-implementation-notes.md`](docs/textual-implementation-notes.md)
records the framework research behind the current interface.
[`conformance/`](conformance/) documents owned file grammars.

## License

MIT
