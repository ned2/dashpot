---
status: research
date: 2026-09-06
---

# GitHub Pull Request search and state colours

## Decision evidence

Full GitHub search compatibility requires executing queries against GitHub.
The current Dashpot `PullRequest` model has lifecycle, draft, Branch, author,
review-decision, check-status, mergeability, and creation/update facts; it lacks
body/comments, labels, assignees, reviewer identities, teams, reactions,
milestones, Projects, and close/merge dates. Local matching can offer a declared
subset, but cannot reproduce all operators or GitHub's relevance ordering.
This is an implementation inference from [the model](../src/dashpot/model.py)
and the operator inventory below.

## Operator inventory

The following inventory covers the documented Pull Request qualifiers:

| Family | Qualifiers / values |
| --- | --- |
| Kind | `is:pr`, `type:pr` |
| Scope | `repo:`, `org:`, `user:`, `language:`, `is:public/private`, `archived:true/false` |
| Lifecycle | `is:open/closed/merged/unmerged`, `state:open/closed` |
| Draft / availability | `draft:true/false`, `is:queued`, `is:archived` |
| Text | unqualified text, `in:title/body/comments` or comma combinations, commit SHA (7+ characters) |
| People | `author:`, `assignee:`, `mentions:`, `team:`, `commenter:`, `involves:` |
| Metadata | `label:`, `milestone:`, `project:OWNER/NUMBER`, `linked:issue` |
| Reviews | `review:none/required/approved/changes_requested`, `reviewed-by:`, `review-requested:`, `review-involves:`, `user-review-requested:`, `team-review-requested:`, `team-review-requested-user:` |
| Branches / status | `head:`, `base:`, `status:pending/success/failure` |
| Dates | `created:`, `updated:`, `closed:`, `merged:` |
| Counts | `comments:`, `interactions:`, `reactions:` |
| Conversation / missing metadata | `is:locked/unlocked`, `no:label/milestone/assignee/project` |

`is:unmerged` includes open and closed-unmerged Pull Requests. `is:archived`
describes an archived Pull Request; `archived:` describes its repository.
Repeated `label:` clauses require all labels; comma-separated labels allow
either. Unqualified text searches title, body, and comments. Negative `no:`
qualifiers are unsupported. `involves:` combines author, assignee, mention,
and commenter relationships. [GitHub qualifier reference](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests)

GitHub's filtering guide additionally documents `is:draft`. Its `reason:`,
Issue-type, `field.*:`, and `has:` examples explicitly concern Issues; do not
advertise them as documented Pull Request filters. Status `pending` includes
having no statuses, while `failure` includes errors. [Filtering guide](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests)

The CLI also exposes `is:internal` through its visibility option and explicitly
documents advanced search for Pull Requests on supporting GitHub hosts.
[GitHub CLI Pull Request search](https://cli.github.com/manual/gh_search_prs)

Numbers/dates support `>`, `>=`, `<`, `<=`, inclusive `a..b`, `a..*`, and
`*..b`; dates accept ISO 8601 timestamps and offsets. Quotes preserve spaces.
Hyphen prefixes negate qualifiers; `NOT` excludes string keywords. Username
qualifiers support `@me` and `@copilot`, requiring the authenticated viewer's
context. [General search syntax](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax)

`sort:` supports `created`, `updated`, `comments`, `interactions`, `reactions`,
and `relevance`; numeric/date sorts accept `-asc`/`-desc`. Reaction-specific
sorts are `reactions-+1`, `reactions--1`, `reactions-smile`, `reactions-tada`,
`reactions-heart`, `reactions-thinking_face`, `reactions-rocket`, and
`reactions-eyes`, with direction suffixes. The documentation groups unsuffixed
reaction-specific sorts with ascending forms, unlike aggregate `reactions`;
delegate this distinction to GitHub. `author-date` and `committer-date` concern
commit search. [Sorting reference](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/sorting-search-results)

Author matching is richer than comparing the published author login: GitHub
now includes Pull Requests Copilot opened on a person's behalf in that
person's `author:` results. The announcement dated June 18 schedules API
support for July 16, 2026. [GitHub author-search change](https://github.blog/changelog/2026-06-18-copilot-authored-pull-requests-now-included-in-author-searches/)

## Boolean grammar and API choice

Advanced filters support `AND`, `OR`, implicit `AND`, and parentheses nested
five levels. [Advanced-filter grammar](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests#building-advanced-filters-for-issues)
Repeated scope qualifiers changed from legacy OR to advanced AND; preserve
explicit grouping when constraining a query to the configured repository.
[Advanced API migration announcement](https://github.blog/changelog/2025-07-17-duplicate-issues-create-from-anywhere-and-more/)

A read-only GraphQL probe against `cli/cli` on September 6 established that
`ISSUE_ADVANCED` supports grouped Pull Request queries while `ISSUE` does not
interpret this example equivalently:

```graphql
query {
  basic: search(query: "repo:cli/cli is:pr (is:open OR is:closed)",
                type: ISSUE, first: 1) { issueCount nodes { __typename } }
  advanced: search(query: "repo:cli/cli is:pr (is:open OR is:closed)",
                   type: ISSUE_ADVANCED, first: 1) {
    issueCount nodes { __typename }
  }
}
```

Observed results: `basic` returned zero; `advanced` returned 4,564 and a
`PullRequest` node. Further `ISSUE_ADVANCED` probes returned 64 open and 4,500
closed; `is:open is:closed` returned zero. Repeated different `repo:` clauses
returned zero. `draft:true` and `is:draft` each returned 189. Counts are
time-specific observations, not test fixtures or guarantees.

GraphQL search permits at most 1,000 returned nodes despite a larger
`issueCount`. Its schema exposes `ISSUE_ADVANCED`, and semantic-search
fallback reasons explicitly identify Pull Requests as non-Issue targets.
Use lexical advanced search for this pane. [GraphQL Search reference](https://docs.github.com/en/graphql/reference/search)

REST `/search/issues` documents web qualifier parity and
`advanced_search=true`. It returns up to 100 records per page, at most 1,000
overall, with an `incomplete_results` signal. Authenticated lexical search
has a 30-request/minute limit. Documented validation limits include 256
non-qualifier/non-operator characters and five Boolean operators. Its explicit
`sort` parameter omits `reactions-rocket` and `reactions-eyes`, though the
web's `sort:` reference includes them: preserving raw query syntax avoids
prematurely narrowing the accepted grammar. [REST Search reference](https://docs.github.com/en/rest/search/search)

For Dashpot, inferred integration requirements are: keep search results
separate from the full Pull Request observation; validate repository and node
kind; refuse partial publication when pagination/counts disagree or exceed
1,000; retain a useful diagnostic for rate limits and invalid queries; cancel
or discard superseded searches. Scope the entire user expression, for example
`repo:OWNER/REPO is:pr AND (<user expression>)`, rather than appending a scope
after an ungrouped OR. This follows the [complete-observation policy](adr/0002-require-complete-issue-profile-snapshots.md)
and [Refresh Budget policy](adr/0021-bound-each-github-refresh-by-a-budget.md).

## State foreground colours

Primer's default light/dark foreground tokens resolve as follows, inspected at
commit `93e536c26d7984f6d2368c0b102f111f079cfe0b`:

| Pull Request presentation | Token | Light | Dark |
| --- | --- | --- | --- |
| Open, ready for review | `fgColor.open` | `#1a7f37` | `#3fb950` |
| Open draft | `fgColor.draft` | `#59636e` | `#9198a1` |
| Closed without merging | `fgColor.closed` | `#d1242f` | `#f85149` |
| Merged | `fgColor.done` | `#8250df` | `#ab7df8` |

The semantic mappings and overrides come from [Primer foreground tokens](https://github.com/primer/primitives/blob/93e536c26d7984f6d2368c0b102f111f079cfe0b/src/tokens/functional/color/fgColor.json5),
resolved through its [light palette](https://github.com/primer/primitives/blob/93e536c26d7984f6d2368c0b102f111f079cfe0b/src/tokens/base/color/light/light.json5)
and [dark palette](https://github.com/primer/primitives/blob/93e536c26d7984f6d2368c0b102f111f079cfe0b/src/tokens/base/color/dark/dark.json5).
These are foreground colours, not badge backgrounds; other GitHub themes have
additional overrides. Reusing Dashpot's existing Issue Glyph character with
these colours is a product choice, while the colour mapping follows Primer.
