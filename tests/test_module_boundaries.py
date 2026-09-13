"""The headless, hook, and Issue-resolution paths load only their own layers."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import dashpot

SOURCE_DIR = Path(dashpot.__file__).parent
# The pane read models: each is a query half whose rendering lives in a
# matching ``*_cells`` module (the Issue table's in ``issue_table`` too).
READ_MODELS = frozenset(
    {"issue_list", "session_list", "branch_list", "worktree_list", "pull_request_list"}
)
# What the CLI, the hook lifecycle and the observation store import; none of
# it needs a terminal.
HEADLESS_MODULES = (
    "dashpot.work",
    "dashpot.worktrees",
    "dashpot.collect",
    "dashpot.cleanup",
    "dashpot.observation_store",
    "dashpot.paged_store",
    "dashpot.markdown_queries",
    *(f"dashpot.{name}" for name in sorted(READ_MODELS)),
)


# A lifecycle hook event runs on every prompt and tool call; resolving an
# Issue Hint serves ``work`` and ``worktree``. Neither observes a Project, so
# neither loads the coordinator, and the hook never loads the GitHub gateway.
LIGHT_PATHS = (
    ("dashpot.hook", ("dashpot.github", "dashpot.collect")),
    ("dashpot.issue_resolution", ("dashpot.collect",)),
)


def assert_import_leaves_out(module: str, absent: tuple[str, ...]) -> None:
    """Import ``module`` in a fresh interpreter and require ``absent`` unloaded."""
    checks = " and ".join(f"{name!r} not in sys.modules" for name in absent)
    probe = f"import sys, {module}; assert {checks}"

    subprocess.run([sys.executable, "-c", probe], check=True)


def test_headless_modules_do_not_load_textual() -> None:
    assert_import_leaves_out(", ".join(HEADLESS_MODULES), ("textual",))


@pytest.mark.parametrize(
    ("module", "absent"), LIGHT_PATHS, ids=[module for module, _ in LIGHT_PATHS]
)
def test_light_paths_do_not_load_observation_or_github(
    module: str, absent: tuple[str, ...]
) -> None:
    assert_import_leaves_out(module, absent)


def private_read_model_imports(path: Path) -> list[str]:
    """``from .<read model> import _name`` statements in one module."""
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ImportFrom) or node.module not in READ_MODELS:
            continue
        found.extend(
            f"{path.name}:{node.lineno} {node.module}.{alias.name}"
            for alias in node.names
            if alias.name.startswith("_")
        )
    return found


@pytest.mark.parametrize(
    "path",
    sorted(path for path in SOURCE_DIR.glob("*.py") if path.stem not in READ_MODELS),
    ids=lambda path: path.stem,
)
def test_no_module_reaches_into_a_read_model_private_name(path: Path) -> None:
    assert private_read_model_imports(path) == []
