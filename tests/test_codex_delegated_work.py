"""Codex sub-agents through the hook seam: delegated work holds its session's run (#355).

Each test replays Codex hook events in the order the pinned release emits
them: a sub-agent's boundaries and its own events carry the root thread's
``session_id`` and the child thread's ``agent_id``, and the child has no
``SessionStart`` or ``SessionEnd`` of its own (ADR 0016, ADR 0067).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dashpot.core.model import AgentRun
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import session_directory, state_directory
from dashpot.sessions.work import IssueWorkError, show_issue_work, start_issue_work
from dashpot.sessions.work_store import WorkStore
from factories import CODEX
from test_work import CODEX_SESSION, codex_lookup, target, two_worktrees

# A second root thread on the same Codex Host Process, as on the managed daemon.
SIBLING = "01a05099-1563-79a3-8504-e30d50949cb7"
CHILD = "01a05099-1d2a-7c30-9a8e-3f1d2c4b5a01"
SECOND_CHILD = "01a05099-1d2a-7c30-9a8e-3f1d2c4b5a02"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def publish(
    at: Path,
    event: str,
    child: str | None = None,
    *,
    session: str = CODEX_SESSION,
) -> HookPublication:
    """Publish one Codex hook event of ``session``, child-scoped when ``child`` is given."""
    payload: dict[str, Any] = {
        "session_id": session,
        "cwd": str(at),
        "hook_event_name": event,
    }
    if child is not None:
        payload["agent_id"] = child
    return publish_hook_event(
        payload, process=CODEX, harness="codex", lookup=codex_lookup
    )


def bound_session(
    at: Path, session: str = CODEX_SESSION, issue: str = "build-observer"
) -> None:
    """Start a root thread's turn at ``at`` and bind it to ``issue`` from its shell."""
    publish(at, "SessionStart", session=session)
    publish(at, "UserPromptSubmit", session=session)
    start_issue_work(
        at, issue, lookup=codex_lookup, environ={"CODEX_THREAD_ID": session}
    )


def runs(*worktrees: Path) -> list[AgentRun]:
    """Every Agent Run observed at ``worktrees``, asserting no diagnostics."""
    observed, diagnostics = observe_agent_runs(
        {"project:test": [target(worktree) for worktree in worktrees]},
        state_directory(),
        lookup=codex_lookup,
    )
    assert diagnostics == []
    return observed


def run_of(at: Path, session: str = CODEX_SESSION) -> AgentRun:
    """The one Agent Run of ``session`` observed at ``at``."""
    (found,) = [run for run in runs(at) if run.session_id == session]
    return found


def stored(at: Path, session: str = CODEX_SESSION) -> dict[str, Any] | None:
    """The hook record of ``session`` in ``at``'s store, if there is one."""
    path = session_directory(at) / f"{session}.json"
    return json.loads(path.read_text()) if path.exists() else None


def recorded(at: Path, session: str = CODEX_SESSION) -> dict[str, Any]:
    """The hook record of ``session`` in ``at``'s store, which must exist."""
    record = stored(at, session)
    assert record is not None, f"no record of {session} at {at}"
    return record


# --- The measured order -------------------------------------------------------


def test_the_measured_order_holds_the_run_until_its_child_stops(tmp_path: Path) -> None:
    # Measured on 0.159.2 and 0.159.3: the root's Stop arrives while the child
    # still works, and the child's prompt follows it.
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    (work,) = WorkStore(a).active()[0]
    bound = run_of(a)
    turn = bound.turn_started_at
    assert turn is not None

    publish(a, "SubagentStart", CHILD)
    assert (run_of(a).state, run_of(a).turn_started_at) == ("running", turn)

    publish(a, "Stop")
    at_stop = run_of(a)
    assert (at_stop.state, at_stop.turn_started_at) == ("running", None)

    # A child's prompt is not a new main turn: the clock stays stopped.
    publish(a, "UserPromptSubmit", CHILD)
    assert (run_of(a).state, run_of(a).turn_started_at) == ("running", None)

    publish(a, "SubagentStop", CHILD)

    done = run_of(a)
    assert (done.state, done.turn_started_at) == ("waiting", None)
    assert (done.id, done.issue_id, done.started_at) == (
        bound.id,
        "I_observer",
        bound.started_at,
    )
    assert WorkStore(a).active()[0] == [work]
    assert stored(a, CHILD) is None


def test_a_child_finishing_inside_the_turn_leaves_the_session_running(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    turn = run_of(a).turn_started_at

    for event in ("SubagentStart", "UserPromptSubmit", "SubagentStop"):
        publish(a, event, CHILD)

    assert (run_of(a).state, run_of(a).turn_started_at) == ("running", turn)
    publish(a, "Stop")
    assert (run_of(a).state, run_of(a).turn_started_at) == ("waiting", None)


# Each step is (event, child or None for the root thread, the run's state after).
ORDERS = {
    "root-stops-first": [
        ("SubagentStart", CHILD, "running"),
        ("SubagentStart", SECOND_CHILD, "running"),
        ("Stop", None, "running"),
        ("SubagentStop", CHILD, "running"),
        ("SubagentStop", SECOND_CHILD, "waiting"),
    ],
    "children-stop-in-reverse": [
        ("SubagentStart", CHILD, "running"),
        ("SubagentStart", SECOND_CHILD, "running"),
        ("Stop", None, "running"),
        ("SubagentStop", SECOND_CHILD, "running"),
        ("SubagentStop", CHILD, "waiting"),
    ],
    "root-stops-between-children": [
        ("SubagentStart", CHILD, "running"),
        ("SubagentStart", SECOND_CHILD, "running"),
        ("SubagentStop", CHILD, "running"),
        ("Stop", None, "running"),
        ("SubagentStop", SECOND_CHILD, "waiting"),
    ],
    "root-stops-last": [
        ("SubagentStart", CHILD, "running"),
        ("SubagentStart", SECOND_CHILD, "running"),
        ("SubagentStop", SECOND_CHILD, "running"),
        ("SubagentStop", CHILD, "running"),
        ("Stop", None, "waiting"),
    ],
    # Measured too: the root's Stop can arrive before its child's start, which
    # leaves a moment of waiting before the start holds the session again.
    "root-stop-arrives-before-the-start": [
        ("Stop", None, "waiting"),
        ("SubagentStart", CHILD, "running"),
        ("SubagentStop", CHILD, "waiting"),
    ],
    "a-child-started-after-the-first-stopped": [
        ("SubagentStart", CHILD, "running"),
        ("Stop", None, "running"),
        ("SubagentStart", SECOND_CHILD, "running"),
        ("SubagentStop", CHILD, "running"),
        ("SubagentStop", SECOND_CHILD, "waiting"),
    ],
}


@pytest.mark.parametrize("order", ORDERS.values(), ids=ORDERS.keys())
def test_several_children_finish_independently(
    tmp_path: Path, order: list[tuple[str, str | None, str]]
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)

    observed = []
    for event, child, _expected in order:
        publish(a, event, child)
        if child is not None and event == "SubagentStart":
            publish(a, "UserPromptSubmit", child)
        observed.append(run_of(a).state)

    assert observed == [expected for _event, _child, expected in order]
    assert recorded(a)["liveSubagents"] == []


# --- A child's interruption and other terminal events --------------------------


@pytest.mark.parametrize("event", ["Interrupt", "Stop", "SessionEnd"])
def test_a_childs_own_end_neither_ends_nor_stops_its_parent(
    tmp_path: Path, event: str
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    (work,) = WorkStore(a).active()[0]
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")

    publication = publish(a, event, CHILD)

    assert publication.work == "unchanged"
    assert WorkStore(a).active()[0] == [work]
    assert (run_of(a).state, run_of(a).turn_started_at) == ("running", None)
    # Only the boundary takes the child out of the live set.
    publish(a, "SubagentStop", CHILD)
    assert run_of(a).state == "waiting"


# What ``work show`` adds under a run whose session lists a sub-agent: the
# harness's way to end a daemon-hosted Codex session (#374).
CODEX_WAY_OUT = (
    "Dashpot lists a sub-agent until Codex reports that it stopped, which an "
    "interrupted one may never do, so if none is still working, end that "
    "session's client (a daemon-hosted thread ends about 60 s after its last "
    "client leaves)"
)


def test_an_interrupted_child_looks_like_a_working_one_until_the_session_ends(
    tmp_path: Path,
) -> None:
    # Measured on 0.160.0 (#374): a controller's ``turn/interrupt`` on one
    # child's own turn publishes no hook at all, and the root's next prompt
    # and Stop arrive while its sibling still works, so neither tells the
    # interrupted child from the working one (ADR 0016's bounded risk).
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    for event, child in [
        ("SubagentStart", SECOND_CHILD),
        ("SubagentStart", CHILD),
        ("Stop", None),
        ("UserPromptSubmit", SECOND_CHILD),
        ("UserPromptSubmit", CHILD),
        # CHILD is interrupted here; then the root's next turn.
        ("UserPromptSubmit", None),
        ("Stop", None),
    ]:
        publish(a, event, child)

    assert recorded(a)["liveSubagents"] == [CHILD, SECOND_CHILD]
    assert (run_of(a).state, run_of(a).turn_started_at) == ("running", None)
    shown = show_issue_work(a, lookup=codex_lookup)
    assert shown[0].startswith("codex pid 4242: build-observer (I_observer) since ")
    assert shown[1:] == [
        f"  codex pid 4242 has 2 sub-agents listed as working ({CHILD}, "
        f"{SECOND_CHILD}). {CODEX_WAY_OUT}"
    ]

    publish(a, "SubagentStop", SECOND_CHILD)

    assert run_of(a).state == "running"
    assert show_issue_work(a, lookup=codex_lookup)[1:] == [
        f"  codex pid 4242 has 1 sub-agent listed as working ({CHILD}). {CODEX_WAY_OUT}"
    ]
    # The way out: the thread's end clears it with its run, and a new
    # incarnation starts with no live children.
    assert publish(a, "SessionEnd").work == "ended"
    assert show_issue_work(a, lookup=codex_lookup) == [
        "no active Issue work at this worktree"
    ]
    assert runs(a) == []


def test_a_new_incarnation_clears_a_silently_interrupted_child(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")
    publish(a, "UserPromptSubmit", CHILD)

    publish(a, "SessionStart")
    publish(a, "Stop")

    assert run_of(a).state == "waiting"
    assert len(show_issue_work(a, lookup=codex_lookup)) == 1


def test_work_show_names_only_the_sub_agents_of_each_runs_own_session(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    bound_session(a, SIBLING, issue="fix-crash")
    publish(a, "SubagentStart", CHILD, session=SIBLING)

    shown = show_issue_work(a, lookup=codex_lookup)

    assert len(shown) == 3
    (line,) = [index for index, text in enumerate(shown) if text.startswith("  ")]
    # The line follows the sibling's run, the session that lists the child.
    assert "fix-crash" in shown[line - 1]
    assert shown[line] == (
        f"  codex pid 4242 has 1 sub-agent listed as working ({CHILD}). {CODEX_WAY_OUT}"
    )


def test_an_interrupted_root_turn_still_waits_for_its_child(tmp_path: Path) -> None:
    # Measured on 0.160.0 (#374): a controller's ``turn/interrupt`` of the
    # root's turn, or Esc in a daemon-attached terminal, while the root waits
    # on a child publishes the root's ``Interrupt`` and no ``Stop``; the
    # child works on and publishes its ``SubagentStop`` as usual, so nothing
    # is stranded.
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "UserPromptSubmit", CHILD)

    publish(a, "Interrupt")

    assert (run_of(a).state, run_of(a).turn_started_at) == ("running", None)
    assert len(show_issue_work(a, lookup=codex_lookup)) == 2
    publish(a, "SubagentStop", CHILD)
    assert run_of(a).state == "waiting"
    assert len(show_issue_work(a, lookup=codex_lookup)) == 1


def test_the_roots_end_ends_the_run_with_a_child_still_live(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")

    publication = publish(a, "SessionEnd")

    assert publication.work == "ended"
    assert WorkStore(a).active()[0] == []
    assert runs(a) == []


# --- Duplicate and late boundaries ---------------------------------------------


def test_a_repeated_start_is_one_live_child(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")

    publish(a, "SubagentStop", CHILD)

    assert run_of(a).state == "waiting"


def test_a_repeated_stop_changes_nothing_after_the_first(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "SubagentStart", SECOND_CHILD)
    publish(a, "Stop")
    publish(a, "SubagentStop", CHILD)

    # A repeat of the first child's stop must not end the second's work.
    publish(a, "SubagentStop", CHILD)
    assert run_of(a).state == "running"

    publish(a, "SubagentStop", SECOND_CHILD)
    publish(a, "SubagentStop", SECOND_CHILD)
    assert run_of(a).state == "waiting"


def test_a_late_stop_during_the_next_turn_keeps_that_turns_clock(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")
    publish(a, "SubagentStop", CHILD)
    publish(a, "UserPromptSubmit")
    turn = run_of(a).turn_started_at
    assert turn is not None

    publish(a, "SubagentStop", CHILD)

    assert (run_of(a).state, run_of(a).turn_started_at) == ("running", turn)
    publish(a, "Stop")
    assert run_of(a).state == "waiting"


def test_a_stop_for_a_child_never_seen_starting_changes_nothing(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "Stop")

    publish(a, "SubagentStop", CHILD)

    assert run_of(a).state == "waiting"
    assert recorded(a)["liveSubagents"] == []


def test_a_new_incarnation_forgets_its_previous_children(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")

    publish(a, "SessionStart")
    publish(a, "Stop")

    assert run_of(a).state == "waiting"


# --- A child never binds, switches or moves its parent's work --------------------


def test_a_child_working_elsewhere_never_moves_or_rebinds_its_parent(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    bound_session(a)
    (work,) = WorkStore(a).active()[0]
    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")

    # The child's events report another Worktree, and its shell claims its
    # own thread there.
    for event in ("UserPromptSubmit", "Stop"):
        assert publish(b, event, CHILD).work == "unchanged"
    with pytest.raises(IssueWorkError):
        start_issue_work(
            b, "fix-crash", lookup=codex_lookup, environ={"CODEX_THREAD_ID": CHILD}
        )
    publish(b, "SubagentStop", CHILD)

    assert WorkStore(a).active()[0] == [work]
    assert WorkStore(b).active()[0] == []
    assert stored(b) is None
    assert stored(b, CHILD) is None
    (run,) = runs(a, b)
    assert (run.session_id, run.issue_id, run.working_directory, run.state) == (
        CODEX_SESSION,
        "I_observer",
        str(a),
        "waiting",
    )


# --- Another root thread on the same Host Process ------------------------------


def test_a_sibling_thread_on_the_same_host_is_unaffected(tmp_path: Path) -> None:
    a, _b = two_worktrees(tmp_path)
    bound_session(a)
    bound_session(a, session=SIBLING, issue="fix-crash")
    publish(a, "Stop", session=SIBLING)

    publish(a, "SubagentStart", CHILD)
    publish(a, "Stop")
    publish(a, "UserPromptSubmit", CHILD)

    states = {run.session_id: (run.state, run.issue_id) for run in runs(a)}
    assert states == {
        CODEX_SESSION: ("running", "I_observer"),
        SIBLING: ("waiting", "I_crash"),
    }
    assert recorded(a, SIBLING)["liveSubagents"] == []

    # The sibling's own turn and end leave the delegating thread's child live.
    publish(a, "UserPromptSubmit", session=SIBLING)
    publish(a, "SessionEnd", session=SIBLING)
    assert run_of(a).state == "running"

    publish(a, "SubagentStop", CHILD)
    assert [(run.session_id, run.state) for run in runs(a)] == [
        (CODEX_SESSION, "waiting")
    ]
