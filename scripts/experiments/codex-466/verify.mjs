// Independent verifier for the Issue #466 Codex trace: checks each finding
// about a command `exec_command` leaves running as a background terminal
// (whether it outlives the turn, `/cd`, `/clear`, `/exit`, a daemon client's
// exit and the daemon's unload, and a headless `codex exec`; where it works;
// whether its end starts a turn; and what Dashpot's `process` Cleanup blocker
// of ADR 0104 names after each) against the recorded hook, command, process
// and `dashpot worktree check --json` evidence, and that the trace came from
// the runner retained beside this file.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
//
// The Dashpot sources the trace hashes may change after the run, so a
// difference from this checkout is reported, and fails only under --strict.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const flags = new Set(process.argv.slice(2).filter((argument) => argument.startsWith("--")));
const [file] = process.argv.slice(2).filter((argument) => !argument.startsWith("--"));
assert(file, "Pass the trace to verify");
const records = readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => {
  try { test(); } catch (error) { console.error(`not ok - ${claim}`); throw error; }
  checks.push(claim);
};
const pinned = "0.160.0";
const treeA = "$ROOT/repository.worktrees/a";
const treeB = "$ROOT/repository.worktrees/b";
const sha = (target) => createHash("sha256").update(readFileSync(target)).digest("hex");
const span = (name) => {
  const start = records.findIndex((record) => record.kind === "scenario" && record.name === name);
  assert(start >= 0, `scenario ${name}`);
  const end = records.findIndex((record, index) => index > start && record.kind === "scenario.end" && record.name === name);
  assert(end > start, `scenario ${name} ended`);
  assert.equal(records[end].ok, true, `scenario ${name}: ${records[end].error}`);
  return records.slice(start, end + 1);
};
const one = (scope, predicate, what) => {
  const found = scope.filter(predicate);
  assert.equal(found.length, 1, `exactly one ${what}`);
  return found[0];
};
const hooksOf = (scope) => scope.filter((record) => record.kind === "hook");
const commandOf = (scope, p, phase) => scope.find((record) => record.kind === "command" && record.label === `${p}-bg` && record.phase === phase);
const probeOf = (scope, label) => one(scope, (record) => record.kind === "probe" && record.label === label, `probe ${label}`);
const blocker = (probe, tree, kind) => probe.checks[tree].blockers.filter((entry) => entry.kind === kind);
const namesPid = (probe, tree, pid) => blocker(probe, tree, "process").some((entry) => entry.processes.some((named) => named.pid === pid));
const sessionBlockers = (probe, tree) => blocker(probe, tree, "agent-session").map((entry) => entry.session);
const runningInA = (probe, command) => {
  assert.equal(probe.command.pid, command.pid);
  assert.equal(probe.command.alive, true, "the command runs");
  assert.equal(probe.command.cwd, treeA);
};
const sessionOf = (scope) => one(hooksOf(scope), (hook) => hook.event === "SessionStart" && hook.payload.source === "startup", "startup SessionStart").payload.session_id;
// The command a session's first turn started: a direct child of the Codex
// process hosting the thread, leading a session and process group of its
// own, working in `a`, whose environment names the thread.
const started = (scope, p, session) => {
  const command = commandOf(scope, p, "start");
  assert(command, `${p} command started`);
  assert.equal(command.cwd, treeA);
  assert.equal(command.env.CODEX_THREAD_ID, session);
  assert.equal(command.ancestry[0].pid, command.ppid);
  assert.match(command.ancestry[0].comm, /^codex/);
  assert.equal(command.pgid, command.pid);
  assert.equal(command.sid, command.pid);
  return command;
};
// The starting turn ended while the command ran.
const turnEnded = (scope, command, session) => {
  const stop = hooksOf(scope).find((hook) => hook.receipt > command.receipt && hook.event === "Stop" && hook.payload.session_id === session);
  assert(stop, "the starting turn's Stop");
  const ended = commandOf(scope, command.label.replace(/-bg$/, ""), "end");
  if (ended) assert(stop.receipt < ended.receipt, "the Stop came before the command's end");
  return stop;
};
// Nothing starts a turn once the gate opens: the command's end is silent.
const silentEnd = (scope, p) => {
  const gate = one(scope, (record) => record.kind === "gate" && record.gate === `${p}-go`, "gate");
  const next = scope.find((record) => record.receipt > gate.receipt && (record.kind === "terminal.type" || record.kind === "probe"));
  const between = hooksOf(scope).filter((hook) => hook.receipt > gate.receipt && (!next || hook.receipt < next.receipt));
  assert.deepEqual(between.map((hook) => hook.event), [], "no hook between the command's end and the next action");
};

// Scenario prefixes in labels: te turn-end, cd cd, cl clear, ex exit,
// dm daemon, hx exec.
const environment = records[0];
check("the trace is of the pinned Codex release, from the runner retained beside this verifier, with every publish succeeding", () => {
  assert.equal(environment.kind, "environment");
  assert.equal(environment.version, `codex-cli ${pinned}`);
  assert.match(environment.binaryTarget, new RegExp(`/releases/${pinned.replaceAll(".", "\\.")}-[^/]+/bin/codex$`));
  for (const name of ["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"]) assert.equal(sha(path.join(here, name)), environment.sourceSHA256[name], `${name} changed since the run`);
  assert.deepEqual(records.find((record) => record.kind === "sources.after").sourceSHA256, environment.sourceSHA256, "no source changed during the run");
  assert.deepEqual(environment.dashpot.dirtySource, [], "the run's Dashpot source was committed");
  for (const record of hooksOf(records)) assert.equal(record.publisher?.status, 0, `publisher failed at #${record.receipt}`);
  assert.deepEqual(environment.scenarios, ["turn-end", "cd", "clear", "exit", "daemon", "exec"]);
});
const checkoutRoot = path.resolve(here, "..", "..", "..");
const drift = Object.entries(environment.sourceSHA256).filter(([name]) => name.startsWith("src/")).filter(([name, hash]) => {
  try { return sha(path.join(checkoutRoot, name)) !== hash; } catch { return true; }
}).map(([name]) => name);
if (drift.length) {
  console.log(`note - working-tree sources changed since the run: ${drift.join(", ")}`);
  assert(!flags.has("--strict"), "sources changed under --strict");
}

check("turn-end: the background terminal outlives its turn in Worktree `a`, the session reads waiting, and the `process` blocker names it", () => {
  const scope = span("turn-end");
  const session = sessionOf(scope);
  const command = started(scope, "te", session);
  turnEnded(scope, command, session);
  const probe = probeOf(scope, "after-turn");
  runningInA(probe, command);
  assert.deepEqual(probe.stored[session].map((entry) => [entry.store, entry.state]), [["a", "waiting"]]);
  assert.equal(probe.checks.a.removable, false);
  assert(namesPid(probe, "a", command.pid));
  assert.deepEqual(sessionBlockers(probe, "a"), [session]);
});
check("no hook Dashpot subscribes to carries a field about a background terminal", () => {
  const events = new Set(hooksOf(records).map((hook) => hook.event));
  assert.deepEqual([...events].sort(), ["SessionEnd", "SessionStart", "Stop", "UserPromptSubmit"]);
  for (const hook of hooksOf(records)) assert(!hook.payloadKeys.some((key) => /background|terminal|task|shell|process/i.test(key)), `#${hook.receipt} ${hook.payloadKeys}`);
});
check("turn-end: the command's end starts no turn, and the blocker no longer names it", () => {
  const scope = span("turn-end");
  assert(commandOf(scope, "te", "end")?.opened);
  silentEnd(scope, "te");
  const probe = probeOf(scope, "after-release");
  assert.equal(probe.command.alive, false);
  assert(!namesPid(probe, "a", probe.command.pid));
});
check("cd: `/cd` to `b` while the command runs leaves the session in `a`; once it has ended, `/cd` forks the thread into a new session in `b`", () => {
  const scope = span("cd");
  const session = sessionOf(scope);
  const command = started(scope, "cd", session);
  const during = one(scope, (record) => record.kind === "prompt.turn" && record.label === "cd-after-cd", "turn after /cd");
  assert.equal(during.session, session);
  assert.equal(during.cwd, treeA);
  const probe = probeOf(scope, "after-cd");
  runningInA(probe, command);
  assert(namesPid(probe, "a", command.pid));
  assert.equal(probe.checks.b.removable, true);
  const fork = one(hooksOf(scope), (hook) => hook.event === "SessionStart" && hook.payload.source === "fork", "SessionStart(fork)");
  assert(fork.receipt > commandOf(scope, "cd", "end").receipt, "the fork followed the command's end");
  assert.equal(fork.payload.cwd, treeB);
  assert.notEqual(fork.payload.session_id, session);
  const after = one(scope, (record) => record.kind === "prompt.turn" && record.label === "cd-after-release-cd", "turn after the second /cd");
  assert.equal(after.session, fork.payload.session_id);
  assert.equal(after.cwd, treeB);
});
check("clear: `/clear` starts a new session beside the first, which stays live, while the command runs on naming the first", () => {
  const scope = span("clear");
  const session = sessionOf(scope);
  const command = started(scope, "cl", session);
  const next = one(hooksOf(scope), (hook) => hook.event === "SessionStart" && hook.payload.source === "clear", "SessionStart(clear)");
  assert.notEqual(next.payload.session_id, session);
  const probe = probeOf(scope, "after-clear");
  runningInA(probe, command);
  assert.equal(commandOf(scope, "cl", "end").env.CODEX_THREAD_ID, session);
  assert.deepEqual(sessionBlockers(probe, "a").sort(), [session, next.payload.session_id].sort());
  assert(namesPid(probe, "a", command.pid));
  for (const id of [session, next.payload.session_id]) assert.deepEqual(probe.stored[id].map((entry) => [entry.store, entry.state]), [["a", "waiting"]]);
  const ends = hooksOf(scope).filter((hook) => hook.event === "SessionEnd");
  assert.deepEqual(ends.map((hook) => hook.payload.session_id).sort(), [session, next.payload.session_id].sort(), "one SessionEnd per session");
  const exited = one(scope, (record) => record.kind === "terminal.exit", "terminal exit");
  assert(ends.every((hook) => hook.receipt > probeOf(scope, "after-release").receipt && hook.receipt < exited.receipt), "both sessions end only at exit");
  silentEnd(scope, "cl");
});
check("exit: `/exit` ends the command with the terminal, leaving `a` removable", () => {
  const scope = span("exit");
  const session = sessionOf(scope);
  started(scope, "ex", session);
  const ended = one(hooksOf(scope), (hook) => hook.event === "SessionEnd", "SessionEnd");
  assert.equal(ended.payload.session_id, session);
  assert.equal(ended.payload.reason, "other");
  const probe = probeOf(scope, "after-exit");
  assert.equal(probe.command.alive, false);
  assert.equal(probe.checks.a.removable, true);
  assert(!commandOf(scope, "ex", "end"), "the command never reached its gate");
});
check("daemon: a command the managed daemon runs outlives the terminal's exit, named alone by the `process` blocker, until the daemon unloads the thread and ends it", () => {
  const scope = span("daemon");
  const session = sessionOf(scope);
  const daemon = one(scope, (record) => record.kind === "daemon.ready", "daemon").pid;
  const command = started(scope, "dm", session);
  assert.equal(command.ppid, daemon, "the daemon runs the command");
  const exited = probeOf(scope, "after-client-exit");
  runningInA(exited, command);
  assert.deepEqual(sessionBlockers(exited, "a"), [session]);
  assert.deepEqual(blocker(exited, "a", "process").flatMap((entry) => entry.processes.map((named) => named.pid)), [command.pid]);
  const unloaded = one(hooksOf(scope), (hook) => hook.event === "SessionEnd", "unload SessionEnd");
  assert.equal(unloaded.payload.session_id, session);
  assert.equal(unloaded.payload.reason, "other");
  const left = one(scope, (record) => record.kind === "terminal.exit", "terminal exit");
  const unloadSeconds = (unloaded.receiptTime - left.receiptTime) / 1000;
  assert(unloadSeconds > 50 && unloadSeconds < 90, `the unload came about a minute after the terminal left (${unloadSeconds} s)`);
  const after = probeOf(scope, "after-unload");
  assert(after.receipt > unloaded.receipt);
  assert.equal(after.command.alive, false);
  assert.equal(after.checks.a.removable, true);
  assert(!commandOf(scope, "dm", "end"), "the command never reached its gate");
});
check("exec: a headless `codex exec` exits while its command runs, and the command ends with it", () => {
  const scope = span("exec");
  const session = sessionOf(scope);
  const command = started(scope, "hx", session);
  const exit = one(scope, (record) => record.kind === "client.exit", "exit");
  const gate = one(scope, (record) => record.kind === "gate", "gate");
  assert(exit.receipt < gate.receipt, "the client exited before the gate opened");
  const probe = probeOf(scope, "after-turn");
  assert.equal(probe.command.alive, false);
  assert.equal(probe.checks.a.removable, true);
  assert(!commandOf(scope, "hx", "end"));
  assert.equal(command.cwd, treeA);
});
check("the run left no fixture process and removed nothing from the shared daemon directory", () => {
  assert.deepEqual(records.find((record) => record.kind === "cleanup.remaining").pids, []);
  assert.equal(records.find((record) => record.kind === "shared-daemon-dir").removed, 0);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} checks passed`);
