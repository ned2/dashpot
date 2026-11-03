// Independent verifier for a Codex 666 fresh-Worker dynamic tool and
// delegation metadata trace. Checks the recorded model requests, client tool
// calls, app-server notifications, thread reads, rollouts and hooks against
// the claims the spike makes for the pinned release, without importing the
// runner.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
//
// The runner's own scripts must match the hashes the trace records; the
// hook example it reads from the checkout may drift after the trace is
// retained, which is reported and fails only under --strict.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath, expectedVersion = "0.166.0"] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
// Every member passes, and there is at least one: a missing record never
// passes a check vacuously.
const all = (list, test, what) => { assert(list.length > 0, `${what}: none recorded`); assert(list.every(test), what); };
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "hook.mjs", "run.mjs"];
const sources = ["examples/codex-hooks.json"];
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...sources].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
const checkout = path.resolve(here, "..", "..", "..");
const drifted = sources.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `checkout sources differ from the run's: ${drifted.join(", ")}`);
assert.match(environment.binaryTarget, new RegExp(`/${expectedVersion.replaceAll(".", "\\.")}-x86_64-unknown-linux-musl/bin/codex$`));
assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "off", "on", "compaction", "resumed"]);

const tool = "fixture_lookup";
const summary = one("summary").phases;
const { off, on } = summary;
const requests = of("model.request");
const requestsFor = (label) => requests.filter((record) => record.label === label && !record.compaction);
const request = (label, step) => one("model.request", (record) => record.label === label && record.step === step && !record.compaction);
const calls = of("tool.call");
const callsFrom = (thread) => calls.filter((record) => record.thread === thread);
const events = of("rpc.event");
const activities = events.filter((record) => record.method === "item/completed" && record.item?.type === "subAgentActivity");
const activity = (thread, kind) => activities.filter((record) => record.thread === thread && record.item.kind === kind);
const turnStarted = (thread) => events.filter((record) => record.method === "turn/started" && record.thread === thread);
const read = (label) => one("thread.read", (record) => record.label === label);
const rollout = (id) => {
  const found = one("rollouts").threads.filter((thread) => thread.id === id);
  assert.equal(found.length, 1, `one rollout for ${id}`);
  return found[0];
};
const hooks = of("hook");
// What the hashed runner asked Codex for, where the trace records only the
// outcome.
const runner = readFileSync(path.join(here, "run.mjs"), "utf8");
const runnerSays = (text) => assert(runner.includes(text), `run.mjs contains ${text}`);
const markersOf = (record) => record.markers.map(([, , , marker]) => marker);
// Each Worker turn a lead turn issued, with the thread it ran on.
const children = [
  { label: "off-fresh", thread: off.fresh, lead: off.lead, leadTurn: off.leadTurn, fresh: true },
  { label: "off-full", thread: off.full, lead: off.lead, leadTurn: off.leadTurn, fresh: false },
  { label: "on-fresh", thread: on.fresh, lead: on.lead, leadTurn: on.leadTurn, fresh: true },
  { label: "on-full", thread: on.full, lead: on.lead, leadTurn: on.leadTurn, fresh: false },
  { label: "on-fresh2", thread: on.fresh, lead: on.lead, leadTurn: on.followTurn, fresh: true },
  { label: "on-fresh3", thread: on.fresh, lead: on.lead, leadTurn: on.compactedTurn, fresh: true },
  { label: "on-fresh4", thread: on.fresh, lead: on.lead, leadTurn: on.resumedTurn, fresh: true },
  { label: "on-full2", thread: on.full, lead: on.lead, leadTurn: on.resumedTurn, fresh: false },
];

check("The fixture ran every scenario with no app-server error, no approval or other server request, and no process outliving its server", () => {
  assert.equal(of("server.error").length, 0);
  assert.equal(of("server.request").length, 0);
  assert.equal(of("cleanup.kill").length, 0);
  assert.deepEqual(one("summary").processes, []);
  assert(requests.every((record) => !record.missing), "every planned non-dynamic tool was offered");
  const listed = one("hooks.list").after;
  assert.equal(listed.length, environment.hookEvents.length);
  all(listed, ([, trust, enabled]) => trust === "trusted" && enabled, "fixture hooks trusted");
  assert.deepEqual(environment.updater, { updater: { autoUpdateEnabled: false } });
  assert.deepEqual(of("server.start").map((record) => [record.server, record.args]), [["trust", []],
    ["off", ["features.multi_agent_v2_dynamic_tools=false"]], ["on", ["features.multi_agent_v2_dynamic_tools=true"]],
    ["resumed", ["features.multi_agent_v2_dynamic_tools=true"]]]);
  assert.match(environment.config, /^multi_agent_v2 = true$/m);
  assert.doesNotMatch(environment.config, /multi_agent_v2_dynamic_tools/);
  assert.deepEqual(environment.dynamicTools.map((spec) => [spec.type, spec.name]), [["function", tool]]);
  assert.match(environment.dynamicTools[0].description, /Reads and changes nothing/);
});

check("Flag off: the fresh Worker is not offered the lead's dynamic tool, its attempted call is refused inside Codex, and no call reaches the client", () => {
  all(requestsFor("off-fresh"), (record) => record.offeredTool === false, `off-fresh offered: false`);
  assert.equal(request("off-fresh", 1).lastOutput.text, `unsupported call: ${tool}`);
  assert.deepEqual(callsFrom(off.fresh), []);
});

check("Flag off: the full-history Worker is offered the tool, its call reaches the client naming the Worker's own thread and turn, and the result reaches it", () => {
  all(requestsFor("off-full"), (record) => record.offeredTool === true, `off-full offered: true`);
  const [call] = callsFrom(off.full);
  assert.equal(callsFrom(off.full).length, 1);
  assert.deepEqual([call.tool, call.probe, call.success, call.turn], [tool, "off-full", true, request("off-full", 0).turn]);
  assert.equal(request("off-full", 1).lastOutput.text, "TOOLRESULT:off-full");
});

check("Flag on: fresh and full-history Workers are both offered the tool; each call reaches the client with the Worker's own thread and turn and the result reaches it", () => {
  for (const [label, thread] of [["on-fresh", on.fresh], ["on-full", on.full]]) {
    all(requestsFor(label), (record) => record.offeredTool === true, `${label} offered: true`);
    const call = one("tool.call", (record) => record.thread === thread && record.probe === label);
    assert.deepEqual([call.tool, call.success, call.turn, call.server], [tool, true, request(label, 0).turn, "on"]);
    assert.equal(request(label, 1).lastOutput.text, `TOOLRESULT:${label}`);
  }
});

check("The lead's sentinel never reaches a fresh Worker's model requests and reaches every full-history Worker request", () => {
  for (const { label, fresh } of children) {
    all(requestsFor(label), (record) => markersOf(record).some((marker) => marker.startsWith("LEADSECRET:")) === !fresh,
      `${label} sentinel ${fresh ? "absent" : "present"}`);
  }
});

check("The lead is offered the tool and reaches the client in every phase, including after a restart whose resume named no dynamic tool", () => {
  for (const [label, thread, server] of [["off-lead", off.lead, "off"], ["on-lead", on.lead, "on"], ["on-resumed", on.lead, "resumed"]]) {
    all(requestsFor(label), (record) => record.offeredTool === true, `${label} offered: true`);
    assert.equal(one("tool.call", (record) => record.thread === thread && record.probe === label).server, server);
  }
  for (const label of ["on-follow", "on-compacted"]) all(requestsFor(label), (record) => record.offeredTool === true, `${label} offered: true`);
  runnerSays('call("thread/resume", { threadId: on.lead })');
});

check("A client denial reaches the Worker as a failed call, and the Worker's next call in the same turn succeeds", () => {
  const denied = one("tool.call", (record) => record.probe === "deny");
  assert.deepEqual([denied.thread, denied.success, denied.answered], [on.fresh, false, "TOOLDENIED:deny"]);
  assert.equal(request("on-fresh2", 1).lastOutput.text, "TOOLDENIED:deny");
  const item = one("rpc.event", (record) => record.method === "item/completed" && record.item?.type === "dynamicToolCall" && record.item.probe === "deny");
  assert.deepEqual([item.item.status, item.item.success], ["failed", false]);
  const after = one("tool.call", (record) => record.probe === "on-fresh2");
  assert.deepEqual([after.turn, after.success], [denied.turn, true]);
});

check("A follow-up keeps the fresh Worker's tool; the lead compacts in a turn of its own while a direct compaction of the Worker is refused; the tool survives on both", () => {
  all(requestsFor("on-fresh2"), (record) => record.offeredTool === true, `on-fresh2 offered: true`);
  const compactions = requests.filter((record) => record.compaction);
  assert.equal(compactions.length, 1);
  const [compaction] = compactions;
  assert.deepEqual([compaction.thread, compaction.metadata.request_kind, compaction.rootTurn], [on.lead, "compaction", compaction.turn]);
  assert(![on.leadTurn, on.followTurn, on.compactedTurn].includes(compaction.turn));
  assert(events.some((record) => record.method === "item/completed" && record.item?.type === "contextCompaction" && record.turn === compaction.turn));
  const lead = one("compact", (record) => record.label === "lead");
  assert.deepEqual([lead.done, lead.requests], [true, [compaction.receipt]]);
  const worker = one("compact", (record) => record.label === "fresh");
  assert.deepEqual([worker.done, worker.response.code], [false, -32600]);
  assert.match(worker.response.message, /not allowed for multi-agent v2 sub-agents/);
  assert(markersOf(request("on-compacted", 0)).includes("SUMMARY:on-follow"));
  all(requestsFor("on-fresh3"), (record) => record.offeredTool === true, `on-fresh3 offered: true`);
  assert.equal(one("tool.call", (record) => record.probe === "on-fresh3").thread, on.fresh);
});

check("After a restart both Workers are cold, reload on follow-up from their rollouts, keep the tool, and their calls reach the new client", () => {
  for (const label of ["on-lead-cold", "on-fresh-cold", "on-full-cold", "off-lead-cold"]) assert.equal(read(label).thread.status.type, "notLoaded", label);
  for (const [label, thread] of [["on-fresh4", on.fresh], ["on-full2", on.full]]) {
    all(requestsFor(label), (record) => record.offeredTool === true, `${label} offered: true`);
    const call = one("tool.call", (record) => record.probe === label);
    assert.deepEqual([call.thread, call.server, call.success], [thread, "resumed", true]);
  }
});

check("Each Worker's rollout records its dynamic tools: a fresh Worker's only with the flag on, a full-history Worker's in both creation records it inherits", () => {
  assert.deepEqual(rollout(off.fresh).dynamicTools, [null]);
  assert.deepEqual(rollout(on.fresh).dynamicTools, [[tool]]);
  for (const [full, lead] of [[off.full, off.lead], [on.full, on.lead]]) {
    const thread = rollout(full);
    assert.deepEqual([thread.sessionMetaCount, thread.forkedFromId, thread.dynamicTools], [2, lead, [[tool], [tool]]]);
  }
  for (const lead of [off.lead, on.lead]) assert.deepEqual(rollout(lead).dynamicTools, [[tool]]);
  assert.equal(rollout(on.lead).compacted, 1);
});

const nullFields = (item) => ["model", "reasoningEffort"].every((key) => item.keys.includes(key) && item[key] === null);
check("Live creation activity carries the resolved model and effort: the requested effort, or the model's default when none was requested", () => {
  const level = environment.fixtureCatalog.defaultReasoningLevel;
  assert.equal(level, "medium");
  for (const { lead, fresh, full } of [off, on]) {
    const started = activity(lead, "started");
    assert.deepEqual(started.map(({ item }) => [item.agentPath, item.agentThreadId, item.model, item.reasoningEffort]),
      [["/root/fresh", fresh, "fixture-v2", "low"], ["/root/full", full, "fixture-v2", level]]);
  }
  for (const phase of ["off", "on"]) {
    runnerSays(`{ spawn: ["fresh", "${phase}-fresh", "none", { reasoning_effort: "low" }] }, { spawn: ["full", "${phase}-full", "all"] }`);
  }
  // Each Worker turn's own context records the same resolved effort; the
  // lead, which requested none, records none.
  for (const { lead, fresh, full } of [off, on]) {
    all(rollout(fresh).turnContexts, (turn) => turn.effort === "low", "fresh Worker turn effort");
    all(rollout(full).turnContexts.filter((turn) => turn.turnId !== rollout(lead).turnContexts[0].turnId), (turn) => turn.effort === level, "full-history Worker turn effort");
    all(rollout(lead).turnContexts, (turn) => turn.effort === null, "lead turn effort");
  }
});

check("Interacted and completed activity, and the wait tool call item, carry model and effort keys with null values", () => {
  const others = activities.filter((record) => record.item.kind !== "started");
  assert.deepEqual([...new Set(others.map(({ item }) => item.kind))].sort(), ["completed", "interacted"]);
  for (const { item } of others) assert(nullFields(item), `${item.kind} nulls`);
  const waits = events.filter((record) => record.method === "item/completed" && record.item?.type === "collabAgentToolCall");
  assert(waits.length > 0 && waits.every(({ item }) => item.tool === "wait" && nullFields(item)));
});

check("Persisted creation activity matches the live values in thread/read on the live and the restarted server and in each lead's rollout", () => {
  const shape = (item) => [item.kind, item.agentPath, item.model, item.reasoningEffort];
  for (const [lead, labels] of [[off.lead, ["off-lead", "off-lead-cold"]], [on.lead, ["on-lead-live", "on-lead-cold", "on-lead-resumed"]]]) {
    const live = activities.filter((record) => record.thread === lead).map(({ item }) => shape(item));
    const persisted = rollout(lead).subAgentActivity;
    assert.deepEqual(persisted.map((item) => [item.kind, item.agentPath, item.model, item.reasoningEffort]), live);
    for (const item of persisted) assert(item.keys.includes("model") && item.keys.includes("reasoning_effort"));
    for (const label of labels) {
      const fromRead = read(label).thread.turns.flatMap((turn) => turn.items.filter((item) => item.type === "subAgentActivity").map(shape));
      assert.deepEqual(fromRead, live.slice(0, fromRead.length), label);
      assert(fromRead.length >= 4, label);
    }
  }
});

check("Each Worker turn's lineage names the lead turn that issued it, in every model request's metadata, as root on the wire turn, and as parent, root and initiator in the rollout", () => {
  for (const { label, thread, lead, leadTurn } of children) {
    const turn = request(label, 0).turn;
    all(requestsFor(label), (record) => record.thread === thread && record.turn === turn, `${label} requests stay in one Worker turn`);
    for (const record of requestsFor(label)) {
      assert.deepEqual([record.metadata.session_id, record.metadata.parent_thread_id, record.metadata.parent_turn_id, record.metadata.root_turn_id],
        [lead, lead, leadTurn, leadTurn], `${label} step ${record.step}`);
      assert.deepEqual([record.parentTurn, record.rootTurn], [leadTurn, leadTurn], `${label} step ${record.step}`);
    }
    assert.equal(one("rpc.event", (record) => record.method === "turn/started" && record.turn === turn).rootTurnId, leadTurn, label);
    const started = rollout(thread).turnsStarted.filter((entry) => entry.turnId === turn);
    assert.equal(started.length, 1, label);
    assert.deepEqual([started[0].rootTurnId, started[0].attribution.parent_turn_id, started[0].attribution.root_turn_id, started[0].attribution.initiating_agent_path],
      [leadTurn, leadTurn, leadTurn, "/root"], label);
  }
});

check("Each lead turn, the compaction turn included, is its own root with no parent; the compaction turn's rollout record carries no attribution", () => {
  const leadTurns = [[off.lead, off.leadTurn], [on.lead, on.leadTurn], [on.lead, on.followTurn], [on.lead, on.compactedTurn], [on.lead, on.resumedTurn]];
  for (const [lead, turn] of leadTurns) {
    const own = requests.filter((entry) => entry.turn === turn);
    assert(own.length > 0, `requests of lead turn ${turn}`);
    for (const record of own) {
      assert.equal(record.thread, lead);
      assert.equal(record.rootTurn, turn);
      assert.equal(record.metadata.parent_turn_id, undefined);
    }
    const started = rollout(lead).turnsStarted.find((entry) => entry.turnId === turn);
    assert.deepEqual([started.rootTurnId, started.attribution.parent_turn_id], [turn, null]);
  }
  for (const { lead } of [off, on]) all(turnStarted(lead), (record) => record.rootTurnId === record.turn, "lead turns are their own roots");
  const compaction = requests.find((record) => record.compaction);
  const record = rollout(on.lead).turnsStarted.find((entry) => entry.turnId === compaction.turn);
  assert.deepEqual([record.rootTurnId, record.attribution, record.keys.includes("turn_attribution")], [compaction.turn, null, false]);
});

check("Worker hooks carry the lead thread as session_id, the Worker thread as agent_id, and the Worker's own turn; follow-up turns publish SubagentStop without SubagentStart", () => {
  for (const { label, thread, lead } of children) {
    const turn = request(label, 0).turn;
    const mine = hooks.filter((record) => record.payload.turn_id === turn);
    all(mine, (record) => record.payload.session_id === lead && record.payload.agent_id === thread, `${label} hook identity`);
    const first = ["off-fresh", "off-full", "on-fresh", "on-full"].includes(label);
    assert.deepEqual(mine.map((record) => record.event), first ? ["SubagentStart", "SubagentStop"] : ["SubagentStop"], label);
  }
  assert(hooks.every((record) => ![off.fresh, off.full, on.fresh, on.full].includes(record.payload.session_id)));
  assert.deepEqual(hooks.filter((record) => record.event === "SessionStart").map((record) => [record.payload.session_id, record.payload.source]),
    [[off.lead, "startup"], [on.lead, "startup"], [on.lead, "compact"], [on.lead, "resume"]]);
  assert(hooks.every((record) => Object.keys(record.env).length === 0));
});

console.log(`Verified ${checks.length} claims against ${path.basename(tracePath)} (codex-cli ${expectedVersion}):`);
for (const claim of checks) console.log(`- ${claim}`);
if (drifted.length) console.log(`Note: checkout sources differ from the run's: ${drifted.join(", ")}`);
