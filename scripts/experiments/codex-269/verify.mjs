// Independent verifier for a Codex 269 experiment trace.
// Checks the recorded hosting, hook, shell, and protocol evidence against the
// declared-relocation claims without importing the runner or the publisher.
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
const forScenario = (kind, scenario) => { const found = of(kind).find((record) => record.scenario === scenario); assert(found, `${kind} recorded for ${scenario}`); return found; };
const hooks = of("hook");
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
// The trace names the exact sources that produced it, this file included.
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs", "verify.mjs"]);
for (const [file, digest] of Object.entries(environment.sourceSHA256)) {
  assert.equal(createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex"), digest, `${file} matches the hash the run recorded`);
}
const { other, third, socketPath } = environment;
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "no-daemon", "in-window", "after-unload"]);
assert.equal(of("hooks.list")[0].after.every(([, trust]) => trust === "trusted"), true);

// The control ran with no daemon: none survived `daemon stop`, and the plain
// terminal did not start one.
const afterStop = of("processes").find((record) => record.label === "after-daemon-stop");
assert.deepEqual(afterStop.processes, []);
assert.equal(afterStop.socketExists, false);
const afterControl = of("processes").find((record) => record.label === "after-no-daemon");
assert.deepEqual(afterControl.processes, []);
assert.equal(afterControl.socketExists, false);
const restarted = of("processes").find((record) => record.label === "daemon-restarted");
assert.equal(restarted.processes.length, 1);
assert.match(restarted.processes[0][3], /app-server/);
const daemonPid = restarted.daemonPid;
assert.equal(daemonPid, restarted.processes[0][0]);
assert.equal(of("client.connect")[1].error, null);
assert.equal(of("client.connect")[1].socket, socketPath);

// Every hook names its thread in the payload and every shell in its environment.
for (const hook of hooks) assert(hook.payload.session_id && hook.payload.cwd, `hook ${hook.event} carries session_id and cwd`);
for (const shell of of("command")) assert.equal(shell.env.CODEX_SESSION_ID, shell.env.CODEX_THREAD_ID, `shell ${shell.label} claims one thread`);
const events = (list) => list.map(([event]) => event);
const cwds = (list) => new Set(list.map(([, , , cwd]) => cwd));
const threadOf = (list, threadId) => list.every(([, session]) => session === threadId);
const turn = ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"];

// Shared shape of every scenario: the first terminal's turn ran in `other`
// under the thread it claims; `codex resume <id> -C third` ran its prompt and
// a typed second turn in `third` under the same thread id, with `SessionStart`
// `resume` at `third` as the first hook of the new runtime; no read-only
// notice or picker appeared; no hook fired between the second turn and the
// resumed terminal's exit; and that exit ended the thread at `third`.
const scenarios = {};
for (const name of ["no-daemon", "in-window", "after-unload"]) {
  const first = forScenario("first.identity", name);
  const exit = forScenario("first.exit", name);
  const resume = forScenario("resume.outcome", name);
  const second = forScenario("resume.second-turn", name);
  const watch = forScenario("resume.late-end-watch", name);
  const final = forScenario("resume.final-exit", name);
  const threadId = first.threadId;
  assert.equal(first.shellCwd, other);
  assert.equal(first.shellEnv.CODEX_SESSION_ID, threadId);
  assert.deepEqual(events(first.hooks), ["SessionStart", ...turn]);
  assert.equal(first.hooks[0][2], "startup");
  assert(threadOf(first.hooks, threadId) && cwds(first.hooks).size === 1 && cwds(first.hooks).has(other), `${name}: first turn at other`);
  assert.equal(exit.exited.status, 0);

  assert.equal(resume.ran, true, `${name}: resumed terminal ran its prompt`);
  assert.equal(resume.exited, null);
  assert.deepEqual(resume.screen, { readOnlyNotice: false, picker: false });
  assert.equal(resume.sameThread, true);
  assert.equal(resume.shellEnv.CODEX_SESSION_ID, threadId);
  assert.equal(resume.shellCwd, third);
  const start = resume.hooks.findIndex(([event]) => event === "SessionStart");
  assert(start >= 0, `${name}: SessionStart after resume`);
  assert.deepEqual(events(resume.hooks.slice(start)), ["SessionStart", ...turn]);
  assert.equal(resume.hooks[start][2], "resume");
  assert(threadOf(resume.hooks, threadId) && cwds(resume.hooks.slice(start)).size === 1 && cwds(resume.hooks.slice(start)).has(third), `${name}: resumed runtime at third`);
  assert(resume.locks.includes(`${threadId}.lock`), `${name}: resumed thread holds its writer lock`);

  assert.equal(second.shellCwd, third);
  assert.equal(second.shellEnv.CODEX_SESSION_ID, threadId);
  assert.deepEqual(events(second.hooks), turn);
  assert(threadOf(second.hooks, threadId) && cwds(second.hooks).size === 1 && cwds(second.hooks).has(third), `${name}: second turn at third`);
  assert.deepEqual(watch.hooksWhileWatching, []);
  assert.equal(watch.resumedExited, null);

  assert.equal(final.exited.status, 0);
  assert(final.sessionEnd, `${name}: the resumed thread ended`);
  assert.equal(final.sessionEnd.cwd, third);
  assert.equal(final.sessionEnd.reason, "other");
  assert.deepEqual(events(final.hooks), ["SessionEnd"]);
  assert(!final.loaded.includes(threadId) && !final.locks.includes(`${threadId}.lock`), `${name}: thread unloaded and unlocked at the end`);
  scenarios[name] = { threadId, first, exit, resume, second, watch, final };
}
assert.equal(new Set(Object.values(scenarios).map((scenario) => scenario.threadId)).size, 3, "three distinct threads");
// The trace's hook records for one thread, in receipt order.
const hooksOfThread = (threadId) => hooks.filter((record) => record.payload.session_id === threadId);
const hostedBy = (record, pid) => record.ancestry.some((entry) => entry.pid === pid);

// Control: with no daemon, each terminal is its own host. `/exit` ran
// `SessionEnd` at `other` before the process ended; the resume launched
// within a second was a fresh process whose first hook was `SessionStart`
// `resume` at `third`.
{
  const { threadId, first, exit, resume, second, watch, final } = scenarios["no-daemon"];
  assert.equal(first.host.daemonHosted, false);
  assert.deepEqual(first.loaded, []);
  assert.deepEqual(exit.hooksSinceExit.map(([event, session, reason, cwd]) => [event, session, reason, cwd]), [["SessionEnd", threadId, "other", other]]);
  assert(resume.launchDelayMs < 1000, `resume launched promptly after the exit: ${resume.launchDelayMs}`);
  assert.deepEqual(exit.processes, [], "no fixture process outlived the first terminal");
  assert(!exit.locks.includes(`${threadId}.lock`), "the writer lock left with the process");
  assert.equal(resume.host.daemonHosted, false);
  assert.notEqual(resume.host.hostPid, first.host.hostPid, "the resumed terminal is a new process");
  assert.equal(resume.hooks[0][0], "SessionStart");
  assert.equal(second.host.hostPid, resume.host.hostPid);
  assert.equal(watch.lateSessionEnd, null);
  assert(final.sessionEnd.msAfterExit < 5000, `embedded SessionEnd at exit: ${final.sessionEnd.msAfterExit}`);
  const ends = hooksOfThread(threadId).filter((record) => record.event === "SessionEnd");
  assert.equal(ends.length, 2);
  assert(hostedBy(ends[0], first.host.hostPid) && hostedBy(ends[1], resume.host.hostPid), "each SessionEnd descends from its own terminal");
}

// Inside the unload window: the daemon still held the idle thread at `other`
// with its lock when the resume was launched within a second of the exit.
// The daemon-hosted resume shut that runtime down — `SessionEnd` `other` at
// `other` — and cold-resumed it at `third`, `SessionStart` `resume` following
// the end; no SessionEnd arrived later while the resumed terminal lived.
{
  const { threadId, first, exit, resume, second, watch, final } = scenarios["in-window"];
  assert.equal(first.host.daemonHosted, true);
  assert.equal(first.host.hostPid, daemonPid);
  assert(first.loaded.includes(threadId));
  assert.deepEqual(exit.hooksSinceExit, [], "the terminal's exit ran no hook");
  assert(resume.launchDelayMs < 1000, `resume launched inside the unload window: ${resume.launchDelayMs}`);
  assert(resume.hooks[0][4] > 0, "the origin SessionEnd came after the launch, not before it");
  assert(exit.loaded.includes(threadId) && exit.locks.includes(`${threadId}.lock`), "thread still loaded and locked at resume time");
  assert.deepEqual([exit.thread.cwd, exit.thread.status.type], [other, "idle"]);
  assert.equal(resume.host.daemonHosted, true);
  assert.equal(resume.host.hostPid, daemonPid);
  assert.deepEqual(resume.hooks.slice(0, 2).map(([event, session, reason, cwd]) => [event, session, reason, cwd]), [["SessionEnd", threadId, "other", other], ["SessionStart", threadId, "resume", third]]);
  assert(resume.hooks[0][4] < resume.hooks[1][4], "SessionEnd at the origin precedes SessionStart at the target");
  assert(resume.hooks[1][4] < 5000, `the new runtime started promptly: ${resume.hooks[1][4]}`);
  assert.equal(resume.thread.cwd, third);
  assert(resume.loaded.includes(threadId));
  assert.equal(second.host.hostPid, daemonPid);
  assert.equal(second.thread.cwd, third);
  assert.deepEqual([watch.lateSessionEnd.cwd, watch.lateSessionEnd.reason], [other, "other"]);
  assert(watch.lateSessionEnd.msAfterResume === resume.hooks[0][4], "the only SessionEnd before the final exit is the one preceding SessionStart");
  assert(final.sessionEnd.msAfterExit >= 55000 && final.sessionEnd.msAfterExit < 90000, `daemon unload after about a minute: ${final.sessionEnd.msAfterExit}`);
  const ends = hooksOfThread(threadId).filter((record) => record.event === "SessionEnd");
  assert.equal(ends.length, 2);
  assert(ends.every((record) => hostedBy(record, daemonPid)), "both SessionEnds descend from the daemon");
}

// After the unload: the daemon ended the thread about a minute after the
// exit, reported it `notLoaded` at `other`, and the resume matched the stored
// thread resume #160 measured: `SessionStart` `resume` at `third` first.
{
  const { threadId, first, exit, resume, second, watch, final } = scenarios["after-unload"];
  assert.equal(first.host.daemonHosted, true);
  assert.deepEqual(exit.hooksSinceExit.map(([event, session, reason, cwd]) => [event, session, reason, cwd]), [["SessionEnd", threadId, "other", other]]);
  assert(exit.hooksSinceExit[0][4] >= 55000 && exit.hooksSinceExit[0][4] < 90000, `unload SessionEnd after about a minute: ${exit.hooksSinceExit[0][4]}`);
  assert(resume.launchDelayMs >= exit.hooksSinceExit[0][4], "the resume launched after SessionEnd");
  assert(!exit.loaded.includes(threadId) && !exit.locks.includes(`${threadId}.lock`), "thread unloaded and unlocked before the resume");
  assert.deepEqual([exit.thread.cwd, exit.thread.status.type], [other, "notLoaded"]);
  assert.equal(resume.host.daemonHosted, true);
  assert.equal(resume.host.hostPid, daemonPid);
  assert.equal(resume.hooks[0][0], "SessionStart");
  assert.equal(resume.thread.cwd, third);
  assert.equal(second.host.hostPid, daemonPid);
  assert.equal(watch.lateSessionEnd, null);
  assert(final.sessionEnd.msAfterExit >= 55000 && final.sessionEnd.msAfterExit < 90000, `daemon unload after about a minute: ${final.sessionEnd.msAfterExit}`);
}

// The trace is ordered by receipt and free of prompt or transcript content.
records.forEach((record, index) => assert.equal(record.receipt, index + 1));
const text = readFileSync(tracePath, "utf8");
for (const key of ["transcript_path", "prompt", "tool_input", "tool_response"]) assert(!text.includes(`"${key}":`), `${key} value absent`);
console.log(`Verified ${records.length} records: ${of("scenario").length} scenarios, ${hooks.length} hooks, ${of("command").filter((record) => record.phase === "start").length} shells.`);
