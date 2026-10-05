"""Whether anyone attends the dashboard, and the Unattended Pause while nobody does.

A dashboard left running with nobody watching still spends the GitHub
allowance on data nobody reads (ADR 0068). Two signals show it unattended:
every tmux client detached from its session and the session's group, or no
key or mouse event for the idle period. Blur alone is not one: a visible
dashboard beside a person's work is attended, and tmux reports focus
unreliably on detach.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..core.commands import CommandError, CommandRunner, run_command
from ..core.model import Diagnostic
from ..core.runtime_events import UnattendedPauseChange, UnattendedSignal

UNATTENDED_PAUSED = "github-unattended-paused"

# How many tmux clients see the dashboard's pane: those of the whole group
# for a grouped session, since ``#{session_attached}`` counts only the clients
# of the one session tmux resolves the pane to.
ATTACHED_CLIENTS = "#{?session_grouped,#{session_group_attached},#{session_attached}}"

# Whether a tmux client is attached to the dashboard's session, or None when
# that could not be told; an unknown answer changes nothing.
AttachmentProbe = Callable[[], bool | None]


@dataclass(frozen=True, slots=True)
class UnattendedPause:
    """A stretch when automatic GitHub refreshes send nothing because nobody attends."""

    signal: UnattendedSignal
    since: datetime


@dataclass(frozen=True, slots=True)
class AttendanceChange:
    """An Unattended Pause starting or ending, for the dashboard to act on."""

    change: UnattendedPauseChange
    pause: UnattendedPause


class Attendance:
    """Whether anyone attends the dashboard, and the Unattended Pause while nobody does.

    Input and focus are noted as they arrive; idleness is checked, and the
    tmux session probed, on each automatic GitHub refresh, so a pause starts
    within one GitHub Refresh Period of its signal. Any input ends a pause,
    as does a tmux client reattaching; an idle pause outlasts a client that
    stayed attached.
    """

    def __init__(
        self,
        *,
        idle_seconds: float,
        probe: AttachmentProbe | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.idle_seconds = idle_seconds
        self.probe = probe
        self._clock = clock
        self._wall_clock = wall_clock or _utc_now
        self._last_input = clock()
        # The last probe's readable answer, so a client reattaching is told
        # apart from one that never left, even across an unreadable probe.
        self._attached: bool | None = None
        self.pause: UnattendedPause | None = None

    def attended(self) -> AttendanceChange | None:
        """Note someone attending the dashboard, ending the pause if one holds."""
        self._last_input = self._clock()
        ended, self.pause = self.pause, None
        return None if ended is None else AttendanceChange("ended", ended)

    def check_idle(self) -> AttendanceChange | None:
        """Start an idle pause once no input has come for the idle period."""
        if self.pause is not None or self.idle_seconds <= 0:
            return None
        if self._clock() - self._last_input < self.idle_seconds:
            return None
        return self._start("idle")

    def probed(self, attached: bool | None) -> AttendanceChange | None:
        """Take a probe's answer: detached starts a pause, reattached attends."""
        if attached is None:
            return None
        was, self._attached = self._attached, attached
        if not attached:
            return None if self.pause is not None else self._start("detached")
        if was is False:
            return self.attended()
        return None

    def diagnostics(self) -> tuple[Diagnostic, ...]:
        """One ``github-unattended-paused`` line while a pause holds."""
        pause = self.pause
        if pause is None:
            return ()
        return (
            Diagnostic(
                source="github",
                severity="info",
                message=(
                    f"GitHub queries paused since {pause.since:%H:%M:%S} UTC: "
                    f"{self.signal_text(pause)}; any key resumes"
                ),
                code=UNATTENDED_PAUSED,
            ),
        )

    def signal_text(self, pause: UnattendedPause) -> str:
        """What showed nobody attending, as a person reads it."""
        if pause.signal == "detached":
            return "no tmux client attached"
        return f"no key or mouse input for {period_text(self.idle_seconds)}"

    def _start(self, signal: UnattendedSignal) -> AttendanceChange:
        pause = UnattendedPause(signal, self._wall_clock().astimezone(UTC))
        self.pause = pause
        return AttendanceChange("started", pause)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def period_text(seconds: float) -> str:
    """A configured period in its largest units, leaving out those that are zero."""
    if seconds < 60 and seconds != int(seconds):
        return f"{seconds:g}s"
    hours, rest = divmod(int(seconds), 3_600)
    minutes, secs = divmod(rest, 60)
    parts = [
        f"{value}{unit}"
        for value, unit in ((hours, "h"), (minutes, "m"), (secs, "s"))
        if value
    ]
    return " ".join(parts) or "0s"


def tmux_attachment(
    environ: Mapping[str, str],
    timeout: float,
    *,
    run: CommandRunner = run_command,
) -> AttachmentProbe | None:
    """The probe of the tmux session this dashboard runs in, or None outside tmux.

    It asks tmux how many clients are attached to the session holding the
    dashboard's own pane, which answers even once every client has
    detached. A grouped session (``tmux new -t``) shares its windows with
    the rest of its group, so a client of any session in the group sees the
    pane, and the group's count is the one asked for.
    """
    pane = environ.get("TMUX_PANE")
    if not environ.get("TMUX") or not pane:
        return None
    args = ("tmux", "display-message", "-p", "-t", pane, ATTACHED_CLIENTS)

    def probe() -> bool | None:
        # tmux answers the same from any directory, so the probe runs at the
        # filesystem root, which always exists, rather than at the working
        # directory, which a removed Worktree takes away.
        try:
            result = run(args, Path("/"), timeout)
        except (CommandError, OSError):
            return None
        count = result.stdout.strip()
        if result.returncode != 0 or not count.isdigit():
            return None
        return int(count) > 0

    return probe
