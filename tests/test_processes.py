from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from dashpot.processes import (
    AgentAncestry,
    ProcessAbsent,
    ProcessIdentity,
    ProcessPresent,
    ProcessUnobservable,
    host_process_lookup,
    namespace_is_isolated,
    nearest_agent_process,
    nearest_codex_process,
    observe_agent_ancestry,
)
from helpers import absent, table_lookup, unobservable


class ProcessLookupTests(unittest.TestCase):
    def test_nearest_agent_process_prefers_the_nearest_harness(self) -> None:
        shell = ProcessIdentity(10, 20, "bash", "Tue Aug 25 01:00:00 2026")
        claude = ProcessIdentity(20, 30, "claude", "Tue Aug 25 00:59:00 2026")
        codex = ProcessIdentity(30, 1, "codex", "Tue Aug 25 00:58:00 2026")
        chain = {10: shell, 20: claude, 30: codex}

        with mock.patch("dashpot.processes.os.getppid", return_value=10):
            result = nearest_agent_process(lookup=table_lookup(chain))

        self.assertEqual(("claude-code", claude), result)

    def test_nearest_codex_process_skips_sandbox_helper(self) -> None:
        sandbox = ProcessIdentity(
            10,
            20,
            "codex",
            "Tue Aug 25 01:00:00 2026",
            "codex-linux-sandbox --sandbox-policy-cwd /repo",
        )
        host = ProcessIdentity(
            20,
            1,
            "codex",
            "Tue Aug 25 00:59:00 2026",
            "/usr/bin/codex",
        )

        with mock.patch("dashpot.processes.os.getppid", return_value=10):
            result = nearest_codex_process(lookup=table_lookup({10: sandbox, 20: host}))

        self.assertEqual(host, result)

    def test_host_process_lookup_parses_portable_ps_fields_and_arguments(
        self,
    ) -> None:
        probes = [
            mock.Mock(returncode=0, stdout="42 1 Tue Aug 25 01:00:00 2026 codex\n"),
            mock.Mock(
                returncode=0, stdout="/opt/codex exec --sandbox workspace-write\n"
            ),
        ]

        with (
            mock.patch(
                "dashpot.processes.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.processes.os.kill") as kill,
            mock.patch("dashpot.processes.subprocess.run", side_effect=probes) as run,
        ):
            result = host_process_lookup(42)

        self.assertEqual(
            ProcessPresent(
                ProcessIdentity(
                    42,
                    1,
                    "codex",
                    "Tue Aug 25 01:00:00 2026",
                    "/opt/codex exec --sandbox workspace-write",
                )
            ),
            result,
        )
        kill.assert_called_once_with(42, 0)
        identity_probe, arguments_probe = run.call_args_list
        self.assertEqual(
            ["-o", "pid=", "-o", "ppid=", "-o", "lstart=", "-o", "comm="],
            identity_probe.args[0][3:],
        )
        self.assertEqual(["-o", "args="], arguments_probe.args[0][3:])
        self.assertEqual("C", identity_probe.kwargs["env"]["LC_ALL"])
        self.assertEqual("UTC", identity_probe.kwargs["env"]["TZ"])

    def test_host_process_lookup_reads_a_spaced_macos_comm_intact(self) -> None:
        # macOS renders ``comm`` as the executable's full path, which may
        # contain spaces; the start time must not shift when it does.
        helper = (
            "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/claude"
        )
        probes = [
            mock.Mock(returncode=0, stdout=f"42 1 Tue Aug 25 01:00:00 2026 {helper}\n"),
            mock.Mock(returncode=0, stdout=f"{helper} --continue\n"),
        ]

        with (
            mock.patch(
                "dashpot.processes.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.processes.os.kill"),
            mock.patch("dashpot.processes.subprocess.run", side_effect=probes),
        ):
            result = host_process_lookup(42)

        self.assertEqual(
            ProcessPresent(
                ProcessIdentity(
                    42, 1, helper, "Tue Aug 25 01:00:00 2026", f"{helper} --continue"
                )
            ),
            result,
        )

    def test_host_process_lookup_reports_a_missing_pid_as_absent(self) -> None:
        with (
            mock.patch(
                "dashpot.processes.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.processes.os.kill", side_effect=ProcessLookupError),
            mock.patch("dashpot.processes.subprocess.run") as run,
        ):
            result = host_process_lookup(42)

        self.assertEqual(ProcessAbsent(42), result)
        run.assert_not_called()

    def test_host_process_lookup_treats_another_users_process_as_present(
        self,
    ) -> None:
        probes = [
            mock.Mock(returncode=0, stdout="42 1 Tue Aug 25 01:00:00 2026 codex\n"),
            mock.Mock(returncode=0, stdout="\n"),
        ]

        with (
            mock.patch(
                "dashpot.processes.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.processes.os.kill", side_effect=PermissionError),
            mock.patch("dashpot.processes.subprocess.run", side_effect=probes),
        ):
            result = host_process_lookup(42)

        self.assertEqual(
            ProcessPresent(ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")),
            result,
        )

    def test_host_process_lookup_reports_every_probe_failure_as_unobservable(
        self,
    ) -> None:
        cases: list[tuple[str, Any]] = [
            ("ps-unavailable", FileNotFoundError("ps")),
            ("ps-timeout", subprocess.TimeoutExpired(["ps"], 2)),
            ("ps-failed", mock.Mock(returncode=1, stdout="")),
            ("ps-unparseable", mock.Mock(returncode=0, stdout="garbage\n")),
            ("ps-unparseable", mock.Mock(returncode=0, stdout="x y z a b c d e f\n")),
        ]
        for reason, outcome in cases:
            with self.subTest(reason=reason, outcome=outcome):
                run_kwargs = (
                    {"side_effect": outcome}
                    if isinstance(outcome, BaseException)
                    else {"return_value": outcome}
                )
                with (
                    mock.patch(
                        "dashpot.processes.process_namespace_is_isolated",
                        return_value=False,
                    ),
                    mock.patch("dashpot.processes.os.kill"),
                    mock.patch("dashpot.processes.subprocess.run", **run_kwargs),
                ):
                    result = host_process_lookup(42)

                self.assertEqual(ProcessUnobservable(42, reason), result)

    def test_host_process_lookup_reports_a_failing_arguments_probe(self) -> None:
        probes = [
            mock.Mock(returncode=0, stdout="42 1 Tue Aug 25 01:00:00 2026 codex\n"),
            mock.Mock(returncode=1, stdout=""),
        ]

        with (
            mock.patch(
                "dashpot.processes.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.processes.os.kill"),
            mock.patch("dashpot.processes.subprocess.run", side_effect=probes),
        ):
            result = host_process_lookup(42)

        self.assertEqual(ProcessUnobservable(42, "ps-failed"), result)

    def test_host_process_lookup_reports_a_kill_probe_failure(self) -> None:
        with (
            mock.patch(
                "dashpot.processes.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.processes.os.kill", side_effect=OSError("EINVAL")),
            mock.patch("dashpot.processes.subprocess.run") as run,
        ):
            self.assertEqual(
                ProcessUnobservable(42, "kill-failed"), host_process_lookup(42)
            )
        run.assert_not_called()

    def test_host_process_lookup_never_probes_an_isolated_namespace(self) -> None:
        with (
            mock.patch(
                "dashpot.processes.process_namespace_is_isolated", return_value=True
            ),
            mock.patch("dashpot.processes.os.kill") as kill,
            mock.patch("dashpot.processes.subprocess.run") as run,
        ):
            result = host_process_lookup(42)

        self.assertEqual(ProcessUnobservable(42, "isolated-namespace"), result)
        kill.assert_not_called()
        run.assert_not_called()


class AgentAncestryTests(unittest.TestCase):
    def test_a_harness_filter_walks_past_other_harnesses(self) -> None:
        shell = ProcessIdentity(10, 20, "bash", "Tue Aug 25 01:00:00 2026")
        claude = ProcessIdentity(20, 30, "claude", "Tue Aug 25 00:59:00 2026")
        codex = ProcessIdentity(30, 1, "codex", "Tue Aug 25 00:58:00 2026")
        chain = {10: shell, 20: claude, 30: codex}

        with mock.patch("dashpot.processes.os.getppid", return_value=10):
            result = observe_agent_ancestry(table_lookup(chain), harness="codex")

        self.assertEqual(("codex", codex), result.located)

    def test_a_filtered_walk_keeps_the_unobservable_reason(self) -> None:
        # One walk serves the filtered and unfiltered questions, so being
        # sandboxed is never read as "no harness here" (issue #77 O-N1).
        with mock.patch("dashpot.processes.os.getppid", return_value=10):
            filtered = observe_agent_ancestry(
                unobservable("isolated-namespace"), harness="codex"
            )
            wrapped = nearest_codex_process(lookup=unobservable("isolated-namespace"))

        self.assertEqual(AgentAncestry(None, "isolated-namespace"), filtered)
        self.assertIsNone(wrapped)

    def test_ancestry_reports_why_the_walk_stopped_short(self) -> None:
        with mock.patch("dashpot.processes.os.getppid", return_value=10):
            isolated = observe_agent_ancestry(unobservable("isolated-namespace"))
            gone = observe_agent_ancestry(absent())
            helper = ProcessIdentity(10, 1, "bwrap", "x", "bwrap --unshare-pid sh")
            sandboxed = observe_agent_ancestry(table_lookup({10: helper}))

        self.assertEqual(AgentAncestry(None, "isolated-namespace"), isolated)
        self.assertEqual(AgentAncestry(None), gone)
        self.assertEqual(AgentAncestry(None), sandboxed)


class NamespaceIsolationTests(unittest.TestCase):
    def namespace_root(
        self,
        init: bytes = b"/sbin/init\0splash\0",
        cgroup: str = "0::/init.scope\n",
        markers: tuple[str, ...] = (),
    ) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / "proc" / "1").mkdir(parents=True)
        (root / "proc" / "1" / "cmdline").write_bytes(init)
        (root / "proc" / "1" / "cgroup").write_text(cgroup)
        for marker in markers:
            (root / marker).parent.mkdir(parents=True, exist_ok=True)
            (root / marker).touch()
        return root

    def test_isolation_is_recognized_for_each_sandbox_helper(self) -> None:
        for init in (
            b"codex-linux-sandbox\0--sandbox-policy-cwd\0/repo\0",
            b"bwrap\0--unshare-pid\0sh\0",
            b"/usr/bin/bwrap\0--ro-bind\0/\0/\0",
        ):
            with self.subTest(init=init):
                self.assertTrue(namespace_is_isolated(self.namespace_root(init)))

    def test_a_host_init_reads_as_not_isolated(self) -> None:
        for init, cgroup in (
            (b"/sbin/init\0splash\0", "0::/init.scope\n"),
            (b"/usr/lib/systemd/systemd\0", "1:name=systemd:/init.scope\n"),
        ):
            with self.subTest(init=init, cgroup=cgroup):
                self.assertFalse(
                    namespace_is_isolated(self.namespace_root(init, cgroup))
                )

    def test_isolation_is_recognized_for_each_container_shape(self) -> None:
        # A container's PID 1 is its entrypoint, so the engines are recognized
        # by their marker files and cgroup names, not by the init command.
        entrypoint = b"/entrypoint.sh\0serve\0"
        for markers in ((".dockerenv",), ("run/.containerenv",)):
            with self.subTest(markers=markers):
                self.assertTrue(
                    namespace_is_isolated(
                        self.namespace_root(entrypoint, "0::/\n", markers)
                    )
                )
        for cgroup in (
            "12:pids:/docker/0123abc\n",
            "3:cpu:/machine.slice/libpod-abc.scope\n",
            "2:memory:/kubepods/besteffort/pod9/abc\n",
            "5:pids:/lxc/mycontainer\n",
            "4:cpu:/system.slice/containerd.service/abc\n",
        ):
            with self.subTest(cgroup=cgroup):
                self.assertTrue(
                    namespace_is_isolated(self.namespace_root(entrypoint, cgroup))
                )

    def test_an_unreadable_proc_reads_as_not_isolated(self) -> None:
        root = self.namespace_root()
        shutil.rmtree(root / "proc")
        self.assertFalse(namespace_is_isolated(root))

    def test_an_unreadable_cmdline_still_reads_the_cgroup(self) -> None:
        root = self.namespace_root(cgroup="12:pids:/docker/0123abc\n")
        (root / "proc" / "1" / "cmdline").unlink()
        self.assertTrue(namespace_is_isolated(root))
