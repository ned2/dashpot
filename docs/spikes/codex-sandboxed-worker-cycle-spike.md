---
status: research
date: 2026-10-06
---

# Codex sandboxed Worker cycle experiment

The experiment for [Issue #639](https://github.com/ned2/dashpot/issues/639)
runs the `dashpot-execute-issues` skill's Codex sandbox check and resume
command on the pinned **codex-cli 0.160.0**, through the TUI a person uses,
then has sandboxed workers run a whole Worker cycle under it.
[ADR 0148](../adr/0148-let-workers-write-their-own-arc-ledger-files-and-commit-under-codexs-sandbox.md)
chose the grant, the Worktree Root and the main checkout's `.git` as
writable roots with the network on, from the
[Codex workspace-write Workers experiment](codex-workspace-write-workers-spike.md).
That experiment set the roots in configuration through `codex app-server`,
ran no gate, hook or push, and ran only `approval_policy = "never"`, so the
command the skill gives and what a Worker can do under it were unmeasured.

Here the **lead** is the root thread of a Codex Agent Session, and a
**worker** is one of its [Sub-agents](../domain-language.md). The fixture
threads only delegate, so they are a skill's Lead and Workers in shape only.
Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **documented**: read from the pinned release's `codex --help`;
- **trace only**: the retained trace shows it, but the verifier does
  not check it;
- **unknown**: with the reason it is unknown.

## Answers

On Linux, with the fixture repository described [below](#reproduce):

| Question | Answer | Basis |
| --- | --- | --- |
| What does the skill's resume command, without its cache options, give the lead? | `workspace-write`, with the Worktree Root and the main checkout's `.git` as writable roots and network access on, as Codex records in each turn's context. The skill's three checks pass, `git worktree add` works, and a write outside every root is still refused. | measured |
| And each worker? | The same sandbox, roots and network setting, under the lead's approval policy. | measured |
| What does Codex's default for a trusted project give instead? | `workspace-write` with no added roots and the network off. All three checks fail: the two writes with `Read-only file system`, and `git ls-remote` with `failed to open socket: Operation not permitted`. | measured |
| Does the resume work straight after the old client exits? | Not at once when the old client's thread was hosted by Codex's background app-server. A resume that adds roots runs in-process instead, and is refused with `thread-store conflict: … already has an active writer` until that server unloads the idle thread, about 60 s after its last client leaves. The TUI shows the conversation read-only, says it is open in another app, and `r` retries. The retry that resumed sent no prompt within 5 s, so the runner typed the one the command line had carried. | measured |
| What does `--add-dir` do under `--sandbox read-only`? | Codex prints `Error adding directories: Ignoring --add-dir (…) because the effective permissions do not allow additional writable roots. Switch to workspace-write or danger-full-access to allow them.` and the client exits with status 1, so no turn runs. | measured |
| Which Worker-cycle steps does the grant alone allow? | Editing the Worktree, writing the worker's Arc Ledger file, and pushing. Preparing the environment, the gate and the commit fail: uv and pre-commit write their caches under `~/.cache`, outside every root. | measured |
| What fixes those refused writes? | Either moving both caches inside the Worktree Root, with `UV_CACHE_DIR` and `PRE_COMMIT_HOME`, or adding `~/.cache` with one more `--add-dir`. Each completes the whole cycle, the commit's hook included. | measured |
| Do the skill's three checks show that gap? | No. They all pass under the grant alone, while the gate and the commit fail. | measured |
| Can the resume command set those variables for every shell? | Yes. `-c 'shell_environment_policy.set.UV_CACHE_DIR="<path>"'`, whose value is a TOML string, and its `PRE_COMMIT_HOME` twin reach each worker's shell and the Git hook its commit runs, with nothing in the worker's command. The unquoted form was not run. | measured |
| What does a refused write do under `-a on-request`? | A plain command fails as it does under `never`, without an ask, for the lead and a worker alike. Only a command the agent itself marks for escalation raises an ask. | measured |
| Who can answer that ask? | Only the person, in the lead's terminal. A worker's ask appears there too, labelled `Thread: Agent (<id>)` with `o to open thread`. The lead's turn had ended when it appeared. | measured |
| What does declining a worker's ask do, with the lead's turn ended? | Escape, "No, and tell Codex what to do differently", cuts the worker's command short with `aborted by user` and aborts the worker's whole turn. The worker sends no further request, so its lead gets no hand-back. | measured |
| What does the lead's model see of a worker's ask, with its turn ended? | Nothing: the trace records no request from the lead after the ask, and the lead got no later turn before the runner sent `/exit` about 2 minutes on. The verifier does not check that absence. | trace only |
| What does a Worker's ask do to a Lead waiting on it, as the skill's Lead waits in its turn? | Not measured: the fixture lead ended its turn after spawning its worker. | unknown |
| Does `gh` work under the grant? | Not measured: the fixture has no forge, and a `gh` run against GitHub would need the person's credentials. `git ls-remote` and the push show the network setting reaches a worker; whether `gh` writes outside the roots, as its configuration or cache, is unknown. | unknown |
| Does any of this hold on macOS? | Out of scope: no macOS host was available. Codex applies its Seatbelt sandbox there rather than bubblewrap. | unknown |

Every check ran with `NoNewPrivs` set and under a seccomp filter, so each
refusal there is the sandbox's. A control write outside every writable root failed
in every scenario that ran a turn.

## Reproduce

The run needs Node 24, uv, Git with `git http-backend`, `script` from
util-linux, and the pinned Codex binary; it needs no Dashpot installation.
uv downloads pre-commit and its dependencies from PyPI, so the run needs the
network. Run the runner detached, from outside any harness, so that its
refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-639/run.mjs ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/codex 0.160.0 > run.log 2>&1'
node scripts/experiments/codex-639/verify.mjs /var/tmp/dashpot-codex-639-SUFFIX/trace.jsonl 0.160.0
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. A run takes about five minutes, most of it the resume waiting for the
background app-server to unload the first thread.

- [Runner](../../scripts/experiments/codex-639/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process.
    - It builds a disposable repository under `/var/tmp`, outside every
      Dashpot Project. Unlike the system temporary directory, `/var/tmp` is
      not writable under `workspace-write` by default, so the fixture is
      sandboxed as a checkout in a home directory is; `/tmp` and `TMPDIR`
      stay writable, as they would for a real Worker.
    - Worktrees go in the Worktree Root `<repository>.worktrees/`, where
      `dashpot worktree create` puts them.
    - Codex gets an isolated `HOME` and `CODEX_HOME`, so `~/.cache` is the
      fixture's. It runs as `codex` through a symlink on a fixture-local
      `PATH`, with its updater and update check off. The background
      app-server it starts serves only that `CODEX_HOME`. The run lists the
      shared `/tmp/codex-daemon-<uid>/` directory before and after, and
      never removes anything from it.
  - **Terminal.** Each lead is the TUI, run under `script` in a 160-column
    terminal. The runner types and presses keys as a person would, and
    keeps labelled tails of each screen.
  - **Repository.** The fixture has a `pyproject.toml` with a
    `pre-commit` dev dependency and a committed `uv.lock`, a
    `.pre-commit-config.yaml` with one local hook, and a tracked
    `.githooks/pre-commit` that runs `uv run --locked pre-commit hook-impl`,
    as this Repository's does, named by `core.hooksPath`. Its `origin` is
    `git http-backend` behind a loopback HTTP server, so a push is a
    network connection.
  - **Model.** A loopback Responses API follows a fixed plan per prompt or
    worker task. Its `fixture-v2` model declares multi-agent v2, so a lead
    spawns workers with `spawn_agent`.
  - **Checks.** [`checks.mjs`](../../scripts/experiments/codex-639/checks.mjs)
    runs the skill's three checks word for word, a control write outside
    every root, and `git worktree add` for each worker the lead will
    spawn. It ran before the skill gained its fourth check, of where the
    caches go, so that check did not run, and the lead's shell's cache
    variables are not recorded.
  - **Cycle.** [`cycle.mjs`](../../scripts/experiments/codex-639/cycle.mjs)
    runs one Worker cycle in the worker's Worktree, each step whatever the
    step before it did: `uv sync --locked --group dev`, an edit to a
    tracked file, `uv run --locked pre-commit run --all-files`, a commit
    with the tracked hook running, a push, and an append to the worker's
    Arc Ledger file in the main checkout. It records each step's outcome
    and every path a refused write names.
- [Independent trace verifier](../../scripts/experiments/codex-639/verify.mjs)
  checks every **measured** claim against the trace without importing the
  runner. It also checks the runner's sources against the hashes the trace
  records.
- [Retained trace](measurements/issue-639-codex-trace.jsonl) is the complete
  metadata stream of the run: 143 records, SHA-256
  `26f6089adda613e930e65ac7df94170c73367249e2531b62d133292b318927f8`.
  The fixture root appears as `$ROOT`, the fixture's home as `$HOME`, the
  experiment directory as `$EXPERIMENT`, and the person's home as `~`.
  Where a terminal's partial redraw broke the fixture root's path, its
  name appears as `<fixture>`. One screen tail starts inside that name, so
  its whole random suffix shows there, which names only a removed
  temporary directory.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Codex | codex-cli 0.160.0, `x86_64-unknown-linux-musl` |
| Platform | Linux 7.0, x86_64, with bubblewrap 0.11.1 installed; Node 24.18 |
| Tools | uv 0.12, Git 2.53, Python 3.14 |
| Base commit | `ffda2ab0` |
| Lead | the TUI, resumed with the skill's command, with and without its cache options |
| Approval policy | `never`, and `on-request` in the ask scenario |

The run leaves out:

- **macOS**, where Codex applies its Seatbelt sandbox;
- **`gh`**, for the reason in the answers;
- **this Repository's own gates**: the fixture's gate is one pre-commit
  hook. A repository whose tools write other caches outside the roots
  shows them as refused writes the same way;
- **a Python uv installs itself**, under `~/.local/share/uv` unless
  `UV_PYTHON_INSTALL_DIR` names another: the fixture used the system
  Python;
- **a real model's choices**: the fixture model only issues the calls its
  plan names, and marks a command for escalation only where the plan says.

## 1. The checks and the resume

Each scenario resumes the same session, the seed's lead thread, after the
previous client exited.

| Scenario | Command | Three checks | Outside write |
| --- | --- | --- | --- |
| Seed | `codex -C <checkout>`, Codex's default for a trusted project | all fail | refused |
| Grant | the skill's resume command without its cache options | all pass | refused |
| Add-dir | Grant's command and `--add-dir ~/.cache` | all pass | refused |
| Env | the skill's resume command: Grant's and its two `shell_environment_policy.set` options | all pass | refused |
| Read-only | `--sandbox read-only` with Grant's `--add-dir` and network options | no turn | no turn |
| Ask | Grant's command and `-a on-request` | not run | see [3](#3-asks-under-on-request) |

The seed ran in Codex's background app-server. The resume with `--add-dir` ran in-process in the
TUI instead, as Codex's own log records, and the background server still
held the seed's thread. The resume was refused until the server logged the
thread as having no subscribers and unloaded it. The TUI showed the
transcript read-only, said the conversation was open in another app, and
offered `r` to retry. The runner pressed it about every 15 s; the
server's log puts the unload about 60 s after the seed exited, and the
fifth retry, about 71 s after, resumed. That retry sent no prompt within
5 s, so the runner typed the one the command line had carried, and the
resumed lead's first request came about 77 s after the seed exited.
Later resumes followed an in-process client, which releases the thread when it exits,
and none waited.

Each turn's record shows the sandbox Codex applied. Under the grant, the
writable roots were the checkout, the Worktree Root, the main checkout's
`.git`, `/tmp` and `TMPDIR`. Each root's own `.git`, `.agents` and `.codex`
stay read-only, except that the main checkout's `.git` named as a root is
writable.

## 2. The Worker cycle

| Step | No override | `UV_CACHE_DIR` in the Worktree Root | Both caches in the Worktree Root | `--add-dir ~/.cache` | Both caches by `shell_environment_policy` |
| --- | --- | --- | --- | --- | --- |
| `uv sync --locked --group dev` | refused at `~/.cache/uv` | yes | yes | yes | yes |
| Edit a tracked file | yes | yes | yes | yes | yes |
| `pre-commit run --all-files` | refused at `~/.cache/uv` | refused at `~/.cache/pre-commit` | yes | yes | yes |
| Commit, hook running | refused at `~/.cache/uv` | refused at `~/.cache/pre-commit` | yes | yes | yes |
| Push | yes | yes | yes | yes | yes |
| Append to the Arc Ledger file | yes | yes | yes | yes | yes |

The first three columns are three workers of the grant scenario. The
second and third set the variables in the worker's own command, and the
last sets them in the session's configuration, which every shell the
session starts inherits. The commit's refusal comes from the hook, which
runs `uv run`: Git itself could write the main checkout's `.git`.

No other path was refused.

Moving a cache into the Worktree Root keeps the sandbox's boundary where
ADR 0148 put it. Adding `~/.cache` widens it: every agent of the session
can then write every tool's cache, and code planted in one, such as a
pre-commit hook environment, runs the next time that tool runs outside the
sandbox.

## 3. Asks under on-request

The lead and then its worker each ran two writes outside every root.

1. **A plain write** failed with `Read-only file system`, exit status 1,
   and no ask, for both.
2. **The lead's escalated write**, `sandbox_permissions:
   "require_escalated"` with a justification, raised the TUI's overlay:
   "Would you like to run the following command?", with the command, the
   justification and three choices. The runner pressed `y`, and the command
   ran outside the sandbox.
3. **The worker's escalated write** raised the same overlay in the lead's
   terminal, headed `Thread: Agent (<id>)` and offering `o to open thread`.
   The lead's turn had already ended. The runner pressed Escape, the
   overlay's "3. No, and tell Codex what to do differently (esc)". Codex
   recorded the worker's command as `aborted by user` and its turn as
   aborted, and the worker sent no further model request. The lead sent
   none after the ask either, so its model saw nothing of it.

The fixture lead ends its turn once it has spawned its worker. The skill's
Lead stays in its turn, waiting on its Workers, and what it sees of a
Worker's ask then is not measured.

## What this means for the skill

- **The resume command is right,** with one wait. When the old thread
  ran in Codex's background app-server, that server keeps it until about a
  minute after its last client leaves; until then the resumed TUI is
  read-only, and `r` retries. A prompt on the command line may not be sent
  after a retry, so the person repeats it.
- **The grant needs the caches, and the checks do not show it.** A
  Worker's gate and commit fail on the first cache their tools write
  outside the roots, while the three checks pass. So the skill adds a
  fourth check, of where the caches go. Moving each cache into the
  Worktree Root with
  `-c 'shell_environment_policy.set.<NAME>="<path>"'` completes the cycle
  without widening the sandbox, so the skill's command carries those
  options, and `--add-dir ~/.cache` is the wider alternative.
- **`read-only` fails loudly.** `--add-dir` under `read-only` stops the
  client, rather than being ignored.
- **`on-request` adds asks only the person can answer,** and declining a
  worker's ask while its lead's turn has ended ends that worker's turn
  without a report.
  `never` remains the skill's assumption: a refused write fails as a
  command, which a Worker can report.
- **Nothing here argues against ADR 0148's grant.** With the caches inside
  the Worktree Root, a sandboxed Worker completed every step.

## Validation

The retained trace passed the independent verifier at the run's base,
`ffda2ab0`, and every script it names matched the hash the run recorded. No
fixture Codex process was left to kill when the run ended.
