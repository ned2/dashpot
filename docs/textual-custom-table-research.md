# Custom sortable and filterable tables in Textual

Research date: 2026-08-27.

## Conclusion

Keep Textual's `DataTable`, but treat it as a rendering and interaction adapter
over Dashpot-owned table view state. Textual 8.2.8 has strong primitives for
keyed rows, incremental cell updates, cursor movement, header-click messages,
and programmatic row sorting. It does **not** have a table query model, row
filter API, column visibility flag, public column-reordering API, column chooser,
sort indicators, or lazy data provider.

The well-supported path is therefore:

1. define a typed registry of all available Issue-list columns;
2. keep visible column order, sort terms, and filters in Dashpot state;
3. project canonical Issue/Project/Agent data through that state;
4. reconcile ordinary row changes by stable row key;
5. rebuild the `DataTable`'s columns only when their visibility or order changes;
   and
6. preserve selection explicitly around every sort, filter, or schema change.

This extends Dashpot's present design rather than replacing it. A custom
query-backed `ScrollView` should only be considered if measured scale exceeds
what an in-memory `DataTable` can handle.

## Version checked

Dashpot pins `textual==8.2.8` in `pyproject.toml` and resolves that same version
in `uv.lock`. Version 8.2.8, released 2026-06-30, is also the current upstream
release as of this research. There is consequently no relevant pinned-versus-
upstream feature delta. [Textual v8.2.8 release](https://github.com/Textualize/textual/releases/tag/v8.2.8)

The observations below were checked against both Dashpot's installed 8.2.8
package and the tagged upstream source. They should not be inferred from older
Textual examples.

## What `DataTable` supports

| Concern | Textual 8.2.8 support | Consequence for Dashpot |
| --- | --- | --- |
| Stable identities | Rows and columns accept stable keys which remain valid when their coordinates change. | Continue keying Issue rows by Issue Identity and restore selection by key. |
| Sorting | `sort(*columns, key=None, reverse=False)` supports one or more columns and a custom key callable. | Dashpot supplies sort interaction, state, indicators, and domain-specific keys. |
| Header interaction | Clicking a header emits `DataTable.HeaderSelected`; it does not sort automatically. | Handle the message, toggle direction, update the label, and invoke the chosen sort path. |
| Filtering | No row predicate, query, or visibility API exists. Official guidance describes applications repopulating after searching or filtering. | Filter the Dashpot row projection, then reconcile or rebuild displayed rows. |
| Column visibility | There is no per-column visible property. `remove_column()` deletes that column and all of its cell values. | Keep the full data outside the widget and rebuild the visible schema from the column registry. |
| Column order | `add_column()` appends; there is no public `move_column()` or reorder method. | Represent order as an ordered tuple of column keys and rebuild columns in that order. Never mutate `_column_locations`. |
| Controls | `Input`, `Select`, `SelectionList`, and `ModalScreen` are supported compositional building blocks. | Use them to build filter and column-chooser UI around the table. |
| Large data | Rendering is viewport-oriented and cached, but every cell is stored in the table's in-memory `_data`. There is no pagination or external row provider. | Good for ordinary Issue lists; not a substitute for a query-backed data source at very large scale. |

The official guide explicitly says row and column keys are location-independent
and recommends them over coordinates after deletion or sorting.
[DataTable keys](https://textual.textualize.io/widgets/data_table/#keys) The
tagged implementation exposes `get_row_index()` and `move_cursor()` as public
operations, which are the necessary selection-restoration primitives.
[8.2.8 key lookup and cursor source](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L1030-L1263)

`DataTable.sort()` sorts its internal row-location map using Python `sorted`.
Its callable receives selected **cell values**, not the domain row or its
`RowKey`; the documentation warns that formatted values may need to be undone by
the sort key. This is useful for simple visible-column sorting, but it is not a
domain query abstraction.
[DataTable sorting guide](https://textual.textualize.io/widgets/data_table/#sorting)
[8.2.8 sort implementation](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L2592-L2633)

Header clicks only emit a message containing the column key, index, and label.
The application decides what that means. Keyboard sorting also needs an
application binding because Dashpot uses a row cursor rather than a column
cursor.
[8.2.8 `HeaderSelected` message and click handling](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L623-L649)
[8.2.8 header click source](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L2669-L2691)

The absence of visibility and ordering APIs is significant. `add_column()`
always appends and populates existing rows with a default value;
`remove_column()` removes the metadata and deletes the value from every row.
`clear(columns=True)` resets rows, columns, cursor, hover, scroll position, and
caches. Rebuilding is supported, but selection and scroll restoration belong to
Dashpot.
[8.2.8 clear/add-column source](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L1582-L1667)
[8.2.8 remove-column source](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L1832-L1868)

## Current Dashpot implementation

Dashpot already follows several important Textual practices in
[`app.py`](../src/dashpot/app.py):

- it uses explicit column keys and collision-safe, stable row keys;
- `build_rows()` is a projection from `WorkspaceSnapshot`, rather than treating
  `DataTable` as the source of truth;
- `reconcile_rows()` diffs rows and cells inside `batch_update()`;
- selection is captured by row key and restored after refresh;
- a removed selection falls back to the nearest surviving row index; and
- closed Issues remain in the snapshot while the projection currently omits
  them.

Those are strengths to preserve. Textual specifically describes stable keys as
the way to refer to rows after sorting or deletion, and the official table guide
positions application-specific searching/filtering as repopulation logic rather
than widget configuration.
[DataTable guide](https://textual.textualize.io/widgets/data_table/)

The limiting parts are narrower than the use of a snapshot itself:

- `COLUMN_KEYS` and the six `add_column()` calls duplicate a fixed schema;
- cell tuples depend on that positional schema;
- the open-only predicate is embedded directly in `build_rows()`;
- `reconcile_rows()` always sorts by `project`, `priority`, then `title`;
- no explicit view state explains why a row is visible or where a column belongs;
  and
- Project placeholders and unmatched Agent Run rows do not yet have defined
  behavior under arbitrary Issue filters.

Adding controls directly to these conditionals would make `app.py` a collection
of cross-coupled special cases. The next uplift should introduce a table model
before adding more filters.

## Recommended table model

The model can remain small and UI-focused:

```python
@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: str
    label: str
    value: Callable[[WorkRow], object]
    format: Callable[[object], CellType]
    sort_key: Callable[[object], object]
    searchable: bool = True
    default_visible: bool = True

@dataclass(frozen=True, slots=True)
class SortTerm:
    column: str
    descending: bool = False

@dataclass(frozen=True, slots=True)
class TableViewState:
    columns: tuple[str, ...]       # visible and in display order
    sort: tuple[SortTerm, ...]
    global_search: str
    filters: FilterSet
```

`WorkRow` should retain the stable row key, `RowContext`, row kind, and canonical
field values. Formatting belongs after filtering and sort-key extraction. This
avoids parsing decorated strings such as priority marks or session summaries to
recover their meaning.

Use one ordered `ColumnSpec` registry as the available-column catalogue. Default
visibility and order come from that registry; a future persisted user preference
can override them without changing row semantics.

### Sort recipe

For the first slice, support one active visible column and an ascending/descending
toggle:

1. handle `DataTable.HeaderSelected` for mouse input and add a keyboard action;
2. look up the `ColumnSpec` by `event.column_key`;
3. update `TableViewState.sort`;
4. decorate the active header with an ascending/descending marker; and
5. call `DataTable.sort(column, key=spec.sort_key, reverse=...)` after each row
   reconciliation.

This is the lightest use of the native API. It works when the canonical value or
an unambiguous formatted value is stored in the cell.

If Dashpot later needs sorting by hidden data, stable domain-identity tie-breaks,
or independent directions in a multi-column sort, sort `WorkRow` objects outside
the widget and rebuild the rows in that order. The native callable cannot see the
row key, and one `reverse` flag applies to the entire native sort. Do not reach
into `_row_locations` to force an externally computed order.

### Filter recipe

Make filters pure predicates over `WorkRow`:

- combine different per-column filters with logical AND;
- define global text search as logical OR across explicitly searchable columns;
- normalize case and missing values before comparison;
- keep open-only as the initial `state` filter rather than a special branch;
- distinguish `no open Issues` from `no Issues match the current filters`; and
- define Project-placeholder and unmatched-Agent-Run inclusion independently of
  Issue-only predicates.

An `Input` emits `Input.Changed` as text changes, while `Select` exposes a typed
value and `Select.Changed`. These are the standard controls for global text and
finite-valued filters such as state, Project, or assignee.
[Input messages](https://textual.textualize.io/widgets/input/#messages)
[Select widget](https://textual.textualize.io/widgets/select/)

For large in-memory lists, debounce free-text changes before reprojecting. For an
ordinary GitHub Issue list, immediate local filtering should be measured before
adding debounce machinery.

### Column visibility and order recipe

Use a modal column editor backed by the registry:

- `SelectionList[str]` naturally represents the visible subset and emits
  `SelectedChanged`;
- explicit move-up/move-down actions modify the ordered selection because neither
  `SelectionList` nor `DataTable` provides drag-to-reorder semantics; and
- applying the result replaces `TableViewState.columns`.

[SelectionList widget](https://textual.textualize.io/widgets/selection_list/)
[Modal screens and returning results](https://textual.textualize.io/guide/screens/#modal-screens)

When the ordered visible columns change:

1. capture selected row key and index;
2. optionally capture scroll offsets if preserving horizontal position is useful;
3. call `clear(columns=True)` inside `batch_update()`;
4. add columns in the state-defined order;
5. repopulate the current row projection;
6. reapply the active sort; and
7. restore the selected key if visible, otherwise use the documented nearest-row
   fallback.

Rebuilding only on schema changes avoids the destructive remove/add bookkeeping
for each individual toggle.

### Selection recipe

Textual's cursor is coordinate-based even though rows have stable identities.
Sorting leaves the cursor at a coordinate; filtering or rebuilding may remove
that coordinate entirely. Preserve entity selection explicitly:

1. resolve the cursor coordinate to a `RowKey` before projection changes;
2. apply row/schema changes and sorting;
3. if that key remains, find its new index with `get_row_index()` and call
   `move_cursor()`;
4. otherwise select `min(previous_index, row_count - 1)`; and
5. clear details if no rows remain.

This is essentially Dashpot's current refresh behavior and should become a
reusable operation for refresh, sort, filter, and column changes. If product
semantics require a temporarily filtered Issue to regain selection when a filter
is removed, retain a separate preferred-selection key; otherwise the existing
nearest-visible-row behavior is coherent.

## Viable implementation patterns

### 1. Dashpot view state over the existing `DataTable` — preferred

Extract the registry, `TableViewState`, `WorkRow` projection, and filter/sort
functions while retaining the current widget and keyed reconciliation.

Advantages:

- smallest incremental change;
- fully supported public Textual APIs;
- preserves current selection and refresh tests;
- supports a large optional column catalogue without rendering every column;
- keeps domain values separate from presentation; and
- leaves persistence and remote querying as independent later decisions.

Tradeoffs:

- schema changes require a controlled table rebuild;
- complex external sort ordering may also require a row rebuild; and
- `DashpotApp` needs either a focused `IssueTable` helper or careful delegation to
  avoid accumulating table behavior again.

The natural endpoint is a composite `IssueTable` widget that owns the registry,
view state, `DataTable`, and reconciliation. It should compose public widgets,
not subclass `DataTable` to alter private storage.

### 2. Rebuild the full projected table for every view change

Sort and filter typed `WorkRow` values outside Textual, clear the table, and add
the resulting visible columns and rows in order on every change.

Advantages:

- simplest correctness model;
- arbitrary sorting, including hidden fields and stable tie-breakers;
- one path for filters, column changes, and refreshes; and
- easy pure-function testing.

Tradeoffs:

- repeats population and width measurement;
- resets cursor and scroll state unless restored explicitly; and
- wastes Dashpot's useful incremental refresh implementation.

This is a credible first implementation if measured Issue counts are small. It
is also a useful fallback specifically for schema changes and complex sorts
inside pattern 1.

### 3. A query-backed virtual table widget

Implement a custom `ScrollView` using Textual's line API, retaining only a
viewport/window and asking an external model for row count and visible slices.
Textual uses this rendering style for `DataTable`; the line API can update
portions of a large widget without redrawing it all.
[Textual line API](https://textual.textualize.io/guide/widgets/#line-api)

Advantages:

- true pagination/lazy loading;
- sorting and filtering can be pushed into a database or source query; and
- memory need not grow with all rows.

Tradeoffs:

- Dashpot must implement cursor movement, hit testing, headers, widths, fixed
  columns, styling, caches, messages, accessibility behavior, and invalidation;
- materially larger testing and maintenance surface; and
- premature for the observed Issue-list scale.

Textual 8.2.8's table keeps all cells in `_data` but renders visible lines through
`ScrollView` and several LRU caches.
[8.2.8 table storage and caches](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L734-L778)
[8.2.8 viewport rendering](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L2416-L2499)
This makes a custom virtual widget an architectural fork, not a configuration of
`DataTable`.

## Performance guidance

`DataTable` is render-virtualized, not data-virtualized. Textual renders only
visible lines and caches rows/cells, so scrolling through many rows need not
render the entire table on every frame. Nevertheless, adding, measuring, storing,
filtering, and sorting still operate over the in-memory contents. Textual's own
performance work added row-renderable caching; it improves rendering constants
but does not create a lazy backing-store interface.
[Textual rendering/caching explanation](https://textual.textualize.io/blog/2022/11/20/stealing-open-source-code-from-textual/)
[merged DataTable cache improvement](https://github.com/Textualize/textual/pull/5959)

For Dashpot:

- keep only visible columns in `DataTable`; very wide tables do more formatting
  and measuring work;
- retain the current changed-cell updates for normal refreshes;
- avoid `update_width=True` on columns whose contents cannot affect width;
- use `batch_update()` to coalesce repainting, while recognizing it does not
  change algorithmic cost;
- benchmark incremental removal against clear-and-repopulate when a filter drops
  most rows, because 8.2.8's `remove_row()` rebuilds the remaining row-location
  map for each removal; and
- record row count, visible column count, projection time, and reconcile time
  before considering a custom virtual widget.

[8.2.8 row removal implementation](https://github.com/Textualize/textual/blob/v8.2.8/src/textual/widgets/_data_table.py#L1793-L1830)

## Preferred incremental path

1. Introduce `ColumnSpec`, `WorkRow`, and `TableViewState` with pure tests. Express
   today's six columns, fixed ordering, and open-only rule through those types so
   behavior does not change.
2. Move row projection and reconciliation behind an `IssueTable`-level interface.
   Keep `DashpotApp` responsible for workspace refresh and detail panes.
3. Add header-click and keyboard single-column sort with direction markers. Use
   the native sort for visible cell-based ordering.
4. Add visible state/global-search controls and a visible/total count. Reuse the
   current keyed row diff and selection restoration.
5. Add the modal column chooser and ordered column state. Rebuild only when the
   visible schema changes.
6. Persist view preferences only after the interaction model settles.
7. Benchmark with realistic repositories. Introduce externally sorted row
   rebuilds, pagination, or a custom virtual widget only in response to a measured
   limitation.

This path keeps the current `WorkspaceSnapshot` usable as one input to the table
without making it the table's query interface. The separate question of whether
Dashpot should collect, cache, or query Project data more dynamically can evolve
behind `WorkRow` production without coupling those decisions to Textual widget
internals.
