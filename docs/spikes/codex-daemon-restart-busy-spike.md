---
status: research
date: 2026-11-03
---

# Codex managed daemon restart with a turn running

[Issue #398](https://github.com/ned2/dashpot/issues/398) asks for two
measurements that [#356](https://github.com/ned2/dashpot/issues/356) left
open: a `codex app-server daemon restart` sent while one thread's turn is
running, and a restart started by the daemon's updater after it installs a
release. [ADR 0086](../adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)
rests on a daemon that is stopping running no `SessionEnd` until its turns
have drained. Were a restart to end an idle thread while another turn held
the daemon open past the settler's 10 s window, that idle thread's run would
end rather than be orphaned. #356 measured the drain for `daemon stop` only,
at `codex-cli` 0.160.0.

This run measures the first on the pinned **codex-cli 0.166.0** and answers
the second from source alone: by the maintainer's decision, no fixture runs
with the updater on
([AGENTS.md](../../AGENTS.md#leading-parallel-issue-work)).

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it.
  Every timing is this run's single sample;
- **source**: read from the 0.166.0 source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`. Nothing checks these mechanically;
- **inference**: what follows, which neither the trace nor the source
  states.

## Answers

1. **A restart with a turn running drains as a stop does** (measured).
   `daemon restart` was sent while thread R7's turn waited on the model,
   held for 20 s, and thread R8 sat idle. Neither thread's `SessionEnd`
   began until R7's turn had finished: the model was released
   20.0 s after the restart began, R7's `Stop` hook followed, and
   both `SessionEnd` hooks, the idle R8's included, began 0.31 s
   after the release, within 1 ms of each other, from the old
   daemon. The old daemon exited 0.24 s after the idle thread's hook
   began, and `daemon restart` returned after 20.8 s.
2. **Dashpot leaves both runs orphaned** (measured). Each settler saw the
   old daemon gone inside its 10 s window and left its run, so both were
   listed as Orphaned Agent Runs under the old daemon, with no last
   activity time. The replacement daemon reloaded both threads. Its own
   stop, at the end of the run, ran their `SessionEnd` hooks from the
   replacement and left both orphans as they were.
3. **ADR 0086 holds** (inference from 1 and 2). The risk its consequences
   name, an idle thread ended while another turn holds the daemon open, does
   not arise for a restart either. No settler change follows. The 10 s
   window is unchanged on `main`
   (`SETTLE_SECONDS = 10.0` in `src/dashpot/sessions/deferred_end.py`).
4. **An updater restart takes the same path** (source; not measured). The
   updater stops the daemon through the same graceful stop as `daemon
   restart` and `daemon stop`, so measurement 1 bears on it by source. It
   publishes the same `SessionEnd` from a `--managed-daemon` host
   ([updater restart by source](#updater-restart-by-source)).
5. **About one updater restart per adopted release** (inference). Eight
   stable releases came out between 2026-10-05 and 2026-10-29, 0.160.1 to
   0.166.0, about one every three days. A daemon with the updater on, its
   default, would restart about that often, each time with whatever turns
   were running then.
6. **Every 0.160.0 claim of the restart acceptance run still holds**
   (measured). The run repeats #356's scenarios at 0.166.0 and the
   verifier checks the same claims, among them the stop with a turn
   running, whose `daemon stop` returned after 23.3 s.

## Reproduce

The run needs Node 24, the pinned Codex binary, and this checkout's `.venv`.
It needs no credentials: a loopback model stands in for the Responses API.
Run the runner detached, from outside any harness, so that its refusal check
passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-356/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-356/verify.mjs <fixture root>/trace.jsonl 0.166.0 --strict
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. `SPIKE_FIXTURE_PARENT` names another parent directory for the fixture
root than the system temporary directory. A run takes about five minutes.

- [Runner](../../scripts/experiments/codex-356/run.mjs): #356's acceptance
  run, extended. Its isolation is #356's: an isolated `HOME`, `CODEX_HOME`
  and XDG directories, the daemon's updater off, a loopback Responses API,
  and Dashpot's real Codex publisher as a trusted command hook. Codex now
  runs as `codex` through a symlink on a fixture-local `PATH`, and the
  environment record keeps the binary's SHA-256. The `restart-busy`
  scenario follows #356's `stop-busy`:
  - `daemon start` starts a third daemon.
  - R7 in the fixture's other Worktree runs `work start 7`, and R8 in the
    main checkout runs `work start 8`. The view shows both runs live under
    the third daemon.
  - R7 starts a turn whose model request the fixture holds for 20 s. Once
    that request arrives, the hook wrapper starts a detached waiter for
    each `SessionEnd`, as in #356.
  - `daemon restart` runs. The runner waits for the replacement, the two
    `SessionEnd` hooks, their waiters and their settlers.
  - A client lists the replacement's loaded threads.
  - `daemon stop` stops the replacement, and the run ends with Dashpot's
    view and Event Log.
  The runner counts the shared `/tmp/codex-daemon-<uid>/` before and after
  and removes only the entries derived from the fixture's own socket paths,
  never the directory.
- [Verifier](../../scripts/experiments/codex-356/verify.mjs): checks every
  #356 claim, and on a trace with the `restart-busy` scenario the claims of
  this document, timings within a tolerance. It still accepts the 0.160.0
  trace, with a note that the runner and verifier changed since it was
  recorded.
- [Trace](measurements/issue-398-codex-trace.jsonl): metadata only, with
  the fixture's paths, home directory and host name rewritten to
  placeholders. Its environment record gives the binary's SHA-256,
  `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`.

## Tested configuration and evidence boundary

- `codex-cli` 0.166.0, `x86_64-unknown-linux-musl`, on Linux. The daemon
  ran from its own copy under the fixture's
  `packages/app-server-daemon/releases/`, as
  `codex app-server --listen unix:// --analytics-default-enabled --managed-daemon`.
- One sample. A turn held for 20 s and one idle thread; a longer turn, more
  threads, or a turn running past the daemon's 60 s shutdown grace were not
  measured. By source, a turn still running at the grace's end is killed
  with the daemon, and no `SessionEnd` runs.
- The fixture's updater was off throughout, so no updater restart ran.
- No network sandbox was available on the machine: the kernel restricts
  unprivileged user namespaces, so writing a namespace's `uid_map` fails.
  The run needed none, since everything it reached was on loopback.

## The restart with a turn running

The timings below are from the trace, relative to the `daemon restart`
command's start unless named otherwise.

| Event | Time |
| --- | --- |
| Model request held for R7's turn released | 20.0 s |
| R7's `Stop` hook begins | 20.04 s |
| R7's and R8's `SessionEnd` hooks begin, from the old daemon | 20.32 s |
| Old daemon exits | 20.56 s |
| `daemon restart` returns | 20.8 s |

The source agrees. `daemon restart` (`restart_with_settings` in
`app-server-daemon/src/lib.rs`) and `daemon stop` (`stop`, same file) call
`stop_with_grace` (`app-server-daemon/src/backend/pid.rs`), which sends
`SIGTERM` and kills the daemon only after the shutdown grace, 60 s by
default and at most 300 s (`app-server-daemon/src/settings.rs`). On the
signal, the app-server stops admitting turns and waits until the running
turns have drained (`ShutdownState::on_signal` and `begin_drain` in
`app-server/src/lib.rs`). Only then does it close its connections and call
`shutdown_threads`, which ends every loaded thread within 10 s
(`shutdown_all_threads_bounded` in
`app-server/src/request_processors/thread_processor.rs`), each running its
`SessionEnd` hook. A `SessionEnd` hook runs for at most 3 s
(`SESSION_END_MAX_TIMEOUT_SEC` in `hooks/src/events/session_end.rs`). The
daemon records its loaded threads for recovery as it stops, and the
replacement reloads them.

Through Dashpot's publisher and settler:

- Both `SessionEnd` hooks reported their Work Store change as `deferred`,
  and both settlers as `unchanged`: each saw the old daemon gone and left
  its run.
- The view after the restart listed R7's and R8's runs as orphaned under
  the old daemon, with no last activity time, and no unbound session.
- The replacement's `thread/loaded/list` named both threads.
- The final `daemon stop` ran both threads' `SessionEnd` hooks from the
  replacement. They started no settler, since neither thread had a run on
  the replacement, and both orphans stayed as they were.
- Every daemon, hook, waiter and settler had exited by the end of the run,
  and the fixture left no entry in the shared daemon directory.

## Updater restart by source

The fixture's updater was off, as AGENTS.md requires for a pinned
experiment, and by the maintainer's decision it stays off. So everything in
this section is source or inference, and none of it is measured.

- **It stops the daemon as `daemon restart` does** (source). After an
  install, the updater calls `try_restart_if_running`
  (`app-server-daemon/src/update_loop.rs`, defined in
  `app-server-daemon/src/lib.rs`). That takes the daemon's operation lock,
  decides whether the running daemon is out of date, and if so calls
  `stop_with_grace` with the configured shutdown grace, the call
  `daemon restart` makes. It then starts the replacement from the new
  release and waits for it. Afterwards the updater re-executes itself from
  the new binary (`reexec_managed_updater`, `update_loop.rs`).
- **It publishes the same `SessionEnd`** (source). The stop is the same
  `SIGTERM` to the same `--managed-daemon` process, so the drain and the
  `SessionEnd` hooks of [the restart above](#the-restart-with-a-turn-running)
  follow, and ADR 0086's settler reads the host's exit as a restart.
- **When it runs** (source). The updater is on unless
  `updater.autoUpdateEnabled` is false (`default_auto_update_enabled` in
  `app-server-daemon/src/settings.rs`). Its first check is 5 min after it
  starts (`INITIAL_UPDATE_DELAY`, `update_loop.rs`) and later checks follow
  every `updater.updateIntervalMinutes`, 60 by default
  (`DEFAULT_UPDATE_INTERVAL_MINUTES`, `settings.rs`).
- **How often** (inference): one restart per release the daemon adopts,
  about every three days at the 2026-10 release rate.

### How to measure it

If the rule ever allows a run with the updater on, this design measures it
without patching Codex. Nothing in it has been run.

- **Where the updater looks** (source). It fetches its install script from
  a fixed URL, `INSTALL_URL` in `update_loop.rs`, which no configuration key
  or environment variable changes. Its HTTP client takes the proxy from the
  environment (`HTTPS_PROXY`, `ALL_PROXY`), and an extra CA from
  `CODEX_CA_CERTIFICATE`, falling back to `SSL_CERT_FILE`. The script must
  contain the guard names `CODEX_INSTALL_IF_LATEST` and
  `CODEX_INSTALL_DAEMON_ONLY`, and runs under `/bin/sh -s` with
  `CODEX_HOME` set. No signature or checksum is checked before it runs: that
  is the real script's job. After it, the selected release must be a stable
  one, named `releases/X.Y.Z-<target>`, with `current` and the
  `auto-update-version` marker naming it.
- **Fixture.** A local CA and a leaf certificate for the install host; a
  loopback `CONNECT` proxy that accepts only the install host, refuses and
  records every other target, and hands the connection to a loopback TLS
  server; and a fake install script that hardlinks the pinned release under
  a new release name and points `current` and the marker at it. The
  restart decision includes the executable's path
  (`ExecutableIdentity` in `app-server-daemon/src/managed_install.rs`), so
  the pinned bytes under a new name force a restart. The scenario holds one
  turn and one idle thread, waits about 5.5 min for the first check, and
  records the hooks, both daemons' argument vectors and the timings.
- **Writes.** Under the fixture's `CODEX_HOME`, apart from the updater's
  own socket and lock in the shared `/tmp/codex-daemon-<uid>/`, named from
  the fixture's own paths as the daemon's are.
- **Risk.** With no network sandbox, nothing on the machine proves the
  updater cannot reach the network. Were its client to ignore the proxy, it
  would fetch the real install script, which would download a real release
  into the fixture's `CODEX_HOME`. The source says it honours the proxy,
  and the proxy's record would show a bypass only after the fact.

## Validation

```bash
node scripts/experiments/codex-356/verify.mjs docs/spikes/measurements/issue-398-codex-trace.jsonl
node scripts/experiments/codex-356/verify.mjs docs/spikes/measurements/issue-356-codex-trace.jsonl 0.160.0
uv run python scripts/trace_drift.py scripts/experiments/codex-356/verify.mjs docs/spikes/measurements/issue-398-codex-trace.jsonl
```

The first verifies this run's claims and #356's at 0.166.0. The second
verifies the 0.160.0 trace, noting that the runner and verifier changed
since it was recorded. The third checks every hash the new trace records
against the checkout.
