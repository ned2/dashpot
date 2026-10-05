// Independent verifier for the Issue #479 Codex trace: checks each finding
// about root-thread Workers (a detached `codex exec -C <worktree>` from a
// daemon-hosted Lead's shell) and `codex queue` as their mailbox against the
// recorded hook, command, model-request, protocol and Dashpot evidence, and
// that the trace came from the runner retained beside this file.
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
const tree = (name) => name === "main" ? "$ROOT/repository" : `$ROOT/repository.worktrees/${name}`;
const sha = (target) => createHash("sha256").update(readFileSync(target)).digest("hex");
const kind = (name) => records.filter((record) => record.kind === name);
const only = (name) => { const found = kind(name); assert.equal(found.length, 1, `exactly one ${name}`); return found[0]; };
const span = (name) => {
  const start = records.findIndex((record) => record.kind === "scenario" && record.name === name);
  assert(start >= 0, `scenario ${name}`);
  const end = records.findIndex((record, index) => index > start && record.kind === "scenario.end" && record.name === name);
  assert(end > start, `scenario ${name} ended`);
  assert.equal(records[end].ok, true, `scenario ${name}: ${records[end].error}`);
  return records.slice(start, end + 1);
};
const hooks = (scope = records) => scope.filter((record) => record.kind === "hook");
const command = (label, phase) => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const requests = (scope = records) => scope.filter((record) => record.kind === "model.request");
const snapshot = (label) => one(kind("snapshot"), (record) => record.label === label, `snapshot ${label}`);
const one = (list, predicate, what) => { const found = list.filter(predicate); assert.equal(found.length, 1, `exactly one ${what}`); return found[0]; };
const runOf = (snap, issue) => snap.agentRuns.filter((run) => run.issueId === issue);
const blockers = (snap, name, type) => snap.checks[name].blockers.filter((entry) => entry.kind === type);
const markersOf = (request) => request.markers.map((marker) => marker[3]);
const nearestCodex = (record) => record.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;

const environment = records[0];
const lead = only("launch.outcome").lead;
check("the trace is of the pinned Codex release, from the runner retained beside this verifier, on the fixture's own daemon, with every publish succeeding", () => {
  assert.equal(environment.kind, "environment");
  assert.equal(environment.version, `codex-cli ${pinned}`);
  assert.match(environment.binaryTarget, new RegExp(`/releases/${pinned.replaceAll(".", "\\.")}-[^/]+/bin/codex$`));
  for (const name of ["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"]) assert.equal(sha(path.join(here, name)), environment.sourceSHA256[name], `${name} changed since the run`);
  assert.deepEqual(only("sources.after").sourceSHA256, environment.sourceSHA256, "no source changed during the run");
  assert.deepEqual(environment.dashpot.dirtySource, [], "the run's Dashpot source was committed");
  for (const record of hooks()) assert.equal(record.publisher?.status, 0, `publisher failed at #${record.receipt}`);
  assert.deepEqual(environment.scenarios, ["launch", "lead-to-worker", "queue-busy", "queue-idle", "queue-overrides", "resume", "resume-posture", "queue-unloaded",
    "queue-cross-process", "signals", "asking-controller", "sandboxed-lead", "approve-for-me", "daemon-restart"]);
  const isolation = only("daemon.isolation");
  assert.equal(isolation.ownsFixtureHome, true);
  assert.equal(isolation.socketUnderFixture, true);
  assert.equal(isolation.settings.updater.autoUpdateEnabled, false);
  assert.match(isolation.cmdline, /^\$ROOT\/codex-home\/.* app-server --listen unix:\/\/ --managed-daemon$/);
  assert.deepEqual(only("cleanup.remaining").pids, []);
  assert.equal(only("shared-daemon-dir").removed, 0);
});
const checkoutRoot = path.resolve(here, "..", "..", "..");
const drift = Object.entries(environment.sourceSHA256).filter(([name]) => name.startsWith("src/")).filter(([name, hash]) => {
  try { return sha(path.join(checkoutRoot, name)) !== hash; } catch { return true; }
}).map(([name]) => name);
if (drift.length) {
  console.log(`note - working-tree sources changed since the run: ${drift.join(", ")}`);
  assert(!flags.has("--strict"), "sources changed under --strict");
}

const launched = only("launch.outcome");
check("launch: each detached `exec -C` Worker is a root thread of its own whose shell claims it, binds its Issue with `work start`, and is hosted by its own `exec` process", () => {
  for (const [label, thread, worktree, issue] of [["wa", launched.workerA, "a", 2], ["wb", launched.workerB, "b", 3]]) {
    const shell = command(`${label}.0`, "work");
    assert.equal(shell.cwd, tree(worktree));
    assert.equal(shell.env.CODEX_THREAD_ID, thread);
    assert.equal(shell.env.CODEX_SESSION_ID, thread, "a root claim, not a delegate");
    assert.notEqual(thread, lead);
    assert.equal(shell.work.status, 0);
    assert.match(shell.work.stdout, new RegExp(`^started work on fixture-${issue} `));
    assert.equal(nearestCodex(shell), launched.execPids[label]);
    // The `exec` process itself stays in the Lead's directory, in a session of its own.
    assert.equal(launched.exec[label].cwd, tree("main"));
    assert.equal(launched.exec[label].sid, launched.exec[label].ppid);
    const start = one(hooks(), (hook) => hook.event === "SessionStart" && hook.payload.session_id === thread && hook.payload.source === "startup", `${label} SessionStart`);
    assert.equal(start.payload.cwd, tree(worktree));
    assert.equal(nearestCodex(start), launched.execPids[label]);
  }
  assert.equal(command("wa.0", "work").env.DASHPOT_LEAD, lead, "the stamp reaches A's shell");
  assert.equal(command("wb.0", "work").env.DASHPOT_LEAD, undefined);
});
check("launch: a Worker's hook processes inherit the Lead's CODEX_THREAD_ID and CODEX_SESSION_ID, while the payload names the Worker", () => {
  for (const thread of [launched.workerA, launched.workerB]) {
    for (const hook of hooks().filter((record) => record.payload.session_id === thread && record.receipt < 100)) {
      assert.equal(hook.env.CODEX_THREAD_ID, lead);
      assert.equal(hook.env.CODEX_SESSION_ID, lead);
    }
  }
});
check("launch: Dashpot lists each Worker's run at its Worktree under its `exec` pid, and Worktree b is blocked by Worker B alone", () => {
  const held = snapshot("launch-held");
  const [runA] = runOf(held, "I_fixture_2");
  const [runB] = runOf(held, "I_fixture_3");
  assert.equal(runA.workingDirectory, tree("a"));
  assert.equal(runA.host, `codex pid ${launched.execPids.wa}`);
  assert.equal(runB.workingDirectory, tree("b"));
  assert.equal(runB.host, `codex pid ${launched.execPids.wb}`);
  assert.deepEqual(blockers(held, "b", "agent-session").flatMap((entry) => entry.sessions), [launched.workerB]);
  assert.match(blockers(held, "b", "agent-run")[0].detail, new RegExp(`codex pid ${launched.execPids.wb} is working on fixture-3`));
  const named = blockers(held, "b", "process").flatMap((entry) => entry.processes.map(([pid]) => pid));
  assert.equal(named.length, 1);
  assert.equal(held.processes.find(([pid]) => pid === named[0])[1], launched.execPids.wb, "the named process is Worker B's command");
  assert(!JSON.stringify(held.checks.b).includes(lead), "nothing in b names the Lead");
});
check("lead-to-worker: a message queued to a running `exec` Worker is accepted, never reaches its model, starts a turn that is interrupted at exit, and is gone from the store's view", () => {
  const sent = only("lead-to-worker.outcome").queue;
  assert.equal(sent.status, 0);
  assert.equal(sent.thread, launched.workerB);
  const ofB = requests().filter((record) => record.thread === launched.workerB);
  assert(ofB.length > 5);
  assert(ofB.every((record) => !markersOf(record).includes("NOTE:to-wb")), "no request of B carries the message, resumed ones included");
  const stop = hooks().find((hook) => hook.payload.session_id === launched.workerB && hook.event === "Stop");
  const interrupt = one(hooks(), (hook) => hook.payload.session_id === launched.workerB && hook.event === "Interrupt", "B's Interrupt");
  assert(interrupt.receipt > stop.receipt);
  assert.notEqual(interrupt.payload.turn_id, stop.payload.turn_id, "a second turn");
  assert(!hooks().some((hook) => hook.event === "UserPromptSubmit" && hook.payload.turn_id === interrupt.payload.turn_id), "the second turn published no UserPromptSubmit");
  const end = hooks().find((hook) => hook.payload.session_id === launched.workerB && hook.event === "SessionEnd");
  assert(end.receipt > interrupt.receipt);
});
check("queue-busy: a message queued to a busy Lead starts a new turn as soon as the busy turn completes, and that turn publishes UserPromptSubmit with the message", () => {
  const outcome = only("queue-busy.outcome");
  assert.equal(outcome.queue.status, 0);
  const completed = outcome.turns.find(([method, turn]) => method === "turn/completed" && turn === outcome.busyTurn);
  const next = outcome.turns.find(([method, turn]) => method === "turn/started" && turn !== outcome.busyTurn);
  assert(outcome.queue.endedAt < completed[3]);
  assert(next[3] >= completed[3] && next[3] - completed[3] < 1000, "the queued turn followed at once");
  const prompt = outcome.hooks.find(([, event, , turn]) => event === "UserPromptSubmit" && turn === next[1]);
  assert.deepEqual(prompt[5], ["SPIKE:l-mail-b", "NOTE:wb-done"]);
});
check("queue-idle: a message queued to an idle daemon-held Lead starts a turn within a second, with no 10 s poll", () => {
  const outcome = only("queue-idle.outcome");
  const started = outcome.turns.find(([method]) => method === "turn/started");
  assert(started[3] - outcome.queue.startedAt < 1000, `latency ${started[3] - outcome.queue.startedAt} ms`);
  const prompt = outcome.hooks.find(([, event, session]) => event === "UserPromptSubmit" && session === lead);
  assert.deepEqual(prompt[5], ["SPIKE:l-mail-a", "NOTE:wa-done"]);
  assert.equal(outcome.workers.wa.status, "0");
  assert.equal(outcome.workers.wb.status, "0");
});
check("Workers' runs end with their `exec`: neither A, which stopped its run, nor B, which did not, keeps a run after exiting", () => {
  const after = snapshot("after-wave");
  assert.deepEqual(runOf(after, "I_fixture_2"), []);
  assert.deepEqual(runOf(after, "I_fixture_3"), []);
  assert.equal(after.checks.a.removable, true);
  assert.equal(after.checks.b.removable, true);
});
check("queue-overrides: `codex queue` refuses a `-c` override, a feature flag included, while the daemon runs, and has no `--no-daemon`", () => {
  const { results, leadRequests } = only("queue-overrides.outcome");
  for (const name of ["o1", "o2"]) {
    assert.equal(results[name].status, 1);
    assert.match(results[name].stderr, /cannot queue through an embedded app server while a local app-server daemon is running/);
  }
  assert.equal(results.o3.status, 2);
  assert.match(results.o3.stderr, /unexpected argument '--no-daemon'/);
  assert.deepEqual(leadRequests, []);
});
check("resume: `cd a && exec resume` and `exec -C b resume` both resume the Worker's thread in its Worktree under a new `exec` process, where `work start` binds again", () => {
  const outcome = only("resume.outcome");
  for (const [label, thread, worktree, issue] of [["wa-r", launched.workerA, "a", 2], ["wb-r", launched.workerB, "b", 3]]) {
    assert.equal(outcome.workers[label].thread, thread);
    const start = outcome.hooks.find(([, event, session]) => event === "SessionStart" && session === thread);
    assert.equal(start[4], tree(worktree));
    const shell = command(`${label}.0`, "work");
    assert.equal(shell.cwd, tree(worktree));
    assert.equal(shell.env.CODEX_THREAD_ID, thread);
    assert.equal(shell.work.status, 0);
    assert.match(shell.work.stdout, new RegExp(`^started work on fixture-${issue} `));
    assert.notEqual(nearestCodex(shell), launched.execPids[label.slice(0, 2)]);
  }
  assert.equal(one(hooks(), (hook) => hook.event === "SessionStart" && hook.payload.session_id === launched.workerA && hook.payload.source === "resume", "A's resume").payload.cwd, tree("a"));
});
check("resume-posture: a bare `exec resume` drops the Worker's `-s workspace-write` for the configured default; `-s` before `resume` or `-c sandbox_mode` after it keeps the sandbox", () => {
  const { probes, workers, thread } = only("resume-posture.outcome");
  for (const label of ["wp", "wp-r1", "wp-r2", "wp-r3"]) assert.equal(workers[label].thread, thread);
  const sandboxed = (label) => { const [entry] = probes[label]; return entry.probe.write === "EROFS" && entry.probe.tcp === "EPERM"; };
  assert.equal(sandboxed("wp"), true);
  assert.equal(sandboxed("wp-r1"), false);
  assert.equal(probes["wp-r1"][0].probe.write, "ok");
  assert.equal(sandboxed("wp-r2"), true);
  assert.equal(sandboxed("wp-r3"), true);
});
check("queue-unloaded: a message queued to an unloaded thread is accepted but does not load it; it starts a turn only once a client resumes the thread", () => {
  const outcome = only("queue-unloaded.outcome");
  assert.equal(outcome.queue.status, 0);
  assert.equal(outcome.loadedBefore, false);
  assert.equal(outcome.loadedAfterQueue, false);
  assert.deepEqual(outcome.beforeResume, { hooks: [], requests: [] });
  assert(outcome.resumedAt - outcome.queue.endedAt > 20000);
  const [, label, at] = outcome.afterResume.requests[0];
  assert.equal(label, "u-mail");
  assert(at - outcome.resumedAt < 2000);
  assert.deepEqual(outcome.afterResume.hooks.map((entry) => entry[1]), ["SessionStart", "UserPromptSubmit", "Stop"]);
});
check("queue-cross-process: a message queued to a thread a separate app-server holds reaches it through that server's poll, within 10 s, without the daemon loading it", () => {
  const outcome = only("queue-cross-process.outcome");
  assert.equal(outcome.samples.length, 2);
  for (const sample of outcome.samples) {
    assert.equal(sample.queue.status, 0);
    assert(sample.latencyMs > 0 && sample.latencyMs <= 10500, `latency ${sample.latencyMs} ms`);
    assert.equal(sample.daemonLoaded, false);
    const prompt = sample.hooks.find((entry) => entry[1] === "UserPromptSubmit");
    assert.equal(prompt[6], outcome.serverPid, "the stdio server ran the turn");
  }
  assert(outcome.samples.some((sample) => sample.latencyMs > 1000), "not the immediate dispatch a daemon-held thread gets");
});
check("signals: SIGINT publishes Interrupt and SessionEnd and frees the Worktree; SIGTERM and SIGKILL publish nothing and leave an orphaned run blocking it", () => {
  const outcome = only("signals.outcome");
  const scope = span("signals");
  const sentAt = Math.min(...Object.values(outcome.sentAt));
  const after = (label) => hooks(scope).filter((hook) => hook.payload.session_id === outcome.threads[label] && hook.receiptTime >= sentAt).map((hook) => hook.event);
  assert.deepEqual(after("wc"), ["Interrupt", "SessionEnd"]);
  assert.deepEqual(after("wd"), []);
  assert.deepEqual(after("we"), []);
  assert.deepEqual([outcome.after.wc.status, outcome.after.wd.status, outcome.after.we.status], ["1", "143", "137"]);
  for (const label of ["wc", "wd", "we"]) assert.equal(outcome.after[label].command.alive, false, `${label}'s command ends with it`);
  const settled = snapshot("signals-settled");
  assert.equal(settled.checks.c.removable, true);
  assert.deepEqual(runOf(settled, "I_fixture_4"), []);
  for (const [name, issue] of [["d", "I_fixture_5"], ["e", "I_fixture_6"]]) {
    assert.equal(runOf(settled, issue)[0].orphaned, true);
    assert.equal(settled.checks[name].removable, false);
    assert.match(blockers(settled, name, "agent-run")[0].detail, /^Orphaned Agent Run on fixture-/);
  }
});
check("asking-controller: a pending ask is replayed with the same request to a client that later resumes the thread, and a thread whose ask is pending does not unload", () => {
  const outcome = only("asking-controller.outcome");
  const [, , , k1Item, k1Request] = outcome.asked.c3.find(([, thread]) => thread === outcome.k1);
  assert.deepEqual(outcome.asked.c4.map(([, thread, , item, request]) => [thread, item, request]), [[outcome.k1, k1Item, k1Request]]);
  const [, , , k2Item, k2Request] = outcome.asked.c3.find(([, thread]) => thread === outcome.k2);
  assert.deepEqual(outcome.asked.c5.map(([, thread, , item, request]) => [thread, item, request]), [[outcome.k2, k2Item, k2Request]]);
  assert.equal(outcome.commands.k1, true);
  assert.equal(outcome.commands.k2, false);
  assert.equal(outcome.k2EndedAt, null);
  assert.equal(outcome.k2Loaded, true);
  assert(outcome.notifications.some(([client, method, thread]) => client === "controller-4" && method === "turn/completed" && thread === outcome.k1));
});
const probeSandboxed = (probe) => {
  assert.equal(probe.write, "EROFS");
  assert.equal(probe.tcp, "EPERM");
  assert.equal(probe.daemonSocket, "EPERM");
  assert.equal(probe.unixMissing, "EPERM", "Unix sockets are refused outright");
  assert.equal(probe.sharedDaemonDir, "EACCES", "the shared daemon directory is masked");
  assert.equal(probe.codexHomeWrite, "EROFS");
};
const queueFailed = (queue) => {
  assert.equal(queue.status, 1);
  assert.match(queue.stderr, /failed to start embedded app server: Read-only file system/);
};
check("sandboxed-lead: a workspace-write Lead's shell reaches neither the daemon nor the store, so `codex queue` fails; a detached launch dies with its command; an escalated launch, once approved, runs", () => {
  const outcome = only("sandboxed-lead.outcome");
  const shell = command("s-launch.0", "end");
  assert.equal(shell.viaFile, true);
  probeSandboxed(shell.probe);
  queueFailed(shell.queue);
  assert.deepEqual(outcome.workers.wsx.eventTypes, []);
  assert.equal(outcome.workers.wsx.status, null, "the unescalated Worker's shell never finished");
  assert.deepEqual(outcome.sleeper, { started: true, alive: false });
  assert.deepEqual(outcome.asks.map(([method, , item]) => [method, item.replace(/_\d+$/, "")]), [["item/commandExecution/requestApproval", "call_s-launch_2"]]);
  assert.deepEqual(outcome.requests.filter(([, , , escalate]) => escalate).map(([, step]) => step), [2]);
  assert.equal(outcome.workers.ws.status, "0");
  const worker = command("ws.0", "end");
  probeSandboxed(worker.probe);
  assert.equal(worker.work.status, 0, "`work start` from the sandboxed Worker shell binds");
  queueFailed(worker.queue);
  assert(!requests().some((record) => ["l-mail-s", "l-mail-s0"].includes(record.label)));
});
check("approve-for-me: the Worker's shell runs in the workspace-write sandbox, binds its Issue, and cannot queue", () => {
  const outcome = only("approve-for-me.outcome");
  assert.equal(outcome.worker.status, "0");
  const shell = command("wg.0", "end");
  probeSandboxed(shell.probe);
  assert.equal(shell.work.status, 0);
  queueFailed(shell.queue);
  assert(!requests().some((record) => record.label === "l-mail-g"));
});
check("daemon-restart: the restart takes the 60 s shutdown grace, leaves the `exec` Worker running, reloads the loaded threads, and the Worker's queued message reaches the reloaded Lead at once; the Lead's run stays orphaned", () => {
  const outcome = only("daemon-restart.outcome");
  const seconds = (outcome.restart.endedAt - outcome.restart.startedAt) / 1000;
  assert.equal(outcome.restart.status, 0);
  assert(seconds > 58 && seconds < 75, `restart took ${seconds} s`);
  assert.notEqual(outcome.newDaemon, outcome.oldDaemon);
  assert.equal(outcome.workerAlive.alive, true);
  assert.deepEqual([...outcome.loadedAfter].sort(), [...outcome.loadedBefore].sort());
  assert.equal(outcome.delivered, true);
  assert.equal(outcome.resumedLead, null);
  const [, , deliveredAt] = outcome.leadRequests.find(([, label]) => label === "l-mail-f");
  assert(deliveredAt - outcome.queue.endedAt < 2000);
  const resumed = outcome.hooks.find(([, event, session]) => event === "SessionStart" && session === lead);
  assert.equal(resumed[6], outcome.newDaemon);
  const prompt = outcome.hooks.find((entry) => entry[1] === "UserPromptSubmit" && entry[2] === lead && entry[0] > resumed[0]);
  assert(prompt);
  for (const label of ["restart-after", "restart-queued", "restart-unloaded"]) {
    const [run] = runOf(snapshot(label), "I_fixture_1");
    assert.equal(run.orphaned, true, `${label}: the Lead's run is orphaned`);
    assert.equal(run.host, `codex pid ${outcome.oldDaemon}`);
  }
  const before = snapshot("restart-before");
  assert.equal(runOf(before, "I_fixture_1")[0].orphaned, false);
  assert.equal(runOf(snapshot("restart-after"), "I_fixture_7")[0].orphaned, false, "the Worker's run is untouched");
  assert.equal(snapshot("restart-queued").checks.f.removable, true);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} checks passed`);
