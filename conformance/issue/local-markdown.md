# Local Issue Markdown

The Local Markdown Issue Source represents one Issue per UTF-8 Markdown file.
Its configured path is relative to the Project's Repository Anchor and may name
one file or a directory. A directory is a collection of its recursively
discovered `*.md` files, ordered by repository-relative POSIX path.

## Document structure

A document contains JSON front matter followed by an ordinary Markdown title
and body:

````markdown
---
{
  "id": "I_example",
  "number": 16,
  "reference": "example",
  "state": "open",
  "stateReason": null,
  "labels": ["enhancement"],
  "assignees": [],
  "author": null,
  "relationships": {
    "parent": null,
    "subIssues": [],
    "blockedBy": [],
    "blocking": []
  },
  "issueType": null,
  "milestone": null,
  "createdAt": "2026-08-26T05:33:04Z",
  "updatedAt": "2026-08-26T05:33:04Z",
  "closedAt": null
}
---
# Example Issue

The body is Markdown. It may contain headings, fenced code, and `---` lines.
````

JSON is used for the front matter so `null`, arrays, strings, and nested
relationships have unambiguous types without adding a YAML interpretation
layer. Duplicate object keys are invalid.

The opening `---` must be the first line. The next line containing exactly
`---` closes the JSON object. After optional empty lines, the next line must be
a non-empty level-one ATX heading (`# Title`). Its text is the Issue `title` and
its one-based line number is the Markdown `location.line`.

The `body` is every line after the title. One empty line immediately following
the title is treated as the title/body separator and removed. Remaining content
is preserved with line endings normalized to `\n`; a final file-terminating
newline is not part of the body.

## Metadata

The front matter requires exactly these fields:

| Field | Meaning |
|---|---|
| `id` | Stable opaque Issue Identity. |
| `number` | Positive Project-local Issue Number, assigned explicitly by the author. |
| `reference` | Mutable human-readable Issue Reference. |
| `state`, `stateReason` | Issue lifecycle facts. |
| `labels`, `assignees`, `author` | Labels and source actor facts. |
| `relationships` | Complete `parent`, `subIssues`, `blockedBy`, and `blocking` facts. |
| `issueType`, `milestone` | Optional GitHub-compatible classification facts. |
| `createdAt`, `updatedAt`, `closedAt` | Explicit lifecycle timestamps or `null` where the profile permits known absence. |

All field values follow the Issue profile rules. Missing and unexpected
metadata fields are errors; omission never means unsupported or not fetched.

The source owns and derives the remaining profile fields:

| Profile field | Derived from |
|---|---|
| `projectId` | The configured Project, never document metadata. |
| `title` | The level-one heading. |
| `body` | The Markdown following the heading. |
| `origin` | `{ "kind": "markdown" }`. |
| `location` | The repository-relative file path and title line. |

This separation prevents a document from changing Project membership or
forging its provenance and location.

## Collection and failure semantics

An existing empty directory is a fresh empty Issue collection. A missing
configured path is unavailable, not empty. Paths and discovered symlinks that
resolve outside the Repository Anchor are rejected.

Every document must parse and conform before a refresh is accepted. One
malformed record, duplicate Issue Identity, duplicate Issue Number, or read
failure fails the whole new collection. Numbers are unique within the Project;
gaps are valid and Dashpot does not allocate them while the source is
read-only. The common Issue Source lifecycle then reports the last complete
collection as stale when one exists, or unavailable otherwise. Diagnostics
distinguish path, absence, permission, I/O, malformed syntax, profile,
duplicate-identity, and duplicate-number failures.

The executable input example is
[`tests/fixtures/local-markdown/ISSUES.md`](../../tests/fixtures/local-markdown/ISSUES.md),
and its canonical adapter output is
[`fixtures/markdown.json`](fixtures/markdown.json).
