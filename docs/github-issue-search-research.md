# GitHub Issue search, filtering, and sorting semantics

Research date: 2026-08-28.

This note describes GitHub.com as it exists today and identifies a practical
compatibility target for Dashpot. GitHub has several related but distinct
surfaces—repository Issue lists, global search, REST search, GraphQL
connections, and GitHub CLI—and their defaults are not identical.

## Executive findings

1. **There is no single GitHub default sort.** A repository's Issues list
   resets its Sort menu to **Newest**, meaning creation time descending. The
   repository REST list endpoint likewise defaults to `sort=created` and
   `direction=desc`. By contrast, the REST Search endpoint uses best-match
   ranking when `sort` is omitted. GitHub.com's current natural-language Issue
   search uses relevance-ranked hybrid search by default, while filter-only or
   quoted searches remain lexical.
   [Issue-list sorting](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests#sorting-issues-and-pull-requests)
   [repository Issue REST parameters](https://docs.github.com/en/rest/issues/issues#list-repository-issues)
   [REST search ranking](https://docs.github.com/en/rest/search/search#ranking-search-results)
   [2026 improved Issue search](https://github.blog/changelog/2026-04-02-improved-search-for-github-issues-is-now-generally-available/)
2. **Explicit date sorting is straightforward.** `sort:created` and
   `sort:updated` mean descending order; adding `-asc` reverses them. For
   Dashpot, these map directly to the complete Issue profile's `createdAt` and
   `updatedAt` fields.
   [GitHub search sort syntax](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/sorting-search-results)
3. **GitHub's filter language is compositional.** Advanced Issue filters
   support `AND`, `OR`, implicit `AND`, and parentheses nested at most five
   levels. A hyphen negates a qualifier, while `NOT` excludes a string keyword.
   Repeated label qualifiers are AND; comma-separated label values are OR.
   [advanced filters](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests#building-advanced-filters-for-issues)
   [exclusion syntax](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax#exclude-results-that-match-a-qualifier)
   [label composition](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-label)
4. **Dashpot already owns enough normalized data for a useful first stage.** It
   can faithfully implement lexical matching over title/body and qualifiers for
   repository, state, close reason, label, assignee, author, type, milestone,
   created date, updated date, and closed date without changing the Issue
   profile. Comments, comment counts, reactions, interactions, lock state, and
   repository archive state are absent, so those search and sort features would
   require model and collector work.
5. **Default sort must be represented separately from explicit query sort.** A
   missing `sort:` term should resolve to a named Dashpot default rather than an
   empty tuple or incidental source order. Clearing an explicit sort should
   restore that default. This is especially important because Dashpot's current
   product default, `LAST ACTION` descending, intentionally differs from the
   GitHub repository list's `created` descending default.

## Implementation slice adopted from this research

The first compatibility slice keeps Dashpot's deliberate `LAST ACTION`
descending default while adding:

- implicit-AND lexical words and quoted lexical phrases;
- `sort:created`, `sort:created-asc`, and `sort:created-desc`;
- `sort:updated`, `sort:updated-asc`, and `sort:updated-desc`;
- restoration of `DEFAULT_SORT` when an explicit query sort is removed;
- sorting by `createdAt` while the `CREATED` column is hidden; and
- diagnostics for malformed or unsupported sort qualifiers.

The Boolean grammar and the modeled qualifiers described below remain staged
follow-up work rather than silently partial implementations.

## The default-sort distinction

### Repository Issue list

GitHub's Issue-list Sort menu offers newest/oldest created, most/least
commented, newest/oldest updated, and most reactions. The documentation says
that clearing a sort uses **Sort > Newest**, and its shareable-URL example
encodes oldest as `sort:created-asc`. Therefore the documented repository-list
default is most recently **created** first, not most recently updated first.
[Filtering and sorting Issue lists](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests#sorting-issues-and-pull-requests)

The repository REST list endpoint independently confirms `sort=created` and
`direction=desc` as its defaults. It supports only `created`, `updated`, and
`comments` as sort fields. Unlike GraphQL's repository `issues` connection, the
REST Issues endpoints may also return pull requests and require checking the
`pull_request` key.
[List repository issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues)

### Search results

The REST Search API has different semantics: unless a sort is supplied, it
ranks results by best match in descending order. Its Issue search endpoint
supports explicit sorts by comments, reactions (including individual reaction
types), interactions, created time, and updated time. `order` defaults to
`desc`, but is ignored when no explicit sort is supplied.
[REST search ranking](https://docs.github.com/en/rest/search/search#ranking-search-results)
[Search Issues and pull requests parameters](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests)

As of April 2026, the GitHub.com Issue UI goes further. A natural-language
query uses hybrid semantic and keyword matching and ranks by best match.
Filter-only queries and queries containing quotation marks use lexical search.
The REST API does **not** implicitly follow that web behavior: omitting
`search_type` still selects lexical search; callers must request `semantic` or
`hybrid`. Semantic and hybrid modes are relevance-ranked and cannot also use an
explicit sort.
[Improved Issue search GA](https://github.blog/changelog/2026-04-02-improved-search-for-github-issues-is-now-generally-available/)
[REST Issue search `search_type`](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests)
[`gh search issues` modes](https://cli.github.com/manual/gh_search_issues)

### Consequence for Dashpot

Dashpot's current `DEFAULT_SORT` is `last_action` descending, matching the
explicit product decision to show recently active Issues first. That is a good
work-queue default, but it should be called a Dashpot default rather than a
GitHub-parity default. If strict repository-list parity becomes the overriding
goal, the default must instead become `created` descending.

Regardless of which product default is chosen, the state transition should be:

```text
query has sort:...  -> use the explicit query sort
query has no sort   -> use DEFAULT_SORT
sort is cleared     -> restore DEFAULT_SORT
```

Do not use collector order as the third state. `GitHubIssuesSource` currently
collects GraphQL pages in explicit `CREATED_AT ASC` order for deterministic
snapshot acquisition; that is an ingestion decision, not a view default.

## Supported sorting idioms

For the Issue-search sorts most relevant to Dashpot:

| Query form | Direction | Meaning |
| --- | --- | --- |
| `sort:created` or `sort:created-desc` | descending | newest created first |
| `sort:created-asc` | ascending | oldest created first |
| `sort:updated` or `sort:updated-desc` | descending | most recently updated first |
| `sort:updated-asc` | ascending | least recently updated first |
| `sort:comments` or `sort:comments-desc` | descending | most comments first |
| `sort:comments-asc` | ascending | fewest comments first |
| `sort:interactions[-asc|-desc]` | default descending | comments plus reactions |
| `sort:reactions[-asc|-desc]` | default descending | total reactions |
| `sort:relevance` | descending | highest relevance first |

GitHub also supports sorting by individual reaction types. The full official
table contains the exact spellings, including `reactions-+1`, `reactions--1`,
`reactions-smile`, `reactions-tada`, `reactions-heart`,
`reactions-thinking_face`, `reactions-rocket`, and `reactions-eyes`.
[Sorting search results](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/sorting-search-results)

GitHub documents only one sort criterion in query examples; it does not
document multi-column Issue-search sorting or a tie-break rule. Dashpot should
therefore accept one GitHub-compatible `sort:` term and apply its own stable,
documented tie-breaker, such as project identity followed by Issue number. That
tie-breaker is a Dashpot determinism guarantee, not claimed GitHub behavior.

GitHub defines an Issue as updated for activities including creation,
reopening, editing, commenting, label changes, assignee changes, milestone
changes, and transfer. This makes `updatedAt` a better activity proxy than body
edit time, but not a literal timestamp for every possible timeline event.
[GitHub's updated-item definition](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/archiving-items-automatically#about-automatically-archiving-items)

## Query and filter semantics

### Composition and grouping

Advanced Issue filtering supports uppercase `AND` and `OR`; a space between
statements is implicit `AND`. Parentheses group expressions and may be nested
up to five levels. This is more expressive than Dashpot's current conjunction
of one state set and one substring.
[Boolean and nested filters](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests#building-advanced-filters-for-issues)

Repeated qualifiers can have qualifier-specific semantics. Labels are the most
important example:

```text
label:bug label:urgent       # both labels (AND)
label:bug,urgent             # either label (OR)
-label:wontfix               # excludes that label
```

[Label qualifier behavior](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-label)

GitHub's July 2025 advanced-search announcement calls out one compatibility
trap: multiple space-separated `repo:`, `org:`, and `user:` qualifiers are AND
under advanced search but were OR under the legacy search. Dashpot spans a
fixed local project set, so it should choose and document advanced semantics
rather than reproduce both modes.
[Advanced Issue search API announcement](https://github.blog/changelog/2025-07-17-duplicate-issues-create-from-anywhere-and-more/)

### Negation

A hyphen before a qualifier excludes matching records, for example
`-author:octocat` or `-label:bug`. `NOT` excludes string keywords and does not
work for numbers or dates. Missing-metadata qualifiers such as `no:assignee`
cannot themselves be negated with a hyphen in GitHub's documented syntax.
[Qualifier and keyword exclusion](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax#exclude-results-that-match-a-qualifier)
[Missing metadata](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-missing-metadata)

### Text matching

Traditional Issue search is case-insensitive. Without `in:`, GitHub searches
the title, body, and comments. `in:title`, `in:body`, and `in:comments` restrict
the fields, and comma-separated values combine fields, such as
`in:title,body`. Quotation marks are required around a value or phrase that
contains whitespace; current GitHub.com also treats quoted searches as a cue
for exact lexical rather than semantic matching.
[Issue text fields and case behavior](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-the-title-body-or-comments)
[Search whitespace syntax](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax#use-quotation-marks-for-queries-with-whitespace)
[Current semantic/lexical selection](https://github.blog/changelog/2026-04-02-improved-search-for-github-issues-is-now-generally-available/)

Dashpot stores title and body but not comments. A compatible first stage should
therefore default free-text matching to title plus body and either reject
`in:comments` as unsupported or report it explicitly; silently treating it as
title/body would be misleading. Dashpot's current search also includes project,
number, and assignees by default, which is useful fuzzy filtering but is not
GitHub's documented unqualified-text field set.

### State and close reason

`state:open`/`state:closed` and `is:open`/`is:closed` are aliases for open and
closed state. `is:issue` restricts a mixed search to Issues rather than pull
requests. GitHub documents `reason:completed` and `reason:"not planned"` for
closed Issues.
[State filtering](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-open-or-closed-state)
[Close-reason filtering](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-the-reason-an-issue-was-closed)

GitHub's current GraphQL schema also has a `DUPLICATE` closed-state reason, and
Dashpot already normalizes it as `duplicate`. The main Issue-search reference
does not currently document `reason:duplicate`, so supporting it locally would
be a sensible GitHub-shaped extension rather than a claim of documented query
parity.
[GraphQL `IssueClosedStateReason`](https://docs.github.com/en/graphql/reference/issues#issueclosedstatereason)

### Dates and quantities

`created:`, `updated:`, and `closed:` accept ISO 8601 dates, optional time and
UTC offset, comparison operators (`>`, `>=`, `<`, `<=`), and inclusive range
syntax such as `2026-01-01..2026-01-31`. The generic syntax also permits
open-ended ranges with `*`.
[Issue date qualifiers](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-when-an-issue-or-pull-request-was-created-or-last-updated)
[Comparison and range syntax](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax)

The same comparison/range language applies to `comments:`, `interactions:`,
and `reactions:`. GitHub defines interactions as comments plus reactions.
[Comments, interactions, and reactions](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-number-of-comments)

### Other Issue qualifiers

The first-party reference documents qualifiers including `repo:`, `org:`,
`user:`, `author:`, `assignee:`, `mentions:`, `team:`, `commenter:`,
`involves:`, `linked:pr`, `label:`, `milestone:`, `project:`, `type:`,
`field.<name>:`, `language:`, `archived:`, `is:locked`, and missing-metadata
forms such as `no:label`, `no:milestone`, `no:assignee`, and `no:project`.
[`Searching issues and pull requests`](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests)

`involves:USER` is specifically an OR over author, assignee, mentions, and
commenter for that user. `assignee:*` means any assignee, but GitHub documents
that wildcard only within a single repository. `@me` may be used wherever a
username qualifier is accepted; a local Dashpot implementation would need an
explicit current-user identity before it can reproduce that behavior.
[People qualifiers](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-a-user-thats-involved-in-an-issue-or-pull-request)

## Pagination, stability, and limits

The REST Search API returns at most 1,000 results for a search, with at most 100
per page and 30 by default. Queries may contain no more than 256 non-operator,
non-qualifier characters and no more than five `AND`, `OR`, or `NOT` operators.
Search is limited to 4,000 repositories. Long-running searches may return a
partial result set with `incomplete_results: true`.
[REST search limits](https://docs.github.com/en/rest/search/search#about-search)
[query and scope limits](https://docs.github.com/en/rest/search/search#limitations-on-query-length)
[timeouts and incomplete results](https://docs.github.com/en/rest/search/search#timeouts-and-incomplete-results)

GitHub cautions that an updated-time sort is unstable while paging: when an
item changes, it moves and shifts intervening items across page boundaries.
GitHub does not document an Issue-search tie-break order. Dashpot queries a
complete local snapshot rather than paging filtered results, avoiding the
server-side page-shift problem, but it should still define a deterministic
tie-break for repeatable rendering and tests.
[REST pagination stability guidance](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#if-you-use-pagination-make-sure-to-use-stable-ordering)

## Gap analysis against Dashpot

Dashpot's current query and view state are intentionally much smaller:

- `IssueListQuery` has a set of open/closed states, one case-folded substring,
  and selectable fields limited to project, number, assignees, and title.
- Unqualified text is one contiguous substring; there is no tokenization,
  phrase handling, Boolean AST, negation, or qualifier parser.
- `IssueTableViewState` owns visible columns and a tuple of sort terms. Current
  interactions produce a single sort term even though the representation is a
  tuple.
- `DEFAULT_SORT` is `last_action` descending.
- The Issue profile already includes title, body, state, state reason, labels,
  assignees, author, Issue type, milestone, creation/update/close timestamps,
  provenance, and location.

That leads to this staged compatibility plan:

1. **Define a query grammar and AST.** Preserve the raw input for editing, but
   parse words/phrases, qualifiers, comparison/ranges, negation, AND/OR, and
   grouped expressions into typed nodes. Do not keep expanding a single
   `text: str` field with ad hoc checks.
2. **Start with modeled, source-neutral facts.** Implement `state`/`is`,
   `reason`, `label`, `assignee`, `author`, `type`, `milestone`, `repo` (mapped
   to Dashpot Project), `created`, `updated`, `closed`, `no:assignee`,
   `no:label`, and `in:title,body`.
3. **Make sort resolution explicit.** Parse at most one GitHub-compatible
   `sort:` term. If absent, restore `DEFAULT_SORT`; never inherit whichever
   column happened to be sorted before a query was cleared. Keep manual table
   column sorting as a richer Dashpot feature, and decide whether it updates the
   query text as GitHub's shareable URLs do.
4. **Add a deterministic secondary key.** Project identity plus Issue number is
   available across sources and avoids display jitter for equal timestamps.
5. **Report unsupported qualifiers.** A small diagnostic is better than either
   silently ignoring a clause or turning `in:comments` into title/body search.
6. **Defer relevance emulation.** GitHub does not publish its best-match
   scoring factors, and current web hybrid search requires embeddings. A
   well-specified lexical subset is more reproducible. If Dashpot later adds
   relevance, model it as a distinct ordering mode, not a fake table column.
7. **Only extend the profile when the feature needs it.** Comment/reaction sorts
   and filters require counts; comment text search requires comment content;
   archive/lock qualifiers require those booleans. None is necessary for the
   first lexical/date/state implementation.

## Recommended acceptance examples

These examples capture the highest-value GitHub-shaped behavior while
preserving Dashpot's current default-sort decision:

```text
""                                      -> open Issues, DEFAULT_SORT
is:open                                 -> open Issues, DEFAULT_SORT
is:closed reason:completed              -> completed closed Issues, DEFAULT_SORT
is:closed reason:"not planned"          -> not-planned closed Issues, DEFAULT_SORT
label:bug label:urgent                  -> both labels, DEFAULT_SORT
label:bug,urgent -assignee:octocat      -> either label and not assigned to octocat
"clipboard failure" in:title,body       -> lexical phrase match in title or body
updated:>=2026-08-01 sort:updated-desc   -> recent activity, newest update first
created:2026-01-01..2026-06-30
  sort:created-asc                      -> first-half Issues, oldest creation first
```

The critical regression tests are that a query without `sort:` always resolves
to `DEFAULT_SORT`, an explicit query sort wins, and deleting the explicit sort
restores `DEFAULT_SORT`.
