---
status: accepted
date: 2026-09-27
---

# Record Runtime Events locally and send none

Dashpot had no record of what it did. A hook publisher that failed printed one
line to its harness's stderr, an off-loop failure kept only its message, and
the cost of a running dashboard was measured from outside it, by sampling its
child processes and tracing it with `strace`
([#311](https://github.com/ned2/dashpot/issues/311)). Recording that behaviour
means writing identifiers from a person's machine — paths, Branch names,
Agent Session Identities — somewhere. Where that data may go is decided
before any of it is recorded.

## Decision

- **Dashpot's own data never leaves the machine.** Dashpot records Runtime
  Events in an Event Log on the local filesystem and sends none of them
  anywhere: there is no telemetry endpoint, crash reporter or exporter. A
  person who wants to share events does so
  by reading the Event Log and attaching what they choose, for example to a
  bug report.
- **`gh`'s own telemetry is left to `gh`.** GitHub CLI 2.100 sends usage
  telemetry of its own by default (`gh send-telemetry` appears among a traced
  dashboard's children), and every `gh` process Dashpot starts sends it like
  any other `gh` run. Dashpot does not override the user's `gh`
  configuration: it neither sets nor clears `GH_TELEMETRY` or
  `DO_NOT_TRACK` in its children's environment. The installation guide
  documents `GH_TELEMETRY=0` and `DO_NOT_TRACK=1` for a person who wants `gh`
  quiet.
- **"Telemetry" is not Dashpot's word.** It implies sending data off the
  machine, which Dashpot never does; the domain language names the local
  record a Runtime Event and its file an Event Log.

## Consequences

- An exporter to a remote collector — OpenTelemetry's OTLP, say — would
  reverse this decision and needs an ADR of its own. The span helper mirrors
  OpenTelemetry's API so that such a change touches one module, not so that
  one is planned.
- A person debugging, or an agent working for them, reads the Event Log
  directly or through `dashpot events`
  ([#316](https://github.com/ned2/dashpot/issues/316)); there is no hosted
  view.
- `gh`'s telemetry is outside Dashpot's control and outside this promise; the
  installation guide says so, rather than implying the promise covers every
  process Dashpot starts.
- The [design](../observability-design.md) and the Event Log's own decision,
  [ADR 0059](0059-keep-an-append-only-event-log-in-each-checkout.md), follow
  from this boundary: everything recorded stays on the machine that recorded
  it, in the checkout it belongs to.

## Considered options

- **Opt-in remote reporting.** Rejected: Dashpot's audiences are the people
  and agents on the machine, and a bug report can carry a log a person has
  read. An opt-in path would still need a collector, retention and a privacy
  policy for data nobody has asked to send.
- **Disable `gh` telemetry in Dashpot's children.** Rejected: it would make
  Dashpot's `gh` behave differently from the user's own, silently override a
  choice that belongs to the user's `gh` configuration, and still leave every
  other `gh` run on the machine sending it.
