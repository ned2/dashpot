---
status: research
date: 2026-10-13
---

# Codex Worker approvals, turn grants and Guardian stops

[Issue #665](https://github.com/ned2/dashpot/issues/665) extends the
[0.160.0 sandboxed Worker cycle](codex-sandboxed-worker-cycle-spike.md)
with a separate runner on **codex-cli 0.162.0**, Linux x86_64. The root and
its V2 Sub-agent are a Lead and Worker in shape only: a scripted loopback
provider selects every call, including three harmless fixture denials.
No real model, credentials, forge, dangerous action or execute-issues Arc
runs. The fixture does not authorize adopting automatic review for an Arc.

## Measured outcomes

Every result in this table is checked by the independent verifier against
actual model requests, tool outputs, publisher hooks and Dashpot observations.

| Case | Result |
| --- | --- |
| A Worker asks while its parent remains in `wait_agent` | The ask appears in the parent's TUI, headed `Thread: Agent`, with `o to open thread`. The parent makes no model request between entering its wait and the answer. It receives no model-visible approval prompt. |
| Approve the Worker | The write outside its original roots succeeds, the Worker completes and hands back its answer, and the wait returns before its 30-second timeout. `SubagentStop` runs. |
| Decline the Worker with Escape | The command never runs. The Worker is interrupted, sends no hand-back, and emits no `SubagentStop`. The parent remains in its wait until the 30-second timeout; `list_agents` then reports the child interrupted. |
| Escalation with a denied read and network restriction | The approved write broadens access while reading the disposable denied file still returns `EACCES`, and a connection to a live loopback listener still returns `EPERM`. The probe has `NoNewPrivs=1` and `Seccomp=2`. A plain command fails its outside write with `EROFS` without asking. |
| A command allow rule | A matching `allow` rule for an ordinary `touch` does not make its outside target writable. The command fails with `Read-only file system` and creates no file. |
| Full-access launch across a local TUI reconnect | With `-a never --sandbox danger-full-access`, after transport loss and a recovered server reply of `on-request` / `readOnly`, the preserved draft's `turn/start` still sends `never` and `dangerFullAccess`. This is a client/protocol measurement; its fixture server executes no commands. |
| Workspace-write launch across that reconnect control | With `-a never --sandbox workspace-write`, `never` survives, but the recovered `turn/start` sends neither `sandboxPolicy` nor `permissions`. This control does **not** establish preservation of the workspace-write sandbox. |
| A background code-mode cell crosses turns | Its originating turn's grant A remains usable after a distinct next turn completes the grant B request. The old cell cannot write B, and the next turn cannot write A: both borrowing attempts return `EROFS`. Both grants are explicitly `turn` scoped. |
| Three Guardian denials, strict circuit break | The child remains interrupted. The parent receives `Agent interrupted by Guardian` and the instruction to tell the user and obtain explicit confirmation before resuming the child or retrying its blocked work. The notification wakes `wait_agent`. |
| Three Guardian denials, default circuit break | The child remains interrupted, but sends no parent notification. The parent's 10-second wait times out. |
| Ordinary `interrupt_agent` under the strict setting | A running child's previous status is `running`, then `list_agents` reports `interrupted`. It sends no parent notification and the 10-second wait times out. |
| Hooks, Worker activity and Cleanup | Strict Guardian, default Guardian, ordinary interruption and decline all retain the native child in `liveSubagents`, without `SubagentStop` during their observation windows. While the parent remains attached, a real Worker Assignment still shows the Worker `running`, and Cleanup of another, idle Worktree reports that child as a `sub-agent` blocker. Approval clears the child's listing, running attribution and blocker. After the standalone parent exits and its Host Process is known gone, the blocker disappears even though its ended hook record retains the stale child listing. |

The parent's own Worktree is also blocked by its live Agent Session and Agent
Run while attached. The separate idle Worktree makes the Sub-agent blocker
observable independently of those direct occupancy reasons. An ordinary
interruption can additionally leave a live shell process while the parent
remains attached; Cleanup observes that process separately.

The strict notification is progress reporting, not a hook repair. A Lead must
report its guidance and wait for the person's explicit confirmation before
retrying blocked work. The fixture stops at the observation and never retries
its Guardian-stopped children.

## Reproduce and verify

The runner needs the checkout's locked development environment, Node 24,
Git, `script` from util-linux, and the retained Linux 0.162.0 binary. It uses
the checkout's real Dashpot publisher and hashes every Python source in its
package before and after the run. The publisher and fixture sources must stay
fixed while it runs. No dependency installation happens inside the fixture.

Run detached so no harness process becomes an ancestor of its sessions:

```bash
setsid -f sh -c 'node scripts/experiments/codex-639/permissions-run.mjs ~/.codex/packages/standalone/releases/0.162.0-x86_64-unknown-linux-musl/bin/codex > /tmp/dashpot-665.log 2>&1'
node scripts/experiments/codex-639/permissions-verify.mjs /tmp/dashpot-codex-665-SUFFIX/trace.jsonl
```

The runner prints its disposable fixture directory and trace path. Its normal
run takes roughly two minutes. `SPIKE_SCENARIOS` can select development cases,
but the independent verifier requires the full seven-case run. Each poll,
RPC, terminal exit and permission probe is bounded. Its final cleanup stops
only processes belonging to its isolated `CODEX_HOME`; it leaves the shared
Codex daemon directory untouched. The retained release is read-only and is
invoked through a fixture-local `PATH` symlink. A retained fixture is left for
inspection, not reused as a task Worktree.

The fixture lives on `/tmp`. Its **named managed permission profile** grants
root reads, writes only to the two explicitly named active checkout paths,
and denies one exact file. It grants neither `slash_tmp` nor `tmpdir` writes;
Codex's recorded turn contexts verify that exclusion. Thus an outside path
on `/tmp` remains protected. This differs from #639's implicit workspace-write
profile, which grants temporary-directory writes and required `/var/tmp`.
Both update checks and the isolated daemon updater are disabled.

- [Runner](../../scripts/experiments/codex-639/permissions-run.mjs) and
  [probe](../../scripts/experiments/codex-639/permissions-probe.mjs) execute the
  disposable real-server cases.
- [Hook wrapper](../../scripts/experiments/codex-639/permissions-hook.mjs)
  invokes Dashpot's real publisher and records its status and identity fields.
  Only these vetted fixture hooks bypass Codex's hook-trust prompt.
- [Reconnect fixture](../../scripts/experiments/codex-639/permissions-reconnect.mjs)
  drives the real local TUI against a deliberately changing protocol server,
  following the pinned upstream [reconnect integration test](https://github.com/openai/codex/blob/rust-v0.162.0/codex-rs/tui/tests/suite/reconnect.rs).
  It strips the TUI's disposable MCP bearer token from retained RPC parameters.
- [Verifier](../../scripts/experiments/codex-639/permissions-verify.mjs) imports
  no runner code. It checks raw observations, distinct turn IDs and grant scopes,
  hooks independently of mail, source digests and the retained binary's bytes.
  Its optional third argument names another copy of that same binary.
- [Retained trace](measurements/issue-665-codex-trace.jsonl.gz) contains only fixture
  evidence, with paths replaced by `$ROOT`, `$HOME`, `$CHECKOUT` and `~`.
  Gzip retains the full metadata stream without exceeding the new-file size gate.
  The stream has 313 records, uncompressed SHA-256
  `f1f88eb07ef767e13456721c079fafc68f8f3779915023136a91067762e7af31`.
  Verifier mutation tests check that missing guidance, fabricated hook outcomes,
  borrowed grants and stale source identity cannot pass as evidence.

## Evidence boundaries

The reconnect server is scripted; it establishes what the real local client
sends, not permission enforcement by a real daemon after reconnect. Full-access
restoration is measured; workspace-write restoration is **not qualified** by
this control. A stock daemon reconnect, named constrained profiles, reviewer-only
overrides, permission-picker changes, new sessions and actual transport failure
of a production server remain unmeasured. The workspace result is retained as
an observed omission rather than interpreted as a successful sandbox grant.

The grant test covers grants made before a background cell starts and isolation
across subsequent turns. A background cell making a new permission request
after a later turn begins, session-scoped grants, strict stdin review, remote
exec-server compatibility, glob-based denied reads, Windows, macOS and real
network-proxy rules remain unmeasured. The network probe measures a kernel
restriction, not a policy document's declared value alone.

Guardian uses the pinned [fixture decision shape](https://github.com/openai/codex/blob/rust-v0.162.0/codex-rs/core/tests/suite/guardian_subagent_notification_tests.rs)
and a scripted deny response. It tests circuit-break behavior and notification
delivery, not classifier judgment or a real model's response to its guidance.
Only actual hooks during the recorded windows establish hook presence or absence.
No parent notification is substituted for `SubagentStop`.

The ordinary-interruption control is owned and regenerated here. No #399 trace
is inherited; a future consumer must independently verify this trace's pinned
release, features, permissions, hosting mode, target and observation setup.
Broader interruption qualification remains with
[#399](https://github.com/ned2/dashpot/issues/399), and hook repair with
[#394](https://github.com/ned2/dashpot/issues/394).
