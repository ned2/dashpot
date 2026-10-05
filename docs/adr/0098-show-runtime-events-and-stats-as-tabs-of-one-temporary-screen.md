---
status: accepted
date: 2026-10-06
---

# Show Runtime Events and Stats as tabs of one temporary screen

A running dashboard keeps its own recent Runtime Events in memory
([ADR 0059](0059-keep-an-append-only-event-log-in-each-checkout.md)), but until
now the only view of them was the aggregate Runtime Stats box on `s`, a centred
modal laid out like the Legend. To see the events themselves you raised the
Event Level to `full`, left the dashboard, and read every process's events
mixed together with `dashpot events`. Neither view could be found from the UI:
Runtime Stats was reachable only by its key, and Dashpot added nothing to
Textual's command palette
([#451](https://github.com/ned2/dashpot/issues/451)).

## Decision

One full-screen temporary screen, **Runtime**, replaces the Runtime Stats box.
It has two tabs, **Events** and **Stats**, under a shared header that names the
Event Level and how to change it, whose events these are, the window the buffer
covers, and how many events it holds. Both tabs read the dashboard's in-memory
buffer, which keeps every level whatever the Event Level records.

- **Events** lists the buffered events, newest last, in a table with a detail
  pane that shows every field of the selected event, including its stored UTC
  time. Rows are in the order the buffer received them, as the Event Log's
  lines are, so a span sits where it ended, after the children it waited on,
  while its time is when it started. Show, Kind and Errors-only filters
  narrow the table and last for the life of the process, never on disk.
  The table follows the newest event until a person moves back through it,
  and `End` resumes following.
- **Stats** holds the Runtime Stats sections at full width, unchanged but
  for their clock, below.
- **Both tabs keep one clock.** Every time either tab shows, from an
  event's row and summary to a pause's end and the last refresh, is on the
  local clock, so a time on one tab is found on the other as it reads.
  Only the detail pane shows an event's stored UTC time, which matches the
  event to its line in the Event Log
  ([#547](https://github.com/ned2/dashpot/issues/547)).
- **Diagnostics keep the same clock.** A Diagnostic that names a time gives
  it on the local clock too, to the second, so a pause read in the
  Diagnostics is found on the Stats tab as it reads
  ([#591](https://github.com/ned2/dashpot/issues/591)). A Diagnostic only a
  dashboard reports, `github-unattended-paused`, shows the time as the tabs
  do. One a Query Source reports also reaches headless output, a `--json`
  document's Diagnostics among it, where no dashboard says which clock a
  time is on, so it adds the clock's UTC offset: `github-rate-limit-paused`
  and the refusal held by a Rate Limit Pause name when queries resume as
  `23:00:00 +10:00`, and `github-rate-limit-low` names the reset GitHub
  reported the same way. These give no date: a pause ends within the hour
  after it starts, and a fresh reading's reset lies within the hour after
  the reading.

### Tabs inside a temporary screen

[ADR 0051](0051-adopt-long-lived-peer-dashboard-screens.md) rejected tabs for
the Peer Screens: a tab hides one of two related query surfaces and adds
navigation state to a destination a person returns to all day. Neither
objection holds here. Runtime is a diagnostic screen opened on purpose and
closed again, and its two tabs are two readings of the same buffer over the
same window under the same Event Level, which the shared header states once.
Two separate screens would repeat that header and its level control; a Stats
sidebar beside the events would squeeze the table, worst below the compact
breakpoint.

### The command palette is where features are discovered

The palette offers **Runtime Events** and **Runtime Stats**, each with a
one-line description, opening the screen on its tab. `e` and `s` do the same
from the keyboard. Textual's own palette commands are left as they are. A
dashboard feature that has no visible control earns a palette command, so a
person can find it by name without first knowing its key.

### Opened from Peer Screens only

The palette commands and the `e` and `s` keys exist only on a Peer Screen
of ADR 0051, and on no temporary screen: not Issue Detail, the Legend,
Cleanup, a column editor, or Runtime itself. Which screens are Peer Screens is
read from the registered peers, so a future peer offers Runtime without
naming it. This changes `s`, which as an App binding used to open Runtime
Stats over any screen. Stacking one temporary screen on another leaves a
person further from the dashboard than the diagnostic is worth, and the
screen's facts are the dashboard's, not the popup's.

### Escape is the only close

Inside the screen, `e` and `s` move to their tab and do nothing on the tab
already shown, and `l` cycles the Event Level from either tab. Only Escape
closes the screen. `s` used to close Runtime Stats as well as open it; with
two tabs a tab key that sometimes closes would make a person check which tab
they are on before pressing it.

## Considered options

- **Two separate screens**: rejected because they share the buffer, the
  window and the Event Level, and switching between them would mean closing
  one and opening the other.
- **A Stats sidebar on the Events screen**: rejected because the event table
  needs the width, especially below the compact breakpoint.
- **Keep the modal Runtime Stats box and add an Events box beside it**:
  rejected because a 90-column modal cannot hold an event table and a detail
  pane together.
- **Let `e` and `s` toggle, closing the screen from their own tab**: rejected
  for the reason under _Escape is the only close_.
- **Open Runtime over any screen, as `s` did**: rejected for the reason under
  _Opened from Peer Screens only_.
- **Diagnostics in UTC, as they were**: rejected because the same pause read
  as `22:01:00` on the Stats tab and as `…T12:01:00Z` in the Diagnostics,
  and a person had to convert one to find the other.
- **A full RFC 3339 stamp with its offset in headless Diagnostics**:
  rejected because the date it adds says nothing a time within the hour
  needs, and the dashboard shows the same message.

## Consequences

- The Legend's Runtime Stats key group becomes a Runtime group, covering the
  screen's keys and the event table's `End`.
- Reading the Event Log files, so the Events tab can show other processes,
  other dashboards and past days, is
  [#452](https://github.com/ned2/dashpot/issues/452). Moving from a Stats
  figure to the events behind it is
  [#453](https://github.com/ned2/dashpot/issues/453).
- The buffer numbers every event it keeps, so the table appends only what
  arrived since its last update and drops only the rows the buffer let go of,
  keeping its cursor on the event it was on.
