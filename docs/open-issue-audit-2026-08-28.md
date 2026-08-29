# Open GitHub issue audit

Audit date: 2026-08-28

## Executive conclusion

Dashpot has six open GitHub Issues: [#2](https://github.com/ned2/dashpot/issues/2),
[#3](https://github.com/ned2/dashpot/issues/3),
[#4](https://github.com/ned2/dashpot/issues/4),
[#5](https://github.com/ned2/dashpot/issues/5),
[#12](https://github.com/ned2/dashpot/issues/12), and
[#17](https://github.com/ned2/dashpot/issues/17). None should be closed as
obsolete, but only #2 remains valid without a substantive edit. Issues #3, #4,
#5, #12, and #17 all predate the accepted Project-local ownership decision in
[ADR 0003](adr/0003-prefer-project-local-dashpot-state.md) or recent interface
changes and now describe at least one stale boundary.

Create **two separate foundation Issues**, not one migration umbrella:

1. migrate tracked Project configuration and discovery from `.dashpot.json` to
   `.dashpot/config.json`; then
2. introduce Project-local, ignored work tracking under `.dashpot/state/` and
   give an already-running agent session an explicit start/switch/stop Issue
   workflow.

They share a directory name but not an owner, lifecycle, or compatibility
contract. Configuration is tracked, comparatively static Project definition;
work tracking is ignored, concurrent, machine-local operational state. The
configuration migration should land first so the work-state feature can rely on
one stable Project root and ignore convention.

No existing Issue owns either complete scope. #3 only packages the current
Codex publisher; #13 explicitly excluded legacy Workspace migration, #15
explicitly excluded starting or controlling agent sessions, and #17 explicitly
excludes persistence ([#3](https://github.com/ned2/dashpot/issues/3),
[#13](https://github.com/ned2/dashpot/issues/13),
[#15](https://github.com/ned2/dashpot/issues/15),
[#17](https://github.com/ned2/dashpot/issues/17)). Claude Code support is not
owned by any current Issue and needs its own adapter/integration Issue after the
harness-neutral work-tracking seam exists.

## Current implementation gap

ADR 0003 accepts `.dashpot/config.json` for tracked configuration and
`.dashpot/state/` for ignored local work state, while retaining multi-Project
Workspaces only as secondary composition
([ADR 0003](adr/0003-prefer-project-local-dashpot-state.md)). Main still:

- loads `PROJECT_CONFIG_NAME = ".dashpot.json"`
  ([project_config.py](../src/dashpot/project_config.py));
- discovers that filename in no-argument CLI startup and exposes a global
  `--state-dir` override ([cli.py](../src/dashpot/cli.py));
- publishes all Codex records to a platform-global application-state directory
  by default ([agents.py](../src/dashpot/agents.py));
- documents both old locations ([README.md](../README.md)); and
- does not ignore `.dashpot/state/` ([.gitignore](../.gitignore)).

The current `AgentRun` also represents a whole observed Codex session and stores
its Issue binding directly ([model.py](../src/dashpot/model.py)). The publisher
copies `DASHPOT_ISSUE_ID` or `DASHPOT_ISSUE_REF` from the environment when the
hook event is emitted; once identity is present, `HookRecordStore` rejects a
different binding ([agents.py](../src/dashpot/agents.py)). That supports binding
at process launch and durable hint promotion, but it cannot represent one
already-running session starting work, switching Issues, or ending Issue work
without ending the underlying session.

## Open-Issue classifications

| Issue | Classification | Recommendation |
|---|---|---|
| [#2 Add cross-platform test and package CI](https://github.com/ned2/dashpot/issues/2) | **Valid unchanged** | Keep open and `ready-for-agent`. Main still has no GitHub Actions workflow, and the Python 3.11/package-build contract agrees with `pyproject.toml`. This work can proceed independently and should precede the first release. |
| [#3 Package the opt-in Codex lifecycle integration](https://github.com/ned2/dashpot/issues/3) | **Needs update; depends on new work tracking** | Retain it as the Codex-specific installation, hook-merge, lifecycle-observation, diagnosis, and uninstall Issue. Replace its global “works across observed repositories” publication assumption with machine-wide installation that routes each observation to the relevant checkout's `.dashpot/state/`. Remove launch-time environment binding as the primary user workflow and make it consume the new explicit work-tracking seam. Depend on both new foundation Issues. Do not broaden #3 to Claude Code. |
| [#4 Validate Dashpot on Apple Silicon macOS](https://github.com/ned2/dashpot/issues/4) | **Needs update; blocked by the storage/integration shape it is meant to validate** | Keep the real-host validation, BSD `ps`, packaging, and compact/wide TUI checks. Replace “macOS application-state directory” with Project-local config/state discovery, linked-worktree routing, ignore cleanliness, and Codex lifecycle/opt-in verification. Run it after the config migration, work-state feature, and updated #3; otherwise it validates a path already accepted for replacement. Claude validation may remain in its own integration Issue unless the release claims Claude support. |
| [#5 Prepare the first installable release](https://github.com/ned2/dashpot/issues/5) | **Needs update; release gate** | Keep open. Add an explicit dependency/gate list: #2, the chosen macOS result from #4, config migration, work-state compatibility/schema, and a decision on which harness integrations are supported in the first release. Ensure installation docs no longer publish `.dashpot.json` or the global hook-record directory as a stable interface. The Local Issue Markdown compatibility decision remains valid. |
| [#12 Show workspace status only when it is relevant](https://github.com/ned2/dashpot/issues/12) | **Needs update, not blocked** | The exceptional-only status/toast concept is still valid and now owns the failure visibility intentionally removed from the Issue table and Project pane. Rewrite the problem statement: Project Status no longer shows normal source/target state, and Diagnostics is the durable detailed surface. Define the alert over the current observation scope—normally one Project, optionally a composed Workspace—rather than motivating it mainly through unseen Projects/targets. Keep refresh, stale/unavailable, recovery, compact-terminal, and non-colour signaling cases. |
| [#17 Refresh and publish observations independently](https://github.com/ned2/dashpot/issues/17) | **Needs update; blocked by Project-local work tracking** | Keep the observation-kind decoupling because independently refreshing agent work without refetching Issues is useful even for one Project. Remove the already-satisfied “Depends on #16” wording, or record #16 as completed. Replace “Agent Runs once per Workspace” with aggregation of independently observed Project-local work state. Make multi-Project targeted refresh and unrelated-Project latency secondary acceptance cases, consistent with the evidence audit. Remove `ready-for-agent` until the body and dependency are updated. |

## Proposed new Issues

### A. Migrate Project configuration to `.dashpot/config.json`

**Goal:** implement the tracked configuration and discovery half of ADR 0003
without changing the Project/Issue identity model.

Suggested scope:

- load Project definition from `.dashpot/config.json` at a Repository Anchor;
- migrate Dashpot's own tracked file and all tests/examples/documentation;
- define explicit behavior for an old `.dashpot.json`—for an unreleased product,
  an actionable error or explicit migration command is preferable to indefinite
  implicit dual-format support;
- preserve current-directory precedence, explicit `--workspace`/`--config`
  precedence, anchor validation, clone grouping, and linked-worktree discovery;
- add `.dashpot/state/` to the repository ignore contract while keeping
  `.dashpot/config.json` tracked; and
- leave the optional global Workspace inventory as anchor composition only, not
  a Project configuration or work-state owner.

**Dependencies:** none. This should precede the work-state Issue, #3, #4, and #5.

**Existing owner:** none. Closed #13 made Project identity and anchors
first-class but explicitly excluded legacy Workspace migration
([#13](https://github.com/ned2/dashpot/issues/13)).

### B. Add Project-local work tracking and live-session Issue opt-in

**Goal:** make “this already-running agent is now working on this Issue” a
Dashpot-owned, harness-neutral operation stored under `.dashpot/state/`.

Suggested scope:

- distinguish an **Agent Session** (harness conversation/process) from a
  time-bounded **Agent Run** (that session working on one Issue), and record the
  vocabulary in the README domain language before encoding the schema;
- provide a versioned, atomic/concurrency-safe Project-local store and a narrow
  API such as `start_work(session, issue, location)`, `stop_work(session)`, and
  `active_work()`;
- let a command invoked from an existing supported session resolve the calling
  session and Project, bind by stable Issue Identity, start or switch work, and
  stop work without ending the session;
- store timestamps, harness/session identity, Issue Identity, observation
  location/worktree context, and binding provenance; diagnose missing Projects,
  Issues, worktrees, sessions, and conflicting concurrent updates;
- derive the Issue `SESSIONS` count and detail list from active Agent Runs while
  retaining harness lifecycle state (`running`, `waiting`, or unknown) as an
  observation about the owning session; and
- migrate or explicitly reject current global version-2 Codex records rather
  than silently combining authorities.

An optional durable “this worktree is intended for Issue X” relationship should
remain a separate follow-up until its user workflow is specified. A Worktree is
execution context and must not by itself increment `SESSIONS`; otherwise an
abandoned worktree looks like active agent work. ADR 0003 only settles where
local work state belongs, not that every possible worktree hint must be
persisted now.

**Dependencies:** proposed config migration A. #3 and #17 then depend on this
Issue, and the Claude Code integration consumes the same seam.

**Existing owner:** none. #15 established stable identity binding but expressly
excluded starting/stopping sessions and Issue claiming
([#15](https://github.com/ned2/dashpot/issues/15)); #17 expressly excludes
persistence ([#17](https://github.com/ned2/dashpot/issues/17)).

### C. Observe and package Claude Code integration

**Goal:** give Claude Code parity with Codex for lifecycle observation and the
same explicit existing-session work-on/work-off workflow.

Suggested scope:

- implement a Claude Code adapter against its supported hook/session surface;
- map supported lifecycle facts into Dashpot's harness-neutral Agent Session
  observation instead of cloning Codex record semantics;
- identify a live Claude session when it invokes the opt-in command;
- route records to the relevant Project-local state directory;
- make install, existing-hook merge, upgrade, diagnosis, and uninstall
  idempotent and opt-in; and
- prove normal exit, killed/orphaned session handling, Issue switching, linked
  worktree routing, and coexistence with Codex.

**Dependencies:** proposed config migration A and work tracking B. It should be
separate from #3 because Codex and Claude Code have different installation and
lifecycle adapter contracts, while sharing the same Dashpot-owned store.

No current open or closed Issue mentions Claude Code; current source, examples,
entry points, README, and #3 are Codex-specific
([agents.py](../src/dashpot/agents.py),
[hook.py](../src/dashpot/hook.py),
[examples/codex-hooks.json](../examples/codex-hooks.json),
[pyproject.toml](../pyproject.toml),
[#3](https://github.com/ned2/dashpot/issues/3)).

## Recommended dependency order

```text
#2 CI ---------------------------------------------------------> #5 release

A config migration
  -> B Project-local work tracking + existing-session opt-in
       -> #3 Codex packaging
       -> C Claude Code integration
       -> #17 independent observation scheduling

A + B + #3 -> #4 macOS validation ----------------------------> #5 release

#12 exceptional status/toast can proceed independently, but should consume
diagnostics from A/B/#17 as those sources arrive.
```

The first release does not necessarily need both Codex and Claude Code support,
but #5 must state the chosen supported surface rather than accidentally shipping
Codex-only implementation as a harness-neutral promise.

## Sources reviewed

- all six open GitHub Issues, including current bodies, labels, assignees, and
  comments, queried through GitHub on 2026-08-28;
- closed Issues #13, #15, and #16 for original scope boundaries and completion
  state;
- the README domain language, ADRs 0001 and 0003, and the multi-repository
  Workspace evidence audit;
- current Project configuration, CLI discovery, agent publisher/observer,
  binding, model, collector, and observation-store source;
- current README, example Codex hooks, package entry points, ignore rules, and
  relevant tests; and
- repository state at commit `768fc3d`.
