from __future__ import annotations

import json
import os
import re
import shutil
import sysconfig
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agents import (
    HARNESS_DISPLAY,
    ProcessLookup,
    SessionRecordSummary,
    StaleSessionRecord,
    host_process_lookup,
    session_directory,
    state_directory,
    summarize_session_records,
    validate_session_claim,
)
from .harnesses import (
    SESSION_OVERRIDE_VARIABLE,
    adapter,
    override_claim,
)
from .repository import worktree_root

HOOK_TIMEOUT = 3
# Inline hook definitions live under ``[hooks]`` or ``[[hooks.<Event>]]``.
# Codex also keeps its hook trust ledger under ``[hooks.state...]``, which is
# not a definition and must not trigger the coexistence note.
CONFIG_HOOKS_TABLE = re.compile(r"^\s*\[+\s*hooks\s*(?:\]|\.(?!state\b))", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class HarnessIntegration:
    """One supported harness's opt-in lifecycle hook installation."""

    harness: str
    display: str
    home_name: str
    hooks_file: str
    command_name: str
    events: tuple[str, ...]
    checks_config_toml: bool

    @property
    def default_home(self) -> Path:
        return Path.home() / self.home_name


CODEX = HarnessIntegration(
    harness="codex",
    display="Codex",
    home_name=".codex",
    hooks_file="hooks.json",
    command_name="dashpot-codex-hook",
    events=(
        "SessionStart",
        "UserPromptSubmit",
        "Stop",
        "Interrupt",
        "SessionEnd",
    ),
    checks_config_toml=True,
)

CLAUDE_CODE = HarnessIntegration(
    harness="claude-code",
    display="Claude Code",
    home_name=".claude",
    hooks_file="settings.json",
    command_name="dashpot-claude-code-hook",
    events=("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"),
    checks_config_toml=False,
)

INTEGRATIONS = {spec.harness: spec for spec in (CODEX, CLAUDE_CODE)}

HOOK_COMMAND_NAMES = frozenset(spec.command_name for spec in INTEGRATIONS.values())

CODEX_HOOK_EVENTS = CODEX.events
CLAUDE_CODE_HOOK_EVENTS = CLAUDE_CODE.events


def integration(harness: str) -> HarnessIntegration:
    spec = INTEGRATIONS.get(harness)
    if spec is None:
        raise RuntimeError(f"unsupported harness: {harness}")
    return spec


def resolve_hook_command(spec: HarnessIntegration) -> Path:
    """Locate this environment's installed hook publisher."""
    scripts = Path(sysconfig.get_path("scripts")) / spec.command_name
    if scripts.is_file():
        return scripts
    found = shutil.which(spec.command_name)
    if found:
        return Path(found)
    raise RuntimeError(
        f"cannot locate the {spec.command_name} publisher installed with "
        "Dashpot; reinstall Dashpot and retry"
    )


def install_integration(
    harness: str,
    home: Path | None = None,
    *,
    command_path: Path | None = None,
) -> list[str]:
    """Idempotently register one harness's lifecycle hooks for this user."""
    spec = integration(harness)
    home = home or spec.default_home
    if not home.is_dir():
        raise RuntimeError(
            f"no {spec.display} configuration directory at {home}; install "
            f"and run {spec.display} once before integrating"
        )
    command = command_path or resolve_hook_command(spec)
    path = home / spec.hooks_file
    document = _load_hooks_document(spec, path)
    original = json.dumps(document, sort_keys=True)
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError(
            f'{path} has a non-object top-level "hooks" value; fix the file and retry'
        )
    handler = {
        "type": "command",
        "command": str(command),
        "timeout": HOOK_TIMEOUT,
    }
    for event in spec.events:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = []
        kept, _ours = _split_dashpot_handlers(groups)
        kept.append({"hooks": [dict(handler)]})
        hooks[event] = kept
    messages: list[str] = []
    if json.dumps(document, sort_keys=True) != original:
        _write_json(path, document)
        messages.append(f"installed {spec.display} lifecycle hooks in {path}")
    else:
        messages.append(f"{spec.display} lifecycle hooks already installed in {path}")
    messages.append(f"hook publisher: {command}")
    messages.extend(_config_toml_coexistence_warning(spec, home))
    return messages


def remove_integration(harness: str, home: Path | None = None) -> list[str]:
    """Remove exactly the Dashpot handlers from one harness's hooks."""
    spec = integration(harness)
    home = home or spec.default_home
    path = home / spec.hooks_file
    if not path.is_file():
        return [f"{spec.display} integration is not installed: no {path}"]
    document = _load_hooks_document(spec, path)
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return [f"{spec.display} integration is not installed: no hooks in {path}"]
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
        return [
            f"{spec.display} integration is not installed: no Dashpot hooks in {path}"
        ]
    if not hooks:
        del document["hooks"]
    if set(document) - {"description"}:
        _write_json(path, document)
        return [f"removed the Dashpot hooks from {path}"]
    path.unlink()
    return [f"removed {path}; it contained only the Dashpot hooks"]


def integration_status(
    harness: str,
    home: Path | None = None,
    *,
    state_dir: Path | None = None,
    current: Path | None = None,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Report the observable state of one harness's integration."""
    spec = integration(harness)
    home = home or spec.default_home
    path = home / spec.hooks_file
    messages: list[str] = []
    if not home.is_dir():
        messages.append(f"{spec.display} configuration directory not found: {home}")
        return messages
    if not path.is_file():
        messages.append(f"not installed: no {path}")
    else:
        try:
            document = _load_hooks_document(spec, path)
        except RuntimeError as exc:
            return [str(exc)]
        commands = _installed_commands(document)
        if not commands:
            messages.append(f"not installed: no Dashpot hooks in {path}")
        else:
            events = sorted(commands)
            missing = [event for event in spec.events if event not in commands]
            messages.append(f"installed in {path} for: {', '.join(events)}")
            if missing:
                messages.append(
                    f"missing hook events (run 'dashpot integrate "
                    f"{spec.harness}' to repair): {', '.join(missing)}"
                )
            for command in sorted({c for cs in commands.values() for c in cs}):
                executable = Path(command)
                if not executable.is_file():
                    messages.append(
                        f"hook publisher missing at {command}; run "
                        f"'dashpot integrate {spec.harness}' to repair"
                    )
                elif not os.access(executable, os.X_OK):
                    messages.append(f"hook publisher at {command} is not executable")
                else:
                    messages.append(f"hook publisher: {command}")
    messages.extend(_config_toml_coexistence_warning(spec, home))
    messages.extend(_record_store_status(state_dir, current, lookup))
    messages.extend(_claimed_identity_status(spec, current, lookup, environ))
    return messages


def install_codex_integration(
    codex_home: Path | None = None,
    *,
    command_path: Path | None = None,
) -> list[str]:
    return install_integration("codex", codex_home, command_path=command_path)


def remove_codex_integration(codex_home: Path | None = None) -> list[str]:
    return remove_integration("codex", codex_home)


def codex_integration_status(
    codex_home: Path | None = None,
    *,
    state_dir: Path | None = None,
    current: Path | None = None,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    return integration_status(
        "codex",
        codex_home,
        state_dir=state_dir,
        current=current,
        lookup=lookup,
        environ=environ,
    )


def _record_store_status(
    state_dir: Path | None, current: Path | None, lookup: ProcessLookup
) -> list[str]:
    """Report the session stores visible from here: Project-local and global.

    Each store's records are classified at this moment without being pruned;
    stale records name the session so undelivered SessionEnd hooks can be
    diagnosed here rather than on the workspace Diagnostics surface.
    """
    messages: list[str] = []
    try:
        root = worktree_root(current or Path.cwd())
    except RuntimeError:
        root = None
    if root is not None and (root / ".dashpot" / "config.json").is_file():
        local = session_directory(root)
        messages.extend(
            _describe_records(
                "for this Project", summarize_session_records(local, lookup)
            )
        )
    directory = state_dir or state_directory()
    if directory.is_dir():
        messages.extend(
            _describe_records(
                "outside configured Projects",
                summarize_session_records(directory, lookup),
            )
        )
    else:
        messages.append(
            f"session records outside configured Projects: none ({directory} "
            "does not exist yet)"
        )
    return messages


def _claimed_identity_status(
    spec: HarnessIntegration,
    current: Path | None,
    lookup: ProcessLookup,
    environ: Mapping[str, str] | None,
) -> list[str]:
    """Report the Agent Session Identity this command's environment claims.

    This is the identity a sandboxed ``dashpot work start`` would use, so
    whether it names a live hook record here is what to check when opt-in
    from a sandbox is refused.
    """
    environment = environ if environ is not None else os.environ
    try:
        claim = override_claim(environment)
    except RuntimeError as exc:
        return [f"Agent Session identity claimed here: {exc}"]
    if claim is None or claim.harness != spec.harness:
        claim = adapter(spec.harness).claim_session_identity(environment)
    if claim is None:
        return [
            f"Agent Session identity claimed here: none for {spec.display} "
            f"(Issue opt-in from a sandbox needs one; {SESSION_OVERRIDE_VARIABLE}"
            f"={spec.harness}:<session id> states it explicitly)"
        ]
    prefix = (
        f"Agent Session identity claimed here: {spec.display} session "
        f"{claim.session_id} (from {claim.source})"
    )
    try:
        root = worktree_root(current or Path.cwd())
    except RuntimeError:
        return [f"{prefix}, not validated: not inside a Git worktree"]
    try:
        validated = validate_session_claim(claim, root, lookup)
    except RuntimeError as exc:
        return [f"{prefix}, rejected: {exc}"]
    return [f"{prefix}, confirmed by its {validated.record.outcome} hook record"]


def _describe_records(scope: str, summary: SessionRecordSummary) -> list[str]:
    unknown = f"{summary.unknown} unknown"
    if summary.unknown_reasons:
        reasons = ", ".join(reason for reason, _count in summary.unknown_reasons)
        unknown += f" [{reasons}]"
    messages = [
        f"session records {scope}: {summary.total} in {summary.directory} "
        f"({summary.live} live, {unknown}, {len(summary.stale)} stale, "
        f"{summary.unreadable} unreadable)"
    ]
    messages.extend(f"  stale: {_describe_stale(record)}" for record in summary.stale)
    return messages


def _describe_stale(record: StaleSessionRecord) -> str:
    display = HARNESS_DISPLAY.get(record.harness, record.harness)
    text = (
        f"{display} session {record.session_id} last event "
        f"{record.event or 'unknown'} at {record.last_activity_at or 'unknown time'}, "
    )
    if record.outcome == "ended":
        return text + "ended by SessionEnd (legacy record; pruned on next observation)"
    process = f"pid {record.pid}" if record.pid is not None else "process"
    return text + f"{process} gone (no SessionEnd delivered)"


def _load_hooks_document(spec: HarnessIntegration, path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"hooks": {}}
    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"cannot read {spec.display} hooks at {path}: {exc}; fix or "
            "move the file and retry"
        ) from exc
    if not isinstance(document, dict):
        raise RuntimeError(
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
        if remaining or set(group) - {"hooks"}:
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
    executable = command.split()[0] if command.split() else command
    return Path(executable).name in HOOK_COMMAND_NAMES


def _installed_commands(document: dict[str, Any]) -> dict[str, list[str]]:
    """Map each hook event to the Dashpot commands registered for it."""
    commands: dict[str, list[str]] = {}
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        _, ours = _split_dashpot_handlers(list(groups))
        if ours:
            commands[event] = [
                handler["command"]
                if isinstance(handler.get("command"), str)
                else handler["command"][0]
                for handler in ours
            ]
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


def _write_json(path: Path, document: dict[str, Any]) -> None:
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
