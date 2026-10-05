"""Check every destination ``integrate`` writes before writing any, and make each.

It holds the errors that refuse an installation or removal, or report one
left incomplete (ADR 0110, ADR 0130).
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import override

from ...core.errors import DashpotError
from ...core.model import Harness


class IntegrationError(DashpotError):
    """An installation or removal of an integration refused, or one left incomplete."""


class IncompleteIntegrationError(IntegrationError):
    """An installation or removal that did every step it could, past those it could not.

    Its message names each step that failed; ``messages`` reports what the
    command did, as a complete one's return value would (ADR 0110,
    ADR 0130).
    """

    def __init__(
        self, harness: Harness, failures: Sequence[str], messages: Sequence[str]
    ) -> None:
        super().__init__(f"{'; '.join(failures)}; {self.remainder(harness)}")
        self.messages = tuple(messages)

    @staticmethod
    def remainder(harness: Harness) -> str:
        """What became of the rest of the integration, and the rerun that finishes it."""
        return (
            "the rest of the integration is written, and rerunning "
            f"'dashpot integrate {harness}' once that is fixed finishes it"
        )


class IncompleteRemovalError(IncompleteIntegrationError):
    """A removal that removed everything of Dashpot's it could, past what it could not.

    Its message names each step that failed; ``messages`` reports what the
    removal did, as a complete one's return value would (ADR 0130).
    """

    @override
    @staticmethod
    def remainder(harness: Harness) -> str:
        """What became of the rest of the integration, and the rerun that finishes it."""
        return (
            "the rest of the integration is removed, and rerunning "
            f"'dashpot integrate {harness} --remove' once that is fixed finishes it"
        )


@dataclass(frozen=True, slots=True)
class PendingWrite:
    """One destination ``integrate`` changes, checked before any is written."""

    # A refusal names the destination, such as "the Dashpot Issue work skill
    # at <path>", so one error can list every destination refused.
    subject: str
    # A file is replaced by renaming a temporary beside it, and removed by
    # unlinking it, so the directories alone decide whether the write can be
    # made, whatever the files' own modes.
    directories: tuple[Path, ...]
    # Deferred, so nothing is written until every destination is checked;
    # raises ``IntegrationError``.
    perform: Callable[[], str]
    # Why the write is refused whatever its directories allow, found while
    # planning it, such as a skill file whose directory a link takes
    # outside the copy.
    blocked: str | None = None

    def refusal(self) -> str | None:
        """Why this write cannot be made; ``None`` when every directory allows it."""
        if self.blocked is not None:
            return f"cannot install {self.subject}: {self.blocked}"
        for directory in self.directories:
            reason = _unwritable(directory)
            if reason is not None:
                return f"cannot install {self.subject}: {reason}"
        return None


# What an installation plans: a line to report as it is, or a write to make.
Planned = str | PendingWrite


def write_planned(harness: Harness, planned: Sequence[Planned]) -> list[str]:
    """Check every pending write, then make each, carrying on past one that fails.

    Nothing is written while any destination is refused, so a destination
    Dashpot cannot write leaves the installation as it was. A check can pass
    and its write still fail, as when the destination changes in between or
    a filesystem refuses only the write; the others are written regardless,
    and every failure is named together once they are (ADR 0110).
    """
    refusals = [
        refusal
        for item in planned
        if isinstance(item, PendingWrite) and (refusal := item.refusal()) is not None
    ]
    if refusals:
        raise IntegrationError("; ".join(refusals))
    messages: list[str] = []
    failures: list[str] = []
    for item in planned:
        if isinstance(item, str):
            messages.append(item)
            continue
        try:
            messages.append(item.perform())
        except IntegrationError as exc:
            failures.append(str(exc))
    if failures:
        raise IncompleteIntegrationError(harness, failures, messages)
    return messages


def _unwritable(directory: Path) -> str | None:
    """Why a file cannot be written in ``directory``, or ``None`` when it can be.

    A directory not there yet is created inside its nearest existing
    ancestor, so that ancestor is the one checked. The check reads
    permissions alone: a write it passes may still fail.
    """
    for candidate in (directory, *directory.parents):
        try:
            mode = file_mode(candidate)
        except OSError as exc:
            return f"could not inspect {candidate}: {exc}; fix it and retry"
        if mode is None:
            continue
        if not stat.S_ISDIR(mode):
            return f"{candidate} is not a directory; move it and retry"
        if not os.access(candidate, os.W_OK | os.X_OK):
            return f"{candidate} is not writable; make it writable and retry"
        return None
    return None  # pragma: no cover - the filesystem root always exists.


def file_mode(path: Path) -> int | None:
    """A path's mode, or ``None`` when nothing is there; raises any other ``OSError``.

    Only absence is absence: ``Path.exists`` reads a path it may not search
    as absent on some Python releases, which would report a copy it cannot
    inspect as missing.
    """
    try:
        return path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return None
