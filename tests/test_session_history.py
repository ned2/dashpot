"""Which of a session's hook records places it, asked of one ``SessionHistory`` (#545)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dashpot.core.model import AgentRun
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions.agents import WorkerEvidence, observe_agent_runs
from dashpot.sessions.hook_records import (
    HookRecordStore,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import (
    SessionHistory,
    locate_agent_session,
    reachable_hook_stores,
    session_histories,
    sessions_at_worktree,
    sessions_with_live_subagents,
)
from dashpot.sessions.processes import ProcessIdentity, ProcessLookup
from dashpot.sessions.session_matching import session_storage_key
from factories import CODEX, EARLIER, LATER, hook_record_document
from helpers import present, table_lookup
from test_work import CODEX_SESSION, target, two_worktrees

OTHER_CODEX = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
WORKER = "019a0000-0000-7000-8000-000000000001"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def put(
    store: Path,
    at: Path,
    process: ProcessIdentity | None,
    *,
    state: str = "running",
    stamp: str = EARLIER,
    **fields: Any,
) -> None:
    """Store the session's record placing it at ``at``, as a store holds one."""
    store.mkdir(parents=True, exist_ok=True)
    document = hook_record_document(
        at, CODEX_SESSION, "codex", process, state=state, at=stamp
    )
    HookRecordStore(store).replace(
        session_storage_key("codex", CODEX_SESSION), {**document, **fields}
    )


def history(stores: list[Path], lookup: ProcessLookup) -> SessionHistory:
    (found,) = session_histories(stores, lookup)
    return found


def observed(*worktrees: Path, lookup: ProcessLookup) -> list[AgentRun]:
    """The Agent Runs the dashboard observes at ``worktrees``."""
    runs, _diagnostics = observe_agent_runs(
        {"project:test": [target(worktree) for worktree in worktrees]},
        state_directory(),
        lookup=lookup,
    )
    return runs


def placed_at(runs: list[AgentRun]) -> list[tuple[str | None, str]]:
    return [(run.observation_target, run.state) for run in runs]


def test_of_two_records_stamped_alike_the_first_read_places_the_session(
    tmp_path: Path,
) -> None:
    # The dashboard used to keep the last one read; every reader now keeps
    # the first, a Worktree's own store before the next and the global one.
    a, b = two_worktrees(tmp_path)
    put(session_directory(a), a, CODEX, state="waiting")
    put(session_directory(b), b, CODEX)
    stores = reachable_hook_stores([a, b])
    lookup = present(CODEX)

    found = history(stores, lookup)

    assert [scanned.record.worktree for scanned in found.records] == [a, b]
    assert found.freshest_current is found.freshest
    assert found.freshest.record.worktree == a
    assert placed_at(observed(a, b, lookup=lookup)) == [(str(a), "waiting")]
    location = locate_agent_session(
        stores, lookup, session_id=CODEX_SESSION, harness="codex"
    )
    assert location is not None
    assert location.worktree == a
    assert [found.worktree for found in sessions_at_worktree(a, stores, lookup)] == [a]
    assert sessions_at_worktree(b, stores, lookup) == []


@pytest.mark.parametrize("older", [CODEX, None], ids=["same-process", "unnamed"])
def test_a_fresher_end_ends_an_older_record_of_its_own_process_or_of_none(
    tmp_path: Path, older: ProcessIdentity | None
) -> None:
    # The ended record keeps the worker its session left working (ADR 0095).
    # The dashboard used to observe the older record at A as running, which
    # Cleanup and placement read as over; all of them now read it over.
    a, b = two_worktrees(tmp_path)
    put(session_directory(a), a, older)
    put(
        session_directory(b),
        b,
        CODEX,
        state="ended",
        stamp=LATER,
        event="SessionEnd",
        liveSubagents=[WORKER],
    )
    stores = reachable_hook_stores([a, b])
    lookup = present(CODEX)

    found = history(stores, lookup)

    assert found.current == ()
    assert found.placing is found.freshest
    assert found.retained_subagents == {WORKER}
    assert observed(a, b, lookup=lookup) == []
    assert sessions_at_worktree(a, stores, lookup) == []
    location = locate_agent_session(
        stores, lookup, session_id=CODEX_SESSION, harness="codex"
    )
    assert location is not None
    assert (location.worktree, location.record.outcome) == (b, "ended")
    # Its worker is still listed, by the ended record that keeps it.
    assert [
        (found.worktree, found.record.live_subagents)
        for found in sessions_with_live_subagents([a, b], stores, lookup)
    ] == [(b, (WORKER,))]


def test_a_fresher_end_of_another_process_leaves_the_older_record_current(
    tmp_path: Path,
) -> None:
    # A client of the session still runs at A after another one, fresher at
    # B, is gone. Cleanup, placement and claims used to read the session as
    # over, and so let A be removed under the live client; every reader now
    # places it at A, where the dashboard already did.
    a, b = two_worktrees(tmp_path)
    put(session_directory(a), a, OTHER_CODEX, liveSubagents=[WORKER])
    put(session_directory(b), b, CODEX, state="waiting", stamp=LATER)
    stores = reachable_hook_stores([a, b])
    lookup = table_lookup({OTHER_CODEX.pid: OTHER_CODEX})

    found = history(stores, lookup)

    assert found.freshest.record.outcome == "gone"
    current = found.freshest_current
    assert current is not None
    assert (current.record.worktree, current.record.outcome) == (a, "live")
    assert placed_at(observed(a, b, lookup=lookup)) == [(str(a), "running")]
    assert [found.worktree for found in sessions_at_worktree(a, stores, lookup)] == [a]
    location = locate_agent_session(
        stores, lookup, session_id=CODEX_SESSION, harness="codex"
    )
    assert location is not None
    assert (location.worktree, location.record.outcome) == (a, "live")
    assert [
        (found.worktree, found.record.live_subagents)
        for found in sessions_with_live_subagents([a, b], stores, lookup)
    ] == [(a, (WORKER,))]
    assert "agent-session" in {
        blocker.kind for blocker in assess_worktree_occupancy(a, [a, b], lookup)
    }


def test_a_session_placed_at_no_observation_target_is_not_observed_at_an_older_one(
    tmp_path: Path,
) -> None:
    # The dashboard used to fall back to the older record at A when the
    # session's freshest record placed it outside every Observation Target;
    # Cleanup already found nothing of it at A, and now the dashboard agrees.
    a, b = two_worktrees(tmp_path)
    elsewhere = (tmp_path / "elsewhere").resolve()
    elsewhere.mkdir()
    put(session_directory(a), a, CODEX)
    put(state_directory(), elsewhere, CODEX, state="waiting", stamp=LATER)
    stores = reachable_hook_stores([a, b])
    lookup = present(CODEX)

    current = history(stores, lookup).freshest_current

    assert current is not None
    assert current.record.worktree == elsewhere
    assert observed(a, b, lookup=lookup) == []
    assert sessions_at_worktree(a, stores, lookup) == []


@pytest.mark.parametrize("older", [CODEX, None], ids=["same-process", "unnamed"])
def test_observation_prunes_the_record_a_fresher_end_superseded(
    tmp_path: Path, older: ProcessIdentity | None
) -> None:
    # The ended record keeps nothing, so the pass prunes it; were the record
    # it superseded kept, the next pass would read that one current again.
    # Worker attribution, which prunes nothing, no longer reads the worker
    # the superseded record lists as running either.
    a, b = two_worktrees(tmp_path)
    put(session_directory(a), a, older, liveSubagents=[WORKER])
    put(session_directory(b), b, CODEX, state="ended", stamp=LATER)
    stores = reachable_hook_stores([a, b])
    lookup = present(CODEX)

    evidence = WorkerEvidence.recorded(stores, lookup)
    assert evidence.state("codex", CODEX_SESSION, None, WORKER) is None
    assert observed(a, b, lookup=lookup) == []
    assert observed(a, b, lookup=lookup) == []
    assert session_histories(stores, lookup) == []


def test_a_superseded_record_lists_no_worker_beside_a_fresher_live_one(
    tmp_path: Path,
) -> None:
    # A's live record lists a worker; a fresher end of the same Host Process
    # superseded it before the session started again at B. A superseded
    # record lists no Sub-agent, whatever record is the freshest.
    a, b = two_worktrees(tmp_path)
    put(session_directory(a), a, CODEX, liveSubagents=[WORKER])
    put(
        state_directory(),
        b,
        CODEX,
        state="ended",
        stamp="2026-08-30T03:36:00.000000Z",
        event="SessionEnd",
    )
    put(session_directory(b), b, CODEX, state="waiting", stamp=LATER)
    stores = reachable_hook_stores([a, b])
    lookup = present(CODEX)

    found = history(stores, lookup)

    assert [scanned.record.worktree for scanned in found.superseded] == [a]
    assert [scanned.record.worktree for scanned in found.subagent_listings] == [b]
    assert sessions_with_live_subagents([a, b], stores, lookup) == []
