# Dashpot

_Useful damping for agent-driven projects._

Dashpot is a passive terminal view of declared work, repository state, and active
coding-agent runs. It makes the small but important project-management pause
visible before another prompt or agent adds more motion.

Like its [mechanical namesake](https://en.wikipedia.org/wiki/Dashpot), Dashpot is
intended to reduce oscillation without stopping progress. Observation never
mutates: the view, every refresh, and `dashpot --json` never assign or edit
Issues, change the Git Repository, or control agent sessions. Dashpot's named
management commands — `init`, `integrate`, `work start`, `work relocate`,
`work stop`, `branch delete`, and `worktree remove` — and its two mutating
keys — `f`, which fetches Git remotes, and `x`, which deletes a Branch or
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
- Codex and Claude Code lifecycle records published through opt-in hooks
- source freshness, failures, and last-good state
- durable Agent Run bindings through opaque Issue Identity

Each source remains independent in the read model. A failed Pull Request
refresh, for example, retains its last good collection without degrading a
healthy Issue Source or hiding repository facts. A Local Issue Markdown
Project reports Pull Requests as not configured rather than inferring a host
from its Git remotes.

## Installation

Once the first release is published, install Dashpot in an isolated tool environment:

```bash
uv tool install --python 3.14 dashpot
```

The release targets CPython 3.12–3.14 on Linux x86-64 and Apple Silicon macOS,
Git 2.39+, and gh 2.100.0+ for GitHub-backed Projects. See
[installation and support](docs/installation.md) for current host-validation
status, candidate installation before publication, PATH setup, harness setup,
diagnosis, upgrades, and uninstall instructions.

For a repository with a GitHub `origin`, authenticate `gh`, run `dashpot init`
and add `.dashpot/state/` to `.gitignore`, then run `dashpot`. For a Project
without GitHub, create an `issues` directory and use `dashpot init --markdown
issues`; that source uses the [Local Issue Markdown grammar](conformance/issue/local-markdown.md).

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

The default 15-second polling period refreshes the
observed Project and can be changed with `--refresh-seconds`; zero disables
polling. `--timeout` bounds every external `git` and `gh` command (default 10
seconds), `--state-dir` overrides where session records land outside a
configured Project (the flag form of `DASHPOT_STATE_DIR`), and `--version`
prints the installed version. `dashpot --help` describes every command and
option, and each command has its own `--help`; an option belongs to the
command it follows, so the timeout for `init` is given as `dashpot init
--timeout 5`, not before `init`. Every command failure — invalid input, a
startup error, or a refused operation — is a one-line `dashpot: ...`
diagnostic on stderr and exit code 2, with no traceback. Beside observation,
the management commands `init`, `integrate`,
`work`, `issue show`, `worktree create` / `check` / `remove`, and
`branch delete` are documented in
[Project configuration](#project-configuration),
[Agent session observation](docs/agent-sessions.md#agent-session-observation),
[Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in), and
[Issue Worktrees](#issue-worktrees).

### Keys

| Key | Action |
|---|---|
| `1` / `2` | Switch directly between Dashboard and Issues & Pull Requests; the complete labels in the top status bar are clickable too |
| `r` | Restart both submitted queries from page one, refresh Project Totals, relevant Issue identities and local observations |
| `Enter` in Worktrees | Open the selected Worktree in a new tmux pane or through the configured launcher |
| `y` in Worktrees | Send the full Worktree path to the terminal clipboard |
| `f` on Dashboard | Fetch and prune the Git remotes of the Repository Anchor behind the Branches pane; also available inside both Cleanup dialogs |
| `x` on Dashboard | Preview removing the highlighted Worktree or deleting the highlighted Branch, then confirm; `Escape` cancels. Optional additional targets start unchecked ([ADR 0036](docs/adr/0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md)) |
| `Tab` / `Shift+Tab` | Cycle through only the active peer's tables: Sessions → Worktrees → Branches, or Pull Requests → Issues |
| `/` on Issues & Pull Requests | Focus the active query pane's search |
| `o` on Issues & Pull Requests | Cycle the focused query pane between open, closed, and all records (the selector beside its search does the same) |
| `n` / `p` on Issues & Pull Requests | Move the focused query pane to its next or previous retained page |
| `g` on Issues & Pull Requests | Restart the focused query pane from its first page |
| `c` with Issues focused | Open the column editor: toggle the other Issue columns and reorder them with `Ctrl+Up` / `Ctrl+Down`; `Escape` cancels |
| Arrow keys | Move or scroll the focused list; `Down` at the last row and `Up` at the first row cycle within the active peer; the newly focused pane's cursor is where it was last left |
| `Enter` | On an Issue, read it full-screen (`Escape` returns); opens a Worktree only from the Worktrees pane and is unbound on Sessions and Pull Requests |
| `?` | Open the Legend: every column's description with its Glyphs, pane by pane, and the keys; `Escape` closes, `End` and `Home` scroll. Resting the mouse on any column header shows the same description as a tooltip |
| `q` | Quit |

Dashboard is the default peer. Its Sessions, Worktrees and Branches panes are
separate from the Pull Requests and Issues query peer. Each long-lived peer
keeps its focused control, row cursors, scroll positions, lifecycle choices,
submitted queries and unsubmitted search text while the other is active; a
pane's first entry starts at its first row. Passive refreshes preserve selected
row identity. Issue Detail, Legend and Cleanup cover their originating peer,
and `Escape` returns there; `1` and `2` are inactive on those temporary screens
and insert text normally while an editable input has focus.

The shared status bar shows exactly `Open Issues: N | Open PRs: N` from Project
Totals. `-` means a total is unavailable. `◆` means every displayed number is
fresh and `◇` means at least one is retained and stale; no freshness mark is
shown when neither total is numeric. At compact widths the summary wraps below
the complete peer labels.

Cleanup previews show the concrete primary target without a redundant checkbox.
Removing a Worktree retains its attached local Branch unless you select that
option; selecting it changes the button to `Remove Worktree and Branch`.
Ignored paths and their contents still need acknowledgement. Occupied, dirty,
locked, protected, and otherwise blocked Worktrees remain unavailable.

For a Branch row, the local Branch is primary when present, otherwise the sole
remote Branch. A remote-only row with several remotes, or a blocked local Branch
with an available remote target, keeps explicit concrete choices. Additional
remote deletion is never automatic.

Press `f` in either dialog to fetch and prune without leaving it. The dialog
shows progress and per-remote outcomes. Repository fetch timestamps are labelled
as repository-wide evidence; failed remotes retain last-known facts. Confirmation waits for fresh Git
observation and re-inspection of the same subject. Unchanged optional choices
may survive; changed or new targets are unchecked, and ignored content must be
acknowledged again. A missing primary never becomes another Branch implicitly.
Fetch completion after cancellation only updates observation. Confirmed Cleanup
and Remote Fetch remain mutually exclusive for a Project; every deletion still
re-inspects and requires the ordinary explicit confirmation.

Both source queries submit on `Enter`; typing leaves the submitted query intact.
Lifecycle changes use the submitted expression and start at page one. GitHub
Projects use GitHub advanced syntax for both Issues and Pull Requests; Markdown
Projects retain local whitespace/quoted text matching. Both default to Open.
Choose All when lifecycle belongs to the raw expression. Clearing search submits
the default source query, without restoring a background inventory.

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
under its cursor emphasizes direct relationships in the other Dashboard panes
with a subtle background and bold identifying cells (HARNESS and TARGET for
Sessions).
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
(Issue state), both unsortable, then `#`, `TITLE`,
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
and the [search research](docs/github-pull-request-search-research.md) for the
operator inventory. GitHub's permissions, indexing, query limits, and search
ordering apply. Scope qualifiers can narrow this Project's results; they do
not expand the pane to other repositories. Lifecycle filtering happens at the
source before pagination. Project-wide counters do not change with the query.
A failed refresh retains last-good rows only for the same verified page request;
a failed navigation leaves the previous page available with the error and restart
guidance. Periodic refresh repeats the displayed page and independently refreshes
totals and relevant bound/selected Issues.

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
dashpot issue list --query 'label:bug' --state open --page-size 50 --json
dashpot pr list --query 'draft:true' --state open --page-size 50 --json
dashpot issue list --query 'is:closed OR author:@me' --state all --compact-json
```

Use `--cursor` with the same query, lifecycle and page size to continue. Page sizes
range from 1 to 100, default 50. Each document contains `page` and independently
scoped `totals`; pages expose request/context, complete records, auxiliary facts,
counts, continuation, limit, status, attempt time, last-good time and Diagnostics.
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
every management command's `--json` (`issue show`, `worktree create`,
`worktree check`, `worktree remove`, `branch delete`): keys are camelCase,
every documented field is present, and
an unknown value is an explicit `null` rather than an omitted key, so a
consumer can tell "unknown" from "not emitted by this version". A shape change
is a compatibility change. `src/dashpot/serialization.py` owns the documents
and `tests/test_serialization.py` pins each command's key set.
`--compact-json` prints the same document without indentation.

## Domain language

The terms used in the interface, code, and documentation — Agent Session versus
Agent Run, Work Store, Issue Binding, Worktree versus Repository Anchor — and the
phrasings to avoid, are defined in [`docs/domain-language.md`](docs/domain-language.md).

## Development setup

Dashpot requires Python 3.12 or newer and uses
[uv](https://docs.astral.sh/uv/) for its locked development environment.

```bash
uv sync --locked --group dev
uv run pre-commit install
uv run pytest -q
# Run serially for debugging or reproduction:
uv run pytest -q -n 0
```

Tests run in parallel by default, reserving half the available CPUs and using
at most eight workers (at least one). Linux uses the current CPU affinity;
other platforms use the reported CPU count. Override with `-n N`, or `-n 0`
for serial execution. CI explicitly uses two workers. Higher counts require
measurement: sixteen failed locally despite eight passing repeatedly; see
[CI and test performance](docs/ci-performance.md).

### Quality gates

[`.pre-commit-config.yaml`](.pre-commit-config.yaml) is the shared quality
gate. `uv run pre-commit install` enables two sets of hooks for the checkout:

- **On commit**: repository hygiene checks (whitespace, line endings, YAML,
  TOML and JSON syntax, merge-conflict markers, stray debug statements, private
  keys, large files), then [Ruff](https://docs.astral.sh/ruff/) lint with safe
  fixes, then `ruff-format`, then [ty](https://docs.astral.sh/ty/) static type
  checking. Ruff's rule selection and ty's rule levels live in
  [`pyproject.toml`](pyproject.toml). Then
  [`scripts/check_docs.py`](scripts/check_docs.py) resolves every in-repo
  Markdown link (its path, heading anchor, or `#L` line fragment) and requires
  the frontmatter described in the
  [documentation map](#documentation-map); it always reads the whole document
  set, because a link resolves against files the commit need not touch.
- **On push**: the pushed-revision gate in
  [`scripts/check_quality.py`](scripts/check_quality.py), which verifies the
  lockfile, Ruff lint and formatting, ty, the documents, and the distribution
  build for the exact revision being pushed, in a temporary detached worktree. The test suite
  runs in CI across the documented platform matrix.

Run the commit hooks across every tracked file:

```bash
uv run pre-commit run --all-files
```

#### Local review gate

Before every commit, run the all-files checks and the full suite with coverage:

```bash
review_base=$(git rev-parse origin/main)
uv run pre-commit run --all-files
uv run --locked python scripts/review_coverage.py --base "$review_base"
```

Pin the review base for the engagement and include it in the review request.
The helper runs pytest once, replacing ordinary pytest in this gate.
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

Before completing review and after commit hooks, verify the evidence without
running the suite again:

```bash
uv run --locked python scripts/review_coverage.py --base "$review_base" --check
```

The source digest includes tracked and non-ignored new files, including modes
and symlink targets. Staging and committing the same files preserves it; source
edits, a different review base, or a replaced report require fresh evidence.
Ignored local state is excluded. This verifies freshness, not reviewer approval.
Keep one writer and one coverage run per Worktree. Supply both reports to the
reviewer and record useful conclusions in the PR; generated evidence is not
committed. Coverage has no percentage threshold and does not establish the
quality of assertions or coverage of every branch outcome.

The pushed-revision gate can also run against the working tree. Its default
includes pytest with the same automatic parallel policy; `--skip-tests` uses already completed local coverage
and avoids another test run. It covers the lockfile, Ruff, ty, documentation,
and distributions, but omits hygiene hooks and coverage collection:

```bash
uv run --locked python scripts/check_quality.py --skip-tests
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
targeting `main` and on manual dispatch.
Integration into `main` does not trigger a duplicate run. It runs the all-files
pre-commit quality gate once on Ubuntu, tests the locked environment on Ubuntu
and macOS under Python 3.12 and 3.14, adds Python 3.13 on Ubuntu,
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
skipped. The complete diff (including both sides of renames) is classified by
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
Issue Source. The `.dashpot/state/` directory holds ignored local runtime
state, including the Work Store; add it to your repository's `.gitignore` so it never
dirties the worktree or gets committed:

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
([ADR 0048](docs/adr/0048-adopt-python-3-13-typing-backports-on-the-3-12-baseline.md)).
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
defaults its Work list to open Issues. Both adapters are currently read-only.

## Agent session observation

Dashpot observes Codex and Claude Code sessions through opt-in lifecycle hooks
installed once per user with `dashpot integrate`. The same command installs the
model-invoked `dashpot-issue-work` skill in the harness's user skill directory;
the skill resolves and declares Issue work, dispatches Worktree handoffs, and
holds the Issue Binding through the repository's delivery workflow. A declared
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
reports the Worktree removable, or
each reason it is not with the command that acts on it: dirty state, a lock
with its reason and whether the holding process is alive (`initializing`
names the forced removal), Agent Sessions whose hooks place them there,
Agent Runs recorded there (an Orphaned Agent Run names its
`dashpot work stop --session` command), and commits not on the upstream or
the Integration Branch. `check` removes nothing.

`worktree remove PATH` and `branch delete NAME` are the Cleanup commands of
[ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md).
Each takes the same read-only preview the dashboard's `x` opens — every
target with its integration state, blockers, and consequences — then
re-inspects and performs only the targets its flags name, only if nothing
observed has changed in between. `worktree remove` removes one linked Worktree with an unforced
`git worktree remove`, so a dirty or locked Worktree is refused, and with
`--delete-branch` deletes its local Branch afterwards; `--delete-ignored`
acknowledges that the Worktree's ignored content (`.venv`, `.dashpot/state/`,
hook records, and the Work Store there) goes with it, and the command is
refused without it when such content exists. `branch delete --local` deletes
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
Neither command deletes the Integration Branch, a checked-out Branch, a
Branch with commits the Integration Branch does not reach, or a Worktree that
is the main one, dirty, locked, occupied by an Agent Session or Agent Run,
the checkout the command runs from, or a configured Repository Anchor (the
checkout's own root when it carries a Project configuration, and every anchor
of the Workspace config). Every target reports its own outcome —
`deleted`, `already-absent`, `refused`, or `unknown` when Git did not answer —
with the command that recreates a deleted one, and after a refused or unknown
outcome the remaining targets are not attempted. `--dry-run` validates the
selection and lists what would be attempted, in order; `--json` prints the
report (`kind`, `subject`, `anchor`, `dryRun`, `performed`, `changed`,
`refusals`, `planned`, `results`, `succeeded`, and the `preview`). The exit
code is 0 only when every selected target was deleted or already absent.

The created Worktree carries no harness. The installed Issue-work skill moves
a running Claude Code session with `EnterWorktree`, or hands a Codex session
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
[`docs/adr/`](docs/adr/).

## Contributing

Every change lands on `main` the same way, whether a human or an agent makes
it:

1. Branch from `main` for the change.
2. Complete the [local review gate](#local-review-gate) and independent review
   as specified in [AGENTS.md](AGENTS.md#independent-review-before-integration).
   Address findings and refresh affected validation and review. Commit with
   the commit hooks installed, then verify coverage evidence still matches.
   A commit message line `Closes #N`
   is what closes the Issue on GitHub once the commit reaches `main`.
3. Push the branch and open a pull request targeting `main` after local
   validation and review. The pre-push hook runs the pushed-revision gate in
   [`scripts/check_quality.py`](scripts/check_quality.py) against the pushed
   revision in a detached worktree, so a red gate stops the push. That gate
   deliberately skips the test suite; local coverage has already run it and
   pull-request CI confirms it across every platform. Fill in the PR template
   with the review base, source digest, final commit, checks, coverage
   observations, and review findings/dispositions.
4. Watch the latest pull-request CI run to completion with
   `gh run watch <id> --exit-status`. Every required job must pass before
   integration. If the branch changes, validate and review the changes and
   wait for its new CI run. `main` advancing beyond the branch's base is not
   a reason to update the branch; only a textual conflict is.
5. Enable auto-merge with `gh pr merge --squash --auto <number>` following
   the [integration procedure](docs/development-integration.md#integrate-a-verified-pr).
   GitHub squash-merges the PR once every required check on its head is
   green; the merged result is not verified before it lands. Verify the PR is
   merged, synchronize the local main checkout only through an authorized
   fast-forward, and leave Worktree cleanup separate.

Agent sessions use the `dashpot-issue-work` skill to declare and verify the
Issue they are working on (see
[Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in)); the expectations
on agents themselves are in [`AGENTS.md`](AGENTS.md).

## Documentation map

These `living` documents carry the detail this README points at:

- [`docs/installation.md`](docs/installation.md) covers installation, support,
  configuration, diagnosis, upgrades, and removal.
- [`docs/releasing.md`](docs/releasing.md) covers release gates, publishing, and recovery.
- [`docs/development-integration.md`](docs/development-integration.md) covers
  Dashpot's required CI ruleset and the integration procedure.
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
- [`docs/design-research/README.md`](docs/design-research/README.md) indexes
  the design research — the research and analysis behind Dashpot's
  direction: keeping understanding of a codebase, held by a person and by a
  team, as agents author more of it; the friction that keeps it; and the
  work rather than the session as the unit.

[`docs/adr/`](docs/adr/) records architectural decisions, one ADR per
decision. The other files in [`docs/`](docs/) are research, audits, and
proposals that informed decisions and implementation.
The [OpenCode identity and lifecycle experiment](docs/opencode-identity-lifecycle-spike.md)
records the reproducible evidence for a possible OpenCode integration, the
[Claude Code identity and lifecycle experiment](docs/claude-code-identity-lifecycle-spike.md)
the measured Claude Code headless and background-worker lifecycle, and the
[Codex identity and lifecycle experiment](docs/codex-identity-lifecycle-spike.md)
the measured Codex app-server and `codex exec` thread lifecycle. The
[Cleanup session handoff feasibility experiment](docs/cleanup-session-handoff-feasibility-spike.md)
measures whether an opted-in controller can move a live interactive session
out of a Worktree on either harness, and proposes the arrangement per harness;
the [Codex declared relocation on a daemon-hosted thread](docs/codex-declared-relocation-daemon-spike.md)
experiment then verifies the sequential `codex resume -C` route of ADR 0029
against the managed daemon.
The [test-duration measurements](docs/test-duration-measurements.md) record the
development-suite baseline and a focused synchronization improvement.
The [codebase review of 2026-09-13](docs/codebase-review-2026-09-13.md) records
a point-in-time survey of clean-code uplifts, package boundaries, and
decomposition seams for the largest modules; the
[codebase review of 2026-09-17](docs/codebase-review-2026-09-17.md) audits
how that plan landed and reviews the resulting state.
[ADR 0042](docs/adr/0042-group-leaf-and-domain-modules-into-subpackages.md)
records the completed package layout and application composition seam.
[ADR 0043](docs/adr/0043-retain-distinct-query-and-collection-adapters.md)
records why query and complete-collection adapters retain distinct contracts,
and [ADR 0047](docs/adr/0047-keep-the-dashboard-screen-as-one-textual-adapter.md)
why the dashboard screen stays one Textual adapter.
[ADR 0048](docs/adr/0048-adopt-python-3-13-typing-backports-on-the-3-12-baseline.md)
records which Python 3.13 typing backports the 3.12 baseline adopts,
[ADR 0049](docs/adr/0049-interrupt-observation-commands-at-dashboard-exit.md)
why quitting interrupts the observation commands in flight, and
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

`uv run python scripts/check_docs.py` enforces the frontmatter and every
in-repo Markdown link, and runs as part of the [quality gates](#quality-gates).

## License

MIT
