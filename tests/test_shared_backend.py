import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Barrier
from types import SimpleNamespace

import pytest

import dashpot.work as work_module
from dashpot.agents import observe_agent_runs
from dashpot.hook_records import (
    HookRecordStore,
    locate_agent_session,
    session_directory,
    sessions_at_worktree,
)
from dashpot.work import identify_agent_session, start_issue_work, stop_issue_work
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore, end_session_runs
from factories import CLAUDE, CODEX, EARLIER, LATER, hook_record, hook_record_document
from helpers import present, table_lookup, unobservable
from test_work import target

A = "session-a"
B = "session-b"


def setup_sessions(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    hook_record(a, A, "codex", CODEX, at=EARLIER)
    hook_record(b, B, "codex", CODEX, at=LATER)
    return a, b, [session_directory(a), session_directory(b)]


def test_named_session_is_not_placed_at_other_sessions_worktree(tmp_path):
    a, _b, stores = setup_sessions(tmp_path)
    location = locate_agent_session(
        stores, present(CODEX), session_id=A, process_key=(CODEX.pid, CODEX.started_at)
    )
    assert location is not None
    assert location.record.session_id == A, (
        f"Asked for {A}, selected {location.record.session_id}"
    )
    assert location.worktree == a


def test_distinct_confirmed_sessions_have_distinct_work_store_keys(tmp_path):
    a, b, stores = setup_sessions(tmp_path)
    first = identify_agent_session(
        present(CODEX), environ={"CODEX_THREAD_ID": A}, worktree=a, stores=stores
    )
    second = identify_agent_session(
        present(CODEX), environ={"CODEX_THREAD_ID": B}, worktree=b, stores=stores
    )
    assert (first.session_id, second.session_id) == (A, B)
    assert first.session_key != second.session_key, (
        f"Distinct sessions share {first.session_key}"
    )


def test_session_end_preserves_different_session_on_same_backend(tmp_path):
    a, b, _stores = setup_sessions(tmp_path)
    for root, session_id, issue_id in [(a, A, "I_a"), (b, B, "I_b")]:
        WorkStore(root).start(
            ActiveWork(
                session_key="codex-shared-process",
                harness="codex",
                session_label="codex shared backend",
                session_process=SessionProcess(
                    pid=CODEX.pid, started_at=CODEX.started_at
                ),
                issue_id=issue_id,
                issue_reference=issue_id,
                binding_provenance="explicit-reference",
                started_at=EARLIER,
                working_directory=str(root),
                branch="main",
                session_id=session_id,
            )
        )
    ended = end_session_runs([a, b], "codex", A, (CODEX.pid, CODEX.started_at))
    assert WorkStore(a).active() == ([], [])
    assert [w.session_id for w in WorkStore(b).active()[0]] == [B], (
        f"Ending {A} also ended {[w.session_id for _, w in ended]}"
    )


def test_start_preserves_other_sessions_issue_binding(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import dashpot.work as work_module
    from dashpot.work import start_issue_work

    a, b, stores = setup_sessions(tmp_path)
    monkeypatch.setattr(work_module, "worktree_root", lambda path: path)
    monkeypatch.setattr(work_module, "repository_worktrees", lambda root: [a, b])
    monkeypatch.setattr(work_module, "reachable_hook_stores", lambda roots: stores)
    monkeypatch.setattr(
        work_module,
        "resolve_issue",
        lambda root, reference, timeout: SimpleNamespace(
            id=reference, reference=reference
        ),
    )
    monkeypatch.setattr(
        work_module,
        "Git",
        lambda *args, **kwargs: SimpleNamespace(maybe=lambda *args: "main"),
    )
    # B's fresh hook permits its first opt-in; A's next turn is then freshest.
    start_issue_work(b, "I_b", lookup=present(CODEX), environ={"CODEX_THREAD_ID": B})
    hook_record(a, A, "codex", CODEX, at="2026-08-30T03:50:00Z")
    messages = start_issue_work(
        a, "I_a", lookup=present(CODEX), environ={"CODEX_THREAD_ID": A}
    )
    assert [w.issue_id for w in WorkStore(a).active()[0]] == ["I_a"]
    assert [w.issue_id for w in WorkStore(b).active()[0]] == ["I_b"], messages


def test_identity_only_lookup_is_a_passing_control(tmp_path):
    a, _b, stores = setup_sessions(tmp_path)
    location = locate_agent_session(stores, present(CODEX), session_id=A)
    assert location is not None
    assert location.record.session_id == A
    assert location.worktree == a


def test_session_end_distinct_process_is_a_passing_control(tmp_path):
    test_root = tmp_path / "b"
    WorkStore(test_root).start(
        ActiveWork(
            session_key="codex-other-process",
            harness="codex",
            session_label="codex",
            session_process=SessionProcess(
                pid=CODEX.pid + 1, started_at=CODEX.started_at
            ),
            issue_id="I_b",
            issue_reference="I_b",
            binding_provenance="explicit-reference",
            started_at=EARLIER,
            working_directory=str(test_root),
            branch="main",
            session_id=B,
        )
    )
    assert (
        end_session_runs([test_root], "codex", A, (CODEX.pid, CODEX.started_at)) == []
    )
    assert [w.issue_id for w in WorkStore(test_root).active()[0]] == ["I_b"]


@pytest.fixture
def roots(tmp_path, monkeypatch):
    a, b, stores = setup_sessions(tmp_path)
    monkeypatch.setattr(work_module, "worktree_root", lambda path: path)
    monkeypatch.setattr(work_module, "repository_worktrees", lambda root: [a, b])
    monkeypatch.setattr(work_module, "reachable_hook_stores", lambda roots: stores)
    monkeypatch.setattr(
        work_module,
        "resolve_issue",
        lambda root, reference, timeout: SimpleNamespace(
            id=reference, reference=reference
        ),
    )
    monkeypatch.setattr(
        work_module,
        "Git",
        lambda *args, **kwargs: SimpleNamespace(maybe=lambda *args: "main"),
    )
    return a, b


def start(root, session_id, issue="I_a"):
    return start_issue_work(
        root, issue, lookup=present(CODEX), environ={"CODEX_THREAD_ID": session_id}
    )


def recorded(root, session_id=A, *, key="legacy-process-key", process=CODEX):
    return ActiveWork(
        session_key=key,
        harness="codex",
        session_label="codex shared backend",
        session_process=SessionProcess(pid=process.pid, started_at=process.started_at)
        if process
        else None,
        issue_id="I_a",
        issue_reference="I_a",
        binding_provenance="explicit-reference",
        started_at=EARLIER,
        working_directory=str(root),
        branch="main",
        session_id=session_id,
    )


def test_operations_never_lock_another_named_sessions_worktree(roots, monkeypatch):
    a, b = roots
    start(b, B, "I_b")
    (before,) = WorkStore(b).active()[0]
    original = WorkStore.locked

    @contextmanager
    def own_lock(store, key):
        assert store.directory != WorkStore(b).directory, (
            "A attempted a write lock in B Worktree"
        )
        with original(store, key):
            yield

    monkeypatch.setattr(WorkStore, "locked", own_lock)
    start(a, A)
    start(a, A, "I_next")
    stop_issue_work(a, lookup=present(CODEX), environ={"CODEX_THREAD_ID": A})
    start(a, A)
    end_session_runs([a, b], "codex", A, CODEX.key)
    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == [before]


@pytest.mark.parametrize("simultaneous", [False, True])
def test_same_worktree_starts_have_independent_bindings(
    roots, monkeypatch, simultaneous
):
    a, _b = roots
    hook_record(a, B, "codex", CODEX, at="2026-08-30T05:00:00Z")
    if simultaneous:
        barrier = Barrier(2)

        def resolve(root, reference, timeout):
            barrier.wait(timeout=5)
            return SimpleNamespace(id=reference, reference=reference)

        monkeypatch.setattr(work_module, "resolve_issue", resolve)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(start, a, sid, issue)
                for sid, issue in [(A, "I_a"), (B, "I_b")]
            ]
            for future in futures:
                future.result(timeout=10)
    else:
        start(a, A)
        start(a, B, "I_b")
    active, diagnostics = WorkStore(a).active()
    assert diagnostics == []
    assert {(w.session_id, w.issue_id) for w in active} == {(A, "I_a"), (B, "I_b")}
    stop_issue_work(a, lookup=present(CODEX), environ={"CODEX_THREAD_ID": A})
    assert [(w.session_id, w.issue_id) for w in WorkStore(a).active()[0]] == [
        (B, "I_b")
    ]


@pytest.mark.parametrize("kind", ["missing", "unreadable", "ended"])
def test_unavailable_named_evidence_cannot_borrow_activity_location_or_work(
    roots, kind
):
    a, b = roots
    work = recorded(a)
    WorkStore(a).start(work)
    path = session_directory(a) / f"{A}.json"
    if kind == "missing":
        path.unlink()
    elif kind == "unreadable":
        path.write_text("not json")
    else:
        document = hook_record_document(a, A, "codex", CODEX, state="ended")
        path.write_text(json.dumps(document))
    with pytest.raises(RuntimeError):
        start(a, A)
    runs, _ = observe_agent_runs(
        {"project:test": [target(a), target(b)]}, a / "global", lookup=present(CODEX)
    )
    by_id = {r.id: r for r in runs}
    assert by_id[work.run_id].state == "unknown"
    assert by_id[work.run_id].last_activity_at is None
    assert by_id[f"codex-session:{B}"].issue_id is None
    assert WorkStore(a).active()[0] == [work]


def test_shared_backend_does_not_produce_duplicate_run_diagnostics(roots):
    a, b = roots
    start(a, A)
    start(b, B, "I_b")
    runs, diagnostics = observe_agent_runs(
        {"project:test": [target(a), target(b)]}, a / "global", lookup=present(CODEX)
    )
    assert {r.issue_id for r in runs} == {"I_a", "I_b"}
    assert diagnostics == []


@pytest.mark.parametrize(
    "harness,process,variable",
    [
        ("codex", CODEX, "CODEX_THREAD_ID"),
        ("claude-code", CLAUDE, "CLAUDE_CODE_SESSION_ID"),
    ],
)
def test_named_identity_agrees_across_visible_and_sandbox_routes(
    tmp_path, harness, process, variable
):
    hook_record(tmp_path, A, harness, process)
    stores = [session_directory(tmp_path)]
    first = identify_agent_session(
        present(process), worktree=tmp_path, stores=stores, environ={variable: A}
    )
    second = identify_agent_session(
        unobservable("isolated-namespace"),
        worktree=tmp_path,
        stores=stores,
        environ={variable: A},
    )
    assert first.session_key == second.session_key
    assert first.session_id == second.session_id == A
    assert first.session_process == second.session_process


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"CODEX_THREAD_ID": "missing"},
        {"CODEX_THREAD_ID": "bad/id"},
        {"DASHPOT_AGENT_SESSION": "codex:missing"},
    ],
)
def test_unconfirmed_claim_never_degrades_to_process_mutation(roots, environment):
    a, b = roots
    with pytest.raises(RuntimeError):
        start_issue_work(a, "I_a", lookup=present(CODEX), environ=environment)
    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == []


def test_legacy_named_storage_is_selected_by_identity_and_not_renamed(roots):
    a, b = roots
    legacy = recorded(a)
    WorkStore(a).start(legacy)
    runs, _ = observe_agent_runs(
        {"project:test": [target(a), target(b)]}, a / "global", lookup=present(CODEX)
    )
    assert next(r for r in runs if r.issue_id == "I_a").id == legacy.run_id
    assert WorkStore(a).active()[0] == [legacy]
    start(a, A, "I_next")
    (restarted,) = WorkStore(a).active()[0]
    assert restarted.session_key == legacy.session_key
    assert restarted.session_id == A
    assert restarted.issue_id == "I_next"


@pytest.mark.parametrize("process", [CODEX, None])
def test_legacy_unnamed_ownership_is_refused_without_duplication(roots, process):
    a, b = roots
    legacy = recorded(b, None, process=process)
    WorkStore(b).start(legacy)
    with pytest.raises(RuntimeError, match="ownership of legacy Agent Run"):
        start(a, A)
    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == [legacy]
    assert end_session_runs([a, b], "codex", A, CODEX.key) == []


def test_conflicting_candidates_are_refused_before_any_new_work(roots):
    a, _b = roots
    first = recorded(a, key="first")
    second = replace(first, session_key="second")
    WorkStore(a).start(first)
    WorkStore(a).start(second)
    with pytest.raises(RuntimeError, match="conflicting Agent Runs"):
        start(a, A)
    assert WorkStore(a).active()[0] == [first, second]


def test_conflicting_destination_identity_is_not_overridden_by_its_filename(roots):
    a, _b = roots
    session = identify_agent_session(
        present(CODEX),
        worktree=a,
        stores=[session_directory(a)],
        environ={"CODEX_THREAD_ID": A},
    )
    other = recorded(a, B, key=session.session_key)
    WorkStore(a).start(other)
    with pytest.raises(RuntimeError, match="occupied"):
        start(a, A)
    assert WorkStore(a).active()[0] == [other]


@pytest.mark.parametrize("operation", ["start", "stop", "end"])
def test_changed_record_is_not_replaced_or_removed_after_selection(
    roots, monkeypatch, operation
):
    a, _b = roots
    before = recorded(a)
    after = replace(before, issue_id="I_changed", started_at=LATER)
    WorkStore(a).start(before)
    original = WorkStore.locked
    changed = False

    @contextmanager
    def replace_before_lock(store, key):
        nonlocal changed
        if not changed:
            changed = True
            with original(store, key):
                from dashpot.work_store import WorkStoreRecord

                store.replace(key, WorkStoreRecord.of(after).model_dump(by_alias=True))
        with original(store, key):
            yield

    monkeypatch.setattr(WorkStore, "locked", replace_before_lock)
    if operation == "end":
        assert end_session_runs([a], "codex", A, CODEX.key) == []
    else:
        with pytest.raises(RuntimeError, match="changed"):
            if operation == "start":
                start(a, A, "I_next")
            else:
                stop_issue_work(
                    a, lookup=present(CODEX), environ={"CODEX_THREAD_ID": A}
                )
    assert WorkStore(a).active()[0] == [after]


def test_late_end_cannot_clear_same_native_identity_on_a_new_runtime(tmp_path):
    resumed = replace(CODEX, pid=5252)
    work = recorded(tmp_path, process=resumed)
    WorkStore(tmp_path).start(work)
    assert end_session_runs([tmp_path], "codex", A, CODEX.key) == []
    assert end_session_runs([tmp_path], "codex", A, None) == []
    assert WorkStore(tmp_path).active()[0] == [work]
    assert end_session_runs([tmp_path], "codex", A, resumed.key) == [(tmp_path, work)]


def test_late_end_cannot_clear_a_run_started_after_ending_evidence(tmp_path):
    work = replace(recorded(tmp_path), started_at=LATER)
    WorkStore(tmp_path).start(work)
    assert end_session_runs([tmp_path], "codex", A, CODEX.key, ended_at=EARLIER) == []
    assert WorkStore(tmp_path).active()[0] == [work]


def test_hook_end_preserves_a_replacement_runtime_record(tmp_path):
    resumed = replace(CODEX, pid=5252)
    hook_record(tmp_path, A, "codex", resumed, at=LATER)
    store = HookRecordStore(session_directory(tmp_path))
    before = store.read(A)
    store.write(
        hook_record_document(tmp_path, A, "codex", CODEX, state="ended", at=EARLIER)
    )
    assert store.read(A) == before


def test_same_native_identity_does_not_authorize_a_live_runtime_takeover(roots):
    a, _b = roots
    previous_process = replace(CODEX, pid=5252)
    work = recorded(a, process=previous_process)
    WorkStore(a).start(work)
    lookup = table_lookup({CODEX.pid: CODEX, previous_process.pid: previous_process})
    with pytest.raises(RuntimeError, match="another live or unobservable runtime"):
        start_issue_work(a, "I_next", lookup=lookup, environ={"CODEX_THREAD_ID": A})
    assert WorkStore(a).active()[0] == [work]


def test_harness_scopes_location_folding_and_observation(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    hook_record(a, A, "codex", CODEX, at=EARLIER)
    hook_record(b, A, "claude-code", CODEX, at=LATER)
    stores = [session_directory(a), session_directory(b)]
    location = locate_agent_session(
        stores, present(CODEX), harness="codex", session_id=A
    )
    assert location is not None
    assert location.worktree == a
    assert [
        (r.record.harness, r.worktree)
        for r in sessions_at_worktree(a, stores, present(CODEX))
    ] == [("codex", a)]
    work = recorded(a)
    WorkStore(a).start(work)
    end_session_runs([a], "claude-code", A, CODEX.key)
    assert WorkStore(a).active()[0] == [work]


def test_equal_native_ids_from_two_harnesses_coexist_in_one_hook_store(tmp_path):
    hook_record(tmp_path, A, "claude-code", CLAUDE, at=EARLIER)
    hook_record(tmp_path, A, "codex", CODEX, at=LATER)
    stores = [session_directory(tmp_path)]
    lookup = table_lookup({CODEX.pid: CODEX, CLAUDE.pid: CLAUDE})
    locations = sessions_at_worktree(tmp_path, stores, lookup)
    assert {item.record.harness for item in locations} == {"codex", "claude-code"}
    for harness in ("codex", "claude-code"):
        found = locate_agent_session(stores, lookup, harness=harness, session_id=A)
        assert found is not None
        assert found.record.harness == harness
    store = HookRecordStore(stores[0])
    store.write(
        hook_record_document(
            tmp_path, A, "codex", CODEX, state="ended", at="2026-08-31T00:00:00Z"
        )
    )
    assert [
        item.record.harness for item in sessions_at_worktree(tmp_path, stores, lookup)
    ] == ["claude-code"]


@pytest.mark.parametrize("competing", ["named", "unnamed", "none"])
def test_relocation_requires_an_unoccupied_session_destination(
    roots, monkeypatch, competing
):
    import dashpot.hook_records as hooks
    from dashpot.work_store import RelocationIntent

    a, b = roots
    resumed = replace(CODEX, pid=5252)
    pending = replace(recorded(a), relocation=RelocationIntent(str(b), EARLIER))
    WorkStore(a).start(pending)
    existing = recorded(
        b, None if competing == "unnamed" else A, key="different-key", process=resumed
    )
    if competing != "none":
        WorkStore(b).start(existing)
    # A same-label Claude hook must not prevent a valid Codex continuation.
    HookRecordStore(session_directory(b)).write(
        hook_record_document(b, A, "claude-code", CLAUDE, at=EARLIER)
    )
    document = hook_record_document(b, A, "codex", resumed, at=LATER)
    HookRecordStore(session_directory(b)).write(document)
    monkeypatch.setattr(hooks, "repository_worktrees", lambda *args, **kwargs: [a, b])
    monkeypatch.setattr(
        hooks,
        "reachable_hook_stores",
        lambda roots, directory=None: [session_directory(a), session_directory(b)],
    )
    moved = hooks.complete_session_work_relocation(
        document, resumed, table_lookup({resumed.pid: resumed, CLAUDE.pid: CLAUDE})
    )
    if competing == "none":
        assert moved
        assert WorkStore(a).active()[0] == []
        (continued,) = WorkStore(b).active()[0]
        assert continued.run_id == pending.run_id
        assert continued.issue_id == pending.issue_id
        assert continued.relocation is None
    else:
        assert not moved
        assert WorkStore(a).active()[0] == [pending]
        assert WorkStore(b).active()[0] == [existing]


def test_stop_preflights_legacy_ownership_before_deleting_any_run(roots):
    a, b = roots
    own = recorded(a)
    legacy = recorded(b, None, process=replace(CODEX, pid=5252))
    WorkStore(a).start(own)
    WorkStore(b).start(legacy)
    with pytest.raises(RuntimeError, match="ownership of legacy Agent Run"):
        stop_issue_work(a, lookup=present(CODEX), environ={"CODEX_THREAD_ID": A})
    assert WorkStore(a).active()[0] == [own]
    assert WorkStore(b).active()[0] == [legacy]


def test_two_compared_mutations_of_one_expected_run_cannot_both_win(tmp_path):
    store = WorkStore(tmp_path)
    before = recorded(tmp_path)
    store.start(before)
    barrier = Barrier(2)

    def update(issue):
        barrier.wait(timeout=5)
        return store.replace_current(before, replace(before, issue_id=issue))

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(update, ["I_first", "I_second"]))
    assert sorted(outcomes) == [False, True]
    assert store.active()[0][0].issue_id in {"I_first", "I_second"}


def test_work_store_start_cannot_overwrite_occupied_state(tmp_path):
    store = WorkStore(tmp_path)
    before = recorded(tmp_path)
    store.start(before)
    for replacement in (
        replace(before, session_id=B),
        replace(before, issue_id="I_next"),
    ):
        with pytest.raises(RuntimeError, match="occupied"):
            store.start(replacement)
        assert store.active()[0] == [before]
