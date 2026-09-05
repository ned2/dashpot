---
status: accepted
date: 2026-09-06
---

# Observe complete Pull Request lifecycle history

[Issue 139](https://github.com/ned2/dashpot/issues/139) requires Open / Closed
summaries and lifecycle navigation, including merged Pull Requests in Closed.
Observe the complete repository-wide Pull Request history under the existing
independent Refresh Budget and last-good boundary. The published `state` admits
`open`, `closed` (without merging), and `merged`; `isDraft` remains independent.
Headless JSON carries this full collection using its existing keys. Consumers
that assumed every entry was open must now filter by state.

Walk GitHub's connection in creation order so ordinary updates and lifecycle
changes cannot reorder pages. Request all three states and `totalCount`, reject
a changing total or a final collection whose size does not match, and preserve
the existing duplicate, cursor, request, and time guards. Publish one complete
collection or retain the whole last-good collection on failure. Display sorting
remains newest update first. GitHub pagination is not a transactional snapshot;
these checks detect incomplete collections but do not promise all fields were
read at the same instant.

The pane defaults to Open. Open includes drafts; Closed includes merged and
unmerged closures, still distinguished on rows. A separate draft selector and
`draft:true` / `draft:false` search narrow both lifecycle counters. Compute
Open / Closed counts after search and draft filtering but before the lifecycle
selector and open/closed search predicates; the count beside search reflects
every filter. Merged/unmerged predicates remain search filters. This follows
[GitHub's search vocabulary](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests)
and the filtered summaries documented in the Issue. The Issues pane retains its
existing fixed inventory behavior.

Complete history costs more requests than the former open-only collection.
A large history can exceed the budget and remain unavailable until a complete
refresh succeeds, or stale after an earlier success. We accept this explicit
limitation rather than present a truncated historical total as complete. A
separate server-side count would not answer arbitrary local search filters;
a historical persistence/incremental protocol would require its own validation
and recovery design. Filtering never triggers a network request.

This amends [ADR 0025](0025-observe-linked-pull-requests-from-pull-request-changes.md)
only in the scope of the independent Pull Request collection. It still supplies
no Issue relationship evidence and cannot affect Issue Source freshness.
