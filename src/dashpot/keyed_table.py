"""Selection continuity for the dashboard's keyed DataTables.

Every dashboard list keeps its rows under stable string keys and rebuilds
them on refresh. These helpers carry the cursor across a rebuild: capture
the highlighted row's identity first, then restore it by key when the row
survived and by position when it did not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Container

    from textual.widgets import DataTable


def cursor_row_key(table: DataTable[Any]) -> str:
    """The key of the row under the table's cursor."""
    return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)


def capture_selection(
    table: DataTable[Any], empty_key: str | None = None
) -> tuple[str | None, int]:
    """The cursor's row key and index, or ``empty_key`` when the table is empty."""
    if not table.row_count:
        return empty_key, 0
    return cursor_row_key(table), table.cursor_row


def restore_selection(
    table: DataTable[Any],
    prior_key: str | None,
    prior_index: int,
    keys: Container[str],
) -> str | None:
    """Move the cursor back to the prior row by identity, else by position.

    Returns the key now under the cursor, or nothing when the table has no
    rows to select.
    """
    if not table.row_count:
        return None
    if prior_key is not None and prior_key in keys:
        selected_index = table.get_row_index(prior_key)
    else:
        selected_index = min(prior_index, table.row_count - 1)
    table.move_cursor(row=selected_index, column=0, animate=False)
    return cursor_row_key(table)
