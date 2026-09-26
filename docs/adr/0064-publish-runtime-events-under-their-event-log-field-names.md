---
status: accepted
date: 2026-09-27
---

# Publish Runtime Events under their Event Log field names

[ADR 0059](0059-keep-an-append-only-event-log-in-each-checkout.md) makes
`dashpot events --json` a published interface under
[ADR 0034](0034-publish-an-alpha-with-patch-compatible-interfaces.md), and
names a Runtime Event's fields after OpenTelemetry semantic conventions
(`event.name`, `process.exit.code`, `dashpot.session.id`, …) where one
exists. Every other `--json` document Dashpot publishes uses camelCase keys
with an unknown value as an explicit `null`
([serialization](../../src/dashpot/serialization.py)). The two rules meet in
`dashpot events --json`
([#316](https://github.com/ned2/dashpot/issues/316)).

## Decision

- **The document is camelCase.** `dashpot events --json` prints
  `{directories, events, unreadable}`, each unreadable file as
  `{path, lines, error}`, like the other published documents.
- **Each event keeps its Event Log field names.** An event in `events` has
  the names it has on disk, every field present, an absent one as `null`.
  It is not renamed to camelCase.
- **The event's key set is published; the file format stays internal.** A
  field removed or renamed in the output is a compatibility change under
  ADR 0034 even though the file carries a `schema` version of its own.

## Consequences

- An event reads the same in a file, in `dashpot events --json` and in the
  observability design's field table, and the conventions a reader knows
  from OpenTelemetry apply to both.
- A consumer of `dashpot events --json` meets two naming schemes in one
  document: camelCase for the envelope, dotted names inside an event. The
  README's JSON contract names the exception.
- An event #314 or a later Issue adds appears in the output under its own
  field names with no serializer change.

## Considered options

- **camelCase every event field** (`processExitCode`, `dashpotSessionId`).
  Rejected: it would give every field a second name to maintain beside its
  on-disk one, lose the OpenTelemetry names that make the fields
  recognisable, and make a line copied from a file differ from the same
  event in the command's output.
- **Print the file lines as they are (JSON Lines).** Rejected: the reader
  skips lines it cannot read and a file may have been written by a newer
  Dashpot, so the raw lines are not the tolerant view the command promises,
  and there would be nowhere to report unreadable lines alongside them.
