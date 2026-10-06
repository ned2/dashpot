---
status: accepted
date: 2026-10-06
---

# Let Workers write their own Arc Ledger files, and commit under Codex's sandbox

The `dashpot-execute-issues` skill passed mid-flight messages through two
files in a Worktree's Git directory: `execute-issues-status`, which a Worker
wrote for its Lead, and `execute-issues-lead`, which the Lead wrote for the
Worker ([#637](https://github.com/ned2/dashpot/issues/637)). They were a
Codex v1 Worker's only way to report, an OpenCode Worker's fallback, and the
backup for every Codex v2 broadcast.

The [Codex workspace-write Workers experiment](../spikes/codex-workspace-write-workers-spike.md)
measured those files, and more, under Codex's `workspace-write` sandbox on
codex-cli 0.160.0:

- **A Worker runs under its Lead's sandbox,** including the writable
  directories the Lead's session was started with. No spawn argument gives
  it another, as the release's source documents.
- **With no writable directories added, a Worker cannot do its Issue.** It
  cannot edit a tracked file in its linked Worktree, and nobody can write a
  Git directory. A linked Worktree's Git directory is inside the main
  checkout's `.git`, which the sandbox keeps read-only, so the status and
  broadcast files never worked there.
- **With the Worktree Root writable, a Worker can edit, but not commit.**
  Neither can its Lead: every commit writes the main checkout's `.git`.
- **With the main checkout's `.git` writable too, a v2 Worker committed;**
  no v1 Worker ran with that grant.
- **A Worker can write a Lead's checkout in the main checkout in every
  configuration measured,** because that checkout is the Lead's workspace.
  A Lead in a linked Worktree can write that Worktree, and its Workers run
  under its sandbox, so a file in the Lead's Arc Ledger is a channel that
  works wherever a Worker can work.
- **A v2 Lead's `send_message` reaches a running Worker** at its next model
  request, after the command it is running.

[ADR 0147](0147-keep-an-arcs-working-record-in-a-local-arc-ledger.md) lets
only the Lead write the Arc Ledger.

## Decision

**Each Worker writes its own file in the Arc Ledger.** An Arc's directory
gains:

- `workers/<worker>.md`: one Worker's reports, appended by that Worker
  alone, where `<worker>` is the name its brief gives it;
- `broadcast.md`: the Lead's broadcasts, appended by the Lead, which
  Workers read.

The Lead still alone writes everything else in the ledger, and reads each
Worker's file without editing it. Each entry ends with an end line, so a
reader treats an entry without one as still being written. A Worker writes
nothing else in the ledger and nothing else in the Lead's checkout.

**The files replace the Git-directory files.** A Codex v1 Worker reports in
its file and reads `broadcast.md` before each gate run, commit and push. An
OpenCode Worker whose report command fails writes its file instead. A Codex
v2 Worker reports and receives broadcasts with `send_message` alone, with no
file backup.

**A Codex Lead's session lets its Workers commit.** Under `workspace-write`,
the Lead checks before it binds that its session can write the Worktree
Root and the main checkout's Git directory, and that it has network access
for `gh` and pushing. If it cannot, it stops and gives the user the command
that starts the session with them:

```bash
codex resume <session-id> -C <checkout> --sandbox workspace-write \
  --add-dir <Worktree Root> --add-dir <main checkout>/.git \
  -c sandbox_workspace_write.network_access=true
```

[#639](https://github.com/ned2/dashpot/issues/639) revised this part of
the Decision after the
[Codex sandboxed Worker cycle experiment](../spikes/codex-sandboxed-worker-cycle-spike.md)
measured the command on codex-cli 0.160.0 on Linux. It gives the Lead and
every Worker those writable roots with the network on, and the Lead's
three checks pass under it; the Lead still runs its checks again in the
resumed session. `--sandbox workspace-write` is needed: under `read-only`,
Codex refuses `--add-dir` and the client exits. When the old thread ran in
Codex's background app-server, the resume waits about a minute until that
server unloads it.

The grant alone lets a Worker edit, push and write its ledger file, but
not run a gate or commit when the repository's tools write caches outside
the named directories: uv's `~/.cache/uv` and pre-commit's
`~/.cache/pre-commit` refused every such step, though the three checks
passed. So the Lead also checks where those caches go, and the command
gains one option per cache the repository's gates use, moving it into the
Worktree Root for every shell of the session:

```bash
-c 'shell_environment_policy.set.UV_CACHE_DIR="<Worktree Root>/.cache/uv"' \
  -c 'shell_environment_policy.set.PRE_COMMIT_HOME="<Worktree Root>/.cache/pre-commit"'
```

With those, a Worker completed its whole cycle, its commit's hook included.
`--add-dir ~/.cache` does too, but it opens every tool's cache to every
agent of the session, so it is the user's alternative rather than the
default.

The Lead names the security cost to the user once, when it asks:

- every agent of the session can write `.git/hooks/` and `.git/config`;
- code planted there runs the next time anything runs `git` outside the
  sandbox, Dashpot's own dashboard included.

The user may instead run the session without the sandbox
(`--sandbox danger-full-access`), where every check passes.

## Considered options

- **Keep the files in the Worktree's Git directory.** Rejected. They work
  only where the main checkout's `.git` is writable, so a Worker that can
  write them can also commit, and a sandbox that refuses them fails
  silently: the reader sees no file, which reads as nothing to report.
- **Each Worker writes in its own Worktree's `.dashpot/state/`,** and the
  Lead reads it there, as #637 first suggested. Rejected. It scatters an
  Arc's state across Worktrees, which Cleanup removes with it, while the
  Lead's checkout already holds the rest of the Arc and is writable to every
  Worker without any grant.
- **Workers write anywhere in the ledger.** Rejected. One writer per file
  needs no locking, keeps a Worker from overwriting the Lead's record or
  another Worker's, and lets the Lead tell whose words it is reading.
- **Only the Worktree Root writable, with the user committing for every
  Worker.** Rejected. It keeps the Git directory protected, but it turns
  every Worker's Issue into a diff the user must finish, which removes
  most of the skill's point.
- **Require running Codex without the sandbox.** Rejected as the default.
  The sandbox still keeps a confused agent out of everything outside the
  named directories, such as the user's home and other repositories,
  though it is not a boundary against a hostile one. It stays the user's
  choice.

## Consequences

- Amends
  [ADR 0147](0147-keep-an-arcs-working-record-in-a-local-arc-ledger.md):
  its rule that the Lead alone writes the Arc Ledger now excepts each
  Worker's own file, and the rest of it stands.
- The skill's `references/harnesses.md` drops `execute-issues-status` and
  `execute-issues-lead`. Its Codex section gains the sandbox check, and its
  `references/arc-ledger.md` the Worker files.
- The brief tells a Worker the main checkout belongs to others, apart from
  its own ledger file. Under `workspace-write` nothing enforces that: the
  whole Lead's checkout is writable to every Worker. A Worker that skips its
  `cd` therefore edits the Lead's checkout, which is one more reason every
  command starts with `cd <Worktree> &&`.
- Under Codex, a sandboxed Worker's gate, commit with hooks, and push are
  measured, with the caches moved into the Worktree Root. A repository
  whose gates write other caches moves them the same way. `gh` under the
  grant, and macOS, where Codex uses its Seatbelt sandbox, are not
  measured.
- Under `on-request`, a refused write still fails as a command; only a
  command an agent asks to run outside the sandbox raises an ask. The
  person answers every ask, a Worker's included, in the Lead's terminal.
  Declining a Worker's ask while the Lead's turn had ended ended that
  Worker's turn without a report; what an ask does to a Lead waiting on
  the Worker is not measured.
- An OpenCode Worker writing outside its Worktree may raise a permission
  ask, which is not measured. A rejected ask leaves only the Worker's
  hand-back.
