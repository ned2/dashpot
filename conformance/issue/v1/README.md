# Issue profile conformance, version 1

Version 1 defines the complete, source-neutral Issue snapshot that every
Dashpot Issue Source must produce. The JSON Schema describes its shape;
`dashpot.issue_profile` owns validation, collection canonicalization, and
semantic equivalence.

The profile version changes when a source would need to emit different fields,
values, availability semantics, or equivalence behavior. Adding a new source
does not create a new profile version if it can satisfy this contract without
loss.

## Complete snapshots

Every field is required in a fresh Issue snapshot. `null` and an empty array
mean that the source positively reports no value. They never mean unsupported,
not fetched, permission denied, or malformed.

If an adapter cannot establish a required field, it must not silently substitute
`null` or an empty array. The Issue Source observation is stale when last-good
Issues exist, otherwise unavailable, and carries a diagnostic that distinguishes
at least unsupported, not fetched, permission denied, and malformed data. One
bad record fails the collection refresh so an omitted Issue cannot masquerade as
source deletion.

## Canonical fields

| Field | Rule |
|---|---|
| `profileVersion` | Integer `1`. |
| `id` | Required opaque Issue Identity. Never derived from text or location. |
| `projectId` | Required opaque identity of the declaring Project. |
| `reference` | Required mutable human-readable Issue Reference. |
| `title` | Required non-empty text. |
| `body` | Required text; the empty string is valid. |
| `state` | `open` or `closed`. |
| `stateReason` | `completed`, `duplicate`, `not-planned`, `reopened`, or `null`. |
| `labels` | Unique, case-preserving strings with set semantics. |
| `assignees` | Unique source actor names with set semantics; assignment is not a claim. |
| `author` | Source actor name or `null` when positively absent. |
| `relationships.parent` | Parent Issue Identity or `null`. |
| `relationships.subIssues` | Unique Issue Identities with set semantics. |
| `relationships.blockedBy` | Unique blocking Issue Identities with set semantics. |
| `relationships.blocking` | Unique blocked Issue Identities with set semantics. |
| `issueType` | Source issue-type name or `null`. |
| `milestone` | Source milestone title or `null`. |
| `createdAt`, `updatedAt`, `closedAt` | RFC 3339 UTC timestamp ending in `Z`, or `null` when positively absent. |
| `origin` | GitHub or Markdown provenance, as defined by the schema. |
| `location` | Actionable GitHub URL or repository-relative Markdown path and one-based line. |

Labels, assignees, and relationship collections are canonicalized by ascending
Unicode code-point order. Their input order is not Issue semantics. Duplicate
values are invalid rather than silently discarded. A future need for ranked
sub-Issues requires a later profile version.

An open Issue has `closedAt: null` and may have `stateReason: reopened`; a closed
Issue may have `stateReason: completed`, `duplicate`, `not-planned`, or `null`.

## Semantic equivalence

Two records are semantically equivalent when their canonical profiles are equal
after removing `origin` and `location`. Every other field, including identity,
Project membership, reference, lifecycle timestamps, and profile version,
participates in equality.

Consequently, moving a Local Issue changes only `location` and does not change
`updatedAt`. A GitHub repository rename changes the Issue Reference and is an
observable semantic change even though Issue Identity is preserved. A GitHub
Issue transfer also changes Project membership and is not equality with its
earlier snapshot.

## Source rules

A GitHub origin contains the durable repository identity and native Issue
number. Its location is the current HTTPS Issue URL. A Markdown origin contains
the local schema version. Its location is resolved relative to the configured
Repository Anchor; absolute checkout paths never enter the Issue profile.
The owned file grammar, discovery rules, and failure behavior are defined by
the [Local Issue Markdown schema](local-markdown.md).

Changing the active Issue Source is a migration, not a refresh toggle. Migration
must validate a complete replacement collection, preserve explicit identities,
establish references and provenance for the destination source, then replace the
source atomically. Version 1 does not define Issue mutation operations.

## Fixtures

- `fixtures/github.json` is the expected canonical output of the GitHub adapter.
- `fixtures/markdown.json` is the expected canonical output of the Markdown
  adapter for the same Issue.
- `fixtures/semantic.json` is their shared semantic projection.

The raw Local Markdown input fixture lives at
[`tests/fixtures/local-markdown-v1/ISSUES.md`](../../../tests/fixtures/local-markdown-v1/ISSUES.md).

Adapters conform when they produce these outputs from their corresponding raw
source fixtures. Raw transport and Markdown parsing fixtures belong to the
adapter slices; this profile does not make transport formats part of the shared
seam.
