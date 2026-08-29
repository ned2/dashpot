---
status: accepted
---

# Observe Branches without fetching

Dashpot lists a Project's Branches as a pane of the main screen next to its
Sessions and Worktrees: which branches exist, where each one exists, how the
local ref relates to its upstream, and where work is happening on it. A
Repository holds two kinds of branch ref — local branches under `refs/heads/`
and Remote-Tracking Branches under `refs/remotes/<remote>/` — and a view that
listed them as two panes, or as two rows per name, would double the interface
for one concept.

Dashpot is a passive view. It reads `git for-each-ref` over both namespaces
and never runs `git fetch`, so what it shows about a remote is the
Repository's own copy as of the last fetch. Instead of hiding that, the pane
title carries the age of `FETCH_HEAD` (`remote as of 3h ago`, or `never
fetched`) as the freshness of everything remote on the screen.

## Considered options

- **A boolean `remote` flag on one Branch record:** rejected because a
  Repository may have several remotes, and `origin/main` and `upstream/main`
  are different refs. The record carries `remote: str | None` and the full
  refname as identity; the boolean is what the read model derives.
- **Separate Local Branch and Remote Branch records or panes:** rejected
  because the interesting facts — pushed or not, ahead or behind, upstream
  gone — are relations between the two kinds of ref, which a join makes
  visible and a split hides. The read model yields one row per branch name
  with a `WHERE` column; the observer keeps every ref distinct.
- **Fetching on refresh to keep remote state current:** rejected because a
  fetch mutates the Repository and touches the network on every refresh, and
  a passive observer must do neither. Reporting the age of the last fetch is
  the honest alternative.
- **Querying GitHub for remote branches:** rejected because it would make the
  Branches pane depend on the Issue Source and on the network, and would show
  a remote the Repository has not fetched, which is not the developer's view.

## Consequences

- `Branch` joins the observed model beside `ObservationTarget`; both travel in
  the `targets` half of an observation and are stale together when a topology
  refresh fails.
- Branches are read from the first Repository Anchor that answers; anchors
  are one Repository ([ADR 0004](0004-observe-one-project-per-run.md)), so any
  answer is the whole answer.
- The headless JSON snapshot gains `branches` and `fetchedAt`.
- Pull-request linkage per branch and Issue Hints derived from branch names
  are separate decisions; the pane shows what Git reports.
