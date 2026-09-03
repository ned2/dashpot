---
status: accepted
date: 2026-09-02
---

# Fetch remotes on an explicit key press

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
  remote, in `git remote` order, under Dashpot's Git timeout
  ([`fetch.py`](../../src/dashpot/fetch.py)). One call per remote attributes
  a failure to the remote that failed and lets the rest complete, so a
  partial failure is reported remote by remote and never as an unqualified
  success. No remote configured is a refusal, not a fetch.
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
