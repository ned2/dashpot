---
status: accepted
date: 2026-08-30
---

# Derive the Legend from the Glyphs the panes render

The panes traded words for Glyphs to keep their columns narrow: the Branches
pane's `SYNC` became `✓`, `↑2 ↓1`, `○` and `✗`; the Issues table gained two
one-glyph header columns, `◉` for Issue state and `◈` for Agent Run state;
and the alert line and Diagnostics box prefix each line with `✖`, `⚠` or
`↻`. Each Glyph reads well once known and not at all the first time, and
nothing in the app explained any of them
([#48](https://github.com/ned2/dashpot/issues/48)). Dashpot is a passive
view, so there is no detail action whose result would teach a Glyph as a
side effect: a Legend is the whole remedy.

The vocabulary had also drifted apart from its explanation. Six Glyphs were
inline literals with no constant behind them, so nothing could enumerate what
the app renders, and `○` meant *unknown* in every `STATE` and `SESSIONS`
column and *unpushed* in `SYNC` a few rows away.

Dashpot now renders every Glyph from a `Glyph` value that pairs the symbol
with its meaning and, where the cell colours it, its light and dark colour
([`glyphs.py`](../../src/dashpot/glyphs.py)). Each pane keeps its own
vocabulary — `STATE_GLYPHS`, `SEVERITY_GLYPH`, `ISSUE_STATE_GLYPHS`,
`AGENT_STATE_GLYPHS`, the `SYNC` constants — keyed by the `Literal` union it
already renders from, and exports the tuple the Legend shows for it. The
Legend ([`legend.py`](../../src/dashpot/legend.py)) concatenates those
tuples into sections that follow the main screen top to bottom and name the
column a Glyph appears in, and a `?` modal renders them with the colour the
cell would use. A test scans every string constant in `src/dashpot/` and
fails on any non-ASCII character that no Legend symbol contains, so a Glyph
cannot be added without appearing in the Legend, and a second test fails when
one symbol is listed with two meanings. `SYNC`'s *unpushed* Glyph became `∅`
so that `○` keeps its one meaning; the Sessions family `● ◐ ○` stays as it
is because its fill is the liveliness.

## Considered options

- **Spell the headers out** (`STATE`, `AGENT`) or pair every Glyph with its
  word in the cell: rejected because the header label is a column's width
  floor, so the change costs eight cells at every terminal width and reverses
  the commits that introduced the Glyphs, while still leaving the per-value
  Glyphs (`■` by colour, `▶ Ⅱ ?`, `↑2 ↓1`, `✖ ⚠ ↻`) unexplained. In-place
  explanation also has no single artefact a test can check for completeness.
- **Tooltips on the `◉` and `◈` headers**: the Issues table paints its
  headers rather than composing widgets, so a tooltip needs a mouse-move
  override that reads the hovered column from the segment meta. It is cheap
  but mouse-only and covers two Glyphs; it remains a possible complement that
  would read from the same `Glyph` values.
- **Textual's `HelpPanel`**: a side panel that takes thirty to sixty columns
  from panes sized to their content, with a closed `compose()` that offers no
  place for a Glyph section. A modal costs nothing while closed and matches
  the column editor.
- **One central Glyph module** owning every constant: rejected because the
  pane modules import one another in a fixed direction (`alerts` and the
  list panes depend on `issue_table`), so a module typed by their `Literal`
  unions would cycle, and because it would split a pane's vocabulary from the
  read model that renders it.

## Consequences

- A new Glyph is a `Glyph` value with a meaning, or the source scan fails;
  a new state in a `Literal` union without a Glyph fails the map-coverage
  test.
- The Legend and the cells cannot disagree, because there is one constant.
- A symbol has one meaning across the app. The Issue state block is the one
  deliberate exception: four states share `■` and differ by colour alone,
  which the Legend shows as four swatches.
- Severity Glyphs carry no colour of their own; they name the theme variable
  the alert and Diagnostics stylesheets use, so the Legend's swatch and the
  boxes stay in step without a second hex value.
