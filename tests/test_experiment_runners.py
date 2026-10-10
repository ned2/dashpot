"""The pinned experiment runners still reach the Dashpot they measure.

A runner under ``scripts/experiments/`` runs only by hand, never in CI, so a
module that moves breaks it silently until the next re-pin (#616). A runner
reads Dashpot through inline ``python -c`` programs and hashes the Dashpot
sources its run exercises: these tests run each program a runner passes as a
plain string, resolve every Dashpot import any of its programs makes, with
the attributes a one-line program reads through an imported module, and
require every source file it names to exist.
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

CHECKOUT = Path(__file__).resolve().parents[1]
EXPERIMENTS = CHECKOUT / "scripts" / "experiments"
SOURCE = CHECKOUT / "src" / "dashpot"
RUNNERS = sorted(EXPERIMENTS.glob("*/run.mjs"))
PYTHON_EXPERIMENTS = sorted(EXPERIMENTS.rglob("*.py"))

# A program a runner passes to Python, the checkout's or an installation's, as
# a double-quoted JavaScript string.
_INLINE_PROGRAM = re.compile(
    r'execFileSync\((?:python|path\.join\([^()]*"python"\)),\s*\["-c",\s*("(?:[^"\\]|\\.)*")'
)
# A Dashpot import in any program a runner embeds, whether in a plain string,
# a template literal or a shell script it writes.
_DASHPOT_IMPORT = re.compile(
    r"\bfrom (dashpot(?:\.\w+)*) import (\w+(?: as \w+)?(?:, \w+(?: as \w+)?)*)"
    r"|\bimport (dashpot(?:\.\w+)*)(?: as (\w+))?"
)
# A source file a runner names: a Dashpot module, plugin or agent definition.
_SOURCE_FILE = re.compile(r'"([\w./-]+\.(?:py|js|md))"')


def inline_programs(runner: str) -> list[str]:
    """Each program a runner passes to Python as a plain string."""
    return [json.loads(literal) for literal in _INLINE_PROGRAM.findall(runner)]


def unresolved_imports(runner: str) -> list[str]:
    """Each Dashpot import in a runner's programs that this checkout cannot satisfy.

    A module imported under an alias must also have each attribute the rest
    of its one-line program reads through that alias, such as the
    publisher's ``h.claude_code_main``.
    """
    imports: list[tuple[str, tuple[str, ...]]] = []
    for match in _DASHPOT_IMPORT.finditer(runner):
        if match[1]:
            names = tuple(name.split(" as ")[0] for name in match[2].split(", "))
            imports.append((match[1], names))
        else:
            rest = runner[match.end() :].split("\n", 1)[0]
            used = re.findall(rf"\b{match[4]}\.(\w+)", rest) if match[4] else []
            imports.append((match[3], tuple(used)))
    return [
        problem for module, names in imports for problem in _unresolved(module, names)
    ]


def unresolved_python_imports(program: str) -> list[str]:
    """Each Dashpot import in a Python experiment that this checkout cannot satisfy."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(program)):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "dashpot"
        ):
            problems += _unresolved(
                node.module, tuple(alias.name for alias in node.names)
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "dashpot":
                    problems += _unresolved(alias.name, ())
    return problems


def _unresolved(module: str, names: tuple[str, ...]) -> list[str]:
    try:
        imported = importlib.import_module(module)
    except ImportError:
        return [module]
    return [f"{module}.{name}" for name in names if not _has(imported, module, name)]


def _has(imported: object, module: str, name: str) -> bool:
    if hasattr(imported, name):
        return True
    try:
        importlib.import_module(f"{module}.{name}")
    except ImportError:
        return False
    return True


def missing_sources(runner: str, directory: Path) -> list[str]:
    """Each source file a runner names that is in neither this checkout nor its directory.

    A path is taken from the checkout's root, from ``src/dashpot``, or from a
    bundled skill's directory, where a runner that hashes a skill's
    reference names it. A bare module name is taken from ``src/dashpot``,
    from ``src/dashpot/sessions``, where most runners map such names, or from
    the runner's own directory. A bare plugin or agent name is a fixture file
    the runner writes, so it is not a source.
    """
    skills = [skill for skill in (SOURCE / "skills").iterdir() if skill.is_dir()]
    missing: list[str] = []
    for name in _SOURCE_FILE.findall(runner):
        if "/" in name:
            places = (
                CHECKOUT / name,
                SOURCE / name,
                *(skill / name for skill in skills),
            )
        elif name.endswith(".py"):
            places = (SOURCE / name, SOURCE / "sessions" / name, directory / name)
        else:
            continue
        if not any(place.is_file() for place in places):
            missing.append(name)
    return missing


def _label(path: Path) -> str:
    return str(path.relative_to(EXPERIMENTS))


INLINE_PROGRAMS = [
    pytest.param(program, id=f"{_label(runner)}-{index}")
    for runner in RUNNERS
    for index, program in enumerate(inline_programs(runner.read_text()))
]


@pytest.mark.parametrize("program", INLINE_PROGRAMS)
def test_inline_program_runs(
    program: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))

    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", RUNNERS, ids=_label)
def test_runner_imports_resolve(runner: Path) -> None:
    assert unresolved_imports(runner.read_text()) == []


@pytest.mark.parametrize("experiment", PYTHON_EXPERIMENTS, ids=_label)
def test_python_experiment_imports_resolve(experiment: Path) -> None:
    assert unresolved_python_imports(experiment.read_text()) == []


@pytest.mark.parametrize("runner", RUNNERS, ids=_label)
def test_runner_sources_exist(runner: Path) -> None:
    assert missing_sources(runner.read_text(), runner.parent) == []


def test_every_subscription_read_is_run() -> None:
    # A change to how runners quote their programs would otherwise leave the
    # guard running none of the reads #616 repaired.
    reading = [
        runner
        for runner in RUNNERS
        if "integration('claude-code')" in runner.read_text()
    ]
    run = [
        runner
        for runner in reading
        if any(
            "integration('claude-code')" in p
            for p in inline_programs(runner.read_text())
        )
    ]

    assert reading
    assert run == reading


def test_a_name_a_module_no_longer_exports_is_reported() -> None:
    runner = """const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import CLAUDE_CODE as c, integration; print(c.events)"]));"""

    assert unresolved_imports(runner) == ["dashpot.sessions.integrate.CLAUDE_CODE"]


def test_a_module_that_moved_is_reported() -> None:
    runner = """writeFileSync(file, `exec '${python}' -c 'import sys; import dashpot.sessions.agents as m'`);"""

    assert unresolved_imports(runner) == ["dashpot.sessions.agents"]


def test_a_function_a_module_no_longer_has_is_reported() -> None:
    runner = """writeFileSync(file, `#!/bin/sh
exec '${python}' -c 'import sys; import dashpot.hook as h; sys.exit(h.renamed_main(h.__name__))'
`);"""

    assert unresolved_imports(runner) == ["dashpot.hook.renamed_main"]


def test_a_python_experiment_import_that_moved_is_reported() -> None:
    program = (
        "from dashpot.sessions.agents import observe_agent_runs\nimport dashpot.hook\n"
    )

    assert unresolved_python_imports(program) == ["dashpot.sessions.agents"]


def test_a_source_that_moved_is_reported(tmp_path: Path) -> None:
    (tmp_path / "helper_probe.py").touch()
    runner = """const sources = ["sessions/hook_publish.py", "sessions/integrate.py", "hook.py", "agents.py",
  "helper_probe.py", "plugins/opencode.js", "dashpot.js", "references/harnesses.md", "references/moved.md"];"""

    assert missing_sources(runner, tmp_path) == [
        "sessions/integrate.py",
        "agents.py",
        "references/moved.md",
    ]


def test_a_program_that_fails_is_seen() -> None:
    runner = """execFileSync("sh", ["-c", "command -v uv"]);
execFileSync(python, ["-c", "from dashpot.sessions.integrate import CLAUDE_CODE"]);"""
    (program,) = inline_programs(runner)

    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, check=False
    )

    assert result.returncode != 0
