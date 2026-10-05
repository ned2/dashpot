---
status: accepted
date: 2026-10-05
---

# Stream the Event Log by UTC day, and select lines before validating them

[ADR 0099](0099-print-runtime-events-as-json-lines.md) prints `dashpot events`
as JSON Lines, but only after the whole read. It rejected streaming day by
day because a span longer than a day would print out of order. The holistic
review of 2026-10-05 measured that whole read
([#557](https://github.com/ned2/dashpot/issues/557)). The reader parsed every
line through the Pydantic models before asking whether the selection kept
it. It then held every selected event and sorted them before printing the
first. The review measured this Repository's own Event Log at 33.7 MB: it
took about 2 s and peaked at 208 MB of memory, about 4.2 KB per event against about 680 B on disk.
[ADR 0059](0059-keep-an-append-only-event-log-in-each-checkout.md) lets an
Event Log grow until a person removes it, and about 100 MB a day at `full`
would need gigabytes of memory, and more than a minute, before
`dashpot events | head` printed a line. `dashpot work show` reads up to seven
days of its session's outcomes, and it validated every line of each day it
read.

## Decision

- **A line is selected by its raw fields before it is validated.** Each line
  is decoded as JSON first. A line that is not a JSON object of this
  `schema`, naming an event this Dashpot has a model for, is unreadable
  whatever the selection, as before. A known event's line is then asked
  whether the selection may keep it: its run ID, its session, harness, Issue
  and Project fields, at the top or among a span's attributes, its `time`
  against `--since`, its level, and whether it may be an outcome. Only a line
  that passes is validated, and the validated event is checked by the
  selection again. Validation is strict, so a line's values are its event's
  values, and the raw check refuses only what the event's own check would
  refuse.
- **A JSON object the raw check leaves out is neither validated nor
  reported.** A line of another session that would not validate is skipped
  silently by `dashpot events --session`, where a read without that filter
  reports it. A line that is not JSON, or that names a later `schema` or an
  unknown event, is still reported under every selection.
- **`dashpot events` streams one UTC day at a time.** Every directory's files
  of one day are read together, oldest day first. An event is held back until
  it is older than the next day's start less a carry-over of two days
  (`SPAN_CARRY_OVER`), because no later file can hold an earlier event
  stamped within that bound. Events print as each day settles, and a reader
  that closes the pipe stops the reading. Events of one instant keep the
  order of their files' days, then their directories, files and lines.
- **The bound is two days.** A span is stamped when it started and written to
  the file of the day it ended, so a span stamped no more than two days
  before the day of its file comes out in order. That covers every span that
  ran past midnight, and a span held across a night's suspended machine. A
  longer one, which only a long-lived dashboard's span held across a longer
  suspension could make, prints once its file is read, after later events
  already printed. The command's help and the installation guide say so. At
  its peak a read holds about three days of selected events: the two the
  carry-over spans and the day being read.
- **What could not be read is reported when the read ends,** as before, but
  only for what was read: a reader that closed the pipe early stopped the
  reading too.
- **`dashpot work show` is unchanged in shape.** Its recent outcomes still
  read back one day at a time only as far as they need, and now validate
  only the lines its session's outcomes may be.

## Measurements

Taken while writing this decision, after the review's figures above, on
this Repository's Event Log of 2026-10-05: 36 MB over nine UTC days,
about 55,000 events, the busiest day 7.9 MB. Peaks were taken with
`tracemalloc`; times were taken without it, on a loaded machine, so they
are approximate.

| Read | Peak memory | First event | Whole read |
|---|---|---|---|
| Whole read, sorted (before) | 228 MB | 1.5–3.0 s | 1.5–3.0 s |
| Streamed, one-day carry-over | 74 MB | — | — |
| Streamed, two-day carry-over (chosen) | 85 MB | 0.6–1.2 s | 1.6–3.5 s |
| Streamed, three-day carry-over | 112 MB | — | — |
| `--session` matching nothing (before) | 0.2 MB | — | 1.8 s |
| `--session` matching nothing (now) | 0.2 MB | — | 0.4–0.6 s |

The memory a streamed read holds follows the busiest run of days the
carry-over spans, not the whole Event Log. Its peak grows with each day the
bound adds.

## Consequences

- Amends [ADR 0099](0099-print-runtime-events-as-json-lines.md): its
  consequence "Events are still printed only after the whole read" and its
  rejected option "Stream events day by day, holding back one day" are
  superseded. The order is exact up to the bound rather than always.
- A consumer can no longer rely on every line of a span longer than the bound
  appearing in time order, and has no sign of one that did not, beyond its
  `time` being earlier than the line before it.
- A malformed line of an event the filters leave out goes unreported under
  those filters. A read without filters still reports it.
- A larger bound costs about one more busiest day of memory per day.

## Considered options

- **Default `--since` for `dashpot events`.** Rejected: it bounds the read
  only when the default is kept. It still holds and sorts everything it
  reads, and changes what a bare `dashpot events` prints.
- **A one-day carry-over.** Rejected: it keeps a span in order only when it
  ended on the day after the one it started, so a span held across a
  suspended night that reaches a second midnight would print out of order,
  for about 11 MB less memory here.
- **An exact order by reading every file twice,** first for the earliest
  stamp each file holds. Rejected: the first event still waits on a pass
  over every file, which is what made the whole read slow.
