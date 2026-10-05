# Dashpot

_Useful damping for agent-assisted projects._

A terminal dashboard for agent-assisted projects that brings your Issues, Pull
Requests, Branches, Worktrees, and live Codex, Claude Code, and OpenCode Agent
Sessions together in one view. Issues can come from GitHub or from Local Issue
Markdown in the repository. Dashpot makes the small but important project-management
pause visible before another prompt or agent adds more motion.

Like its [mechanical namesake](https://en.wikipedia.org/wiki/Dashpot), Dashpot is
intended to reduce oscillation without stopping progress. Observation never
mutates: the view, every refresh, and `dashpot --json` never assign or edit
Issues, change the Git Repository, or control agent sessions. Dashpot's named
management commands — `init`, `integrate`, `work start`, `work relocate`,
`work stop`, `work forget-subagents`, `work assign`, `work unassign`,
`branch delete`, `worktree create`, `worktree remove`, and
`events remove` — and its two mutating keys — `f`, which fetches Git remotes, and `x`, which deletes a Branch or
removes a Worktree — mutate only what their name says, on explicit invocation,
and report what they changed
([ADR 0008](docs/adr/0008-let-management-commands-mutate-on-explicit-invocation.md),
[ADR 0014](docs/adr/0014-fetch-remotes-on-explicit-key-press.md)). A Cleanup
goes one step further: it deletes only the targets a person selected from a
read-only preview and confirmed
([ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).

> [!NOTE]
> Dashpot 0.1.0 is being prepared as its first alpha release. Publication and
> real-host acceptance are tracked in [#5](https://github.com/ned2/dashpot/issues/5).
> The [release policy](docs/adr/0034-publish-an-alpha-with-patch-compatible-interfaces.md)
> preserves documented interfaces within 0.1.x.

## What it observes

Everything below is read, never changed: observation's only writes are
Dashpot's own ignored runtime state, such as
pruning the hook record of a session that has ended.

- Projects with either GitHub Issues or Dashpot's Local Issue Markdown
- GitHub Pull Requests across their lifecycle, including review, checks, and mergeability
- git Branches, Remote-Tracking Branches, worktrees, HEAD, and dirty state
- Codex and Claude Code lifecycle records published through opt-in hooks, and
  OpenCode's through an opt-in plugin
- source freshness, failures, and last-good state
- durable Agent Run bindings through opaque Issue Identity

Each source remains independent in the read model. A failed Pull Request
refresh, for example, retains its last good collection without degrading a
healthy Issue Source or hiding repository facts. A Local Issue Markdown
Project reports Pull Requests as not configured rather than inferring a host
from its Git remotes.

## Supported harnesses

Dashpot observes Agent Sessions of three coding-agent harnesses. Each is
supported at the release its [acceptance run](#harness-acceptance-runs) last
passed on, on Linux. These are accepted releases, not minimum versions: other
releases are unsupported until that run passes on them, and no lower bound has
been established yet. Supporting newer releases without a new acceptance run,
and finding each harness's real lower bound, is tracked in
[#416](https://github.com/ned2/dashpot/issues/416).

| Harness | Observed through | Accepted release | Other releases |
| --- | --- | --- | --- |
| [Codex](docs/agent-sessions.md#codex-hosting-modes) | Lifecycle hooks | `codex-cli` 0.160.0 | Not checked: Dashpot does not read the Codex release |
| [Claude Code](docs/agent-sessions.md#claude-code-hosting-modes) | Lifecycle hooks | 2.1.287 | Not checked: Dashpot does not read the Claude Code release |
| [OpenCode](docs/agent-sessions.md#opencode-hosting-modes) | A plugin | 2.0.22 | 1.x is refused; another 2.x release is observed with a warning; a later major release is warned about and not observed ([details](docs/installation.md#observe-agent-sessions)) |

Install a harness's integration with `dashpot integrate codex`,
`dashpot integrate claude-code`, or `dashpot integrate opencode`, or several
at once, and refresh every integrated one after an upgrade with `dashpot
integrate --installed`; see
[Agent session observation](#agent-session-observation).

## Installation

Once the first release is published, install Dashpot in an isolated tool environment:

```bash
uv tool install --python 3.14 dashpot
```

The release targets CPython 3.13–3.14 on Linux x86-64 and Apple Silicon macOS,
Git 2.39+, and gh 2.100.0+ for GitHub-backed Projects. See
[installation and support](docs/installation.md) for current host-validation
status, candidate installation before publication, PATH setup, harness setup,
diagnosis, upgrades, and uninstall instructions.

For a repository with a GitHub `origin`, authenticate `gh`, run `dashpot init`,
commit `.dashpot/config.json`, then run `dashpot`. For a Project
without GitHub, create an `issues` directory and use `dashpot init --markdown
issues`; that source uses the [Local Issue Markdown grammar](conformance/issue/local-markdown.md).

### GitHub authentication

A GitHub-backed Project requires an authenticated GitHub CLI. Dashpot keeps
no credential of its own: it asks GitHub every question through `gh`, as
whichever account `gh auth status` reports. Run `gh auth login` before
`dashpot init`. The account must be able to read the repository, its Issues
and its Pull Requests. A Project whose Issue Source is Local Issues needs
neither `gh` nor a login. A `GH_TOKEN` that a directory-scoped mechanism such
as a direnv `.envrc` supplies in the main checkout may not reach a linked
Worktree, or an agent's commands there:
[Credentials in a linked Worktree](docs/installation.md#credentials-in-a-linked-worktree)
gives what each harness's commands receive and the operator-local options.

GitHub's rate limit constrains how Dashpot can be used. Nearly every query
Dashpot sends is GraphQL, and a personal account gets 5,000 GraphQL points an
hour whatever its plan. That allowance is shared by every tool acting as the
same user, including `gh` run by agents. An open dashboard spends points on
every automatic refresh of its GitHub queries, once a minute by default, so
several dashboards at once or a short `--github-refresh-seconds` can exhaust
the hour, leaving GitHub observations stale until it resets. [GitHub rate limits](docs/github-rate-limits.md) gives the
limits for each authentication method, how Dashpot spends them, and how to
stay inside them.

## Usage

Open the TUI for a Project — Dashpot observes exactly one Project per run:

```bash
cd /path/to/configured/project
dashpot

dashpot --workspace personal=/path/to/project
dashpot --workspace personal=/path/first-clone \
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

Two Refresh Periods pace automatic refresh
([ADR 0056](docs/adr/0056-refresh-github-queries-on-their-own-period.md)).
Local observation (Worktrees, Branches, Agent Sessions, and a Local Markdown
Issue Source) refreshes every 15 seconds, set by `--refresh-seconds`. GitHub queries
(both pages, Project Totals and bound Issues) refresh every 60 seconds, set by
`--github-refresh-seconds`. Each can also be set in the
[machine-local settings](docs/installation.md#machine-local-settings) as
`refresh_seconds` and `github_refresh_seconds`. A flag overrides its setting,
and zero disables that period's automatic refresh; `r` refreshes both at once.
GitHub refreshes pause while nobody attends the dashboard: when every tmux
client has detached from its session, or after two hours without a key or
mouse event, set by `--unattended-seconds` or `unattended_seconds`, where zero
disables the idle pause. Any key resumes them at once
([ADR 0068](docs/adr/0068-pause-github-queries-while-the-dashboard-is-unattended.md)).
`--timeout` bounds every external `git` and `gh` command (default 10
seconds); a named mutation's Git commands — a Remote Fetch, a confirmed
Cleanup, `worktree create`'s `git worktree add` — get at least five minutes
([ADR 0014](docs/adr/0014-fetch-remotes-on-explicit-key-press.md)).
`--state-dir` overrides where session records land outside a
configured Project (the flag form of `DASHPOT_STATE_DIR`), and `--version`
prints the installed version. `dashpot --help` describes every command and
option, and each command has its own `--help`; an option belongs to the
command it follows, so the timeout for `init` is given as `dashpot init
--timeout 5`, not before `init`. Every command failure — invalid input, a
startup error, or a refused operation — is a one-line `dashpot: ...`
diagnostic on stderr and exit code 2, with no traceback. Beside observation,
the management commands `init`, `integrate`, `work start` / `relocate` /
`stop` / `forget-subagents` / `assign` / `unassign`, `worktree create` /
`remove`, `branch delete`, and `events remove`, and the read-only commands
`work show`, `issue show`, `worktree check`, and `events`, are documented in
[Project configuration](#project-configuration),
[Agent session observation](docs/agent-sessions.md#agent-session-observation),
[Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in),
[Issue Worktrees](#issue-worktrees), and
[the Event Log](docs/installation.md#read-the-event-log).

### Keys

| Key | Action |
|---|---|
| `1` / `2` | Switch directly between Dashboard and Issues & Pull Requests; the complete labels in the top status bar are clickable too |
| `Ctrl+Shift+Left` / `Ctrl+Shift+Right` | Move to the previous or next Peer Screen, wrapping at either end; these global shortcuts remain active while editing a query |
| `r` | Restart both submitted queries from page one, refresh Project Totals, relevant Issue identities and local observations |
| `Enter` in Worktrees | Open the selected Worktree in a new tmux pane or through the configured launcher |
| `y` in Worktrees | Send the full Worktree path to the terminal clipboard |
| `y` in Sessions | On an Orphaned Agent Run, send the command that resumes its session to the terminal clipboard |
| `f` on Dashboard | Fetch and prune the Git remotes of the Repository Anchor behind the Branches pane; also available inside both Cleanup dialogs |
| `x` on Dashboard | Preview removing the highlighted Worktree or deleting the highlighted Branch, then confirm; `Escape` cancels. Optional additional targets start unchecked ([ADR 0036](docs/adr/0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md)) |
| `Tab` / `Shift+Tab` | Cycle through only the active peer's tables: Sessions → Worktrees → Branches, or Pull Requests → Issues |
| `/` on Issues & Pull Requests | Focus the active query pane's search |
| `o` on Issues & Pull Requests | Cycle the focused query pane's lifecycle — open, Ready (Issues only), closed, and all records (the selector beside its search does the same) |
| `n` / `p` on Issues & Pull Requests | Move the focused query pane to its next or previous retained page |
| `g` on Issues & Pull Requests | Restart the focused query pane from its first page |
| `c` with Issues focused | Open the column editor: toggle the other Issue columns and reorder them with `Ctrl+Up` / `Ctrl+Down`; `Escape` cancels |
| Arrow keys | Move or scroll the focused list; `Down` at the last row and `Up` at the first row cycle within the active peer; the newly focused pane's cursor is where it was last left |
| `Enter` | On an Issue, read it full-screen (`Escape` returns); opens a Worktree only from the Worktrees pane and is unbound on Sessions and Pull Requests |
| `?` | Open the Legend: every column's description with its Glyphs, pane by pane, and the keys; `Escape` closes, `End` and `Home` scroll. Resting the mouse on any column header shows the same description as a tooltip |
| `e` on a Peer Screen | Open the full-screen Runtime screen on its Events tab: this dashboard's last hour of Runtime Events at every level, newest last, with every field of the selected event beside the table (below it under 90 columns). Show, Kind and Errors-only filters last until the dashboard exits; the table follows new events until you move back through it, and `End` follows again. The command palette (`Ctrl+P`) offers it as Runtime Events ([design](docs/observability-design.md#reading)) |
| `s` on a Peer Screen | Open the Runtime screen on its Stats tab: the GitHub allowance and the points each operation spent, refresh health by trigger and by key, commands by program, and this dashboard's version, uptime, memory and Event Log, computed from its last hour of Runtime Events and updated while open; the palette offers it as Runtime Stats. Inside the screen `e` and `s` switch tabs, `l` changes the Event Level for this run only, and `Escape` alone closes it |
| `q` | Quit |

Dashboard is the default peer. Its Sessions, Worktrees and Branches panes are
separate from the Pull Requests and Issues query peer. Each long-lived peer
keeps its focused control, row cursors, scroll positions, lifecycle choices,
submitted queries and unsubmitted search text while the other is active; a
pane's first entry starts at its first row. Passive refreshes preserve selected
row identity. Issue Detail, Legend, Runtime and Cleanup cover their
originating peer, and `Escape` returns there; all Peer Screen keys, `e` and `s`
included, are inactive on those temporary screens. `1` and `2` insert text normally while an editable input has focus;
`Ctrl+Shift+Left` and `Ctrl+Shift+Right` remain global screen navigation there
rather than selecting query text by words.

The shared status bar shows exactly `Open PRs: N | Open Issues: N` from Project
Totals. `-` means a total is unavailable. `◆` means every displayed number is
fresh and `◇` means at least one is retained and stale; no freshness mark is
shown when neither total is numeric. The aggregate Glyph follows one final `|`,
and both states use a muted neutral colour so freshness remains available
without competing with signal-bearing Glyphs. At compact widths the summary
wraps below the complete peer labels. One blank terminal row separates the
status bar from the first content pane and separates each later pane from its
predecessor.

Dashboard panes grow toward their complete inventories when terminal height is
available. A small or empty pane keeps only the height it needs and donates the
rest; when the inventories cannot all fit, panes with remaining rows share the
live height and scroll independently. Pull Requests remains bounded to eight
content lines so the Issues table keeps its minimum height.

Cleanup previews open with the subject's name — hover it for the Worktree's
full path, or the Repository Anchor's for a Branch — and how long ago the Repository
was last fetched, with the exact fetch time as its tooltip. Each target's
availability sits in a right-hand gutter, and its reasons and consequences wrap
beside it; its **Details** list its path or ref, commit, and each blocker with
its suggested next command. Recovery commands stay with the command-line
report. The concrete primary target shows without a redundant checkbox, and the
Worktree's Branches follow under **Also remove**. When nothing can be deleted,
the preview says so above its targets.
Removing a Worktree is finishing its work, so its attached local Branch starts
selected, as does the same Branch at the remote a plain `git push` reaches when
it is integrated and at the local Branch's tip; untick either to retain it.
Ignored paths and their contents are listed rather than acknowledged. The
confirm button always reads `Remove Worktree` or `Delete Branch`; a callout at
the end of the preview states exactly what confirming removes and deletes.
Occupied, dirty, locked, protected, and otherwise blocked Worktrees remain
unavailable, and hold their Branches unavailable with them. That includes
every Worktree of a Repository while an Agent Session in it lists a
live sub-agent, even after that session ended, since Dashpot cannot tell which Worktree a sub-agent works in
([sub-agents and Worktree Cleanup](docs/agent-sessions.md#sub-agents-and-worktree-cleanup)),
a Worktree with a process running inside it
([processes inside a Worktree](docs/agent-sessions.md#processes-inside-a-worktree)),
and one that holds another registered Worktree
([ADR 0125](docs/adr/0125-block-removing-a-worktree-that-holds-another-worktree.md)).
When listed sub-agents are all that hold a Worktree, the dialog names each
session and its count of sub-agents beside an unticked toggle, "I have
checked that none of these sub-agents works in this Worktree"; ticking it is
a person's Sub-agent Override, and frees the Worktree, and the Branch held
only by it, to be confirmed
([ADR 0112](docs/adr/0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)).
A Branch blocked as unintegrated against a Remote-Tracking Branch says that
`f` checks again if the work has since merged
([ADR 0054](docs/adr/0054-finish-a-worktree-with-its-branch-by-default.md)).

For a Branch row, the local Branch is primary when present, otherwise the sole
remote Branch. A remote-only row with several remotes, or a blocked local Branch
with an available remote target, keeps explicit concrete choices. Nothing
starts selected beyond the primary there: that pane is a general Branch editor.

Press `f` in either dialog to fetch and prune without leaving it. The dialog
shows progress and per-remote outcomes. Repository fetch timestamps are labelled
as repository-wide evidence; failed remotes retain last-known facts. Confirmation waits for fresh Git
observation and re-inspection of the same subject. Unchanged optional targets
keep your choice; changed or new targets are unchecked, even one a first
preview would have selected. A missing primary never becomes another Branch
implicitly.
Fetch completion after cancellation only updates observation. Confirmed Cleanup
and Remote Fetch remain mutually exclusive for a Project; every deletion still
re-inspects and requires the ordinary explicit confirmation.

Both source queries submit on `Enter`; typing leaves the submitted query intact.
Lifecycle changes use the submitted expression and start at page one. GitHub
Projects use GitHub advanced syntax for both Issues and Pull Requests; Markdown
Projects retain local whitespace/quoted text matching. Both default to Open.
Choose All when lifecycle belongs to the raw expression. Clearing search submits
the default source query, without restoring a background inventory.

The Issue lifecycle selector also offers Ready: the open Issues none of whose
blockers is still open, so they can be picked up now. A GitHub Project asks
GitHub for `is:open -is:blocked`, which counts only open blockers; a Markdown
Project judges each blocker against its own Issues, and a blocker that is not
one of them counts as open, so an Issue is never shown Ready on a guess.

`n` requests Next, `p` returns to Previous, and `g` restarts the focused query
pane from page one. Eight accepted pages are retained; an evicted Previous is
unavailable and requires restart. The page displays its own observation time. The count separates
rows shown from all matching results; `Open N · Closed M` always reports Project-wide
totals, independently of search, lifecycle selection and page, with unavailability
or stale status when appropriate. GitHub exposes only the first 1,000 search results:
a query with 2,400 matches can show its first 50, and the final accessible page
explains the provider limit and invites a narrower query.

GitHub column sorts are enabled only for exact source equivalents: `CREATED`
maps to `sort:created-asc/desc`, `LAST ACTION` to `sort:updated-asc/desc`, and
`COMMENTS` to `sort:comments-asc/desc`. A submitted `sort:` owns ordering and disables
competing header sorts. Other GitHub header sorts are unavailable. Markdown sorts
its complete local query result before pagination, defaulting to latest action,
and retains local `sort:created` / `sort:updated` qualifiers.

Sessions, Worktrees, Branches, and Issues share a fixed first `◈` column:
`●` running, `◐` waiting, and `○` unknown. It stays visible when scrolling
horizontally. Worktrees and Branches summarize the liveliest located Agent
Session and show the total in the next `SESSIONS` column (`-` when none).
Issues summarizes explicitly bound Agent Runs, without a count. An empty
aggregate has a blank Glyph. The Issue column editor always keeps agent
activity first and preserves the order of your other choices.

While Sessions, Worktrees, or Branches has keyboard focus on Dashboard, the row
under its cursor emphasizes direct relationships in the other Dashboard panes:
a related row lights its `◈` agent-activity cell and bolds its identifying
cells (HARNESS and TARGET for Sessions, PATH for Worktrees, BRANCH for
Branches), and the rest of the row keeps its own background.
Sessions emphasizes its observed Worktree and Branch. Worktrees emphasizes its
located Sessions and checked-out Branch. Branches emphasizes its Worktrees and
directly associated Sessions. Worktree–Branch topology also works
without Sessions; shared locations never recursively add unrelated Sessions.

Arrow keys and mouse selection update this cue. Entering or re-entering a pane
re-emphasizes from the row its cursor stayed on; refresh preserves a surviving
cursor key.
Controls, the query peer, and temporary screens clear Dashboard emphasis.
Issues and Pull Requests are never sources or destinations. Other cursors,
filters, pagination, scroll positions, activity Glyphs, and counts stay
unchanged. Selection performs no observation or mutation. Paths and Branch
names are scoped to Project Identity; associations use accepted Agent Run
membership.
Distinct native Agent Session identities remain separate even on a shared
backend. Issue Hints and process identities do not establish relationships.

The Issue table's columns are `◈` (agent activity), `◉`
(Issue state), both unsortable, then `#`, `TITLE`, `WAITING ON`,
`PRIORITY`, `LABELS`, `PROJECT`, `ASSIGNEES`, `AUTHOR`, `MILESTONE`, `TYPE`,
`COMMENTS`, `CREATED`, and `LAST ACTION`. Clicking a sortable column's
header sorts by it, and clicking it again reverses the sort. `TITLE` keeps the first 70
characters of a title and clips the rest with an ellipsis, so the default
columns fit at a glance; the Issue view shows the whole title. `PRIORITY` is read from a
recognized priority label (`priority/p0` … `priority/p3`, or `critical`,
`high`, `medium`, `low`) and shown as a `P0`–`P3` chip in that label's colour;
the label leaves `LABELS` so it is not rendered twice. The column is
conditional: it appears only while some Issue in the table carries such a
label, an Issue without one shows nothing there, and a table with none omits
the column rather than invent a default, so an Issue Source that does not use
priority labels pays no width for it.

`WAITING ON` lists an open Issue's Open Blockers by number — `#12 #15`, the
first three and then `+2` for the rest — naming a blocker in another
Repository by its whole Reference. It is blank for a Ready Issue and for a
closed one, and like `PRIORITY` it appears only while some listed Issue waits.
An open Issue that waits is also dimmed, so the Ready rows stand out; the
column, not the colour, is what says it waits. The column is not sortable,
because no Issue Source orders by it.

The `PULL REQUESTS` pane defaults to open Pull Requests of a GitHub-backed
Project, in provider search order. Its lifecycle selector offers `Open`, `Closed`,
and `All`; Open includes drafts and non-drafts, while Closed includes merged
Pull Requests and those closed without merging.

Enter a GitHub Pull Request query in its search box and press `Enter` to
submit it. Use `draft:true` for drafts or `draft:false` for non-drafts; there
is no separate draft selector. Queries run through GitHub's advanced search
within this Project's configured repository, using the signed-in `gh` account.
GitHub evaluates the operators, including labels, assignees, review requests,
comments, dates and numeric ranges, `@me`, negation, Boolean `AND` / `OR`,
parentheses, and `sort:`. For example:

```text
(label:bug OR label:regression) draft:false comments:>2 sort:updated-desc
```

See [GitHub's qualifier reference](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests)
and the [search research](docs/research/github-pull-request-search-research.md) for the
operator inventory. GitHub's permissions, indexing, query limits, and search
ordering apply. Scope qualifiers can narrow this Project's results; they do
not expand the pane to other repositories. Lifecycle filtering happens at the
source before pagination. Project-wide counters do not change with the query.
A failed refresh retains last-good rows only for the same verified page request;
a failed navigation leaves the previous page available with the error and restart
guidance. Periodic refresh repeats the displayed page and independently refreshes
totals and relevant bound/selected Issues, on the GitHub period for a GitHub
source; a change in which Issues are bound resolves as soon as the Agent Runs
that show it are observed.

The columns are `STATE`, `#`, `TITLE`, `HEAD`, `BASE`, `AUTHOR`, `REVIEW`,
`CHECKS`, `MERGE`, and `UPDATED`. The state uses the same `■` character as
Issues, with GitHub's foreground colours: green for open, grey for draft, red
for closed without merging, and purple for merged. State labels remain visible,
including closed drafts. Mergeability is not applicable after closure. The
Legend and the header tooltips explain every column and its Glyphs, and long
content scrolls horizontally.

Complete history is collected only by explicit `--json` / `--compact-json`
Workspace Snapshot export, using repository pagination under a Refresh Budget.
No partial export is placed in complete inventory fields. The existing wire
contract retains all Issue Profiles and Pull Request lifecycle distinctions.

Paged CLI queries share the dashboard's source semantics:

```bash
dashpot issue list --query 'label:bug' --state open --page-size 50
dashpot pr list --query 'draft:true' --state open --page-size 50
dashpot issue list --query 'is:closed OR author:@me' --state all --compact-json
dashpot issue list --state ready
```

`--state ready` lists Ready Issues; a Pull Request list has no Ready state. Each
Issue's auxiliary facts carry its `openBlockers`, each with its identity and,
when known, its Reference and number; the field is `null` when the blockers
were not observed, which is not the same as an empty list.

Use `--cursor` with the same query, lifecycle and page size to continue. Page sizes
range from 1 to 100, default 50. Each document contains `page` and the Project-wide
`totals` the same request counted; pages expose request/context, complete
records, auxiliary facts, counts, continuation, limit, status, attempt time,
last-good time and Diagnostics.
`more`, `end`, `provider-limit` and `unavailable` distinguish continuation outcomes.
These commands never exhaust pages implicitly. Valid observation documents return
exit zero, including unavailable or provider-limited observations; inspect status.
Invalid arguments or malformed/mismatched/expired continuation return stderr and
exit 2, without a success document. Authentication/network failure is unavailability,
not proof of token mismatch. Markdown file edits, renames, insertion or deletion
expire continuation and require restart. `issue show` still resolves one complete
Issue Profile by Issue Hint.

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
authoritative checkout used for Issue and Pull Request collection.

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
dashpot --workspace my-project=/path/to/project --json
```

The TUI uses each Project's mutable display label. Headless snapshots also
include its durable `projectId` and `repositoryId`, along with Workspace names
and Repository Anchors, so automation and diagnostics do not depend on labels or
paths for identity.

The headless JSON key set is a stable contract, for `dashpot --json` and for
the `--json` of `issue show`, `worktree create`,
`worktree check`, `worktree remove`, `branch delete`, `events`,
and `events remove`: keys are camelCase,
every documented field is present, and
an unknown value is an explicit `null` rather than an omitted key, so a
consumer can tell "unknown" from "not emitted by this version". A shape change
is a compatibility change. The one exception is `dashpot events --json`,
which prints JSON Lines rather than one document: one Runtime Event per line,
oldest first, each under the field names it has in the Event Log, with every
field present and an unknown one as `null`, and nothing at all when no event
matches. Unreadable lines and files are reported on standard error
([ADR 0064](docs/adr/0064-publish-runtime-events-under-their-event-log-field-names.md),
[ADR 0099](docs/adr/0099-print-runtime-events-as-json-lines.md)).
`src/dashpot/serialization.py` owns the documents
and `tests/test_serialization.py` pins each command's key set.
`--compact-json` prints the same document without indentation.

## Domain language

The terms used in the interface, code, and documentation — Agent Session versus
Agent Run, Work Store, Issue Binding, Worktree versus Repository Anchor — and the
phrasings to avoid, are defined in [`docs/domain-language.md`](docs/domain-language.md).

## Development setup

Dashpot requires Python 3.13 or newer and uses
[uv](https://docs.astral.sh/uv/) for its locked development environment.

```bash
uv sync --locked --group dev
uv run pre-commit install
uv run pytest -q
# Run serially for debugging or reproduction:
uv run pytest -q -n 0
```

After pulling a change to the hooks, skills or agents Dashpot bundles,
refresh every harness you have integrated from the main checkout, never
from a linked Worktree, whose `.venv` is removed with it:

```bash
uv run dashpot integrate --installed
```

Tests run in parallel by default, reserving half the available CPUs and using
at most eight workers (at least one). The count is `os.process_cpu_count()`,
which respects CPU affinity where the platform reports it. Override with `-n N`, or `-n 0`
for serial execution. CI explicitly uses two workers. Higher counts require
measurement: sixteen failed locally despite eight passing repeatedly; see
[CI and test performance](docs/ci-performance.md).

Every Git command a test starts reads the suite's own global configuration
(`GIT_CONFIG_GLOBAL`, with `GIT_CONFIG_NOSYSTEM`): a committer identity, no
signing, `main` as the initial branch, and no hooks. Your own Git settings
never reach a test repository, so a test that commits needs no per-call
`-c` overrides.

### Quality gates

[`.pre-commit-config.yaml`](.pre-commit-config.yaml) is the shared quality
gate. `uv run pre-commit install` enables two sets of hooks for the checkout:

- **On commit**: repository hygiene checks (whitespace, line endings, YAML,
  TOML and JSON syntax, merge-conflict markers, stray debug statements, private
  keys, large files), then [Ruff](https://docs.astral.sh/ruff/) lint with safe
  fixes, then `ruff-format`, then [ty](https://docs.astral.sh/ty/) static type
  checking. Ruff and ty run through `uv run --locked`, so the hooks use the
  versions [`uv.lock`](uv.lock) pins, as the pre-push gate and every other
  `uv run` do. Ruff's rule selection and ty's rule levels live in
  [`pyproject.toml`](pyproject.toml). Then
  [`scripts/maintain_docs.py`](scripts/maintain_docs.py) resolves every in-repo
  Markdown link (its path, heading anchor, or `#L` line fragment), requires
  the frontmatter described in the
  [documentation map](#documentation-map), requires each ADR's number to
  be its own, requires the [ADR index](docs/adr/README.md) to be the file
  the script generates, and requires the [code map](docs/code-map.md) to link
  every module and asset the package ships; it always reads the whole
  document set, because a link resolves against files the commit need not
  touch, and neither an ADR's number nor the index's or the map's
  completeness is a property of one document.
- **On push**: the pushed-revision gate in
  [`scripts/check_quality.py`](scripts/check_quality.py), which verifies the
  lockfile, Ruff lint and formatting, ty, the documents, and the distribution
  build for the exact revision being pushed, in a temporary detached worktree. The test suite
  runs in CI across the documented platform matrix.

Run the commit hooks across every tracked file:

```bash
uv run pre-commit run --all-files
```

#### Harness acceptance runs

Each supported harness release is pinned by an acceptance run: a runner that drives the real harness in an isolated, disposable fixture through Dashpot's real hook publisher and `dashpot work` commands, and a verifier that checks the documented claims against the runner's metadata-only trace, which records the SHA-256 of the runner and of the Dashpot sources it exercised. They launch real harness processes, so they run by hand when the pinned release or the lifecycle code changes, never in CI. A release is supported once its run passes, and its trace is retained in [`docs/spikes/measurements/`](docs/spikes/measurements/README.md).

- **Codex 0.160.0**: [runner](scripts/experiments/codex-161/run.mjs) and
  [verifier](scripts/experiments/codex-161/verify.mjs),
  [trace](docs/spikes/measurements/issue-161-codex-trace.jsonl), including
  sub-agents that outlive their parent's turn and interrupted ones
  ([supported modes](docs/agent-sessions.md#codex-hosting-modes)).
- **Claude Code 2.1.287**: [runner](scripts/experiments/claude-162/run.mjs) and
  [verifier](scripts/experiments/claude-162/verify.mjs),
  [trace](docs/spikes/measurements/issue-162-claude-trace.jsonl) and
  [idle-eviction trace](docs/spikes/measurements/issue-162-claude-idle-trace.jsonl)
  ([supported modes](docs/agent-sessions.md#claude-code-hosting-modes)).
- **OpenCode 2.0.22**: [runner](scripts/experiments/opencode-163/run.mjs) and
  [verifier](scripts/experiments/opencode-163/verify.mjs),
  [trace](docs/spikes/measurements/issue-163-opencode-trace.jsonl), including
  the shared service, `--standalone` clients, background Sub-agents, moves,
  plugin instance churn, and a TUI of 2.0.21 replacing the service
  ([supported modes](docs/agent-sessions.md#opencode-hosting-modes)). The
  Issue-work skill's self-move has its own
  [runner](scripts/experiments/opencode-423/run.mjs),
  [verifier](scripts/experiments/opencode-423/verify.mjs) and
  [trace](docs/spikes/measurements/issue-423-opencode-trace.jsonl)
  ([acceptance](docs/spikes/opencode-v2-self-relocation-acceptance.md)).
  An experiment on the same release measures background commands,
  `opencode run` under default permissions, and retried and failed
  executions:
  [runner](scripts/experiments/opencode-379/run.mjs),
  [verifier](scripts/experiments/opencode-379/verify.mjs) and
  [trace](docs/spikes/measurements/issue-379-opencode-trace.jsonl)
  ([experiment](docs/spikes/opencode-v2-background-permissions-spike.md)).

#### Local review gate

Before every commit, run the all-files checks and the full suite with coverage
(a documentation-only change skips coverage, as described below):

```bash
review_base=$(git rev-parse origin/main)
uv run pre-commit run --all-files
uv run --locked python scripts/review_coverage.py --base "$review_base"
```

Pin the review base for the engagement and include it in the review request.
The coverage helper runs pytest once, replacing ordinary pytest in this gate.
It inherits pytest's automatic parallel default and combines worker coverage.
Use `--workers N` to choose a count, or `--workers 0` for serial execution.
Choose a worker count appropriate to local CPU and memory capacity. Worker crashes fail
the run without restarting. The evidence records the exact command. It prints
missing lines and writes `.review-coverage/coverage.json` plus `evidence.json`.
Evidence records the base, source content digest, coverage report digest,
command, Python/coverage versions, platform, and completion time. A failed run
removes prior success evidence; changes during the run prevent new evidence.
Generated files are ignored. Use the checkout's locked environment; Python
3.14 is preferred for its lower-overhead coverage backend. Other supported
versions remain usable, and targeted `uv run pytest ...` development runs
remain uninstrumented.

The run measures the maintenance scripts under `scripts/` beside the `dashpot`
package (`[tool.coverage.run]` in [`pyproject.toml`](pyproject.toml)), so a
change to a script carries evidence about its own lines through this same
gate, with no separate command. The
[harness acceptance runs](#harness-acceptance-runs) under `scripts/experiments/`
are left unmeasured: they drive real harness releases by hand, and no test runs
them. Coverage does not follow subprocesses, so a line a test reaches only by
running a script as a command reports as missed, as does a script that only
CI's build and installation jobs run.

Before completing review and after commit hooks, verify the evidence without
running the suite again:

```bash
uv run --locked python scripts/review_coverage.py --base "$review_base" --check
```

The source digest includes every tracked and non-ignored new file, `scripts/`
as well as `src/` and `tests/`, including modes and symlink targets. Staging and committing the same files preserves it; source
edits, a different review base, or a replaced report require fresh evidence.
Ignored local state is excluded. This verifies freshness, not reviewer approval.
Keep one writer and one coverage run per Worktree. Supply both reports to the
reviewer and record useful conclusions in the PR; generated evidence is not
committed. Coverage has no percentage threshold and does not establish the
quality of assertions or coverage of every branch outcome.

A documentation-only change, one CI's [documentation lane](#continuous-integration)
classifies as `docs`, skips the coverage run and its check;
[AGENTS.md](AGENTS.md#quality-gates-and-integration) says what it still
requires. Confirm the classification before pushing with CI's own classifier,
run from the checkout root. It reads the committed `$review_base...HEAD` diff
and prints `docs`, or `full` when the coverage run is required:

```bash
uv run --locked python -c 'import sys; sys.path[:0] = ["scripts"]; import ci_lane; print(ci_lane.classify("pull_request", sys.argv[1], "HEAD"))' "$review_base"
```

The pushed-revision gate can also run against the working tree. Its default
includes pytest with the same automatic parallel policy; `--skip-tests` uses already completed local coverage
and avoids another test run. It covers the lockfile, Ruff, ty, documentation,
and distributions, but omits hygiene hooks and coverage collection:

```bash
uv run --locked python scripts/check_quality.py --skip-tests
```

Ruff fixes and formatting are idempotent: a second `--all-files` run after the
first has fixed something is clean. The hygiene hooks' revision is pinned to a
frozen commit SHA; refresh it with

```bash
uv run pre-commit autoupdate --freeze
```

Ruff and ty have no hook revision of their own: `uv.lock` is their single
version source, so upgrading them (`uv lock --upgrade-package ruff
--upgrade-package ty`) moves the hooks, CI's quality job, and the pre-push gate
together. First-time hook setup downloads the pinned hygiene hook environment,
so it needs network access.

### Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pull requests
targeting `main` and on manual dispatch.
Integration into `main` does not trigger a duplicate run. It runs the all-files
pre-commit quality gate once on Ubuntu, tests the locked environment on Ubuntu
and macOS under Python 3.13 and 3.14,
exercises Debian 12’s maintained Git 2.39.x package in a container, and builds
the package once per run. Installed-artifact jobs
install the wheel and source distribution
independently on the Python/OS matrix, including TUI and hook-publisher checks. No
credentials are provided and no live GitHub collection happens in CI; the test
suite exercises Issue collection against fakes. Ubuntu/Python 3.14 collects
line coverage during its test run and writes the report to the job summary.
Coverage has no percentage threshold; tests and report generation must pass.
The CI report is additional diagnostic evidence; unchanged reviewed code does
not need another review when that report becomes available.

A pull-request run checks out the exact branch head and does not require the
branch to contain `main`
([ADR 0045](docs/adr/0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md)),
so a semantic conflict between two independently green PRs surfaces on the
next PR run that contains both rather than before merge.
The quality job publishes the verified head, base, and run identity in the
`ci-revision-<attempt>` artifact.
A PR changing only root Markdown or Markdown under `docs/` or
`conformance/` runs the documentation lane: quality and revision-artifact
checks still run, while tests, build, installation, and minimum-Git jobs are
skipped. The root Markdown the build reads is not documentation to the lane:
[`README-pypi.md`](README-pypi.md), the package description that
`check_distributions.py` and `twine check --strict` inspect, and
[`CHANGELOG.md`](CHANGELOG.md), whose entry for the current version
`check_release.py` requires, both select full verification. The complete diff
(including both sides of renames) is classified by
[`scripts/ci_lane.py`](scripts/ci_lane.py). Mixed, empty, unavailable, or
non-Markdown diffs run full verification; manual and reusable invocations do too.
`CI required` accepts only successful jobs and the exact skips authorized by a
successful classification; failures, cancellations, and unexpected skips fail.

Full verification runs tests in two independent processes per job, including
Debian compatibility, and combines worker coverage on Ubuntu/Python 3.14.
The same parallel command is available locally; `-n 0` keeps debugging serial.
See [CI and test performance](docs/ci-performance.md) for benchmark commands,
worker selection, UI profiling, and measured results. It is the
required-check context to configure for `main`; repository administration
setup is described in [development integration](docs/development-integration.md).
The operator's half of that setup is the `Protect main` ruleset: the
`CI required` check without a strict up-to-date requirement
([configure required CI](docs/development-integration.md#configure-required-ci)).

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

The [release workflow](.github/workflows/release.yml) reuses CI at the exact
release revision and publishes its verified artifacts only after environment
approval. [Releasing](docs/releasing.md) documents setup, rehearsal, real-host
acceptance, and recovery. The local artifact checks are:

```bash
uv run python scripts/check_distributions.py dist
uvx --from twine==7.0.0 twine check --strict dist/*
uv run python scripts/smoke_install.py dist/*.whl dist/*.tar.gz
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
Issue Source. The `.dashpot/state/` directory holds local runtime state,
including the Work Store. It ignores itself: Dashpot writes a `.gitignore`
containing `*` into it whenever it writes state there, as `.venv` does, so it
never dirties the worktree or gets committed whatever the repository's own
`.gitignore` says. A state directory written by an earlier Dashpot gains the
file the next time Dashpot writes state there.

A GitHub-backed Project looks like this:

```json
{
  "projectId": "project:01947e42-3f67-7c38-a41c-218df18a169b",
  "displayLabel": "Dashpot",
  "repositoryId": "R_kgDOUEerrg",
  "issueSource": {
    "kind": "github",
    "reconciliationSeconds": 300
  }
}
```

The Repository Anchor must have a GitHub `origin`; collection uses the
authenticated `gh` CLI. `reconciliationSeconds` is deprecated and unused.
Existing positive finite values remain readable; the setting no longer schedules
whole-source sweeps or constrains `--refresh-seconds`, and the loaded model
declares the field deprecated
([ADR 0105](docs/adr/0105-raise-the-python-floor-to-3-13.md)).
A Local Issue Markdown Project selects a repository-relative file or directory:

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
defaults its Issues pane to open Issues. Both adapters are currently read-only.

## Agent session observation

Dashpot observes Codex and Claude Code sessions through opt-in lifecycle hooks,
and OpenCode sessions through an opt-in plugin, installed once per user with
`dashpot integrate`. The same command installs the agent skills Dashpot
bundles in the harness's user skill directory, and updates, checks and removes
them with the hooks. Among them, the model-invoked `dashpot-issue-work` skill
resolves and declares Issue work, dispatches Worktree handoffs, and holds the
Issue Binding through the repository's delivery workflow. The
user-invoked `dashpot-execute-issues` skill lands an arc of Issues, an
epic's sub-issues or a list, through background workers that each take one
Issue to a PR in its own Issue Worktree, under Claude Code, Codex or
OpenCode; its record goes in Issue comments
([ADR 0092](docs/adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)).
Its lead assigns each worker to its Issue with `dashpot work assign`, so the
Issues pane shows that Issue running while the worker works
([ADR 0096](docs/adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)).
A declared
Codex resume can preserve the same Agent Run and `startedAt` across client
processes; Claude Code continues to relocate its live client. The
commands, the Work Store, and how a session is identified are documented in
[`docs/agent-sessions.md`](docs/agent-sessions.md).

## Issue Worktrees

Two source-neutral commands prepare Issue work in a linked Worktree, so an
agent or a person never has to choose between `gh` and Local Issue Markdown
or re-derive Git's collision rules. Both run from any directory of a
configured Worktree, which is the Repository Anchor of the result:

```bash
dashpot issue show 35                 # resolve an Issue Hint, print the profile
dashpot issue show '#35' --json       # the complete Issue Profile as JSON
dashpot worktree create 35            # a linked Worktree on Branch 35-<title-slug>
dashpot worktree create 35 --dry-run  # the same report, creating nothing
dashpot worktree create 35 --branch 35-alternate --base main --worktree-root ~/w
dashpot worktree check ~/w/35-alternate   # read-only: removable, or why not
dashpot worktree check                    # the same for every linked Worktree
dashpot worktree remove ~/w/35-alternate --delete-ignored   # unforced, after that check
dashpot worktree remove ~/w/35-alternate --delete-branch --delete-ignored --dry-run
dashpot worktree remove ~/w/35-alternate --delete-branch --delete-remote-branch --delete-ignored
dashpot branch delete 35-alternate --local   # the local Branch, once integrated
dashpot branch delete 35-alternate --local --remote origin   # and at origin, leased
```

`issue show` accepts the Issue Hints `work start` accepts — a bare Issue
Number, `#35`, a full Issue Reference, or a Local Issue slug — and prints the
reference, title, state, and location, or with `--json` the complete Issue
Profile with the snapshot's camelCase keys. A source that is not fresh, no
match, or an ambiguous hint is refused with exit code 2; nothing is written.

`worktree create` is a management command under
[ADR 0008](docs/adr/0008-let-management-commands-mutate-on-explicit-invocation.md):
it creates one linked Worktree at one path outside every Worktree of the
Project, on one new Branch, and never fetches, pushes, merges, deletes, or
moves anything. Its conventions are recorded in
[ADR 0011](docs/adr/0011-prepare-issue-worktrees-by-convention.md):

- **Worktree Root:** `--worktree-root DIR`, else `DASHPOT_WORKTREE_ROOT`,
  else `worktree_root` in the machine-local `~/.config/dashpot/config.toml`
  (`XDG_CONFIG_HOME` respected), else the sibling directory
  `<main parent>/<main name>.worktrees/` of the Repository's main working
  tree — the same pool whether the command runs in the main checkout or in
  a linked Worktree
  ([ADR 0039](docs/adr/0039-anchor-the-default-worktree-root-on-the-main-working-tree.md)).
  The root is real-path normalised, refused inside any Worktree of the
  Project, and reported with its source; the default names the main working
  tree it sits beside.
- **Base:** `--base REF`, else `origin/HEAD`, else the one local `main` or
  `master` when exactly one exists, else a refusal naming `--base`; resolved
  to an exact commit, never fetched, and reported with its source. The base
  revision's `.dashpot/config.json` must carry the anchor's Project and
  Repository Identity, checked before anything is created.
- **Branch:** `--branch NAME`, else `<number>-<title-slug>` (a Local Issue's
  slug), validated with `git check-ref-format --branch`; a name that extends
  an existing Branch with `/` is refused. The path leaf is the Branch with
  `/` replaced by `-`.
- **Refusals**, all before Git is called and each reported: a non-empty
  path, an empty directory Dashpot did not create, an existing or
  checked-out Branch, a registered Worktree at the path (one locked
  `initializing` by a killed `git worktree add` is reported with the
  `git worktree remove -f -f` and `git branch -D` recovery), and, for the
  default name, an existing Worktree whose Branch starts with the Issue
  Number — listed as a hint; pass `--branch` for a second approach.
- **Rollback:** when `git worktree add` fails, only a Branch this invocation
  created that still points at the base commit and is checked out nowhere,
  and the empty directories it created, are removed; a populated path, a
  lock, or another creator's Worktree is reported and left alone. The
  command verifies the result: a registered, unlocked, clean Worktree at the
  base commit on the new Branch, with the main Worktree unchanged.

`--dry-run` reports the path, Branch, base commit and source, root and
source, and every refusal, without creating anything. `--json` prints the
same facts (`issueId`, `issueReference`, `path`, `branch`, `baseRef`,
`baseSource`, `baseCommit`, `worktreeRoot`, `worktreeRootSource`,
`mainWorktree`, `dryRun`, `created`, `refusals`, `hints`, `warnings`); a
refusal exits 2 in either mode. `warnings` carries non-fatal observations, such as unknown fields in
the machine-local settings file, which are ignored rather than fatal so a
settings file written by a newer Dashpot never stops this one.

Worktrees supports `Enter` to open a terminal and `y` to copy its full path.
See [Open Worktrees and copy paths](docs/installation.md#open-worktrees-and-copy-paths)
for custom launchers, tmux behavior, and clipboard requirements. Opening a
Worktree does not create or relocate an Agent Session or establish Issue work.

Machine-local settings use flat snake_case TOML keys. See the
[settings guide](docs/installation.md#machine-local-settings) for syntax and
one-time setup when replacing `settings.json`. Workspace `--config` and public
JSON fields such as `worktreeRoot` retain their existing meanings.

`worktree check [path]` is read-only. With no path it reports every linked
Worktree of the Repository, one after another (`--json` gives a list). It
assesses a Worktree by the sequence a Cleanup preview applies, protecting the
same checkouts, so a Worktree it reports removable is one `worktree remove`
would offer
([ADR 0129](docs/adr/0129-disclose-what-a-cleanup-gates-on-and-share-one-removability-verdict.md)).
It reports the Worktree removable, or
each reason it is not with the command that acts on it: dirty state, a lock
with its reason and whether the holding process is alive (`initializing`
names the forced removal), Agent Sessions whose hooks place them there
(each named as live there or of unknown liveness, with how to free the
Worktree from it: [Agent Sessions and Worktree Cleanup](docs/agent-sessions.md#agent-sessions-and-worktree-cleanup)),
Agent Runs recorded there (an Orphaned Agent Run, whose session is gone,
names its `dashpot work stop --session` command, while a run whose
relocation is pending is named as moving, with the resume that carries it),
a `sub-agent` that an Agent
Session elsewhere in the Repository still lists as working, which may be
working here because Dashpot cannot tell which Worktree a sub-agent works in
(it names how to end that session if none is still working, or for a session
that has already ended, its `dashpot work forget-subagents` command:
[ADR 0066](docs/adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md),
[ADR 0095](docs/adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)),
a `process` whose working directory is inside the Worktree, named by pid,
command and directory
([processes inside a Worktree](docs/agent-sessions.md#processes-inside-a-worktree)),
another linked Worktree registered inside it, named with the
`dashpot worktree remove` that removes it first, or a stale record of one,
named with the `git worktree prune` that drops it (preceded by
`git worktree unlock` for a locked record, which prune leaves alone)
([ADR 0125](docs/adr/0125-block-removing-a-worktree-that-holds-another-worktree.md)),
the checkout the command runs from or a configured Repository Anchor
(`protected`), and commits not on the upstream or the Integration Branch.
Every command it names is quoted for a POSIX shell. Like the Cleanup
commands, it refuses when the Workspace config cannot be read, since it
could not tell which Repository Anchors to protect. A removable
Worktree's text report says that its remove commands also delete the ignored
paths inside it, which `--json` lists as `ignored`, and adds that sub-agents
of Agent Sessions outside the Repository are not checked. When the host's processes could not all be
read, as inside a sandbox, it says so beneath that, and `--json` carries
the sentence as `uncheckedProcesses`; `removable` stays true, so a caller
that reads only `removable` should read `uncheckedProcesses` too. `check`
removes nothing.

`worktree remove PATH` and `branch delete NAME` are the Cleanup commands of
[ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md).
Each takes the same read-only preview the dashboard's `x` opens — every
target with its integration state, blockers, and consequences — then
re-inspects and performs only the targets its flags name, only if nothing
observed has changed in between. `worktree remove` removes one linked Worktree with an unforced
`git worktree remove`, so a dirty or locked Worktree is refused, and with
`--delete-branch` deletes its local Branch afterwards;
`--delete-remote-branch` first deletes the same Branch at the remote a plain
`git push` of it reaches (its `pushRemote`, `remote.pushDefault`, its upstream
remote, else `origin`), leased as `branch delete --remote` is, and is refused
when that remote has no Remote-Tracking Branch for it; `--delete-ignored`
acknowledges that the Worktree's ignored content (`.venv`, `.dashpot/state/`,
hook records, and the Work Store there) goes with it, and the command is
refused without it when such content exists.
`--despite-subagents SESSION_ID:AGENT_ID,AGENT_ID` (one per session) is a
person's Sub-agent Override: it removes the Worktree despite exactly the
sub-agents the preview lists as working, when they are all that hold it and
the processes inside it were all checked. A refused removal prints the
exact value to pass. The listed set is compared again on confirmation, and
the Worktree's occupants and processes are inspected again before each step,
so a changed set or a process inside refuses; no other blocker is lifted,
and each performed override is recorded in the Event Log as
`cleanup.subagents_acknowledged`. An agent never passes it
([ADR 0112](docs/adr/0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)). No flag is implied: the
dashboard's default selections
([ADR 0054](docs/adr/0054-finish-a-worktree-with-its-branch-by-default.md))
never apply to the command line. `branch delete --local` deletes
the local Branch with `git update-ref -d` guarded by the previewed commit, so a
Branch that moved is refused rather than deleted, and drops its `branch.NAME.*`
configuration. `branch delete --remote REMOTE` (repeatable) deletes the Branch
at that remote with `git push --force-with-lease=refs/heads/NAME:<oid> REMOTE
:refs/heads/NAME`, the lease being the Remote-Tracking Branch's tip as of the
last fetch, before any local deletion; it needs the canonical fetch mapping
and exactly one push URL, honours the pre-push hook, and never fetches. Git
rejects the push with `stale info` when the remote moved and when the Branch
is already gone there, so that rejection is followed by one read-only
`git ls-remote` to report `refused` (press `f`, or `git fetch --prune`, then
confirm again) or `already-absent` (the stale Remote-Tracking Branch is pruned
the same way); a successful delete push drops the Remote-Tracking Branch itself.
Neither command deletes the Integration Branch, a Branch checked out, being
rebased (including one `rebase --update-refs` moves), or being bisected in
any Worktree, as Git tells it, a
Branch with commits the Integration Branch does not reach, or a Worktree that
is the main one, dirty, locked, occupied by an Agent Session or Agent Run,
possibly occupied by a live Claude Code sub-agent of a session in the
Repository, one a process is running inside, one that holds another
registered Worktree, one whose ignored content Git could not list, the
checkout the command runs from or its Worktree root, or a configured
Repository Anchor (every anchor of the Workspace config; the dashboard
protects its Project's anchors by the same rule). Every target reports its own outcome —
`deleted`, `already-absent`, `refused`, or `unknown` when Git did not answer —
with the command that recreates a deleted one, and after a refused or unknown
outcome the remaining targets are not attempted. `--dry-run` validates the
selection and lists what would be attempted, in order; `--json` prints the
report (`kind`, `subject`, `anchor`, `dryRun`, `performed`, `changed`,
`refusals`, `planned`, `results`, `succeeded`, and the `preview`, whose
`sub-agent` blockers carry `sessionId`, `harness` and `agents`). The exit
code is 0 only when every selected target was deleted or already absent.

The created Worktree carries no harness. The installed Issue-work skill moves
a running Claude Code session with `EnterWorktree`, has a root OpenCode
session on the shared service move itself with OpenCode's own session move
and confirm the move in its next step before any Dashpot work there
([ADR 0094](docs/adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md),
[ADR 0108](docs/adr/0108-keep-opencode-self-move-and-leading-workers-on-the-shared-service.md)),
or hands a Codex session
off through sequential `codex resume <session-id> -C <path>` when that version
supports it. An active Codex run first declares the target with `dashpot work
relocate <path>`; after the old client exits, the resumed hook moves the same
run only when it proves the same Agent Session Identity at that target and no
client remains live or unobservable elsewhere. The resumed session verifies
the preserved binding with `work show`; an unbound session uses `work start`.
A fresh `codex -C <path>` session is the disclosed compatibility fallback and
cannot preserve another session's Agent Run; a person's `/cd <path>` in the
live Codex client likewise starts a new Agent Session, keeping the model's
context but not the run
([Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in)). Claude Code's
own `--worktree` is not used because it places, names, bases, and may reset
Worktrees by its own rules. Each Worktree owns its own `.venv` and
`.dashpot/state/`.

## Design

How the pieces fit — the observation pipeline, the read model, the source and
store seams, and the Textual layer over them — is described in
[`docs/design.md`](docs/design.md). The decisions behind them are in
[`docs/adr/`](docs/adr/), listed in its
[index](docs/adr/README.md).

## Contributing

Every change lands on `main` the same way, whether a human or an agent makes
it:

1. Branch from `main` for the change.
2. Complete the [local review gate](#local-review-gate) and independent review
   as specified in [AGENTS.md](AGENTS.md#independent-review-before-integration).
   Address findings and refresh affected validation and review. Commit with
   the commit hooks installed, then verify coverage evidence still matches,
   unless AGENTS.md exempts the change.
   A commit message line `Closes #N`
   is what closes the Issue on GitHub once the commit reaches `main`.
3. Push the branch and open a pull request targeting `main` after local
   validation and review. The pre-push hook runs the pushed-revision gate in
   [`scripts/check_quality.py`](scripts/check_quality.py) against the pushed
   revision in a detached worktree, so a red gate stops the push. That gate
   deliberately skips the test suite; local coverage has already run it and
   pull-request CI confirms it across every platform, except for a
   documentation-only change, which touches no code and runs neither. Fill in the PR template
   with the review base, source digest, final commit, checks, coverage
   observations, and review findings/dispositions.
4. Watch the latest pull-request CI run to completion with
   `gh run watch <id> --exit-status`. Every required job must pass before
   integration. If the branch changes, validate and review the changes and
   wait for its new CI run. `main` advancing beyond the branch's base is not
   a reason to update the branch; only a textual conflict is.
5. The operator reviews the PR and squash-merges it following the
   [integration procedure](docs/development-integration.md#integrate-a-verified-pr).
   An agent's work ends before this step, with the PR open, its validation
   section recorded, and CI green
   ([AGENTS.md](AGENTS.md#integration-and-rebase)); it neither
   merges the PR nor enables auto-merge. The PR title and body, not the
   branch's own commits, are what land on `main`, and nothing runs CI on
   `main` itself, so the merged result is not verified before it lands. After
   the merge, the operator verifies that remote `main` carries the squash
   commit, synchronizes the local main checkout only through an authorized
   fast-forward, and leaves Worktree cleanup separate.

Issues are labelled and triaged as [`docs/issue-labels.md`](docs/issue-labels.md)
describes.

Agent sessions use the `dashpot-issue-work` skill to declare and verify the
Issue they are working on (see
[Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in)); the expectations
on agents themselves are in [`AGENTS.md`](AGENTS.md).

## Documentation map

These `living` documents carry the detail this README points at:

- [`docs/installation.md`](docs/installation.md) covers installation, support,
  configuration, diagnosis, upgrades, and removal.
- [`docs/github-rate-limits.md`](docs/github-rate-limits.md) records GitHub's
  rate limits for each authentication method, how Dashpot spends them, and how
  to stay inside them.
- [`docs/releasing.md`](docs/releasing.md) covers release gates, publishing, and recovery.
- [`docs/development-integration.md`](docs/development-integration.md) covers
  Dashpot's required CI ruleset and the integration procedure.
- [`docs/issue-labels.md`](docs/issue-labels.md) defines this Repository's
  Issue labels and how Issues are triaged with them: what each label means,
  who may apply and clear it, and how to tell whether an Issue is free to
  pick up.
- [`docs/domain-language.md`](docs/domain-language.md) defines the terms used in
  the interface, code, and documentation, including the phrasings to avoid.
- [`docs/agent-sessions.md`](docs/agent-sessions.md) documents `dashpot
  integrate` and `dashpot work`, the Work Store, and how a session is
  identified.
- [`docs/agent-harness-server-client-reference.md`](docs/agent-harness-server-client-reference.md)
  compares Claude Code, Codex CLI, and OpenCode hosting, clients, conversation
  identity, and lifecycle, with source and experiment boundaries.
- [`docs/design.md`](docs/design.md) describes how the pieces fit — the
  observation pipeline, the read model, and the seams beneath the interface.
- [`docs/code-map.md`](docs/code-map.md) names the module that owns each
  domain concept, with a line on each module's role, and lists every module
  and asset the package ships.
- [`docs/observability-design.md`](docs/observability-design.md) records how
  Dashpot records its own behaviour as Runtime Events in a local Event Log:
  levels, content, the on-disk fields, and the measurements behind them.
- [`docs/design-research/README.md`](docs/design-research/README.md) indexes
  the design research — the research and analysis behind Dashpot's
  direction: keeping understanding of a codebase, held by a person and by a
  team, as agents author more of it; the friction that keeps it; and the
  work rather than the session as the unit.

[`docs/adr/`](docs/adr/) records architectural decisions, one ADR per
decision, indexed by number in
[`docs/adr/README.md`](docs/adr/README.md).

The top level of [`docs/`](docs/) holds only `living` documents: those above,
[`ci-performance.md`](docs/ci-performance.md), and
[`textual-implementation-notes.md`](docs/textual-implementation-notes.md).
The other documents are grouped by kind, never by `status`, so a document
keeps its path when its status changes. Each kind directory has a `README.md`
index giving every document's title, `status`, and date; a new document is
added to its directory's index in the change that creates it:

- [`docs/research/`](docs/research/README.md) — investigations of upstream
  capabilities and of Dashpot's data access that informed a decision.
- [`docs/spikes/`](docs/spikes/README.md) — dated, reproducible experiments
  against a harness, GitHub, or the development suite, with their raw traces
  indexed in [`docs/spikes/measurements/`](docs/spikes/measurements/README.md).
- [`docs/reviews/`](docs/reviews/README.md) — point-in-time reviews and audits
  of the codebase, its models, and its open Issues.
- [`docs/proposals/`](docs/proposals/README.md) — designs and the evidence
  assembled for them, open or superseded.

Two directories sit outside this grouping. The design research above stays a
self-contained corpus in [`docs/design-research/`](docs/design-research/README.md),
with its own index, dating conventions, and cross-links, rather than joining
`docs/research/`: it studies Dashpot's direction, not an upstream capability
behind one decision. [`docs/agents/`](docs/agents/) holds the documents
installed skills read by path, listed below.

[ADR 0042](docs/adr/0042-group-leaf-and-domain-modules-into-subpackages.md)
records the completed package layout and application composition seam.
[ADR 0043](docs/adr/0043-retain-distinct-query-and-collection-adapters.md)
records why query and complete-collection adapters retain distinct contracts,
and [ADR 0047](docs/adr/0047-keep-the-dashboard-screen-as-one-textual-adapter.md)
why the dashboard screen stays one Textual adapter.
[ADR 0105](docs/adr/0105-raise-the-python-floor-to-3-13.md)
records why the Python floor is 3.13, superseding the typing backports
[ADR 0048](docs/adr/0048-adopt-python-3-13-typing-backports-on-the-3-12-baseline.md)
adopted on the 3.12 baseline.
[ADR 0049](docs/adr/0049-interrupt-observation-commands-at-dashboard-exit.md)
records why quitting interrupts the observation commands in flight,
[ADR 0050](docs/adr/0050-describe-every-pane-column-once-for-the-tooltip-and-the-legend.md)
why every pane column describes itself once for both its header tooltip and
the Legend, and
[ADR 0051](docs/adr/0051-adopt-long-lived-peer-dashboard-screens.md)
why the dashboard adopts two long-lived peer screens over shared application
state.
[`CHANGELOG.md`](CHANGELOG.md) records release notes;
[`README-pypi.md`](README-pypi.md) is the compact package-index description.
[`conformance/`](conformance/) documents owned file grammars, and
[AGENTS.md](AGENTS.md) is the working guidance for coding agents.
[`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md) tells
`code-review` and other skills that look it up by path how to reach this
Repository's Issues.

Every document under `docs/` declares in its frontmatter how it should be read,
so its standing is visible without reading it:

| `status` | Meaning |
| --- | --- |
| `living` | Maintained alongside the code; expected to be current. |
| `research` | A dated investigation. True as of its `date:`, never updated. |
| `proposal` | A direction under review; nothing has been accepted yet. |
| `superseded` | Kept as evidence, and no longer describes the code. |

An ADR's `status` is `proposed`, `accepted`, `amended`, or `superseded`
instead; an `amended` ADR still holds, with the change recorded in its own
Consequences. The `date:` is the decision or research date, not the last edit —
a document that keeps up with the code is `living`, and its date moves with it.

A `superseded` document names its replacement in `superseded-by:`, and an
`amended` one names every ADR that changed it in `amended-by:`. Both are
comma-separated paths written relative to the naming document's own directory,
the way its prose links are, and both are resolved by the gate: a replacement
that is renamed or removed fails the build rather than rotting quietly.

Each ADR's filename opens with the zero-padded four-digit number that prose
and code comments use to name it, and no two ADRs may claim the same one: a
shared number leaves every bare "ADR NNNN" identifying neither document.

[`docs/adr/README.md`](docs/adr/README.md) indexes every ADR by number, with
its title, `status`, and whatever resolved it. It is generated from the ADRs
themselves and gated against them rather than maintained by hand, so it cannot
describe a set of decisions that no longer exists; it carries no number of its own, because it
records no decision, and it declares a document `status` for the same reason.
Its `date:` is its newest ADR's, which makes the file a function of its inputs
and lets the gate compare it whole. Run
`uv run python scripts/maintain_docs.py --write-adr-index` after adding or
changing an ADR.

`uv run python scripts/maintain_docs.py` enforces the frontmatter, every
in-repo Markdown link, ADR numbering, the index's freshness, and the
[code map](docs/code-map.md)'s coverage of every shipped module and asset,
and runs as part of the [quality gates](#quality-gates).

## License

MIT
