"""The headless observation path stays independent of the widget layer."""

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


def test_headless_modules_do_not_load_textual() -> None:
    imports = ", ".join(HEADLESS_MODULES)
    probe = f"import sys, {imports}; assert 'textual' not in sys.modules"

    subprocess.run([sys.executable, "-c", probe], check=True)


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
