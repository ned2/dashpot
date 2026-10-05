"""Install, remove and report OpenCode's managed plugin, and the OpenCode it runs under.

OpenCode loads the plugin in place of hook definitions (ADR 0079). Its
report also names the OpenCode releases on PATH and in the shared service,
other copies of the plugin OpenCode would load, and the other harnesses'
skill copies OpenCode also discovers (ADR 0090).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import override

from pydantic import Field, ValidationError

from ...core.model import Harness
from ...core.pydantic import PublishedModel, describe_validation_error
from ...core.record_store import replace_atomically
from ...core.working_directory import current_directory
from ...core.worktree_paths import same_path
from ..harnesses import OPENCODE_ACCEPTED_VERSION, is_opencode_host_process
from ..processes import (
    ProcessAbsent,
    ProcessLookup,
    ProcessPresent,
    ProcessUnobservable,
)
from .installer import HookInstaller, StatusProbe
from .publisher import publisher_status
from .registry import BundledSkill, HarnessIntegration, integration
from .skill_copies import SKILL_FILE, is_current, is_managed
from .writes import IntegrationError, PendingWrite, Planned, file_mode

# ``opencode --version`` prints ``opencode v2.0.22`` from v2 and a bare
# ``1.18.30`` from v1; the service's registration names a bare release.
OPENCODE_RELEASE = re.compile(
    r"(?:opencode )?v?(?P<release>\d+\.\d+\.\d+\S*)", re.IGNORECASE
)
PLUGIN_MARKER = "// dashpot-managed-plugin: opencode"
PLUGIN_HELPER_PLACEHOLDER = '"__DASHPOT_OPENCODE_HELPER__"'
PLUGIN_HELPER = re.compile(r'^const HELPER = (".*");$', re.MULTILINE)
VERSION_TIMEOUT_SECONDS = 5


class OpenCodePlugin(HookInstaller):
    """The managed plugin OpenCode loads from its configuration directory."""

    @property
    @override
    def noun(self) -> str:
        return "plugin"

    @override
    def plan(
        self,
        spec: HarnessIntegration,
        home: Path,
        command: Path,
        *,
        version_probe: Callable[[], str | None] | None,
    ) -> list[Planned]:
        """The plugin bound to ``command``, after the release on PATH it would run under.

        The plugin is refused while the ``opencode`` on PATH, which
        ``version_probe`` asks by default, is a v1 release (ADR 0090).
        """
        reported = (version_probe or _opencode_version)()
        release = None if reported is None else opencode_release(reported)
        if release is not None and _major(release) == 1:
            raise IntegrationError(
                f"the opencode on PATH is OpenCode {release}, and Dashpot observes "
                f"OpenCode v2 only; install OpenCode {OPENCODE_ACCEPTED_VERSION} "
                "and retry"
            )
        return [
            *_opencode_release_status("OpenCode release on PATH", reported),
            _plan_plugin(spec, home, command),
        ]

    @override
    def remove(self, spec: HarnessIntegration, home: Path) -> str:
        return remove_plugin(spec, home)

    @override
    def missing(self, spec: HarnessIntegration, home: Path) -> tuple[str, ...] | None:
        """None of the plugin's events, or all: it registers every one at once."""
        path = home / spec.hooks_file
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise IntegrationError(
                f"cannot tell whether {spec.display} is integrated: cannot read "
                f"{path}: {exc}; fix or move it and retry"
            ) from exc
        return () if text.startswith(PLUGIN_MARKER) else None

    @override
    def has_update(self, spec: HarnessIntegration, home: Path) -> bool:
        try:
            plugin = _managed_plugin(home / spec.hooks_file)
        except IntegrationError:  # pragma: no cover - read as Dashpot's just before.
            return False
        helper = None if plugin is None else _plugin_helper(plugin)
        return helper is not None and plugin != render_plugin(helper)

    @override
    def status_lines(self, spec: HarnessIntegration, home: Path) -> list[str]:
        return plugin_status(spec, home)

    @override
    def notes(
        self,
        spec: HarnessIntegration,
        home: Path,
        skills: Sequence[tuple[BundledSkill, Path]],
        probe: StatusProbe | None,
    ) -> list[str]:
        messages = _opencode_skill_copies(skills)
        if probe is not None:
            messages.extend(
                _opencode_plugin_copies(
                    home / spec.hooks_file, probe.current, probe.environ
                )
            )
            messages.extend(
                _opencode_runtime_status(
                    probe.version_probe, probe.environ, probe.lookup
                )
            )
        return messages


OPENCODE_PLUGIN = OpenCodePlugin()


def _bundled_plugin() -> Path:
    return Path(__file__).parents[2] / "plugins" / "opencode.js"


def render_plugin(command: Path) -> str:
    """The managed plugin, bound to the helper at ``command``."""
    source = _bundled_plugin().read_text(encoding="utf-8")
    return source.replace(PLUGIN_HELPER_PLACEHOLDER, json.dumps(str(command)), 1)


def _managed_plugin(path: Path) -> str | None:
    """The managed plugin's text at ``path``; ``None`` when there is no file.

    A file that is not Dashpot's is refused rather than overwritten or
    removed: it is the user's plugin of the same name.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise IntegrationError(
            f"cannot read the plugin at {path}: {exc}; move it and retry"
        ) from exc
    if not text.startswith(PLUGIN_MARKER):
        raise IntegrationError(
            f"{path} is not a plugin Dashpot manages; move it and retry"
        )
    return text


def _plan_plugin(spec: HarnessIntegration, home: Path, command: Path) -> Planned:
    """The pending write of the plugin bound to ``command``, unless it is current."""
    path = home / spec.hooks_file
    current = _managed_plugin(path)
    rendered = render_plugin(command)
    if current == rendered:
        return f"{spec.display} plugin already installed in {path}"
    action = "install" if current is None else "update"

    def write() -> str:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            replace_atomically(path, rendered, temporary_prefix=f".{path.name}.")
        except OSError as exc:
            raise IntegrationError(
                f"could not {action} the {spec.display} plugin in {path}: {exc}"
            ) from exc
        verb = "installed" if current is None else "updated"
        return f"{verb} the {spec.display} plugin in {path}"

    return PendingWrite(
        subject=f"the {spec.display} plugin at {path}",
        directories=(path.parent,),
        perform=write,
    )


def remove_plugin(spec: HarnessIntegration, home: Path) -> str:
    """Remove the managed plugin, leaving any other file at its path alone.

    Raises ``IntegrationError`` when the managed plugin cannot be unlinked.
    """
    path = home / spec.hooks_file
    try:
        current = _managed_plugin(path)
    except IntegrationError as exc:
        return f"left {path} unchanged: {exc}"
    if current is None:
        return f"{spec.display} integration is not installed: no {path}"
    try:
        path.unlink()
    except OSError as exc:
        raise IntegrationError(
            f"could not remove the {spec.display} plugin {path}: {exc}"
        ) from exc
    return f"removed the {spec.display} plugin {path}"


def plugin_status(spec: HarnessIntegration, home: Path) -> list[str]:
    """Report whether the managed plugin is installed, current, and bound to a helper."""
    path = home / spec.hooks_file
    try:
        current = _managed_plugin(path)
    except IntegrationError as exc:
        return [f"plugin conflict: {exc}"]
    if current is None:
        return [f"not installed: no {path}"]
    helper = _plugin_helper(current)
    if helper is None:
        return [
            f"plugin at {path} names no hook publisher; run 'dashpot integrate "
            f"{spec.harness}' to repair"
        ]
    messages = [f"plugin installed in {path}"]
    if current != render_plugin(helper):
        messages.append(
            f"plugin update available at {path}; run 'dashpot integrate "
            f"{spec.harness}' to repair"
        )
    messages.extend(publisher_status(spec.harness, str(helper), helper))
    return messages


def _plugin_helper(plugin: str) -> Path | None:
    """The hook publisher a managed plugin's text is bound to, if it names one."""
    bound = PLUGIN_HELPER.search(plugin)
    try:
        return Path(json.loads(bound.group(1))) if bound else None
    except ValueError:
        return None


# The skill directories in the home directory that OpenCode also reads, and
# the harness whose integration writes there by default. OpenCode reads them
# from the home directory whatever ``CLAUDE_CONFIG_DIR`` names.
_OPENCODE_DISCOVERED_SKILLS: tuple[tuple[Harness, Path], ...] = (
    ("claude-code", Path(".claude/skills")),
    ("codex", Path(".agents/skills")),
)


def _opencode_skill_copies(
    destinations: Sequence[tuple[BundledSkill, Path]],
) -> list[str]:
    """Report the other copies of each bundled skill OpenCode also discovers.

    OpenCode reads skills from Claude Code's ``~/.claude`` and the shared
    ``~/.agents`` directories too, and when two share a name it uses either.
    Each harness's integration owns only its own copy, so a copy that
    differs from the one this Dashpot ships is reported for its own harness
    to repair, or to be moved when that harness's integration writes
    elsewhere.
    """
    messages: list[str] = []
    for skill, own in destinations:
        for owner, discovered in _OPENCODE_DISCOVERED_SKILLS:
            directory = Path.home() / discovered / skill.name
            if same_path(directory, own) or not _may_hold_a_skill(directory):
                continue
            if not (is_managed(skill, directory) and is_current(skill, directory)):
                # The owner's integration repairs only the copy it writes,
                # which its configuration variable may put elsewhere.
                spec = integration(owner)
                repair = (
                    f"run 'dashpot integrate {owner}' or move it"
                    if same_path(directory, spec.default_skills_home / skill.name)
                    else "move it"
                )
                messages.append(
                    f"warning: OpenCode also discovers the {skill.label} at "
                    f"{directory}, which differs from this Dashpot's, and may use "
                    f"either; {repair}"
                )
    return messages


def _may_hold_a_skill(directory: Path) -> bool:
    """Whether a directory has a ``SKILL.md``, or cannot be inspected to say."""
    try:
        mode = file_mode(directory / SKILL_FILE)
    except OSError:
        return True
    return mode is not None and stat.S_ISREG(mode)


def _opencode_plugin_copies(
    own: Path, current: Path | None, environ: Mapping[str, str] | None
) -> list[str]:
    """Report other copies of the managed plugin that OpenCode would also load.

    OpenCode loads every ``{plugin,plugins}/*.{js,ts}`` of each configuration
    directory it reads: the global one, every project ``.opencode`` from the
    working directory up to its Worktree, ``~/.opencode``, and
    ``$OPENCODE_CONFIG_DIR``. A second copy, under any name, is another
    plugin in the same server: it shares the first's registry, but may be
    bound to another helper, which then writes whichever events its instances
    admit first (ADR 0090).
    """
    environment = environ if environ is not None else os.environ
    directories = [own.parent.parent]
    if not _enabled(environment.get("OPENCODE_DISABLE_PROJECT_CONFIG")):
        start = (current or current_directory()).resolve()
        for directory in (start, *start.parents):
            directories.append(directory / ".opencode")
            if (directory / ".git").exists():
                break
    directories.append(Path.home() / ".opencode")
    configured = environment.get("OPENCODE_CONFIG_DIR")
    if configured:
        directories.append(Path(configured))
    seen: set[Path] = set()
    messages: list[str] = []
    for directory in directories:
        if directory.resolve() in seen:
            continue
        seen.add(directory.resolve())
        for candidate in sorted(
            path
            for folder in ("plugin", "plugins")
            for pattern in ("*.js", "*.ts")
            for path in (directory / folder).glob(pattern)
        ):
            try:
                managed = candidate.read_text(encoding="utf-8").startswith(
                    PLUGIN_MARKER
                )
            except (OSError, UnicodeDecodeError):
                managed = False
            if managed and not same_path(candidate, own):
                messages.append(
                    f"warning: OpenCode also loads a copy of the Dashpot plugin "
                    f"at {candidate}; each copy may publish through its own "
                    f"helper, so remove it"
                )
    return messages


def _enabled(value: str | None) -> bool:
    """Whether an OpenCode flag variable is set to true."""
    return (value or "").lower() in {"1", "true"}


def _opencode_version() -> str | None:
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


def opencode_release(reported: str) -> str | None:
    """The OpenCode release that ``reported`` names; ``None`` when it names none."""
    match = OPENCODE_RELEASE.fullmatch(reported.strip())
    return None if match is None else str(match.group("release"))


def _major(release: str) -> int:
    return int(release.split(".", 1)[0])


def _opencode_release_status(label: str, reported: str | None) -> list[str]:
    """Report one OpenCode release: accepted, another v2, refused v1, or unknown."""
    if reported is None:
        return [f"{label}: none found"]
    release = opencode_release(reported)
    if release is None:
        return [
            f"{label}: unreadable",
            f"warning: Dashpot cannot read an OpenCode release in {reported!r}, "
            "so cannot tell whether the plugin observes it",
        ]
    if release == OPENCODE_ACCEPTED_VERSION:
        return [f"{label}: {release}, the accepted release"]
    if _major(release) == 1:
        return [
            f"{label}: {release}, refused",
            f"warning: Dashpot observes OpenCode v2 only: under {release} the "
            "plugin publishes nothing and no command can opt in; install "
            f"OpenCode {OPENCODE_ACCEPTED_VERSION} and run 'dashpot integrate opencode'",
        ]
    if _major(release) == 2:
        return [
            f"{label}: {release}",
            f"warning: OpenCode {release} is not the accepted release "
            f"{OPENCODE_ACCEPTED_VERSION}; the plugin observes it, but another "
            "release may change what it observes",
        ]
    return [
        f"{label}: {release}",
        f"warning: OpenCode {release} is not v2, so the plugin observes nothing "
        f"under it; install OpenCode {OPENCODE_ACCEPTED_VERSION}",
    ]


class OpenCodeServiceRegistration(PublishedModel):
    """The shared OpenCode service's registration, as far as Dashpot reads it."""

    version: str
    pid: int = Field(gt=0)


def _opencode_service_file(environ: Mapping[str, str]) -> Path | None:
    """Where OpenCode registers its service; ``None`` when that cannot be known.

    OpenCode takes ``XDG_STATE_HOME`` as it finds it, so a relative value
    names a directory relative to whichever process wrote the registration.
    """
    configured = environ.get("XDG_STATE_HOME")
    if not configured:
        return Path.home() / ".local" / "state" / "opencode" / "service.json"
    if not Path(configured).is_absolute():
        return None
    return Path(configured) / "opencode" / "service.json"


def _opencode_service_status(
    environ: Mapping[str, str], lookup: ProcessLookup
) -> list[str]:
    """Report the running shared service's release, which a client may replace.

    A client of another release replaces the service when it connects, so
    the service can run another release than the one on PATH (ADR 0090). A
    killed service leaves its registration behind, so its pid must still
    be an OpenCode server's.
    """
    path = _opencode_service_file(environ)
    if path is None:
        return [
            "OpenCode service: unknown; XDG_STATE_HOME is relative, so where "
            "OpenCode registers its service depends on the process that wrote it"
        ]
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"OpenCode service: none registered in {path}"]
    except (OSError, UnicodeDecodeError) as exc:
        return [f"OpenCode service: cannot read {path}: {exc}"]
    try:
        registration = OpenCodeServiceRegistration.model_validate_json(raw)
    except ValidationError as exc:
        return [
            f"OpenCode service: cannot read {path}: {describe_validation_error(exc)}"
        ]
    observed = lookup(registration.pid)
    if isinstance(observed, ProcessAbsent):
        return [
            f"OpenCode service: none running; {path} names pid "
            f"{registration.pid}, which has exited"
        ]
    if isinstance(observed, ProcessPresent) and not is_opencode_host_process(
        observed.identity
    ):
        return [
            f"OpenCode service: none running; {path} names pid "
            f"{registration.pid}, which is now another process"
        ]
    if isinstance(observed, ProcessUnobservable):
        running = (
            f"OpenCode service: pid {registration.pid}, registered in {path}, "
            f"could not be observed ({observed.reason})"
        )
    else:
        running = f"OpenCode service: pid {registration.pid}, registered in {path}"
    return [
        running,
        *_opencode_release_status("OpenCode service release", registration.version),
    ]


def _opencode_runtime_status(
    version_probe: Callable[[], str | None] | None,
    environ: Mapping[str, str] | None,
    lookup: ProcessLookup,
) -> list[str]:
    """Report the OpenCode releases and the settings that keep the plugin out."""
    environment = environ if environ is not None else os.environ
    messages = [
        *_opencode_release_status(
            "OpenCode release on PATH", (version_probe or _opencode_version)()
        ),
        *_opencode_service_status(environment, lookup),
    ]
    if _enabled(environment.get("OPENCODE_PURE")):
        messages.append(
            "warning: OPENCODE_PURE is set here; OpenCode started with it, or "
            "with --pure, loads no plugin and publishes nothing"
        )
    return messages
