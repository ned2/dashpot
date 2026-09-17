---
status: accepted
date: 2026-09-17
---

# Retain distinct query and collection adapters

[Issue #232](https://github.com/ned2/dashpot/issues/232) assesses the parallel
adapter families left after the [structural refactor](0042-group-leaf-and-domain-modules-into-subpackages.md).
Keep their existing composition and distinct retention policies. Shared parsing,
normalization, nested Profile completion, and complete-collection retention already
remove substantial duplication; merging the remaining contracts would require
callers or a configurable base to recover distinctions that the current interfaces
express directly. This decision changes documentation only.

## Call paths and ownership

| Consumer | Current path | Contract that must survive |
| --- | --- | --- |
| Dashboard and `issue list` / `pr list` | Composition or CLI builds a configured Query Source; `CachedQuerySource` calls provider page/totals/identity implementations. | A page is an atomic set of complete records for one request, not a complete inventory. Totals and identity observations have independent freshness. |
| Bound-Issue details and background resolution | Query Source `resolve_identities` deduplicates opaque identities and fetches attributable outcomes. | Missing/inaccessible, outside-Repository, and unavailable outcomes remain distinct; one failed identity need not invalidate siblings. |
| `issue show`, Issue work, and Worktree creation | `issue_resolution.resolve_issue` builds an Issue Source and calls `find` with a parsed Issue Hint. | Resolve exactly one fresh Issue by number/reference; a hint is not an opaque identity, and a failed lookup is not usable stale evidence for an Issue Binding. |
| Explicit `--json` Workspace Snapshot export | Non-recurring coordinator → configured `ProjectCollector` → Query Source `enumerate_source` → retaining collection source; collector shapes the result into snapshot source halves. | Complete collection coverage, original snapshot output, collection diagnostics, and last-good behavior; GitHub export uses repository connections rather than capped search results. |

The owners are [query contracts](../../src/dashpot/queries/source_queries.py),
[query retention](../../src/dashpot/queries/query_source.py),
[GitHub queries](../../src/dashpot/queries/github_queries.py),
[Markdown queries](../../src/dashpot/queries/markdown_queries.py),
[Issue resolution](../../src/dashpot/issues/issue_resolution.py), and
[collection orchestration](../../src/dashpot/observation/collect.py).
The recurring coordinator's `query_driven` scheduling selects Repository State
and Agent Runs; the UI page runner owns remote queries. Constructing collection
adapters does not itself enumerate sources. Markdown queries do read their local
documents to establish a deterministic revision; they do not invoke the explicit
export operation. These facts preserve [ADR 0033](0033-query-pages-and-independent-issue-resolution.md).

## Why the retention policies differ

`CachedQuerySource` retains up to 16 pages by verified context/request fingerprint
and cursor, totals by resource kind with a context check, and up to 256 fresh
identity observations with context checks on reuse. A different query cannot
inherit a previous query's rows. Invalid continuation is refused, while an
unavailable context observation does not prove a mismatch. Expected observation
failures become Diagnostics; programmer faults such as `AssertionError` escape.
Required page Profiles are atomic, while auxiliary observations and attributable
identity failures can degrade independently.

[RetainingSource](../../src/dashpot/issues/retaining_source.py) owns one complete
last-good collection and timestamp per source instance. It checks invariants before
publishing and preserves historical containment of unexpected adapter exceptions
as internal Diagnostics. [IssueSource](../../src/dashpot/issues/issue_sources.py)
and [PullRequestSource](../../src/dashpot/issues/pull_request_sources.py) supply
resource-specific validation and observation shapes. A generic cache shared with
queries would need policies for keys, context, eviction, partial outcomes,
exception containment, and severity; those choices would enlarge the interface.

## Concrete duplication and alternatives

| Candidate | Benefit | Cost and decision |
| --- | --- | --- |
| Merge query and collection adapters into one family | Fewer classes and potentially fewer constructed source objects. | Page/find/export semantics still differ. Search cannot enumerate beyond its provider limit; Issue Hint lookup cannot be replaced by opaque-identity lookup. Callers would need modes or a broader interface. Rejected. |
| Share a generic retention engine while retaining both public contracts | Centralize success/failure bookkeeping. | Most of the remaining bookkeeping expresses the different policies above. Complete Issue/Pull Request retention already shares `RetainingSource` from #183. Reject another policy-driven engine until an actual repeated contract appears. |
| Extract common Markdown file traversal | Centralize path containment, ordering, decoding, and duplicate checks. | Query context hashes paths and exact bytes from the same read used for Profiles; export preserves specific path/parse Diagnostics and complete-collection validation. Parsing is already shared through `parse_local_markdown_issue`. A reader would need to preserve both contracts; no extraction is justified by traversal similarity alone. |
| Remove the collector's enumeration round trip | Avoid converting source observations into `SourceEnumeration` and back. | The collector also assembles auxiliary label colors/activity and supplies fallback Diagnostic codes for snapshot output. Bypassing enumeration would give configured export a second route instead of the common Query Source contract. Keep the conversion at the snapshot consumer. |
| Keep current composition and existing shared implementation | Callers retain operation-specific interfaces and established failure behavior. | Accept the small amount of shape conversion, duplicated local traversal, and unused fallback source objects in configured collectors. Chosen. |

The GitHub Query Source already uses the collection adapter's nested Profile
completion methods and shared normalization functions; its enumeration method
calls the same collection `refresh` implementation as direct collection consumers.
Markdown shares its Profile parser and uses a retaining source for export.
`ProjectCollector` can also use directly injected collection sources when no Query
Source is set, which supports its existing standalone seam and fake-source tests.
The configured factory currently constructs these fallback sources before assigning
a Query Source that owns its own export sources. This is redundant object
construction, not evidence of duplicate full network enumeration; removing it is
not a prerequisite for retaining the two contracts. No measured construction or
latency problem was established by this assessment.

Revisit a smaller shared implementation if changes repeatedly require fixing the
same parsing/traversal bug in both paths, a new provider demonstrates a shared
contract, or measurements show material construction/export conversion cost.
Any future consolidation must preserve the cache and failure distinctions above;
reducing class or line counts alone is insufficient.

## Verification evidence

Existing public-seam tests make these differences observable:

- [Source query tests](../../tests/test_source_queries.py) assert that the same
  verified page can become stale but a new query cannot inherit it; principal,
  configuration, and Markdown revision changes invalidate continuation; identity
  siblings survive attributable failures; auxiliary failure does not invalidate
  complete Profiles; and unexpected query programmer faults escape.
- The same file's `test_export_over_search_limit_uses_repository_connections`
  exports 1,001 Issues in eleven connection requests and asserts that no advanced
  search query is used. Page tests separately assert bounded requested-page work.
- [GitHub Issue tests](../../tests/test_github_issues.py) assert whole-refresh
  rejection and last-good retention, shared nested-page budgets, and fresh
  number/reference lookup; [local Markdown tests](../../tests/test_local_markdown_issues.py)
  exercise path containment, malformed documents, and collection invariants.
- [Collector tests](../../tests/test_collectors.py) explicitly assert fallback
  Diagnostic codes for enumeration from both resource families, including keeping
  existing coded Diagnostics unchanged. [CLI query tests](../../tests/test_query_cli.py)
  exercise published page/totals output and cross-invocation continuation.

The repository's full review gate and independent review validate this assessment
against the unchanged implementation; test fakes perform no network observation.
No new tests, dependencies, or runtime abstractions are introduced.
