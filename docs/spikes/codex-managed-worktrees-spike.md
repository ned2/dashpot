---
status: research
date: 2026-11-03
---

# Codex-managed Worktrees experiment

The experiment for [Issue #668](https://github.com/ned2/dashpot/issues/668)
asks whether Codex's managed-worktree tools could improve two things. One
is the Worktree preparation and recovery that Dashpot performs only when a
person asks for it. The other is Dashpot's passive view of which task made
which checkout. The run pins **codex-cli 0.166.0**, as the maintainer
decided on 2026-11-03: read the Issue's "0.162.0" as 0.166.0. The
`worktrees` feature flag is no longer a condition. At this tag it is
`Removed`, and its comment says managed worktrees "are always available"
([`features/src/lib.rs#L231`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/features/src/lib.rs#L231),
[`#L1539-L1543`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/features/src/lib.rs#L1539-L1543)).
So the first question is availability: where the tools appear, and whether
an integration can reach them.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **documented**: read from the 0.166.0 source at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`;
- **inference**: concluded from the measured and documented facts, not
  observed;
- **unknown**: with the reason it is unknown.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| Where are the tools offered? | Only to the model, inside an interactive terminal session (the TUI) on a trusted local project. They are deferred behind `tool_search`, which is why #681's list of thirteen direct tools did not show them. A standalone terminal names them in the `codex_worktrees` namespace and a terminal attached to the managed daemon in `codex_tui`. `codex exec`, a thread an app-server client starts, and an explicitly untrusted folder are offered none. | measured; documented, `tui/src/app_server_session.rs`, `core/src/tools/spec_plan.rs` |
| Can Dashpot call them? | Not through a supported interface. The terminal serves them from its own loopback MCP server, guarded by a random bearer token, and the app-server has no worktree-creation method. | documented, `tui/src/dynamic_tools_mcp.rs`, `app-server-protocol/src/protocol/common.rs` |
| How does creation behave? | It is asynchronous. `create_worktree` answers `pending` with an operation id at once. A second request while one is pending returns the same id and starts nothing. Status polls stay `pending` until the result is `created`. | measured |
| What does it create? | A checkout in Codex's own pool (`CODEX_HOME/worktrees/<4 hex>/<repo>`), detached at origin's remote HEAD by default, or at an explicit `ref`. It creates no Branch, runs no Git hook, and copies no uncommitted, untracked or ignored file. The pool is a fixed location: the tool takes no destination path. | measured |
| Does the session move? | No. Its cwd, hooks and sandbox stay in the source checkout. Under `workspace-write`, a write inside the new checkout is refused (`EROFS`). | measured |
| What survives a failure? | A ref that does not resolve fails before anything is allocated. A Codex process killed after `git worktree add` leaves an orphan: a registered Git worktree with no files, no owner record and no attachment. If the attachment fails, the result is `registrationFailed`, and the checkout is kept, bound to its owner but not attached. | measured |
| What survives a restart? | The attachments survive, and operation status does not. The resumed thread is told its interrupted operation is unknown. An independent app-server, and the daemon after a restart, read the attachments and their owner thread through the documented attachment methods. | measured |
| Is `--worktree` the same thing? | No. `codex --worktree` and `codex exec --worktree` start the session inside a new pool checkout at the source's own HEAD, not origin's. They bind the owner record but add no attachment. | measured |
| How does this compare with `dashpot worktree create`? | Dashpot plans an Issue Branch and path, checks that the base carries the Project configuration, refuses collisions before Git runs, and rolls back a failed add. Codex's tool does none of these. Codex's own advantages are the duplicate guard and the asynchronous status, and both last only as long as the process. | measured; documented |
| Does Cleanup see Codex's ownership? | No. Dashpot's Cleanup preview offers an attached checkout owned by a Codex thread as an available target with no blocker, while the attachment owner query still names that thread. | measured |
| Recommendation: preparation | **No integration.** Dashpot cannot invoke the tools, and their result does not meet the Issue Worktree contract. | inference |
| Recommendation: provenance | **Defer.** The attachment API is documented and stable, but it covers only the checkouts this tool created, needs an app-server connection, and identifies a checkout by its path. | inference |

## Reproduce

The run needs Node 24, the pinned Codex binary, and this checkout's `.venv`.
Run the runner detached, from outside any harness, so that its refusal check
passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-668/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-668/verify.mjs /var/tmp/dashpot-668-SUFFIX/trace.jsonl 0.166.0 --strict
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it. The fixture lives under `/var/tmp`, because a fixture under a deep
scratch directory overruns the 108-byte limit on a Unix socket path. A run
takes about four minutes. `SPIKE_SCENARIOS=standalone,restart` runs a
subset, which the verifier does not accept. The retained trace is
[issue-668-codex-trace.jsonl](measurements/issue-668-codex-trace.jsonl):

```bash
node scripts/experiments/codex-668/verify.mjs docs/spikes/measurements/issue-668-codex-trace.jsonl
```

Without `--strict`, the verifier only reports a Dashpot module that has
changed since the run. With it, the change fails verification.

## Tested configuration and evidence boundary

- codex-cli 0.166.0, `x86_64-unknown-linux-musl`, binary SHA-256
  `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`, run
  read-only through a fixture-local symlink, on Linux with Git 2.53.
- Dashpot at `10b049b07c2f69ea97760e895e1d8b5bd36391a6`, with no change under
  `src/`. The runner's SHA-256 is
  `4da0a3d790202f7c5281ec7b27f650fe154dfa1724c2674df5c3e61079588f83`, and
  the trace records each hashed source.
- The fixture is isolated:
  - its own `HOME`, `XDG_*`, `TMPDIR` and `CODEX_HOME`;
  - a fixture-local mock model served over the Responses API, so no network
    and no credential;
  - `sandbox_mode = "workspace-write"`, `approval_policy = "never"`;
  - the daemon updater, plugins and apps off.
  The lifecycle hooks `dashpot integrate codex` installs run through a
  metadata-only wrapper into Dashpot's real publisher. They are trusted in
  the fixture through the hook ledger.
- The fixture Repository:
  - a bare `origin` with its remote HEAD set to `main`;
  - local `main` one commit ahead of `origin/main`, and a `feature` Branch,
    so the three possible bases are distinct commits;
  - an uncommitted change, an untracked file and an ignored file;
  - a `post-checkout` hook that writes a marker;
  - a Local Issue, `fixture-1`, set up with `dashpot init --markdown issues`.
  A second repository is saved as explicitly untrusted.
- A `git` wrapper on the fixture's `PATH` logs every Git command. It can
  hold `git worktree add --detach --no-checkout` after Git has run, which
  keeps a creation pending at a known point.
- Codex's own Git commands are recognised by the `core.fsmonitor=` override
  it passes.
- The shared daemon directory in `/tmp` is used by every Codex on the
  machine. The runner tells the fixture's entry apart by the SHA-256 Codex
  derives from its control socket path. That entry was present while the
  daemon ran and gone afterwards, and the directory's other entries were
  unchanged.
- The trace holds metadata only. Paths are scrubbed to `$ROOT`, `$CHECKOUT`
  and `~`. It keeps tool names, tool replies (paths scrubbed), Git state and
  attachment reads. It keeps no prompt text, model output or file content.
- **Evidence boundary.** Every claim is about the CLI terminal, `codex
  exec` and the app-server at 0.166.0 on Linux, with a mock model.
  - Codex Desktop also uses this pool and owner record, as the manager's
    comment notes ("the existing Codex Desktop contract",
    [`worktree/src/lib.rs#L46`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/worktree/src/lib.rs#L46)).
    Its setup scripts, ignored-file copying and automatic cleanup were not
    run, and nothing here describes them. For the CLI, the manager's
    settings turn automatic cleanup off
    ([`worktree/src/settings.rs#L28-L36`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/worktree/src/settings.rs#L28-L36)).
  - A real model decides for itself whether to search for and call the
    tools. Here the mock model always did.
  - The worktree browser (`/worktree`) was not driven.
  - The 64-operation cap and the one-hour retention of a finished result
    are documented, not measured.

## 1. Interfaces and requirements

| Interface | Who can use it | Status at 0.166.0 |
| --- | --- | --- |
| `create_worktree`, `get_worktree_creation_status`, `list_worktrees` | The model in a TUI session only | A TUI-private MCP server ([`tui/src/dynamic_tools_mcp.rs#L149-L161`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/dynamic_tools_mcp.rs#L149-L161)). Its tool contracts are [`tui/src/managed_worktree_tool_specs.rs#L7-L18`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/managed_worktree_tool_specs.rs#L7-L18) |
| `thread/attachment/add`, `/list`, `/remove`, `thread/attachmentOwner/list`, notification `thread/attachment/updated` | Any app-server client | Documented in [`app-server/README.md#L365`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server/README.md#L365). Declared without an experimental marker in [`app-server-protocol/src/protocol/common.rs#L688-L707`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server-protocol/src/protocol/common.rs#L688-L707). At most 100 per thread ([`state/src/lib.rs#L136`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/state/src/lib.rs#L136)) |
| `codex --worktree`, `codex exec --worktree`, `codex fork --worktree` | A person starting a session | Creates a checkout at the source's HEAD (`base: None`, [`tui/src/worktree_startup.rs#L246-L250`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/worktree_startup.rs#L246-L250)) and starts the session there |
| `/worktree` browser | A person in the TUI | Not measured. The [reference](../agent-harness-server-client-reference.md#managed-worktrees-at-01660) records it |
| Owner record `codex-thread.json` in the checkout's Git admin directory | Codex | Private file format, `{"version":1,"ownerThreadId":…}`, written by [`bind_thread`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/worktree/src/lib.rs#L274-L277) |

The app-server offers no method to create a worktree. The tools are
advertised to the model only when all of these hold:

1. The terminal's app-server is embedded or the local daemon, not remote,
   and the session uses no remote environment
   ([`tui/src/app/startup.rs#L503-L518`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/app/startup.rs#L503-L518)).
2. The project is not explicitly untrusted. A project with no trust
   decision qualifies
   ([`tui/src/app_server_session.rs#L503`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/app_server_session.rs#L503),
   [`config/src/config_toml.rs#L627-L629`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/config/src/config_toml.rs#L627-L629)).
3. A probe `thread/attachment/list` succeeds, which shows that attachment
   storage is available
   ([`#L504-L524`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/app_server_session.rs#L504-L524)).
4. The model supports tool search. The tools are then deferred rather than
   direct
   ([`core/src/tools/spec_plan.rs#L267-L274`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/core/src/tools/spec_plan.rs#L267-L274)).

The namespace is `codex_tui` when the terminal also serves its task tools,
which happens on the daemon, and `codex_worktrees` otherwise
([`tui/src/dynamic_tools_mcp.rs#L107-L113`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/dynamic_tools_mcp.rs#L107-L113)).
`create_worktree` is pre-approved there (`"approval_mode": "approve"`).

Each call also checks the thread. An ephemeral side conversation is
refused, the thread's environment must be local, and the source project
must not be untrusted
([`tui/src/managed_worktree_tools.rs#L188-L217`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/managed_worktree_tools.rs#L188-L217)).

Storage:

- The pool is `CODEX_HOME/worktrees`, or the `[desktop]` setting
  `git-worktree-root`
  ([`worktree/src/settings.rs#L43-L44`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/worktree/src/settings.rs#L43-L44)).
- Attachments are kept in Codex's state database.
- Operation status lives only in the terminal process's memory. A finished
  result is kept for an hour, and at most 64 operations at once
  ([`tui/src/managed_worktree_tools.rs#L218-L231`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/managed_worktree_tools.rs#L218-L231)).

The Issue's 0.162.0 citations still hold at 0.166.0:

- the two TUI files named above exist;
- `WorktreeManager::create` is still at
  [`worktree/src/lib.rs#L62`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/worktree/src/lib.rs#L62);
- creation still takes a `ref` and no destination or Branch argument.

What no longer holds is the feature condition, which is removed, as the
introduction says.

## 2. Creation, measured

The measured sequence, in a standalone terminal:

1. **First request.** `create_worktree {allowAsync: true}` returned `pending`
   with an operation id and "Creation is running. Poll status; do not
   repeat creation."
2. **Duplicate request.** A second call while the first was pending got the
   same id, without a message.
3. **Held after the add.** Git had already registered the checkout,
   detached at `origin/main`, and it had no owner record yet.
4. **Released.** The status became `created`, with `root`, `workspaceRoot`
   (the root with a trailing `/`) and `sourceCwd`, and with "Keep the task
   cwd."

Codex's Git sequence:

1. `for-each-ref` to find the default base: origin's remote HEAD, then
   `origin/main`, `origin/master`, `main`, `master`
   ([`worktree/src/git.rs#L99-L140`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/worktree/src/git.rs#L99-L140));
2. `rev-parse --verify <base>^{commit}`;
3. `worktree add --detach --no-checkout <pool>/<hex>/repository <sha>`;
4. `config --file <config.worktree> core.worktree`;
5. `--work-tree=. reset --hard`.

Every Git call disables hooks, fsmonitor, filters and LFS smudge
([`worktree/src/git.rs#L171-L178`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/worktree/src/git.rs#L171-L178)).
So the fixture's `post-checkout` marker was not written. Dashpot's own
`git worktree add` did run it.

After creation:

- The shell probe still ran in the source checkout, where it could write.
  Writing inside the new checkout failed with `EROFS`.
- Every hook record kept the source cwd.
- The owner record named the thread, and the thread held a `worktree`
  attachment whose identity key is the root path.

A second request with `ref: "feature"` started a new operation and created a
new checkout detached at `feature`. `list_worktrees` reads one attachment per
page (`limit: Some(1)`,
[`tui/src/managed_worktree_tools.rs#L318-L330`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/managed_worktree_tools.rs#L318-L330)).
So a caller must follow `nextCursor`, as the tool's description says.
Nothing reuses a checkout automatically: the description tells the model
to inspect the list and prefer an active checkout.

## 3. Failure and recovery, measured

- **Missing ref.** Status returned the Git error ("Needed a single
  revision") before any pool directory was allocated.
- **Interrupted.** The terminal's Codex process was killed while Git was
  held. The orphan stayed registered in `git worktree list`, detached, with
  no files, no owner record and no attachment. Dashpot's Cleanup check
  holds it as `dirty`, since the missing files show as deletions.
- **Resume.** The resumed thread kept its session id (`SessionStart` source
  `resume`). Its status request for the old operation got "Unknown
  operation. Inspect this task's worktree attachments before creating
  another checkout." `list_worktrees` listed the two attached checkouts and
  not the orphan.
- **Registration failed.** On the daemon, a controller filled the thread's
  100 attachments through the documented `thread/attachment/add`, and the
  101st was refused. The next creation returned `registrationFailed`:
  "Checkout retained; registration failed. Do not create a duplicate." The
  checkout was clean and owner-bound but unattached, and
  `thread/attachmentOwner/list` returned no thread for it. So that query
  reads attachments, not the owner record. After `codex app-server daemon
  restart`, the thread still held exactly its one earlier attachment.

## 4. Compared with `create_issue_worktree`

| | `dashpot worktree create` | Codex `create_worktree` |
| --- | --- | --- |
| Invoked by | A person or agent, explicitly, from any shell | The model inside a TUI session; no supported external call |
| Destination | `<Worktree Root>/<issue>`, the sibling `.worktrees` root by default | `CODEX_HOME/worktrees/<random 4 hex>/<repo>`, not configurable per call |
| Branch | A new Issue Branch, created atomically ([`create.py#L372`](../../src/dashpot/repository/worktrees/create.py#L372)) | None: detached HEAD |
| Base | `origin/HEAD` by default, or `--base` | Origin's remote HEAD by default, or `ref` |
| Checks before Git runs | Worktree Root, Branch name, collisions, an existing Issue Worktree, and a base that carries the same Project configuration ([`create.py#L253`](../../src/dashpot/repository/worktrees/create.py#L253)) | The ref resolves |
| Failure | Refused before mutation, or rolled back (ADR 0011) | An orphan is possible; `registrationFailed` keeps the checkout |
| Duplicate guard | Refuses a second Worktree for the Issue | One pending operation per thread, while the process lives |
| Hooks, setup | The Repository's own hooks run; no dependency setup | No hooks; no setup; nothing copied |
| Session placement | Unchanged; `work start` binds the Issue where the session runs | Unchanged; the session stays in its source checkout |

In the same fixture, `dashpot worktree create fixture-1` planned and created
Branch `fixture-1` at `origin/main` in `$ROOT/repository.worktrees/fixture-1`
in about 250 ms.

Keeping Dashpot's contract on top of Codex's tool would take all of the
following:

- a Branch;
- a destination in the Worktree Root;
- the compatibility check;
- rollback of an orphan;
- a way to invoke the tool from outside the model.

The only gains left would be the asynchronous status and the duplicate
guard, and Dashpot's own creation is synchronous and fast.

## 5. Provenance and Cleanup

The attachment record says three things: this thread asked Codex to make
this checkout, from this source cwd, and when. Dashpot's other sources do
not say this:

- Git discovery sees an anonymous detached Worktree in the pool.
- Hooks see the session stay in its source checkout.

So attachments would explain a detached pool checkout that otherwise has no
explanation.

Their limits:

- **Coverage.** Attachments cover only checkouts this tool attached. Those
  made by `--worktree`, an orphan, and a `registrationFailed` checkout have
  none. The owner record does cover `--worktree` and `registrationFailed`,
  but it is a private file.
- **Access.** Reading attachments needs an app-server connection: a new
  loopback app-server for the same `CODEX_HOME`, or the daemon's control
  socket. A per-poll observation would pay for that connection. The data is
  per thread: `thread/attachment/list` needs a thread id, which Dashpot
  already has from hooks. `thread/attachmentOwner/list` goes from a path to
  its threads.
- **Identity.** The identity key is the checkout's path. Dashpot never
  derives identity from paths, so the record could only describe an
  observed Worktree, never identify one.
- **Meaning.** An attachment is provenance only. It is not an Issue Binding
  and not Worker placement. The creating session never runs in the
  checkout, so it is not occupancy either.

The measured gap is Cleanup. The standalone session had ended, its
checkout was attached, and `thread/attachmentOwner/list` still named the
owner thread. In that state:

```console
$ dashpot worktree check $ROOT/codex-home/worktrees/9d75/repository
Worktree   $ROOT/codex-home/worktrees/9d75/repository
Branch     (detached)
Removable  yes
           Sub-agents of Agent Sessions outside this Repository are not checked.
Remove with
  $ git worktree remove $ROOT/codex-home/worktrees/9d75/repository
```

`dashpot worktree remove <same path> --dry-run --json` planned the removal,
listing it as an available target with no blocker. So the Cleanup preview,
not only `check`, would offer it.

Two things could hold such a checkout in Cleanup: an `agent-session`
blocker, or a `detached` blocker. Neither applies:

- The session never ran in the checkout, so no `agent-session` blocker
  arises.
- Its HEAD is reachable from `origin/main`, so no `detached` blocker
  arises.

The `exec --worktree` checkout was also offered. That is expected, since
its session had ended. The difference is that a Codex thread may still
resume into its attached checkout, and a person might still be working in
it.

## Recommendations

- **Preparation and recovery: no integration.** Dashpot cannot call the
  tools. A TUI's loopback server with a private token is a private internal.
  The result also lacks the Branch, path and compatibility that an Issue
  Worktree needs, and leaves an orphan when interrupted. Reconsider only if
  Codex adds an app-server creation method that takes a destination and a
  Branch.
- **Provenance: defer.** The attachment API is a supported interface, and
  it would explain an anonymous pool checkout. But the evidence does not yet
  justify an observation adapter:
  - it covers only one of Codex's two creation routes;
  - it needs a connection per observation;
  - it is keyed by path;
  - no user report shows a pool checkout that Dashpot failed to explain.

  A narrow, testable follow-up comes first: let Cleanup's preview name a
  Codex thread that holds an attachment to the target, as a blocker or a
  stated consequence. Doing so needs a design decision, because it would be
  the first Cleanup fact read from an app-server.

## Implications for the skills

The `dashpot-execute-issues` harness reference
(`src/dashpot/skills/dashpot-execute-issues/references/harnesses.md`) is
outside this change. What it could say:

- A Codex Worker may be offered `create_worktree`.
- The tool must not stand in for `dashpot worktree create`: it makes no
  Branch and does not move the Worker.
- A Lead should not let a Worker use it for an Issue Worktree.

That wording is proposed as a follow-up.

## Validation

- `node scripts/experiments/codex-668/verify.mjs
  docs/spikes/measurements/issue-668-codex-trace.jsonl` passes all 19
  claims, with and without `--strict`.
- The run's scenarios, in order:
  1. a standalone terminal (availability, creation, reuse, missing ref,
     interrupt);
  2. restart (an independent app-server read, then resume);
  3. an untrusted folder;
  4. `codex exec`;
  5. `codex exec --worktree`;
  6. an app-server client thread;
  7. the managed daemon (availability, creation, registration failure,
     restart);
  8. Dashpot's preparation, check and Cleanup preview.

  Every scenario finished, every hook reached the real publisher and exited
  0, and no fixture process outlived the run.
- One wait is expected to go unmet: the untrusted folder's first request.
  Codex holds a saved untrusted folder at folder consent. The runner accepts
  its highlighted "Open restricted", which keeps the folder's trust setting
  ([`tui/src/onboarding/directory_trust.rs#L83-L117`](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/onboarding/directory_trust.rs#L83-L117)).
