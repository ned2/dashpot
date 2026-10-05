---
status: accepted
date: 2026-09-02
---

# Fetch remotes on an explicit key press

Amended by [ADR 0036](0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md): Cleanup dialogs keep their concrete
primary subject fixed and permit explicit Remote Fetch while the preview is idle.
The fetch, observation, and re-inspection finish before confirmation is available.

Amended in place for [#539](https://github.com/ned2/dashpot/issues/539):
a named mutation's Git commands get a bound of their own, the Git timeout
raised to at least five minutes, and a command that outlasts its bound is
asked to stop with its whole process group before it is killed.

Amended in place for [#599](https://github.com/ned2/dashpot/issues/599):
`dashpot worktree create`'s `git worktree add` shares the bound but keeps
Dashpot's session and terminal, so a timeout stops `git` alone
([ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md#the-add-of-worktree-create-stays-interactive--2026-10-06)).

The Branches pane lists local Branches and Remote-Tracking Branches as of
the Repository's last fetch, and its border reports that fetch age
([ADR 0005](0005-observe-branches-without-fetching.md)). Bringing those
facts up to date meant leaving Dashpot and running `git fetch` by hand,
because observation — startup, polling, `r`, and `dashpot --json` — must
never mutate the Repository
([ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)).

Dashpot will let the `f` key on the main dashboard fetch and prune the
remotes of exactly one Repository: the Repository Anchor whose refs supplied
the current Branch observation. It is a named mutation under ADR 0008's
boundary, invoked by a person, and it mutates only what its name says:

- The Branch observation records the anchor that answered
  (`branchAnchor` in the headless JSON), so the fetch targets the clone the
  pane is showing and never every Repository Anchor of a Workspace that
  holds independent clones of one Project.
- The invocation is `git fetch --prune -- <remote>` once per configured
  remote, in `git remote` order
  ([`fetch.py`](../../src/dashpot/repository/fetch.py)). One call per remote attributes
  a failure to the remote that failed and lets the rest complete, so a
  partial failure is reported remote by remote and never as an unqualified
  success. No remote configured is a refusal, not a fetch.
- Each call runs under a named mutation's bound: Dashpot's Git timeout,
  raised to at least five minutes (`MUTATION_TIMEOUT` in
  [`git.py`](../../src/dashpot/core/git.py)). The Git timeout is sized for
  reads, and a large update over a slow link outlasts it; stopped there,
  every retry would restart the download and be stopped again. Cleanup's
  confirmed removal and `dashpot worktree create`'s `git worktree add`
  share the bound. A command that outlasts even that bound is first asked
  to stop and killed only after a two-second grace, and for a fetch or a
  Cleanup, each in a session of its own, the signals go to its whole
  process group, so Git removes its lock files and temporary
  packs, and no SSH transport or `index-pack` it started runs on orphaned.
  The price is a dashboard exit that waits for a stuck fetch up to the
  bound ([ADR 0049](0049-interrupt-observation-commands-at-dashboard-exit.md)).
- The fetch is non-interactive: `GIT_TERMINAL_PROMPT=0` disables Git's own
  credential prompt, and the command runs without stdin in its own session,
  so neither Git nor an SSH helper can open the controlling terminal and
  take over the screen; it fails or times out instead.
- The fetch runs off the Textual event loop, one at a time per Project. A
  second `f` while one is in flight is refused with a toast; the alert line
  says `fetching remotes <Project>` from the moment it starts.
- Nothing about the Repository is inferred from the fetch. After any remote
  is fetched, the Project's Git state is re-observed the passive way, so the
  pane, the Integration Branch facts, Remote-Tracking Branch presence, and
  the fetch age all come from observation. A fetch that reached no remote
  re-observes nothing and leaves the last good observation as it is; the
  failure is a toast and a Diagnostics line until a fetch there succeeds.

## Considered options

- **Fetching on refresh:** rejected again, for ADR 0005's reasons: a fetch
  mutates the Repository and touches the network, and a passive observer
  must do neither.
- **`git fetch --all --prune` as one command:** rejected because one exit
  code and one interleaved stderr cannot say which remote failed, so a
  partial failure would be presented as one failure or, worse, hidden by
  the remotes that succeeded.
- **Fetching every Repository Anchor of the Project:** rejected because
  Repository Anchors may be independent clones; mutating clones the pane is
  not showing is mutation the person did not ask for.
- **A management command (`dashpot fetch`) instead of a key:** not chosen
  because the request is made while looking at the pane and the outcome is
  read there; the key is the named invocation, and the boundary is the
  same. A command can follow if a caller outside the TUI needs it.

## Consequences

- `f` joins the dashboard bindings, the Footer, the Legend, and the README
  key table. Startup, polling, `r`, and `dashpot --json` continue never to
  run `git fetch`, and a `DashpotApp` built without a fetcher refuses `f`.
- `ProjectSnapshot` and the headless JSON gain `branchAnchor`; ADR 0005's
  "Dashpot never fetches" is read as "observation never fetches" from this
  decision on, and ADR 0008's list of named mutations gains the `f` key.
- `commands.run_command` gains a non-interactive mode, used only by the
  fetch.
- Whether Dashpot should also observe live remote Branches without
  mutating Git ([#66](https://github.com/ned2/dashpot/issues/66)) is a
  separate decision.
