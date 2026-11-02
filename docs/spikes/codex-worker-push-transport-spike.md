---
status: research
date: 2026-11-02
---

# Codex Worker push transport under the sandbox

[Issue #684](https://github.com/ned2/dashpot/issues/684) measures each
transport remedy for
[F9](../proposals/codex-arc-provisioning.md#f9-ssh-fails-inside-the-sandbox-before-connecting).
In each case a sandboxed Codex Worker runs `git ls-remote`, a first push, a
lease push (`--force-with-lease=refs/heads/<branch>:<old head>`) and the
pre-push hook.

The release is **codex-cli 0.166.0**, Linux x86_64. The maintainer
re-pinned the Issue from 0.162.0 to that retained release. The host runs
Ubuntu on Linux 7.0.0, with OpenSSH 10.2p1, Git 2.53.0, gh 2.103.3 and
bubblewrap 0.11.1.

A scripted loopback provider plays the Lead and its V2 Sub-agent, and
selects every call. So the Lead and Worker are a Lead and Worker in shape
only. The remote is disposable: one bare repository on loopback, served by
the runner's own `sshd` and HTTPS server, and the runner owns every key,
token and agent. No real forge, model or operator credential is used.

## Measured outcomes

Each Worker ran with the grants the
[execute-issues skill's resume command](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#codex)
gives:

- `workspace-write`;
- the Worktree Root and the Git directory as its only writable roots;
- the network on.

Each remedy reached the Worker's shell through `shell_environment_policy.set`
alone. The `origin` remote is the scp-like SSH URL `fixture-forge:owner/repo.git`.
Every row below is checked by the independent verifier against three
sources:

- the Worker's own step reports;
- the remote's own records: its receive hook, its HTTPS requests and its
  `sshd` sessions;
- the approvals the client answered, and Codex's rollouts.

| Case | Result |
| --- | --- |
| F9 inside the sandbox, every scenario | `/etc/ssh/ssh_config` and the fragment `/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf` show as uid **65534**, mode 644. `ssh -F /etc/ssh/ssh_config -G` exits 255 with `Bad owner or permissions on /etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`. A control write outside the roots fails with `EROFS`. |
| F9 on the host, outside every sandbox | The fragment is a symlink to `/usr/lib/systemd/ssh_config.d/20-systemd-ssh-proxy.conf`, uid 0, mode 644. `ssh -G` through the system configuration exits 0, and `git ls-remote` over each transport succeeds. |
| Baseline: SSH through the system configuration | `git ls-remote` and `git push` both exit 128 with that error and `fatal: Could not read from remote repository.` The pre-push hook never runs. The remote receives nothing, and `sshd` accepts no session. |
| Remedy 1: HTTPS for the session only | `GIT_CONFIG_COUNT=2` with `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` gave two command-scope keys, `url.https://127.0.0.1:<port>/.insteadof` and `credential.https://127.0.0.1:<port>.helper` (`!gh auth git-credential`), and Git resolved `origin` to HTTPS for fetch and push. `gh` read the fixture token from its own store in `GH_CONFIG_DIR`. `git ls-remote`, the first push and the lease push succeed. The remote received exactly two updates over HTTPS: new branch, then the lease's replacement. Each operation was first refused with 401, then authorized with the fixture token. A stale lease is refused with `(stale info)` after the ref advertisement, before any upload. The pre-push hook ran inside the sandbox (`EROFS`). No SSH session was opened. |
| Remedy 2: `GIT_SSH_COMMAND="ssh -F <user-owned config>"` | The Worker's `$GIT_SSH_COMMAND -G` resolved the fixture host, port, `BatchMode` and `IdentitiesOnly` from the user-owned file and passed. With `SSH_AUTH_SOCK` naming the fixture agent's socket, in a directory outside the writable roots, `ssh-add -l` listed its one key from inside the sandbox. `git ls-remote`, the first push and the lease push succeed. The remote received exactly two updates over SSH, and a stale lease is refused with `(stale info)`. The pre-push hook ran inside the sandbox. No HTTPS request was made. |
| Remedy 2: a host key not yet known | The configured known-hosts file was pre-seeded with the fixture host key, and the configuration set `StrictHostKeyChecking yes`; every operation above ran so. A separate `git ls-remote` overrode both: `UserKnownHostsFile` named an absent file outside the writable roots, with `StrictHostKeyChecking=accept-new`. It succeeded, printed `Failed to add the host to the list of known hosts`, and left no file. |
| Remedy 3 under `never` | Both escalated calls (`sandbox_permissions: "require_escalated"`) are rejected without running: `approval policy is Never; reject command — you cannot ask for escalated permissions if the approval policy is Never`. No approval request reaches the client, and the remote receives nothing. |
| Remedy 3 under `on-request`, human reviewer | The sandboxed attempt fails first, as in the baseline. Each escalated `ls-remote`, push and lease push raised one `item/commandExecution/requestApproval` request carrying the Worker's thread, and all three were accepted. Each then succeeded over SSH, and a stale lease was refused. The pre-push hook ran **outside** the sandbox: its control write outside the roots succeeded, for every push. |
| The remote, every scenario | `remote.origin.url` kept the same digest before and after, and no `pushurl` was set. The Worker's Git configuration showed only the two local `remote.origin.*` keys, plus remedy 1's two command-scope keys. |

The trace records configuration keys, scheme classes, digests and statuses.
It never records a configuration value or a credential, and the verifier
checks that the token never reached it.

## Source at rust-v0.166.0

The facts below were re-derived from `openai/codex` at tag `rust-v0.166.0`
(commit 6ff1e1ca), restating the Codex facts the Issue and F9 took from
earlier releases.

- **The uid mapping** (source): the Linux sandbox always passes
  `--unshare-user` to bubblewrap (`codex-rs/linux-sandbox/src/bwrap.rs:360`,
  in `create_bwrap_flags`, and `:284` for the full-filesystem variant). The
  namespace maps only the invoking uid, so root's files appear as the
  overflow uid. The probes above measure the consequence.
- **The OpenSSH check** (source, OpenSSH `V_10_2_P1` as F9 cites it; the
  host runs 10.2p1): every `Include`d file is read with
  `SSHCONF_CHECKPERM`, while a file given with `-F` is not.
- **`shell_environment_policy.set` runs last** (source): it is applied after
  the default excludes, `*KEY*`, `*SECRET*` and `*TOKEN*`, in `populate_env`
  (`codex-rs/protocol/src/shell_environment.rs:138-157`). Only a non-empty
  `include_only`, applied after it, can still drop a variable set this way.
  - So `GIT_CONFIG_KEY_n` reaches the shell when it is set this way. It is
    dropped when it is inherited from the Host Process.
  - A token in an inherited variable would be dropped too. Remedy 1 relies
    on `gh`'s own store instead.
- **The rejection under `never`** (source): it comes from
  `codex-rs/core/src/tools/handlers/unified_exec/preparation.rs:280`.
- **The approval method** (source): `item/commandExecution/requestApproval`
  is defined at `codex-rs/app-server-protocol/src/protocol/common.rs:1848`.

## Reproduce and verify

The runner needs:

- Node 24, Git, OpenSSH's `sshd`, `ssh-agent` and `ssh-keygen`;
- `openssl`, `gh`;
- the retained Linux 0.166.0 binary.

It writes only its fixture under `/var/tmp/dashpot-codex-684-*`. It never
reads the user's `~/.codex`, `gh` login, SSH agent or keys, and every `ssh`
it runs names its configuration with `-F`. Commit the experiment's sources
first: the trace records whether they were clean. Then run it detached, so
that no harness process becomes an ancestor of its sessions:

```bash
setsid -f sh -c 'node scripts/experiments/codex-684/run.mjs ~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex > /var/tmp/dashpot-684.log 2>&1'
node scripts/experiments/codex-684/verify.mjs /var/tmp/dashpot-codex-684-SUFFIX/trace.jsonl
```

The retained run's details:

- Trace: [issue-684-codex-trace.jsonl](measurements/issue-684-codex-trace.jsonl),
  210 records, SHA-256
  `286ca24c7c47478ad12358cc3b766481617909a252e02595c263206b413657cf`.
- Binary SHA-256:
  `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`.
- The experiment sources were committed and clean when the run began. It
  records the SHA-256 of `ancestry.mjs`, `prepush.mjs`, `run.mjs`,
  `step.mjs` and `verify.mjs`.

The verifier:

- checks those hashes against the current files;
- checks the binary's bytes, by default against the release named in the
  trace;
- imports none of the runner's code.

`tests/test_codex_push_evidence.py` runs it on the retained trace, and on
mutated copies that overstate each result.

## Evidence boundaries

- **A scripted fixture.** The host is a scripted fixture that calls
  `codex app-server` over stdio, not the TUI. The sandbox, approval policy
  and environment are the ones the resume command sets, and the rollouts
  confirm them for each Lead and Worker. A real model and a real terminal
  are not measured.
- **Loopback remotes, not GitHub.** Neither a real forge nor these were
  measured:
  - a token's permission to push changes under `.github/workflows`;
  - GitHub's host key;
  - `gh` with a keyring-backed store.

  The `gh` store here is the plain `hosts.yml` that insecure storage
  writes. HTTPS used a fixture certificate, trusted through
  `GIT_SSL_CAINFO`, which a GitHub remote does not need.
- **How a token reaches commands.** This is #659's question, still open.
  Remedy 1 kept the token in `gh`'s store and out of the environment. A
  `GH_TOKEN` in the Host Process is not measured here, and the
  `shell_environment_policy` default excludes would drop it.
- **Remedy 3 scope.** Remedy 3 is measured with the human reviewer only.
  `approvals_reviewer = "auto_review"` and a declined escalation are not
  measured.
- **Remedy 2 scope.** Remedy 2 is measured with a key in an agent. A key
  file read directly through `IdentityFile`, a passphrase prompt, and a
  `ProxyCommand` or `ProxyJump` are not measured.
- **Platform.** Linux only. macOS sandboxes with Seatbelt, which has no uid
  mapping, and F9 there is unknown.
