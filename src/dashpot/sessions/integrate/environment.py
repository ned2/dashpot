"""What one ``integrate`` command takes from the process it runs in.

An ``IntegrationEnvironment`` carries the bundled skills and agents the
command installs, the probe of the OpenCode release on PATH, the process
lookup ``--status`` observes with, and the environment variables every
configuration directory and skill home is resolved from.
``PROCESS_ENVIRONMENT`` is the process's own, which every install, refresh,
remove, status and presence entry point takes by default; a test passes its
own value in its place.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..processes import ProcessLookup, host_process_lookup
from .registry import BUNDLED_AGENTS, BUNDLED_SKILLS, BundledAgent, BundledSkill

VERSION_TIMEOUT_SECONDS = 5


def opencode_version() -> str | None:
    """The version the ``opencode`` on PATH reports, or ``None`` when it cannot say."""
    found = shutil.which("opencode")
    if found is None:
        return None
    try:
        completed = subprocess.run(
            [found, "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    version = completed.stdout.strip()
    return version if completed.returncode == 0 and version else None


def _process_variables() -> Mapping[str, str]:
    # The live mapping rather than a copy: the process's own environment is
    # read as it stands when a directory is resolved, not when Dashpot loaded.
    return os.environ


@dataclass(frozen=True, slots=True)
class IntegrationEnvironment:
    """What one ``integrate`` command installs, and what it asks of its host.

    Nothing in ``integrate`` reads these from anywhere else, so one value
    decides every directory a command resolves and everything it observes
    of the host beyond the configuration directory it is given.
    """

    skills: tuple[BundledSkill, ...] = BUNDLED_SKILLS
    agents: tuple[BundledAgent, ...] = BUNDLED_AGENTS
    # What ``opencode --version`` reports for the release on PATH; ``None``
    # when there is none, or it cannot say (ADR 0090).
    version_probe: Callable[[], str | None] = opencode_version
    lookup: ProcessLookup = host_process_lookup
    # The variables each harness's configuration directory and skill home
    # are resolved from (ADR 0130), and the Agent Session Identity and
    # OpenCode settings ``--status`` reports.
    environ: Mapping[str, str] = field(default_factory=_process_variables)


PROCESS_ENVIRONMENT = IntegrationEnvironment()
