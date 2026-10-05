"""``dashpot init``: declare the current repository a Dashpot Project."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter

from ..core.state_paths import enclosing_checkout
from ..core.working_directory import current_directory
from ..project.init import initialize_project
from ..project.project_config import declared_project_id
from .shared import Timeout, command_outcome, print_lines


def init(
    *,
    markdown: Annotated[
        str | None,
        Parameter(
            help=(
                "PATH: declare a Local Issue Markdown source at this "
                "repository-relative path instead of GitHub Issues"
            )
        ),
    ] = None,
    timeout: Timeout = 10.0,
) -> int:
    """Configure the current repository as a Dashpot Project.

    Writes .dashpot/config.json for the current repository. With a GitHub
    origin remote the Issue Source defaults to GitHub and the durable
    repository identity is resolved through the authenticated gh CLI.
    """
    with command_outcome("init") as outcome:
        current = current_directory()
        outcome.target_path = current
        print_lines(
            initialize_project(current, markdown_path=markdown, timeout=timeout)
        )
        outcome.action = "initialized"
        # The process opened its Event Log before the Project was declared,
        # at the root of the Worktree ``current`` lies in.
        root = enclosing_checkout(current) or current
        outcome.identify(project_id=declared_project_id(root))
    return 0
