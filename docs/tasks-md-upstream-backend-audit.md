# Upstream tasks.md backend audit

## Scope and source pin

This audit covers the upstream [`tasksmd/tasks.md`](https://github.com/tasksmd/tasks.md)
repository at commit
[`90bf97361c80f9c479eeaed7cd7fdefa8ad97416`](https://github.com/tasksmd/tasks.md/commit/90bf97361c80f9c479eeaed7cd7fdefa8ad97416),
committed 2026-08-21 and inspected 2026-08-26. The package manifests at that
commit still declare CLI/parser/MCP version `0.10.2`; the latest GitHub release
is also [`v0.10.2`, published 2026-07-14](https://github.com/tasksmd/tasks.md/releases/tag/v0.10.2).
The audit is therefore pinned to current `main`, which contains unreleased work
after the tag, rather than treating the tag as equivalent to the inspected tree.

The three in-repo backends are:

- file, called `tasks-md`, whose source of truth is one or more `TASKS.md` files;
- `git-native`, whose source of truth is an event log on `refs/heads/tasks-claims`;
- `github-issues`, whose source of truth is open GitHub Issues carrying a marker
  label.

All claims below come from upstream specification, implementation, and tests at
the pinned commit, plus the official GitHub CLI manual where the adapter leaves
GitHub functionality unused.

## Executive finding

The worry about using tasks.md as Dashpot's data-model foundation is justified.
The upstream promise is that the spec, parser, CLI, and MCP surface behave
identically across backends
([spec](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L531-L533),
[vision](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/VISION.md#L13-L23)).
The code does not currently provide that contract.

There are actually three increasingly narrow models:

1. The Markdown spec defines at least 22 named metadata fields, custom fields,
   policies, subtasks, claims, file/line location, and multi-file discovery
   ([spec fields](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L196-L261),
   [parser model](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/parser/src/index.ts#L1-L74)).
2. The pluggable `BackendTask` keeps only `id`, `title`, `priority`, `tags`,
   `assignee`, `body`, `blocked`, `blockedBy`, `url`, and git-native claim/lease
   fields
   ([backend types](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/types.ts#L9-L45)).
3. The GitHub adapter populates only `id`, `title`, `priority`, `tags`, first
   assignee, body, and URL. It has no representation for either blocker form or
   any richer Markdown metadata
   ([mapping](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L132-L142)).

The CLI hides this split by bypassing `TaskBackend` for file-backed `pick` and
`list`, while using `TaskBackend` for git-native and GitHub
([pick branch](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L331-L390),
[list branch](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L397-L442)).
Consequently JSON schemas, filtering, ordering, location, and metadata vary with
the configured backend even when the command is the same.

For Dashpot, tasks.md is usable as an **ingestion protocol**, provided Dashpot
owns its canonical domain model and treats each upstream backend as a lossy
adapter with explicit capabilities. It is not safe to adopt upstream
`BackendTask`, `tasks list --json`, or the Markdown AST as a single authoritative
domain model without a normalization and provenance boundary.

## Capability matrix

`✓` means the inspected implementation supplies the behavior through the named
backend path. `Partial` means that only a narrower or behaviorally different
version exists. `—` means absent or explicitly unsupported.

| Concern | File (`tasks-md`) | Git-native | GitHub Issues |
| --- | --- | --- | --- |
| Source of truth | Discovered `TASKS.md` files | `tasks-claims` event log | Marker-labelled open issues |
| Offline read/write | ✓ | ✓ locally; cross-machine freshness needs origin | — |
| Stable identity | Optional kebab-case `**ID**`; CLI-created slug can collide | Unique slug in current fold | Issue number string, repository implicit |
| Title / priority / tags / body | ✓ | ✓ | ✓ |
| `Blocked` / `Blocked by` in backend record | Parser ✓; `TaskBackend` mapping drops both | ✓ | — |
| Rich/custom metadata | ✓ in parser/file tools | — | — |
| Policies and subtasks | ✓ in parser | — | — |
| File/line location | ✓ | — | No file/line; single-repo records have a URL, but workspace mode drops it and synthesizes `TASKS.md:0` |
| List includes claimed/blocked tasks | CLI `list` ✓; `TaskBackend.listOpen` no | ✓ | ✓ |
| Deterministic picker semantics | Priority, blockers, standing-loop, impact, tag preference | Priority + blockers only | Priority + unassigned only |
| Programmatic create | Partial; narrow fields, location and ID defects | ✓ for narrow backend model | Partial; ignores blockers |
| Programmatic update | — (direct file edit advised) | ✓ for narrow backend model | — (manual issue edit advised) |
| Claim exclusivity | Best effort | Ref-CAS, leases, fencing | No exclusivity check; adds `@me` as another assignee |
| Release / complete / cancel | ✓ | ✓ | ✓ |
| Heartbeat / lease / steal | — | ✓ | — |
| Render `TASKS.md` | Reads only the constructor-relative root file | Deterministic narrow projection | — |
| Workspace aggregation | Root file only per repo | Partial; blockers are discarded | Partial; errors/repos may disappear |
| Conformance target in CI | One lifecycle check; capability skips | 11 applicable properties asserted | None; mocked command tests only |
| Pagination / bound | Filesystem discovery; no task count cap | Whole log; compaction suggested at 5,000 events | Hard cap of 200 open issues |

The declared backend capabilities themselves are a useful concise source for
the broad operation split
([file](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L46-L68),
[git-native](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L62-L82),
[GitHub](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L88-L109)).
Those capability objects do not capture the field loss and command-path
differences described below.

## Detailed audit

### 1. Configuration and backend resolution

Common behavior:

- `.tasksmd.json` is resolved at the git root, falling back to the supplied
  directory outside git. `--backend` overrides only the backend kind. The only
  common config fields are `backend`, optional GitHub `repo`, and GitHub marker
  `label` (default `tasks.md`)
  ([config](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/config.ts#L5-L69)).
- Unknown backend names and malformed JSON produce useful errors. The config
  loader does not runtime-validate the types or formats of `repo` and `label`.

Disjoint behavior:

- Git-native also reads an undocumented-in-the-config-type `autoRefresh`
  boolean directly from `.tasksmd.json`; lease duration is only injectable via
  the programmatic constructor
  ([git-native options and auto-refresh](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L49-L60),
  [auto-refresh read](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L192-L209)).
- The GitHub adapter constructor is not given the target directory, so its `gh`
  processes have no explicit `cwd`; an omitted `repo` is resolved from the host
  process's current directory
  ([backend factory](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/index.ts#L7-L18),
  [GitHub process wrapper](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L88-L117)).
  This matters in workspace aggregation, which constructs a backend for each
  `repoRoot` without changing process `cwd`; an unqualified GitHub config can
  therefore query the wrong repository.
- File `create()` and `render()` use `directory/TASKS.md`, while file reads and
  ID mutations recursively discover from the git root. Invoking backend-aware
  commands from a git subdirectory can therefore read the repository queue but
  create/render a different subdirectory file
  ([file backend paths](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L46-L47),
  [create/render](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L84-L110),
  [discovery scope](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/parser/src/discovery.ts#L29-L49)).

### 2. Task identity

- The Markdown spec permits tasks without IDs; IDs are only required for
  references and are intended to be unique across all repository task files
  ([spec](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L183-L194)).
  In contrast, every `BackendTask` requires a string ID and every backend-aware
  mutation addresses an ID.
- File `create()` generates a 60-character slug from title, with no collision or
  empty-slug handling. Git-native generates the same style of slug but adds a
  suffix until it is unique, with a UUID fallback for an empty slug
  ([file ID](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L84-L110),
  [git-native ID](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L286-L304)).
- GitHub identity is only the decimal issue number string. Repository identity
  is implicit in adapter configuration, not part of `BackendTask.id`; only the
  URL is globally identifying. Dashpot must therefore qualify an upstream ID by
  source repository.
- Duplicate file IDs are handled inconsistently: `claim()` takes the first
  match, while `complete()`/`cancel()` remove every matching block across every
  discovered file
  ([claim](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L113-L134),
  [remove all matches](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L187-L207)).

### 3. Fields, metadata, and round-trip loss

The genuinely common round-trippable subset is:

`title`, `priority`, `tags`, and a free-form body/details string.

Even that subset is not identical:

- GitHub reads the highest-priority recognized label if several exist, defaults
  missing/unknown priority to P2, preserves non-priority label casing as tags,
  and excludes the marker and recognized priority labels
  ([label mapping](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L17-L79)).
- File `create()` mistakenly writes the priority itself as a lower-case tag
  (`p0` etc.) but returns a task whose `tags` omit it
  ([file create](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L84-L110)).
- CLI create accepts `--blocked` and `--blocked-by` for every backend
  ([CLI](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L600-L633)).
  Git-native persists both. File and GitHub accept them through the shared type
  but silently omit them during create. This is silent data loss, not an
  `unsupported` result
  ([git-native create](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L835-L866),
  [file create](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L84-L110),
  [GitHub create](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L178-L203)).
- The file parser supports named metadata including Files, Acceptance, Plan,
  Parent, Research, Last-enriched, Estimate, Verification, Risk, five Rule-#9
  fields, Touches, Surfaced-by, and Milestone, plus arbitrary custom fields.
  None exists in `BackendTask`; git-native rendering and migration preserve only
  the narrow model, so moving a rich file queue to git-native is lossy despite
  the vision's portability language
  ([spec field table](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L232-L261),
  [git-native render](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L703-L728),
  [migration model](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L1063-L1123)).
- Policies and parent subtasks are file-AST concepts with no backend-neutral
  representation
  ([parser](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/parser/src/index.ts#L53-L74),
  [subtask parsing](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/parser/src/index.ts#L176-L249)).

GitHub itself now exposes native `blockedBy`/`blocking` JSON fields and
`--blocked-by`/`--add-blocked-by` mutation flags
([official `gh issue list`](https://cli.github.com/manual/gh_issue_list),
[official `gh issue create`](https://cli.github.com/manual/gh_issue_create),
[official `gh issue edit`](https://cli.github.com/manual/gh_issue_edit)). The
adapter neither requests those JSON fields nor uses those flags, so this is an
adapter gap rather than an unavoidable GitHub limitation.

### 4. List and pick JSON contracts

There is no common JSON schema across backends.

`tasks pick --json` returns:

- file: `{picked, summary, priority, file, line, metadata, candidates,
  unblocks}`;
- git-native/GitHub: `{picked, ...BackendTask}`;
- workspace mode: `{picked, workspace, repo, id, summary, priority, backend,
  file, line, ref}`.

These three branches are visible in one command implementation
([workspace/non-file/file branches](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L293-L370)).

`tasks list --json` returns:

- file: `ListedTask[]` with `id?`, `summary`, `priority`, `tags`, computed
  boolean `blocked`, `claimed`, `file`, and `line`;
- git-native/GitHub: `BackendTask[]` with required `id`, `title`, `priority`,
  `tags`, and backend-specific optional fields.

The file schema is defined separately
([ListedTask](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/lib.ts#L24-L81))
and the CLI emits the two array types without a common envelope
([list command](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L397-L442)).
There is no CLI `show`/`read <id>` operation.

MCP is a fourth shape: file `list_tasks` returns `{summary, tasks}` where each
task carries the full `metadata` object and optional `subtasks`, while non-file
MCP delegates to CLI and returns its bare array
([file MCP format](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/tools.ts#L40-L102),
[delegation](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/index.ts#L60-L89)).

### 5. Filters and ordering

File picking is the richest algorithm. It skips claimed, blocked, and
`standing-loop` tasks, orders by P0→P3, then prefers tasks that unblock the most
other tasks, then tag overlap. A requested tag acts as a preference: it filters
only if at least one candidate matches
([picker](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/parser/src/index.ts#L345-L405)).

Git-native `next()` orders by priority and skips assignees plus its two blocker
forms, but does not skip `standing-loop`, score unblocking impact, or resume a
prior actor claim
([git-native next](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L818-L832)).

GitHub `next()` takes the first unassigned item from its priority-stable sorted
list. It cannot account for blockers and does not skip standing loops or score
impact
([GitHub next](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L148-L175)).

For `list`, priority, tag, and unclaimed filters work in both CLI paths. The
advertised `--unblocked` flag is silently ignored for all non-file backends:
`filterBackendTasks` has no `unblocked` predicate even though the caller passes
the option
([filters](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L561-L580),
[caller](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L397-L428)).
This is observable for git-native, whose records do carry blocker data.

There is a second blocker regression when a non-file pick includes `--tags`:
the CLI bypasses `backend.next()`, filters `backend.listOpen()` only for an empty
assignee, and returns the first tag match. A blocked git-native task can therefore
be returned by `tasks pick --tags ...` even though `tasks pick` without tags
would skip it
([tagged backend pick](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L582-L597)).

Tie ordering is source order, not a common semantic. The shared priority sorter
is explicitly stable
([sort](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/types.ts#L162-L180));
therefore file order, git event-fold order, and GitHub API order survive within
a priority bucket and need not agree.

### 6. Claims, blockers, and lifecycle mutations

File:

- Claims are best-effort text suffixes and have no lease or fencing. `claim()`
  does not reject a blocked task; direct CLI claim can therefore claim work that
  the picker would skip
  ([file claim](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L113-L142)).
- Release does not check the requesting actor; complete/cancel remove the block
  regardless of owner. Missing IDs throw exceptions rather than returning the
  shared `missing` status
  ([file mutations](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L153-L176)).

Git-native:

- Implements collision-free remote ref compare-and-swap, 24-hour default
  leases, heartbeats, steal after expiry, and claim fencing
  ([capability and defaults](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L49-L82),
  [claim](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L878-L971),
  [heartbeat](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L1000-L1032)).
- Blocked state affects `next()` and `claim()`. This is the only adapter where
  blocker state survives the narrow backend contract end-to-end.
- `update()` and `claim()` return `missing`, but release/complete/cancel can
  append an event for a nonexistent task and still return `ok`; the fold ignores
  that event. Error semantics are therefore inconsistent within the backend
  ([update and lifecycle](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L974-L1059)).

GitHub:

- Claim always runs `gh issue edit <id> --add-assignee @me` and returns
  `claimed`; it does not first verify marker label, current assignees, blocker
  state, or the post-write owner. Release removes only `@me`
  ([claim/release](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L205-L230)).
- GitHub permits adding assignees rather than atomically replacing a sole owner
  (the official CLI explicitly calls the operation “Add assigned users” and
  accepts multiple logins: [`gh issue edit`](https://cli.github.com/manual/gh_issue_edit)).
  Two agents can both become assignees. The adapter then exposes only
  `issue.assignees[0]`, so this does not implement an exclusive claim.
- Complete/cancel close any issue number supplied, even if it does not carry the
  marker label. Update is explicitly unsupported, though the reason tells the
  caller to edit manually
  ([mutations](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L217-L249)).

### 7. MCP parity gaps

The MCP README says non-file mutation tools delegate to the CLI, but the surface
is not behaviorally identical
([README](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/README.md#L35-L64)).

- `claim_task` advertises an ID **or summary substring** and requires
  `agent_name`. On non-file backends it passes only `tasks claim <query>`: the
  summary fallback no longer exists and the supplied actor identity is dropped
  ([MCP claim](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/index.ts#L92-L140)).
- `pick_task(task_id=...)` provides exact targeting, duplicate detection,
  blocked status, and resume status only for the file backend. On non-file
  backends `task_id` is not passed to the CLI at all; queue pick occurs instead
  ([non-file branch](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/index.ts#L233-L302),
  [file exact-target implementation](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/tools.ts#L250-L366)).
- `add_task` accepts rich file fields but deliberately sends only title,
  priority, details/body, and tags for non-file backends. It drops the caller's
  explicit ID, files, acceptance, blockers, research, and enrichment date
  ([MCP create](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/index.ts#L305-L405)).
- `enrich_task` has no backend branch. It always discovers and edits Markdown,
  even though git-native declares `TASKS.md` a generated snapshot that agents
  must not edit, and GitHub may have no file surface at all
  ([enrich registration](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/index.ts#L408-L466),
  [git-native source-of-truth rule](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L613-L619)).
- There are no MCP tools for generic update, cancel, render, or heartbeat,
  despite the specification's operation table saying each mutation maps to a
  CLI command, MCP tool, and backend method
  ([spec table](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L581-L598),
  [registered tool catalog](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/mcp/src/tools.ts#L15-L33)).

### 8. Location, discovery, and workspaces

Single-repository file discovery recursively finds every `TASKS.md` below the
git root, excluding `.git` and `node_modules`, and reports real file/line
location. Outside git it checks only a direct file
([discovery](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/parser/src/discovery.ts#L21-L123)).
That conflicts with the current vision of “one root TASKS.md per repo”
([vision G3](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/VISION.md#L13-L14)).

Workspace discovery is shallower and different: it sees only the workspace root
and immediate child directories containing root `TASKS.md` or `.tasksmd.json`
([workspace discovery](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/commands/workspaces.ts#L34-L56)).
For file repos it parses only the root file, so nested task files visible in
single-repo mode disappear in workspace mode.

For non-file repos workspace aggregation explicitly overwrites `blockedBy` with
an empty array and omits `blocked`, even though git-native's `BackendTask`
contains both. A blocked git-native task can therefore become globally pickable
([mapping](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/commands/workspaces.ts#L97-L121),
  [pickability](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/commands/workspaces.ts#L127-L142)).
GitHub tasks have no blocker state to carry in the first place.

Other workspace differences:

- inaccessible/unauthenticated non-file repos are silently skipped;
- non-file locations are reported as synthetic `<repo>/TASKS.md` line `0`, even
  for GitHub Issues, which instead have a real URL;
- ties use workspace/repo lexicographic order, not file picker's impact or tag
  scoring;
- config fields `exclude`, `priorityWeight`, and `discovery.autoDetect` are
  parsed but not applied by aggregation/detection
  ([config model](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/config/workspaces.ts#L11-L26),
  [selection](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/config/workspaces.ts#L79-L111),
  [gather and sort](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/commands/workspaces.ts#L58-L172)).

The spec says both `tasks next` and `list` aggregate workspaces, but only
`pick`/`next` exposes workspace flags; `list` does not
([spec](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L703-L741),
[CLI options](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L274-L283),
[list options](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L397-L406)).

### 9. Limits, pagination, freshness, and errors

GitHub:

- `listOpen()` hard-codes `gh issue list --limit 200`; there is no cursor or
  follow-up page. Repositories with more than 200 open marker-labelled issues
  expose a truncated queue
  ([implementation](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L148-L170),
  [official limit semantics](https://cli.github.com/manual/gh_issue_list)).
- Auth has a specific actionable error, but after auth succeeds **any** issue
  list failure—network, permissions, invalid repository, rate limiting, timeout—
  is converted to `[]`. “Queue empty” is indistinguishable from “queue could not
  be read.” JSON parse errors still escape
  ([auth/list handling](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L111-L170)).
- Commands use 30-second operation timeouts and a 10-second auth timeout. Other
  mutation failures throw raw subprocess errors rather than returning the
  backend-neutral status union.

File:

- Git-root discovery gives `fd` 10 seconds, then falls back to an unbounded
  recursive walk. Inaccessible directories and unreadable files are silently
  skipped
  ([discovery](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/parser/src/discovery.ts#L61-L123)).
- There is no task-count limit or pagination because reads return the entire
  discovered queue.

Git-native:

- Reads fold the entire log using two git processes and a 256 MiB `cat-file`
  buffer; individual git processes time out at 30 seconds
  ([read implementation](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L103-L175),
  [log scan](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L465-L509)).
  The doctor suggests compaction after 5,000 events
  ([threshold](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/commands/fleet.ts#L12-L13)).
- Fetch failures are ignored by `fetchClaimsRef`, so reads can operate on a
  stale local ref. This enables offline operation but gives no freshness signal
  ([fetch](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L177-L190)).
- Non-claim writes retry remote contention up to eight times with bounded
  backoff, then throw
  ([retry](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.ts#L731-L766)).

### 10. Conformance evidence

The in-repo suite has 12 named properties and seven capability gates. It tests
claim races, stale/idempotent projection, mutable update, leases and heartbeat
fencing, serialization, claim/path fencing, release/reclaim, and blocked-by
unclaimability
([contract](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/conformance/src/types.ts#L62-L115),
[checks](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/conformance/src/checks.ts#L42-L305)).
It does **not** test field round-tripping, JSON output schemas, filtering parity,
priority tie ordering, discovery/location, pagination, errors, exact lookup, or
workspace behavior.

- Git-native has a real multi-clone conformance target. Its test asserts 11
  applicable properties run and pass; `canonical-serialization` is honestly not
  claimed because raw event injection is unavailable
  ([target capabilities](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.conformance.test.ts#L151-L171),
  [asserted checks](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/git-native.conformance.test.ts#L174-L208)).
- File has a conformance target, but only the ungated `release-and-reclaim`
  lifecycle property is asserted to pass; collision, snapshot, lease,
  enforcement, blocker, and mutable-update capabilities are declared false and
  skipped
  ([file target](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.conformance.test.ts#L76-L119)).
- GitHub has **no `ConformanceTarget` and no live workflow in the repository**.
  Its adapter tests mock `execFileSync` and cover only auth messaging, mapping,
  priority, create argv, claim argv, complete argv, and repository threading
  ([tests](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.test.ts#L1-L117),
  [CI](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/.github/workflows/ci.yml#L66-L81)).

The conformance README nevertheless says the GitHub backend “inherits
collision-free claiming from GitHub's server-side issue-assignee atomicity” and
that a live conformance run occurs outside the unit suite
([claim](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/conformance/README.md#L1-L15)).
No such target or workflow exists in the inspected tree, and add-assignee is not
an exclusive compare-and-swap. The package is also `private: true`, version
`0.0.0`, despite README language about third-party self-certification
([manifest](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/conformance/package.json#L1-L18)).

## Explicitly unsupported or scoped-out behavior

Upstream explicitly identifies these limitations:

- file claims are best effort and visible cross-agent only after push
  ([spec](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L497-L513));
- file and GitHub programmatic update are unsupported; GitHub render is
  unsupported
  ([file](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/tasks-md.ts#L144-L150),
  [GitHub](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/backend/github-issues.ts#L217-L249));
- heartbeat/leases are git-native only
  ([CLI](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/packages/cli/src/cli.ts#L739-L762));
- workspaces do not support atomic multi-repo claim/complete, a global lease, or
  cross-repo generated-snapshot writes
  ([spec](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L741-L743));
- git-native's single-writer projection is still a workflow template/operator
  responsibility, and a ruleset must make its claim check required
  ([status](https://github.com/tasksmd/tasks.md/blob/90bf97361c80f9c479eeaed7cd7fdefa8ad97416/spec.md#L697-L701)).

Several other gaps in this audit are not marked unsupported; they silently
degrade or contradict the advertised common surface. Those are the greater
risk for a downstream domain model.

## Dashpot's current projection

Dashpot does not currently consume the upstream `TaskBackend` seam. It has two
independent adapters:

- local Markdown runs `tasks list --json` and expects the file-only
  `ListedTask[]` shape;
- GitHub runs `gh issue list` directly and builds its own projection.

That split is visible in
[`sources.py`](../src/dashpot/sources.py): the local adapter requests the CLI's
`summary`/`file`/`line` fields, while the GitHub adapter requests only
`number,title,labels,assignees,url`. It means some discrepancies are inherited
from tasks.md, while others are introduced by Dashpot itself.

| Domain concern | Dashpot local Markdown | Dashpot GitHub Issues | Effective common contract |
| --- | --- | --- | --- |
| Queue membership | Whatever the file `list` command returns | Open issues with one configured marker label | Currently open/declared Tasks only |
| Identity | Absolute root + declared ID, else file/line | Mutable `owner/repo#number` | Collection-time key, not durable identity |
| Title | `summary` | `title` | ✓ |
| Priority | Native P0-P3 string, default P2 | Highest recognized priority label, default P2 | P0-P3 by convention, with silent coercion |
| Tags | TASKS.md tags | Every non-marker, non-priority label | String labels with different source semantics |
| Claimant | One `claimed` string | First GitHub assignee only | One display claimant, not a shared claim contract |
| Blocking | Boolean when emitted, otherwise `unknown` | Always `unknown` | Tri-state field, but no cross-source blocker evidence |
| Details/body | Not returned by this CLI shape | Available from GitHub but not requested | Dropped |
| Dependencies/subtasks | Not returned by this CLI shape | Available natively in current `gh`, but not requested | Dropped |
| Location | File and optional line | Issue URL | Source-specific actionable location |
| Native opaque ID | Declared ID retained inside a path-qualified key | GitHub node ID available but not requested | Not represented |
| Ordering | Preserves CLI order | Stable sort by normalized priority | No adapter-level tie-order contract |
| Read bound | Upstream file discovery behavior | Hard cap of 200 issues | No complete-list guarantee |
| Failure behavior | Nonzero/invalid CLI output becomes a diagnostic | Nonzero/invalid `gh` output becomes a diagnostic | Last-good snapshot is retained |

There are two important positives in Dashpot's own seam:

- `TaskSource.refresh()` consistently preserves last-good data and distinguishes
  fresh, stale, and unavailable observations
  ([implementation](../src/dashpot/sources.py#L34-L63)); and
- unlike upstream's GitHub adapter, Dashpot does not convert a failed `gh issue
  list` call to an empty queue
  ([GitHub collection](../src/dashpot/sources.py#L139-L161)).

The seam is nevertheless too implicit for issue #9:

- [`Task`](../src/dashpot/model.py#L27-L37) combines identity, reference,
  presentation fields, source facts, location, and correlated observations in
  one record;
- `BlockedState = bool | "unknown"` cannot distinguish unsupported,
  not-fetched, malformed, and genuinely unknown;
- a single `declared_claimant` erases GitHub's multiple-assignee cardinality and
  suggests semantic parity with a TASKS.md claim;
- the GitHub API fields that issue #9 needs—opaque `id`, `blockedBy`, `blocking`,
  `parent`, and `subIssues`—are available through current `gh issue list` but
  omitted from the query
  ([official field list](https://cli.github.com/manual/gh_issue_list));
- project/source configuration is loaded from a checkout, and collection calls
  `observe_repository()` before selecting either source, so even GitHub-backed
  observation currently requires a local git worktree
  ([collector construction](../src/dashpot/collect.py#L68-L89)); and
- the external `tasks` executable and its JSON contract are not version-pinned
  in Dashpot's package dependencies
  ([package manifest](../pyproject.toml),
  [documented runtime](../README.md#L62-L76)).

The five focused adapter tests pass, but they test extraction rather than
substitutability. There are no cross-adapter contract cases for durable
identity, multiple claimants, blockers/dependencies, pagination, capability
reporting, or equivalent error semantics
([tests](../tests/test_sources.py)).

## Implications for Dashpot issue #9

1. **Do not make upstream `BackendTask` Dashpot's domain object.** It is a
   transport DTO for a small common subset and cannot represent the canonical
   Markdown task model.
2. **Do not deserialize `tasks list --json` into one unversioned schema.** Branch
   on the actual observed shape, record the upstream version/commit, normalize
   it at an anti-corruption boundary, and retain the raw payload for diagnosis.
3. **Use a source-qualified identity.** At minimum, identity needs backend kind,
   repository/workspace identity, and native ID; file location is also needed
   when IDs are optional or duplicated.
4. **Model capability and provenance explicitly.** Distinguish missing from
   unsupported from unknown/not-fetched. In particular, an absent GitHub
   blocker is not evidence that the task is unblocked, and an empty GitHub list
   may be a swallowed read failure.
5. **Treat writes as backend-specific commands, not symmetric CRUD.** Validate
   postconditions by re-reading the authoritative source. Never assume shared
   CLI options were persisted merely because the operation returned success.
6. **Prefer the GitHub API/`gh` adapter directly if GitHub is a first-class
   Dashpot source.** Upstream's adapter is small enough that inheriting its
   truncation, field loss, cwd ambiguity, and non-exclusive claim semantics buys
   little. GitHub's native blocker fields can be mapped directly.
7. **Keep tasks.md as an optional ingestion/facade layer until upstream has a
   published, versioned contract suite that covers data round trips and a live
   GitHub target.** Git-native has meaningful concurrency evidence; the claimed
   cross-backend data-model parity does not.

The safe architectural reading is: tasks.md supplies a useful Markdown grammar
and workflow vocabulary. Dashpot should supply the durable domain model.
