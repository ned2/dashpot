// Independent verifier for a Codex 148 experiment trace.
// Checks the recorded daemon, protocol, hook and shell evidence against the
// relocation claims without importing the runner or the publisher.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const expectedVersion = process.argv[3] ?? "0.155.1";
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const hooks = of("hook");
const commands = of("command").filter((record) => record.phase === "start");
const command = (label) => commands.find((record) => record.label === label);
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const { fixture, other, third, socketPath } = environment;
const scenarios = of("scenario").map((record) => record.name);
for (const name of ["daemon-start", "attached-terminal", "controller-relocation", "sibling-thread", "busy-thread", "plain-terminal", "terminal-exit"]) {
  assert(scenarios.includes(name), `scenario ${name} ran`);
}

// The shared daemon is one process, addressed on its control socket, and the
// controller reached it there rather than through a server of its own.
const daemon = of("daemon.identity")[0];
assert.equal(daemon.versionJSON.status, "running");
assert.equal(daemon.versionJSON.appServerVersion, expectedVersion);
assert.equal(daemon.socket, socketPath);
assert.equal(daemon.processes.length, 1);
assert.match(daemon.processes[0][3], /app-server --listen unix:\/\/ --managed-daemon/);
const controller = of("client.connect").find((record) => record.client === "controller");
assert.equal(controller.transport, "unix-websocket");
assert.equal(controller.error, null);
assert.equal(of("hooks.list")[1].after.every(([, trust]) => trust === "trusted"), true);

// Every hook names its thread in the payload and every shell in its
// environment; the shell's ancestry is the daemon, not the terminal that
// attached to it.
for (const hook of hooks) assert(hook.payload.session_id && hook.payload.cwd, `hook ${hook.event} carries session_id and cwd`);
for (const shell of commands) assert.equal(shell.env.CODEX_SESSION_ID, shell.env.CODEX_THREAD_ID, `shell ${shell.label} claims one thread`);
const attached = of("attached.identity")[0];
assert.equal(attached.shellCwd, other);
assert.equal(attached.shellAncestry[0].cmdline, daemon.processes[0][3]);
assert(attached.loaded.includes(attached.threadId), "the terminal's thread is loaded on the daemon");
assert.equal(attached.thread.cwd, other);
assert.equal(attached.thread.status.type, "idle");

// thread/resume on a loaded thread ignores its cwd override; turn/start
// honours one, and it sticks: the thread reads at the new cwd and the
// terminal's own next turn runs there, all under one thread id.
const subscribe = of("controller.subscribe")[0];
assert.equal(subscribe.error, null);
assert.equal(subscribe.cwdOverrideHonoured, false);
assert.deepEqual(subscribe.hooksAtSubscribe, []);
const move = of("controller.move")[0];
assert.equal(move.status, "completed");
assert.equal(move.shellCwd, fixture);
assert.equal(move.shellEnv.CODEX_THREAD_ID, attached.threadId);
assert.equal(move.thread.cwd, fixture);
assert.equal(move.terminalSawTurn, true);
assert.deepEqual(move.newHooks.map(([event, session, , cwd]) => [event, session === attached.threadId, cwd]),
  [["UserPromptSubmit", true, fixture], ["PreToolUse", true, fixture], ["PostToolUse", true, fixture], ["Stop", true, fixture]]);
const after = of("terminal.after-move")[0];
assert.equal(after.shellCwd, fixture);
assert.equal(after.shellEnv.CODEX_THREAD_ID, attached.threadId);
assert.equal(after.thread.cwd, fixture);
assert(!hooks.some((record) => record.event === "SessionStart" && record.receipt > attached.receipt && record.receipt < after.receipt), "no new session during the move");

// A sibling thread on the same daemon is untouched by the move.
const sibling = of("sibling.outcome")[0];
assert.notEqual(sibling.b.threadId, attached.threadId);
assert.equal(sibling.a.shellCwd, other);
assert.equal(sibling.b.shellCwd, third);
assert.equal(sibling.b.shellSession, sibling.b.threadId);
assert(sibling.loaded.includes(attached.threadId) && sibling.loaded.includes(sibling.b.threadId), "both threads loaded");
// The daemon also lists the terminals' ephemeral helper threads.
assert(sibling.otherLoaded.length > 0 && sibling.otherLoaded.every((thread) => thread.ephemeral === true), "every other loaded thread is ephemeral");

// turn/start while the thread is busy is answered with the running turn's own
// id: the request's input joins that turn, runs after the active command in
// that turn's cwd, and only then does the thread report the requested cwd.
const busyRequest = of("busy.request")[0];
assert.equal(busyRequest.error, null);
assert.equal(busyRequest.result.status, "inProgress");
const runningTurn = hooks.find((record) => record.event === "UserPromptSubmit" && record.receipt > of("scenario").find((s) => s.name === "busy-thread").receipt).payload.turn_id;
assert.equal(busyRequest.result.turnId, runningTurn, "the busy request names the running turn");
assert(hooks.filter((record) => record.event === "UserPromptSubmit" && record.payload.turn_id === runningTurn).length >= 2, "the request's input ran inside the running turn");
const busy = of("busy.outcome")[0];
assert(busy.controllerTurnRanAt > busy.holdEndedAt, "queued turn ran after the hold");
assert.equal(busy.controllerShellCwd, other);
assert.equal(busy.thread.cwd, third);
assert.deepEqual(of("busy.background-terminals")[0].result, { data: [], nextCursor: null });

// A plain terminal launched without `--remote` while the managed daemon runs
// is daemon-hosted too: its shell descends from the daemon, the daemon lists
// its thread, and the controller subscribes to it (the cwd override again
// ignored on a loaded thread).
const plain = of("plain.outcome")[0];
assert.equal(plain.shellCwd, third);
assert.equal(plain.shellAncestry[0][0], daemon.processes[0][0]);
assert(plain.loaded.includes(plain.threadId), "plain terminal's thread loaded on the daemon");
assert.equal(plain.resumeError, null);
assert.equal(plain.resumed.cwd, third);
assert(plain.processes.some(([, , comm, cmdline]) => comm === "codex" && !cmdline.includes("--remote") && !cmdline.includes("app-server")), "a plain codex client process exists");
assert.deepEqual(of("plain.exit")[0].newHooks, []);

// The terminal's exit neither ends nor unloads the thread while the
// controller stays subscribed; SessionEnd follows the controller's
// unsubscribe after the daemon's idle unload delay.
const terminalExit = of("terminal.exit-outcome")[0];
assert.equal(terminalExit.exited.status, 0);
assert.deepEqual(terminalExit.newHooks, []);
assert(terminalExit.loaded.includes(attached.threadId), "thread still loaded after the terminal exits");
assert(terminalExit.locksAfter.includes(`${attached.threadId}.lock`), "writer lock held after the terminal exits");
const unload = of("unload.outcome")[0];
assert.equal(unload.unsubscribe.status, "unsubscribed");
assert(unload.delayMs >= 55000 && unload.delayMs < 90000, `idle unload after about a minute: ${unload.delayMs}`);
assert.equal(unload.reason, "other");
assert.equal(unload.endCwd, third);
assert(!unload.loaded.includes(attached.threadId), "thread unloaded");
assert(!unload.locks.includes(`${attached.threadId}.lock`), "writer lock released");

// The trace is ordered by receipt and free of prompt or transcript content.
records.forEach((record, index) => assert.equal(record.receipt, index + 1));
const text = readFileSync(tracePath, "utf8");
for (const key of ["transcript_path", "prompt", "tool_input", "tool_response"]) assert(!text.includes(`"${key}":`), `${key} value absent`);
console.log(`Verified ${records.length} records: ${scenarios.length} scenarios, ${hooks.length} hooks, ${commands.length} shells.`);
