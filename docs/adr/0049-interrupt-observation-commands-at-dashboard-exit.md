---
status: accepted
date: 2026-09-18
---

# Interrupt observation commands at dashboard exit

Quitting the dashboard sometimes returned the shell prompt a second or more
after the screen was torn down, and up to the command timeout on a slow
GitHub ([#255](https://github.com/ned2/dashpot/issues/255)). Measured in a
pseudo-terminal, an idle quit took 0.3 seconds, 0.2 of which is Textual's
own input-thread teardown; a quit while the four `gh api graphql` queries of
a refresh were in flight took 1.5–1.7 seconds, all of it after `App.run()`
had returned. The same numbers reproduce at the commit before the refactor
series (#230–#254), so this is not a regression of that series but a
property of how commands run: every observation and query runs on a
`ThreadPoolExecutor` thread, `shutdown(wait=False, cancel_futures=True)`
cancels only the futures that have not started, and
`concurrent.futures.thread._python_exit` joins every pool thread at
interpreter exit. A thread blocked in `subprocess.run` holds the process
open until its `git` or `gh` child exits. With the default fifteen-second
refresh and queries of one to two seconds, roughly one quit in ten landed
in that window.

Three remedies were weighed. Daemon pool threads are not available: the
standard executor dropped them in Python 3.9 and `_python_exit` joins its
threads regardless. `os._exit` after `App.run()` returns skips the join but
also skips interpreter finalisation, and would hide any thread the app
failed to shut down rather than reveal it. What actually holds the thread is
the child process, and a child can be told to stop.

## Decision

The dashboard interrupts the observation and query commands still running
when it exits, and refuses the ones their threads would start next. Each
`DashpotApp` owns one `RunningCommands` registry
(`src/dashpot/core/commands.py`), and the threads of its refresh and query
pools adopt it as they start, through the executor's initializer and a
context variable; `run_command` holds each Interruptible Command it spawns
in the registry the calling thread adopted, and a thread that adopted none —
a one-shot `dashpot` command, a test — is never registered. The app's
`on_unmount`, after shutting its pools down, calls `interrupt()`, which
closes the registry and sends each running child a termination request
rather than a kill, so Git removes its lock files on the way out. The
thread's `communicate` returns at once, and the command's caller sees a
`CommandError` — never a result with a signal exit code that a `maybe` read
could mistake for Git answering "no" — so an interrupted observation is a
failed observation, which the cancelled worker discards.

An observation that runs several commands in turn tolerates one failing —
identity resolution continues with its next batch — so it would start its
next child as soon as the current one stopped. Once the registry is closed,
`run_command` refuses an Interruptible Command before it spawns, and a child
that registers after the close, started between its caller's check and the
interruption, is signalled as it registers. The close is permanent and
`interrupt()` neither joins nor waits: the registry belongs to one exited
dashboard, whose pool threads have nothing left to run, so no later command
of any other owner — the test suite runs many apps per worker process — can
find itself refused, and the exit path never blocks the event loop before
Textual closes its driver. The threads themselves end once their interrupted
commands have raised, which is milliseconds later, and interpreter exit's
join of them is then immediate.

The registry travels as a context variable rather than a thread-local so a
pool thread that fans out reaches its children: `GitHubGateway.graphql_many`
runs each request in a copy of the calling thread's context, so the `gh`
children of a batched identity resolution are as interruptible as the
thread that started them.

Which commands may be abandoned follows the line
[ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)
draws: observation never mutates, so nothing is lost by stopping it, and
every observation and query command is interruptible by default. The two
named mutations opt out and run to completion through an exit: a Remote
Fetch ([ADR 0014](0014-fetch-remotes-on-explicit-key-press.md)) and a
Cleanup ([ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md))
each build their Git adapter with `non_interactive_runner(...,
interruptible=False)`, so a confirmed `git worktree remove` is never left
half-way through a Worktree and a `git fetch --prune` finishes the ref
updates it began. A Cleanup preview only reads, so its adapter is built
interruptible like any observation. A Worktree launch has its own bounded
runner and is not registered, and the Agent Run observation's `ps` runs
through `subprocess.run` under a two-second timeout of its own, short enough
not to need interrupting. Every adapter that constructs its own runner —
`Git(root, timeout)` at a dozen sites — needs nothing threaded through,
because the registry reaches a command through the thread that runs it, not
through the adapter.

## Consequences

Quitting with queries in flight now takes the same 0.3 seconds as an idle
quit, measured with the same pseudo-terminal harness. A quit during a
Remote Fetch or a confirmed Cleanup still waits for that command, bounded
by the command timeout, which is the price of never abandoning a mutation
someone asked for; interrupting a Remote Fetch too would be safe for Git
and is the first thing to revisit if that wait is noticed. The termination
request reaches the child alone: a helper the child started that kept the
output pipe open would hold the thread until the command timeout, which no
observation command of Dashpot's does. Textual's 0.2
seconds of input-thread teardown remain: its key thread polls at a hundred
milliseconds and `disable_input` joins it before one final poll. The
exit path is covered by `tests/test_app_exit.py`, which runs the shipped
app over an observation holding a real sleeping child and asserts the
thread is released when the app exits, the registry by
`tests/test_commands.py`, and the fan-out's context by
`tests/test_github.py`. The
[Textual implementation notes](../textual-implementation-notes.md#refresh-concurrency)
record that executor work is released at exit by interrupting its command,
not by cancelling the worker.
