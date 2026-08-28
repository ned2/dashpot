from __future__ import annotations

import json
import os
import re
import shutil
import sysconfig
import tempfile
from pathlib import Path
from typing import Any

from .agents import session_directory, state_directory
from .repository import worktree_root


CODEX_HOOK_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "Stop",
    "Interrupt",
    "SessionEnd",
)
CODEX_HOOK_COMMAND = "dashpot-codex-hook"
CODEX_HOOK_TIMEOUT = 3
CODEX_HOOKS_FILE = "hooks.json"
CONFIG_HOOKS_TABLE = re.compile(r"^\s*\[+\s*hooks", re.MULTILINE)


def default_codex_home() -> Path:
    return Path.home() / ".codex"


def resolve_hook_command() -> Path:
    """Locate this environment's installed hook publisher."""
    scripts = Path(sysconfig.get_path("scripts")) / CODEX_HOOK_COMMAND
    if scripts.is_file():
        return scripts
    found = shutil.which(CODEX_HOOK_COMMAND)
    if found:
        return Path(found)
    raise RuntimeError(
        f"cannot locate the {CODEX_HOOK_COMMAND} publisher installed with "
        "Dashpot; reinstall Dashpot and retry"
    )


def install_codex_integration(
    codex_home: Path | None = None,
    *,
    command_path: Path | None = None,
) -> list[str]:
    """Idempotently register the Codex lifecycle hooks for this user."""
    home = codex_home or default_codex_home()
    if not home.is_dir():
        raise RuntimeError(
            f"no Codex configuration directory at {home}; install and run "
            "Codex once before integrating"
        )
    command = command_path or resolve_hook_command()
    path = home / CODEX_HOOKS_FILE
    document = _load_hooks_document(path)
    original = json.dumps(document, sort_keys=True)
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError(
            f"{path} has a non-object top-level \"hooks\" value; fix the "
            "file and retry"
        )
    handler = {
        "type": "command",
        "command": str(command),
        "timeout": CODEX_HOOK_TIMEOUT,
    }
    for event in CODEX_HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = []
        kept, _ours = _split_dashpot_handlers(groups)
        kept.append({"hooks": [dict(handler)]})
        hooks[event] = kept
    messages: list[str] = []
    if json.dumps(document, sort_keys=True) != original:
        _write_json(path, document)
        messages.append(f"installed Codex lifecycle hooks in {path}")
    else:
        messages.append(f"Codex lifecycle hooks already installed in {path}")
    messages.append(f"hook publisher: {command}")
    messages.extend(_config_toml_coexistence_warning(home))
    return messages


def remove_codex_integration(codex_home: Path | None = None) -> list[str]:
    """Remove exactly the Dashpot handlers from the user's Codex hooks."""
    home = codex_home or default_codex_home()
    path = home / CODEX_HOOKS_FILE
    if not path.is_file():
        return [f"Codex integration is not installed: no {path}"]
    document = _load_hooks_document(path)
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return [f"Codex integration is not installed: no hooks in {path}"]
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
        return [f"Codex integration is not installed: no Dashpot hooks in {path}"]
    if hooks or set(document) - {"hooks", "description"}:
        _write_json(path, document)
        return [f"removed the Dashpot hooks from {path}"]
    path.unlink()
    return [f"removed {path}; it contained only the Dashpot hooks"]


def codex_integration_status(
    codex_home: Path | None = None,
    *,
    state_dir: Path | None = None,
    current: Path | None = None,
) -> list[str]:
    """Report the observable state of the Codex integration."""
    home = codex_home or default_codex_home()
    path = home / CODEX_HOOKS_FILE
    messages: list[str] = []
    if not home.is_dir():
        messages.append(f"Codex configuration directory not found: {home}")
        return messages
    if not path.is_file():
        messages.append(f"not installed: no {path}")
    else:
        try:
            document = _load_hooks_document(path)
        except RuntimeError as exc:
            return [str(exc)]
        commands = _installed_commands(document)
        if not commands:
            messages.append(f"not installed: no Dashpot hooks in {path}")
        else:
            events = sorted(commands)
            missing = [
                event for event in CODEX_HOOK_EVENTS if event not in commands
            ]
            messages.append(
                f"installed in {path} for: {', '.join(events)}"
            )
            if missing:
                messages.append(
                    f"missing hook events (run 'dashpot integrate codex' to "
                    f"repair): {', '.join(missing)}"
                )
            for command in sorted({c for cs in commands.values() for c in cs}):
                executable = Path(command)
                if not executable.is_file():
                    messages.append(
                        f"hook publisher missing at {command}; run "
                        "'dashpot integrate codex' to repair"
                    )
                elif not os.access(executable, os.X_OK):
                    messages.append(
                        f"hook publisher at {command} is not executable"
                    )
                else:
                    messages.append(f"hook publisher: {command}")
    messages.extend(_config_toml_coexistence_warning(home))
    messages.extend(_record_store_status(state_dir, current))
    return messages


def _record_store_status(
    state_dir: Path | None, current: Path | None
) -> list[str]:
    """Report the session stores visible from here: Project-local and global."""
    messages: list[str] = []
    try:
        root = worktree_root(current or Path.cwd())
    except RuntimeError:
        root = None
    if root is not None and (root / ".dashpot" / "config.json").is_file():
        local = session_directory(root)
        records = len(list(local.glob("*.json"))) if local.is_dir() else 0
        messages.append(
            f"session records for this Project: {records} in {local}"
        )
    directory = state_dir or state_directory()
    if directory.is_dir():
        records = len(list(directory.glob("*.json")))
        messages.append(
            f"session records outside configured Projects: {records} in "
            f"{directory}"
        )
    else:
        messages.append(
            f"session records outside configured Projects: none ({directory} "
            "does not exist yet)"
        )
    return messages


def _load_hooks_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"hooks": {}}
    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"cannot read Codex hooks at {path}: {exc}; fix or move the "
            "file and retry"
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
        if not isinstance(group, dict) or not isinstance(
            group.get("hooks"), list
        ):
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


def _is_dashpot_handler(handler: Any) -> bool:
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return False
    command = handler.get("command")
    if isinstance(command, list) and command:
        command = command[0]
    if not isinstance(command, str):
        return False
    executable = command.split()[0] if command.split() else command
    return Path(executable).name == CODEX_HOOK_COMMAND


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


def _config_toml_coexistence_warning(home: Path) -> list[str]:
    config = home / "config.toml"
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return []
    if CONFIG_HOOKS_TABLE.search(text):
        return [
            f"note: {config} also defines hooks; Codex merges both layers "
            "and warns at startup"
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
