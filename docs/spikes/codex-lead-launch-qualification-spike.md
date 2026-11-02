---
status: research
date: 2026-11-02
---

# Codex Lead launch qualification experiment

The experiment for [Issue #678](https://github.com/ned2/dashpot/issues/678)
qualifies, on the pinned **codex-cli 0.166.0** on Linux, how a sandboxed
Codex Lead is launched for an Arc. It covers two launches:

- the execute-issues skill's measured resume command, which the
  [Codex sandboxed Worker cycle experiment](codex-sandboxed-worker-cycle-spike.md)
  measured on 0.160.0;
- a **profile-file launch**: `$CODEX_HOME/<name>.config.toml`, selected with
  `--profile <name>`, whose named permissions profile grants the same
  directories and sets no legacy sandbox key.

It measures each launch with and without an operator's own
`default_permissions` profile in `config.toml`. It also compares the checks
a Lead runs inside its session with the same probes run under
`codex sandbox`, the tool the read-only preflight of
[#679](https://github.com/ned2/dashpot/issues/679) would use.

The **lead** here is the root thread of a Codex Agent Session, and a
**worker** is one of its [Sub-agents](../domain-language.md), spawned with
multi-agent v2. The fixture threads only run commands, so they are a
skill's Lead and Workers in shape only.

Each answer is marked:

- **measured**: the retained trace shows it, and the verifier checks it;
- **source**: read at tag
  [`rust-v0.166.0`](https://github.com/openai/codex/tree/rust-v0.166.0),
  commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`, paths under
  `codex-rs/`. The verifier checks each cited range's text when it is
  given a checkout of that tag;
- **inference**: reasoned from the two, not run;
- **unknown**: with the reason.

## Answers

| Question | Answer | Basis |
| --- | --- | --- |
| Does the measured resume command still qualify on 0.166.0? | Yes. The lead's four checks pass and its control write is refused. A fresh v2 worker completes its whole cycle, from `uv sync` through the gate, commit and push to its ledger file. | measured |
| What permissions does that command give? | A legacy `workspace-write` turn, with the Worktree Root and the Git directory as writable roots, the network on, and no named permissions profile. | measured |
| Does a profile-file launch qualify? | A fresh `codex -C <checkout> --profile <name>` does: the lead and its worker run under the named profile with the network enabled, every check passes, and the worker's cycle passes. | measured |
| Does `codex resume <id> --profile <name>` qualify? | Not alone. A resumed thread keeps the named profile it last ran under, and a plain launch saves the built-in `:workspace`. That resume kept `:workspace` and refused the Worktree Root, the Git directory and the network. Adding `-c 'default_permissions="<name>"'` makes the profile win, and that launch passes with a full worker cycle. | measured; source, `core/src/config/mod.rs:5110-5115`, `app-server/src/request_processors/thread_processor.rs:313-345` |
| Must the profile name the Git directory? | Yes. With only the Worktree Root granted, the main checkout's `.git` stayed read-only, though it lies inside a workspace root. The Git directory check and its `test -w` failed, and so did `git worktree add`. | measured; source, `protocol/src/permissions.rs:860-871` |
| What do `--approve-for-me` and `--sandbox workspace-write` do beside `--profile`? | Each replaces the profile's permissions with a legacy `workspace-write` sandbox with no added root and no network, so three of the four checks fail. The profile file's cache variables still apply. | measured; source, `utils/cli/src/shared_options.rs:80-93`, `core/src/config/mod.rs:2690-2692` |
| Does `--approve-for-me` outlast its launch? | Yes. It set `approvals_reviewer = "auto_review"` and `approval_policy = "on-request"` on the thread, and every later resume of that thread kept both, with no option asking for them. | measured |
| How does the resume command combine with a `default_permissions` profile in `config.toml`? | Its `--sandbox` selects the legacy sandbox outright, so the session runs without the operator's profile. A file that profile denied became readable. The command still passes, with a full worker cycle. | measured; source, `core/src/config/mod.rs:2690-2692` |
| And a profile-file launch? | Its own named profile replaces the operator's, deny rules included, unless it extends it. A profile that sets `extends = "<operator's profile>"` and adds the two directories keeps the deny rule and the network. That launch passes with a full worker cycle while the denied read still fails with `EACCES`. | measured |
| Does `shell_environment_policy.set` reach a fresh worker's shell and commit hook? | Yes, under every passing launch: the measured command's `-c` options and the profile file's `[shell_environment_policy.set]` alike. The lead's own shell got both variables in every launch that set them, even where the grant failed. | measured |
| Which process hosts each launch? | Every launch with `--profile` or a `-c` option runs in its own TUI client, which is then the session's Host Process. By source, a `-c` option from a short list of display and feature switches would not. The terminal's environment reaches its commands and hooks, and its `SessionEnd` fires as the client exits. A plain launch runs on the managed daemon. Its commands carry the environment of the terminal that started the daemon, and its `SessionEnd` fires when the daemon unloads the thread. | measured; source, `tui/src/daemon_startup.rs:78-79`, `:97-118` |
| Do `codex sandbox` probes match the checks in the session? | Yes, for a fresh launch with the same options. `--profile <name>`, with or without `-P <name> -C <checkout>`, and the legacy `-c` options gave the same `test -w` results, network and variables as the matching sessions. They also kept or dropped an operator's deny rule as those sessions did. They cannot show a resume that keeps a saved profile, since `codex sandbox` reads no thread. | measured; inference for the limit |
| What does `codex sandbox` need, and write? | `-C` requires `-P`. With neither `-P` nor a configured `default_permissions`, it runs read-only. Under `$CODEX_HOME` it replaces its own helper binaries in `tmp/arg0-linux/` and changes nothing else. | source, `cli/src/lib.rs:125-131`, `cli/src/debug_sandbox.rs:693-731`, `:762-768`; measured for the read-only fallback and the writes |

## Reproduce

The run needs Node 24, the pinned Codex binary, uv, and this checkout's
`.venv`. Run the runner detached, from outside any harness, so that its
refusal check passes:

```bash
setsid -f sh -c 'node scripts/experiments/codex-678/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex 0.166.0 > run.log 2>&1'
node scripts/experiments/codex-678/verify.mjs docs/spikes/measurements/issue-678-codex-trace.jsonl
node scripts/experiments/codex-678/verify.mjs docs/spikes/measurements/issue-678-codex-trace.jsonl 0.166.0 --strict --codex-source <rust-v0.166.0 checkout>
node scripts/experiments/codex-678/verify.mjs /var/tmp/dashpot-codex-678-SUFFIX/trace.jsonl 0.166.0 --strict --codex-source <rust-v0.166.0 checkout>
```

The runner prints the fixture root, and the trace is `trace.jsonl` inside
it.

## Tested configuration and evidence boundary

- **Codex**: codex-cli 0.166.0, the retained standalone release
  `0.166.0-x86_64-unknown-linux-musl`, sha256
  `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`,
  run through a fixture-local `PATH` symlink with its daemon updater off.
- **Platform**: Ubuntu, Linux 7.0.0, bubblewrap 0.11.1, Node v24.18.0,
  uv 0.13.5, Git 2.53.0.
- **Fixture**: a disposable uv project under `/var/tmp`, outside the
  directories `workspace-write` grants by default. It has a locked
  pre-commit dependency and a tracked pre-commit hook that runs
  `uv run --locked pre-commit` and reports the two cache variables it was
  given. Its `origin` is a bare repository served by `git http-backend` on
  loopback, so pushing needs the network. HOME, the XDG directories and
  CODEX_HOME are isolated. The model is a scripted loopback Responses API
  serving a bundled model marked multi-agent v2.
- **Hooks**: every event `dashpot integrate codex` subscribes, trusted
  through Codex's hook ledger. Each runs Dashpot's real publisher through a
  wrapper that records the hook's ancestry and the terminal's marker.
- **Trace**: [`issue-678-codex-trace.jsonl`](measurements/issue-678-codex-trace.jsonl),
  sha256 `fe80856f778595bc854eed0fc4bd14a8c9a7ee0e50a15893fa6e78ca54bf9df8`.
  It records the SHA-256 of the runner's scripts and of the Dashpot modules
  the hooks ran, and the verifier checks the scripts against it.

Not measured:

- macOS and Seatbelt;
- `gh`;
- SSH remotes (the push is loopback HTTP);
- a session whose thread was last saved under a named profile other than
  `:workspace`;
- a profile file that sets `approvals_reviewer`, the remedy proposed below
  for `--approve-for-me`;
- the operator's real `~/.codex` configuration, which the fixture never
  reads;
- a Worker on a model without multi-agent v2.

## 1. Launches without an operator profile

The run first starts two sessions, A and B, with no option at all. A
person's first session in an Arc starts this way. Both run on the managed
daemon under the built-in `:workspace` profile, so every check fails. Each
has its own scenario from then on.

| Launch | Thread | Turn's permissions | Worktree Root | Git dir | Network | Variables | Worker cycle |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Measured resume command | A | legacy `workspace-write`, both roots, network on | pass | pass | pass | set | passes |
| `codex -C <checkout> --profile dashpot-arc` | new | `dashpot-arc` | pass | pass | pass | set | passes |
| `codex resume <B> --profile dashpot-arc` | B | `:workspace`, as saved | fail | fail | fail | set | none: `git worktree add` refused |
| the same, `-c 'default_permissions="dashpot-arc"'` | B | `dashpot-arc` | pass | pass | pass | set | passes |
| `--profile dashpot-arc-nogit` | new | `dashpot-arc-nogit` | pass | fail | pass | set | none: `git worktree add` refused |
| `resume <A> --profile dashpot-arc --approve-for-me` | A | legacy, no roots, network off | fail | fail | fail | set | not run |
| `resume <A> --profile dashpot-arc --sandbox workspace-write` | A | legacy, no roots, network off | fail | fail | fail | set | not run |

In every launch, the control write outside the grants was refused.

The first resume of A and the first of B met the read-only screen that
says the thread is open in another app, since the daemon still held each
thread from its plain launch. They started once the daemon released the
thread, as on 0.160.0. Later resumes, of threads last hosted by a client,
met no such screen.

The profile file the fixture used names its own permissions profile. It
grants the Worktree Root and the Git directory by explicit rule, and moves
both caches. Shown with the fixture's paths:

```toml
default_permissions = "dashpot-arc"

[permissions.dashpot-arc.filesystem]
":root" = "read"
":workspace_roots" = "write"
":slash_tmp" = "write"
":tmpdir" = "write"
"<Worktree Root>" = "write"
"<Git directory>" = "write"

[permissions.dashpot-arc.network]
enabled = true

[shell_environment_policy.set]
UV_CACHE_DIR = "<Worktree Root>/.cache/uv"
PRE_COMMIT_HOME = "<Worktree Root>/.cache/pre-commit"
```

Why the plain `resume --profile` fails (source):

- `apply_persisted_permission_profile` restores the profile the thread last
  ran under, unless the resume carries a `sandbox_mode`,
  `permission_profile` or `default_permissions` override
  (`app-server/src/request_processors/thread_processor.rs:313-345`).
- A profile file is a configuration layer, not such an override.
- `resolve_effective_permission_selection` then takes the override, or else
  the saved profile, ahead of the configured `default_permissions`
  (`core/src/config/mod.rs:5110-5115`).

## 2. Launches over an operator's `default_permissions`

The run then gives the base `config.toml` its own permissions profile,
`base`. It grants the workspace roots and the temporary directories,
denies reading one file, and turns the network on. A plain launch runs
under it: the denied read fails with `EACCES`, and the network passes.

| Launch | Turn's permissions | Four checks | Denied file | Worker cycle |
| --- | --- | --- | --- | --- |
| Measured resume command | legacy `workspace-write`, both roots | pass | **readable** | passes |
| `--profile dashpot-arc` | `dashpot-arc` | pass | **readable** | passes |
| `--profile dashpot-arc-extends` | `dashpot-arc-extends` | pass | `EACCES` | passes |
| `resume <A> --profile dashpot-arc` | `dashpot-arc` | pass | readable | not run |

The two resumes of A ran after its `--approve-for-me` launch in section 1,
so both ran with the automatic reviewer and `on-request`, which the thread
had kept. That does not change what the sandbox granted.

The extending profile adds only the two directories to the operator's
own profile:

```toml
default_permissions = "dashpot-arc-extends"

[permissions.dashpot-arc-extends]
extends = "base"

[permissions.dashpot-arc-extends.filesystem]
"<Worktree Root>" = "write"
"<Git directory>" = "write"
```

`config.toml` defines the `base` profile, and the profile file loads as a
second user layer on top of it (source,
`config/src/loader/mod.rs:292-294`). A user profile cannot extend a
built-in such as `:workspace` (source, `config/src/permissions_toml.rs:78`).

The last resume took `dashpot-arc` because A's last turn had run under the
legacy sandbox, with no named profile to restore. It does not contradict
section 1. Which profile a `resume --profile` takes depends on the thread's
history, which is why the skill's resume pins it.

## 3. Environment and Host Process

The fixture gives each terminal a marker variable, and the probe and the
hook wrapper record the marker their process inherited.

- **Launches with an option:** the lead's commands, its worker's commands
  and every hook carried that launch's own marker. Every hook ran under the
  `codex` client process, and Dashpot's record named that client as the
  Host Process. `SessionEnd` came from the client as it exited.
- **Plain launches:** both sessions' commands and hooks carried the marker
  of the terminal that had started the daemon. Dashpot's record named the
  daemon, `app-server --managed-daemon`. Each `SessionEnd` came from the
  daemon after the client exited, when the daemon unloaded the thread.

So a variable the terminal exports reaches the commands of an
option-carrying launch. That is not how to give one to Workers: the
`shell_environment_policy.set` table reached each worker's shell and the
hook its commit ran under every passing launch, whatever the terminal held.

## 4. `codex sandbox` against the checks in the session

`probe.mjs` asks `test -w` of the Worktree Root, the Git directory, both
caches and the outside directory. It runs `git ls-remote` and tries the
denied read, and records the cache variables. It writes nothing. The
runner ran it under `codex sandbox` with no session or daemon running, and
the lead's checks ran the same probe inside each session.

| `codex sandbox` options | Matches |
| --- | --- |
| `--profile dashpot-arc` | the fresh profile launch |
| `--profile dashpot-arc -P dashpot-arc -C <checkout>` | the fresh profile launch |
| the measured command's grants as `-c sandbox_mode=…` and `-c sandbox_workspace_write.*` | the measured resume command |
| `--profile dashpot-arc-nogit -P dashpot-arc-nogit -C <checkout>` | the launch without the Git directory rule |
| none, no operator profile | read-only: nothing writable, no network, no variables |
| `-P :workspace -C <checkout>` | the plain launches: nothing outside the checkout writable |
| none, or `-P base -C <checkout>`, over the operator profile | the plain launch: denied read `EACCES` |
| `--profile dashpot-arc …` and the legacy `-c` options, over it | their launches: the denied file readable |
| `--profile dashpot-arc-extends …`, over it | the extending launch: denied read `EACCES` |

So `codex sandbox --profile <name>` answers, before any session starts,
what a fresh launch with that profile file will grant. It cannot answer
what a resume will grant. That depends on the thread's saved profile,
which `codex sandbox` never reads, and a resume without the pin went
the other way (section 1). The checks inside the session stay
authoritative.

Two fixture details:

- Where the network was restricted, a Node process started by Node exited
  0 but printed nothing, in a session and under `codex sandbox` alike. The
  lead's checks therefore run the probe in their own process, and the
  runner reads `codex sandbox`'s probe through `cat`.
- A shell child printed normally. The cause is unknown.

## 5. Source facts re-derived at rust-v0.166.0

The proposal cited these facts at `rust-v0.162.0`. At `rust-v0.166.0`:

- **Still holds:** `--profile` keeps the TUI off the managed daemon, and so
  does any `-c` option outside a short list of display and feature
  switches (`tui/src/daemon_startup.rs:78-79`, `:97-118`).
- **Still holds:** `resume` and `sandbox` both accept `--profile`
  (`cli/src/main.rs:1973-1998`). The profile file loads as a second user
  layer above `config.toml` (`config/src/loader/mod.rs:292-294`).
- **Still holds, lines moved:** a `--sandbox` override selects the legacy
  sandbox outright (`core/src/config/mod.rs:2690-2692`). Setting both
  `sandbox_mode` and `default_permissions` as overrides is an error
  (`:3527-3532`). A sandbox or permission override drops the saved
  profile identity (`:3668-3676`).
- **Still holds:** `--approve-for-me` adds `approvals_reviewer`,
  `approval_policy = "on-request"` and `sandbox_mode = "workspace-write"`
  as overrides (`utils/cli/src/shared_options.rs:80-93`). Clap refuses it
  beside `--sandbox` (`:43-50`).
- **Still holds:** writable roots keep a project's `.git` read-only only
  where no explicit rule names it (`protocol/src/permissions.rs:860-871`).

These the proposal did not cite, and were read at `rust-v0.166.0` alone:

- `codex sandbox`'s `-C` requires `-P/--permission-profile`
  (`cli/src/lib.rs:125-131`). Without a permissions profile it falls back
  to read-only, unless a legacy `-c sandbox_mode` is given
  (`cli/src/debug_sandbox.rs:693-731`).
- `--profile <name>` is refused while `config.toml` still holds a legacy
  `profile = "<name>"` or `[profiles.<name>]`
  (`config/src/loader/mod.rs:316-325`).
- A user permissions profile cannot extend a built-in one
  (`config/src/permissions_toml.rs:78`).
- A resume restores the thread's saved permissions profile unless it
  carries a permission override
  (`app-server/src/request_processors/thread_processor.rs:313-345`), and
  an override wins over the saved profile
  (`core/src/config/mod.rs:5110-5115`).

## What this means for the skill

- The measured resume command stays qualified on 0.166.0. What it does to
  a `default_permissions` profile is now measured: the session runs
  without the operator's profile, deny rules included, so the Lead tells
  the user so.
- A profile-file launch is qualified as a fresh launch, or as a resume
  that pins the profile with `-c 'default_permissions="<name>"'`. It must
  name the Git directory by explicit rule.
  - Where the user's configuration selects a permissions profile, the
    profile extends it and keeps its deny rules. The measured command
    cannot keep them.
  - It must not be combined with `--approve-for-me` or `--sandbox`.
  - (inference, not measured) a user who wants the automatic reviewer sets
    `approvals_reviewer = "auto_review"` in the profile file instead.
- The checks inside the resumed session stay the Lead's evidence. A
  `codex sandbox --profile` preflight can check a profile file before a
  fresh launch, but not a resume.

[ADR 0149](../adr/0149-offer-a-profile-file-launch-for-a-codex-lead.md)
records the skill's change.

## Validation

- The verifier passes on the retained trace, with and without
  `--codex-source`. With a `rust-v0.166.0` checkout it also checks each
  cited source range.
- `tests/test_experiment_runners.py` checks the runner's sources.
