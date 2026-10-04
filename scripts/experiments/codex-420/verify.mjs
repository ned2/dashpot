// Independent verifier for a Codex 420 worker-mechanics trace. Checks the
// recorded model requests, hooks, shells, protocol replies, and Dashpot's own
// views against the claims the spike makes for the pinned release, without
// importing the runner or Dashpot.
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
const outcome = (name) => one(`${name}.outcome`);
const view = (label) => one("dashpot.view", (record) => record.label === label);
const check = (label) => one("dashpot.worktree-check", (record) => record.label === label);
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const shellEnd = (label) => of("command").find((record) => record.label === label && record.phase === "end") ?? null;
const workOf = (label) => shell(label, "work").work;
const requests = of("model.request");
const requestsFor = (label) => requests.filter((record) => record.label === label);
const request = (label, step) => one("model.request", (record) => record.label === label && record.step === step);
const hooks = of("hook");
const hookTimes = (event, agent) => hooks.filter((record) => record.event === event && record.payload.agent_id === agent).map((record) => record.receiptTime);
const hasMarker = (record, marker) => record.markers.some(([, , , found]) => found === marker);
// A worker's final message, as the lead's history carries it.
const finalFrom = (record, author) => record.agentMessages.filter(([, from, , text]) => from === author && text.includes("Message Type: FINAL_ANSWER"))
  .map(([, , , text]) => text.split("Payload:\n").at(-1).trim());
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
// The workers a v2 `list_agents` reply names.
const listed = (record) => (parseJson(record.lastOutput)?.agents ?? []).map((agent) => agent.agent_name);
const hostOf = (record) => record.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const toolsOf = (label) => requestsFor(label).find((record) => record.tools)?.tools ?? null;
const collaboration = ["followup_task", "interrupt_agent", "list_agents", "send_message", "spawn_agent", "wait_agent"].map((name) => `collaboration/${name}`);
const multiAgentV1 = ["close_agent", "resume_agent", "send_input", "spawn_agent", "wait_agent"].map((name) => `multi_agent_v1/${name}`);
const refused = /^dashpot: no supported agent session encloses this command;.*no lifecycle hook record for Codex session ([0-9a-f-]{36}) \(from Codex environment\)/;

// The trace names the exact sources that produced it, this file included.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs", "verify.mjs"];
const modules = ["deferred_end.py", "harnesses.py", "hook_publish.py", "hook_records.py", "hook_scan.py", "processes.py", "work.py", "work_reconciliation.py"].map((file) => `src/dashpot/sessions/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
const { main, other } = environment.worktrees;
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "daemon", "skills", "launch", "collect", "wait", "resume", "wait-loop", "limit", "v1", "flag",
  "limit-raised", "agent-interrupt", "lead-interrupt", "lead-unload", "lead-delete", "daemon-stop"]);
assert(of("hooks.list")[0].after.every(([, trust]) => trust === "trusted"), "fixture hooks trusted");
assert(of("processes").every((record) => record.daemonSettings?.updater?.autoUpdateEnabled === false), "the daemon's updater stayed off");
assert.deepEqual(one("processes", (record) => record.label === "after-daemon-stop").processes, []);
assert(hooks.every((record) => record.publisher.status === 0), "every hook reached Dashpot's publisher and succeeded");

// The bundled catalog decides each real model's tool set.
const catalog = Object.fromEntries(environment.catalogSummary.map(([slug, version]) => [slug, version]));
for (const slug of ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra"]) assert.equal(catalog[slug], "v2", `${slug} is v2`);
for (const slug of ["gpt-5.6-luna", "codex-auto-review"]) assert.equal(catalog[slug], "v1", `${slug} is v1`);
assert.equal(catalog["gpt-5.5"], null);

// 8. Skill loading: a user skill is listed unless its policy disallows
// implicit invocation, and `$name` injects even a disallowed one.
const skills = outcome("skills");
assert(skills.bind.every((seen) => seen.implicitListed && !seen.explicitListed && !seen.explicitBody));
assert(skills.explicit.some((seen) => seen.explicitBody), "$fixture-explicit injected the skill body");
const workerRequests = requests.filter((record) => record.session && record.thread !== record.session);
assert(["wa", "wl", "v1a"].every((label) => workerRequests.some((record) => record.label === label)), "v2 and v1 workers made requests");
assert(workerRequests.every(({ skills: seen }) => seen.implicitListed && !seen.explicitListed && !seen.explicitBody),
  "every worker lists the model-invoked skill alone, without its body");

// 1. Launch: v2 spawns return a task path at once, the lead's turn ends
// while the workers run, and every worker shares the lead's host and root
// session.
const launch = outcome("launch");
const { lead, workerA, workerB } = launch;
assert(collaboration.every((tool) => toolsOf("a-bind").includes(tool)), "a catalog-v2 lead gets the collaboration tools");
assert.equal(request("a-launch", 1).lastOutput, `{"task_name":"/root/worker_a"}`);
assert.equal(request("a-launch", 2).lastOutput, `{"task_name":"/root/worker_b"}`);
// Timings are single samples; the bounds are looser than the spike's figures.
for (const step of [1, 2]) assert(request("a-launch", step).receiptTime - request("a-launch", step - 1).receiptTime < 1000, "each spawn returns at once");
assert(launch.leadStoppedAt - request("a-launch", 0).receiptTime < 2000, "the lead's turn ends right after its spawns");
for (const worker of [workerA, workerB]) {
  const [started] = hookTimes("SubagentStart", worker);
  const [stoppedAt] = hookTimes("SubagentStop", worker);
  assert(started && stoppedAt - launch.leadStoppedAt > 5000, "each worker outlives the lead's launch turn");
  assert(hooks.filter((record) => record.payload.agent_id === worker).every((record) => record.payload.session_id === lead && record.payload.cwd === main),
    "worker hooks carry the root session and the lead's directory");
}
for (const label of ["wa.0", "wb.0"]) {
  const record = shell(label);
  assert.equal(record.env.CODEX_SESSION_ID, lead, `${label} names the root session`);
  assert.notEqual(record.env.CODEX_THREAD_ID, lead, `${label} names its own thread`);
}
const shellHosts = new Set(of("command").filter((record) => record.phase === "start").map(hostOf));
assert(shellHosts.size === 1 && !shellHosts.has(null), "every lead and worker shell runs under the daemon's one Host Process");
assert(collaboration.every((tool) => toolsOf("wa").includes(tool)), "a v2 worker on a v2 model gets the collaboration tools");
assert.deepEqual(outcome("limit").started, [true, true, false, false, true]);
for (const step of [3, 4]) assert.match(request("a-limit", step).lastOutput, /agent thread limit reached/);
assert.deepEqual(outcome("limit-raised").started, [true, true, true, true, true], "agents.max_threads = 5 admits five workers");
// v1 and the feature flag.
const v1 = outcome("v1");
assert(multiAgentV1.every((tool) => toolsOf("v1-launch").includes(tool)), "an uncatalogued model gets the v1 tools");
assert.match(request("v1-launch", 1).lastOutput, /^\{"agent_id":"[0-9a-f-]{36}","nickname":"[^"]+"\}$/);
assert(!toolsOf("v1a").some((tool) => tool.startsWith("multi_agent_v1/")), "a v1 worker gets no multi-agent tools");
const prompted = new Set(hooks.filter((record) => record.event === "UserPromptSubmit" && record.payload.agent_id).map((record) => record.payload.agent_id));
assert.deepEqual([...prompted], [v1.worker], "only the v1 worker's turns fire UserPromptSubmit");
assert(collaboration.every((tool) => toolsOf("f-launch").includes(tool)), "features.multi_agent_v2 gives the lead v2");
assert(!toolsOf("fc").some((tool) => tool.startsWith("collaboration/")), "the flag does not reach a worker on a non-v2 model");

// 2. Mid-flight report: queue-only, so an idle lead is not woken; a
// waiting lead's `wait_agent` returns on each message.
assert.deepEqual(launch.leadRequestsAfterStop, [], "the idle lead made no request while its workers messaged and finished");
assert.deepEqual(launch.leadNotificationsAfterStop.filter(([method]) => method === "turn/started"), []);
assert.equal(request("wa", 3).action, "send_message");
const loop = outcome("wait-loop");
// Wait k is issued by request k and answered in request k + 1.
assert.deepEqual(loop.requests.map(([, , action]) => action), ["spawn_agent", "wait_agent", "wait_agent", "wait_agent", "wait_agent", "list_agents", null]);
const issuedAt = (k) => loop.requests[k][1];
const answeredAt = (k) => loop.requests[k + 1][1];
const answer = (k) => loop.requests[k + 1][3];
const sendTimes = loop.workerRequests.filter(([, , action]) => action === "send_message").map(([, time]) => time);
assert.equal(sendTimes.length, 2);
const [loopStopped] = hookTimes("SubagentStop", loop.worker);
assert(answeredAt(1) >= sendTimes[0] && answeredAt(1) - sendTimes[0] < 2000, "the first wait returns on the worker's first message");
assert(answeredAt(2) >= sendTimes[1] && answeredAt(2) - sendTimes[1] < 2000, "the second wait returns on the worker's second message");
assert(answeredAt(3) - loopStopped > -1000 && answeredAt(3) - loopStopped < 2000, "the third wait returns on the worker's completion");
assert(answeredAt(4) - issuedAt(4) >= 9500, "the last wait runs to its timeout");
assert.equal(answer(1), `{"message":"Wait completed.\\n\\nRequested timeout of 5000ms was clamped to the minimum of 10000ms.","timed_out":false}`);
for (const k of [2, 3]) assert.equal(answer(k), `{"message":"Wait completed.","timed_out":false}`);
assert.equal(answer(4), `{"message":"Wait timed out.","timed_out":true}`);
assert(hasMarker(request("a-loop", 2), "NOTE:wl1"), "the message is in the lead's history once the wait returns");
assert(request("a-loop", 2).agentMessages.some(([, from, to, text]) => from === "/root/worker_l" && to === "/root" && text.startsWith("Message Type: MESSAGE") && text.includes("NOTE:wl1")),
  "a message reaches the lead as an agent_message item");
const wcSent = request("wc", 1);
assert.equal(wcSent.action, "send_message");
assert(shell("a-wait.1").receiptTime < wcSent.receiptTime && wcSent.receiptTime < shellEnd("a-wait.1").receiptTime, "worker C messaged while the lead ran a command");
assert(!hasMarker(request("a-wait", 1), "NOTE:wc") && hasMarker(request("a-wait", 2), "NOTE:wc"), "the busy lead saw the message at its next request");
assert(request("v1a", 1).missing, "a v1 worker has no tool to message its lead");

// 3. Completion: Codex starts no lead turn; the final message reaches a v2
// lead's history as a FINAL_ANSWER item, and `list_agents` reports it.
assert.deepEqual(request("a-collect", 0).agentMessages, [], "the first request after the workers finished did not yet carry their results");
assert.deepEqual(finalFrom(request("a-wait", 0), "/root/worker_a"), ["DONE:wa"]);
assert.deepEqual(finalFrom(request("a-wait", 0), "/root/worker_b"), ["DONE:wb"]);
assert.deepEqual(finalFrom(request("a-wait", 3), "/root/worker_c"), ["DONE:wc"]);
assert.match(request("a-loop", 6).lastOutput, /"agent_name":"\/root\/worker_l","agent_status":\{"completed":"DONE:wl"\}/);
assert(listed(request("a-loop", 6)).includes("/root/worker_a"));
assert(!listed(request("a-limit-again", 2)).includes("/root/worker_a") && !outcome("limit").loaded.includes(workerA), "an unloaded worker leaves list_agents");
assert(hasMarker(request("v1-collect", 0), "DONE:v1a"), "v1 injects the worker's result into the lead's history");
assert.match(request("v1-resume", 2).lastOutput, /"completed":"DONE:v1a2"/);

// 4. Resume: `followup_task` (v2) and `send_input` (v1) restart a finished
// worker with its context; a v2 `send_message` does not.
const resume = outcome("resume");
const wa2 = request("wa2", 0);
assert(["SPIKE:wa", "NOTE:wa", "DONE:wa"].every((marker) => hasMarker(wa2, marker)), "the follow-up turn keeps the worker's earlier context");
assert.equal(wa2.thread, workerA);
assert.equal(hookTimes("SubagentStop", workerA).length, 2, "worker A stops once per task");
assert.deepEqual(resume.requestsB, [], "a queued message does not restart a finished worker");
const v1a2 = request("v1a2", 0);
assert.equal(v1a2.thread, v1.worker);
assert(hasMarker(v1a2, "DONE:v1a"));

// 5. Shared Agent Session: Dashpot refuses `work start`, `relocate`, and
// `stop` from a worker's shell as no session, naming the worker's thread.
for (const [label, worker] of [["wa.0", workerA], ["wb.0", workerB], ["wa.1", workerA], ["we.0", outcome("agent-interrupt").worker]]) {
  const work = workOf(label);
  assert.equal(work.status, 2, `${label} refused`);
  assert.equal(work.stderr.match(refused)?.[1], worker, `${label} refused for the worker's own thread`);
}
assert.deepEqual(workOf("wa.0").args, ["work", "start", "2"]);
assert.deepEqual(workOf("wb.0").args, ["work", "start", "2"]);
assert.deepEqual(workOf("wa.1").args, ["work", "relocate", "."]);
assert.deepEqual(workOf("we.0").args, ["work", "stop"]);
assert.equal(workOf("wa.2").stdout, "no active Issue work at this worktree\n");
assert.match(workOf("wb.1").stdout, /^codex pid \d+: fixture-1 \(I_fixture_1\) since .*\n {2}codex pid \d+ has 2 sub-agents listed as working \([0-9a-f-]{36}, [0-9a-f-]{36}\)\. Dashpot lists a sub-agent until Codex reports that it stopped, which an interrupted one may never do, so if none is still working, end that session's client \(a daemon-hosted thread ends about 60 s after its last client leaves\)\n$/);
// `work show` lists the Worktree's runs whatever the session: a worker of the
// v1 lead, which holds no run, prints the main lead's.
assert.match(workOf("v1a2.0").stdout, /^codex pid \d+: fixture-1 \(I_fixture_1\) since \S+\n$/);
const leadRun = (label) => view(label).agentRuns.find((run) => run.issueId === "I_fixture_1");
assert.equal(leadRun("launch-workers-running").state, "running");
assert.equal(leadRun("launch-workers-stopped").state, "waiting");
assert(leadRun("after-agent-interrupt"), "a worker's refused stop left the lead's run in place");
assert(check("launch-workers-running-other").result.obstacles.some((obstacle) => obstacle.kind === "sub-agent"));
assert.equal(check("launch-workers-stopped-other").result.removable, true);

// 6. Location: a worker starts in the lead's directory and moves only by a
// per-command `cd`; hooks and thread/read keep the lead's directory.
assert.equal(shell("wa.0").cwd, other);
assert.equal(shell("wb.0").cwd, main);
assert.equal(launch.workerARead.cwd, main);
assert.equal(shell("wa2.0").cwd, other);
assert.equal(shell("wa2.1").cwd, main, "the next command without cd starts in the lead's directory");

// 7. Interruption.
const cut = outcome("agent-interrupt");
assert.equal(request("a-cut", 3).lastOutput, `{"previous_status":"running"}`);
assert(shellEnd("we.1") && shellEnd("we.1").receiptTime - cut.cutAt > 10000, "the interrupted worker's command ran on");
assert.deepEqual(hookTimes("SubagentStop", cut.worker), [], "an interrupted worker publishes no SubagentStop");
assert(check("after-agent-interrupt-fourth").result.obstacles.some((obstacle) => obstacle.kind === "sub-agent" && obstacle.detail.includes(cut.worker)));
const leadInterrupt = outcome("lead-interrupt");
assert.equal(leadInterrupt.status, "interrupted");
assert(hookTimes("SubagentStop", leadInterrupt.worker)[0] - leadInterrupt.interruptedAt > 5000, "interrupting the lead leaves its worker running");
assert(hooks.some((record) => record.event === "Interrupt" && record.payload.session_id === leadInterrupt.lead));
assert.deepEqual(request("m-after", 0).agentMessages, [], "the worker's result did not reach the interrupted lead's history");
assert.match(request("m-after", 1).lastOutput, /"agent_name":"\/root\/worker_f","agent_status":\{"completed":"DONE:wf"\}/);
const unload = outcome("lead-unload");
const unloadEnded = hooks.find((record) => record.event === "SessionEnd" && record.payload.session_id === unload.lead).receiptTime;
const runOfN = (label) => view(label).agentRuns.find((run) => run.issueId === "I_fixture_3") ?? null;
const blocksForG = (label) => check(label).result.obstacles.some((obstacle) => obstacle.kind === "sub-agent" && obstacle.detail.includes(unload.worker));
assert.equal(runOfN("lead-unload-bound")?.state, "running", "lead N's run is running while worker G works");
assert(blocksForG("lead-unload-bound-fourth"), "worker G blocks Cleanup while its lead is loaded");
assert(unloadEnded - unload.leftAt > 55000 && unloadEnded - unload.leftAt < 70000, "the daemon unloads the lead about 60 s after its last client leaves");
assert(runOfN("lead-unload-first") && unload.settlerSeen, "SessionEnd defers lead N's run to a settler");
assert.equal(runOfN("lead-unload-settled"), null, "the settler ended lead N's run");
assert(!blocksForG("lead-unload-settled-fourth"), "nothing blocks Cleanup for worker G once the run has ended");
assert(unload.workingAtSettle && unload.shells.at(-1).ended > unload.settledAt, "worker G was still working when its run ended");
assert(unload.shells.at(-1).started > unloadEnded, "the worker kept working after its lead unloaded");
const [unloadStopped] = hookTimes("SubagentStop", unload.worker);
assert(unloadStopped > unload.settledAt, "worker G's SubagentStop came after its run had ended");
const eventsOfN = one("dashpot.events").events.filter((event) => event["event.name"] === "hook.outcome" && event["dashpot.agent_session.id"] === unload.lead);
const changes = (event) => eventsOfN.filter((record) => record["dashpot.hook.event"] === event).map((record) => record["dashpot.work_store.change"]);
assert.deepEqual(changes("SessionEnd"), ["deferred", "ended"], "the SessionEnd hook deferred, then its settler ended, lead N's run");
assert.equal(changes("SubagentStop").at(-1), "unchanged", "the late SubagentStop changed nothing");
const deleted = outcome("lead-delete");
assert.match(deleted.afterDelete.lead.error.message, /^thread not loaded/);
assert.match(deleted.afterDelete.worker.error.message, /^thread not loaded/);
assert.equal(deleted.shell.ended, null, "deleting the lead ended its worker's command");
assert.deepEqual(hookTimes("SubagentStop", deleted.worker), []);
// Codex runs the lead's SessionEnd before its thread/delete reply returns.
assert(hooks.some((record) => record.event === "SessionEnd" && record.payload.session_id === deleted.lead && record.receiptTime > shell("wh.0").receiptTime
  && Math.abs(record.receiptTime - deleted.deletedAt) < 5000), "deleting the lead ends its session");

console.log(JSON.stringify({ verified: tracePath, version: environment.version, drifted }));
