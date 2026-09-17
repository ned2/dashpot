"""The headless, hook, and Issue-resolution paths load only their own layers.

The package-level runtime import graph is also acyclic and no module reaches
into another's private names, so the layering ADR 0042 records cannot regress
silently: Python resolves modules, never packages, so a package cycle raises
nothing at import time.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from itertools import pairwise
from pathlib import Path
from typing import TypeGuard

import pytest

import dashpot

SOURCE_DIR = Path(dashpot.__file__).parent
SOURCE_MODULES = sorted(SOURCE_DIR.rglob("*.py"))
# What the CLI, the hook lifecycle and the observation store import; none of
# it needs a terminal.
HEADLESS_MODULES = (
    "dashpot.sessions.work",
    "dashpot.repository.worktrees.create",
    "dashpot.repository.worktrees.removability",
    "dashpot.observation.collect",
    "dashpot.repository.cleanup",
    "dashpot.observation.observation_store",
    "dashpot.observation.paged_store",
    "dashpot.queries.markdown_queries",
    "dashpot.observation",
    "dashpot.observation.keys",
    "dashpot.observation.related_rows",
    "dashpot.observation.list_result",
    "dashpot.observation.issue_list",
    "dashpot.observation.session_list",
    "dashpot.observation.branch_list",
    "dashpot.observation.worktree_list",
    "dashpot.observation.pull_request_list",
)


# A lifecycle hook event runs on every prompt and tool call; resolving an
# Issue Hint serves ``work`` and ``worktree``. Neither observes a Project, so
# neither loads the coordinator, and the hook never loads the GitHub gateway.
# Composition wires the headless entry points, so it loads neither the CLI
# nor Textual.
LIGHT_PATHS = (
    ("dashpot.composition", ("dashpot.cli", "textual", "dashpot.ui")),
    ("dashpot.repository.cleanup", ("dashpot.repository.worktrees.create",)),
    (
        "dashpot.repository.worktrees.removability",
        ("dashpot.repository.worktrees.create",),
    ),
    ("dashpot.hook", ("dashpot.github.github", "dashpot.observation.collect")),
    ("dashpot.issues.issue_resolution", ("dashpot.observation.collect",)),
)


def assert_import_leaves_out(module: str, absent: tuple[str, ...]) -> None:
    """Import ``module`` in a fresh interpreter and require ``absent`` unloaded."""
    checks = " and ".join(f"{name!r} not in sys.modules" for name in absent)
    probe = f"import sys, {module}; assert {checks}"

    subprocess.run([sys.executable, "-c", probe], check=True)


def test_headless_modules_do_not_load_textual() -> None:
    assert_import_leaves_out(", ".join(HEADLESS_MODULES), ("textual", "dashpot.ui"))


@pytest.mark.parametrize(
    ("module", "absent"), LIGHT_PATHS, ids=[module for module, _ in LIGHT_PATHS]
)
def test_light_paths_leave_unrelated_modules_unloaded(
    module: str, absent: tuple[str, ...]
) -> None:
    assert_import_leaves_out(module, absent)


def module_name(path: Path) -> str:
    """The dotted name of one shipped module; a package initializer is its package."""
    parts = path.relative_to(SOURCE_DIR.parent).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def package_of(module: str) -> str:
    """The ADR 0042 package owning a module; root modules form their own layer."""
    parts = module.split(".")
    return parts[1] if len(parts) > 2 else "dashpot"


def dashpot_imports(
    path: Path, *, runtime_only: bool
) -> Iterator[tuple[int, str, list[str]]]:
    """Every ``dashpot`` import one module states, resolved to a dotted target.

    An import under ``if TYPE_CHECKING:`` never runs, so ``runtime_only``
    leaves it out; one inside a function body stays, since it runs when the
    function does.
    """
    module = module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]

    def walk(nodes: Iterable[ast.AST]) -> Iterator[tuple[int, str, list[str]]]:
        for node in nodes:
            if runtime_only and _guards_type_checking(node):
                yield from walk(node.orelse)
                continue
            yield from _import_edges(node, package)
            yield from walk(ast.iter_child_nodes(node))

    yield from walk([ast.parse(path.read_text(encoding="utf-8"))])


def _guards_type_checking(node: ast.AST) -> TypeGuard[ast.If]:
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "TYPE_CHECKING"
    )


def _import_edges(node: ast.AST, package: str) -> Iterator[tuple[int, str, list[str]]]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] == "dashpot":
                yield node.lineno, alias.name, []
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            base = package.split(".")[: len(package.split(".")) - node.level + 1]
            target = ".".join([*base, node.module] if node.module else base)
        else:
            target = node.module or ""
        if target.split(".")[0] == "dashpot":
            yield node.lineno, target, [alias.name for alias in node.names]


def package_edges() -> dict[tuple[str, str], list[str]]:
    """The runtime import edges between packages, each with the sites that draw it."""
    modules = {module_name(path) for path in SOURCE_MODULES}
    edges: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in SOURCE_MODULES:
        source = package_of(module_name(path))
        for line, target, names in dashpot_imports(path, runtime_only=True):
            # ``from dashpot.pkg import module`` names the module in the alias.
            candidates = [f"{target}.{name}" for name in names] or [target]
            for candidate in candidates:
                imported = candidate
                while imported not in modules and "." in imported:
                    imported = imported.rpartition(".")[0]
                destination = package_of(imported)
                if destination != source:
                    edges[source, destination].append(
                        f"{path.relative_to(SOURCE_DIR)}:{line} -> {candidate}"
                    )
    return edges


def package_cycles(edges: dict[tuple[str, str], list[str]]) -> list[list[str]]:
    """Every elementary cycle the package edges close, as the packages along it."""
    successors: dict[str, set[str]] = defaultdict(set)
    for source, destination in edges:
        successors[source].add(destination)
    cycles: list[list[str]] = []
    finished: set[str] = set()
    trail: list[str] = []

    def visit(package: str) -> None:
        trail.append(package)
        for successor in sorted(successors[package]):
            if successor in trail:
                cycles.append([*trail[trail.index(successor) :], successor])
            elif successor not in finished:
                visit(successor)
        trail.pop()
        finished.add(package)

    for package in sorted(successors):
        if package not in finished:
            visit(package)
    return cycles


def test_the_package_import_graph_is_acyclic() -> None:
    edges = package_edges()

    cycles = package_cycles(edges)

    sites = [
        site
        for cycle in cycles
        for source, destination in pairwise(cycle)
        for site in edges[source, destination]
    ]
    assert cycles == [], "\n".join([*(" -> ".join(cycle) for cycle in cycles), *sites])


def test_core_imports_no_other_package() -> None:
    edges = package_edges()

    assert [edge for edge in edges if edge[0] == "core"] == []


def private_imports(path: Path) -> list[str]:
    """``from <dashpot module> import _name`` statements in one module."""
    return [
        f"{path.name}:{line} {target}.{name}"
        for line, target, names in dashpot_imports(path, runtime_only=False)
        for name in names
        if name.startswith("_")
    ]


@pytest.mark.parametrize(
    "path", SOURCE_MODULES, ids=lambda path: str(path.relative_to(SOURCE_DIR))
)
def test_no_module_imports_a_private_name_from_another(path: Path) -> None:
    assert private_imports(path) == []
