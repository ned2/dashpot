---
status: proposal
date: 2026-10-16
---

# Codex Arc provisioning and preflight

What a sandboxed Codex Lead needs before it binds, what went wrong when one
set up the Codex 0.162.0 qualification Arc, and a bounded proposal for making
that setup reusable. Written for
[Issue #671](https://github.com/ned2/dashpot/issues/671). The operator
launcher that loads a credential environment is tracked separately in
`ned2/env#8`, which owns its implementation and its release-qualified
validation. This document owns the Dashpot-facing account, and links that
work as coordination only, not as a prerequisite.

The shipped guidance is the
[`dashpot-execute-issues` Codex reference](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#codex).
It changes in the same change as this document where a finding below
supports it. Everything else here is a proposal until the maintainer
approves it. Throughout, the **operator** is the person who launches the
Lead and provisions the machine, whom the skill calls the user.

## Evidence classes

Each claim carries one:

- **measured**: a retained, independently verified Dashpot experiment shows
  it. The Worker experiments are pinned to **codex-cli 0.160.0**
  ([sandboxed Worker cycle](../spikes/codex-sandboxed-worker-cycle-spike.md),
  [linked Worktree environment](../spikes/linked-worktree-environment-spike.md)).
- **observed**: a Lead's or another session's preflight saw it, as recorded
  on Issue #671 between 2026-10-10 and 2026-10-12. Nothing was retained,
  and nobody verified it independently. These are session observations and
  cannot be reproduced as they ran.
- **probed**: a command this document's author ran on 2026-10-13, from a
  Claude Code session on this machine, outside any Codex session: codex-cli
  0.162.1, Ubuntu, Linux 7.0.0, OpenSSH 10.2p1. A probe that names
  another date and release ran then, with that release. Each probe gives its
  command, some of them under `codex sandbox`. Nothing was retained.
- **documented** or **source**: Codex's
  [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
  or `--help`, Codex's source at `rust-v0.162.0` (commit c1382380),
  OpenSSH's source at `V_10_2_P1`, or a Dashpot runner's source.
- **inference** and **unknown**, as named.

An observed or probed result on a release other than 0.162.0 (0.162.1 or
0.163.0) is not a 0.162.0 qualification result. Nor does any observed or
probed result say anything about a Worker unless it names one. The 0.160.0
measurements stay dated history, and this document does not restate them
as current.

## Friction register

### F1: The Worktree Root and Git directory were read-only

- **When**: the initial preflight, recorded in the Issue body on
  2026-10-10. The release and launch options were not recorded. The later
  recheck was on 2026-10-12, with 0.162.1.
- **Operation**: a Lead's `workspace-write` sandbox checks before binding,
  then Worktree preparation and commits.
- **Result** (observed): create-and-remove probes of the durable Worktree
  Root, the resolved shared Git directory and the default pre-commit cache
  failed with `Read-only file system`. The uv cache was already writable,
  and `uv sync --locked --group dev` passed.
- **Later** (observed): after the Lead was relaunched with grants, the same
  probes passed for the Worktree Root, the Git directory, a dedicated
  fixture parent and both gate-cache destinations.
- **Probe**: the skill's first two checks,
  `touch <dir>/.execute-issues-check && rm <dir>/.execute-issues-check`,
  run inside the session.
- **Matches** (measured, 0.160.0): Codex's default for a trusted project
  adds no writable roots and turns the network off, and the skill's resume
  command fixes both.
- **Remedy**: the skill's resume command. The cost of the Git-directory
  grant, which lets every agent write hooks and Git configuration, is
  already disclosed there.
- **Probed, write-free** (2026-10-13, 0.162.1, Linux): inside
  `codex sandbox`, `test -w <dir>` reports a grant without writing
  anything. With no writable roots, the Worktree Root, the Git directory
  and `/var/tmp` all read as read-only. With
  `-c 'sandbox_workspace_write.writable_roots=[<Worktree Root>, <Git directory>]'`,
  the first two read as writable and `/var/tmp` stays read-only. What
  macOS Seatbelt reports is unknown.
- **Unknown**: which launch options the later grants came from.

### F2: The Worktree Root differs between sessions

- **When** (probed): 2026-10-13, Dashpot 0.1.0.
- **Operation**: `dashpot worktree create`, and the grant that covers
  where it creates.
- **Result**: no machine-local `config.toml` exists and
  `DASHPOT_WORKTREE_ROOT` is unset in a Claude Code session. So
  `dashpot worktree create 671 --json`, when it created this Issue's
  Worktree there, reported
  `"worktreeRootSource": "default-sibling"` and `<main checkout>.worktrees`.
  The Codex qualification Lead's grants and probes name another directory,
  `~/projects/.worktrees/dashpot` (observed), and `git worktree list` shows
  Issue Worktrees in both (probed).
- **Consequence** (inference): suppose a Lead is granted one root, and its
  `worktree create` resolves to the other. It then creates Worktrees its
  Workers cannot write. The skill tells the Lead to read `worktreeRoot`
  from a dry run, which catches this only when the dry run runs with the
  same environment as the later creates.
- **Remedy**: one `worktree_root` in the
  [machine-local settings](../installation.md#machine-local-settings), which
  every session reads. Choosing that directory is the operator's decision.
- **Unknown**: how the Codex Lead selects its root, whether
  `--worktree-root` on each command or `DASHPOT_WORKTREE_ROOT` in its
  environment.

### F3: Writable caches, but the cache variables unset

- **When** (observed): 2026-10-12, 0.162.1, a resumed Lead.
- **Operation**: environment preparation, the gates and the commit hook,
  for the Lead and for each Worker.
- **Result**: both cache destinations were writable, but `UV_CACHE_DIR` and
  `PRE_COMMIT_HOME` were unset in the Lead's tool environment. A
  per-command prefix,
  `env UV_CACHE_DIR=<Worktree Root>/.cache/uv PRE_COMMIT_HOME=<Worktree Root>/.cache/pre-commit`,
  let locked dependency preparation pass, and a Git hook inherits the
  prefix.
- **Probe**: the skill's fourth check, `echo "UV_CACHE_DIR=$UV_CACHE_DIR PRE_COMMIT_HOME=$PRE_COMMIT_HOME"`,
  run inside the session.
- **Mechanism** (measured, 0.160.0): a Codex session hosted by the managed
  daemon runs every command with the daemon's environment, fixed when the
  daemon started. A later client's environment never reaches a command, a
  resume with `-C` included. A resume that adds writable roots ran
  in-process instead, not on the daemon. `shell_environment_policy.set` in
  the resume command reached each Worker's shell and the Git hook its
  commit ran.
- **Mechanism** (inference): the operator's launcher sets `UV_CACHE_DIR` in
  the client's own environment and grants that directory. It does not set
  `PRE_COMMIT_HOME` at all. A grant is not an environment variable, and a
  client's environment reaches its commands only where that client hosts
  the session. This is consistent with the observation, but nobody
  established which launch layer dropped the variables.
- **Probed**: `codex sandbox` applies `-c shell_environment_policy.set.<VAR>`
  and `-c sandbox_workspace_write.writable_roots=[…]` to the command it
  runs. With this command, the probe directory was writable, `/var/tmp`
  outside it was not, and the variable was set:

  ```bash
  codex sandbox -c 'sandbox_mode="workspace-write"' \
    -c 'sandbox_workspace_write.writable_roots=["/var/tmp/probe"]' \
    -c 'shell_environment_policy.set.UV_CACHE_DIR="/var/tmp/probe/uv"' \
    -- /path/to/probe.sh   # touches /var/tmp/probe and /var/tmp, prints UV_CACHE_DIR
  ```

- **Remedy**: the skill's resume command already sets both variables with
  `shell_environment_policy.set`. The per-command prefix is a workaround
  for a session launched without them. It reaches only the commands that
  carry it, so each brief would have to repeat it.
- **Source** (rust-v0.162.0): `--profile`, or any `-c` override beyond a
  short allowlist, keeps the session off the managed daemon
  (`tui/src/daemon_startup.rs:61-124`).
- **Inference**: both the resume command and a profile launch would then
  run the session in-process, and the terminal's environment would reach
  its commands.
- **Unknown**: which process hosts a resumed session that adds roots,
  which is unmeasured at 0.162.x. Also unknown, and unmeasured at 0.160.0
  too: whether the Lead's own shell gets `shell_environment_policy.set`.
  [#678](https://github.com/ned2/dashpot/issues/678) measures both.

### F4: Codex's user configuration and the resume command's sandbox options

- **When** (probed): 2026-10-13, 0.162.1, by reading the operator's
  `~/.codex/config.toml`.
- **Documented**: `default_permissions` names a permissions profile, a
  `[permissions.<name>]` table with its `filesystem` and `network` grants.
  It must not be combined with `sandbox_mode` or
  `[sandbox_workspace_write]`.
- **Result**: the operator's Codex user configuration selects a named
  permissions profile with `default_permissions`. The skill's resume
  command sets `--sandbox workspace-write` and
  `sandbox_workspace_write.network_access`.
- **Source** (rust-v0.162.0):
  - `--sandbox` makes Codex use the legacy sandbox options outright
    (`core/src/config/mod.rs:2599`), and drops the permissions profile a
    resumed thread saved (`:3490-3497`).
  - Setting both as launch overrides is an error (`:3385-3390`), but
    `default_permissions` in a configuration file plus `--sandbox` is not.
  - `--approve-for-me` adds `sandbox_mode="workspace-write"`
    (`utils/cli/src/shared_options.rs:80-94`).
- **Inference**: the resume command does not combine with the operator's
  profile. It silently replaces it, deny rules included, and
  `--approve-for-me` would do the same to a profile launch.
- **Unknown**: what a 0.162.0 session actually runs with. No retained
  experiment ran the resume command over a configuration that sets
  `default_permissions`. The checks in the resumed session are the only
  evidence of what took effect, and
  [#678](https://github.com/ned2/dashpot/issues/678) measures it.
- **Probed, confounded**: under that configuration, outbound HTTPS from
  `codex sandbox -c 'sandbox_mode="workspace-write"' -- <script>` to a
  public API endpoint returned 200. It did so with and without
  `-c sandbox_workspace_write.network_access=true`. The result reflects
  the operator's profile, not Codex's default, so it is not evidence either
  way. It also appears to disagree with the source reading above, though
  it used `-c sandbox_mode`, not `--sandbox`. That is one more reason to
  measure.

### F5: Automatic approval review

- **When** (observed): the initial preflight, 2026-10-10.
- **Result**: `approvals_reviewer = "auto_review"` was active, and the
  skill then required running an Arc without it.
- **Settled**: [#672](https://github.com/ned2/dashpot/issues/672), by
  [PR #673](https://github.com/ned2/dashpot/pull/673). Automatic review is
  an acceptable posture for Leads and Workers, and manual review and
  `never` remain available. The original candidate of forcing human review
  is dated analysis, not a requirement.

### F6: An invalid launch flag combination

- **When**: observed on 2026-10-12 with 0.162.1, and probed on 2026-10-13
  with `codex --approve-for-me -a never completion bash`.
- **Result**: Codex exits before starting, with status 2 and
  `error: the argument '--approve-for-me' cannot be used with '--ask-for-approval <APPROVAL_POLICY>'`.
  The observed launch used `-a on-request`, and the probe `-a never`.
- **Class**: a launch-command mistake, not a reviewer denial or a Worker
  defect. Per `codex --help` (documented, 0.162.1), `--approve-for-me`
  already routes approval requests through automatic review under
  `workspace-write`.
- **Remedy**: name the conflict in the skill wherever it offers `-a`.

### F7: Credentials in a new session or a linked Worktree

- **When** (observed): 2026-10-12, 0.162.1.
- **Result**: an independent policy session started in tmux reported no
  `gh` authentication, while the original Lead had a `GH_TOKEN`. In the
  policy Worktree, plain tool commands had no `GH_TOKEN` or
  `GITHUB_TOKEN`. The main checkout has an ignored `.envrc`, but neither
  the Worktree nor its Worktree Root has one. A command-scoped
  `direnv exec <main checkout> …` supplied `GH_TOKEN`, checked by presence
  only, and read the Issue while keeping the Worktree as the working
  directory.
- **Mechanism** (measured, 0.160.0 and direnv 2.37.1): direnv does not
  follow a session into a linked Worktree. A Codex daemon's commands keep
  the daemon's start-time environment
  ([credentials in a linked Worktree](../installation.md#credentials-in-a-linked-worktree)).
- **Remedies**: the installation guide already documents two
  operator-local options. One is a Worktree Root `.envrc` that runs
  `source_env` on the main checkout's. The other is a launcher wrapper. A
  third is `ned2/env#8`'s launcher, which runs Codex under `direnv exec`
  of an explicitly approved environment source. By the 0.160.0
  measurements, that launcher's environment reaches tool commands when its
  client starts the daemon, or when it runs with
  `--disable daemon_auto_start` while no daemon runs. By inference from
  the same rule, it also reaches them when the session runs in-process, as
  a resume adding roots did; no retained run measured that resume's
  environment. Which of these applies at 0.162.x is unknown.
- **Unknown**: inheritance at 0.162.1 for a fresh Lead, a resumed Lead and
  a fresh Worker. `ned2/env#8`'s acceptance asks for exactly those
  measurements.
- **Boundary**: Dashpot loads no ignored configuration and supplies no
  credentials. A token never goes in a `-c` value, where `ps -ww` shows it.

### F8: GitHub reads do not prove writes

- **When** (observed): 2026-10-12, 0.162.1.
- **Result**: authenticated API reads and a command-scoped HTTPS fetch
  passed. Creating an Issue with the same credentials failed with
  `GraphQL: Resource not accessible by personal access token (createIssue)`.
  Later, from the policy session's external credential environment, Issue
  creation, a PR (#673) and Issue comments all succeeded.
- **Probe**: not reproducible as a check. A write probe would itself be
  a mutation.
- **Class**: API permission, separate from authentication. A fine-grained
  token can read a repository it cannot write Issues or PRs in. A read
  cannot establish Issue creation, PR management, push or merge rights.
- **Remedy**: the Lead's preflight confirms authentication with
  `gh auth status`.
  The Lead treats its first write of each kind as that permission's check,
  and reports a refusal as a blocker naming the operation. It never falls
  back to other credentials.
- **Unknown**: which permissions the token that refused lacked, and
  whether the later success used another token.

### F9: SSH fails inside the sandbox before connecting

- **When**: observed on 2026-10-12 with 0.162.1, and probed on
  2026-10-13.
- **Result** (observed): inside the sandbox, `git ls-remote` and a push
  over SSH failed with
  `Bad owner or permissions on /etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`.
  The same push, retried by exact-command escalation outside the sandbox,
  succeeded. An earlier attempt outside the sandbox had failed with
  `Permission denied (publickey)`. That authentication change happened on
  the operator's side and was not investigated.
- **Probed**: the probe was
  `codex sandbox -c 'sandbox_mode="workspace-write"' -- <script>`, run as
  uid 1000.
  - `stat -L` showed both `/etc/ssh/ssh_config` and the fragment as uid
    **65534**, mode 644.
  - `ssh -G github.com` exited 255 with the message above.
  - `ssh -F /dev/null -G github.com` exited 0.
  - On the host, the fragment is a symlink to
    `/usr/lib/systemd/ssh_config.d/20-systemd-ssh-proxy.conf`, owned by
    root with mode 644, and `ssh -G github.com` passes.
- **Mechanism** (source): OpenSSH reads the system-wide `ssh_config`
  without a permission check. But every file it `Include`s gets
  `SSHCONF_CHECKPERM`, which is fatal unless the owner is uid 0 or the
  invoking user and the mode has no group or other write bit. Ubuntu's
  `ssh_config` includes `/etc/ssh/ssh_config.d/*.conf`. A file passed with
  `-F` is read without the check, which is why selecting the fragment or a
  user-owned copy explicitly passed.
- **Mechanism** (inference): Codex's Linux sandbox maps only the invoking
  uid, so files root owns appear owned by the overflow uid 65534. Any
  root-owned fragment that the system configuration includes then fails
  the check. The host file needs no repair.
- **Consequence** (inference): on such a host, SSH through the system
  configuration fails for every agent under the sandbox, however the
  network option is set. A Worker's push would fail too, though none was
  observed.
- **Candidate remedies**, each an explicit operator choice:
  1. Push outside the sandbox, by an escalation the operator's posture
     decides, as the observed retry did.
  2. Select HTTPS transport with `gh` as the credential helper
     explicitly, never by silently rewriting the remote.
  3. Inject `GIT_SSH_COMMAND` with an `-F` naming a user-owned
     configuration, through `shell_environment_policy.set`. This skips the
     system configuration, including the systemd proxy fragment. It is
     unmeasured.
- **Unknown**: whether a real session's sandbox maps uids exactly as
  `codex sandbox` does. The observed failure suggests it does.

### F10: The fixture parent is deliberately not writable

- **When**: observed on 2026-10-10 and 2026-10-12, and probed on
  2026-10-13 and 2026-10-16.
- **Result** (observed): the baseline `codex-639` runner creates its
  fixture directly under `/var/tmp`, which refused the Lead's write probe.
  A dedicated parent, `/var/tmp/dashpot-codex-0162-qualification`, was
  granted later and passed the probe.
- **Probed**: `touch /var/tmp/.probe` under
  `codex sandbox -c 'sandbox_mode="workspace-write"'` failed with
  `Read-only file system`.
- **Design** (source, with the control write measured): the runner puts the
  fixture under `/var/tmp` *because* `workspace-write` does not grant it.
  The fixture's own Codex then sandboxes the fixture as it would a checkout
  in a home directory, which the experiment's refused control write
  measured. The runner also refuses to start under a harness process, and
  the repository runs it detached with `setsid -f`.
- **Probed** (2026-10-16, 0.163.0,
  [#685](https://github.com/ned2/dashpot/issues/685)): under
  `codex sandbox -c 'sandbox_mode="workspace-write"'`, the command runs as
  pid 2 with parent pid 1, so a runner's ancestry walk ends at once and
  sees no harness.
- **Consequence** (inference): in a real Lead session, whose sandbox the
  probe suggests uses the same PID namespace, the runner's
  harness-ancestry refusal would not stop it. Granting the fixture parent
  to the Lead would then let a runner start inside the Lead's sandbox,
  with the Lead's grants. And a fixture parent writable for the fixture's
  own Codex would change the permissions being measured.
- **Unknown**: how a qualification Lead launches a pinned runner at all,
  whether by escalation outside the sandbox, by the operator, or by a
  runner option for a validated parent. Also unknown: whether a dedicated
  parent leaves the fixture's denied-write controls intact. Any runner
  change is a source change, which needs renewed evidence under the Arc's
  source-hash rules.

### F11: tmux handoff needed escalation

- **When** (observed): 2026-10-12, 0.162.1.
- **Operation**: the qualification Lead driving tmux to start and steer
  the independent policy session.
- **Result**: tmux control needed command-scoped sandbox escalation. The
  exact refusal was not recorded.
- **Probe**: not reproducible as recorded.
- **Class**: a handoff observation. Normal Sub-agent dispatch does not use
  tmux, so this is not a requirement for Workers.
- **Unknown**: which write or socket the sandbox refused.

## Classification

| Class | Items |
| --- | --- |
| Operator provisioning (one-time setup) | F1 grants, F2 one `worktree_root`, F7 credential source, F9 transport choice |
| Skill wording and setup guidance | F3 grant versus variable, F4 profile conflict, F6 flag conflict, F8 reads versus writes, F9 failure identification, consolidated reporting |
| Harness or environment behaviour | F3 daemon environment, F9 sandbox uid mapping, F11 |
| Authentication | F7 |
| API permission | F8 |
| Git transport | F9 |
| Fixture placement | F10 |
| Settled policy | F5 |
| Unresolved decisions | the Worker-side check, `worktree_root`, transport, fixture launch, `default_permissions` support (see [Maintainer choices](#maintainer-choices)) |

## Minimum capabilities by operation

What a sandboxed Lead and its Workers need, and nothing more. Each grant
applies to every agent of the session. A gate tool's cache is that tool's
private state: grant it as a directory, never read it, and never cite it
as evidence.

| Operation | Needs | Evidence |
| --- | --- | --- |
| Edit an Issue Worktree | Write on the one Worktree Root that `worktree create` resolves (F2) | measured, 0.160.0 |
| `git commit`, `git worktree add` | Write on the main checkout's Git directory (`git rev-parse --path-format=absolute --git-common-dir`), which exposes its hooks and configuration to every agent | measured, 0.160.0: both worked under the grant, and the default refused the Git-directory write |
| Prepare the environment, run the gates, commit through the hook | Each gate tool's cache both writable and named in every shell, with `UV_CACHE_DIR` and `PRE_COMMIT_HOME` set by `shell_environment_policy.set` and the caches inside the Worktree Root. Each cache keeps to its own directory, not all of `~/.cache` | measured, 0.160.0 |
| `git ls-remote`, `git push` | Network on, plus a transport that works under the sandbox (F9) | measured over HTTP, 0.160.0; SSH observed failing |
| `gh` reads | Network on, plus a token in the commands' environment (F7) | observed |
| `gh` Issue and PR writes, merges | A token with those permissions (F8). A merge also needs the operator's merge authority | observed |
| Run a pinned harness experiment | Outside the Lead's sandbox and ancestry, as the repository's experiment rules require. The runner's own process writes only its fixture under one dedicated parent. That parent stays out of the measured fixture's grants unless the grant is the scenario under test (F10) | source, with the control write measured; launch unknown |

## Proposal

### 1. One preflight, every failure, one remedy (skill, in this change)

The Codex reference now tells the Lead to run every check, and
`gh auth status`, before it reports. It gives the operator every failure in
one message: one launch command for the sandbox's failures, and beside it
each choice only the operator can make, such as the transport. It does not
stop at the first failure. The reference also names the failures this
register identified, each with its evidence:

- a grant is not a variable;
- a `default_permissions` profile conflicts with the resume command's
  sandbox options;
- `--approve-for-me` cannot be combined with `-a`;
- the SSH ownership refusal blocks binding, but leaves its remedy to the
  operator;
- reads do not prove writes.

A resumed Lead reruns the checks rather than trusting the command it was
resumed with.

### 2. A Dashpot preflight that verifies a launch profile (ownership decided; ADR pending, #679)

The execute-issues skill ships to every operator. So checking a Codex
Arc's provisioning is Dashpot's job, not the job of one operator's
launcher. The maintainer decided this on 2026-10-16.
[#679](https://github.com/ned2/dashpot/issues/679) tracks the ADR and the
command.

The check verifies a launch profile the operator writes (proposal 4). It
never constructs or prints launch flags, and never writes the profile.
`codex sandbox` takes `--profile` (documented, `--help` on 0.162.1). With
`-c` overrides, it applies writable roots and `shell_environment_policy.set`
to the command it runs (F3, probed). The inference, until
[#678](https://github.com/ned2/dashpot/issues/678) compares them, is that
probes run under `codex sandbox --profile <name>` check the same grants
the launch will use, before any session starts:

- `test -w` on the Worktree Root that Dashpot resolves itself, on the Git
  directory and on each cache. The probe writes nothing (F1, probed);
  whether `codex sandbox` itself writes state under `$CODEX_HOME` is
  unknown;
- that each injected variable is set and names a directory inside the
  granted roots;
- `ssh -G` for an SSH remote (F9), and `git ls-remote` for the remote;
- that `gh auth status` succeeds, by presence and exit status only.

It reports every failure at once, each with its remedy. It has two limits.
`codex sandbox` runs with the invoking terminal's environment, not a
daemon's, so it cannot show what a daemon-hosted session's commands
inherit (F3, F7). It also runs no Worker. The checks inside the session
stay authoritative.

The check needs an ADR first, because the check runs Codex's own sandbox
tool and
[ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)
does not cover launching harnesses. The ADR would let Dashpot run that
tool, with probes that write nothing, to check provisioning. The check
would:

- never start an Agent Session;
- never read or print a credential value;
- be requalified for each pinned release.

Dashpot may ship a profile template, but never writes a profile or
`config.toml` in `$CODEX_HOME`. There, `integrate` writes only its hooks
file
([ADR 0130](../adr/0130-write-integrates-configuration-where-each-harness-reads-it.md)).
The `ned2/env#8` launcher would call the check, and keep only credential
loading.

Two dependencies apply. Neither the command nor its guidance recommends a
profile launch until #678 passes. And the Worktree Root should be settled
first (F2, maintainer choice 4), because the profile hard-codes it.

### 3. A Worker-side check (proposed)

A Worker shares the Lead's sandbox, but nothing yet shows that a 0.162.x
Worker's shell has what the Lead's has. The brief template would open each
Worker's cycle with the fourth check and `gh auth status`, run in its
Issue Worktree, and have the Worker report the result in its first message.
On a failure, the Lead holds the rest of the wave and reports it with the
same consolidated remedy. This adds one command to every Worker's start and
needs no new grant. Until the maintainer approves it, Worker
verification stays incomplete: neither the Lead's own checks nor the
Dashpot preflight covers a fresh Worker.

### 4. A persistent launch configuration (proposed, unqualified)

The long resume command could become one profile. Codex documents profile
files, `$CODEX_HOME/<name>.config.toml` selected with `--profile <name>`,
and named permissions profiles with filesystem and network grants. A
`dashpot-arc` profile would name the Worktree Root, the Git directory, the
two caches, the network and the two variables. The launch would then
become `codex resume <session-id> -C <checkout> --profile dashpot-arc`.
The reference does not list which keys a profile file may set. In
rust-v0.162.0's source, `resume` takes `-p/--profile`. The profile file
loads as a second user configuration layer, through the same loader as
`config.toml` (`config/src/loader/mod.rs:290-338`). By inference, then, it
can set any key, `shell_environment_policy` included.

Two other source findings bear on it. The measured command's `--sandbox`
replaces an operator's `default_permissions` profile (F4). And writable
roots keep `.git` read-only only when no explicit rule names it
(`protocol/src/permissions.rs:860-871`).

The maintainer chose to qualify the profile launch within the 0.162.0
requalification of the resume command
([#678](https://github.com/ned2/dashpot/issues/678); its scope is under
[Follow-ups](#follow-ups-and-incomplete-measurements)). Until that passes,
the skill keeps the measured command.

### 5. A credential environment (tracked in `ned2/env#8`)

The launcher must account for F3's mechanism: on a running daemon, the
environment of the client it starts does not reach tool commands. Its
acceptance already asks for validation on the release being qualified: a
fresh Lead, a resumed Lead and a fresh Worker, with reads distinguished
from Issue and PR writes. Once that validation succeeds, the operator setup
and the
[credentials guidance](../installation.md#credentials-in-a-linked-worktree)
link its result. Until then, this document and the skill claim nothing
about it.

### 6. Checkpoint recovery (proposed)

A paused or resumed Lead should not ask again for what the operator already
settled. The arc map in the Arc Ledger already records the permission
posture and merge authority. The proposal adds two things to it: the
accepted launch remedy, and the date each preflight check last passed.
After a resume, the Lead then reruns the checks, compares the results, and
asks only about a check that now fails.

### 7. Transport (proposed)

The Lead's preflight names the SSH sandbox refusal (done in the skill). The
operator chooses a remedy from F9 once. The HTTPS and `GIT_SSH_COMMAND`
options each need a measured push from a Worker before the skill
recommends either.

## Maintainer choices

1. Where the preflight lives. **Decided**: Dashpot owns a
   read-only check, and an ADR comes first
   ([#679](https://github.com/ned2/dashpot/issues/679), proposal 2).
2. Whether to add the Worker-side check to the brief template
   (proposal 3, [#682](https://github.com/ned2/dashpot/issues/682)).
3. Whether to qualify the profile-file launch (proposal 4). **Decided**:
   qualify it within the 0.162.0 requalification of the resume command
   ([#678](https://github.com/ned2/dashpot/issues/678)), which states the
   resume command's interaction with `default_permissions`.
4. Which `worktree_root` this machine uses (F2). That is the operator's
   setting, not a repository change. The Dashpot preflight and a launch
   profile both depend on it (proposal 2).
   [#683](https://github.com/ned2/dashpot/issues/683) documents that the
   setting applies to every Repository.
5. Which F9 remedy the operator chooses, once
   [#684](https://github.com/ned2/dashpot/issues/684) has measured each.
   There is no machine-wide default.
6. How a qualification Lead runs pinned experiment runners (F10,
   [#685](https://github.com/ned2/dashpot/issues/685)).
7. Whether a `default_permissions` profile counts as a supported Lead
   configuration, once #678 has stated how it interacts with the launch.

## Follow-ups and incomplete measurements

- Qualify the resume command, or its profile replacement, on 0.162.0
  ([#678](https://github.com/ned2/dashpot/issues/678)). That covers:
  - whether the Lead's own shell and a fresh Worker's shell get the
    injected variables;
  - the command's interaction with `default_permissions`;
  - `codex sandbox --profile` compared with the checks inside the session.
- Decide the preflight's boundary by ADR, then add the read-only check
  ([#679](https://github.com/ned2/dashpot/issues/679)).
- Measure environment inheritance at 0.162.x for a fresh Lead, a resumed
  Lead and a fresh Worker, through `ned2/env#8`.
- Measure a Worker's push under each SSH remedy
  ([#684](https://github.com/ned2/dashpot/issues/684)).
- Decide how a sandboxed Lead launches the pinned runners, and implement
  any runner change with renewed evidence
  ([#685](https://github.com/ned2/dashpot/issues/685)).
- Add the Worker-side check, if chosen
  ([#682](https://github.com/ned2/dashpot/issues/682)).
- Document the machine-wide scope of `worktree_root`
  ([#683](https://github.com/ned2/dashpot/issues/683)).
- Measure `gh` under the sandbox grant, which the 0.160.0 experiment could
  not.

These add no prerequisite to the qualification Arc's Issues (#644, #663,
#664, #665, #666, #668, #399), and none of them is complete.
