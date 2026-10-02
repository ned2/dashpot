"""Keep the record of which OpenCode publisher generation owns a backend's directory.

One OpenCode backend runs one instance of Dashpot's plugin per directory it
serves, and replaces an instance — reloading its configuration, or disposing
of it — without ending the backend. Each plugin instance is one publisher
generation. Its **publisher record**, beside the hook records it publishes to,
holds which generation owns the pairing of backend and directory, the
generations retired from it, the last publication of each session, and the
sessions OpenCode deleted (ADR 0077). Only the active generation publishes,
and only its acknowledgment can corroborate a command's identity claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from ..core.pydantic import PersistedRecord
from ..core.record_store import LockedRecordStore
from .harnesses import PUBLISHER_GENERATION
from .processes import ProcessIdentity, ProcessKey, SessionProcessRecord

PUBLISHER_RECORD_VERSION = 1
# The subdirectory of a hook store holding its publisher records; a store's
# scans read only its top-level ``*.json``, so they never meet these.
PUBLISHERS_DIRECTORY = "opencode"
PUBLISHER_KEY = re.compile(r"^[0-9a-f]{64}$")
# Retired generations and deleted sessions are kept as tombstones, boundedly:
# a generation retires once per plugin instance, and a late publication comes
# within seconds of its retirement, never hundreds of retirements later.
RETIRED_LIMIT = 64
DELETED_LIMIT = 512
WATERMARK_LIMIT = 512
# One plugin instance's opaque identity, drawn before its first publication.
PublisherGeneration = Annotated[str, Field(pattern=PUBLISHER_GENERATION.pattern)]
# A native session status the plugin publishes; OpenCode 1.18.30 has no error
# status, a failed turn ending ``idle`` like any other.
NativeStatus = Literal["busy", "retry", "idle"]


class SessionWatermark(PersistedRecord):
    """The last publication a generation made for one OpenCode session.

    ``status`` is the native status it last accepted, so a repeat is a
    duplicate; ``root`` says whether the session is a root, whose Agent
    Session record the generation has started.
    """

    generation: PublisherGeneration
    sequence: int
    status: NativeStatus | None = None
    root: bool = False


class PublisherRecord(PersistedRecord):
    """Which publisher generation owns one OpenCode backend's directory."""

    version: Literal[1]
    backend: SessionProcessRecord
    directory: str
    active: PublisherGeneration | None = None
    retired: list[PublisherGeneration] = Field(default_factory=list)
    sessions: dict[str, SessionWatermark] = Field(default_factory=dict)
    deleted: list[str] = Field(default_factory=list)

    @property
    def backend_key(self) -> ProcessKey:
        return self.backend.identity.key


def new_publisher_record(backend: ProcessIdentity, directory: Path) -> PublisherRecord:
    """The record of a pairing no generation has registered for yet."""
    return PublisherRecord(
        version=PUBLISHER_RECORD_VERSION,
        backend=SessionProcessRecord.of(backend),
        directory=str(directory),
    )


def publisher_key(backend: ProcessKey, directory: Path) -> str:
    """Name the record of one backend's directory, by the Host Process and the path."""
    pid, started_at = backend
    return hashlib.sha256(f"{pid}\0{started_at}\0{directory}".encode()).hexdigest()


class PublisherStore(LockedRecordStore):
    """The publisher records beside one hook store."""

    def __init__(self, hook_store: Path, *, checkout: Path | None = None) -> None:
        super().__init__(
            hook_store / PUBLISHERS_DIRECTORY,
            PUBLISHER_KEY,
            "OpenCode publisher key is not a digest",
            checkout=checkout,
        )

    def read(self, key: str) -> PublisherRecord | None:
        """The record under ``key``; ``None`` when there is none, or it cannot be read.

        An unreadable record is no ownership at all: nothing it names may
        publish or corroborate a claim until a registration rewrites it.
        """
        try:
            raw = json.loads(self.record_path(key).read_text())
            return PublisherRecord.model_validate(raw)
        except (OSError, ValueError, ValidationError):
            return None

    def write(self, key: str, record: PublisherRecord) -> None:
        """Replace the record under ``key``, keeping its tombstones bounded."""
        bounded = record.model_copy(
            update={
                "retired": record.retired[-RETIRED_LIMIT:],
                "deleted": record.deleted[-DELETED_LIMIT:],
                "sessions": dict(list(record.sessions.items())[-WATERMARK_LIMIT:]),
            }
        )
        self.replace(key, bounded.model_dump(by_alias=True, mode="json"))

    def record_keys(self) -> list[str]:
        """Every record key in the store."""
        return sorted(
            path.stem
            for path in self.directory.glob("*.json")
            if PUBLISHER_KEY.fullmatch(path.stem)
        )


def corroboration_refusal(
    hook_store: Path,
    backend: ProcessIdentity,
    directory: Path,
    generation: str,
    session_id: str,
) -> str | None:
    """Why ``generation`` cannot corroborate ``session_id`` there, or ``None`` when it can.

    It can while it is the active generation of the backend's directory and
    OpenCode has not deleted the session.
    """
    store = PublisherStore(hook_store)
    record = store.read(publisher_key(backend.key, directory))
    if record is None or record.backend_key != backend.key:
        return "no publisher generation is registered for its OpenCode backend"
    if generation in record.retired:
        return "the plugin instance that corroborated it has been retired"
    if record.active != generation:
        return "the plugin instance that corroborated it no longer publishes"
    if session_id in record.deleted:
        return "OpenCode has deleted the session"
    return None
