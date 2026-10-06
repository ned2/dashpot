---
status: research
date: 2026-10-06
---

# Codex workspace-write Workers experiment

The experiment for [Issue #637](https://github.com/ned2/dashpot/issues/637)
measures what a Codex lead thread and its workers can write under Codex's
`workspace-write` sandbox, on the pinned **codex-cli 0.160.0**. The
`dashpot-execute-issues` skill passes mid-flight messages through files, and
every earlier Codex worker experiment ran `danger-full-access`. So none of
them said whether a sandboxed Worker can edit and commit in its Worktree at
all, or where it can leave a message.

Here the **lead** is the root thread of a Codex Agent Session, and a
**worker** is one of its [Sub-agents](../domain-language.md), as in the
[Codex worker mechanics experiment](codex-worker-mechanics-spike.md). The
fixture threads only delegate, so they are a skill's Lead and Workers in
shape only. Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **documented**: read from the pinned release's `codex --help` or source,
  here or in an earlier experiment that this one cites;
- **unknown**: with the reason it is unknown.

## Answers

Every answer holds for `approval_policy = "never"` with network access off,
on Linux; [the evidence boundary](#tested-configuration-and-evidence-boundary)
says what that leaves out.

| Question | Answer | Basis |
| --- | --- | --- |
| Which sandbox does a worker run under? | Its lead's, including the writable roots that lead was started with. Under v2 and v1 alike for the Worktrees directory as a root; only a v2 worker ran with the main checkout's `.git` added. | measured |
| Can a lead give a worker a directory or a sandbox of its own? | No. Under v2, `spawn_agent`'s arguments are a message, a task name, a fork setting, a model, a reasoning effort and an agent type, and no spawn argument of either tool set sets a worker's directory. | documented ([codex-420](codex-worker-mechanics-spike.md#1-launch) and [its location section](codex-worker-mechanics-spike.md#6-location), from the 0.160.0 source) |
| Where can a lead in the main checkout and its workers write, with no writable roots? | Anywhere in the main checkout except its `.git`, including tracked files and `.dashpot/state/`. Nowhere in a linked Worktree, not even its tracked `README.md`, and in no Git directory. | measured |
| Can a worker commit in its own Worktree then? | No. It cannot edit the Worktree's files, and `git add` fails creating `<main>/.git/worktrees/<name>/index.lock`. | measured |
| With the Worktrees directory as a writable root? | The Worktree's tracked files become editable. Its `.dashpot/state/` can be created from nothing, and Git ignores it. `git add` still fails on the same lock file, for the lead as much as the worker: the main checkout's `.git` stays read-only. | measured |
| With the main checkout's `.git` as a writable root as well? | Everything the probe tries succeeds, the commit included. So does a write to `.git/hooks/`. | measured |
| Can a lead bound in a linked Worktree write the main checkout's `.dashpot/state/`? | No. It can read it, and it writes only within its own Worktree's files. It cannot commit there either. | measured |
| Does a v2 lead's `send_message` reach a running worker? | It is queued. It does not cut short the command the worker is running. The worker's next model request carries it, after that command's output. | measured |
| How does a person grant the writable roots? | At session start, with `--add-dir <DIR>`, "additional directories that should be writable alongside the primary workspace", or `[sandbox_workspace_write] writable_roots` in configuration. This run set the configuration key per thread; `--add-dir` was not run. | documented |
| Can a worker escalate a refused write under another approval policy? | Not measured. Every thread ran `approval_policy = "never"`, which refuses without asking. | unknown |

A control write outside every writable root failed in every probe. Every
probe's shell ran with `CODEX_SANDBOX_NETWORK_DISABLED=1` and `NoNewPrivs`
set, so each outcome is the sandbox's.

## Reproduce

The run needs Node 24 and the pinned Codex binary; it needs no Dashpot
installation. Run the runner detached, from outside any harness, so that its
refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-637/run.mjs ~/.codex/packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl/codex 0.160.0 > run.log 2>&1'
node scripts/experiments/codex-637/verify.mjs /tmp/dashpot-codex-637-SUFFIX/trace.jsonl 0.160.0
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. A run takes under a minute.

- [Runner](../../scripts/experiments/codex-637/run.mjs):
  - **Isolation.** It refuses to start under a Codex, Claude Code or
    OpenCode process.
    - It builds a disposable repository under the temporary directory,
      outside every Dashpot Project.
    - Each probe gets its own linked Worktree, beside the main checkout as
      `<repository>.worktrees/<name>`, where `dashpot worktree create`
      puts them. No Worktree has a `.dashpot/state/` before its probe.
    - The main checkout holds a mail directory with a broadcast in it, at
      `.dashpot/state/skills/dashpot-execute-issues/arcs/fixture/mail/`.
      That is where the design review of #637 proposed Worker mailboxes,
      inside an Arc's ledger directory. The runner creates it, outside the
      sandbox.
    - Codex gets an isolated `HOME`, `CODEX_HOME`, XDG directories and
      `TMPDIR`. It runs as `codex` through a symlink on a fixture-local
      `PATH`, as a loopback `codex app-server`.
  - **Sandbox.** `sandbox_mode = "workspace-write"` with network access off.
    The fixture is under the system temporary directory, which
    `workspace-write` makes writable by default. The run therefore excludes
    both it and `TMPDIR`, as for a checkout outside them. Each thread's
    `thread/start` reply records the sandbox Codex applied.
  - **Model.** A loopback Responses API follows a fixed plan per prompt or
    worker task, as in the codex-420 run: `fixture-v2` declares
    multi-agent v2, and `fixture-model` gets v1.
  - **Probe.** [`probe.mjs`](../../scripts/experiments/codex-637/probe.mjs)
    tries each write in turn and prints one line of outcomes. That line
    reaches the runner as the tool output in the agent's next model
    request. A worker runs the probe after a `cd` into its Worktree; a lead
    runs it where its thread started. The probe commits with
    `core.hooksPath=/dev/null`, so no Git hook runs.
- [Independent trace verifier](../../scripts/experiments/codex-637/verify.mjs)
  checks every **measured** claim against the trace without importing the
  runner. It also checks the runner's sources against the hashes the trace
  records.
- [Retained trace](measurements/issue-637-codex-trace.jsonl) is the complete
  metadata stream of the run: 72 records, SHA-256
  `9b3548957d0d7ac498f6015b3860d449ac606e234b5f9db6bb0490dbc2381634`. The
  fixture root appears as `$ROOT`, and the home directory as `~`.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Codex | codex-cli 0.160.0, `x86_64-unknown-linux-musl` |
| Platform | Linux 7.0, x86_64, with bubblewrap 0.11.1 installed; Node 24.18 |
| Base commit | `895bf1dc` |
| Sandbox | `workspace-write`, network off, `/tmp` and `TMPDIR` excluded |
| Approval policy | `never` |
| Lead | a `codex app-server` thread on the loopback model; no TUI, no hooks |

The run leaves out:

- **macOS**, where Codex applies its Seatbelt sandbox differently;
- **any other approval policy**, under which a refused command might be
  retried with escalation;
- **the network**: no push and no `gh` command ran;
- **a repository's own tooling**: no gate ran, and no Git hook did;
- **a real model's choices**: the fixture model only issues the calls its
  plan names.

## 1. Where each side can write

Each probe tries the same targets. `L` is the main checkout, where every
lead but one started, and `W` is the probe's own linked Worktree.

| Target | No roots | Worktrees directory | Worktrees directory and `L/.git` | Lead in a linked Worktree |
| --- | --- | --- | --- | --- |
| `L/.dashpot/state/…/mail/<label>.md`, written | yes | yes | yes | no |
| `L/.dashpot/state/…/mail/broadcast.md`, read | yes | yes | yes | yes |
| `L/README.md`, a tracked file, edited | yes | yes | yes | no |
| `L/.git/` | no | no | yes | no |
| `L/.git/hooks/` | no | no | yes | no |
| `W`'s Git directory, `L/.git/worktrees/<name>/` | no | no | yes | no |
| `W/README.md`, a tracked file, edited | no | yes | yes | yes |
| `W/.dashpot/state/`, created with its `.gitignore` | no | yes | yes | yes |
| `git check-ignore` on that state | n/a | yes | yes | yes |
| `git add` and `git commit` in `W` | no | no | yes | no |
| A directory outside every root | no | no | no | no |

The first three columns hold for the lead's own probe, its v2 worker's and
its v1 worker's alike. The third column has no v1 worker. The last column is
a lead thread started in its own linked Worktree, so `W` is that Worktree.

The `check-ignore` row has no answer with no roots: there the state's `mkdir`
fails with `ENOENT` rather than `EROFS`, and the `git check-ignore` that
follows fails to start with `EPERM`, though the `git add` after it starts.

The `.git` column is the sandbox's own protection: a writable root keeps its
`.git` read-only, and a linked Worktree's Git directory is inside the main
checkout's `.git`. Naming `L/.git` as a writable root of its own lifts that
protection for all of it.

That grant has a security cost. The probe wrote a file into `.git/hooks/`,
and by the same grant a sandboxed agent can write `.git/config`, which names
`core.hooksPath` and `core.fsmonitor`. Code planted there runs when `git` is
next run outside the sandbox, by the person or by a tool. Withholding `L/.git`
does not close that path where a repository keeps its hooks in tracked files,
as this one does in `.githooks/`: `L`'s tracked files are writable with no
roots at all.

## 2. Commit

With no roots, and with the Worktrees directory alone, `git add` fails with
`fatal: Unable to create '$ROOT/repository/.git/worktrees/<name>/index.lock':
Read-only file system`, and the commit after it fails the same way. This is
so for the lead's own probe as much as for its workers'. Every Git operation
that writes the index, a ref or an object writes under `L/.git`, so neither
a sandboxed worker nor its lead can commit in a linked Worktree unless
`L/.git` is writable.

## 3. A message to a running worker

1. The v2 lead spawned a worker whose first command sleeps 8 s.
2. The lead slept 2 s itself, sent `send_message` to `/root/worker_s`, and
   waited.
3. The worker's command ran its full 8 s.
4. The worker's next model request, about 8 s after its first, carried the
   lead's message as an `agent_message` item, after the command's output.
5. The lead's `wait_agent` returned when the worker finished.

A running worker therefore gets a message at its next model request, which
comes no sooner than the end of the command it is running. Delivery to an
idle worker was not measured; the codex-420 run measured that a message to a
finished worker only queues.

## What this means for the skill

Under `approval_policy = "never"`, and before any repository tooling or
network use:

- **No writable roots.** A Codex Worker cannot do its Issue in a linked
  Worktree at all: it cannot even edit a tracked file. Its messaging is the
  smaller problem.
- **The Worktrees directory as a writable root.** A Worker can edit its
  Worktree and keep ignored state there. Neither it nor its Lead can commit,
  so only the person, or a command outside the sandbox, could commit for
  them.
- **`L/.git` writable as well.** A Worker can commit. Whether it can then run
  this Repository's commit hooks, gates and push is not measured; the
  sandbox's network setting decides the push. The grant also opens
  `.git/hooks/` and `.git/config` to the agent, which is a decision for the
  person rather than a default.
- **Messaging.** Wherever a Worker can work, it can read and write the main
  checkout's `.dashpot/state/`, because `L` is its Lead's workspace. A Worker
  mailbox there works in every configuration measured with the Lead in the
  main checkout. ADR 0147 lets only the Lead write the Arc Ledger, so
  mailboxes inside an Arc's ledger directory would need that ADR revised.
  The current files in the Worktree's Git directory work only once `L/.git`
  is writable.
- **v2 broadcasts.** `send_message` reaches a running v2 Worker at its next
  model request. A Worker running a gate, commit and push as one command
  sees a broadcast only after that command ends. A v1 Worker still has no
  tool to message its Lead, so its reports need a file.

## Validation

The retained trace passed the independent verifier at the run's base,
`895bf1dc`, and every script it names matched the hash the run recorded. No
fixture Codex process was left to kill when the run ended.
