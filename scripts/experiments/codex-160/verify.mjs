// Independent verifier for a Codex 160 experiment trace. Checks the recorded
// hook, shell, thread and process evidence against the identity and lifecycle
// claims without importing the runner or publisher.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const expectedVersion = process.argv[3] ?? "0.155.1";
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const hooks = of("hook");
const commands = of("command").filter((record) => record.phase === "start");
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "verify.mjs"]);
// The trace names the exact sources that produced it, this file included.
for (const [file, digest] of Object.entries(environment.sourceSHA256)) {
  assert.equal(createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex"), digest, `${file} matches the hash the run recorded`);
}
const scenarios = of("scenario").map((record) => record.name);
for (const name of ["hook-trust", "two-root-threads", "fork", "subagent", "second-client-attach", "interrupt", "unsubscribe-unload", "exec-cli", "competing-resume", "unsubscribe-unload-wait", "abrupt-server-exit", "stored-thread-resume", "graceful-server-exit"]) {
  assert(scenarios.includes(name), `scenario ${name} ran`);
}
const servers = Object.fromEntries(of("server.start").map((record) => [record.label, record.pid]));
const under = (chain, pid) => chain.some((entry) => entry.pid === pid);

// Hooks were untrusted until the ledger named their hashes; then every hook ran.
const [before, after] = of("hooks.list");
assert(before.before.every((entry) => entry[2] === "untrusted") && after.after.every((entry) => entry[1] === "trusted"), "trust came from the ledger");

// Every shell claims a thread and a session; a root thread's two claims agree,
// and the hook process itself carries no thread identity in its environment.
for (const command of commands) {
  assert(command.env.CODEX_THREAD_ID && command.env.CODEX_SESSION_ID, `command ${command.label} claims thread and session`);
}
for (const hook of hooks) {
  assert(hook.payload.session_id && hook.payload.cwd && hook.env.CODEX_HOME, `hook ${hook.event} carries session_id and cwd`);
  assert(!hook.env.CODEX_THREAD_ID && !hook.env.CODEX_SESSION_ID, `hook ${hook.event} environment names no thread`);
}

// Two root threads on one app-server: id = sessionId = hook session_id = shell claims.
const started = of("threads.started")[0];
const identities = of("identity");
assert.equal(identities.length, 2);
for (const [label, thread] of [["root-a", started.a], ["root-b", started.b]]) {
  const identity = identities.find((record) => record.label === label);
  assert.equal(thread.sessionId, thread.id);
  assert.equal(identity.hookSessionId, thread.id);
  assert.equal(identity.shellEnv.CODEX_THREAD_ID, thread.id);
  assert.equal(identity.shellEnv.CODEX_SESSION_ID, thread.id);
  assert.equal(identity.hookCwd, thread.cwd);
  assert.equal(identity.shellCwd, thread.cwd);
  assert(under(identity.shellAncestry, servers.primary) && under(identity.hookAncestry, servers.primary), `${label} shell and hook run under the primary server`);
}
assert.notEqual(started.a.cwd, started.b.cwd);
const loaded = of("threads.loaded")[0].loaded;
assert(loaded.includes(started.a.id) && loaded.includes(started.b.id));
const serverIdentity = of("server.identity")[0];
assert.equal(serverIdentity.comm, "codex");
assert(!serverIdentity.otherProcesses.some((entry) => /codex/.test(entry[2]) || /codex/.test(entry[3])), "no second Codex process serves the loaded threads");
for (const label of ["root-a", "root-b"]) {
  const start = hooks.find((record) => record.event === "SessionStart" && record.payload.session_id === (label === "root-a" ? started.a.id : started.b.id));
  assert.equal(start.payload.source, "startup");
}

// A fork takes its own id and sessionId, records its origin, and starts with source "fork".
const fork = of("fork.identity")[0];
assert.notEqual(fork.forkId, started.a.id);
assert.equal(fork.forkSessionId, fork.forkId);
assert.equal(fork.forkedFromId, started.a.id);
assert.equal(fork.startSource, "fork");
assert.equal(fork.startSessionId, fork.forkId);
assert(!fork.startPayloadKeys.some((key) => /parent|origin|fork/i.test(key)), "SessionStart names no parent for a fork");
assert.equal(fork.shellEnv.CODEX_THREAD_ID, fork.forkId);
assert.equal(fork.shellEnv.CODEX_SESSION_ID, fork.forkId);

// A sub-agent is its own loaded thread with parentThreadId set; its shell
// carries its own CODEX_THREAD_ID beside the root CODEX_SESSION_ID; its hooks
// carry the root session_id plus agent_id; it publishes no SessionStart.
const subagent = of("subagent.identity")[0];
const childId = subagent.childShellEnv.CODEX_THREAD_ID;
assert.notEqual(childId, started.a.id);
assert.equal(subagent.childShellEnv.CODEX_SESSION_ID, started.a.id);
assert.equal(subagent.subagentStart.session_id, started.a.id);
assert.equal(subagent.subagentStart.agent_id, childId);
assert.equal(subagent.subagentStop.payload.agent_id, childId);
assert.equal(subagent.childThread.id, childId);
assert.equal(subagent.childThread.parentThreadId, started.a.id);
assert.equal(subagent.childThread.sessionId, started.a.id);
assert(subagent.loadedWithChild.includes(childId), "the child is a loaded thread");
assert.deepEqual(subagent.childToolHooks.map((event) => [event[0], event[1], event[2]]), [["PreToolUse", started.a.id, childId], ["PostToolUse", started.a.id, childId]]);
assert.deepEqual(subagent.sessionStartsDuringDelegate, [], "no SessionStart for a sub-agent");
assert(under(subagent.childShellAncestry, servers.primary));
const childTurnIds = new Set(hooks.filter((record) => record.payload.agent_id === childId).map((record) => record.payload.turn_id));
const parentTurnIds = new Set(hooks.filter((record) => record.payload.session_id === started.a.id && record.payload.agent_id === undefined && record.payload.turn_id).map((record) => record.payload.turn_id));
assert(childTurnIds.size === 1 && ![...childTurnIds].some((id) => parentTurnIds.has(id)), "the child's hooks carry their own turn_id");
assert(!hooks.some((record) => record.event === "SessionEnd" && record.payload.session_id === childId), "no SessionEnd for a sub-agent");

// Attaching a second client to loaded threads publishes nothing; the turn a
// departed client started completes for the remaining subscriber.
const attach = of("client.attach")[0];
assert.deepEqual(attach.newHooks, []);
assert.deepEqual(attach.errors, []);
assert.equal(attach.b.id, started.b.id);
const departure = of("client.departure")[0];
assert(departure.commandEnded && departure.turnStatus === "completed");
assert(!departure.newHooks.some((event) => ["Interrupt", "SessionEnd"].includes(event[0])));

// Interrupt kills the command, publishes Interrupt with the turn id, and no Stop.
const interrupt = of("interrupt.result")[0];
assert.equal(interrupt.turnStatus, "interrupted");
assert(!interrupt.commandEnded && !interrupt.commandAlive);
assert.equal(interrupt.interruptHook.session_id, started.b.id);
assert(interrupt.interruptHook.turn_id);
assert(!interrupt.newHooks.some((event) => event[0] === "Stop" || event[0] === "PostToolUse"));

// `codex exec` is its own process and its own thread; it ends at exit and
// resumes under the process's cwd with source "resume".
const exec = of("exec.identity")[0];
assert.equal(exec.status, 0);
assert.equal(exec.shellEnv.CODEX_THREAD_ID, exec.threadId);
assert.equal(exec.shellEnv.CODEX_SESSION_ID, exec.threadId);
assert(under(exec.shellAncestry, exec.pid) && !under(exec.shellAncestry, servers.primary));
assert(exec.hooks.every((event) => event[4] === true && event[5] === false), "every exec hook descends from the exec process");
assert.deepEqual(exec.hooks.map((event) => event[0]), ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"]);
const resume = of("exec.resume")[0];
assert.equal(resume.status, 0);
assert.equal(resume.startSessionId, exec.threadId);
assert.equal(resume.startSource, "resume");
assert.notEqual(resume.shellCwd, exec.shellCwd);
assert.equal(resume.startCwd, resume.shellCwd);

// A thread the server holds loaded refuses a competing resume on both routes.
const [competeExec, competeServer] = of("compete.result");
assert.notEqual(competeExec.status, 0);
assert(competeExec.conflict && !competeExec.commandRan && competeExec.newHooks.length === 0);
assert(competeServer.error && /active writer/i.test(competeServer.error.message));
assert.equal(competeServer.read.id, started.a.id);
assert(competeExec.locks.includes(`${started.a.id}.lock`));

// Unsubscribing the last client unloads the thread after the default delay,
// with SessionEnd; the sub-agent unloaded with thread/closed but no hook.
const unload = of("unload.result")[0];
assert(unload.ended && unload.reason === "other");
assert(unload.elapsedMs >= 60000 && unload.elapsedMs < 70000, `unload after ${unload.elapsedMs} ms`);
assert(unload.closedNotifications.some((entry) => entry[0] === fork.forkId));
assert(!unload.loaded.includes(fork.forkId) && !unload.loaded.includes(childId));

// SIGKILL publishes nothing and leaves the writer locks; the stored thread
// still resumes elsewhere with source "resume" and the cwd override.
const kill = of("kill.result")[0];
assert.deepEqual(kill.newHooks, []);
assert.equal(kill.serverExit.signal, "SIGKILL");
assert(kill.locksAfter.includes(`${started.a.id}.lock`) && kill.locksAfter.includes(`${started.b.id}.lock`));
assert.deepEqual(kill.leftover, [], "no fixture process outlives the killed server");
const resumed = of("thread.resumed")[0];
assert.equal(resumed.read.status.type, "notLoaded");
assert.equal(resumed.read.cwd, started.a.cwd);
assert.equal(resumed.resumed.id, started.a.id);
assert.equal(resumed.resumed.cwd, started.b.cwd);
assert.deepEqual(resumed.hooksAtResume, [], "thread/resume publishes no hook until a turn runs");
const stored = of("stored.identity")[0];
assert.equal(stored.startSource, "resume");
assert.equal(stored.startSessionId, started.a.id);
assert.equal(stored.startCwd, started.b.cwd);
assert.equal(stored.shellCwd, started.b.cwd);
assert.equal(stored.shellEnv.CODEX_THREAD_ID, started.a.id);
assert(under(stored.shellAncestry, servers.replacement));

// Graceful exit publishes SessionEnd for the loaded thread and releases its lock.
const graceful = of("graceful.result")[0];
assert.equal(graceful.exit.status, 0);
assert(graceful.newHooks.some((event) => event[0] === "SessionEnd" && event[1] === started.a.id && event[2] === "other"));
assert(!graceful.locksAfter.includes(`${started.a.id}.lock`));
assert.deepEqual(graceful.leftover, []);

// The trace holds metadata only: no prompts, transcripts, or tool payloads.
const text = readFileSync(tracePath, "utf8");
assert(!/"transcript_path":|"last_assistant_message":|"tool_input":|"tool_response":|"prompt":/.test(text), "transcripts, prompts and tool payloads not retained");
console.log(`Verified ${records.length} records: ${hooks.length} hooks, ${commands.length} commands, ${scenarios.length} scenarios.`);
