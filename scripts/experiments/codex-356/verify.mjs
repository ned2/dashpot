// Independent verifier for a Codex 356 acceptance trace. Checks what the
// managed daemon's SessionEnd hooks saw on an unload, a restart and a stop,
// and Dashpot's own published view and Event Log at each step, against the
// claims ADR 0086 and the docs make for the pinned release, without importing
// the runner or Dashpot.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath, expectedVersion = "0.160.0"] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const labelled = (kind, label) => one(kind, (record) => record.label === label);
const view = (label) => labelled("dashpot.view", label);
const hooks = of("hook");
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const scenario = (name) => one("scenario", (record) => record.name === name);
const nextScenario = (name) => of("scenario")[of("scenario").indexOf(scenario(name)) + 1] ?? records.at(-1);
const within = (name) => (record) => record.receipt > scenario(name).receipt && record.receipt < nextScenario(name).receipt;
const hooksIn = (name) => hooks.filter(within(name));
const endsIn = (name) => hooksIn(name).filter((record) => record.event === "SessionEnd");
const runFor = (snapshot, number) => snapshot.agentRuns.filter((run) => run.issueId === `I_fixture_${number}`);
const onlyRun = (snapshot, number) => { const runs = runFor(snapshot, number); assert.equal(runs.length, 1, `${snapshot.label}: one run for Issue ${number}`); return runs[0]; };
const issues = (snapshot) => snapshot.agentRuns.filter((run) => run.issueId !== null).map((run) => run.issueId).sort();
const unbound = (snapshot) => snapshot.agentRuns.filter((run) => run.issueId === null);
const hostedBy = (pid) => `codex pid ${pid}`;
const orphanedUnder = (snapshot, number, pid) => {
  const run = onlyRun(snapshot, number);
  assert.deepEqual([run.orphaned, run.state, run.processOrSession], [true, "unknown", hostedBy(pid)], `${snapshot.label}: Issue ${number} orphaned under ${pid}`);
  return run;
};
const liveUnder = (snapshot, number, pid) => {
  const run = onlyRun(snapshot, number);
  assert.deepEqual([run.orphaned, run.processOrSession], [false, hostedBy(pid)], `${snapshot.label}: Issue ${number} live under ${pid}`);
  return run;
};

// The trace names the exact sources that produced it, this file included.
const environment = one("environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs", "verify.mjs", "waiter.mjs"];
const modules = ["src/dashpot/hook.py", ...["deferred_end.py", "harnesses.py", "hook_publish.py", "liveness.py", "processes.py", "work_reconciliation.py", "work_store.py"]
  .map((file) => `src/dashpot/sessions/${file}`)];
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.deepEqual([...environment.hookEvents].sort(), ["Interrupt", "SessionEnd", "SessionStart", "Stop", "SubagentStart", "SubagentStop", "UserPromptSubmit"]);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "exec", "standalone-exit", "daemon-start", "unload", "restart", "reload-recover", "reload-unload", "stop-busy"]);
assert(of("hooks.list")[0].after.every(([, trust]) => trust === "trusted"), "fixture hooks trusted");
// The daemon's updater stayed off for the whole run, so no updater process
// ever ran and nothing could replace or restart the pinned daemon.
for (const record of of("processes")) {
  assert.equal(record.daemonSettings?.updater?.autoUpdateEnabled, false, `updater off at ${record.label}`);
  assert(!record.processes.some(([, , , cmdline]) => / pid-update-loop/.test(cmdline)), `no updater process at ${record.label}`);
}
// Dashpot's real publisher accepted every hook, and every hook names its thread.
for (const hook of hooks) {
  assert.equal(hook.publisher.status, 0, `publisher accepted ${hook.event}: ${hook.publisher.stderr}`);
  assert(hook.payload.session_id && hook.payload.cwd, `${hook.event} carries session_id and cwd`);
}
for (const record of of("dashpot.view")) {
  assert.equal(record.status, 0, `dashpot view ${record.label}`);
  assert.deepEqual(record.diagnostics, [], `${record.label}: no diagnostics`);
}
assert.equal(of("server.error").length, 0, "the fixture servers saw no error");
// The trace keeps Codex's status lines only: no prompt, model output or
// command text from a one-shot command.
for (const record of of("codex.command")) assert(!/SPIKE:|^user$/m.test(record.stderr ?? "") && !(record.args[0] === "exec" && record.stdout), `${record.label} keeps status lines only`);

// Every SessionEnd, whatever its cause, carries the same keys and reason.
const allEnds = hooks.filter((record) => record.event === "SessionEnd");
assert.equal(allEnds.length, 13);
for (const end of allEnds) {
  assert.deepEqual(end.payloadKeys, allEnds[0].payloadKeys, "one SessionEnd shape");
  assert.equal(end.payload.reason, "other");
}

// Dashpot's Event Log: every hook and settler succeeded. `outcomesOf` lists
// one session's SessionEnd outcomes in order, each [change, Issue].
const outcomes = one("dashpot.events").outcomes;
assert(outcomes.length > 0 && outcomes.every((event) => event["dashpot.outcome.result"] === "succeeded"), "every hook and settler succeeded");
assert(!outcomes.some((event) => event["dashpot.work_store.change"] === "continued" || event["dashpot.work_store.change"] === "relocated"), "nothing continued or carried");
const outcomesOf = (thread) => outcomes.filter((event) => event["dashpot.agent_session.id"] === thread && event["dashpot.hook.event"] === "SessionEnd")
  .sort((left, right) => left.time.localeCompare(right.time)).map((event) => [event["dashpot.work_store.change"], event["dashpot.issue.id"] ?? null]);

// `codex exec` hosts its own thread and its SessionEnd ends Issue 5's run at
// once, with no settler.
const exec = one("exec.outcome").shell;
assert.equal(exec.work.status, 0);
assert.match(shell("exec").ancestry.find((entry) => entry.pid === exec.host).cmdline, / exec /);
assert.deepEqual(endsIn("exec").map((record) => record.host), [exec.host]);
assert.deepEqual(outcomesOf(exec.thread), [["ended", "I_fixture_5"]]);
assert.deepEqual(view("after-exec").agentRuns, []);
assert.deepEqual(labelled("processes", "after-exec").daemons, []);

// A standalone terminal hosts its own thread; its `/exit` ends Issue 6's run
// at once, with no settler.
const standalone = one("standalone.identity").shell;
assert.equal(standalone.work.status, 0);
assert.match(shell("ts-start").ancestry.find((entry) => entry.pid === standalone.host).cmdline, /--disable daemon_auto_start/);
assert.deepEqual(one("standalone.identity").daemons, []);
liveUnder(view("standalone-bound"), 6, standalone.host);
assert.deepEqual(endsIn("standalone-exit").map((record) => record.host), [standalone.host]);
assert.deepEqual(outcomesOf(standalone.thread), [["ended", "I_fixture_6"]]);
assert.deepEqual(view("after-standalone-exit").agentRuns, []);

// The managed daemon runs as `codex app-server … --managed-daemon`.
const started = labelled("processes", "daemon-started");
assert.equal(started.daemons.length, 1);
const firstDaemon = started.daemons[0];
assert.match(started.daemonCmdlines[0], /\/bin\/codex app-server .*--listen unix:\/\/ .*--managed-daemon$/);

// An idle unload: R3 and U1 end about 60 s after their client left, from the
// daemon, which keeps running. Codex kills each SessionEnd hook at about 3 s
// although it is configured for 30 s; a detached waiter sees the daemon still
// running 15 s later. R3's run ends once the settler has seen that; R4, whose
// client stayed, is untouched.
const unload = one("unload.outcome");
const { r3, u1, r4 } = unload.threads;
assert.equal(unload.firstDaemon, firstDaemon);
const unloadEnds = endsIn("unload");
assert.deepEqual(unloadEnds.map((record) => record.payload.session_id).sort(), [r3, u1].sort());
for (const end of unloadEnds) {
  assert.equal(end.host, firstDaemon);
  const afterLeaving = end.startedAt - unload.leftAt;
  assert(afterLeaving > 55000 && afterLeaving < 66000, `unload about 60 s after the client left: ${afterLeaving}`);
}
const killedAtClamp = (name) => {
  for (const end of endsIn(name)) {
    const beats = of("hook.beat").filter((beat) => beat.pid === end.pid).map((beat) => beat.sinceBegin);
    assert(beats.length > 0 && Math.max(...beats) > 2000 && Math.max(...beats) < 3500, `${name}: hook ${end.pid} beat until about 3 s: ${Math.max(...beats)}`);
    assert(!of("hook.end").some((record) => record.pid === end.pid), `${name}: hook ${end.pid} never reached its end`);
  }
};
killedAtClamp("unload");
const unloadWaiters = of("waiter").filter(within("unload"));
assert.deepEqual(unloadWaiters.map((record) => record.session).sort(), [r3, u1].sort());
for (const waiter of unloadWaiters) assert.deepEqual([waiter.exitedSinceHookBegan, waiter.hostAliveAtEnd], [null, true], "the daemon outlives an unload");
assert.equal(shell("r3-start", "work").work.status, 0);
assert.equal(shell("r4-start", "work").work.status, 0);
const unloadBound = view("unload-bound");
liveUnder(unloadBound, 3, firstDaemon);
liveUnder(unloadBound, 4, firstDaemon);
assert.deepEqual(outcomesOf(r3), [["deferred", "I_fixture_3"], ["ended", "I_fixture_3"]]);
assert.deepEqual(outcomesOf(u1), [["unchanged", null]]);
const afterUnload = view("after-unload");
assert.deepEqual(issues(afterUnload), ["I_fixture_4"]);
liveUnder(afterUnload, 4, firstDaemon);
assert.deepEqual(labelled("processes", "after-unload").daemons, [firstDaemon]);
assert.deepEqual(labelled("processes", "after-unload").settlers, []);

// `daemon restart` with four threads loaded: their SessionEnd hooks begin
// within a few milliseconds of one another, from the old daemon, which exits
// once they end; a replacement takes its place. Every bound run is left
// orphaned under the old daemon; the unbound thread's end changes nothing.
const restart = one("restart.outcome");
const { r1, r2, u2 } = one("restart.loaded").threads;
assert.deepEqual([...one("restart.loaded").loaded].sort(), [r1, r2, u2, r4].sort());
assert.equal(restart.firstDaemon, firstDaemon);
const secondDaemon = restart.secondDaemon;
assert.notEqual(secondDaemon, firstDaemon);
const restartEnds = endsIn("restart");
assert.deepEqual(restartEnds.map((record) => record.payload.session_id).sort(), [r1, r2, u2, r4].sort());
assert(restartEnds.every((record) => record.host === firstDaemon));
const restartBegan = restartEnds.map((record) => record.startedAt);
assert(Math.max(...restartBegan) - Math.min(...restartBegan) < 250, "the hooks run in parallel");
const lastHookEnd = Math.max(...restartEnds.map((end) => end.startedAt + one("hook.end", (record) => record.pid === end.pid).sinceBegin));
const exitAfterBegin = restart.firstDaemonExitedAt - Math.min(...restartBegan);
assert(restart.firstDaemonExitedAt >= lastHookEnd && restart.firstDaemonExitedAt - lastHookEnd < 500, "the daemon exits once its hooks end");
assert(exitAfterBegin > 0 && exitAfterBegin < 2000, `the old daemon exits soon after its hooks begin: ${exitAfterBegin}`);
for (const waiter of of("waiter").filter(within("restart"))) {
  assert.equal(waiter.host, firstDaemon);
  assert(waiter.exitedSinceHookBegan !== null && waiter.exitedSinceHookBegan < 2000, "a detached waiter sees the daemon exit");
}
const restartBound = view("restart-bound");
for (const number of [1, 2, 4]) liveUnder(restartBound, number, firstDaemon);
const afterRestart = view("after-restart");
assert.deepEqual(issues(afterRestart), ["I_fixture_1", "I_fixture_2", "I_fixture_4"]);
for (const number of [1, 2, 4]) assert.equal(orphanedUnder(afterRestart, number, firstDaemon).lastActivityAt, null, "an orphan the settler left has no last activity");
assert.deepEqual(unbound(afterRestart), []);
for (const [thread, issue] of [[r1, "I_fixture_1"], [r2, "I_fixture_2"], [r4, "I_fixture_4"]]) {
  assert.deepEqual(outcomesOf(thread).slice(0, 2), [["deferred", issue], ["unchanged", null]], `${issue}: deferred, then left`);
}
assert.deepEqual(outcomesOf(u2)[0], ["unchanged", null]);
assert.deepEqual(labelled("processes", "after-restart").daemons, [secondDaemon]);
assert.deepEqual(labelled("processes", "after-restart").settlers, []);

// The replacement reloaded every thread with no hook. The runner's own
// `thread/resume` of R1 runs no hook either, but R1's next turn on the
// replacement then publishes SessionStart `resume` before its prompt: that
// SessionStart is the resume's, not the reload's, since without a resume a
// reloaded thread's next hook is UserPromptSubmit (#380). The turn binds
// nothing: R1 is listed unbound beside its orphaned run until `work start`
// recovers Issue 1 there, as a new run.
const reloaded = one("reload.loaded");
assert.deepEqual([...reloaded.loaded].sort(), [r1, r2, u2, r4].sort());
assert.equal(reloaded.newHooks, 0);
const show = one("reload.show");
assert.equal(show.shell.host, secondDaemon);
assert.deepEqual(show.hooks.filter(([event]) => event !== "Stop"), [["SessionStart", r1, secondDaemon, false], ["UserPromptSubmit", r1, secondDaemon, false]]);
assert.equal(hooks.find((record) => record.event === "SessionStart" && record.host === secondDaemon).payload.source, "resume");
const reloadedView = view("reloaded-unbound");
orphanedUnder(reloadedView, 1, firstDaemon);
assert.deepEqual(unbound(reloadedView).map((run) => run.processOrSession), [`${r1} hook`]);
assert.equal(one("reload.recover").shell.work.status, 0);
const recovered = liveUnder(view("recovered"), 1, secondDaemon);
assert(recovered.startedAt > onlyRun(restartBound, 1).startedAt, "the recovered run is a new run");
orphanedUnder(view("recovered"), 2, firstDaemon);
orphanedUnder(view("recovered"), 4, firstDaemon);
assert.deepEqual(unbound(view("recovered")), []);

// The threads the replacement reloaded with no client unload about 60 s after
// the restart, from the replacement. Their ends find no run of theirs to end:
// R2's and R4's runs stay orphaned under the old daemon, and no settler starts.
const reloadUnload = one("reload.unload");
assert.equal(reloadUnload.restartedAt, restart.firstDaemonExitedAt);
const reloadEnds = endsIn("reload-unload");
assert.deepEqual(reloadEnds.map((record) => record.payload.session_id).sort(), [r2, u2, r4].sort());
for (const end of reloadEnds) {
  assert.equal(end.host, secondDaemon);
  const afterRestart = end.startedAt - reloadUnload.restartedAt;
  assert(afterRestart > 55000 && afterRestart < 66000, `a reloaded idle thread unloads about 60 s after the restart: ${afterRestart}`);
}
for (const thread of [r2, u2, r4]) assert.deepEqual(outcomesOf(thread).at(-1), ["unchanged", null], "a late end from the replacement leaves the orphan");
const afterReloadUnload = view("after-reload-unload");
assert.deepEqual(issues(afterReloadUnload), ["I_fixture_1", "I_fixture_2", "I_fixture_4"]);
liveUnder(afterReloadUnload, 1, secondDaemon);
orphanedUnder(afterReloadUnload, 2, firstDaemon);
orphanedUnder(afterReloadUnload, 4, firstDaemon);
assert.deepEqual(labelled("processes", "after-reload-unload").settlers, []);

// `daemon stop` while R1's turn waits on the model and R5 sits idle: the
// daemon lets the turn finish (about 20 s) before it runs either thread's
// SessionEnd, so the idle thread's settler cannot see the daemon outlive the
// drain. Codex kills each hook at about 3 s and the daemon exits with them.
// Both runs are left orphaned under the replacement.
const stop = one("stop.outcome");
const { r5 } = stop.threads;
assert.equal(stop.threads.r1, r1);
assert.equal(stop.secondDaemon, secondDaemon);
const stopBound = view("stop-bound");
liveUnder(stopBound, 1, secondDaemon);
liveUnder(stopBound, 5, secondDaemon);
const released = one("model.busy-released");
assert.equal(released.closed, false);
const stopCommand = labelled("codex.command", "daemon-stop");
assert(released.receiptTime - stopCommand.began > 15000, "the turn ran on after the stop began");
// The turn's own Stop hook shows it completed; its `turn/completed` may not
// reach a client of a daemon that is shutting down.
const busyStop = one("hook", (record) => record.event === "Stop" && record.payload.turn_id === stop.busyTurn);
assert(busyStop.startedAt > released.receiptTime - 1000, "the busy turn completed after the model released it");
const stopEnds = endsIn("stop-busy");
assert.deepEqual(stopEnds.map((record) => record.payload.session_id).sort(), [r1, r5].sort());
assert(stopEnds.every((record) => record.host === secondDaemon && record.startedAt > busyStop.startedAt), "no SessionEnd, not even the idle thread's, before the turn finished");
const stopBegan = stopEnds.map((record) => record.startedAt);
assert(Math.max(...stopBegan) - Math.min(...stopBegan) < 250, "the stop's hooks run in parallel");
killedAtClamp("stop-busy");
const stopExit = stop.secondDaemonExitedAt - Math.min(...stopBegan);
assert(stopExit > 2500 && stopExit < 3600, `the daemon exits with its killed hooks: ${stopExit}`);
const stopWaiters = of("waiter").filter(within("stop-busy"));
assert.deepEqual(stopWaiters.map((record) => record.session).sort(), [r1, r5].sort());
for (const waiter of stopWaiters) assert(waiter.exitedSinceHookBegan > 2500 && waiter.exitedSinceHookBegan < 3600, "a detached waiter outlives the killed hook and sees the daemon exit");
const afterStop = view("after-stop");
assert.deepEqual(issues(afterStop), ["I_fixture_1", "I_fixture_2", "I_fixture_4", "I_fixture_5"]);
orphanedUnder(afterStop, 1, secondDaemon);
orphanedUnder(afterStop, 2, firstDaemon);
orphanedUnder(afterStop, 4, firstDaemon);
orphanedUnder(afterStop, 5, secondDaemon);
assert.deepEqual(unbound(afterStop), []);
assert.deepEqual(outcomesOf(r1).slice(2), [["deferred", "I_fixture_1"], ["unchanged", null]]);
assert.deepEqual(outcomesOf(r5), [["deferred", "I_fixture_5"], ["unchanged", null]]);
assert.deepEqual(labelled("processes", "after-stop").daemons, []);
assert.deepEqual(labelled("processes", "after-stop").processes, [], "no daemon, hook, waiter or settler outlives the run");
assert.equal(of("cleanup.kill").length, 0, "nothing was left for the runner to kill");

console.log(`Verified ${records.length} records from codex-cli ${expectedVersion}`);
console.log(drifted.length ? `Dashpot modules changed since the run: ${drifted.join(", ")}` : `Dashpot modules match the run's (${environment.dashpot.head})`);
