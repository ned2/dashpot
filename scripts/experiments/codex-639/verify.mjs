// Independent verifier for a Codex 639 trace. Checks the recorded checks,
// Worker cycles, Codex's own rollout and log records, and the terminals'
// screens against the claims the spike makes for the pinned release,
// without importing the runner.
//
//   node verify.mjs <trace.jsonl> [expected version]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const [tracePath, expectedVersion = "0.160.0"] = process.argv.slice(2);
assert(tracePath, "Pass the trace.jsonl path");
const raw = readFileSync(tracePath, "utf8");
const records = raw.trim().split("\n").map((line) => JSON.parse(line));
assert(!/dashpot-codex-639-\w{6}/.test(raw), "the fixture root's name is replaced everywhere, a redrawn screen's broken paths included");
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const screen = (label) => one("screen", (record) => record.label === label).tail;

// The trace names the exact sources that produced it, this file included.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "checks.mjs", "cycle.mjs", "run.mjs", "verify.mjs"];
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), scripts);
for (const file of scripts) {
  assert.equal(createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex"), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
}
assert.deepEqual(of("scenario").map((record) => record.name), ["seed", "grant", "adddir", "env", "readonly", "ask"]);
assert.deepEqual(of("server.error"), []);
assert.deepEqual(of("cleanup.kill"), [], "every Codex process the run started had exited before cleanup");
assert.equal(one("shared-daemon-dir").removed, 0, "the run removed nothing from the shared daemon directory");
const { main, worktreeRoot, gitDir } = environment;
const cache = "$HOME/.cache";

// 1. The skill's three checks: refused under Codex's default sandbox, all
// passing under the resume command, and a write outside every named root
// refused either way.
const checks = Object.fromEntries(of("checks").map((record) => [record.report.label, record.report]));
assert.deepEqual(Object.keys(checks).sort(), ["lead-adddir", "lead-env", "lead-grant", "seed"]);
const seed = checks.seed.results;
assert.match(seed.worktreeRoot.error, /\.execute-issues-check': Read-only file system$/);
assert.match(seed.gitDir.error, /\.git\/execute-issues-check': Read-only file system$/);
assert.match(seed.network.error, /failed to open socket: Operation not permitted$/);
assert.equal(checks.seed.networkDisabled, "1");
for (const [label, report] of Object.entries(checks)) {
  assert.equal(report.gitDir, gitDir);
  assert.equal(report.noNewPrivs, "1", `${label} ran under the sandbox`);
  assert.equal(report.seccomp, "2", `${label} ran under a seccomp filter`);
  assert.equal(report.results.outside.ok, false, `${label}'s write outside every root was refused`);
  assert.match(report.results.outside.error, /Read-only file system$/);
  if (label === "seed") continue;
  assert.equal(report.networkDisabled, null, `${label} had network access`);
  for (const [check, result] of Object.entries(report.results)) if (check !== "outside") assert.equal(result.ok, true, `${label}'s ${check}`);
}

// 2. The sandbox Codex recorded for each thread, per turn: the lead's turns
// under each scenario, and every Worker's, which a Worker inherits from
// its lead's session.
const session = one("session").id;
const { threads } = one("rollouts");
const lead = threads.find((thread) => thread.id === session);
const workers = Object.fromEntries(threads.filter((thread) => thread.source?.subagent?.thread_spawn?.parent_thread_id === session)
  .map((thread) => [thread.source.subagent.thread_spawn.agent_path.replace("/root/", ""), thread]));
assert.deepEqual(Object.keys(workers).sort(), ["worker_adddir", "worker_ask", "worker_default", "worker_env", "worker_override", "worker_uv"]);
const policy = (roots, network, approval) => ({ approval_policy: approval, sandbox_policy: roots === null
  ? { type: "workspace-write", network_access: network, exclude_tmpdir_env_var: false, exclude_slash_tmp: false }
  : { type: "workspace-write", writable_roots: roots, network_access: network, exclude_tmpdir_env_var: false, exclude_slash_tmp: false } });
const turnPolicy = (turn) => ({ approval_policy: turn.approval_policy, sandbox_policy: turn.sandbox_policy });
const granted = policy([worktreeRoot, gitDir], true, "never");
const withCache = policy([worktreeRoot, gitDir, cache], true, "never");
const asking = policy([worktreeRoot, gitDir], true, "on-request");
const distinct = (turns) => turns.map(turnPolicy).filter((entry, index, all) => all.findIndex((other) => JSON.stringify(other) === JSON.stringify(entry)) === index);
assert.deepEqual(distinct(lead.turns), [policy(null, false, "never"), granted, withCache, asking],
  "the lead ran Codex's default, then the skill's grant, the grant with the cache, and the grant under on-request; the env scenario's grant matches the first");
for (const [name, expected] of Object.entries({ worker_default: granted, worker_uv: granted, worker_override: granted, worker_env: granted, worker_adddir: withCache, worker_ask: asking })) {
  assert.deepEqual(distinct(workers[name].turns), [expected], `${name}'s sandbox`);
  assert.equal(workers[name].cwd, main, `${name} shares its lead's directory; its commands name their Worktree`);
}
// Naming the main `.git` grants it write access over the read-only
// carve-out a writable root's `.git` otherwise gets.
const entries = lead.turns.find((turn) => JSON.stringify(turnPolicy(turn)) === JSON.stringify(granted)).permissions.entries;
assert.deepEqual(entries.slice(0, 6), [["root", "read"], [main, "write"], [worktreeRoot, "write"], [gitDir, "write"], ["slash_tmp", "write"], ["tmpdir", "write"]]);
for (const carved of [".git", ".agents", ".codex"]) assert(entries.some(([where, access]) => where === `${worktreeRoot}/${carved}` && access === "read"), `${carved} under the Worktree Root stays read-only`);

// 3. Each Worker cycle's steps. Without a cache override a Worker's uv and
// pre-commit write under $HOME/.cache, outside every root, and fail;
// moving both caches into the Worktree Root, or adding $HOME/.cache as a
// writable root, completes the cycle.
const cycles = Object.fromEntries(of("cycle").map((record) => [record.report.label, record.report]));
assert.deepEqual(Object.keys(cycles).sort(), ["worker-adddir", "worker-default", "worker-env", "worker-override", "worker-uv"]);
const outcome = (report) => Object.fromEntries(Object.entries(report.steps).map(([step, result]) => [step, result.ok]));
const refused = (report) => Object.fromEntries(Object.entries(report.steps).filter(([, result]) => result.refused?.length).map(([step, result]) => [step, result.refused]));
const complete = { prepare: true, edit: true, gate: true, commit: true, push: true, report: true };
assert.deepEqual(outcome(cycles["worker-default"]), { ...complete, prepare: false, gate: false, commit: false });
assert.deepEqual(refused(cycles["worker-default"]), { prepare: [`${cache}/uv`], gate: [`${cache}/uv`], commit: [`${cache}/uv`] });
assert.deepEqual(outcome(cycles["worker-uv"]), { ...complete, gate: false, commit: false });
assert.deepEqual(refused(cycles["worker-uv"]), { gate: [`${cache}/pre-commit`], commit: [`${cache}/pre-commit`] });
for (const label of ["worker-override", "worker-adddir", "worker-env"]) {
  assert.deepEqual(outcome(cycles[label]), complete, `${label} completed its cycle`);
  assert.deepEqual(refused(cycles[label]), {});
}
for (const [label, report] of Object.entries(cycles)) {
  assert.equal(report.cwd, `${worktreeRoot}/${label}`);
  assert.equal(report.networkDisabled, null);
  assert.match(report.steps.commit.tail ?? "", label === "worker-default" || label === "worker-uv" ? /./ : new RegExp(`^\\[${label} [0-9a-f]+\\] Cycle ${label}`), `${label}'s commit ran its hook`);
}
assert.deepEqual(cycles["worker-uv"].overrides, ["UV_CACHE_DIR"]);
assert.deepEqual(cycles["worker-override"].overrides, ["UV_CACHE_DIR", "PRE_COMMIT_HOME"]);
// The env scenario sets the caches through Codex's shell environment
// policy alone, so the Worker's shell arrives with them.
assert.deepEqual(cycles["worker-env"].overrides, []);
assert.deepEqual(cycles["worker-env"].inherited, Object.fromEntries(environment.cacheOverrides.map((pair) => pair.split(/=(.*)/s).slice(0, 2))));
assert.deepEqual(cycles["worker-default"].inherited, { UV_CACHE_DIR: null, PRE_COMMIT_HOME: null });
const refs = one("remote.refs").refs;
for (const label of Object.keys(cycles)) assert(refs.includes(`refs/heads/${label}`), `${label} pushed to the loopback remote`);
assert.equal(of("remote.request").filter((record) => record.method === "POST" && record.path === "/remote.git/git-receive-pack" && record.status === 200).length, 5,
  "each push was an HTTP connection to the loopback remote");
assert.deepEqual(one("ledger").files, ["worker-default", "worker-uv", "worker-override", "worker-adddir", "worker-env"]);

// 4. The resume: in-process rather than in the daemon, refused while the
// daemon still holds the seed's thread, and resumed after a retry once the
// daemon unloads it.
const { entries: log } = one("codex.log");
const grantStart = one("lead.started", (record) => record.name === "grant");
assert(grantStart.conflicts >= 1 && grantStart.retries >= 1, "the grant's resume waited on the daemon");
assert.match(screen("conflict"), /This conversation is open in another app/);
assert.match(screen("conflict"), /r retry/);
// The retry that resumed sent no model request within 5 s, so the runner
// typed the prompt the command line had carried.
assert.equal(grantStart.typed, true);
assert(log.some((entry) => entry.method === "thread/start" && entry.transport === "unix_socket" && entry.pid === one("lead.started", (record) => record.name === "seed").daemonPid));
assert(log.some((entry) => entry.pid === grantStart.hostPid && entry.method === "thread/resume" && entry.transport === "in-process" && /already has an active writer/.test(entry.message)));
const unloaded = log.find((entry) => entry.pid === grantStart.daemonPid && entry.message === `thread ${session} has no subscribers and is idle; shutting down`);
const seedExit = one("terminal.exit", (record) => record.name === "seed").receiptTime / 1000;
assert(unloaded.ts - seedExit >= 50 && unloaded.ts - seedExit <= 70, "the background server unloaded the seed's thread about 60 s after its client exited");
assert.equal(grantStart.hostPid !== grantStart.daemonPid, true);
// A resume after an in-process client waits for nothing.
for (const name of ["adddir", "env", "ask"]) assert.equal(one("lead.started", (record) => record.name === name).conflicts, 0, `${name} resumed at once`);

// 5. `--add-dir` under `read-only`: an error, and the client exits.
assert.deepEqual(one("terminal.exit", (record) => record.name === "readonly").status, 1);
assert.match(screen("readonly-done"), /Error adding directories: Ignoring --add-dir \(\$ROOT\/repository\.worktrees, \$ROOT\/repository\/\.git\) because the effective permissions do not allow additional writable roots\. Switch to workspace-write or danger-full-access to allow them\./);
assert.equal(of("model.request").some((record) => record.label === "lead-readonly"), false);

// 6. `on-request`: a plain refused write fails without an ask; an escalated
// one asks in the lead's terminal, the Worker's labelled with its thread.
const requests = (label) => of("model.request").filter((record) => record.label === label && !record.sideThread);
for (const who of ["lead", "worker"]) {
  const [, afterPlain] = requests(`${who}-ask`);
  assert.match(afterPlain.lastOutput, new RegExp(`exited with code 1 .*touch: cannot touch '\\$ROOT/outside/plain-${who}-ask': Read-only file system`));
  assert.equal(afterPlain.action, "exec_command:escalated");
}
assert.deepEqual(one("asks").answered, ["lead", "worker"]);
// A screen's text loses spaces the terminal drew by moving the cursor.
assert.match(screen("ask-lead"), /Would you like to run the following command\?\s*Environment:\s*local\s*Reason:\s*Fixture: write outside every writable root\s*\$\s*touch \$ROOT\/outside\/escalated-lead-ask/);
assert.match(screen("ask-worker"), /Would you like to run the following command\?\s*Thread:\s*Agent \([0-9a-f]{8}\)/);
assert.match(screen("ask-worker"), /o to open thread/);
assert.match(screen("ask-worker"), /3\.\s*No,\s*and\s*tell\s*Codex\s*what\s*to\s*do\s*differently\s*\(esc\)/);
const leadEnded = requests("lead-ask").find((record) => record.action === null);
assert(leadEnded.receipt < one("screen", (record) => record.label === "ask-worker").receipt, "the lead's turn had ended before the worker's ask");
// The person approved the lead's ask, and the command ran. Escape on the
// Worker's ask cut its command short and aborted its turn; the Worker made
// no further request, and the lead's own record shows nothing of it.
assert.match(requests("lead-ask")[2].lastOutput, /exited with code 0/);
assert.deepEqual(one("outside").entries, ["escalated-lead-ask"]);
assert.equal(requests("worker-ask").length, 2);
assert.deepEqual([workers.worker_ask.aborted, workers.worker_ask.abortedCalls], [["interrupted"], 1]);
assert.deepEqual([lead.aborted, lead.abortedCalls], [[], 0]);
assert.match(screen("answered-worker"), /Ask Codex to do anything/);

console.log(JSON.stringify({ verified: tracePath, version: environment.version, threads: threads.length, cycles: Object.keys(cycles).length }));
