---
status: proposal
date: 2026-10-13
---

# Codex Arc provisioning and preflight

What a sandboxed Codex Lead needs before it binds, what went wrong when one
set up the Codex 0.162.0 qualification Arc, and a bounded proposal for making
that setup reusable. Written for
[Issue #671](https://github.com/ned2/dashpot/issues/671). The operator
launcher that loads a credential environment is tracked separately in
`ned2/env#8`, which owns its implementation and its release-qualified
validation; this document owns the Dashpot-facing account and links that
work as coordination only, not as a prerequisite.

The [`dashpot-execute-issues` Codex reference](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md#codex)
is the shipped guidance. It changes in the same change as this document
where a finding below is verified; everything else here is a proposal until
the maintainer approves it.

## Evidence classes

Each claim carries one:

- **measured**: a retained, independently verified Dashpot experiment shows
  it. The Worker experiments are pinned to **codex-cli 0.160.0**
  ([sandboxed Worker cycle](../spikes/codex-sandboxed-worker-cycle-spike.md),
  [linked Worktree environment](../spikes/linked-worktree-environment-spike.md)).
- **observed**: a session or preflight saw it, as recorded on Issue #671 on
  2026-10-11 and 2026-10-12, with **codex-cli 0.162.1** where a release is
  named. Nothing was retained, and nobody verified it independently.
- **probed**: a command this document's author ran on 2026-10-13, with
  codex-cli 0.162.1 on Ubuntu (Linux 7.0.0, OpenSSH 10.2p1), reproducible
  with the command given. It ran outside any Codex session, with
  `codex sandbox`, and nothing was retained.
- **documented** or **source**: Codex's
  [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
  or `--help`, or OpenSSH's source at `V_10_2_P1`.
- **inference** and **unknown**, as named.

An observed or probed result on 0.162.1 is not a 0.162.0 qualification
result, and says nothing about a Worker unless it names one. The 0.160.0
measurements stay dated history; this document does not restate them as
current.

## Friction register

### F1: The Worktree Root and Git directory were read-only

- **Operation**: a Lead's `workspace-write` sandbox checks before binding,
  then Worktree preparation and commits.
- **Result** (observed, initial preflight): create-and-remove probes of the
  durable Worktree Root, the resolved shared Git directory and the default
  pre-commit cache failed with `Read-only file system`. The uv cache was
  already writable, and `uv sync --locked --group dev` passed.
- **Later** (observed, 2026-10-12, 0.162.1): after the Lead was relaunched
  with grants, the same probes passed for the Worktree Root, the Git
  directory, a dedicated fixture parent and both gate-cache destinations.
- **Matches** (measured, 0.160.0): Codex's default for a trusted project
  adds no writable roots and turns the network off, and the skill's resume
  command fixes both.
- **Remedy**: the skill's resume command. The cost of the Git-directory
  grant, which lets every agent write hooks and Git configuration, is already
  disclosed there.
- **Unknown**: none new. Which launch the later grants came from is not
  recorded.

### F2: The Worktree Root differs between sessions

- **Operation**: `dashpot worktree create`, and the grant that covers
  where it creates.
- **Result** (probed): no machine-local `config.toml` exists and
  `DASHPOT_WORKTREE_ROOT` is unset in a Claude Code session, so
  `worktree create` there reports `worktreeRootSource: default-sibling` and
  `<main checkout>.worktrees`. The Codex qualification Lead's grants and
  probes name another directory, `~/projects/.worktrees/dashpot`, and
  `git worktree list` shows Issue Worktrees in both.
- **Consequence** (inference): a Lead granted one root, whose `worktree
  create` resolves to the other, creates Worktrees its Workers cannot write.
  The skill tells the Lead to read `worktreeRoot` from a dry run, which
  catches this only when the dry run runs with the same environment as the
  later creates.
- **Remedy**: one `worktree_root` in the
  [machine-local settings](../installation.md#machine-local-settings), which
  every session reads. Choosing that directory is the operator's decision.

### F3: Writable caches, but the cache variables unset

- **Operation**: environment preparation, the gates and the commit hook,
  for the Lead and for each Worker.
- **Result** (observed, 0.162.1, resumed Lead): both cache destinations
  were writable, but `UV_CACHE_DIR` and `PRE_COMMIT_HOME` were unset in the
  Lead's tool environment. A per-command prefix,
  `env UV_CACHE_DIR=<Worktree Root>/.cache/uv PRE_COMMIT_HOME=<Worktree Root>/.cache/pre-commit`,
  let locked dependency preparation pass, and a Git hook inherits the prefix.
- **Mechanism** (measured, 0.160.0): a Codex session hosted by the managed
  daemon runs every command with the daemon's environment, fixed when it
  started. A later client's environment, a resume with `-C` included, never
  reaches a command. `shell_environment_policy.set` in the resume command does
  reach each Worker's shell and the Git hook its commit runs.
- **Mechanism** (inference): the operator's launcher sets `UV_CACHE_DIR` in
  the client's own environment and grants that directory, and does not set
  `PRE_COMMIT_HOME` at all. A grant is not an environment variable, and a
  client's environment reaches its commands only when that client hosts the
  session or starts the daemon. This is consistent with the observation, but
  nobody established which launch layer dropped the variables.
- **Probed**: `codex sandbox` applies `-c shell_environment_policy.set.<VAR>`
  and `-c sandbox_workspace_write.writable_roots=[…]` to the command it runs:

  ```bash
  codex sandbox -c 'sandbox_mode="workspace-write"' \
    -c 'sandbox_workspace_write.writable_roots=["/var/tmp/probe"]' \
    -c 'shell_environment_policy.set.UV_CACHE_DIR="/var/tmp/probe/uv"' \
    -- /path/to/probe.sh   # prints UV_CACHE_DIR and touches /var/tmp/probe
  ```

- **Remedy**: the skill's resume command already sets both variables with
  `shell_environment_policy.set`. The per-command prefix is a workaround for a
  session that was not launched with them. It reaches only the commands that
  carry it, so each brief would have to repeat it.
- **Unknown**: at 0.162.x, which process hosts a resumed session that adds
  roots. At 0.160.0, such a resume ran in-process rather than on the daemon.
  Also unknown: whether the Lead's own shell gets `shell_environment_policy.set`
  (unmeasured at 0.160.0 too).

### F4: Codex's user configuration and the resume command's sandbox options

- **Documented**: `default_permissions`, the name of a permissions profile
  (`[permissions.<name>]`, with its `filesystem` and `network` grants), must
  not be combined with `sandbox_mode` or `[sandbox_workspace_write]`.
- **Result** (observed): the operator's Codex user configuration selects a
  named permissions profile with `default_permissions`. The skill's resume
  command sets `--sandbox workspace-write` and
  `sandbox_workspace_write.network_access`.
- **Unknown**: what Codex does with both. No retained experiment ran the
  resume command over a configuration that sets `default_permissions`. The
  checks in the resumed session are the only evidence of what took effect.
- **Probed, confounded**: under that configuration, outbound HTTPS from
  `codex sandbox` succeeded with and without
  `sandbox_workspace_write.network_access=true`. The network result
  reflects the operator's profile, not Codex's default, so it is not
  evidence either way.

### F5: Automatic approval review

- **Result** (observed): `approvals_reviewer = "auto_review"` was active,
  and the skill then required running an Arc without it.
- **Settled**: [#672](https://github.com/ned2/dashpot/issues/672), by
  [PR #673](https://github.com/ned2/dashpot/pull/673). Automatic review is
  an acceptable posture for Leads and Workers, and manual review and `never`
  remain available. The original candidate of forcing human review is dated
  analysis, not a requirement.

### F6: An invalid launch flag combination

- **Result** (observed, then probed): `codex --approve-for-me -a on-request …`
  exits before starting, with
  `error: the argument '--approve-for-me' cannot be used with '--ask-for-approval <APPROVAL_POLICY>'`.
  The same refusal comes back for `-a never`, with status 2.
- **Class**: a launch-command mistake, not a reviewer denial or a Worker
  defect. `--approve-for-me` already selects automatic review under
  `workspace-write`.
- **Remedy**: name the conflict in the skill wherever it offers `-a`.

### F7: Credentials in a new session or a linked Worktree

- **Result** (observed): an independent policy session that was started
  in tmux reported no `gh` authentication, while the original Lead had a
  `GH_TOKEN`. In the policy Worktree, plain tool commands had no `GH_TOKEN`
  or `GITHUB_TOKEN`. The main checkout has an ignored `.envrc`, but neither
  the Worktree nor its Worktree Root has one. A command-scoped
  `direnv exec <main checkout> …` supplied `GH_TOKEN`, checked by presence
  only, and read the Issue while keeping the Worktree as the working
  directory.
- **Mechanism** (measured, 0.160.0, and direnv 2.37.1): direnv does not
  follow a session into a linked Worktree, and a Codex daemon's commands keep
  the daemon's start-time environment
  ([credentials in a linked Worktree](../installation.md#credentials-in-a-linked-worktree)).
- **Remedies**: the two operator-local options the installation guide
  already documents, a Worktree Root `.envrc` that runs `source_env` on the
  main checkout's, or a launcher wrapper. A third is `ned2/env#8`'s
  launcher, which runs Codex under `direnv exec` of an explicitly approved
  environment source. By the measured daemon behaviour, that launcher's
  environment reaches tool commands only when its client starts the daemon,
  or runs with `--disable daemon_auto_start` while no daemon runs.
- **Unknown**: inheritance at 0.162.1 for a fresh Lead, a resumed Lead and a
  fresh Worker. `ned2/env#8`'s acceptance asks for exactly those
  measurements.
- **Boundary**: Dashpot loads no ignored configuration and supplies no
  credentials. A token never goes in a `-c` value, where `ps -ww` shows it.

### F8: GitHub reads do not prove writes

- **Result** (observed): authenticated API reads and a command-scoped
  HTTPS fetch passed. Creating an Issue with the same credentials failed with
  `GraphQL: Resource not accessible by personal access token (createIssue)`.
  Later, from the policy session's external credential environment, Issue
  creation, a PR (#673) and Issue comments all succeeded.
- **Class**: API permission, separate from authentication. A fine-grained
  token can read a repository it cannot write Issues or PRs in. A read
  probe cannot establish Issue creation, PR management, push or merge
  rights, and a write probe would itself be a mutation.
- **Remedy**: the preflight confirms authentication (`gh auth status`).
  The Lead treats its first write of each kind as that permission's check,
  and reports a refusal as a blocker naming the operation. It never falls
  back to other credentials.

### F9: SSH fails inside the sandbox before connecting

- **Result** (observed): inside the sandbox, `git ls-remote` and a push over
  SSH failed with
  `Bad owner or permissions on /etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`.
  The same push, retried by exact-command escalation outside the sandbox,
  succeeded. An earlier attempt outside the sandbox had failed with
  `Permission denied (publickey)`. That authentication change happened on
  the operator's side and was not investigated.
- **Probed**: inside `codex sandbox -c 'sandbox_mode="workspace-write"'`, as
  uid 1000, `stat -L` shows both `/etc/ssh/ssh_config` and the fragment as
  uid **65534**, mode 644, and `ssh -G github.com` fails with the message
  above, while `ssh -F /dev/null -G github.com` passes. On the host, the
  fragment is a symlink to `/usr/lib/systemd/ssh_config.d/20-systemd-ssh-proxy.conf`,
  owned by root with mode 644, and `ssh -G github.com` passes.
- **Mechanism** (source): OpenSSH reads the system-wide `ssh_config`
  without a permission check, but every file it `Include`s gets
  `SSHCONF_CHECKPERM`, which is fatal unless the owner is uid 0 or the
  invoking user and the mode has no group or other write bit. Ubuntu's
  `ssh_config` includes `/etc/ssh/ssh_config.d/*.conf`. A file passed with
  `-F` is read without the check, which is why selecting the fragment or a
  user-owned copy explicitly passed.
- **Mechanism** (inference): Codex's Linux sandbox maps only the user's
  uid, so files that root owns appear owned by the overflow uid 65534, and
  any root-owned fragment that the system configuration includes fails the
  check. The host file needs no repair.
- **Consequence**: on such a host, no agent under the sandbox can reach an
  SSH remote, a Worker's push included, however the network option is set.
- **Candidate remedies**, each an explicit operator choice:
  1. push outside the sandbox, by an escalation the user's posture decides,
     as the observed retry did;
  2. select HTTPS transport with `gh` as the credential helper explicitly,
     never by silently rewriting the remote;
  3. inject `GIT_SSH_COMMAND` with an `-F` naming a user-owned
     configuration, through `shell_environment_policy.set`. This skips the
     system configuration, including the systemd proxy fragment. It is
     unmeasured.

### F10: The fixture parent is deliberately not writable

- **Result** (observed): the baseline `codex-639` runner creates its fixture
  directly under `/var/tmp`, which refused the Lead's write probe. A
  dedicated parent, `/var/tmp/dashpot-codex-0162-qualification`, was granted
  later and passed the probe.
- **Probed**: `/var/tmp` is read-only under `codex sandbox` in
  `workspace-write`.
- **Design** (measured, and stated in the spike): the runner puts the
  fixture under `/var/tmp` *because* `workspace-write` does not grant it,
  so that the fixture's own Codex sandboxes the fixture as it would a
  checkout in a home directory. The runner also refuses to start under a
  harness process, and the repository runs it detached with `setsid -f`.
- **Consequence** (inference): granting the fixture parent to the Lead does
  not by itself let a sandboxed Lead run the runner, which refuses harness
  ancestry. If the fixture parent were writable for the fixture's own Codex,
  it would change the permissions being measured.
- **Unknown**: how a qualification Lead launches a pinned runner at all,
  whether by escalation outside the sandbox, by the operator, or by a runner
  option for a validated parent. Also unknown: whether a dedicated parent
  leaves the fixture's denied-write controls intact. Any runner change is a
  source change that needs renewed evidence under the Arc's source-hash rules.

### F11: tmux handoff needed escalation

- **Result** (observed): driving tmux for the independent policy session
  needed command-scoped sandbox escalation.
- **Class**: a handoff observation. Normal Sub-agent dispatch does not use
  tmux, so it is not a requirement for Workers.

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
| Unresolved decisions | the preflight's owner, persistent configuration, transport, fixture launch (see [Maintainer choices](#maintainer-choices)) |

## Minimum capabilities by operation

What a sandboxed Lead and its Workers need, and nothing more. Each grant
applies to every agent of the session.

| Operation | Needs | Evidence |
| --- | --- | --- |
| Edit an Issue Worktree | Write on the one Worktree Root that `worktree create` resolves (F2) | measured, 0.160.0 |
| `git commit`, `git worktree add` | Write on the main checkout's Git directory (`git rev-parse --path-format=absolute --git-common-dir`), which exposes its hooks and configuration to every agent | measured, 0.160.0 |
| Prepare the environment, run the gates, commit through the hook | Each gate tool's cache writable *and* named in every shell: `UV_CACHE_DIR`, `PRE_COMMIT_HOME` by `shell_environment_policy.set`, with the caches inside the Worktree Root. Keep each cache to its own directory, not all of `~/.cache` | measured, 0.160.0 |
| `git fetch`, `git push` | Network on, plus a transport that works under the sandbox (F9) | measured over HTTP, 0.160.0; SSH observed failing |
| `gh` reads | Network on, plus a token in the commands' environment (F7) | observed |
| `gh` Issue and PR writes, merges | A token with those permissions (F8); a merge also needs the user's merge authority | observed |
| Run a pinned harness experiment | Outside the Lead's sandbox and ancestry, as the repository's experiment rules require. A fixture parent stays out of the measured fixture's grants unless the grant is the scenario under test (F10) | measured design; launch unknown |

## Proposal

### 1. One preflight, every failure, one remedy (skill, in this change)

The Codex reference now tells the Lead to run every check before it reports,
and to give the user every failure in one message with one launch command
that remedies all of them, instead of stopping at the first. It also names
the failures this register identified: a grant is not a variable, a
`default_permissions` profile in the user's configuration, the
`--approve-for-me` flag conflict, the SSH ownership refusal, and reads not
proving writes. A resumed Lead reruns the checks rather than trusting the
command it was resumed with.

### 2. An operator-run preflight before launch (proposed)

`codex sandbox` runs a command under Codex's Linux sandbox with the same
`-c` overrides a launch takes, and applies writable roots and
`shell_environment_policy.set` (probed). A small probe script run that way,
with the overrides the launch will use, could check before any session
starts:

- write on the Worktree Root, the Git directory and each cache, then remove
  the probe file;
- that each injected variable is set;
- `ssh -G` for an SSH remote (F9), and `git ls-remote` for the remote;
- that `gh auth status` succeeds, by presence and exit status only.

It reports every failure at once. Its limits: `codex sandbox` runs with the
invoking terminal's environment, not a daemon's, so it cannot show what a
daemon-hosted session's commands inherit (F3, F7), and it does not run a
Worker. The checks inside the session stay authoritative.

Ownership is a [maintainer choice](#maintainer-choices). It could live in
the operator's launcher (`ned2/env#8`), or in a documented script. A Dashpot
command would need an ADR first: the probe writes files, and
[ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)
keeps Dashpot's mutations to named management commands.

### 3. A persistent launch configuration (proposed, unqualified)

The long resume command could become one profile. Codex documents profile
files, `$CODEX_HOME/<name>.config.toml` selected with `--profile <name>`,
and named permissions profiles with filesystem and network grants. A
`dashpot-arc` profile would name the Worktree Root, the Git directory, the
two caches, the network and the two variables, and the launch would become
`codex resume <session-id> -C <checkout> --profile dashpot-arc`. The
reference does not list which keys a profile file may set, and
`default_permissions` conflicts with the sandbox options the measured
command uses (F4), so this needs a qualification experiment before the skill
offers it. Until then the skill keeps the measured command.

### 4. A credential environment (tracked in `ned2/env#8`)

The launcher must account for F3's mechanism: on a running daemon, the
environment of the client it starts does not reach tool commands. Its
validation, a fresh Lead, a resumed Lead and a fresh Worker on the release
being qualified, with reads distinguished from Issue and PR writes, is
already its acceptance. When it is validated, the operator setup and the
[credentials guidance](../installation.md#credentials-in-a-linked-worktree)
link its result. Until then, this document and the skill claim nothing
about it.

### 5. Checkpoint recovery (proposed)

A paused or resumed Lead should not ask again for what the user already
settled. The Arc map already records the permission posture and merge
authority. The proposal adds the accepted launch remedy and the date each
preflight check last passed, so that after a resume the Lead reruns the
checks, compares the results, and asks only about a check that now fails.

### 6. Transport (proposed)

Name the SSH sandbox refusal in the preflight (done in the skill), and let
the operator choose a remedy from F9 once. The HTTPS and `GIT_SSH_COMMAND`
options need a measured push from a Worker before the skill recommends
either.

## Maintainer choices

1. Where the operator preflight lives: the launcher (`ned2/env#8`), a
   documented script, or a Dashpot command with an ADR.
2. Whether to qualify the profile-file launch (proposal 3), and whether a
   `default_permissions` profile counts as a supported Lead configuration.
3. Which `worktree_root` this machine uses (F2). That is the operator's
   setting, not a repository change.
4. The default SSH remedy under the sandbox (F9), if any.
5. How a qualification Lead runs pinned experiment runners (F10).

## Follow-ups and incomplete measurements

- Qualify the resume command, or its profile replacement, on the current
  release: the Lead's own shell and a fresh Worker's shell getting the
  injected variables, and its interaction with `default_permissions`.
- Measure environment inheritance at 0.162.x for a fresh Lead, a resumed
  Lead and a fresh Worker, through `ned2/env#8`.
- Measure a Worker's push under each SSH remedy.
- Decide, and if chosen implement, a fixture-parent option for the pinned
  runners, with renewed evidence.
- Measure `gh` under the sandbox grant, which the 0.160.0 experiment could
  not.

These add no prerequisite to the qualification Arc's Issues (#644, #663,
#664, #665, #666, #668, #399), and none of them is complete.
