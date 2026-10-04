---
status: accepted
date: 2026-10-05
---

# Print Runtime Events as JSON Lines

[ADR 0064](0064-publish-runtime-events-under-their-event-log-field-names.md)
has `dashpot events --json` print one camelCase document,
`{directories, events, unreadable}`, and rejected JSON Lines as printing the
file lines as they are. But the command's output is a stream of events. A
consumer that pipes it into `jq -c`, `grep`, `head` or a log tool first has to
unwrap `.events[]`, and the whole document is built before anything is printed.
The output also looks unlike the `.jsonl` files it reads
([#450](https://github.com/ned2/dashpot/issues/450)).

## Decision

- **`dashpot events --json` prints JSON Lines:** one Runtime Event per line,
  each a compact JSON object, in the order the reader merges them: every
  Worktree of the Repository and the machine-local fallback, oldest first.
  With no matching event it prints nothing.
- **Each line is the tolerant reader's event, not the file's line.** It is
  the object `events` held under ADR 0064: the Event Log field names, every
  field its kind of event has, and `null` for an unknown one. A field a
  newer Dashpot wrote is left out, and a line the reader cannot read is
  skipped. `published_event_fields` in `core/event_log_files.py` builds it,
  beside `event_fields`. That is the on-disk projection the Runtime screen's
  detail pane shows, so both name every field the same way. The lines do
  not print `event_fields` itself, which drops every unknown field. That
  would remove keys from the published set under
  [ADR 0034](0034-publish-an-alpha-with-patch-compatible-interfaces.md).
- **What could not be read goes to standard error**, as it does without
  `--json`: one line for each file or directory that could not be read, and
  a count of the lines skipped in each file. The exit status is unchanged.
- **`directories` is dropped.** It named the Event Log directories that held
  files. That is diagnostic detail, not data, and nothing reports it any
  more.
- **`dashpot events remove --json` keeps its single document.** It reports
  each selected file's outcome, which is not a stream.
- **A reader that closes the pipe early ends the output quietly.** When
  `dashpot events --json | head` stops reading, the command stops printing
  and still exits 0. With or without `--json`, it prints no traceback.

## Consequences

- Amends [ADR 0064](0064-publish-runtime-events-under-their-event-log-field-names.md):
  this supersedes its decision "The document is camelCase", and its rejected
  option "Print the file lines as they are (JSON Lines)", for this command.
  ADR 0064 rejected raw lines for two reasons. Printing the reader's own
  events answers the first: a raw line is not the tolerant view. Standard
  error answers the second: there would be nowhere to report unreadable
  lines. ADR 0064's other two decisions stand: each event keeps its Event Log
  field names, and its key set is published.
- A closed pipe is the one exit status that changes: before this, it ended
  in a traceback and a non-zero status, with or without `--json`.
- `dashpot events --json | jq -c 'select(...)'`, `grep` and `tail` work
  without an unwrap step, and the output reads like the `.jsonl` files.
- A consumer no longer meets two naming schemes. The output has no camelCase
  envelope, only events under their Event Log names.
- This is a breaking change to a published `--json` shape. It lands before
  the first release, so the unreleased 0.1.0 entry in the changelog records it
  and no minor version is needed.
- A consumer that needs unreadable lines as data reads standard error, which
  names each file. There is no machine-readable form of them any more.
- **Events are still printed only after the whole read.** A span is stamped
  when it started but written to the file of the day it ended, so any later
  file can hold an earlier event. An exact oldest-first merge therefore has
  to read every selected file before it knows the first event. Printing each
  event as it is read would need a bound on how long before its file's day
  an event can be stamped. The Event Log records no such bound, since a span
  can run across midnight or across a suspended machine. JSON Lines still
  spares the reader one whole document. A later `--follow`, or the Runtime
  screen reading the files
  ([#452](https://github.com/ned2/dashpot/issues/452)), would have to settle
  that order first.

## Considered options

- **Add `--jsonl` beside `--json`.** Rejected: it would leave two output
  formats to maintain for one command.
- **Print `event_fields(event)`, the on-disk projection.** Rejected: it
  leaves out every field whose value is unknown, while ADR 0064 publishes
  every field present with `null`.
- **Print `directories` on standard error.** Rejected: every run would print
  diagnostic noise for a detail no consumer asked for.
- **Stream events day by day, holding back one day.** Rejected for now. It
  would be exact only for spans shorter than a day. A longer span would be
  printed where its file is read, out of order, and the command promises
  oldest first.
