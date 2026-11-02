// Independently verify a retained Issue #684 trace: a sandboxed Codex
// Worker's `git ls-remote`, first push, lease push and pre-push hook under
// each F9 transport remedy. Checks the Worker's own step reports against the
// remote's records (its receive hook, its HTTPS requests and its SSH
// sessions), the approvals the runner answered, and Codex's own rollouts.
// Imports neither the runner nor its step and hook scripts.
//
//   node verify.mjs <trace.jsonl[.gz]> [codex binary]
// The binary defaults to the retained release the trace names; its bytes
// must match the recorded digest.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

const here = path.dirname(fileURLToPath(import.meta.url));
const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const bytes = readFileSync(tracePath);
const text = bytes[0] === 0x1f && bytes[1] === 0x8b ? gunzipSync(bytes).toString("utf8") : bytes.toString("utf8");
const records = text.trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const sha = (data) => createHash("sha256").update(data).digest("hex");
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

// The run: unbroken, complete, detached, pinned and free of credentials.
records.forEach((record, index) => {
  assert.equal(record.receipt, index + 1, "unbroken receipt order");
  if (index) assert(record.receiptTime >= records[index - 1].receiptTime, "monotonic receipt times");
});
const environment = records[0];
assert.equal(environment.kind, "environment");
check("pinned release", () => {
  assert.equal(environment.version, "codex-cli 0.166.0");
  assert.equal(environment.platform, "linux");
  const binary = process.argv[3] ?? environment.binaryTarget.replace(/^~(?=\/)/, os.homedir());
  assert.equal(sha(readFileSync(binary)), environment.binarySHA256, "the retained release's bytes");
  assert.equal(environment.updater.updater.autoUpdateEnabled, false);
  assert(environment.config.includes("check_for_update_on_startup = false"));
});
check("source identity", () => {
  const scripts = ["ancestry.mjs", "prepush.mjs", "run.mjs", "step.mjs", "verify.mjs"];
  assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), scripts, "every fixture source is named");
  for (const file of scripts) assert.equal(sha(readFileSync(path.join(here, file))), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
  assert.equal(environment.checkout.experimentDirty, false, "the experiment's sources were committed when the run began");
});
check("detached from every harness", () => {
  assert(environment.runnerParent === 1 || environment.ancestry[0]?.pid === environment.runnerParent, "the runner's parent is init or the first recorded ancestor");
  assert(environment.ancestry.every((entry) => entry.harness === false && !/^(codex|claude|opencode)/.test(entry.comm)), "no harness above the runner");
});
check("completed without failure", () => {
  for (const kind of ["failure", "server.error", "scenario.timeout", "cleanup.kill", "model.other"]) assert.equal(of(kind).length, 0, `no ${kind} record`);
  assert.deepEqual(one("completed").scenarios, ["baseline", "https", "ssh-config", "escalated-never", "escalated-approved"]);
  const shared = one("shared-daemon-dir");
  assert.deepEqual([shared.added, shared.removed], [0, 0], "the shared daemon directory was left alone");
});
check("no credential or operator path in the trace", () => {
  const last = records.at(-1);
  assert.equal(last.kind, "artifact");
  assert.equal(last.tokenAbsent, true);
  assert(!/oauth_token|password=|PRIVATE KEY|<fixture-token>/.test(text));
  assert(!text.includes("/home/"), "every home path is rewritten");
});

// The host, outside every sandbox: the fragment is root's, and each
// transport works against the fixture's servers.
check("host: root-owned system configuration and fragment, and every transport works", () => {
  const host = one("host");
  assert.deepEqual([host.systemConfig.uid, host.systemConfig.mode], [0, "644"]);
  assert(host.includes.includes("Include /etc/ssh/ssh_config.d/*.conf"));
  const fragment = host.fragments.find((entry) => entry.name === "20-systemd-ssh-proxy.conf");
  assert.deepEqual([fragment.symlink, fragment.target, fragment.uid, fragment.mode], [true, "/usr/lib/systemd/ssh_config.d/20-systemd-ssh-proxy.conf", 0, "644"]);
  assert.equal(host.sshThroughSystem.status, 0);
  assert.deepEqual(host.controls.map((control) => [control.name, control.status, control.refs]), [["baseline", 0, 2], ["ssh-config", 0, 2], ["https", 0, 2]]);
  assert.equal(host.agentKeys, 1);
});

// Codex's own records: each scenario's lead and its one Worker ran under the
// skill's grants, the Worker spawned by that lead.
const scenarios = ["baseline", "https", "ssh-config", "escalated-never", "escalated-approved"];
const threads = one("rollouts").threads;
const outcome = (name) => one("scenario.outcome", (record) => record.name === name);
const worker = (name) => {
  const found = threads.filter((thread) => thread.source?.subagent?.thread_spawn?.parent_thread_id === outcome(name).lead);
  assert.equal(found.length, 1, `${name}: one Worker of its lead`);
  return found[0];
};
const steps = (name) => of("step").filter((record) => record.scenario === name);
const report = (name, step, index = 0) => {
  const found = steps(name).map((record) => record.report).filter((entry) => entry.step === step);
  assert(found.length > index, `${name}: ${step} report ${index}`);
  return found[index];
};
const plans = {
  baseline: ["probe", "ls-remote", "commit", "push"],
  https: ["probe", "ls-remote", "commit", "push", "amend", "lease", "stale-lease"],
  "ssh-config": ["probe", "ls-remote", "commit", "push", "amend", "lease", "stale-lease", "unknown-host"],
  "escalated-never": ["probe", "ls-remote", "commit", "push"],
  "escalated-approved": ["probe", "ls-remote", "commit", "push", "ls-remote", "push", "amend", "lease", "stale-lease"],
};
check("every lead and Worker ran workspace-write with the skill's roots and the network on", () => {
  for (const name of scenarios) {
    const result = outcome(name);
    assert.equal(result.completed, true, `${name} completed`);
    const policy = name === "escalated-approved" ? "on-request" : "never";
    assert.equal(result.approvalPolicy, policy);
    const launch = one("scenario.launch", (record) => record.name === name);
    assert.deepEqual(launch.overrides.slice(0, 5), ["sandbox_mode", "sandbox_workspace_write.writable_roots", "sandbox_workspace_write.network_access", "approval_policy", "approvals_reviewer"]);
    assert(launch.overrides.slice(5).every((key) => key.startsWith("shell_environment_policy.set.")), `${name}: the remedy reaches the shell through shell_environment_policy.set alone`);
    for (const thread of [threads.find((entry) => entry.id === result.lead), worker(name)]) {
      assert(thread.turns.length > 0, `${name}: turn contexts`);
      for (const turn of thread.turns) {
        assert.equal(turn.sandbox_policy.type, "workspace-write");
        assert.deepEqual(turn.sandbox_policy.writable_roots, ["$ROOT/repository.worktrees", "$ROOT/repository/.git"]);
        assert.equal(turn.sandbox_policy.network_access, true);
        assert.equal(turn.approval_policy, policy);
      }
    }
    assert.deepEqual(steps(name).map((record) => record.report.step), plans[name], `${name}: the Worker ran its plan`);
    assert(steps(name).every((record) => record.thread === worker(name).id && record.report.label === `worker-${name}`), `${name}: every step in the Worker's shell`);
    assert.equal(report(name, "probe").thread, worker(name).id);
  }
});

// Inside the sandbox, F9 reproduces in every scenario: the system files read
// as the overflow uid, and `ssh` through the system configuration refuses the
// included fragment. A control write outside every root is refused.
const refusal = "Bad owner or permissions on /etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf";
check("F9 reproduces inside the sandbox", () => {
  for (const name of scenarios) {
    const probe = report(name, "probe");
    assert.notEqual(probe.uid, 0, `${name}: an ordinary uid`);
    assert.deepEqual([probe.fragment.symlink, probe.fragment.uid, probe.fragment.mode], [true, 65534, "644"], `${name}: fragment as uid 65534`);
    assert.deepEqual([probe.systemConfig.uid, probe.systemConfig.mode], [65534, "644"], `${name}: system configuration as uid 65534`);
    assert.deepEqual([probe.sshThroughSystem.status, probe.sshThroughSystem.lines], [255, [refusal]], `${name}: ssh -G refuses the fragment`);
    assert.deepEqual(probe.outsideWrite, { ok: false, error: "EROFS" }, `${name}: sandboxed`);
    assert(!probe.envNames.some((variable) => /TOKEN/.test(variable)), `${name}: no token variable in the Worker's shell`);
  }
});
check("the remote URL stayed the scp-like SSH URL in every scenario", () => {
  const digest = outcome("baseline").remoteUrlDigest;
  for (const name of scenarios) {
    assert.equal(outcome(name).remoteUrlUnchanged, true);
    assert.equal(outcome(name).remoteUrlDigest, digest);
    assert.deepEqual(report(name, "probe").remoteUrl, { scheme: "ssh", sha256: digest, pushUrls: 0 });
    assert.equal(report(name, "probe").gitConfigKeys.filter(([scope, key]) => scope === "local" && key.startsWith("remote.origin.")).length, 2, `${name}: no push URL or other remote key`);
  }
});

// A transport's full cycle: first push, lease push naming the pushed head, a
// stale lease refused, and the remote's own record of exactly two updates.
const zero = "0".repeat(40);
const cycle = (name, via, sandboxed) => {
  const push = report(name, "push", name === "escalated-approved" ? 1 : 0);
  const lease = report(name, "lease");
  const stale = report(name, "stale-lease");
  assert.equal(push.status, 0, `${name}: first push`);
  assert.equal(lease.status, 0, `${name}: lease push`);
  assert.equal(lease.old, push.local, `${name}: the lease names the pushed head`);
  assert.equal(lease.local, report(name, "amend").after);
  assert.notEqual(stale.status, 0, `${name}: stale lease refused`);
  assert(stale.lines.some((line) => line.endsWith(`HEAD -> ${name} (stale info)`)));
  assert.equal(stale.stale, push.local, `${name}: the stale lease names the replaced head`);
  assert.equal(stale.remoteHolds, lease.local);
  const remote = outcome(name).remote;
  assert.deepEqual(remote.receives.map((entry) => [entry.via, entry.old, entry.new, entry.ref]),
    [[via, zero, push.local, `refs/heads/${name}`], [via, push.local, lease.local, `refs/heads/${name}`]], `${name}: the remote received the push and the lease, nothing else`);
  assert.equal(remote.head, lease.local);
  assert(one("remote.refs").refs.includes(`refs/heads/${name} ${lease.local}`));
  const hooks = [push, lease, stale].map((entry) => { assert.equal(entry.prepush.length, 1, `${name}: one pre-push report per push`); return entry.prepush[0]; });
  assert.deepEqual(hooks.map((hook) => [hook.remote, hook.scheme]), [["origin", via], ["origin", via], ["origin", via]]);
  assert.deepEqual(hooks.map((hook) => hook.refs.map((ref) => [ref.remoteRef, ref.remoteIsNew])),
    [[[`refs/heads/${name}`, true]], [[`refs/heads/${name}`, false]], []], `${name}: Git hands the hook no ref it already refused`);
  for (const hook of hooks) {
    assert.deepEqual(hook.outsideWrite, sandboxed ? { ok: false, error: "EROFS" } : { ok: true }, `${name}: the pre-push hook ran ${sandboxed ? "sandboxed" : "unsandboxed"}`);
  }
  return hooks;
};
const sessionsDuring = (name) => outcome(name).sshd.after.accepted - outcome(name).sshd.before.accepted;

check("baseline: ls-remote and push fail on the fragment before connecting", () => {
  const probe = report("baseline", "probe");
  assert.deepEqual([probe.sshCommand.status, probe.sshCommand.lines], [255, [refusal]]);
  for (const step of ["ls-remote", "push"]) {
    const entry = report("baseline", step);
    assert.deepEqual([entry.status, entry.lines, entry.prepush], [128, [refusal, "fatal: Could not read from remote repository."], []]);
  }
  assert.equal(report("baseline", "commit").status, 0);
  assert.deepEqual([outcome("baseline").remote, outcome("baseline").sshSessions, sessionsDuring("baseline")], [{ head: null, receives: [] }, [], 0]);
  assert.equal(of("remote.request").filter((record) => record.scenario === "baseline").length, 0);
});

check("HTTPS remedy: insteadOf and gh's credential helper carry every operation", () => {
  const probe = report("https", "probe");
  const commandKeys = probe.gitConfigKeys.filter(([scope]) => scope === "command").map(([, key]) => key);
  assert.equal(commandKeys.length, 2);
  const [, base] = /^url\.(https:\/\/127\.0\.0\.1:\d+\/)\.insteadof$/.exec(commandKeys[0]);
  assert.equal(base, `https://127.0.0.1:${environment.ports.https}/`);
  assert.equal(commandKeys[1], `credential.${base.slice(0, -1)}.helper`);
  assert.deepEqual(probe.transport, { fetch: "https", push: "https" });
  assert.equal(probe.sshCommand, null);
  for (const variable of ["GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "GIT_CONFIG_KEY_1", "GIT_CONFIG_VALUE_1", "GIT_SSL_CAINFO", "GH_CONFIG_DIR"]) {
    assert(probe.envNames.includes(variable), `the Worker's shell has ${variable}`);
  }
  assert.deepEqual([report("https", "ls-remote").status, report("https", "ls-remote").refs], [0, ["HEAD", "refs/heads/main"]]);
  for (const hook of cycle("https", "https", true)) assert.deepEqual(hook.env, ["GIT_CONFIG_COUNT", "GIT_SSL_CAINFO", "GH_CONFIG_DIR"]);
  // Each operation is challenged, then authenticated by the helper; the
  // stale lease is refused after the ref advertisement, before any POST.
  const served = of("remote.request").filter((record) => record.scenario === "https");
  const exchange = (service, post = true) => [["GET", service, false, false, 401], ["GET", service, true, true, 200], ...(post ? [["POST", null, true, true, 200]] : [])];
  assert.deepEqual(served.map((record) => [record.method, record.service, record.credentialSent, record.authorized, record.status]),
    [...exchange("git-upload-pack"), ...exchange("git-receive-pack"), ...exchange("git-receive-pack"), ...exchange("git-receive-pack", false)]);
  assert(served.every((record) => record.transport === "https"));
  assert.deepEqual([outcome("https").sshSessions, sessionsDuring("https")], [[], 0], "no SSH session");
});

check("SSH -F remedy: a user-owned configuration, the agent, known hosts and every operation", () => {
  const probe = report("ssh-config", "probe");
  assert.deepEqual(probe.sshCommand, { status: 0, lines: [], hostname127: true, port: environment.ports.ssh, batchMode: true, identitiesOnly: true,
    strictHostKeyChecking: "true", knownHostsSeeded: true }, "strict host key checking against a pre-seeded known-hosts file");
  assert.deepEqual(probe.agent, { status: 0, keys: 1, lines: [], directoryWrite: { ok: false, error: "EROFS" } }, "the agent's socket, outside every writable root, answers");
  assert.deepEqual(probe.transport, { fetch: "ssh", push: "ssh" });
  assert.equal(probe.gitConfigKeys.filter(([scope]) => scope === "command").length, 0);
  assert.equal(report("ssh-config", "ls-remote").status, 0);
  for (const hook of cycle("ssh-config", "ssh", true)) assert.deepEqual(hook.env, ["GIT_SSH_COMMAND", "SSH_AUTH_SOCK", "GH_CONFIG_DIR"]);
  const unknown = report("ssh-config", "unknown-host");
  assert.equal(unknown.status, 0, "accept-new lets the connection through");
  assert.deepEqual(unknown.lines, ["Failed to add the host to the list of known hosts ($ROOT/outside/known_hosts-worker-ssh-config)."]);
  assert.equal(unknown.knownHostsWritten, false, "the sandbox kept the new host key out of a file outside its roots");
  assert.deepEqual(outcome("ssh-config").sshSessions, ["git-upload-pack", "git-receive-pack", "git-receive-pack", "git-receive-pack", "git-upload-pack"]);
  assert.equal(sessionsDuring("ssh-config"), 5);
  assert.equal(of("remote.request").filter((record) => record.scenario === "ssh-config").length, 0, "no HTTPS request");
});

const neverRejection = "approval policy is Never; reject command — you cannot ask for escalated permissions if the approval policy is Never";
check("escalation remedy under never: each escalation is rejected and nothing reaches the remote", () => {
  for (const step of ["ls-remote", "push"]) assert.deepEqual(report("escalated-never", step).lines, [refusal, "fatal: Could not read from remote repository."]);
  const outputs = outcome("escalated-never").workerOutputs;
  assert.deepEqual(outputs.slice(1), [neverRejection, neverRejection], "both escalated calls rejected without running");
  assert.deepEqual(outcome("escalated-never").approvals, []);
  assert.equal(of("approval").filter((record) => record.scenario === "escalated-never").length, 0, "no approval request reached the client");
  assert.deepEqual([outcome("escalated-never").remote, outcome("escalated-never").sshSessions, sessionsDuring("escalated-never")], [{ head: null, receives: [] }, [], 0]);
});

check("escalation remedy under on-request: approved escalations push, and the pre-push hook runs unsandboxed", () => {
  for (const step of ["ls-remote", "push"]) assert.deepEqual(report("escalated-approved", step).lines, [refusal, "fatal: Could not read from remote repository."], "the sandboxed attempt fails first");
  const approvals = of("approval").filter((record) => record.scenario === "escalated-approved");
  assert.deepEqual(approvals.map((record) => [record.method, record.steps, record.decision]), [
    ["item/commandExecution/requestApproval", "ls-remote", "accept"],
    ["item/commandExecution/requestApproval", "push", "accept"],
    ["item/commandExecution/requestApproval", "lease stale-lease", "accept"]]);
  assert(approvals.every((record) => record.thread === worker("escalated-approved").id), "each approval request was the Worker's own");
  assert.equal(report("escalated-approved", "ls-remote", 1).status, 0);
  for (const hook of cycle("escalated-approved", "ssh", false)) assert.deepEqual(hook.env, ["GIT_SSH_COMMAND", "GH_CONFIG_DIR"]);
  assert.deepEqual(outcome("escalated-approved").sshSessions, ["git-upload-pack", "git-receive-pack", "git-receive-pack", "git-receive-pack"]);
  assert.equal(sessionsDuring("escalated-approved"), 4);
});

check("only the unsandboxed pre-push hooks wrote outside the roots", () => {
  const entries = one("outside").entries;
  assert.equal(entries.length, 3);
  assert(entries.every((entry) => /^prepush-\d+$/.test(entry)));
});

console.log(JSON.stringify({ trace: path.basename(tracePath), records: records.length, version: environment.version, binarySHA256: environment.binarySHA256, checks }, null, 2));
