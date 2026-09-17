"""Separate Agent Session identity from shared host-process evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from ..core.model import Harness
from .processes import ProcessKey


@dataclass(frozen=True, slots=True)
class SessionEvidence:
    """Compare validated session facts without treating a process as ownership."""

    harness: Harness
    session_id: str | None
    process_key: ProcessKey | None = None

    def match(
        self, other: SessionEvidence
    ) -> Literal["same", "different", "unresolved"]:
        """Match native identities and retain uncertainty for unnamed records."""
        if self.harness != other.harness:
            return "different"
        if self.session_id is not None and other.session_id is not None:
            return "same" if self.session_id == other.session_id else "different"
        return "unresolved"

    @property
    def native_key(self) -> tuple[str, str] | None:
        """Return the full native identity independently of its storage name."""
        if self.session_id is None:
            return None
        return self.harness, self.session_id

    def storage_key(self) -> str:
        """Name a new named run with a digest whose stored identity is checked."""
        if self.session_id is None:
            raise ValueError(
                "a new Agent Run requires a confirmed Agent Session Identity"
            )
        return session_storage_key(self.harness, self.session_id)


def session_storage_key(harness: str, session_id: str) -> str:
    """Name the record of a native identity, whatever harness it claims."""
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    return f"{harness}-session-{digest}"
