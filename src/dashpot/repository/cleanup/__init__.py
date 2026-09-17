"""Expose Cleanup preview and confirmed execution through one public seam."""

from ..worktrees.removability import CleanupBlocker as CleanupBlocker
from .adapter import CleanupAdapter as CleanupAdapter
from .adapter import GitCleanupAdapter as GitCleanupAdapter
from .perform import (
    CHANGED_SINCE_PREVIEW as CHANGED_SINCE_PREVIEW,
)
from .perform import (
    CleanupConfirmation as CleanupConfirmation,
)
from .perform import CleanupError as CleanupError
from .perform import CleanupReport as CleanupReport
from .perform import Outcome as Outcome
from .perform import TargetResult as TargetResult
from .perform import cleanup_git as cleanup_git
from .perform import (
    describe_cleanup_report as describe_cleanup_report,
)
from .perform import perform_cleanup as perform_cleanup
from .preview import (
    describe_cleanup_preview as describe_cleanup_preview,
)
from .preview import inspect_cleanup as inspect_cleanup
from .targets import (
    BranchCleanupRequest as BranchCleanupRequest,
)
from .targets import CleanupPreview as CleanupPreview
from .targets import CleanupRequest as CleanupRequest
from .targets import CleanupTarget as CleanupTarget
from .targets import IntegrationFact as IntegrationFact
from .targets import TargetKind as TargetKind
from .targets import (
    WorktreeCleanupRequest as WorktreeCleanupRequest,
)
