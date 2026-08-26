# Textual implementation notes for Dashpot

Research date: 2026-08-25. These notes target Textual 8.2.8, the version already
exercised by the framework spike. They are implementation guidance for the first
passive observer slice, not a claim that Textual is permanently locked in.

## Recommended shape

Build one `App` with one long-lived default screen:

```text
DashpotApp
├── Header
├── source-status
├── body
│   ├── queue-pane
│   │   └── DataTable
│   └── detail-pane
│       └── Markdown (or Static)
├── diagnostics
└── Footer
```

Keep the headless `WorkspaceCollector` and its snapshots independent of Textual.
Inject a collector into the app, compose the widget tree once, and update those
widgets in place. `compose()` is Textual's preferred startup mechanism; dynamic
`mount()` is asynchronous and is only guaranteed complete by the next message
handler unless explicitly awaited. The first slice has no need for that extra
lifecycle complexity. [App basics: composing and mounting](https://textual.textualize.io/guide/app/#widgets)

Do not use reactive recomposition for the app body. Recomposing removes and
recreates children, and Textual specifically warns that this resets state in
widgets such as `DataTable`. [Reactivity: recompose](https://textual.textualize.io/guide/reactivity/#recompose)

Use `on_mount()` only for operations which require the table itself to be mounted:
add stable columns and focus it. Start the first refresh and install the timer in
the app's `on_ready()` handler. The implementation tests found that an effectively
initial refresh worker started from the app's mount handler can deliver a row event
before later sibling widgets are queryable; waiting for the ready phase removes
that startup race. Keep construction side-effect free so tests can instantiate the
app without touching GitHub, subprocesses, or the filesystem.

## State ownership and data flow

Use a small amount of app-owned state:

- `snapshot: var[WorkspaceSnapshot | None]`
- `refresh_generation: var[int]`
- `refreshing: var[bool]`
- `selected_row_key: str | None`
- a non-reactive, wholesale-replaced `rows_by_key` lookup for rendering details

`var` retains watchers and other reactive behavior but does not automatically
repaint, which is appropriate when a watcher will update specific widgets.
`reactive` repaints by default. Prefer assigning a new immutable snapshot over
mutating collections; Textual cannot detect in-place mutation unless
`mutate_reactive()` is called. [Reactive and `var` API](https://textual.textualize.io/api/reactive/)

Avoid assigning an initial snapshot in `__init__` if its watcher queries the DOM.
Reactive watchers may run before children are mounted; either assign after mount,
declare the state with `init=False`, or use `set_reactive()` during construction
and explicitly render it in `on_mount()`. [Reactivity: setting without
superpowers](https://textual.textualize.io/guide/reactivity/#setting-reactives-without-superpowers)

The desired flow is:

```text
timer / r binding
       │
       ▼
refresh worker ── immutable WorkspaceSnapshot / failure message ──▶ App
                                                                  │
                                         ┌────────────────────────┼──────────┐
                                         ▼                        ▼          ▼
                                    status/diagnostics       DataTable     detail
                                                                  │
                                                      RowHighlighted message
                                                                  │
                                                                  └──▶ selected_row_key
```

Textual messages are queued and processed by each app/widget's asyncio message
pump. Custom messages are the intended mechanism for coordination, and
`post_message()` is thread-safe. That makes a result message a clean boundary
between a blocking collector and the main-thread UI. [Events and messages](https://textual.textualize.io/guide/events/)

## Refresh concurrency

The collector is synchronous and starts subprocesses, so dispatch it to an
explicitly owned executor from an async worker rather than running it in a
message or timer handler. Textual notes that a
handler doing work longer than a few milliseconds prevents other messages from
being processed. [Workers: concurrency](https://textual.textualize.io/guide/workers/#concurrency)

Use a dedicated worker group:

```python
@work(
    name="workspace refresh",
    group="refresh",
    exclusive=True,
    exit_on_error=False,
)
async def refresh_workspace(self, generation: int) -> None:
    snapshot = await asyncio.get_running_loop().run_in_executor(
        self.refresh_executor, self.collector.refresh
    )
```

Owning the bounded executor gives the app an explicit shutdown point and avoids
coupling test and process shutdown to asyncio's global default executor. Shut it
down from `on_unmount()` with queued work cancelled.

`exclusive=True` cancels previous workers in the same group, so manual and timed
refreshes do not compete to update the display. `exit_on_error=False` is important
for an observer: the Textual default is to exit the app when a worker raises.
[The `work` decorator API](https://textual.textualize.io/api/work/) and [worker
error behavior](https://textual.textualize.io/guide/workers/#worker-errors)

Cancellation is cooperative at the executor boundary. Cancelling the async
worker does not stop a collector call already running in a Python thread, so the
worker must inspect `get_current_worker().is_cancelled`. Consequently:

1. Increment `refresh_generation` on the UI thread before starting each refresh.
2. Run only `collector.refresh()` in the worker.
3. After collection, check `worker.is_cancelled` before posting a result.
4. Include the generation in the result and discard it on the UI thread unless it
   equals the current generation.
5. Keep subprocess timeouts in the collector so shutdown and superseded refreshes
   are bounded even while a thread is inside a command.

Also serialize calls at the stateful workspace-collector boundary. Cancelling a
Textual worker does not terminate its executor call, so a replacement can
otherwise enter the same source adapter while the cancelled generation is still
updating its in-memory last-good cache. Serialization still lets independent
projects fan out inside one generation, while the UI generation check prevents
the completed older result from being accepted.

The generation check is still necessary: a superseded call may finish after its
replacement. Post a custom result message and update all UI state in its handler.

Set the periodic trigger with `set_interval()` and keep the returned `Timer`.
Timers can be paused, resumed, reset, and stopped. Reset the interval after a
manual refresh if an immediate timer follow-up would be surprising. Textual's
timer defaults to skipping events it could not send on time, while the exclusive
worker and generation guard cover overlap after an event has been delivered.
[Timer API](https://textual.textualize.io/api/timer/) and [`set_interval()`
API](https://textual.textualize.io/api/message_pump/#textual.message_pump.MessagePump.set_interval)

On normal app exit, Textual cancels workers tied to the app/DOM node. Still retain
collector command timeouts and cancellation checks because executor work is not
force-cancellable. [Workers: lifetime](https://textual.textualize.io/guide/workers/#worker-lifetime)

## Updating the `DataTable`

Encode the row kind and opaque stable identities into every Textual row key. A
normal Issue row uses globally unique Issue Identity so selection survives a
Project transfer; only an identity-conflict fallback also includes Project
Identity. Project placeholders and Agent Runs use separately tagged encodings.
This prevents opaque identities from colliding across row kinds. Add explicit
stable column keys as well. Textual row keys remain valid when rows move because
of deletion or sorting; coordinates do not.
[DataTable keys](https://textual.textualize.io/widgets/data_table/#keys)

Set `cursor_type="row"`. Arrow navigation then emits `DataTable.RowHighlighted`,
whose message carries both the stable `row_key` and current row coordinate. Drive
the detail pane and selected row identity from that message.
[DataTable cursors and messages](https://textual.textualize.io/widgets/data_table/#cursors)

On each accepted snapshot:

1. Capture the highlighted row key with
   `coordinate_to_cell_key(table.cursor_coordinate)` and remember its index.
2. Build an ordered mapping of stable row key to rendered cell tuple.
3. Within `with app.batch_update():`, remove absent rows, add new rows, and call
   `update_cell(row_key, column_key, value)` only for changed cells.
4. Restore ordering with the table's `sort()` API when the observer's ordering can
   be expressed through its columns.
5. If the prior row key remains, restore it with
   `get_row_index(key)` and `move_cursor(row=...)`. If it disappeared, select the
   nearest surviving index; if there are no rows, clear the detail pane.

`batch_update()` suspends repainting until the batch is complete. `DataTable`
provides keyed `update_cell`, `remove_row`, `get_row_index`, and `move_cursor`
operations for this algorithm. [`App.batch_update()`](https://textual.textualize.io/api/app/#textual.app.App.batch_update),
[`DataTable.update_cell()`](https://textual.textualize.io/widgets/data_table/#update_cell),
and [`DataTable.get_row_index()`](https://textual.textualize.io/widgets/data_table/#get_row_index)

`update_cell(..., update_width=False)` is the default. Use `update_width=True` for
values such as a title which may grow, or columns may remain too narrow. It does
not provide a shrink-to-current-content operation. If arbitrary snapshot order
cannot be reproduced by `sort()`, a first implementation may clear and re-add
rows inside `batch_update()`, then restore selection by stable key. That is less
incremental but remains correct and should be measured before adding ordering
machinery. [DataTable update API](https://textual.textualize.io/widgets/data_table/#update_cell)

Do not use the prototype's current `work:<project-index>:<item-index>` keys. They
identify presentation positions, so a refresh which inserts or reorders work can
silently move the user's selection to another Issue.

## Responsive layout

Prefer Textual 8.2.8's responsive breakpoint classes over imperative
`on_resize()` code:

```python
HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (100, "-wide")]
```

Textual applies the matching class to the screen based on terminal width, allowing
TCSS rules such as `Screen.-wide #body { layout: horizontal; }` and
`Screen.-compact #body { layout: vertical; }`. It also supports vertical
breakpoints. [App breakpoint API](https://textual.textualize.io/api/app/#textual.app.App.HORIZONTAL_BREAKPOINTS)

For the first slice:

- wide terminals: retain the queue/detail horizontal split;
- compact terminals: stack queue over detail or hide the detail behind a binding;
- keep the table horizontally scrollable rather than dynamically destroying
  columns; and
- use fractional dimensions (`fr`) for the panes and an explicit `1fr` height for
  the body/table.

Textual's horizontal layout does not add a scrollbar to an overflowing container
unless `overflow-x: auto` is set. [Layout guide](https://textual.textualize.io/guide/layout/#horizontal)
If a compact mode hides a pane, `display: none` removes it from layout entirely;
`Widget.display` is the Python shortcut. [Display style](https://textual.textualize.io/styles/display/)

Only handle `Resize` directly if the app needs non-style behavior. The event
contains new cell, virtual, container, and optional pixel sizes.
[Resize event](https://textual.textualize.io/events/resize/)

## Loading, errors, and diagnostics

Preserve the last accepted snapshot during refresh. Do not replace a useful stale
queue with a spinner on every interval. On the cold first load only, setting the
table's `loading` reactive temporarily replaces it with Textual's loading
indicator. [Widget loading state](https://textual.textualize.io/guide/widgets/#loading-indicator)

Treat collection problems as observer data:

- source status and age stay visible in the status line;
- per-project/source diagnostics stay in a persistent diagnostics pane;
- stale data remains rendered and visibly marked;
- unexpected worker exceptions preserve the last snapshot and become an explicit
  diagnostic; and
- an error toast may supplement the pane for a failed manual refresh, but must not
  be the only record.

`App.notify()` supports information, warning, and error severities and is
thread-safe, although posting a result message keeps this app's updates in one
place. [`App.notify()`](https://textual.textualize.io/api/app/#textual.app.App.notify)

Use `panic()` only for an unrecoverable invariant violation; it exits and prints
an error. Use `exit(return_code=..., message=...)` for a graceful startup/config
failure. Normal GitHub, Local Issue Markdown, or process-observation failures are recoverable
source diagnostics and should not terminate the TUI. [`panic()` and
`exit()`](https://textual.textualize.io/api/app/#textual.app.App.panic)

## Test plan

Keep collector/read-model tests synchronous and framework-free. Give app tests a
fake collector or an explicit initial snapshot; never make live `gh` or filesystem
calls in routine UI tests.

Use async pytest with `pytest-asyncio`. `App.run_test()` starts a headless app and
returns a `Pilot`; `Pilot.press()` drives bindings and `Pilot.pause()` waits until
pending messages have been processed. [Textual testing guide](https://textual.textualize.io/guide/testing/)

Minimum behavioral coverage:

- cold load, populated, empty, stale, and unavailable snapshots;
- up/down selection changes the detail to the highlighted stable key;
- refresh preserves selection when rows are inserted or reordered;
- removal of the selected row chooses the nearest remaining row;
- an older slow refresh cannot overwrite a newer result;
- a worker exception leaves last-good rows visible and adds a diagnostic;
- `r` refreshes and `q` exits;
- timer and manual refresh share the exclusive group;
- an empty table has a useful detail/empty state; and
- clean exit with a refresh in flight does not hang.

Exercise both initial and live resize behavior. `run_test(size=(width, height))`
sets the initial terminal, while `Pilot.resize_terminal(width, height)` changes it
during the same session. Verify breakpoint class/layout, row selection, and detail
identity at approximately 60×20, 80×24, and 120×32.
[`run_test()` options](https://textual.textualize.io/api/app/#textual.app.App.run_test)
and [`Pilot.resize_terminal()`](https://textual.textualize.io/api/pilot/#textual.pilot.Pilot.resize_terminal)

`run_test()` disables notifications by default; pass `notifications=True` if a
test asserts toast behavior. Its `message_hook` callback can record every delivered
message, which is useful for asserting refresh-result ordering without reaching
into worker internals. [The `run_test()` API](https://textual.textualize.io/api/app/#textual.app.App.run_test)

Add a small number of visual snapshots only after the layout stabilizes. Textual's
official pytest snapshot plugin captures SVG output and supports terminal sizes;
behavioral `Pilot` assertions should remain the primary contract.
[Snapshot testing](https://textual.textualize.io/guide/testing/#snapshot-testing)

## Development and logging

Do not debug with ordinary terminal `print()`, which can overwrite the application.
Use `self.log(...)` / `textual.log`, and install `textual-dev` in the development
dependency group. `textual run --dev` connects to the separate console and live
reloads TCSS. The console can filter `EVENT`, `DEBUG`, `INFO`, `WARNING`, `ERROR`,
`PRINT`, `SYSTEM`, `LOGGING`, and `WORKER` groups. [Textual devtools](https://textual.textualize.io/guide/devtools/)

Log refresh generation, trigger, elapsed time, project counts, and worker terminal
state. Do not log command environments, `GH_TOKEN`, hook payload content beyond
the observer's normalized fields, or other credentials.

Use an external `.tcss` file for the implementation rather than a large inline
`CSS` string. Textual supports one or multiple `CSS_PATH` files, and dev mode live
reloads them. [Textual CSS files](https://textual.textualize.io/guide/CSS/#css-files)

## Packaging and version policy

Pin runtime Textual exactly at `textual==8.2.8` for the first implementation and
commit the project lockfile. That is the exact API exercised by the prototype and
the latest PyPI release as of this research date. PyPI publishes a platform-neutral
`py3-none-any` wheel, requires Python 3.9–3.14, classifies the project as typed and
production/stable, and lists Linux and macOS support. [Textual 8.2.8 on
PyPI](https://pypi.org/project/textual/)

Keep `textual-dev`, pytest, `pytest-asyncio`, and any snapshot plugin in a
development dependency group, not the runtime dependency set. The Textual project
describes `textual-dev` as supplying the development console. [Textual project
metadata](https://pypi.org/project/textual/#dev-console)

Expose a console script for the observer instead of asking users to invoke a
module path. On each Textual upgrade, update the exact pin and lock together, then
run collector unit tests, all headless `Pilot` sizes, selection-preservation and
refresh-race tests, visual snapshots if present, and one live env smoke test. This
makes the framework choice and its upgrade cost explicit and reversible.

## First implementation checklist

1. Promote the headless snapshot/workspace modules out of the spike import hacks
   without changing their public snapshot contract.
2. Create the package, console entry point, `pyproject.toml`, exact Textual pin,
   lockfile, and external TCSS.
3. Compose the long-lived queue/detail/status/diagnostic widgets.
4. Give every table row and column a stable domain key.
5. Implement manual refresh through a named exclusive async-worker group and an
   app-owned executor,
   cancellation check, generation guard, and main-thread result message.
6. Add incremental keyed table reconciliation and selection restoration.
7. Add the periodic timer and cold-load-only loading state.
8. Add wide/compact breakpoint TCSS.
9. Add fake-collector `run_test()` coverage, including resize, race, error, and
   shutdown behavior.
10. Dogfood against `~/env`; only then decide whether visual snapshots or further
    widget extraction are justified.
