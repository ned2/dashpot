"""Install, remove and report Dashpot's handlers in a harness's own hooks file.

Codex reads them from ``hooks.json`` and Claude Code from ``settings.json``.
The file is the user's: only Dashpot's handlers are changed, and a file
reached through a link is written where the link leads (ADR 0130).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import stat
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, override

from .installer import HookInstaller, StatusProbe
from .publisher import publisher_status
from .registry import HOOK_COMMAND_NAMES, BundledSkill, HarnessIntegration, hook_label
from .writes import IntegrationError, PendingWrite, Planned

HOOK_TIMEOUT = 3
# Inline hook definitions live under ``[hooks]`` or ``[[hooks.<Event>]]``.
# Codex also keeps its hook trust ledger under ``[hooks.state...]``, which is
# not a definition and must not trigger the coexistence note.
CONFIG_HOOKS_TABLE = re.compile(r"^\s*\[+\s*hooks\s*(?:\]|\.(?!state\b))", re.MULTILINE)


class HooksFile(HookInstaller):
    """Dashpot's handlers in the hooks file the harness reads them from."""

    @property
    @override
    def noun(self) -> str:
        return "hooks"

    @override
    def plan(
        self,
        spec: HarnessIntegration,
        home: Path,
        command: Path,
        *,
        version_probe: Callable[[], str | None] | None,
    ) -> list[Planned]:
        return [_plan_hooks(spec, home, command)]

    @override
    def remove(self, spec: HarnessIntegration, home: Path) -> str:
        return _remove_hooks(spec, home)

    @override
    def missing(self, spec: HarnessIntegration, home: Path) -> tuple[str, ...] | None:
        path = home / spec.hooks_file
        if not path.is_file():
            return None
        commands = _installed_commands(_load_hooks_document(spec, path))
        if not commands:
            return None
        return tuple(label for label in spec.hook_labels if label not in commands)

    @override
    def has_update(self, spec: HarnessIntegration, home: Path) -> bool:
        return False

    @override
    def status_lines(self, spec: HarnessIntegration, home: Path) -> list[str]:
        path = home / spec.hooks_file
        if not path.is_file():
            return [f"not installed: no {path}"]
        commands = _installed_commands(_load_hooks_document(spec, path))
        if not commands:
            return [f"not installed: no Dashpot hooks in {path}"]
        events = sorted(commands)
        missing = [label for label in spec.hook_labels if label not in commands]
        messages = [f"installed in {path} for: {', '.join(events)}"]
        if missing:
            messages.append(
                f"missing hook events (run 'dashpot integrate "
                f"{spec.harness}' to repair): {', '.join(missing)}"
            )
        for command in sorted({c for cs in commands.values() for c in cs}):
            messages.extend(
                publisher_status(spec.harness, command, _hook_executable(command))
            )
        return messages

    @override
    def notes(
        self,
        spec: HarnessIntegration,
        home: Path,
        skills: Sequence[tuple[BundledSkill, Path]],
        probe: StatusProbe | None,
    ) -> list[str]:
        return _config_toml_coexistence_warning(spec, home)


HOOKS_FILE = HooksFile()


def _plan_hooks(spec: HarnessIntegration, home: Path, command: Path) -> Planned:
    """The pending write of the hooks bound to ``command``, unless they are current."""
    path = home / spec.hooks_file
    # A hooks path holding anything but a file would be read as absent and
    # then fail only at the write, after the other destinations are written.
    if path.is_symlink() and not path.exists():
        raise IntegrationError(
            f"cannot install the {spec.display} lifecycle hooks in {path}: the "
            f"link leads to nothing at {path.resolve()}; restore what it names "
            "or move it, and retry"
        )
    if os.path.lexists(path) and not path.is_file():
        raise IntegrationError(
            f"cannot install the {spec.display} lifecycle hooks in {path}: the "
            "path is not a file; move it and retry"
        )
    document = _load_hooks_document(spec, path)
    original = json.dumps(document, sort_keys=True)
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise IntegrationError(
            f'{path} has a non-object top-level "hooks" value; fix the file and retry'
        )
    handler = {
        "type": "command",
        "command": shlex.quote(str(command)),
        "timeout": HOOK_TIMEOUT,
    }
    # One event may carry several subscriptions (a matcher per relocation
    # tool), so its existing Dashpot handlers are cleared once and every
    # group re-added, rather than each subscription clearing the last.
    matchers_by_event: dict[str, list[str | None]] = {}
    for event in spec.events:
        matchers_by_event.setdefault(event, []).append(None)
    for event, matcher in spec.matched_events:
        matchers_by_event.setdefault(event, []).append(matcher)
    for event, matchers in matchers_by_event.items():
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = []
        kept, _ours = _split_dashpot_handlers(groups)
        for matcher in matchers:
            group: dict[str, Any] = {"hooks": [dict(handler)]}
            if matcher is not None:
                group = {"matcher": matcher, **group}
            kept.append(group)
        hooks[event] = kept
    if json.dumps(document, sort_keys=True) == original:
        return f"{spec.display} lifecycle hooks already installed in {path}"

    def write() -> str:
        try:
            _write_json(path, document)
        except OSError as exc:
            raise IntegrationError(
                f"could not install the {spec.display} lifecycle hooks in {path}: {exc}"
            ) from exc
        return f"installed {spec.display} lifecycle hooks in {path}"

    # The hooks are written to the file a link names, so the check is of
    # the directory that file is replaced in.
    target = _link_target(path)
    subject = f"the {spec.display} lifecycle hooks in {path}"
    if target != path:
        subject += f", a link to {target}"
    return PendingWrite(subject=subject, directories=(target.parent,), perform=write)


def _remove_hooks(spec: HarnessIntegration, home: Path) -> str:
    """Remove Dashpot's handlers from the hooks file, and the file if nothing else is left.

    A hooks file reached through a link is never unlinked: the link is the
    user's, so the file it names is rewritten without the hooks instead.
    Raises ``IntegrationError`` when the file cannot be read or changed.
    """
    path = home / spec.hooks_file
    if not path.is_file():
        return f"{spec.display} integration is not installed: no {path}"
    document = _load_hooks_document(spec, path)
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return f"{spec.display} integration is not installed: no hooks in {path}"
    removed = False
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept, ours = _split_dashpot_handlers(groups)
        if ours:
            removed = True
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not removed:
        return (
            f"{spec.display} integration is not installed: no Dashpot hooks in {path}"
        )
    keep_file = bool(hooks or set(document) - {"description", "hooks"})
    try:
        # A link is the user's, so its file is rewritten rather than unlinked.
        if keep_file or path.is_symlink():
            if not hooks:
                del document["hooks"]
            _write_json(path, document)
            return f"removed the Dashpot hooks from {path}"
        path.unlink()
    except OSError as exc:
        raise IntegrationError(
            f"could not remove the Dashpot hooks from {path}: {exc}"
        ) from exc
    return f"removed {path}; it contained only the Dashpot hooks"


def _load_hooks_document(spec: HarnessIntegration, path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"hooks": {}}
    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    # ``ValueError`` holds a file that is not JSON and one that is not UTF-8.
    except (OSError, ValueError) as exc:
        raise IntegrationError(
            f"cannot read {spec.display} hooks at {path}: {exc}; fix or "
            "move the file and retry"
        ) from exc
    if not isinstance(document, dict):
        raise IntegrationError(
            f"{path} must contain a JSON object; fix or move the file and retry"
        )
    return document


def _split_dashpot_handlers(
    groups: list[Any],
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Split one event's matcher groups from the Dashpot handlers inside them."""
    kept: list[Any] = []
    ours: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            kept.append(group)
            continue
        remaining = []
        for handler in group["hooks"]:
            if _is_dashpot_handler(handler):
                ours.append(handler)
            else:
                remaining.append(handler)
        # A group that held only Dashpot handlers matches nothing once they
        # are gone; its matcher is part of the subscription, not user state.
        if remaining or set(group) - {"hooks", "matcher"}:
            preserved = dict(group)
            preserved["hooks"] = remaining
            kept.append(preserved)
    return kept, ours


def _is_dashpot_handler(handler: object) -> bool:
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return False
    command = handler.get("command")
    if isinstance(command, list) and command:
        command = command[0]
    if not isinstance(command, str):
        return False
    # Older installers wrote paths without shell quoting; recognise those
    # whole so rerunning integration can repair their command lines.
    candidates = [command]
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    if words:
        candidates.append(words[0])
    return any(Path(candidate).name in HOOK_COMMAND_NAMES for candidate in candidates)


def _hook_executable(command: str) -> Path:
    """Locate the executable in a current or older installed hook command."""
    raw = Path(command)
    if raw.is_file():
        return raw
    try:
        words = shlex.split(command)
    except ValueError:
        return raw
    return Path(words[0]) if words else raw


def _installed_commands(document: dict[str, Any]) -> dict[str, list[str]]:
    """Map each subscription label to the Dashpot commands registered for it."""
    commands: dict[str, list[str]] = {}
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            _, ours = _split_dashpot_handlers([group])
            if not ours:
                continue
            matcher = group.get("matcher") if isinstance(group, dict) else None
            label = hook_label(event, matcher if isinstance(matcher, str) else None)
            commands.setdefault(label, []).extend(
                handler["command"]
                if isinstance(handler.get("command"), str)
                else handler["command"][0]
                for handler in ours
            )
    return commands


def _config_toml_coexistence_warning(spec: HarnessIntegration, home: Path) -> list[str]:
    if not spec.checks_config_toml:
        return []
    config = home / "config.toml"
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return []
    if CONFIG_HOOKS_TABLE.search(text):
        return [
            f"note: {config} also defines hooks; {spec.display} merges both "
            "layers and warns at startup"
        ]
    return []


def _link_target(path: Path) -> Path:
    """The file a symbolic link at ``path`` names, through every link; else ``path``."""
    return path.resolve() if path.is_symlink() else path


def _write_json(path: Path, document: dict[str, Any]) -> None:
    """Replace the user's JSON configuration at ``path``, keeping what it is.

    The file is the user's: one reached through a link, as a dotfiles
    manager leaves it, is replaced where the link leads, so the link stays,
    and a replaced file keeps its mode. Text outside ASCII is written as
    itself, not escaped (ADR 0130).
    """
    target = _link_target(path)
    try:
        mode: int | None = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        mode = None
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            stream.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
