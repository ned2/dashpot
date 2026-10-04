// Independent verifier for the Issue #466 Claude Code trace: checks each
// finding about a `run_in_background` Bash command (whether it outlives the
// turn, a move with `EnterWorktree`, `/clear`, `/exit` with either answer to
// its dialog, and a headless `claude -p`; where it works; which session its
// end wakes; and what Dashpot's `process` Cleanup blocker of ADR 0104 names
// after each) against the recorded hook, command, process and
// `dashpot worktree check --json` evidence, and that the trace came from the
// runner retained beside this file.
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
const pinned = "2.1.289";
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
// The `process` blocker of a Worktree names this pid.
const namesPid = (probe, tree, pid) => blocker(probe, tree, "process").some((entry) => entry.processes.some((named) => named.pid === pid));
// The command, as a process, alive and working in Worktree `a`.
const runningInA = (probe, started) => {
  assert.equal(probe.command.pid, started.pid);
  assert.equal(probe.command.alive, true, "the command runs");
  assert.equal(probe.command.cwd, treeA);
};
const sessionBlockers = (probe, tree) => blocker(probe, tree, "agent-session").map((entry) => entry.session);
// The command a session started: a child of the shell Claude Code spawned
// for it, in a session and process group of its own, working in `a`, whose
// environment names the session and its Host Process.
const started = (scope, p, session, host) => {
  const command = commandOf(scope, p, "start");
  assert(command, `${p} command started`);
  assert.equal(command.cwd, treeA);
  assert.equal(command.env.CLAUDE_CODE_SESSION_ID, session);
  assert.equal(Number(command.env.CLAUDE_PID), host);
  assert.equal(command.ancestry[0].comm, "bash");
  assert.equal(command.ancestry[0].ppid, host, "the shell is the Host Process's child");
  assert.equal(command.pgid, command.ppid, "the shell leads the command's process group");
  assert.equal(command.sid, command.ppid, "and its session");
  return command;
};
// The Stop that ended the starting turn reports the shell as running.
const reportsRunning = (stop) => {
  assert(stop, "the Stop");
  assert.equal(stop.backgroundTasks.length, 1);
  assert.equal(stop.backgroundTasks[0].type, "shell");
  assert.equal(stop.backgroundTasks[0].status, "running");
};
const client = (scope) => one(scope, (record) => record.kind === "client.ready", "ready client");
const firstStopAfter = (scope, record, session) => hooksOf(scope).find((hook) => hook.receipt > record.receipt && hook.event === "Stop" && hook.payload.session_id === session && !hook.payload.agent_id);
const notification = (scope, after) => hooksOf(scope).find((hook) => hook.receipt > after.receipt && hook.event === "UserPromptSubmit" && hook.prompt?.taskNotification);

// The run itself.
// Scenario prefixes in labels: te turn-end, mv move, cl clear, es exit-stop,
// eb exit-background, hl headless.
const environment = records[0];
check("the trace is of the pinned Claude Code release, with the updater off and an isolated configuration", () => {
  assert.equal(environment.kind, "environment");
  assert.equal(environment.version, `${pinned} (Claude Code)`);
  assert.match(environment.binary, new RegExp(`/claude/versions/${pinned.replaceAll(".", "\\.")}$`));
  assert.equal(environment.flags.DISABLE_AUTOUPDATER, "1");
  assert.equal(environment.flags.CLAUDE_CONFIG_DIR, "$ROOT/home/.claude");
});
check("the trace came from the runner retained beside this verifier", () => {
  assert.deepEqual(Object.keys(environment.experimentSHA256).sort(), ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs"]);
  for (const [name, hash] of Object.entries(environment.experimentSHA256)) assert.equal(sha(path.join(here, name)), hash, `${name} changed since the run`);
});
check("the hooks were subscribed as `dashpot integrate claude-code` subscribes them, every publish succeeded, and every scenario ran", () => {
  assert.deepEqual(environment.subscriptions.events, ["SessionStart", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "SessionEnd"]);
  for (const record of hooksOf(records)) assert.equal(record.publisher?.status, 0, `publisher failed at #${record.receipt}`);
  assert.deepEqual(environment.worktreeDirty, [], "the run's Dashpot source was committed");
  assert.deepEqual(environment.scenarios, ["turn-end", "move", "clear", "exit-stop", "exit-background", "headless"]);
});
const checkoutRoot = path.resolve(here, "..", "..", "..");
const drift = Object.entries(environment.worktreeSourceSHA256).filter(([name, hash]) => {
  try { return sha(path.join(checkoutRoot, name)) !== hash; } catch { return true; }
}).map(([name]) => name);
if (drift.length) {
  console.log(`note - working-tree sources changed since the run: ${drift.join(", ")}`);
  assert(!flags.has("--strict"), "sources changed under --strict");
}

check("turn-end: the command outlives its turn in Worktree `a`, the stop reports it running, the session reads waiting, and the `process` blocker names it", () => {
  const scope = span("turn-end");
  const { session, host } = client(scope);
  const command = started(scope, "te", session, host);
  reportsRunning(firstStopAfter(scope, command, session));
  const probe = probeOf(scope, "after-turn");
  runningInA(probe, command);
  assert.equal(probe.shell.ppid, host);
  assert.deepEqual(probe.stored[session].map((entry) => [entry.store, entry.state]), [["a", "waiting"]]);
  assert.equal(probe.checks.a.removable, false);
  assert(namesPid(probe, "a", command.pid), "the process blocker names the command");
  assert(namesPid(probe, "a", command.ppid), "and its shell");
  const named = blocker(probe, "a", "process")[0].processes.find((entry) => entry.pid === command.pid);
  assert.equal(named.comm, "MainThread", "named by Node's main thread name, not `node`");
  assert.deepEqual(sessionBlockers(probe, "a"), [session]);
});
check("turn-end: the command's end wakes the session with a task notification, whose stop reports no background task, and the blocker no longer names it", () => {
  const scope = span("turn-end");
  const { session } = client(scope);
  const ended = commandOf(scope, "te", "end");
  assert(ended?.opened, "the command ended at its gate");
  const woke = notification(scope, ended);
  assert.equal(woke?.payload.session_id, session);
  assert.deepEqual(firstStopAfter(scope, woke, session).backgroundTasks, []);
  const probe = probeOf(scope, "after-release");
  assert.equal(probe.command.alive, false);
  assert(!namesPid(probe, "a", ended.pid));
});
check("move: after `EnterWorktree` to `b` the command keeps working in `a`, where only the `process` blocker remains, while `b` holds the session", () => {
  const scope = span("move");
  const { session, host } = client(scope);
  const command = started(scope, "mv", session, host);
  const moved = hooksOf(scope).find((hook) => hook.event === "PostToolUse" && hook.payload.tool_name === "EnterWorktree");
  assert.equal(moved?.payload.cwd, treeB);
  reportsRunning(firstStopAfter(scope, moved, session));
  const probe = probeOf(scope, "after-move");
  runningInA(probe, command);
  assert.equal(probe.checks.a.removable, false);
  assert.deepEqual(probe.checks.a.blockers.map((entry) => entry.kind), ["process"]);
  assert(namesPid(probe, "a", command.pid));
  assert(!namesPid(probe, "a", host), "the Host Process moved with the session");
  assert.deepEqual(sessionBlockers(probe, "b"), [session]);
  assert(namesPid(probe, "b", host));
});
check("move: the command's end wakes the session where it moved to", () => {
  const scope = span("move");
  const { session } = client(scope);
  const woke = notification(scope, commandOf(scope, "mv", "end"));
  assert.equal(woke?.payload.session_id, session);
  assert.equal(woke.payload.cwd, treeB);
  assert(!namesPid(probeOf(scope, "after-release"), "a", commandOf(scope, "mv", "end").pid));
});
check("clear: `/clear` replaces the session in the same Host Process while the command runs on, its environment still naming the session that ended", () => {
  const scope = span("clear");
  const { session, host } = client(scope);
  const command = started(scope, "cl", session, host);
  const ended = one(hooksOf(scope), (hook) => hook.event === "SessionEnd" && hook.payload.reason === "clear", "SessionEnd(clear)");
  assert.equal(ended.payload.session_id, session);
  const next = one(hooksOf(scope), (hook) => hook.event === "SessionStart" && hook.payload.source === "clear", "SessionStart(clear)");
  assert.notEqual(next.payload.session_id, session);
  assert.equal(next.hostPid, host);
  const probe = probeOf(scope, "after-clear");
  runningInA(probe, command);
  assert.deepEqual(probe.stored[session], [], "the ended session has no record");
  assert.deepEqual(sessionBlockers(probe, "a"), [next.payload.session_id]);
  assert(namesPid(probe, "a", command.pid));
  const woke = notification(scope, commandOf(scope, "cl", "end"));
  assert.equal(woke?.payload.session_id, next.payload.session_id, "the notification wakes the new session");
});
check("exit-stop: `/exit` asks about the running command, and \"Exit and stop tasks\" ends it, leaving `a` removable", () => {
  const scope = span("exit-stop");
  const { session, host } = client(scope);
  const command = started(scope, "es", session, host);
  assert(one(scope, (record) => record.kind === "wait" && record.label === "es exit dialog", "dialog wait").met);
  const dialog = one(scope, (record) => record.kind === "screen" && record.label === "es-exit-dialog", "dialog screen").tail;
  for (const text of ["Background work is running", "The following will stop when you exit: shell", "1. Exit and stop tasks", "2. Move to background and exit", "3. Stay"])
    assert(dialog.includes(text), `the dialog shows ${text}`);
  assert.equal(one(scope, (record) => record.kind === "action.choose", "choice").choice, "first");
  assert.equal(one(scope, (record) => record.kind === "client.exit", "exit").status, 0);
  const probe = probeOf(scope, "after-exit");
  assert.equal(probe.command.alive, false);
  assert.equal(probe.shell.alive, false);
  assert.equal(probe.checks.a.removable, true);
  assert(!commandOf(scope, "es", "end"), "the command never reached its gate");
  assert.equal(command.cwd, treeA);
});
check("exit-background: \"Move to background and exit\" forks a session into a new background Host Process and ends the first; the command runs on, reparented, its environment naming the ended session", () => {
  const scope = span("exit-background");
  const { session, host } = client(scope);
  const command = started(scope, "eb", session, host);
  assert.equal(one(scope, (record) => record.kind === "action.choose", "choice").choice, "second");
  const fork = one(hooksOf(scope), (hook) => hook.event === "SessionStart" && hook.payload.source === "fork", "SessionStart(fork)");
  assert.notEqual(fork.payload.session_id, session);
  assert.notEqual(fork.hostPid, host, "the fork runs in another Host Process");
  const ended = one(hooksOf(scope), (hook) => hook.event === "SessionEnd" && hook.payload.session_id === session, "first session's end");
  assert.equal(ended.payload.reason, "prompt_input_exit");
  const agents = one(scope, (record) => record.kind === "action.claude" && record.label === "eb-agents", "agents").agents;
  assert.deepEqual(agents.map((agent) => [agent.sessionId, agent.kind, agent.pid]), [[fork.payload.session_id, "background", fork.hostPid]]);
  const probe = probeOf(scope, "after-exit");
  runningInA(probe, command);
  assert.equal(probe.shell.ppid, 1, "the shell outlived its Host Process");
  assert.deepEqual(probe.stored[session], []);
  assert.deepEqual(sessionBlockers(probe, "a"), [fork.payload.session_id]);
  assert(namesPid(probe, "a", command.pid));
  assert(namesPid(probe, "a", fork.hostPid));
  const directories = one(scope, (record) => record.kind === "daemon.directories" && record.label === "eb-exited", "directories");
  assert.equal(directories.added, 1, "the background Host Process took a daemon directory");
});
check("exit-background: the command's end wakes the forked session, and stopping the daemon ends it", () => {
  const scope = span("exit-background");
  const fork = one(hooksOf(scope), (hook) => hook.event === "SessionStart" && hook.payload.source === "fork", "fork");
  const woke = notification(scope, commandOf(scope, "eb", "end"));
  assert.equal(woke?.payload.session_id, fork.payload.session_id);
  const stop = one(scope, (record) => record.kind === "action.claude" && record.label === "eb-daemon-stop", "daemon stop");
  assert.equal(stop.status, 0);
  const listed = one(scope, (record) => record.kind === "action.claude" && record.label === "eb-agents-after", "agents after");
  const ended = one(hooksOf(scope), (hook) => hook.event === "SessionEnd" && hook.payload.session_id === fork.payload.session_id, "fork's end");
  assert(ended.receipt > listed.receipt, "the fork ended once the daemon was stopped");
  const directories = one(scope, (record) => record.kind === "daemon.directories" && record.label === "eb-daemon-stopped", "directories");
  assert.equal(directories.added, 0);
});
check("headless: `claude -p` exits while its command runs, and the command ends with it", () => {
  const scope = span("headless");
  const spawned = one(scope, (record) => record.kind === "client.spawn", "client");
  const command = commandOf(scope, "hl", "start");
  assert.equal(command.cwd, treeA);
  assert.equal(command.env.CLAUDE_CODE_ENTRYPOINT, "sdk-cli");
  assert.equal(command.ancestry[0].ppid, spawned.pid);
  reportsRunning(firstStopAfter(scope, command, command.env.CLAUDE_CODE_SESSION_ID));
  const exit = one(scope, (record) => record.kind === "client.exit", "exit");
  assert.equal(exit.status, 0);
  const gate = one(scope, (record) => record.kind === "gate", "gate");
  assert(exit.receipt < gate.receipt, "the client exited before the gate opened");
  const probe = probeOf(scope, "after-turn");
  assert.equal(probe.command.alive, false);
  assert.equal(probe.checks.a.removable, true);
  assert(!commandOf(scope, "hl", "end"));
  const session = command.env.CLAUDE_CODE_SESSION_ID;
  assert(!hooksOf(scope).some((hook) => hook.event === "SessionEnd"), "a headless exit publishes no SessionEnd");
  assert.deepEqual(probe.stored[session].map((entry) => [entry.store, entry.state]), [["a", "waiting"]]);
});
check("the run left no fixture process, and the operator's daemon directories were kept", () => {
  assert.deepEqual(records.find((record) => record.kind === "cleanup.remaining").pids, []);
  for (const entry of records.filter((record) => record.kind === "daemon.directories")) {
    assert.equal(entry.preexistingKept, true);
    assert.equal(entry.removed, 0);
  }
  assert.equal(records.find((record) => record.kind === "daemon.directories" && record.label === "cleanup").added, 0);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} checks passed`);
