# Dashpot

_Useful damping for agent-driven projects._

Dashpot is a passive terminal view of declared work, repository state, and active
coding-agent runs. It makes the small but important project-management pause
visible before another prompt or agent adds more motion.

Like its [mechanical namesake](https://en.wikipedia.org/wiki/Dashpot), Dashpot is
intended to reduce oscillation without stopping progress. Observation never
mutates: the view, every refresh, and `dashpot --json` never assign or edit
Issues, change the Git Repository, or control agent sessions. Dashpot's named
management commands — `init`, `integrate`, `work start` and `stop`, `branch
delete` and `worktree remove` — and its two mutating keys — `f`, which fetches
Git remotes, and `x`, which deletes a Branch or removes a Worktree — mutate
only what their name says, on explicit invocation, and report what they
changed
([ADR 0008](docs/adr/0008-let-management-commands-mutate-on-explicit-invocation.md),
[ADR 0014](docs/adr/0014-fetch-remotes-on-explicit-key-press.md)). A Cleanup
goes one step further: it deletes only the targets a person selected from a
read-only preview and confirmed
([ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).

> [!NOTE]
> Dashpot is an early implementation extracted from a successful research spike.
> Its interfaces and packaging are not yet stable.

## What it observes

Everything below is read, never changed: observation's only writes are the
housekeeping of Dashpot's own ignored state, such as pruning the hook record of
a session that has ended.

- Projects with either GitHub Issues or Dashpot's Local Issue Markdown
- active GitHub Pull Requests, including review, checks, and mergeability
- git Branches, Remote-Tracking Branches, worktrees, HEAD, and dirty state
- Codex and Claude Code lifecycle records published through opt-in hooks
- source freshness, failures, and last-good state
- durable Agent Run bindings through opaque Issue Identity

Each source remains independent in the read model. A failed Pull Request
refresh, for example, retains its last good collection without degrading a
healthy Issue Source or hiding repository facts. A Local Issue Markdown
Project reports Pull Requests as not configured rather than inferring a host
from its Git remotes.

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
| `r` | Refresh every observation in the Workspace, observing every GitHub Issue afresh rather than only what changed |
| `f` | Fetch and prune the Git remotes of the Repository Anchor behind the Branches pane, then re-observe its Git state |
| `x` | Preview deleting the highlighted Branch (local, and at each remote) or removing the highlighted Worktree: every target starts unselected, an unavailable one says why, `Delete selected` performs the selection, `Escape` cancels, and a preview that changed in between reopens for another confirmation; refused while the Project fetches, as `f` is refused while it cleans up ([ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)) |
| `Tab` / `Shift+Tab` | Cycle through the Sessions, Worktrees, Branches, Pull Requests, and Issues lists |
| `/` | Focus the Issue search |
| `o` | Cycle the Issue table between open, closed, and all Issues (the `Open` / `Closed` / `All` selector beside the search does the same) |
| `c` | Open the column editor: toggle the visible Issue columns and reorder them with `Ctrl+Up` / `Ctrl+Down`; `Escape` cancels |
| Arrow keys | Move the row cursor in the focused list |
| `Enter` | On an Issue, read it full-screen (`Escape` returns); on a Session with an Issue Binding, highlight that Issue in the table; unbound on Pull Requests |
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

The `PULL REQUESTS` pane lists every open Pull Request of a GitHub-backed
Project, newest update first. Its columns are `STATE`, `#`, `TITLE`, `HEAD`,
`BASE`, `AUTHOR`, `REVIEW`, `CHECKS`, `MERGE`, and `UPDATED`; drafts, review
decisions, the head commit's combined check/status result, merge conflicts,
and mergeability still being calculated are distinct Glyphs explained by the
Legend. Long content scrolls horizontally rather than dropping facts. A fresh
empty collection says `no active pull requests`; stale last-good data and an
unavailable or unconfigured source say so separately.

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
uv run dashpot --workspace my-project=/path/to/project --json
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
  [`pyproject.toml`](pyproject.toml). Then
  [`scripts/check_docs.py`](scripts/check_docs.py) resolves every in-repo
  Markdown link and requires the frontmatter described in the
  [documentation map](#documentation-map); it always reads the whole document
  set, because a link resolves against files the commit need not touch.
- **On push**: the pushed-revision gate in
  [`scripts/check_quality.py`](scripts/check_quality.py), which verifies the
  lockfile, Ruff lint and formatting, ty, the documents, and the distribution
  build for the exact revision being pushed, in a temporary detached worktree. The test suite
  runs in CI across every supported operating-system and Python-version pair.

Run the commit hooks across every tracked file:

```bash
uv run pre-commit run --all-files
```

The gate before every commit is both of these, clean:

```bash
uv run pre-commit run --all-files
uv run pytest -q
```

The pushed-revision gate can also be run directly against the working tree; it
covers the lockfile, Ruff, ty, the documents and the distribution build, but
not the hygiene hooks or the test suite, so it does not replace the two
commands above:

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

Dashpot observes Codex and Claude Code sessions through opt-in lifecycle hooks
installed once per user with `dashpot integrate`, and a session declares the
Issue it is working on with `dashpot work start`. Both commands, the Work Store,
and how a session is identified are documented in
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
  else `worktreeRoot` in the machine-local `~/.config/dashpot/settings.json`
  (`XDG_CONFIG_HOME` respected), else the sibling directory
  `<anchor parent>/<anchor name>.worktrees/`. The root is real-path
  normalised, refused inside any Worktree of the Project, and reported with
  its source.
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
`baseSource`, `baseCommit`, `worktreeRoot`, `worktreeRootSource`, `dryRun`,
`created`, `refusals`, `hints`, `warnings`); a refusal exits 2 in either
mode. `warnings` carries non-fatal observations, such as unknown fields in
the machine-local settings file, which are ignored rather than fatal so a
settings file written by a newer Dashpot never stops this one.

`worktree check [path]` is read-only. With no path it reports every linked
Worktree of the Repository, one after another (`--json` gives a list). It
reports the Worktree removable, or
each reason it is not with the command that acts on it: dirty state, a lock
with its reason and whether the holding process is alive (`initializing`
names the forced removal), Agent Sessions whose hooks place them there,
Agent Runs recorded there (an Orphaned Agent Run names its
`dashpot work stop --session` command), and commits not on the upstream or
the base Branch. `check` removes nothing.

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

The created Worktree carries no harness. Launch whichever harness should
work there with its working directory set — `codex -C <path>` or
`cd <path> && claude` — and declare the Issue from inside that session with
`dashpot work start` ([Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in)); Claude Code's
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
2. Commit with the commit hooks installed. A commit message line `Closes #N`
   is what closes the Issue on GitHub once the commit reaches `main`.
3. Fast-forward `main` onto the branch and `git push origin main`. The
   pre-push hook runs the pushed-revision gate in
   [`scripts/check_quality.py`](scripts/check_quality.py) against the pushed
   revision in a detached worktree, so a red gate stops the push. That gate
   deliberately skips the test suite; run `uv run pytest -q` before pushing
   and let CI confirm it across every platform.
4. Watch CI to completion with `gh run watch <id> --exit-status`; the change
   is done when the run is green.

Agent sessions additionally declare the Issue they are working on with
`dashpot work start` (see [Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in)); the
expectations on agents themselves are in [`AGENTS.md`](AGENTS.md).

## Documentation map

Three `living` documents carry the detail this README points at:

- [`docs/domain-language.md`](docs/domain-language.md) defines the terms used in
  the interface, code, and documentation, including the phrasings to avoid.
- [`docs/agent-sessions.md`](docs/agent-sessions.md) documents `dashpot
  integrate` and `dashpot work`, the Work Store, and how a session is
  identified.
- [`docs/design.md`](docs/design.md) describes how the pieces fit — the
  observation pipeline, the read model, and the seams beneath the interface.

[`docs/adr/`](docs/adr/) records architectural decisions, one ADR per
decision. The other files in [`docs/`](docs/) are research, audits, and
proposals that informed decisions and implementation.
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
