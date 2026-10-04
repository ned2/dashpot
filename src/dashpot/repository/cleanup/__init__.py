"""Expose Cleanup preview, default and retained choices, and confirmed execution through one seam."""

from .adapter import CleanupAdapter as CleanupAdapter
from .adapter import GitCleanupAdapter as GitCleanupAdapter
from .obstacles import counted as counted
from .override import DESPITE_SUBAGENTS_FLAG as DESPITE_SUBAGENTS_FLAG
from .override import NO_ACKNOWLEDGEMENT as NO_ACKNOWLEDGEMENT
from .override import Acknowledgement as Acknowledgement
from .override import ListedSubagents as ListedSubagents
from .override import lifted as lifted
from .override import listed_by as listed_by
from .override import listed_in as listed_in
from .override import override_offer as override_offer
from .override import (
    parse_despite_subagents as parse_despite_subagents,
)
from .override import worktree_target as worktree_target
from .perform import (
    CHANGED_SINCE_PREVIEW as CHANGED_SINCE_PREVIEW,
)
from .perform import (
    CleanupConfirmation as CleanupConfirmation,
)
from .perform import CleanupReport as CleanupReport
from .perform import Outcome as Outcome
from .perform import TargetResult as TargetResult
from .perform import cleanup_git as cleanup_git
from .perform import (
    describe_cleanup_report as describe_cleanup_report,
)
from .perform import perform_cleanup as perform_cleanup
from .preview import SUB_AGENT_SCOPE as SUB_AGENT_SCOPE
from .preview import (
    describe_cleanup_preview as describe_cleanup_preview,
)
from .preview import inspect_cleanup as inspect_cleanup
from .preview import sub_agent_scope as sub_agent_scope
from .preview import unchecked_processes_note as unchecked_processes_note
from .selection import default_choices as default_choices
from .selection import primary_target as primary_target
from .selection import retained_choices as retained_choices
from .targets import (
    BranchCleanupRequest as BranchCleanupRequest,
)
from .targets import CleanupBlocker as CleanupBlocker
from .targets import CleanupError as CleanupError
from .targets import CleanupPreview as CleanupPreview
from .targets import CleanupRequest as CleanupRequest
from .targets import CleanupTarget as CleanupTarget
from .targets import IntegrationFact as IntegrationFact
from .targets import TargetKind as TargetKind
from .targets import (
    WorktreeCleanupRequest as WorktreeCleanupRequest,
)
