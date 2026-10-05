"""Define Cleanup requests, targets, and preview evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import computed_field

from ...core.errors import DashpotError
from ...core.model import Harness, IntegrationState, integration_state
from ...core.pydantic import LaxSequence, PublishedModel


# The RuntimeError base predates the DashpotError contract and stays for
# callers outside the package that catch the built-in type.
class CleanupError(DashpotError, RuntimeError):
    """A Cleanup command refused before previewing: a usage-shaped mistake."""


TargetKind = Literal["local-branch", "remote-branch", "worktree"]

BlockerKind = Literal[
    "integration-branch",
    "checked-out",
    "unintegrated",
    "unknown-integration",
    "remote-mapping",
    "push-url",
    "main-worktree",
    "protected",
    "unavailable",
    "dirty",
    "ignored-content",
    "nested-worktree",
    "locked",
    "agent-session",
    "sub-agent",
    "process",
    "agent-run",
    "work-store",
    "unpushed",
    "unmerged",
    "detached",
]


class CleanupBlocker(PublishedModel):
    """One reason a Cleanup target is unavailable, with the command that acts on it.

    A ``sub-agent`` blocker also names its Agent Session and the agent IDs
    it lists as working, the set a person's override acknowledges
    (ADR 0112); every other blocker leaves them empty.
    """

    kind: BlockerKind
    detail: str
    command: str | None = None
    session_id: str | None = None
    harness: Harness | None = None
    agents: LaxSequence[str] = ()


def held_by_blocked_worktree(worktree: str | Path, *, remote: bool) -> CleanupBlocker:
    """The blocker of a Branch a Worktree preview offers while that Worktree cannot go.

    It is the only ``checked-out`` blocker a Sub-agent Override lifts with
    the Worktree, so one function builds it for the preview and for the
    override's comparison: a Branch also in use in another Worktree carries
    another blocker and stays unavailable (ADR 0112, ADR 0129).
    """
    if remote:
        detail = (
            f"its local Branch is checked out at {worktree}, whose removal is blocked"
        )
    else:
        detail = f"checked out at {worktree}, whose removal is blocked"
    return CleanupBlocker(kind="checked-out", detail=detail)


class IntegrationFact(PublishedModel):
    """How one concrete ref stands against the Integration Branch."""

    integration_ref: str | None
    unintegrated_commits: int | None
    content_integrated: bool | None

    @computed_field
    @property
    def state(self) -> IntegrationState:
        return integration_state(self.unintegrated_commits, self.content_integrated)


class CleanupTarget(PublishedModel):
    """Describe one concrete Cleanup target and its deletion evidence.

    ``expected`` is the value confirmation must observe again — a ref's
    commit, or a Worktree's HEAD — before anything is performed. A target
    with ``requires`` can only be selected together with that other target:
    the attached Branch of a Worktree is deletable once the Worktree is gone.
    """

    identity: str
    kind: TargetKind
    label: str
    expected: str
    ref: str | None = None
    remote: str | None = None
    path: str | None = None
    integration: IntegrationFact | None = None
    # Repository FETCH_HEAD time does not prove success at any particular remote.
    observed_at: str | None = None
    requires: str | None = None
    blockers: LaxSequence[CleanupBlocker] = ()
    consequences: LaxSequence[str] = ()

    @computed_field
    @property
    def available(self) -> bool:
        return not self.blockers


class CleanupPreview(PublishedModel):
    """What a Cleanup of one Branch or Worktree could remove, and why not.

    ``fingerprint`` summarises every observed fact the targets rest on;
    confirmation compares it with a fresh preview's and performs nothing when
    they differ. ``ignored`` lists the ignored paths a Worktree removal would
    delete, which a confirmation covers only with ``delete_ignored``.
    ``unchecked_processes`` says why the processes inside a Worktree could
    not all be checked, when they could not (ADR 0104).
    """

    kind: Literal["branch", "worktree"]
    subject: str
    anchor: str
    targets: LaxSequence[CleanupTarget] = ()
    ignored: LaxSequence[str] = ()
    refusals: LaxSequence[str] = ()
    unchecked_processes: str | None = None
    fingerprint: str = ""

    @property
    def selectable(self) -> tuple[CleanupTarget, ...]:
        return tuple(target for target in self.targets if target.available)

    def target(self, identity: str) -> CleanupTarget | None:
        for target in self.targets:
            if target.identity == identity:
                return target
        return None


def disclosed_facts(target: CleanupTarget) -> dict[str, Any]:
    """Every fact a preview discloses about a target, as a confirmation compares it.

    Everything the target carries counts, a field added later included,
    save three exclusions. ``observed_at`` is the Repository's last fetch
    time, which proves nothing about any one remote; what a fetch changed
    shows in ``expected``. A blocker's ``detail`` and ``command`` narrate
    the current evidence of a gate whose ``kind`` counts: a blocked target
    is never performed, so a count, a timestamp, or a pid in that
    narration changing cannot make a confirmation reach anything the
    person did not see, while the gate appearing or going does. The
    sub-agents a ``sub-agent`` blocker lists (its ``session_id``,
    ``harness``, and ``agents``) are the one gate a confirmation can lift,
    and the acknowledgement it lifts them with is compared with them
    instead, by a refusal that names both sets (ADR 0112).
    """
    facts = target.model_dump(mode="json", exclude={"observed_at"})
    facts["blockers"] = [
        blocker.model_dump(
            mode="json",
            exclude={"detail", "command", "session_id", "harness", "agents"},
        )
        for blocker in target.blockers
    ]
    return facts


def fingerprint(preview: CleanupPreview) -> str:
    """Summarise what a preview discloses, which a confirmation must observe again.

    Every preview field counts — its targets by ``disclosed_facts``, its
    ignored paths, refusals, and whether the processes inside were all
    checked — so a confirmation and a retained choice agree on what
    changed (ADR 0019).
    """
    facts = preview.model_dump(mode="json", exclude={"fingerprint", "targets"})
    facts["targets"] = [disclosed_facts(target) for target in preview.targets]
    encoded = json.dumps(facts, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class BranchCleanupRequest:
    """Preview deleting the Branch ``name`` at the Repository of ``anchor``."""

    anchor: Path
    name: str

    @property
    def starting_directory(self) -> Path:
        """Where the Cleanup's Git adapter is rooted: the Repository Anchor."""
        return self.anchor


@dataclass(frozen=True, slots=True)
class WorktreeCleanupRequest:
    """Preview removing the Worktree at ``path`` of the Repository ``current`` is in."""

    current: Path
    path: Path

    @property
    def starting_directory(self) -> Path:
        """Where the Cleanup's Git adapter is rooted: ``current``."""
        return self.current


CleanupRequest = BranchCleanupRequest | WorktreeCleanupRequest
