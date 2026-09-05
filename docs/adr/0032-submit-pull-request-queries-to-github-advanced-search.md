---
status: accepted
date: 2026-09-06
---

# Submit Pull Request queries to GitHub advanced search

The follow-up to [Issue 139](https://github.com/ned2/dashpot/issues/139) removes
the draft dropdown, requests GitHub's PR search operators generally, and uses
the Issues state character with GitHub's PR colours. Reproducing the operators
locally would require comment text, team membership, review history, metadata,
and GitHub's own indexing semantics beyond the compact observed profile.

Submit non-empty Pull Request queries to GraphQL `ISSUE_ADVANCED` on Enter,
scoped to the configured Repository Identity after resolving its current name.
Pass the expression through so GitHub owns qualifier and Boolean semantics,
including sorting. Check grouping before wrapping the expression in the Project
scope. Read every page under a Refresh Budget and reject totals above GitHub's
1,000-result limit, changing totals, duplicate identities or numbers, foreign
Repository results, and incomplete collections. These choices follow the
[primary-source research](../github-pull-request-search-research.md).

Keep search results and their freshness separate from background observations.
Run only one search at a time; coalesce submissions to the latest query and
never display a superseded completion. A failed repeat of the same query keeps
its last-good results as stale; a different query reports unavailability on
failure. Submission and manual refresh trigger the search; ordinary typing and
periodic background observation do not. Submitting an empty query restores the
background list. This preserves the headless contract and independent Issue
Source freshness while introducing a different interaction from Issues' local
search as the person types.

The Open / Closed / All selector remains local to the returned search
collection, and both lifecycle counters reflect the submitted expression before
that selector. Thus an explicit `is:closed` in the expression can produce an
Open count of zero; select All to let the expression own lifecycle selection.
The count beside search is the number of displayed matches. This deliberately
amends [ADR 0031](0031-observe-complete-pull-request-lifecycle-history.md)'s
local-only search and separate draft selector; complete background history is
unchanged.

Both Issue and Pull Request states use `■`. Pull Request foreground colours
follow Primer's open, draft, closed, and done tokens for the default light and
dark themes: green, grey, red, and purple. Retain the state labels, including
closed drafts, so the facts remain readable without distinguishing colours.
The Legend includes each coloured state block through the same Glyph values.
