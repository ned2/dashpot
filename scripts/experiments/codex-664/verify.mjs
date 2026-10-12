// Independent verifier for a Codex 664 Worker mail and follow-up trace.
// Checks the recorded model requests, hooks, protocol replies, loaded
// threads and Dashpot's own views against the claims the spike makes for the
// pinned release, without importing the runner or Dashpot.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath, expectedVersion = "0.162.0"] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const outcome = (name) => one(`${name}.outcome`);
const view = (label) => one("dashpot.view", (record) => record.label === label);
const residency = (label) => one("residency", (record) => record.label === label);
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const threadOf = (label) => shell(label).env.CODEX_THREAD_ID;
const requests = of("model.request");
const requestsFor = (label) => requests.filter((record) => record.label === label);
const request = (label, step) => one("model.request", (record) => record.label === label && record.step === step);
const hooks = of("hook");
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
// The workers a `list_agents` reply names, with their status.
const listed = (record) => Object.fromEntries((parseJson(record.lastOutput)?.agents ?? []).map((agent) => [agent.agent_name, agent.agent_status]));
// The reply to step `step` of a plan, which the next request carries.
const reply = (label, step) => request(label, step + 1).lastOutput;
// Markers delivered as messages, in input order, one entry per item: a
// tool call or its output is the sender's own record, not delivery.
const delivered = (record) => record.markers.filter(([, type]) => !/_call(_output)?$/.test(type ?? "")).map(([, , , marker]) => marker);
const count = (list, marker) => list.filter((found) => found === marker).length;
const finalsFrom = (record, author) => record.agentMessages.filter(([, from, , text]) => from === author && text.includes("FINAL_ANSWER"))
  .map(([, , , text]) => text.split("Payload:").at(-1).trim());
const hooksFor = (agent) => hooks.filter((record) => record.payload.agent_id === agent);
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

// The trace names the exact sources that produced it, this file included.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs", "verify.mjs"];
const modules = ["deferred_end.py", "harnesses.py", "hook_publish.py", "hook_records.py", "hook_scan.py", "processes.py", "work.py", "work_reconciliation.py", "working_directories.py"]
  .map((file) => `src/dashpot/sessions/${file}`).concat(["src/dashpot/repository/cleanup/obstacles.py"]);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.match(environment.binaryTarget, new RegExp(`/${expectedVersion.replaceAll(".", "\\.")}-x86_64-unknown-linux-musl/bin/codex$`));
assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "daemon", "local-eviction", "lead-unload", "daemon-restart", "daemon-stop"]);

check("Every hook reached Dashpot's real publisher, which exited 0; the fixture model answered every request; no fixture process outlived the daemon's stop", () => {
  assert(hooks.length > 0);
  for (const record of hooks) assert.equal(record.publisher.status, 0, `${record.event} publisher status`);
  assert.equal(of("server.error").length, 0);
  assert(requests.every((record) => !record.missing), "every planned tool was offered");
  assert.equal(of("cleanup.kill").length, 0);
  assert.deepEqual(one("processes", (record) => record.label === "after-daemon-stop").processes, []);
});

const lead = one("thread.start", (record) => record.name === "lead-l").thread.id;
const workerA = threadOf("wa.0");
const workerF = threadOf("wf.0");
const [workerB, workerC, workerD] = ["wb.0", "wc.0", "wd.0"].map(threadOf);
const workersL = { a: workerA, f: workerF, b: workerB, c: workerC, d: workerD };
const loadedWorkers = (label) => Object.entries(workersL).filter(([, id]) => residency(label).loaded.includes(id)).map(([name]) => name).sort();

// Capacity: residency counts loaded workers, finished ones included, and
// evicts a finished one on demand; running workers cannot be evicted.
check("Capacity: three running workers fill the default residency; finished A and F are evicted to make room, though each holds unread queue-only mail, a fourth spawn while three run is refused, and a follow-up to evicted A finds no slot either", () => {
  assert.deepEqual(loadedWorkers("l-spawned"), ["a", "f"]);
  assert.deepEqual(loadedWorkers("l-pre"), ["a", "f"]);
  assert.deepEqual(["wb", "wc", "wd"].map((child, index) => parseJson(reply("l-fill", index))?.task_name), ["/root/worker_b", "/root/worker_c", "/root/worker_d"]);
  assert.deepEqual(listed(request("l-fill", 4)), { "/root": "running", "/root/worker_b": "running", "/root/worker_c": "running", "/root/worker_d": "running" });
  assert.equal(reply("l-fill", 4), "collab spawn failed: agent thread limit reached");
  assert.equal(of("command").some((record) => record.label.startsWith("we.")), false, "E never ran");
  assert.match(reply("l-fill", 5), /agent thread limit reached/);
  assert.deepEqual(loadedWorkers("l-filled"), ["b", "c", "d"]);
  for (const name of ["a", "f"]) assert.deepEqual(residency("l-filled").threads[name].status, { type: "notLoaded" });
});

check("Queue-only mail to a finished, resident worker only queues: neither A nor F ran a turn, and every `send_message` reply is empty", () => {
  assert.deepEqual(outcome("l-pre").requestsA, []);
  assert.deepEqual(outcome("l-pre").requestsF, []);
  for (const label of ["l-pre", "l-post"]) for (const step of [0, 1, 2]) assert.equal(reply(label, step), "");
  for (const label of ["r-pre", "r-post", "s-pre", "s-post"]) assert.equal(reply(label, 0), "");
  assert.equal(reply("r-cold", 1), "");
  assert.equal(reply("s-cold", 1), "");
});

check("Queue-only mail to a locally evicted worker neither reloads nor starts it: with every slot free, A and F stayed unloaded, made no model request, and published no hook", () => {
  assert.deepEqual(loadedWorkers("l-filled-stopped"), ["b", "c", "d"]);
  assert.deepEqual(loadedWorkers("l-post"), ["b", "c", "d"]);
  assert.deepEqual(outcome("l-post").requestsA, []);
  assert.deepEqual(outcome("l-post").requestsF, []);
  assert.deepEqual(outcome("l-fill").requestsA, []);
  const firstStop = (agent) => hooksFor(agent).find((record) => record.event === "SubagentStop").receiptTime;
  const followAt = one("turn.start", (record) => record.label === "SPIKE:l-follow").receiptTime;
  for (const agent of [workerA, workerF]) assert.deepEqual(hooksFor(agent).filter((record) => record.receiptTime > firstStop(agent) && record.receiptTime < followAt), []);
  assert.deepEqual(listed(request("l-post", 4)), { "/root": "running", "/root/worker_b": { completed: "DONE:wb" }, "/root/worker_c": { completed: "DONE:wc" }, "/root/worker_d": { completed: "DONE:wd" } });
});

check("`followup_task` reloads an evicted worker into the least recently used finished worker's slot: A took B's, then F took C's", () => {
  assert.deepEqual(loadedWorkers("l-follow-a-running"), ["a", "c", "d"]);
  assert.deepEqual(residency("l-follow-a-running").threads.a.status.type, "active");
  assert.deepEqual(loadedWorkers("l-followed"), ["a", "d", "f"]);
  assert.deepEqual(listed(request("l-follow", 5)), { "/root": "running", "/root/worker_a": { completed: "DONE:wa2" }, "/root/worker_d": { completed: "DONE:wd" }, "/root/worker_f": { completed: "DONE:wf2" } });
});

check("Mail held across local eviction reaches the reloaded worker in order, exactly once, ahead of the follow-up task; the refused follow-up never arrives", () => {
  const firstA = request("wa2", 0);
  assert.equal(firstA.thread, workerA);
  assert.deepEqual(delivered(firstA), ["SPIKE:wa", "DONE:wa", "NOTE:a-pre1", "NOTE:a-pre2", "NOTE:a-post1", "NOTE:a-post2", "SPIKE:wa2"]);
  const kinds = firstA.agentMessages.map(([, from, to, text]) => [from, to, text.split("\n")[0], text.match(/(SPIKE|NOTE):[a-z0-9-]+/)?.[0]]);
  assert.deepEqual(kinds, [["/root", "/root/worker_a", "Message Type: NEW_TASK", "SPIKE:wa"], ...["a-pre1", "a-pre2", "a-post1", "a-post2"].map((note) => ["/root", "/root/worker_a", "Message Type: MESSAGE", `NOTE:${note}`]),
    ["/root", "/root/worker_a", "Message Type: NEW_TASK", "SPIKE:wa2"]]);
  const firstF = request("wf2", 0);
  assert.equal(firstF.thread, workerF);
  assert.deepEqual(delivered(firstF).slice(-5), ["SPIKE:wf", "DONE:wf", "NOTE:f-pre1", "NOTE:f-post1", "SPIKE:wf2"]);
  for (const record of requests.filter((found) => found.thread === workerA || found.thread === workerF)) {
    const markers = delivered(record);
    for (const note of ["NOTE:a-pre1", "NOTE:a-pre2", "NOTE:a-post1", "NOTE:a-post2", "NOTE:f-pre1", "NOTE:f-post1"]) assert(count(markers, note) <= 1, `${note} once in request ${record.receipt}`);
    assert.equal(count(markers, "SPIKE:wa-full"), 0);
  }
});

check("A second follow-up delivers no mail again, and the worker keeps every earlier turn", () => {
  const third = request("wa3", 0);
  assert.equal(third.thread, workerA);
  assert.deepEqual(delivered(third), ["SPIKE:wa", "DONE:wa", "NOTE:a-pre1", "NOTE:a-pre2", "NOTE:a-post1", "NOTE:a-post2", "SPIKE:wa2", "DONE:wa2", "SPIKE:wa3"]);
});

check("Context retained through eviction: A, spawned with `fork_turns: \"none\"`, holds only its own turns; F, spawned with the full history, still holds the lead's earlier prompts after reload", () => {
  for (const record of requests.filter((found) => found.thread === workerA)) assert.equal(delivered(record).some((marker) => marker.startsWith("SPIKE:l-")), false);
  assert.deepEqual(delivered(request("wf", 0)).filter((marker) => marker.startsWith("SPIKE:l-")), ["SPIKE:l-bind", "SPIKE:l-spawn"]);
  assert.deepEqual(delivered(request("wf2", 0)).filter((marker) => marker.startsWith("SPIKE:l-")), ["SPIKE:l-bind", "SPIKE:l-spawn"]);
});

check("Completion after a follow-up reaches the initiating lead: each `wait_agent` returned on completion, and the lead's history carries each FINAL_ANSWER once", () => {
  for (const step of [1, 3]) assert.deepEqual(parseJson(reply("l-follow", step)), { message: "Wait completed.", timed_out: false });
  assert.deepEqual(parseJson(reply("l-again", 1)), { message: "Wait completed.", timed_out: false });
  const last = request("l-again", 3);
  assert.deepEqual(finalsFrom(last, "/root/worker_a"), ["DONE:wa", "DONE:wa2", "DONE:wa3"]);
  assert.deepEqual(finalsFrom(last, "/root/worker_f"), ["DONE:wf", "DONE:wf2"]);
});

check("`list_agents` names only loaded workers: evicted A and F were missing from it until their follow-ups reloaded them", () => {
  assert.deepEqual(Object.keys(listed(request("l-pre", 4))).sort(), ["/root", "/root/worker_a", "/root/worker_f"]);
  assert.deepEqual(Object.keys(listed(request("l-fill", 7))).sort(), ["/root", "/root/worker_b", "/root/worker_c", "/root/worker_d"]);
  assert.deepEqual(Object.keys(listed(request("l-again", 3))).sort(), ["/root", "/root/worker_a", "/root/worker_d", "/root/worker_f"]);
});

check("Dashpot: B, C and D are listed as working, and block the linked Worktree, while they run; a followed-up worker publishes `SubagentStop` but no `SubagentStart`, so Dashpot does not list A while its follow-up runs", () => {
  const running = view("l-filled-running");
  for (const worker of [workerB, workerC, workerD]) assert(running.workShow.stdout.includes(worker), `work show names ${worker}`);
  assert.match(running.workShow.stdout, /has 3 sub-agents listed as working/);
  assert(running.otherCheck.result.obstacles.some((obstacle) => obstacle.kind === "sub-agent"));
  for (const label of ["l-filled-stopped", "l-post-idle", "l-followed"]) {
    assert.doesNotMatch(view(label).workShow.stdout, /sub-agents? listed as working/);
    assert.deepEqual(view(label).otherCheck.result.obstacles, []);
  }
  const during = view("l-follow-a-running");
  assert(shell("wa2.0").receiptTime < during.receiptTime && during.receiptTime < shell("wa2.0", "end").receiptTime, "the view was taken while A's follow-up command ran");
  assert.deepEqual(during.agentRuns.map((run) => [run.issueId, run.state]), [["I_fixture_1", "running"]]);
  assert.doesNotMatch(during.workShow.stdout, /listed as working/);
  assert.deepEqual(during.otherCheck.result.obstacles, []);
  for (const agent of [workerA, workerF]) {
    assert.deepEqual(hooksFor(agent).filter((record) => record.event === "SubagentStart").length, 1, "one SubagentStart, at the spawn");
    assert(hooksFor(agent).filter((record) => record.event === "SubagentStop").length >= 2);
    assert.equal(hooksFor(agent).some((record) => record.event === "SessionStart" || record.event === "SessionEnd"), false);
  }
});

// Lead R: mail held for an evicted worker across the lead's unload.
const leadR = outcome("lead-unload").lead;
const [r1, r2] = [outcome("lead-unload").workerR1, outcome("lead-unload").workerR2];
const statusIn = (label, id) => residency(label).loaded.includes(id);
check("Lead unload: the daemon unloads lead R about 60 s after its last client leaves while finished worker R2 stays loaded; mail held for evicted R1 is not delivered after `thread/resume`", () => {
  assert.equal(statusIn("r-before-unload", r1), false);
  assert.equal(statusIn("r-before-unload", r2), true);
  const ended = hooks.find((record) => record.event === "SessionEnd" && record.payload.session_id === leadR && record.receiptTime > outcome("lead-unload").leftAt);
  const seconds = (ended.receiptTime - outcome("lead-unload").leftAt) / 1000;
  assert(seconds > 55 && seconds < 75, `R unloaded after ${seconds} s`);
  assert.equal(statusIn("r-unloaded", leadR), false);
  assert.equal(statusIn("r-unloaded", r2), true);
  assert.equal(one("thread.resume", (record) => record.threadId === leadR).error, null);
  for (const record of requests.filter((found) => found.thread === r1)) {
    assert.equal(count(delivered(record), "NOTE:r1-pre"), 0);
    assert.equal(count(delivered(record), "NOTE:r1-post"), 0);
  }
});

check("Cold restoration: after the lead's resume, `list_agents` omits evicted R1; a queue-only message reloads it (`pending_init`) without starting a turn, and its follow-up gets that message once, then the task, with its earlier context", () => {
  assert.deepEqual(listed(request("r-cold", 1)), { "/root": "running", "/root/worker_r2": { completed: "DONE:r2" } });
  assert.deepEqual(listed(request("r-cold", 3)), { "/root": "running", "/root/worker_r1": "pending_init", "/root/worker_r2": { completed: "DONE:r2" } });
  assert.equal(statusIn("r-cold", r1), true);
  // R1 reloaded beside R2, which outlived R's unload, though R was resumed
  // with a capacity of one.
  assert.equal(statusIn("r-cold", r2), true);
  assert.deepEqual(outcome("lead-unload").coldRequestsR1, []);
  assert.deepEqual(delivered(request("r1b", 0)), ["SPIKE:r1", "DONE:r1", "NOTE:r1-cold", "SPIKE:r1b"]);
  assert.deepEqual(finalsFrom(request("r-follow", 2), "/root/worker_r1"), ["DONE:r1", "DONE:r1b"]);
});

// Lead S: the same across a daemon restart.
const leadS = outcome("daemon-restart").lead;
const s1 = outcome("daemon-restart").workerS1;
const s2 = outcome("daemon-restart").workerS2;
check("Daemon restart: the replacement daemon reloads the leads but no worker; mail held for evicted S1 is lost, a queue-only message reloads S1 without a turn, and its follow-up keeps its earlier context", () => {
  const restart = outcome("daemon-restart");
  assert.equal(restart.restart.status, 0);
  assert.notEqual(restart.newDaemon, restart.oldDaemon);
  assert.equal(statusIn("s-before-restart", s1), false);
  assert.equal(statusIn("s-before-restart", s2), true);
  const after = residency("s-restarted");
  assert(after.loaded.includes(leadS) && after.loaded.includes(lead) && after.loaded.includes(leadR), "the leads are loaded again");
  for (const worker of [s1, s2, workerA, workerD, workerF, r1, r2]) assert.equal(after.loaded.includes(worker), false);
  assert.deepEqual(listed(request("s-cold", 1)), { "/root": "running" });
  assert.deepEqual(listed(request("s-cold", 3)), { "/root": "running", "/root/worker_s1": "pending_init" });
  assert.equal(statusIn("s-cold", s1), true);
  assert.deepEqual(restart.coldRequestsS1, []);
  assert.deepEqual(delivered(request("s1b", 0)), ["SPIKE:s1", "DONE:s1", "NOTE:s1-cold", "SPIKE:s1b"]);
  for (const record of requests.filter((found) => found.thread === s1)) {
    assert.equal(count(delivered(record), "NOTE:s1-pre"), 0);
    assert.equal(count(delivered(record), "NOTE:s1-post"), 0);
  }
  assert.deepEqual(finalsFrom(request("s-follow", 2), "/root/worker_s1"), ["DONE:s1", "DONE:s1b"]);
});

check("Dashpot orphans lead L's run when the daemon restarts, as ADR 0086 decides", () => {
  assert.deepEqual(view("s-before-restart").agentRuns.filter((run) => run.issueId).map((run) => [run.issueId, run.state, run.orphaned]), [["I_fixture_1", "waiting", false]]);
  assert.deepEqual(view("s-restarted").agentRuns.filter((run) => run.issueId).map((run) => [run.issueId, run.orphaned]), [["I_fixture_1", true]]);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
