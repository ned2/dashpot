"""``dashpot worktree`` and ``dashpot branch``: prepare, inspect and clean up Issue work.

``worktree remove`` and ``branch delete`` are each one Cleanup: a read-only
preview, the targets their flags select, then the confirmed removal.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from ..composition import cleanup_protection, run_cleanup
from ..core.command_outcomes import OutcomeNote
from ..core.working_directory import current_directory
from ..repository.cleanup import (
    NO_ACKNOWLEDGEMENT,
    Acknowledgement,
    BranchCleanupRequest,
    CleanupError,
    CleanupPreview,
    CleanupRequest,
    TargetKind,
    WorktreeCleanupRequest,
    describe_cleanup_report,
    parse_despite_subagents,
)
from ..repository.worktrees.create import (
    create_issue_worktree,
    describe_worktree_plan,
)
from ..repository.worktrees.removability import (
    check_worktree,
    describe_removability,
    linked_worktrees,
)
from ..serialization import (
    cleanup_report_document,
    removability_document,
    render_json,
    worktree_plan_document,
)
from .shared import (
    USAGE_EXIT_CODE,
    IssueHint,
    JsonOutput,
    Timeout,
    command_outcome,
    print_lines,
)

worktree = App(
    name="worktree",
    help=(
        "Prepare, inspect, and remove linked Worktrees for Issue work.\n\n"
        "create mutates: one linked Worktree at one path outside every "
        "Worktree of the Project, on one new Branch, never fetching (ADR "
        "0008). remove mutates: one linked Worktree, unforced, after a "
        "read-only preview, and its Branch — locally, at its push remote — "
        "only when asked (ADR 0019, ADR 0054). check "
        "is read-only and removes nothing."
    ),
)


@worktree.command(name="create")
def worktree_create(
    reference: IssueHint,
    /,
    *,
    base: Annotated[
        str | None,
        Parameter(
            help=(
                "REF: the commit to branch from; defaults to origin/HEAD, else "
                "the one local main or master Branch"
            )
        ),
    ] = None,
    branch: Annotated[
        str | None,
        Parameter(
            help=(
                # The help is Markdown: an unescaped ``<…>`` is an HTML tag.
                r"NAME: the new Branch; defaults to \<number\>-\<title-slug\> "
                "(a Local Issue's slug)"
            )
        ),
    ] = None,
    worktree_root: Annotated[
        Path | None,
        Parameter(
            help=(
                "DIR: the parent directory for the Worktree; defaults to "
                "DASHPOT_WORKTREE_ROOT, then the worktree_root setting, then "
                r"the main working tree's sibling \<main\>.worktrees/"
            )
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Parameter(
            show_default=False,
            help="report the path, Branch, base, root, and refusals without creating",
        ),
    ] = False,
    timeout: Timeout = 10.0,
    json_output: JsonOutput = False,
) -> int:
    """Create a linked Worktree on a new Branch for an Issue."""
    with command_outcome("worktree create", dry_run=dry_run) as outcome:
        plan = create_issue_worktree(
            current_directory(),
            reference,
            base=base,
            branch=branch,
            worktree_root_option=worktree_root,
            dry_run=dry_run,
            timeout=timeout,
        )
        outcome.identify(issue_id=plan.issue_id)
        outcome.target_path = Path(plan.path)
        outcome.target_branch = plan.branch
        outcome.refusals = len(plan.refusals)
        if plan.created:
            outcome.action = "created"
        elif not plan.refusals:
            outcome.action = "planned"
    if json_output:
        print(render_json(worktree_plan_document(plan)))
    else:
        print_lines(describe_worktree_plan(plan))
        # Refusals go to stderr straight off the structured field, in the
        # same one-line ``dashpot:`` voice as every other command failure.
        for item in plan.refusals:
            print(f"dashpot: refused: {item}", file=sys.stderr)
    return USAGE_EXIT_CODE if plan.refusals else 0


@worktree.command(name="check")
def worktree_check(
    path: Annotated[
        Path | None,
        Parameter(
            help="PATH: the Worktree to report on; every linked Worktree of the "
            "Repository when omitted",
            show_default=False,
        ),
    ] = None,
    /,
    *,
    timeout: Timeout = 10.0,
    json_output: JsonOutput = False,
) -> int:
    """Report whether a Worktree is removable, and each reason it is not."""
    current = current_directory()
    # The checkouts a Cleanup never removes are never reported removable.
    protected = cleanup_protection()
    if path is not None:
        report = check_worktree(current, path, protected=protected, timeout=timeout)
        if json_output:
            print(render_json(removability_document(report)))
        else:
            print_lines(describe_removability(report))
        return 0
    reports = [
        check_worktree(current, worktree, protected=protected, timeout=timeout)
        for worktree in linked_worktrees(current, timeout=timeout)
    ]
    if json_output:
        print(render_json([removability_document(report) for report in reports]))
    elif not reports:
        print("no linked Worktrees in this Repository")
    else:
        for index, report in enumerate(reports):
            if index:
                print()
            print_lines(describe_removability(report))
    return 0


_DryRun = Annotated[
    bool,
    Parameter(
        show_default=False,
        help="report what would be attempted, in order, without changing anything",
    ),
]


def _cleanup(
    request: CleanupRequest,
    *,
    select: Callable[[CleanupPreview], tuple[str, ...]],
    delete_ignored: bool = False,
    despite_subagents: Acknowledgement = NO_ACKNOWLEDGEMENT,
    dry_run: bool,
    timeout: float,
    json_output: bool,
    outcome: OutcomeNote,
) -> int:
    """Preview, select, perform, and report one Cleanup from this checkout."""
    report = run_cleanup(
        request,
        select=select,
        delete_ignored=delete_ignored,
        despite_subagents=despite_subagents,
        dry_run=dry_run,
        timeout=timeout,
    )
    outcome.refusals = len(report.refusals)
    if report.dry_run:
        outcome.action = None if report.refusals else "previewed"
    elif report.succeeded:
        outcome.action = "removed" if report.kind == "worktree" else "deleted"
    else:
        # A target left in place, or a preview the Repository no longer
        # matches: the Cleanup did not do what was confirmed.
        outcome.incomplete = True
    if json_output:
        print(render_json(cleanup_report_document(report)))
    else:
        print_lines(describe_cleanup_report(report))
        for item in report.refusals:
            print(f"dashpot: refused: {item}", file=sys.stderr)
    if report.dry_run:
        return USAGE_EXIT_CODE if report.refusals else 0
    return 0 if report.succeeded else USAGE_EXIT_CODE


branch = App(
    name="branch",
    help=(
        "Delete Branches after a read-only preview.\n\n"
        "delete mutates: only the refs named by its flags — the local Branch, "
        "the Branch at each named remote — each only at the commit the preview "
        "observed, the remote first, never the Integration Branch or a "
        "checked-out Branch (ADR 0019)."
    ),
)


@branch.command(name="delete")
def branch_delete(
    name: Annotated[str, Parameter(help="NAME: the Branch, as git branch lists it")],
    /,
    *,
    local: Annotated[
        bool,
        Parameter(
            show_default=False,
            help="delete the local Branch refs/heads/NAME, if it is integrated",
        ),
    ] = False,
    remote: Annotated[
        list[str] | None,
        Parameter(
            help=(
                "REMOTE: delete the Branch at this remote (repeatable), leased on "
                "its Remote-Tracking Branch as of the last fetch"
            ),
            show_default=False,
        ),
    ] = None,
    dry_run: _DryRun = False,
    timeout: Timeout = 10.0,
    json_output: JsonOutput = False,
) -> int:
    """Delete the selected refs of a Branch, each at its previewed commit."""
    with command_outcome("branch delete", dry_run=dry_run) as outcome:
        outcome.target_branch = name
        if not local and not remote:
            raise CleanupError(
                "name at least one target to delete: --local, --remote REMOTE"
            )
        current = current_directory()
        # The identities are spelled out rather than picked from the preview
        # so a ref that is not there is refused by name.
        selected = [f"local:refs/heads/{name}"] if local else []
        selected.extend(f"remote:{each}:refs/heads/{name}" for each in remote or ())
        return _cleanup(
            BranchCleanupRequest(current, name),
            select=lambda _preview: tuple(selected),
            dry_run=dry_run,
            timeout=timeout,
            json_output=json_output,
            outcome=outcome,
        )


@worktree.command(name="remove")
def worktree_remove(
    path: Annotated[Path, Parameter(help="PATH: the linked Worktree to remove")],
    /,
    *,
    delete_branch: Annotated[
        bool,
        Parameter(
            show_default=False,
            help=(
                "also delete the Worktree's local Branch, once the Worktree is "
                "gone and only if it is integrated"
            ),
        ),
    ] = False,
    delete_remote_branch: Annotated[
        bool,
        Parameter(
            show_default=False,
            help=(
                "also delete the Worktree's Branch at the remote a plain git push "
                "reaches, first, leased on its Remote-Tracking Branch as of the "
                "last fetch and only if it is integrated"
            ),
        ),
    ] = False,
    delete_ignored: Annotated[
        bool,
        Parameter(
            show_default=False,
            help=(
                "acknowledge that the Worktree's ignored content (.venv, "
                ".dashpot/state, and the like) is deleted with it"
            ),
        ),
    ] = False,
    despite_subagents: Annotated[
        list[str] | None,
        Parameter(
            show_default=False,
            help=(
                "SESSION:AGENT,AGENT: remove despite the sub-agents this session "
                "lists as working, exactly as the preview names them (repeatable, "
                "one per session). A person's own assertion that none of them "
                "works in this Worktree: an agent never passes it. Refused if the "
                "listed sub-agents change, a process runs inside the Worktree, or "
                "the processes inside could not all be checked; no other blocker "
                "is lifted"
            ),
        ),
    ] = None,
    dry_run: _DryRun = False,
    timeout: Timeout = 10.0,
    json_output: JsonOutput = False,
) -> int:
    """Remove a linked Worktree without force, after a read-only preview."""

    def select(preview: CleanupPreview) -> tuple[str, ...]:
        kinds: set[TargetKind] = {"worktree"}
        if delete_branch:
            kinds.add("local-branch")
        if delete_remote_branch:
            kinds.add("remote-branch")
        chosen = [target for target in preview.targets if target.kind in kinds]
        found = {target.kind for target in preview.targets}
        if (delete_branch or delete_remote_branch) and "local-branch" not in found:
            raise CleanupError(f"{path} has no Branch checked out to delete")
        if delete_remote_branch and "remote-branch" not in found:
            raise CleanupError(
                f"{path}'s Branch has no Remote-Tracking Branch for it at the "
                f"remote a plain git push reaches; fetch, or delete it with "
                f"dashpot branch delete --remote"
            )
        return tuple(target.identity for target in chosen)

    with command_outcome("worktree remove", dry_run=dry_run) as outcome:
        current = current_directory()
        outcome.target_path = Path(os.path.abspath(current / path))
        return _cleanup(
            WorktreeCleanupRequest(current, path),
            select=select,
            delete_ignored=delete_ignored,
            despite_subagents=parse_despite_subagents(despite_subagents or ()),
            dry_run=dry_run,
            timeout=timeout,
            json_output=json_output,
            outcome=outcome,
        )
