---
status: amended
date: 2026-09-11
amended-by: 0055-verify-the-query-context-in-the-response-that-carries-it.md, 0057-observe-project-totals-in-the-query-page-request.md
---

# Query pages and independent Issue resolution

Amended by [ADR 0055](0055-verify-the-query-context-in-the-response-that-carries-it.md):
the Repository and principal context is observed before sending only for a
continuation; every other GitHub request carries it and is verified in its
response.

Amended by [ADR 0057](0057-observe-project-totals-in-the-query-page-request.md):
Project Totals are counted by the Query Page request rather than a count
request of their own.

## Context

Issue 140 replaces complete dashboard inventories with source queries. A complete
Issue Profile is a record contract; it does not imply complete collection coverage.
Bindings and details need particular identities, independently of query membership.

## Decision

The configured Issue Source exposes Query Pages, Project Totals, Resolved Issues
and explicit Source Enumeration. The dashboard and CLI share these operations.
A Query Page publishes complete records atomically, its effective request,
continuation outcome, matching count and observation times. Project Totals and
auxiliary engagement and label colours have independent availability. None of
these observations change the complete Workspace Snapshot export wire contract.

Portable continuation binds to non-secret Project, Repository, source location,
principal, request and ordering evidence. Markdown additionally binds to a digest
of paths and contents. An observation failure cannot prove context mismatch.
GitHub's search limit is coverage information, not failure of the first page.

The Work Store remains authoritative. Resolved Issues distinguish membership,
outside-Repository evidence, missing-or-inaccessible, and unavailable observations.
A Query Page's absence never invalidates an Issue Binding.

The dashboard retains bounded navigation history and identity observations. User
changes supersede requests; timer refreshes coalesce. Pages, totals, identities and
local state publish independently. Only explicit export enumerates whole sources.

## Consequences

Source ordering precedes pagination. GitHub header sorts map only exact fields
(created, updated and comments); explicit query sorting takes precedence. Remote
advanced syntax remains the provider's responsibility. Markdown retains local
text matching and column ordering.

GitHub's Linked Pull Request connection cannot order by number: its documented
arguments allow ordering by state only. Preserving the lowest-numbered twenty
therefore requires deliberate auxiliary connection completion when more than
twenty exist, under a separate budget; this is display work, never incremental
bookkeeping. A failed auxiliary read must not invalidate complete Issue Profiles.
See [GitHub's Issue reference](https://docs.github.com/en/graphql/reference/issues).

Historical inventory scheduling and Snapshot Seeds are retired from ordinary
operation. `reconciliationSeconds` stays readable as a deprecated, unused setting.

For a 50-Issue page with no additional nested pages, the source performs four
requests: one search page and three batches of complete Issue nodes (24, 24, 2),
each carrying the Repository/principal context. A continuation, and the first
page a source asks for, observe the context in one request more. Required nested
Profile pages spend the same Refresh Budget. Auxiliary Linked Pull Request
completion spends one separate budget shared by the page, after required Profiles
complete. Project Totals are counted in the Query Page request itself
([ADR 0057](0057-observe-project-totals-in-the-query-page-request.md)). Targeted
lookups deduplicate identities and batch by 24; they never recursively enumerate
relationship targets.

GraphQL identity errors are attributed by their `nodes` response positions.
Required-field errors make only that identity unavailable, including errors on
nullable Profile fields; auxiliary-field errors degrade auxiliary facts alone.
Errors that cannot be safely attributed make the affected batch unavailable.
