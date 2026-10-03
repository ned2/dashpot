"""Keep the Publisher Record of one hook store's OpenCode sessions.

OpenCode v2 orders each session's events by the session's own durable
sequence, whichever server, plugin instance or generation saw them. The
**Publisher Record** beside a hook store keeps, for every OpenCode session
published there, the highest sequence it accepted and, for a child session,
the root it is recorded with, and the sessions OpenCode deleted (ADR 0090).
A publication at or below a session's sequence is stale, and one for a
deleted session is refused. A Publisher Generation names one plugin
instance, but owns nothing here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from ..core.pydantic import PersistedRecord
from ..core.record_store import LockedRecordStore
from .harnesses import HookSessionIdentity

PUBLISHER_RECORD_VERSION = 2
# The subdirectory of a hook store holding its Publisher Record; a store's
# scans read only its top-level ``*.json``, so they never meet it.
PUBLISHERS_DIRECTORY = "opencode"
PUBLISHER_KEY = "publisher"
# Sessions and deletions are kept boundedly, oldest first out: a late
# publication comes within seconds of the one that superseded it, never
# hundreds of sessions later.
SESSION_LIMIT = 1024
DELETED_LIMIT = 512
# One plugin instance's opaque identity, drawn when the instance is set up.
PUBLISHER_GENERATION = re.compile(r"^[A-Za-z0-9-]{1,64}$")
PublisherGeneration = Annotated[str, Field(pattern=PUBLISHER_GENERATION.pattern)]
# Why a root session reads unknown while its Host Process runs: the Host
# Process's last live plugin instance was cleaned up, so nothing observes the
# session and the end of its execution may have reached no instance (ADR 0080,
# ADR 0090).
NO_LIVE_INSTANCE = "opencode-no-live-instance"


class SessionEntry(PersistedRecord):
    """What one hook store last accepted for one OpenCode session.

    ``root`` names the root session a child is recorded with, and is absent
    for a root session.
    """

    sequence: int = Field(ge=0)
    root: HookSessionIdentity | None = None


class PublisherRecord(PersistedRecord):
    """The OpenCode sessions one hook store has accepted publications for."""

    version: Literal[2]
    sessions: dict[str, SessionEntry] = Field(default_factory=dict)
    deleted: list[str] = Field(default_factory=list)

    def refuses(self, session_id: str, root: str) -> bool:
        """Whether OpenCode deleted the session, or the root it is recorded with."""
        return session_id in self.deleted or root in self.deleted


def new_publisher_record() -> PublisherRecord:
    """The record of a hook store no OpenCode publication has reached yet."""
    return PublisherRecord(version=PUBLISHER_RECORD_VERSION)


class PublisherStore(LockedRecordStore):
    """The Publisher Record beside one hook store, under its own lock.

    Its lock is taken before any hook record lock, never after, so a
    publication's check, hook record writes and update are one ordered step.
    """

    def __init__(self, hook_store: Path, *, checkout: Path | None = None) -> None:
        super().__init__(
            hook_store / PUBLISHERS_DIRECTORY,
            re.compile(rf"^{PUBLISHER_KEY}$"),
            "OpenCode Publisher Record key is fixed",
            checkout=checkout,
        )

    def read(self) -> PublisherRecord:
        """The store's record; a fresh one when there is none, or it cannot be read.

        An unreadable record loses only its sequences and deletions: the
        next publication of each session is accepted and corrects its state.
        """
        try:
            raw = json.loads(self.record_path(PUBLISHER_KEY).read_text())
            return PublisherRecord.model_validate(raw)
        except (OSError, ValueError, ValidationError):
            return new_publisher_record()

    def write(self, record: PublisherRecord) -> None:
        """Replace the store's record, keeping its sessions and deletions bounded."""
        bounded = record.model_copy(
            update={
                "deleted": record.deleted[-DELETED_LIMIT:],
                "sessions": dict(list(record.sessions.items())[-SESSION_LIMIT:]),
            }
        )
        self.replace(PUBLISHER_KEY, bounded.model_dump(by_alias=True, mode="json"))


def recorded_root(hook_store: Path, session_id: str) -> str | None:
    """The root session a child OpenCode session is recorded with in a hook store."""
    entry = PublisherStore(hook_store).read().sessions.get(session_id)
    return None if entry is None else entry.root


def deleted_session(hook_store: Path, session_id: str) -> bool:
    """Whether a hook store's Publisher Record holds OpenCode's deletion of a session."""
    return session_id in PublisherStore(hook_store).read().deleted
