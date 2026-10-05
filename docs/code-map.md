---
status: living
date: 2026-10-05
---

# Code map

Where each concept of the [domain language](domain-language.md) lives in
`src/dashpot`: the concept, the module or modules that own it, and each one's
role in a line. Look a concept up here before searching for it; a module's own
docstring carries the rest of its contract.

The map lists every module Dashpot ships, each linked by its own path, and
every asset beside them. An empty package initializer is left out, since it
holds nothing; an initializer that exports a seam is listed with its package.
`uv run python scripts/maintain_docs.py` fails while a shipped module or asset
is missing from the map or the map links one that is not shipped, so a new
module is added here in the change that creates it, under the concept it
serves.

[ADR 0042](adr/0042-group-leaf-and-domain-modules-into-subpackages.md) records
why the packages are grouped as they are and the
[layering](adr/0042-group-leaf-and-domain-modules-into-subpackages.md#package-layering)
that `tests/test_module_boundaries.py` holds them to: `core` imports no other
package, then `github`, `project`, `issues`, `queries`, `sessions`,
`repository`, `observation` and `ui`, with the entry points above them all.
[`design.md`](design.md) describes how the pieces fit together, and the coding
rules are in [AGENTS.md](../AGENTS.md#code-conventions).

## Entry points and composition

| Concept | Module | Role |
| --- | --- | --- |
| Package | [`__init__.py`](../src/dashpot/__init__.py) | Exports the observation values a library caller reads: the Workspace Snapshot and its parts. |
| | [`py.typed`](../src/dashpot/py.typed) | Marks the package as typed for type checkers. |
| Command line | [`__main__.py`](../src/dashpot/__main__.py) | Runs `python -m dashpot`. |
| | [`cli/__init__.py`](../src/dashpot/cli/__init__.py) | Re-exports `main`, the `dashpot` console script. |
| | [`cli/__main__.py`](../src/dashpot/cli/__main__.py) | Runs `python -m dashpot.cli`. |
| | [`cli/root.py`](../src/dashpot/cli/root.py) | Gathers the command groups on the root App and maps a command line to its exit status. |
| | [`cli/shared.py`](../src/dashpot/cli/shared.py) | The options, Event Log hand-off and outcome recording every command group shares. |
| | [`cli/observe.py`](../src/dashpot/cli/observe.py) | The default command: opens the dashboard, or prints a headless Workspace Snapshot. |
| | [`cli/init.py`](../src/dashpot/cli/init.py) | `dashpot init`: declares the current Repository a Project. |
| | [`cli/work.py`](../src/dashpot/cli/work.py) | `dashpot work`: Issue work for the enclosing Agent Session, and Worker Assignments. |
| | [`cli/worktrees.py`](../src/dashpot/cli/worktrees.py) | `dashpot worktree` and `dashpot branch`: create, check and remove Issue Worktrees, delete Branches. |
| | [`cli/sources.py`](../src/dashpot/cli/sources.py) | `dashpot issue` and `dashpot pr`: read-only questions to the configured Query Source. |
| | [`cli/integrate.py`](../src/dashpot/cli/integrate.py) | `dashpot integrate`: install, check or remove a Harness Integration. |
| | [`cli/events.py`](../src/dashpot/cli/events.py) | `dashpot events`: read the Event Log, or remove its older files. |
| Hook publisher | [`hook.py`](../src/dashpot/hook.py) | The entry point every lifecycle hook runs: reads one hook event from standard input and publishes it. |
| Composition | [`composition.py`](../src/dashpot/composition.py) | Builds the collector and Query Sources for an entry point, and composes Cleanup's preview, selection and execution into a report. |
| Headless output | [`serialization.py`](../src/dashpot/serialization.py) | The published JSON contract: one document shape per command. |

## Declared work

| Concept | Module | Role |
| --- | --- | --- |
| Project | [`project/init.py`](../src/dashpot/project/init.py) | Writes a new Project configuration into the current Repository. |
| | [`project/project_config.py`](../src/dashpot/project/project_config.py) | Reads the Project configuration tracked at a Worktree's root. |
| Workspace, Repository Anchor | [`project/workspace.py`](../src/dashpot/project/workspace.py) | Loads the Workspace inventory and resolves its Repository Anchors to one Project. |
| | [`project/settings.py`](../src/dashpot/project/settings.py) | Machine-local settings — the Worktree Root, Refresh Periods, idle period and Event Level — beside the Workspace inventory. |
| Issue Profile | [`core/issue_profile.py`](../src/dashpot/core/issue_profile.py) | Validates the source-neutral facts every Issue Source conforms its Issues to. |
| Issue Source | [`issues/issue_sources.py`](../src/dashpot/issues/issue_sources.py) | The Issue Source seam, and the parser of the Issue Hints that name Issues. |
| | [`issues/source_factories.py`](../src/dashpot/issues/source_factories.py) | Builds the Issue Source a Project's configuration declares. |
| | [`issues/retaining_source.py`](../src/dashpot/issues/retaining_source.py) | Retains a complete source observation through a diagnosed refresh failure. |
| GitHub Issue | [`issues/github_issues.py`](../src/dashpot/issues/github_issues.py) | Observes a GitHub Issue Source and conforms its Issues, with their Linked Pull Requests, to the Issue Profile. |
| Local Issue | [`issues/local_markdown_issues.py`](../src/dashpot/issues/local_markdown_issues.py) | Observes a Local Markdown Issue Source and conforms its Issues to the Issue Profile. |
| Issue Hint | [`issues/issue_resolution.py`](../src/dashpot/issues/issue_resolution.py) | Resolves an Issue Hint to one Issue through the configured Issue Source. |
| Ready Issue, Open Blocker | [`issues/lifecycle.py`](../src/dashpot/issues/lifecycle.py) | Decides which Issues a lifecycle choice lists: open, Ready, closed or all. |
| Issue search and order | [`issues/search.py`](../src/dashpot/issues/search.py) | Parses the search subset item lists share, and matches Issues against it. |
| | [`issues/ordering.py`](../src/dashpot/issues/ordering.py) | Derives the facts Issues are ordered by: priority, comment activity, dates. |
| Pull Request | [`issues/pull_request_sources.py`](../src/dashpot/issues/pull_request_sources.py) | The seam for observing a complete Pull Request collection. |
| | [`issues/github_pull_requests.py`](../src/dashpot/issues/github_pull_requests.py) | Observes a Project's GitHub Pull Requests as one bounded complete collection. |
| GitHub gateway, Refresh Budget, Rate Limit Pause | [`github/github.py`](../src/dashpot/github/github.py) | Asks GitHub through `gh`: classifies failures as Diagnostics, bounds a refresh by its Refresh Budget, and holds requests through a Rate Limit Pause. |
| | [`github/github_wire.py`](../src/dashpot/github/github_wire.py) | The selected GitHub response shapes and GraphQL field selections. |
| Repository Identity on GitHub | [`github/github_repository.py`](../src/dashpot/github/github_repository.py) | Identifies a GitHub repository: the reference a remote names, and its durable id. |

## Source queries

| Concept | Module | Role |
| --- | --- | --- |
| Query Source, Query Page | [`queries/pages.py`](../src/dashpot/queries/pages.py) | Query Pages, their requests, and the Query Source contract. |
| | [`queries/cached_source.py`](../src/dashpot/queries/cached_source.py) | Keeps a Query Source's failures and bounded last-good observations behind one seam. |
| | [`queries/github_queries.py`](../src/dashpot/queries/github_queries.py) | The GitHub Query Source: pages, Project Totals and Resolved Issues without reading whole history. |
| | [`queries/markdown_queries.py`](../src/dashpot/queries/markdown_queries.py) | The Local Markdown Query Source, over a deterministic revision of the Local Issue documents. |
| Page navigation | [`queries/page_navigation.py`](../src/dashpot/queries/page_navigation.py) | Retains the bounded accepted pages a person moves between, never reconstructing evicted ones. |

## Observation

| Concept | Module | Role |
| --- | --- | --- |
| Workspace Snapshot, Diagnostic | [`core/model.py`](../src/dashpot/core/model.py) | The published observation read model: the Workspace Snapshot, its Projects, Agent Runs and Diagnostics. |
| | [`core/observation_errors.py`](../src/dashpot/core/observation_errors.py) | Names the expected failures an observation boundary contains. |
| Observation scheduling | [`observation/collect.py`](../src/dashpot/observation/collect.py) | The `ObservationCoordinator`: observes each Project's keys, generation by generation, and publishes the Workspace Snapshot. |
| | [`observation/keys.py`](../src/dashpot/observation/keys.py) | Names the scheduled observations, and carries their tickets and outcomes. |
| Observation store | [`observation/observation_store.py`](../src/dashpot/observation/observation_store.py) | Holds the accepted observations per Project and derives the Workspace Snapshot from them. |
| | [`observation/paged_store.py`](../src/dashpot/observation/paged_store.py) | Joins Query Pages and Resolved Issues into the store the dashboard reads. |
| Pane read models | [`observation/list_result.py`](../src/dashpot/observation/list_result.py) | Carries one list query's rows and summary together. |
| | [`observation/issue_list.py`](../src/dashpot/observation/issue_list.py) | The Issues pane read model. |
| | [`observation/pull_request_list.py`](../src/dashpot/observation/pull_request_list.py) | The Pull Requests pane read model. |
| | [`observation/session_list.py`](../src/dashpot/observation/session_list.py) | The Sessions pane read model: every active Agent Session, once. |
| | [`observation/worktree_list.py`](../src/dashpot/observation/worktree_list.py) | The Worktrees pane read model: every Observation Target, once. |
| | [`observation/branch_list.py`](../src/dashpot/observation/branch_list.py) | The Branches pane read model: every Branch, once by name. |
| | [`observation/related_rows.py`](../src/dashpot/observation/related_rows.py) | Selects the related rows a focused pane emphasises in the others. |
| Repository State, Branch, Integration Branch | [`repository/observe.py`](../src/dashpot/repository/observe.py) | Observes a Repository's Observation Targets, Branches and their integration. |
| | [`repository/refs.py`](../src/dashpot/repository/refs.py) | Names a Repository's Branch refs and chooses its Integration Branch among them. |
| Worktree topology | [`core/worktree_paths.py`](../src/dashpot/core/worktree_paths.py) | Locates paths within a Repository's Worktrees, without loading Git observation. |
| | [`repository/worktrees/records.py`](../src/dashpot/repository/worktrees/records.py) | Locates and identifies Worktrees in Git's topology records. |
| Remote Fetch | [`repository/fetch.py`](../src/dashpot/repository/fetch.py) | Fetches every remote of one Repository Anchor on explicit invocation. |
| Issue Worktree, Worktree Root | [`repository/worktrees/create.py`](../src/dashpot/repository/worktrees/create.py) | Prepares an Issue Worktree after validating its plan. |
| | [`repository/worktrees/base.py`](../src/dashpot/repository/worktrees/base.py) | Resolves a new Worktree's base ref and commit. |
| | [`repository/worktree_launcher.py`](../src/dashpot/repository/worktree_launcher.py) | Opens a selected Worktree through one bounded launcher request. |
| Cleanup | [`repository/cleanup/__init__.py`](../src/dashpot/repository/cleanup/__init__.py) | The Cleanup seam the CLI, serialization and dashboard import. |
| | [`repository/cleanup/targets.py`](../src/dashpot/repository/cleanup/targets.py) | Cleanup requests, targets, blockers and preview evidence. |
| | [`repository/cleanup/preview.py`](../src/dashpot/repository/cleanup/preview.py) | Inspects Cleanup targets without mutating their Repository. |
| | [`repository/cleanup/obstacles.py`](../src/dashpot/repository/cleanup/obstacles.py) | Assesses what obstructs removing a Worktree or deleting its Branch: the one Worktree verdict. |
| | [`repository/cleanup/protection.py`](../src/dashpot/repository/cleanup/protection.py) | Names the checkouts a Cleanup never removes. |
| | [`repository/cleanup/selection.py`](../src/dashpot/repository/cleanup/selection.py) | Retains a person's Cleanup choices against refreshed evidence. |
| | [`repository/cleanup/perform.py`](../src/dashpot/repository/cleanup/perform.py) | Performs the confirmed targets after rechecking their evidence, and reports each outcome. |
| | [`repository/cleanup/adapter.py`](../src/dashpot/repository/cleanup/adapter.py) | Adapts Cleanup inspection and execution for the dashboard. |
| | [`repository/worktrees/removability.py`](../src/dashpot/repository/worktrees/removability.py) | The `dashpot worktree check` report, built on the Cleanup preview's Worktree verdict. |
| Sub-agent Override | [`repository/cleanup/override.py`](../src/dashpot/repository/cleanup/override.py) | Lets a person's acknowledgement lift the `sub-agent` blockers a preview names. |

## Agent Sessions

| Concept | Module | Role |
| --- | --- | --- |
| Harness, Harness Adapter | [`sessions/harnesses.py`](../src/dashpot/sessions/harnesses.py) | The Harness Adapters: how each harness identifies an Agent Session and which events locate it. |
| Host Process, Session Liveness | [`sessions/processes.py`](../src/dashpot/sessions/processes.py) | Observes host processes, harness ancestry and PID-namespace isolation. |
| | [`sessions/liveness.py`](../src/dashpot/sessions/liveness.py) | Derives Session Liveness from a session's recorded Host Process. |
| | [`sessions/session_matching.py`](../src/dashpot/sessions/session_matching.py) | Keeps Agent Session Identity apart from shared Host Process evidence. |
| Background Command | [`sessions/working_directories.py`](../src/dashpot/sessions/working_directories.py) | Finds the processes on this host whose working directory is inside a directory. |
| Hook records, Session History | [`sessions/hook_publish.py`](../src/dashpot/sessions/hook_publish.py) | Publishes a hook event to its Agent Session's record stores. |
| | [`sessions/hook_records.py`](../src/dashpot/sessions/hook_records.py) | The hook record and its store: what each event writes, under the store's lock. |
| | [`sessions/hook_scan.py`](../src/dashpot/sessions/hook_scan.py) | Classifies and scans hook records into each session's Session History. |
| | [`sessions/hook_claims.py`](../src/dashpot/sessions/hook_claims.py) | Validates a claimed Agent Session Identity against hook evidence. |
| | [`sessions/deferred_end.py`](../src/dashpot/sessions/deferred_end.py) | Settles a deferred `SessionEnd` by the fate of the Host Process that published it. |
| Publisher Generation, Publisher Record | [`sessions/opencode_publish.py`](../src/dashpot/sessions/opencode_publish.py) | Translates an OpenCode plugin publication into the shared hook record rules. |
| | [`sessions/opencode_publisher_records.py`](../src/dashpot/sessions/opencode_publisher_records.py) | Keeps the Publisher Record of one hook store's OpenCode sessions. |
| Agent Session labels | [`sessions/session_labels.py`](../src/dashpot/sessions/session_labels.py) | Formats an Agent Session's display label, never its identity. |
| Leaving a Worktree, resuming a session | [`sessions/session_exits.py`](../src/dashpot/sessions/session_exits.py) | Names each harness's way to move or end a session, its resume command, and how to stop its Sub-agents, for every surface that tells a person. |
| Agent Run | [`sessions/agent_runs.py`](../src/dashpot/sessions/agent_runs.py) | Observes Agent Runs and Agent Sessions across the Work Stores and hook stores. |
| Orphaned Agent Run | [`sessions/orphaned_runs.py`](../src/dashpot/sessions/orphaned_runs.py) | Tells an Orphaned Agent Run by the one rule observation, `work` and Cleanup share. |
| Issue Binding | [`sessions/agent_bindings.py`](../src/dashpot/sessions/agent_bindings.py) | Validates observed Agent Runs' Issue Bindings against the Issues. |
| Issue work | [`sessions/session_identity.py`](../src/dashpot/sessions/session_identity.py) | Identifies the Agent Session enclosing a `work` command. |
| | [`sessions/work.py`](../src/dashpot/sessions/work.py) | Declares, relocates, ends and shows Issue work for the enclosing Agent Session. |
| Work Store | [`sessions/work_store.py`](../src/dashpot/sessions/work_store.py) | Persists and reads each Agent Session's active Issue work at one Worktree. |
| Relocation Intent, Live Relocation | [`sessions/work_reconciliation.py`](../src/dashpot/sessions/work_reconciliation.py) | Reconciles Agent Runs from published hook events: ends, continues, carries and completes relocations. |
| Worker Assignment | [`sessions/worker_assignments.py`](../src/dashpot/sessions/worker_assignments.py) | Assigns a Lead's working Sub-agents, as Workers, to Issues, and ends those assignments. |
| Harness Integration | [`sessions/integrate/__init__.py`](../src/dashpot/sessions/integrate/__init__.py) | The integration seam the CLI imports. |
| | [`sessions/integrate/registry.py`](../src/dashpot/sessions/integrate/registry.py) | What each harness's integration installs and where, and the skills and agents it bundles. |
| | [`sessions/integrate/harness.py`](../src/dashpot/sessions/integrate/harness.py) | Installs, removes, checks and describes one harness's integration. |
| | [`sessions/integrate/across.py`](../src/dashpot/sessions/integrate/across.py) | Installs, refreshes and reports several harnesses' integrations in one command. |
| | [`sessions/integrate/arguments.py`](../src/dashpot/sessions/integrate/arguments.py) | Refuses `dashpot integrate` arguments that name no one action, and totals its harnesses' reports. |
| | [`sessions/integrate/installer.py`](../src/dashpot/sessions/integrate/installer.py) | The interface a hook installer implements. |
| | [`sessions/integrate/hooks_file.py`](../src/dashpot/sessions/integrate/hooks_file.py) | Installs, removes and reports Dashpot's handlers in a Codex or Claude Code hooks file. |
| | [`sessions/integrate/opencode_plugin.py`](../src/dashpot/sessions/integrate/opencode_plugin.py) | Installs, removes and reports OpenCode's managed plugin, and the OpenCode it runs under. |
| | [`sessions/integrate/skill_copies.py`](../src/dashpot/sessions/integrate/skill_copies.py) | Manages each harness's copy of a bundled skill. |
| | [`sessions/integrate/agent_copies.py`](../src/dashpot/sessions/integrate/agent_copies.py) | Manages each harness's copy of a bundled agent. |
| | [`sessions/integrate/writes.py`](../src/dashpot/sessions/integrate/writes.py) | Checks every destination `integrate` writes before writing any, then writes each. |
| | [`sessions/integrate/publisher.py`](../src/dashpot/sessions/integrate/publisher.py) | Reports the hook publisher `integrate` binds, and the linked Worktree it may live in. |
| | [`sessions/integrate/diagnostics.py`](../src/dashpot/sessions/integrate/diagnostics.py) | Reports the session record stores and the Agent Session Identity claimed where `--status` runs. |
| Bundled skills, agent and plugin | [`skills/dashpot-issue-work/`](../src/dashpot/skills/dashpot-issue-work/) | The model-invoked skill for Issue work: opt-in, Worktree dispatch, handoff, recovery and finish. |
| | [`skills/dashpot-execute-issues/`](../src/dashpot/skills/dashpot-execute-issues/) | The user-invoked skill a Lead runs to land an Arc of Issues through Workers. |
| | [`agents/dashpot-worker.md`](../src/dashpot/agents/dashpot-worker.md) | The OpenCode agent each Worker of `dashpot-execute-issues` runs as, denied OpenCode's session move. |
| | [`plugins/opencode.js`](../src/dashpot/plugins/opencode.js) | The OpenCode plugin that hands OpenCode's own session events to the hook publisher, in OpenCode's order. |

## Presentation

| Concept | Module | Role |
| --- | --- | --- |
| Dashboard | [`ui/launch.py`](../src/dashpot/ui/launch.py) | Assembles the dashboard around one collector and runs it until it closes. |
| Peer Screen | [`ui/app.py`](../src/dashpot/ui/app.py) | `DashpotApp` and its two Peer Screens, `DashboardScreen` and `IssuesPullRequestsScreen`, with their panes. |
| | [`dashpot.tcss`](../src/dashpot/dashpot.tcss) | The dashboard's stylesheet, which `ui/app.py` loads from the package root. |
| | [`ui/messages.py`](../src/dashpot/ui/messages.py) | The messages the dashboard posts to itself: off-loop outcomes and a layout. |
| | [`ui/status_bar.py`](../src/dashpot/ui/status_bar.py) | Renders navigation and exact Project Totals on both Peer Screens. |
| | [`ui/navigation_summary.py`](../src/dashpot/ui/navigation_summary.py) | Derives the Peer Screen navigation summary from Project Totals. |
| | [`ui/alerts.py`](../src/dashpot/ui/alerts.py) | The alert line and the Diagnostics box. |
| Observation runners | [`ui/observation_runner.py`](../src/dashpot/ui/observation_runner.py) | Runs the keyed observations behind the dashboard, one per key at a time, and sizes its thread pool. |
| | [`ui/page_runner.py`](../src/dashpot/ui/page_runner.py) | Runs the source queries behind the pages, totals and Resolved Issues. |
| Unattended Pause | [`ui/attendance.py`](../src/dashpot/ui/attendance.py) | Whether anyone attends the dashboard, and the Unattended Pause while nobody does. |
| List panes | [`ui/panes.py`](../src/dashpot/ui/panes.py) | Declares each list pane once: what it shows, reads, controls and relates. |
| | [`ui/list_pane.py`](../src/dashpot/ui/list_pane.py) | Presents content-sized, read-only lists in a Peer Screen's pane row. |
| | [`ui/list_rows.py`](../src/dashpot/ui/list_rows.py) | The widget-free shape of a pane row: its columns, cells and clipping. |
| | [`ui/pane_layout.py`](../src/dashpot/ui/pane_layout.py) | The height arithmetic that fits list panes within a Peer Screen. |
| | [`ui/session_cells.py`](../src/dashpot/ui/session_cells.py) | The Sessions pane's columns, state Glyphs and cells. |
| | [`ui/session_table.py`](../src/dashpot/ui/session_table.py) | Dispatches the Sessions pane's keyboard actions apart from mouse selection. |
| | [`ui/worktree_cells.py`](../src/dashpot/ui/worktree_cells.py) | The Worktrees pane's columns, colours and cells. |
| | [`ui/worktree_table.py`](../src/dashpot/ui/worktree_table.py) | Dispatches Worktree keyboard activation apart from mouse selection. |
| | [`ui/branch_cells.py`](../src/dashpot/ui/branch_cells.py) | The Branches pane's columns, Glyphs and cells. |
| | [`ui/pull_request_cells.py`](../src/dashpot/ui/pull_request_cells.py) | The Pull Requests pane's columns, Glyphs and cells. |
| Issue table | [`ui/issue_table.py`](../src/dashpot/ui/issue_table.py) | The Issue table's column catalogue and view state. |
| | [`ui/issue_table_controller.py`](../src/dashpot/ui/issue_table_controller.py) | Drives the Issue table's submitted query, columns, rows and selection. |
| | [`ui/issue_cells.py`](../src/dashpot/ui/issue_cells.py) | The Issue table's cells, Glyphs and chips. |
| | [`ui/column_editor.py`](../src/dashpot/ui/column_editor.py) | Edits which Issue table columns the dashboard shows. |
| Issue Detail | [`ui/issue_view.py`](../src/dashpot/ui/issue_view.py) | The full-screen, read-only rendering of one Issue. |
| | [`ui/detail_fields.py`](../src/dashpot/ui/detail_fields.py) | Renders one selected item's detail fields. |
| Filter bars | [`ui/list_queries.py`](../src/dashpot/ui/list_queries.py) | Owns the queries the Issue and Pull Request filter bars submit. |
| | [`ui/item_filter.py`](../src/dashpot/ui/item_filter.py) | Presents a filter's status, query and matched count. |
| Glyph | [`ui/glyphs.py`](../src/dashpot/ui/glyphs.py) | The Glyph vocabulary: a rendered symbol is never separated from its meaning. |
| Legend, Column Description | [`ui/legend.py`](../src/dashpot/ui/legend.py) | The Legend: every column, Glyph and key the Peer Screens render, explained. |
| Tables and widgets | [`ui/focus_table.py`](../src/dashpot/ui/focus_table.py) | A table whose row cursor shows only while focused, with a header tooltip for each column. |
| | [`ui/spread_table.py`](../src/dashpot/ui/spread_table.py) | A table whose columns share its spare width. |
| | [`ui/keyed_table.py`](../src/dashpot/ui/keyed_table.py) | Keeps a keyed table's selection across refreshes. |
| | [`ui/marked_widgets.py`](../src/dashpot/ui/marked_widgets.py) | `MarkedSelectionList` and `MarkedCheckbox`: toggles whose `X` shows only when on. |
| Remote Fetch on `f` | [`ui/fetch_flow.py`](../src/dashpot/ui/fetch_flow.py) | Runs the Remote Fetch a person asks for, one Project at a time. |
| Cleanup on `x` | [`ui/cleanup_flow.py`](../src/dashpot/ui/cleanup_flow.py) | Runs a Cleanup: preview, confirm, perform, re-observe. |
| | [`ui/cleanup_view.py`](../src/dashpot/ui/cleanup_view.py) | The Cleanup dialog: each target's choice, blockers, consequences and evidence. |
| Runtime screen | [`ui/runtime_view.py`](../src/dashpot/ui/runtime_view.py) | The Runtime screen that holds the Events and Stats tabs. |
| | [`ui/runtime_events_view.py`](../src/dashpot/ui/runtime_events_view.py) | The Events tab: this dashboard's buffered Runtime Events, one per row. |
| | [`ui/runtime_stats_view.py`](../src/dashpot/ui/runtime_stats_view.py) | The Stats tab: this dashboard's Runtime Stats. |

## Runtime

Three modules with near-identical names split the Event Log between them.
[`event_logs.py`](../src/dashpot/event_logs.py), at the package root, decides
where one process's Event Log is and at which Event Level, then opens it;
[`core/event_log.py`](../src/dashpot/core/event_log.py) is the writer that
open returns, appending events and timing spans;
[`core/event_log_files.py`](../src/dashpot/core/event_log_files.py) works on
the files afterwards, finding, reading, measuring and removing them. The
opener sits at the root because it reads the Project's settings, which `core`
may not import. [`observability-design.md`](observability-design.md#implementation)
holds the design they implement.

| Concept | Module | Role |
| --- | --- | --- |
| Event Log, Event Level | [`event_logs.py`](../src/dashpot/event_logs.py) | Opens one process's Event Log: chooses its checkout or the machine-local fallback, and its Event Level. |
| | [`core/event_log.py`](../src/dashpot/core/event_log.py) | The `EventLog` writer: appends a process's Runtime Events and times its work as spans. |
| | [`core/event_log_files.py`](../src/dashpot/core/event_log_files.py) | Finds, reads, measures and removes an Event Log's files, merging a Repository's by time. |
| Runtime Event | [`core/runtime_events.py`](../src/dashpot/core/runtime_events.py) | The closed models of every Runtime Event, and the tolerant reader of one line. |
| | [`core/command_outcomes.py`](../src/dashpot/core/command_outcomes.py) | Records a management command's `command.outcome` Runtime Event. |
| | [`ui/refresh_spans.py`](../src/dashpot/ui/refresh_spans.py) | Times each dashboard refresh, and every key it asks for, as spans. |
| | [`ui/change_events.py`](../src/dashpot/ui/change_events.py) | Records the Agent Session and Diagnostic changes a dashboard observes as Runtime Events. |
| Runtime Stats | [`core/runtime_stats.py`](../src/dashpot/core/runtime_stats.py) | Aggregates a dashboard's buffered Runtime Events into its Runtime Stats. |
| Running Dashpot | [`core/distribution.py`](../src/dashpot/core/distribution.py) | Describes the running Dashpot: its version, how it was installed, and its commit. |

## Shared infrastructure

| Concept | Module | Role |
| --- | --- | --- |
| Interruptible Command | [`core/commands.py`](../src/dashpot/core/commands.py) | Runs one external command to completion through a replaceable runner that a dashboard's exit can interrupt. |
| Git | [`core/git.py`](../src/dashpot/core/git.py) | The one Git adapter for a Repository Anchor, and the runners and timeouts every Git command uses. |
| Commands a person reads | [`core/shell.py`](../src/dashpot/core/shell.py) | Spells a command Dashpot shows a person so it survives a paste into a shell. |
| Validating seams | [`core/pydantic.py`](../src/dashpot/core/pydantic.py) | The Pydantic bases and annotated types for every validating seam. |
| | [`core/json_records.py`](../src/dashpot/core/json_records.py) | Reads strings out of untrusted hook inputs and records. |
| Project-local state | [`core/state_paths.py`](../src/dashpot/core/state_paths.py) | Locates Dashpot's own state: a configured checkout's, or the machine-local fallback. |
| | [`core/record_store.py`](../src/dashpot/core/record_store.py) | The locked, atomic JSON record store beneath the hook and Work stores. |
| | [`core/file_locks.py`](../src/dashpot/core/file_locks.py) | Per-record lock files a pruner may delete without breaking exclusion. |
| Errors | [`core/errors.py`](../src/dashpot/core/errors.py) | The CLI error contract: `DashpotError`, the one-line refusal every seam's error derives from. |
| | [`core/working_directory.py`](../src/dashpot/core/working_directory.py) | Reads a command's working directory, refusing once it no longer exists. |
| Time and wording | [`core/timestamps.py`](../src/dashpot/core/timestamps.py) | Stamps and reads the RFC 3339 UTC instants Dashpot records and observes. |
| | [`core/ages.py`](../src/dashpot/core/ages.py) | Says how long ago an observed timestamp was. |
| | [`core/text.py`](../src/dashpot/core/text.py) | Words the English a person reads the same way on every surface. |
