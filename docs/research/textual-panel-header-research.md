---
status: research
date: 2026-08-27
---

# Panel headers and accent bars in Textual

Research date: 2026-08-27. This note targets Dashpot's pinned
`textual==8.2.8`.

## Conclusion

Textual has a particularly good built-in match for Dashpot's one-line pane
titles: use a widget's `border_title` with the `panel` border type. Unlike an
ordinary line border, Textual 8.2.8's `panel` border uses a full block for the
top edge and deliberately reverses the title colors, producing a full-width
themed top band with highlighted text. The public border reference includes
`panel` among the supported border types; the tagged implementation shows both
the block top edge and the title-color reversal.
[Border styles](https://textual.textualize.io/styles/border/)
[8.2.8 `panel` border source](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/_border.py#L110-L113)
[8.2.8 title reversal](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/_border.py#L235-L241)

For Dashpot, try this terminal-native treatment first on Project Status and
Selection:

```css
#project-pane,
#selection-pane {
    border: panel $primary-darken-2;
    border-title-align: left;
    border-title-style: bold;
}
```

Set each pane's `border_title` instead of rendering a separate `.pane-title`.
This fits the current contract because both headings are already one terminal
row. Keep an explicit header child instead if the design later needs wrapping,
actions, status controls, or independently addressable header content.

## What the visual idiom is called

| Visual treatment | Established name | Meaning here |
| --- | --- | --- |
| A filled, full-width top region containing a title | **Panel header**; **card header** when the container is called a card | This is the closest front-end term for the requested Dashpot treatment. PatternFly exposes `PanelHeader`; Bootstrap and Salt expose card headers. |
| Text interrupting or embedded in an outline | **Border title** in Textual; visually **fieldset legend** or **legend-style title** on the web | Textual's ordinary `border_title` appearance. HTML `legend` is specifically the caption of a `fieldset`, so the name is only a visual analogy for a non-form pane. |
| A thin colored edge with no content in it | **Top accent**, **top accent border**, or **accent edge** | A decorative/emphasis treatment, not a header. Salt's Card API calls its positioned treatment an accent border. |
| A short colored rule beside header text | **Accent bar** | The bar supports the header but is not itself the header container. |

[PatternFly Panel and `PanelHeader`](https://www.patternfly.org/components/panel/)
[Bootstrap card headers](https://getbootstrap.com/docs/5.0/components/card/#header-and-footer)
[Salt Card accents and `CardHeader`](https://www.saltdesignsystem.com/salt/components/card/usage)
[HTML `fieldset` and `legend`](https://html.spec.whatwg.org/multipage/form-elements.html#the-legend-element)

Accordingly, call the Dashpot component a **panel header**. Describe this visual
variant as a **colored panel-header bar**. Reserve **top accent border** for a
thin line that does not contain the heading. The `panel`-border implementation
is a terminal-specific hybrid: structurally it is Textual's **border title**, but
visually it reads as a **panel-header bar**.

## Textual strategies

### 1. `border: panel` plus `border_title` — recommended for Dashpot

Every Textual widget has `border_title` and `border_subtitle`; the title is
painted in the top border and only appears when a border is enabled. It can be
set per instance or with `BORDER_TITLE` on a widget class.
[Textual border-title guide](https://textual.textualize.io/guide/widgets/#border-titles)

TCSS can independently set `border-title-align`, `border-title-color`,
`border-title-background`, and `border-title-style`. Alignment defaults to left.
The `panel` border is the notable special case because its filled top edge and
automatic reversal create the header band without padding a string to the pane
width.
[Border-title alignment](https://textual.textualize.io/styles/border_title_align/)
[Border-title colors and background](https://textual.textualize.io/styles/border_title_color/)
[Border-title text style](https://textual.textualize.io/styles/border_title_style/)

Limitations are deliberate: a border title is one line, long content is cropped
with an ellipsis, and it is content painted into the border rather than a child
widget. It therefore cannot contain controls or use child layout. These are good
constraints for Dashpot's current pane titles, including `#<ID>: <TITLE>`, but
not for a future toolbar-like header.

Dynamic strings are parsed as Textual markup by the 8.2.8 setter. Assign a
literal `Content(title)` (or otherwise escape/parameterize markup) for issue
titles so square brackets from source data are not interpreted.
[8.2.8 border-title setter](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widget.py#L249-L267)
[Safe content variables](https://textual.textualize.io/guide/content/#markup-variables)

### 2. Explicit header child — best for richer headers

Dashpot already composes each pane from a `Vertical`, a one-row `Static` title,
and the detail body. Styling that title with `width: 100%`, a theme background,
contrasting text, padding, and bold text produces a true full-width panel
header. This is an ordinary Textual **compound widget** pattern: a widget made
from composed children.
[Compound widgets](https://textual.textualize.io/guide/widgets/#compound-widgets)

This approach supports wrapping, title/actions layouts, focus or hover states,
and separate testing/querying. A simple vertical layout is enough for a header
and body. Use a grid only when the header itself needs structured regions, such
as `1fr auto` title/actions columns.
[Textual grid layout](https://textual.textualize.io/guide/layout/#grid)

If the header lives inside the same scrolling container and must stay visible,
`dock: top` is Textual's documented sticky-header primitive: docking removes the
widget from normal layout and fixes it to a container edge. It is unnecessary
when the header is already a sibling of an independently scrolling body.
[Dock](https://textual.textualize.io/styles/dock/)

### 3. Thin accent edge or legend-style border title

For a quieter treatment, Textual supports `border-top` independently of the
other edges. `border-top: heavy $accent` is the terminal analogue of a top
accent border. Adding `border_title` embeds a legend-style title in that rule,
but `border-title-background` colors only the title segment; it does not turn an
ordinary border into a filled full-width band.
[Per-edge borders](https://textual.textualize.io/styles/border/)

## Theme and accessibility constraints

Use theme variables instead of literal colors. Textual describes `$primary` as
appropriate for titles and strong-emphasis backgrounds and `$accent` as a color
to use sparingly to draw attention. `$text` is generated for legibility, while
`$primary-muted` with `$text-primary` provides a calmer pairing.
[Textual theme variables](https://textual.textualize.io/guide/design/#base-colors)
[Text legibility](https://textual.textualize.io/guide/design/#ensuring-text-legibility)

Keep the visible heading text: color should strengthen hierarchy, not carry the
only meaning. Check both light and dark themes, `NO_COLOR`, narrow terminals,
long issue titles, and terminals whose fonts render block/box characters
differently. Textual's own FAQ notes that terminal font settings can affect box
character alignment. Snapshot tests are the supported regression tool for the
resulting visual contract.
[Terminal box-character caveat](https://textual.textualize.io/FAQ/#why-doesnt-textual-look-good-on-macos)
[Snapshot testing](https://textual.textualize.io/guide/testing/#snapshot-testing)

The phrase **fieldset legend** should not imply web semantics here. The HTML
Standard defines a legend as the caption for a fieldset's grouped content, and
GOV.UK guidance relies on that association for groups of inputs. Textual's
border title is a rendering facility, not an HTML accessibility relationship.
[HTML legend semantics](https://html.spec.whatwg.org/multipage/form-elements.html#the-legend-element)
[GOV.UK fieldset guidance](https://design-system.service.gov.uk/components/fieldset/)
