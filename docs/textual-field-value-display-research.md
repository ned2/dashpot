---
status: research
date: 2026-08-27
---

# Field-value displays in Textual detail panes

Research date: 2026-08-27.

## Conclusion

Textual 8.2.8 has no dedicated description-list, property-grid, or key-value
widget. The official widget catalogue provides `Label`, `Static`, layout
containers, `Rule`, and generic tabular widgets, but no semantic field-value
display. [Official widget catalogue](https://textual.textualize.io/widgets/)

For Dashpot, the best fit is a small read-only compound widget containing a
two-column grid of separate label and value widgets:

```text
Status       fresh
Workspaces   /repo
Anchor       /repo
Targets      1
```

This recommendation is an inference from documented Textual idioms, not a
framework-prescribed pattern. It adapts Textual's official compound-widget
example, which pairs a right-aligned fixed-width `Label` with a `1fr` control,
and its documented grid support for content-sized and fractional columns.
[Compound widgets](https://textual.textualize.io/guide/widgets/#compound-widgets)
[Grid auto columns](https://textual.textualize.io/guide/layout/#auto-rows-columns)

Use one reusable `DetailFields`-style widget in both Project Status and Issue
panes. Give field names and values distinct classes, render field names in
`$text-muted`, render values in `$text`, and align all values on one vertical
edge. Let headings and repeated-data sections span both columns. This gives
TCSS direct control over hierarchy and wrapping while keeping the domain-to-view
projection shared by both panes.

## Version and current Dashpot shape

Dashpot pins `textual==8.2.8` in `pyproject.toml` and `uv.lock`. The current
Project Status and selection panes each update one vertically scrollable
`Static` with newline-delimited `Field: value` strings in `src/dashpot/app.py`.

`Static` is not a wrong primitive: it accepts strings, Textual `Content`, and
Rich renderables, and `update()` supports the same content types.
[Static reference](https://textual.textualize.io/widgets/static/)
The question is whether the field/value distinction should remain inline
content styling or become layout structure.

## Documented Textual building blocks

### Compound label/content rows

The official compound-widget guide constructs an `InputWithLabel` widget from
two children. Its CSS makes the row horizontal, gives the label a fixed width,
right-aligns its text, and gives the input the remaining `1fr` width. The guide
presents composition as the reusable pattern when multiple widgets form one UI
concept. [Compound widgets](https://textual.textualize.io/guide/widgets/#compound-widgets)

Adapting the second child from `Input` to `Static` or `Label` for read-only
values is a Dashpot-specific inference. The alignment and composition idiom
itself is directly documented.

### Two-column grid

Textual's grid layout supports explicit column counts, gutters, spans, and
content-sized or fractional columns. `auto` computes a column size from its
content, while `1fr` consumes remaining space; `column-span` lets a title,
section heading, or full-width list occupy both columns.
[Grid styles](https://textual.textualize.io/styles/grid/)
[Grid columns](https://textual.textualize.io/styles/grid/grid_columns/)
[Auto rows and columns](https://textual.textualize.io/guide/layout/#auto-rows-columns)

The direct Dashpot application is inferred: use `grid-size: 2`, either
`grid-columns: auto 1fr` or a deliberately fixed label width plus `1fr`,
`grid-rows: auto`, and a one-cell horizontal gutter. Prefer short field names
so the label column cannot starve values in a narrow pane.

### Visual hierarchy through theme variables

Textual defines `$text` for ordinary legible content and `$text-muted` for
lower-importance text such as subtitles and supplementary information. It also
defines `$surface`, `$panel`, and `$boost` for layered backgrounds.
[Textual themes and variables](https://textual.textualize.io/guide/design/#theme-variables)

Using `$text-muted` for field names and `$text` for values is an inferred
information hierarchy consistent with those documented meanings. A subtle
`$boost` background on labels is possible, but spacing, alignment, and color
should be tried first; heavy row boxes would add noise to these dense panes.

`Rule` is the official separator widget, analogous to an HTML horizontal rule.
It is suitable between sections such as Issue metadata and Agent Sessions, not
between every field row. [Rule widget](https://textual.textualize.io/widgets/rule/)
That placement is a design inference.

## Two viable implementations

| Approach | Official support | Strengths for Dashpot | Costs |
| --- | --- | --- | --- |
| Styled `Content` or a Rich renderable in the existing `Static` | `Static` accepts `Content` and Rich renderables; the content guide documents span styles and theme variables. | Smallest change; one wholesale `update()`; a Rich table can align columns. | Field and value remain one renderable, so TCSS cannot target individual fields; responsive layout and section composition are less direct. |
| Native two-column grid with label/value children | Compound widgets and two-column layouts are documented patterns. | Structural alignment; separate TCSS classes; natural wrapping in the value column; reusable for both panes; headings can span columns. | More child widgets and an update/recomposition API are required. |

[Textual content guide](https://textual.textualize.io/guide/content/)
[Rich renderable in a `Static` example](https://textual.textualize.io/guide/widgets/#content-size)

The native grid is the better fit because the requested uplift is specifically
about persistent field/value demarcation in two long-lived panes, and those
panes also contain headings and repeated sublists. Styled inline content is a
reasonable smaller first slice if preserving the existing single-`Static`
update seam matters more than layout control.

## Suggested Dashpot presentation contract

The following is proposed, not documented Textual API:

```python
DetailFields(
    Field("Status", project.status),
    Field("Workspaces", ", ".join(project.workspaces)),
    Field("Anchor", project.primary_anchor),
    Field("Targets", str(len(targets))),
    Section("Observation targets"),
    FullWidth(target_summary),
)
```

```css
DetailFields {
    layout: grid;
    grid-size: 2;
    grid-columns: auto 1fr;
    grid-rows: auto;
    grid-gutter: 0 1;
}

DetailFields > .field-name {
    width: 100%;
    color: $text-muted;
    text-align: right;
}

DetailFields > .field-value {
    height: auto;
    color: $text;
}

DetailFields > .detail-heading,
DetailFields > .detail-section,
DetailFields > .detail-list {
    column-span: 2;
    height: auto;
}
```

Keep the Issue title as a full-width heading rather than inventing a `Title`
field. Keep Agent Sessions as a labelled section with full-width repeated rows.
Defer Observation Targets from the Project Status pane until Dashpot explicitly
designs the multi-target management experience; a single target otherwise
repeats Anchor and Agents while exposing low-level collection details.

If the one-`Static` approach is chosen, construct `Content` safely. The official
content guide warns that interpolating user or source text into markup with an
f-string can interpret square brackets as markup, and recommends
`Content.from_markup(..., variable=value)` for escaped substitution.
[Safe markup variables](https://textual.textualize.io/guide/content/#markup-variables)
This matters for Issue titles, labels, paths, and external identifiers.
