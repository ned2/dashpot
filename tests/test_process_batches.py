"""Portable batched identities preserve the persisted ps start-time contract."""

import os
import subprocess
from typing import Any
from unittest import mock

import pytest

from dashpot.sessions.liveness import LivenessObservation, LivenessProbe
from dashpot.sessions.processes import (
    ProcessAbsent,
    ProcessIdentity,
    ProcessPresent,
    ProcessUnobservable,
    host_process_identities,
    host_process_lookup,
    pid_namespace,
)


def test_batch_reads_spaced_commands_once_and_never_reads_arguments() -> None:
    output = (
        "42 1 Tue Aug 25 01:00:00 2026 /Applications/Spaced App/codex\n"
        "77 2 Tue Aug 25 02:00:00 2026 claude\n"
    )
    with (
        mock.patch(
            "dashpot.sessions.processes.process_namespace_is_isolated",
            return_value=False,
        ),
        mock.patch("dashpot.sessions.processes.os.kill") as kill,
        mock.patch(
            "dashpot.sessions.processes.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout=output),
        ) as run,
    ):
        observed = host_process_identities([77, 42, 42])
    assert observed == {
        42: ProcessPresent(
            ProcessIdentity(
                42,
                1,
                "/Applications/Spaced App/codex",
                "Tue Aug 25 01:00:00 2026",
                pid_namespace=pid_namespace(),
            )
        ),
        77: ProcessPresent(
            ProcessIdentity(
                77,
                2,
                "claude",
                "Tue Aug 25 02:00:00 2026",
                pid_namespace=pid_namespace(),
            )
        ),
    }
    assert kill.call_count == 2
    run.assert_called_once()
    assert run.call_args.args[0] == [
        "ps",
        "-ww",
        "-p",
        "42,77",
        "-o",
        "pid=",
        "-o",
        "ppid=",
        "-o",
        "lstart=",
        "-o",
        "comm=",
    ]
    assert run.call_args.kwargs["env"]["LC_ALL"] == "C"
    assert run.call_args.kwargs["env"]["TZ"] == "UTC"


@pytest.mark.parametrize(
    "output",
    [
        "",
        "garbage",
        "42 x Tue Aug 25 01:00:00 2026 codex",
        "42 1 too short",
        "77 1 Tue Aug 25 01:00:00 2026 codex",
        "42 1 Tue Aug 25 01:00:00 2026 codex\n42 1 Tue Aug 25 01:00:00 2026 codex",
    ],
)
def test_missing_malformed_or_duplicate_rows_are_unknown_not_gone(output: str) -> None:
    with (
        mock.patch(
            "dashpot.sessions.processes.process_namespace_is_isolated",
            return_value=False,
        ),
        mock.patch(
            "dashpot.sessions.processes.pid_namespace", return_value=OWN_NAMESPACE
        ),
        mock.patch("dashpot.sessions.processes.os.kill"),
        mock.patch(
            "dashpot.sessions.processes.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout=output),
        ),
    ):
        assert host_process_identities([42]) == {
            42: ProcessUnobservable(42, "ps-unparseable")
        }


@pytest.mark.parametrize(
    "failure,reason",
    [
        (OSError(), "ps-unavailable"),
        (subprocess.TimeoutExpired("ps", 2), "ps-timeout"),
        (mock.Mock(returncode=1, stdout=""), "ps-failed"),
    ],
)
def test_batch_failure_makes_every_selected_pid_unobservable(
    failure: object, reason: str
) -> None:
    kwargs: dict[str, Any] = (
        {"side_effect": failure}
        if isinstance(failure, BaseException)
        else {"return_value": failure}
    )
    with (
        mock.patch(
            "dashpot.sessions.processes.process_namespace_is_isolated",
            return_value=False,
        ),
        mock.patch("dashpot.sessions.processes.os.kill"),
        mock.patch("dashpot.sessions.processes.subprocess.run", **kwargs),
    ):
        assert host_process_identities([42, 77]) == {
            pid: ProcessUnobservable(pid, reason) for pid in (42, 77)
        }


def test_presence_probes_alone_prove_absence_and_do_not_run_ps() -> None:
    with (
        mock.patch(
            "dashpot.sessions.processes.process_namespace_is_isolated",
            return_value=False,
        ),
        mock.patch(
            "dashpot.sessions.processes.os.kill",
            side_effect=[ProcessLookupError(), OSError()],
        ),
        mock.patch("dashpot.sessions.processes.subprocess.run") as run,
    ):
        assert host_process_identities([-1, 42, 77]) == {
            -1: ProcessAbsent(-1),
            42: ProcessAbsent(42),
            77: ProcessUnobservable(77, "kill-failed"),
        }
        assert host_process_identities([]) == {}
    run.assert_not_called()


# A PID namespace as ``/proc/self/ns/pid`` names one; macOS has none, so
# the tests that need one name it.
OWN_NAMESPACE = "pid:[4026531836]"


def test_an_isolated_probe_reads_only_a_process_recorded_in_its_own_namespace() -> None:
    # Inside a container, a process recorded without a PID namespace may be
    # one outside it; one recorded in this namespace, or the batch probing
    # it as this namespace's own, is observed like anywhere else.
    started = "Tue Aug 25 01:00:00 2026"
    with (
        mock.patch(
            "dashpot.sessions.processes.process_namespace_is_isolated",
            return_value=True,
        ),
        mock.patch(
            "dashpot.sessions.processes.pid_namespace", return_value=OWN_NAMESPACE
        ),
        mock.patch("dashpot.sessions.processes.os.kill"),
        mock.patch(
            "dashpot.sessions.processes.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout=f"42 1 {started} claude"),
        ),
    ):
        assert host_process_lookup(42) == ProcessUnobservable(42, "isolated-namespace")
        probe = LivenessProbe(host_process_lookup)
        probe.prepare([(42, started)])
        assert probe.observe((42, started), namespace=None) == LivenessObservation(
            "unknown", "isolated-namespace"
        )
        assert probe.observe((42, started), namespace=OWN_NAMESPACE).liveness == "live"
        assert probe.observe((42, started), namespace="pid:[1]") == LivenessObservation(
            "unknown", "isolated-namespace"
        )
        # A process the pass did not batch is probed alone.
        unprepared = LivenessProbe(host_process_lookup)
        assert (
            unprepared.observe((42, started), namespace=OWN_NAMESPACE).liveness
            == "live"
        )


def test_prepared_liveness_compares_each_start_time_and_refreshes_next_pass() -> None:
    started = "Tue Aug 25 01:00:00 2026"
    with (
        mock.patch(
            "dashpot.sessions.processes.process_namespace_is_isolated",
            return_value=False,
        ),
        mock.patch("dashpot.sessions.processes.os.kill", side_effect=PermissionError()),
        mock.patch(
            "dashpot.sessions.processes.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout=f"42 1 {started} codex"),
        ) as run,
    ):
        probe = LivenessProbe(host_process_lookup)
        probe.prepare([(42, started), (42, "older"), None])
        assert probe.observe((42, started), namespace=None).liveness == "live"
        assert probe.observe((42, "older"), namespace=None).liveness == "gone"
        probe.prepare([(42, started)])
        assert run.call_count == 1
        later = LivenessProbe(host_process_lookup)
        later.prepare([(42, started)])
        assert later.observe((42, started), namespace=None).liveness == "live"
        assert run.call_count == 2


def test_batch_start_time_matches_single_probe_and_ps_on_the_running_platform() -> None:
    pid = os.getpid()
    expected = subprocess.run(
        ["ps", "-ww", "-p", str(pid), "-o", "lstart="],
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
    )
    # Hook records already normalize ps's padding between the date fields.
    started = " ".join(expected.stdout.split())
    with mock.patch(
        "dashpot.sessions.processes.process_namespace_is_isolated", return_value=False
    ):
        single = host_process_lookup(pid)
        batch = host_process_identities([pid])[pid]
    assert isinstance(single, ProcessPresent)
    assert isinstance(batch, ProcessPresent)
    assert (
        batch.identity.started_at.encode()
        == single.identity.started_at.encode()
        == started.encode()
    )
    assert batch.identity.parent_pid == single.identity.parent_pid == os.getppid()
    assert batch.identity.command == single.identity.command
