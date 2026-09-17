"""Define Cleanup requests, targets, and preview evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import computed_field

from ...core.model import IntegrationState, integration_state
from ...core.pydantic import LaxSequence, PublishedModel

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
    "locked",
    "agent-session",
    "agent-run",
    "work-store",
    "unpushed",
    "unmerged",
    "detached",
]


class CleanupBlocker(PublishedModel):
    """One reason a Cleanup target is unavailable, with the command that acts on it."""

    kind: BlockerKind
    detail: str
    command: str | None = None


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
    delete, which a person acknowledges separately.
    """

    kind: Literal["branch", "worktree"]
    subject: str
    anchor: str
    targets: LaxSequence[CleanupTarget] = ()
    ignored: LaxSequence[str] = ()
    refusals: LaxSequence[str] = ()
    fingerprint: str = ""

    @property
    def selectable(self) -> tuple[CleanupTarget, ...]:
        return tuple(target for target in self.targets if target.available)

    def target(self, identity: str) -> CleanupTarget | None:
        for target in self.targets:
            if target.identity == identity:
                return target
        return None


@dataclass(frozen=True, slots=True)
class BranchCleanupRequest:
    """Preview deleting the Branch ``name`` at the Repository of ``anchor``."""

    anchor: Path
    name: str


@dataclass(frozen=True, slots=True)
class WorktreeCleanupRequest:
    """Preview removing the Worktree at ``path`` of the Repository ``current`` is in."""

    current: Path
    path: Path


CleanupRequest = BranchCleanupRequest | WorktreeCleanupRequest
