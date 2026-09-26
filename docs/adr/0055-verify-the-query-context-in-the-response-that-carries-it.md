---
status: accepted
date: 2026-09-26
---

# Verify the query context in the response that carries it

[ADR 0033](0033-query-pages-and-independent-issue-resolution.md) binds a
Query Page continuation to the Repository and principal it was issued under,
so a `gh auth switch`, a Repository rename or transfer, or an edited
`.dashpot/config.json` cannot make page 2 continue page 1 under a different
identity. The GitHub Query Source met that by observing the context in a
request of its own, `DashpotQueryContext`, before every Query Page, every
Project Totals request and every Resolved Issues lookup. On 2026-09-26 that
was 6 of the 14 requests a dashboard sent on each refresh, 43% of its GraphQL
spend ([#303](https://github.com/ned2/dashpot/issues/303),
[#308](https://github.com/ned2/dashpot/issues/308)).

Only a request that uses a continuation has to know the context before it is
sent. Every other request can select the Repository node and `viewer` beside
its own data at no extra cost, and be verified in its response.

## Decision

- Every GitHub query selects `repository: node(id: $repositoryId) { id
  nameWithOwner }` and `viewer { id }`. A response for another Repository is
  refused, as the separate observation refused it.
- A request without a continuation (page one of a Query Page, Project Totals,
  a Resolved Issues batch) is sent under the last context a response reported
  and takes its principal from its own response. The observation it publishes
  carries that verified context.
- A continuation still observes the context first, and its continuation is
  still verified before the cursor is used. Its response must then answer for
  the same principal, or it is discarded.
- The Issue batches that complete a Query Page must answer for the principal
  its search answered for, and the batches of one Resolved Issues lookup for
  the principal the first of them answered for. A page is never assembled
  from answers for two principals.
- The search names the Repository (`repo:<owner>/<name>`), and the name is
  not in the Project configuration. The first Query Page a source asks for
  therefore observes the context separately, once, to learn it. Each response
  then reports the current name; when it reports a new name for the same
  Repository, page one is searched again once under the new name. A
  continuation searches under the name its own context observation reported;
  only a rename between that observation and its search restarts it from
  page one.
- The Project configuration is re-read before every request, locally, so a
  Query Page under an edited configuration is still refused before anything
  is sent.
- A failed request proves nothing about the context: the last good page,
  Project Totals or Resolved Issue is found under the last context a response
  reported, with the configuration the request was sent under, and shown as
  stale. When a response reported a new principal before a later part of the
  same request failed, or was refused for answering for one, that is the new
  principal, so the previous principal's observation is not shown. A
  continuation whose own context observation fails is looked up under the
  configuration it was about to be sent under.

## Consequences

A dashboard's steady refresh sends no `DashpotQueryContext` request; only a
source's first Query Page and each continuation do. A principal or Repository
change is still detected by the next request that reaches GitHub.

Two failures now keep a last good observation where the separate context
request made them unavailable, because neither reports a context that
replaces the one it was made under: a Project configuration that cannot be
read, and a response for another Repository, which is discarded with its
mismatch Diagnostic while the last good observation is shown as stale.

A local Markdown Issue Source is unchanged: its context is local, so it is
observed before every request as before.

## Considered options

- **Share one context observation per refresh across the five Query
  Sources.** It saves four of the five or six requests, but needs shared,
  locked state across the executor threads and an ordering between them each
  refresh.
- **Observe the context once for the life of a source, again only on a manual
  refresh.** A principal or Repository change would go unnoticed until `r` or
  a restart, which is later than ADR 0033's next refresh.
