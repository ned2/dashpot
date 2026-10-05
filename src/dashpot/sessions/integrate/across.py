"""Install, refresh and report several harnesses' integrations in one command (ADR 0111)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...core.model import HARNESS_DISPLAY, Harness
from .diagnostics import record_store_status
from .environment import PROCESS_ENVIRONMENT, IntegrationEnvironment
from .harness import (
    has_update,
    install_integration,
    integration_presence,
    integration_status,
)
from .publisher import linked_worktree_binding, linked_worktree_consequence
from .registry import configuration_directory, integration, resolve_hook_command
from .writes import IncompleteIntegrationError, IntegrationError

# Several harnesses in one command run in this order, whatever order they
# are named in: OpenCode also discovers Claude Code's and Codex's skill
# copies, so its check of them then reads copies this same command has just
# refreshed, and warns only about a genuine conflict (ADR 0111).
INTEGRATION_ORDER: tuple[Harness, ...] = ("claude-code", "codex", "opencode")

# What one harness's part of a command across harnesses came to.
HarnessOutcome = Literal[
    "installed", "incomplete", "refused", "partial", "not integrated", "reported"
]


@dataclass(frozen=True, slots=True)
class HarnessReport:
    """One harness's part of an ``integrate`` across harnesses."""

    harness: Harness
    outcome: HarnessOutcome
    # What the harness's own ``integrate`` or ``--status`` would print.
    messages: tuple[str, ...] = ()
    # Said beside the harness's name, such as "refused" or "not integrated".
    note: str | None = None
    # Why the harness was refused or left incomplete; ``None`` otherwise.
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CombinedStatus:
    """``--status`` across harnesses: each harness's report, then what they share."""

    harnesses: tuple[HarnessReport, ...]
    # The session record stores, which every harness shares, and any advice
    # that spans harnesses.
    messages: tuple[str, ...]


def in_integration_order(harnesses: Iterable[Harness]) -> tuple[Harness, ...]:
    """Each named harness once, in the order a command across harnesses runs them."""
    named = frozenset(harnesses)
    return tuple(harness for harness in INTEGRATION_ORDER if harness in named)


def _partial_advice(harness: Harness, detail: str) -> str:
    return (
        f"{detail}; run 'dashpot integrate {harness}' to complete it, or "
        f"'dashpot integrate {harness} --remove' to clear it"
    )


@dataclass(frozen=True, slots=True)
class _PlannedInstall:
    """A harness a command across harnesses will install, bound to its publisher."""

    harness: Harness
    command: Path


def install_integrations(
    harnesses: Sequence[Harness],
    *,
    command_paths: Mapping[Harness, Path] | None = None,
    environment: IntegrationEnvironment = PROCESS_ENVIRONMENT,
) -> list[HarnessReport]:
    """Install each named harness's integration, each standing alone.

    The harnesses run in ``INTEGRATION_ORDER``: one refused, or left
    incomplete, does not stop the others (ADR 0110). A publisher in a
    linked Worktree concerns the whole command, so it is refused, raising
    ``IntegrationError``, before any harness changes (ADR 0111).
    """
    named = in_integration_order(harnesses)
    return _install_across(
        [_plan_install(harness, command_paths) for harness in named],
        " ".join(named),
        environment,
    )


def refresh_integrations(
    *,
    command_paths: Mapping[Harness, Path] | None = None,
    environment: IntegrationEnvironment = PROCESS_ENVIRONMENT,
) -> list[HarnessReport]:
    """Refresh every integrated harness, as ``--installed``, and install into no other.

    Only a harness whose every lifecycle hook is registered is refreshed,
    however stale its skills or agents; a partial one is left as it is and
    reported, and one not integrated gets a line. Otherwise it runs as
    ``install_integrations`` does (ADR 0111).
    """
    return _install_across(
        [
            _skip_unless_integrated(harness, environment)
            or _plan_install(harness, command_paths)
            for harness in INTEGRATION_ORDER
        ],
        "--installed",
        environment,
    )


def _plan_install(
    harness: Harness, command_paths: Mapping[Harness, Path] | None
) -> HarnessReport | _PlannedInstall:
    """Bind a harness to its publisher, or refuse it alone when none is found."""
    try:
        command = (command_paths or {}).get(harness) or resolve_hook_command(
            integration(harness)
        )
    except IntegrationError as exc:
        return _refused(harness, exc)
    return _PlannedInstall(harness, command)


def _install_across(
    planned: Sequence[HarnessReport | _PlannedInstall],
    arguments: str,
    environment: IntegrationEnvironment,
) -> list[HarnessReport]:
    """Install each planned harness in turn, once no publisher is a linked Worktree's.

    ``arguments`` are the command's own, which a linked-Worktree refusal
    names for the rerun.
    """
    _refuse_linked_worktree_publishers(
        [item for item in planned if isinstance(item, _PlannedInstall)], arguments
    )
    reports: list[HarnessReport] = []
    for item in planned:
        if isinstance(item, HarnessReport):
            reports.append(item)
            continue
        try:
            messages = install_integration(
                item.harness,
                command_path=item.command,
                environment=environment,
            )
        except IncompleteIntegrationError as exc:
            reports.append(
                HarnessReport(
                    item.harness, "incomplete", exc.messages, "incomplete", str(exc)
                )
            )
        except IntegrationError as exc:
            reports.append(_refused(item.harness, exc))
        else:
            reports.append(HarnessReport(item.harness, "installed", tuple(messages)))
    return reports


def _skip_unless_integrated(
    harness: Harness, environment: IntegrationEnvironment
) -> HarnessReport | None:
    """The report of a harness ``--installed`` leaves alone; ``None`` to refresh it."""
    try:
        presence = integration_presence(harness, environment=environment)
    except IntegrationError as exc:
        return _refused(harness, exc)
    if presence.state == "integrated":
        return None
    if presence.state == "partial":
        return HarnessReport(
            harness,
            "partial",
            (f"left unchanged: {_partial_advice(harness, presence.detail)}",),
            "partial",
        )
    return HarnessReport(
        harness, "not integrated", note=f"not integrated ({presence.detail})"
    )


def _refused(harness: Harness, error: IntegrationError) -> HarnessReport:
    return HarnessReport(harness, "refused", note="refused", error=str(error))


def _refuse_linked_worktree_publishers(
    planned: Sequence[_PlannedInstall], arguments: str
) -> None:
    """Refuse the whole command when any harness would bind a linked Worktree's publisher."""
    linked = [
        (item.harness, item.command, binding)
        for item in planned
        if (binding := linked_worktree_binding(item.command)) is not None
    ]
    if not linked:
        return
    harness, command, binding = linked[0]
    if len(linked) == 1:
        raise IntegrationError(
            f"cannot bind the {HARNESS_DISPLAY[harness]} hooks to {command}: "
            f"{linked_worktree_consequence(arguments, binding)}"
        )
    # One environment installs every harness's publisher, so the first
    # names the Worktree they all live in.
    names = _display_list([harness for harness, _command, _binding in linked])
    consequence = linked_worktree_consequence(
        arguments, binding, publisher="those publishers live"
    )
    raise IntegrationError(
        f"cannot bind the {names} hooks to their publishers in {command.parent}: "
        f"{consequence}"
    )


def _display_list(harnesses: Sequence[Harness]) -> str:
    """Name harnesses in prose: ``Codex``, ``Claude Code and Codex``, or a serial list."""
    names = [HARNESS_DISPLAY[harness] for harness in harnesses]
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def integrations_status(
    harnesses: Sequence[Harness] = (),
    *,
    state_dir: Path | None = None,
    current: Path | None = None,
    environment: IntegrationEnvironment = PROCESS_ENVIRONMENT,
) -> CombinedStatus:
    """Report each named harness's integration, or every harness's when none is named.

    With none named, a harness not integrated gets one line; an integrated
    or partial one gets its full report, a partial one led by how to
    complete or clear it. The session record stores, which every harness
    shares, are reported once, after them. When two or more integrated
    harnesses have an update available, one line names the command that
    updates them together (ADR 0111).
    """

    def report(harness: Harness) -> list[str]:
        return integration_status(
            harness,
            state_dir=state_dir,
            current=current,
            environment=environment,
            records=False,
        )

    reports: list[HarnessReport] = []
    stale: list[Harness] = []
    for harness in in_integration_order(harnesses or INTEGRATION_ORDER):
        spec = integration(harness)
        try:
            presence = integration_presence(harness, environment=environment)
        except IntegrationError:
            # The harness's own report names what cannot be read.
            presence = None
        state = None if presence is None else presence.state
        detail = "" if presence is None else presence.detail
        if state == "integrated" and has_update(
            spec, configuration_directory(spec, environment.environ).path, environment
        ):
            stale.append(harness)
        if state == "partial":
            advice = _partial_advice(harness, detail)
            reports.append(
                HarnessReport(harness, "partial", (advice, *report(harness)), "partial")
            )
        elif state == "not integrated" and not harnesses:
            note = f"not integrated ({detail})"
            reports.append(HarnessReport(harness, "not integrated", note=note))
        else:
            reports.append(HarnessReport(harness, "reported", tuple(report(harness))))
    messages = record_store_status(state_dir, current, environment.lookup)
    if len(stale) > 1:
        rerun = " ".join(stale) if harnesses else "--installed"
        messages.append(
            f"updates available for {_display_list(stale)}; run 'dashpot "
            f"integrate {rerun}' to update them together"
        )
    return CombinedStatus(tuple(reports), tuple(messages))
