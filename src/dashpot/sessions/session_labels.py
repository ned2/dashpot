"""Format Agent Session display labels independently of identity."""

from __future__ import annotations


def work_session_label(harness: str, session_id: str, *, pid: int | None) -> str:
    """Label declared Issue work with process evidence or native session identity."""
    return (
        f"{harness} pid {pid}" if pid is not None else f"{harness} session {session_id}"
    )
