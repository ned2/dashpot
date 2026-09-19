---
status: research
date: 2026-09-16
---

<!-- The instructions given verbatim to every card-extraction agent, as used on 2026-09-16; the frontmatter above and this comment are the only additions. -->

# Extractor instructions

You are decomposing a research note into atomic **idea cards**. You extract; you do not group, rank, judge, or synthesise. Do not read any file other than the note files you are given. Do not search the web. Do not look in any git repository.

One card = one claim, mechanism, definition, practice, tool, policy, argument, measurement, or substantive dead end, as the note states it. Stay in the note's own words; do not paraphrase into your own framing.

## Output

Write a JSON file at the path you are given. It is a JSON array of card objects. Each card has exactly these keys:

- `id`: `"<note-code>:<n>"` — the note code you are given and a running number in document order, starting at 1.
- `claim`: one sentence, in the note's own terms. At most 40 words; at most 60 words when `kind` is `measurement`.
- `figures`: the numbers in the claim, verbatim, with units and conditions (e.g. `"23% fewer medical errors, I-PASS, 9 hospitals"`). Empty string if none. If the note marks the claim `(corrected …)` or `(qualified …)`, put the marker text here too.
- `kind`: one of `finding`, `mechanism`, `definition`, `practice`, `tool`, `policy`, `argument`, `measurement`, `dead-end`.
- `evidence`: one of `C` (causal: randomised or controlled, with the outcome measured), `M` (measured: telemetry or observational, not an experiment), `Q` (qualitative study: interviews, ethnography, case study), `T` (testimonial, self-report, vendor claim, blog), `A` (argument or theory with no data), `-` (none stated). Use what the note says about the evidence, not your own judgment.
- `unit`: what the claim is about: one of `hunk`, `file`, `change`, `PR`, `module`, `repository`, `session`, `person`, `team`, `organisation`, `field` (the discourse or literature itself), `-`.
- `where`: where in the work the note places this, **in the note's own words** (free text, e.g. `"at code review"`, `"when a session is compacted"`, `"on joining a project"`). Empty string if the note does not place it.
- `actor`: one of `person`, `agent`, `team`, `tool`, `-`.
- `source`: the terminal citation in short form as the note gives it — author and year, or product and page/document (e.g. `"Fagan 1976"`, `"Linear docs, Agents page"`). Empty string if the note gives none.
- `anchor`: the exact `##` or `###` heading text of the section the card was read from, verbatim (the heading line without the leading `#`s).
- `counterpart`: `"none"` **only** when the card comes from a row of a "Mapping to the existing notes" (or similar) table that says no other note covers this idea (wording like "No counterpart", "none", "not covered", "no note touches"). Otherwise empty string.
- `restates`: the `id` of an earlier card in this note that this card restates (same claim, same figures, said again in a Finding section, a summary table, or a mapping table). Empty string if this is the first statement.

## Rules

1. Every body section (`##` and `###`) yields at least one card — except a Finding/summary section, which yields cards **only** for claims stated nowhere else in the note; anything it restates is either skipped or recorded with `restates`.
2. A catalogue entry (a named tool, product, policy, project, paper-as-item) yields **one** card of kind `tool` or `policy` (or `finding` for a paper) whose claim carries the name, what it does (mechanism), when it fires (trigger), and its evidence status. Do not split a catalogue entry into several cards unless the note makes several distinct claims about it.
3. A table row containing a number yields its own `measurement` card. A table row without a number yields a card of the appropriate kind if it states something not already carded; otherwise a `restates` card or nothing.
4. A claim the note marks `(corrected …)` or `(qualified …)` is carried in its corrected form, with the marker in `figures`.
5. A **substantive** dead end — "no source measures reviewer-hours per PR", "no study compares X with Y" — yields a `dead-end` card. A **procedural** dead end — a blocked page, a 403, a search budget, a paywall, a query that returned nothing — yields **no card**.
6. A "Mapping to the existing notes" table: each row yields a card only if it states a claim or a connection not already carded (mark `restates` when it restates); a row saying no other note covers the idea yields a card with `counterpart: "none"`. Do not follow the links in that table.
7. A claim stated in two notes yields a card in each; do not de-duplicate across notes.
8. Preserve every number exactly as written. Do not round, convert, or infer.
9. Do not add claims the note does not make. Do not editorialise.

## Granularity check

A 2,000-word note should yield roughly 25–45 cards; a 10,000-word note roughly 100–200. If you are far outside those ranges, you are splitting too finely or lumping too coarsely: re-read rules 2 and 3.

When done, validate that the file is well-formed JSON, that ids are sequential, and that every `restates` points to an earlier id in the same file. Reply with only: the card count, the count by `kind`, and any section you found hard to card and why (two or three sentences at most).
