---
status: accepted
date: 2026-10-05
---

# Share the Local Issue reader and contain Linked Pull Request completion

The 2026-10-05 review found the Issue Sources inconsistent in two ways
that the Query Sources built over them expose
([#550](https://github.com/ned2/dashpot/issues/550)).

**Two Local Markdown readers.**
[ADR 0043](0043-retain-distinct-query-and-collection-adapters.md) kept two
traversals of the Local Issue documents. The Markdown Query Source read them
itself, to hash a revision for its pages, and the Issue Source read them
again for export and resolution. ADR 0043 found no extraction justified by
similarity alone, and said to revisit that if both paths kept needing the
same fix. They had since diverged:

- A page refused a collection with a bare `ValueError`. Its Diagnostic
  carried the generic `source-query-unavailable` code, where export carried
  `markdown-path`, `markdown-not-found`, `markdown-permission`,
  `markdown-malformed` or `markdown-profile`.
- The page's duplicate check named neither document. Export's named both
  locations.
- The two paths decoded a document in different ways.

Every rule a Local Issue collection follows had to be made, and tested,
twice: containment, POSIX path order, decoding, the codes and the
collection invariants.

**Presentation failing a collection.** Linked Pull Requests are display
facts. [ADR 0033](0033-query-pages-and-independent-issue-resolution.md)
says a failed auxiliary read must not invalidate complete Issue Profiles.
Yet the GitHub Issue Source completed an Issue's Linked Pull Requests
beyond the first twenty inside its required observation. A timeout, an
exhausted Refresh Budget or a null node on that display page therefore
failed the whole collection that an export reads. It also failed the
Issue Hint resolution behind `issue show` and `work start`, which keeps the
Issue alone and threw the completed connection away.

## Decision

**One Local Issue reader.** `read_local_issue_documents` in
[`local_markdown_issues.py`](../../src/dashpot/issues/local_markdown_issues.py)
reads every document a configured path names. It yields each document's
repository-relative path, its exact bytes and its parsed Issue. A refusal is
an `IssueSourceRefreshError` carrying its `markdown-*` code.

- `LocalMarkdownIssuesSource` collects through it.
- Its `read_documents` adds the collection invariants a refresh checks.
- The Markdown Query Source's `request_context` calls `read_documents`. It
  only adds the revision digest over the paths and bytes it is handed.
- A document is read as bytes and decoded as UTF-8 once. The parser splits
  lines itself, so CR and CRLF documents parse alike on both paths.

**Linked Pull Request completion is contained per Issue.** The GitHub Issue
Source observes every Issue's required profile first. Only then does it
complete each Issue's Linked Pull Requests, on the collection's own Refresh
Budget meter.

- A completion that fails degrades only its Issue. That Issue's comment
  count stays, no Linked Pull Request is listed, and every one is counted
  as unlisted. The first page cannot say which are the declared
  lowest-numbered twenty.
- One `github-linked-pull-requests` warning names the first degraded Issue
  and its failure, and the collection stays fresh.
- `find` no longer completes Linked Pull Requests at all.

## Consequences

- Amends [ADR 0043](0043-retain-distinct-query-and-collection-adapters.md):
  its "Extract common Markdown file traversal" alternative is taken. Pages
  and export keep their own contracts: the page path hashes the bytes it
  parsed, and export keeps its last-good retention. They share the reader.
- A refused Local Issue collection reports the same Diagnostic code and
  message on a Query Page as in an export. A test drives both paths over
  each refusal.
- `find` still reads a slug's conventional document directly, decoding it
  as the reader does. Its fallback to a full scan goes through the reader.
- The revision digest is unchanged. It covers the same paths and bytes in
  the same order, so a continuation issued before this change stays valid.
- Amends [ADR 0033](0033-query-pages-and-independent-issue-resolution.md)
  for the complete collection. There, Linked Pull Request completion
  shares the collection's Refresh Budget rather than a separate one. It
  runs after the last required page, so it can no longer spend a budget the
  required pages need, and an exhausted budget only degrades the Issues
  still waiting for it. Query Pages keep their separate auxiliary budget.
- The same failure still reads differently on the two paths. On a Query
  Page, the Issue's whole auxiliary observation is `unavailable`. In an
  export, the Issue's activity is degraded and stays `fresh`, beside the
  source's warning. Both keep the Issue Profile, which is what ADR 0033
  requires.
- Resolving an Issue Hint costs no Linked Pull Request pages, and it no
  longer fails on one.
