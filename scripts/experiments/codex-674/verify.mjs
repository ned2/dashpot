// Independent verifier for a Codex 674 follow-up hook trace. Checks the
// recorded hooks, model requests, shells and loaded threads against the
// claims the spike makes for the pinned release, without importing the
// runner or Dashpot. With `--codex-source`, it also checks each Codex source
// fact the spike cites against a `rust-v0.166.0` checkout.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict] [--codex-source <checkout>]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const strict = argv.includes("--strict");
const sourceAt = argv.indexOf("--codex-source");
const codexSource = sourceAt >= 0 ? argv[sourceAt + 1] : null;
assert(sourceAt < 0 || (codexSource && !codexSource.startsWith("--")), "--codex-source needs a checkout path");
const positionals = argv.filter((argument, index) => !argument.startsWith("--") && !(sourceAt >= 0 && index === sourceAt + 1));
const [tracePath, expectedVersion = "0.166.0"] = positionals;
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind, predicate = () => true) => records.filter((record) => record.kind === kind && predicate(record));
const one = (kind, predicate) => {
  const found = of(kind, predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

// The trace names the exact sources that produced it, this file included.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "verify.mjs"];
const modules = ["harnesses.py", "hook_records.py", "hook_scan.py", "integrate/registry.py"].map((file) => `src/dashpot/sessions/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
assert.deepEqual(of("scenario").map((record) => record.name), ["v2-spawn", "v2-path", "v2-relative", "v2-id", "v2-evict", "v2-evicted", "v2-limit", "v2-evicted-id",
  "v2-unknown", "v2-restart", "v2-restored", "v2-restored-id", "v1-spawn", "v1-send", "v1-unknown", "v1-closed"]);

const outcome = one("outcome");
const { workerA, workerB, workerV, workerVFromSpawn } = outcome.learned;
const { v2: leadV2, v1: leadV1 } = outcome.leads;
const hooks = of("hook");
// One record per hook Codex ran without a matcher: each tool call once.
const all = hooks.filter((record) => record.tag === "all");
const lifecycle = hooks.filter((record) => record.tag === "lifecycle");
// The matched subscription `dashpot integrate codex` installs (ADR 0161),
// whose events reached Dashpot's publisher too.
const dashpotMatcher = "collaborationfollowup_task|multi_agent_v1send_input";
const dashpotMatched = hooks.filter((record) => record.tag === `dashpot:${dashpotMatcher}`);
const published = [...lifecycle, ...dashpotMatched];
const requests = of("model.request");
const calls = (tool) => requests.filter((record) => record.action === tool);
const toolHooks = (event, callId) => all.filter((record) => record.event === event && record.payload.tool_use_id === callId);
// The reply Codex gave the lead for a call: the next request that carries it.
const replyTo = (call) => requests.find((record) => record.lastCallId === call.callId)?.lastOutput;
const shell = (label) => one("command", (record) => record.label === label && record.phase === "start");
const starts = (agent, scenario) => lifecycle.filter((record) => record.event === "SubagentStart" && record.payload.agent_id === agent && (!scenario || record.scenario === scenario));
const stops = (agent, scenario) => lifecycle.filter((record) => record.event === "SubagentStop" && record.payload.agent_id === agent && record.scenario === scenario);
const residency = (label) => one("residency", (record) => record.label === label);

check("The run used the pinned release through a fixture-local symlink, with the fixture daemon's updater off, outside every harness session, no daemon started, the shared daemon directory unchanged, and every fixture hook trusted", () => {
  assert.match(environment.binaryTarget, /\/\.codex\/packages\/standalone\/releases\/0\.166\.0-[^/]+\/(bin\/)?codex$/);
  assert.equal(environment.updater.updater.autoUpdateEnabled, false);
  assert(environment.runnerAncestry.every((entry) => !entry.harness));
  assert.deepEqual(of("failure"), []);
  const shared = one("shared-daemon-dir");
  assert.deepEqual([shared.added, shared.removed], [0, 0]);
  assert(!/app-server-daemon\/releases|--managed-daemon/.test(JSON.stringify(records)));
  const listed = one("hooks.list").entries;
  assert(listed.length > 0 && listed.every((entry) => entry.trust === "trusted" && entry.enabled));
  // The bare tool names among them, so that their empty selections below
  // are a measurement and not an absent subscription.
  assert.deepEqual(environment.matchers, ["followup_task", "send_input", "collaborationfollowup_task", "multi_agent_v1send_input", "followup_task$|send_input$"]);
  for (const matcher of environment.matchers) {
    for (const event of ["preToolUse", "postToolUse"]) assert(listed.some((entry) => entry.event === event && entry.matcher === matcher && entry.tag === `matcher:${matcher}`));
  }
  // Every subscription Dashpot installs, as its example spells them.
  assert.deepEqual(environment.hooksDocument.hooks.PostToolUse.filter((group) => group.hooks[0].command.endsWith(`'dashpot:${dashpotMatcher}'`)).map((group) => group.matcher), [dashpotMatcher]);
  assert(listed.some((entry) => entry.event === "postToolUse" && entry.matcher === dashpotMatcher && entry.tag === `dashpot:${dashpotMatcher}`));
  assert(!listed.some((entry) => entry.event === "preToolUse" && entry.tag?.startsWith("dashpot:")));
});

check("No record keeps a prompt, a message or a worker's reply: none holds the fixture's `SPIKE:` or `DONE:` markers, which every prompt, task and reply carries. No record names a path outside the placeholders `$ROOT`, `$EXPERIMENT`, `$CHECKOUT` and `~`", () => {
  records.forEach((record, index) => {
    const line = JSON.stringify(record);
    assert(!/SPIKE:|DONE:/.test(line), `record ${index + 1} keeps fixture text`);
    // An agent path such as `/root/worker_a` is Codex's, not the machine's.
    assert(!/(?<![\w$~.])\/(?:home|var|tmp|usr|opt|run|mnt|srv|etc)\//.test(line), `record ${index + 1} names a machine path`);
  });
  for (const record of hooks) for (const shape of [record.toolInput, record.toolResponse]) assert(!shape?.identity || !("message" in shape.identity));
});

check("Dashpot's Codex publisher accepted every event the fixture handed it, lifecycle and matched follow-up alike, exiting 0 with nothing on stderr; no stored record holds a follow-up field", () => {
  assert(lifecycle.length > 0 && dashpotMatched.length > 0);
  for (const record of published) {
    assert.deepEqual([record.publisher.status, record.publisher.stderr, record.publisher.error], [0, "", null], `${record.event} ${record.receipt}`);
    assert(Array.isArray(record.dashpotStore), `${record.event} ${record.receipt}: a store snapshot`);
    assert(record.dashpotStore.every((stored) => stored.followUpStored === false), `${record.event} ${record.receipt}`);
  }
});

// Question 1: the lead's hooks for `followup_task`.
const followups = calls("followup_task");
const preKeys = ["session_id", "turn_id", "transcript_path", "cwd", "hook_event_name", "model", "permission_mode", "tool_name", "tool_input", "tool_use_id"];
check("Every `followup_task` call fires `PreToolUse` on the lead once, with `tool_name` `collaborationfollowup_task`, the model's call ID as `tool_use_id`, no `agent_id`, and `tool_input` `{target, message}` whose `target` is exactly what the lead wrote", () => {
  assert.equal(followups.length, 12);
  for (const call of followups) {
    const [pre] = toolHooks("PreToolUse", call.callId);
    assert.equal(toolHooks("PreToolUse", call.callId).length, 1);
    assert.equal(pre.payload.tool_name, "collaborationfollowup_task");
    assert.equal(pre.payload.session_id, leadV2);
    assert(!("agent_id" in pre.payload));
    assert.deepEqual(pre.payloadKeys, preKeys);
    assert.deepEqual(pre.toolInput.keys, ["target", "message"]);
    assert.equal(pre.toolInput.identity.target, call.target);
  }
  assert.deepEqual([...new Set(followups.map((call) => call.target))].sort(), ["/root/nobody", "/root/worker_a", "/root/worker_b", outcome.unknownId, workerA, workerB, "worker_a"].sort());
});

// The follow-ups that failed: both unknown targets, and evicted B while A
// ran the only worker turn.
const failedFollowup = (call) => call.label === "v2-unknown" || (call.label === "v2-limit" && call.target === "/root/worker_b");
const succeeded = followups.filter((call) => !failedFollowup(call));
check("A successful `followup_task` fires `PostToolUse` once, with the same `tool_use_id` and `tool_input`, `tool_response` the empty string, before the worker's turn ends", () => {
  assert.equal(succeeded.length, 9);
  for (const call of succeeded) {
    const [pre] = toolHooks("PreToolUse", call.callId);
    const posts = toolHooks("PostToolUse", call.callId);
    assert.equal(posts.length, 1, `${call.label}.${call.step} PostToolUse`);
    const [post] = posts;
    assert.deepEqual(post.payloadKeys, [...preKeys.slice(0, 9), "tool_response", "tool_use_id"]);
    assert.deepEqual(post.toolInput, pre.toolInput);
    assert.deepEqual(post.toolResponse, { type: "string", length: 0, json: null });
    assert.equal(replyTo(call), "");
    // A lead's request carries the label of the scenario it runs in.
    const stop = lifecycle.find((record) => record.event === "SubagentStop" && record.scenario === call.label && record.receipt > pre.receipt);
    assert(stop && post.receipt < stop.receipt, `${call.label}: PostToolUse before the worker's SubagentStop`);
  }
});

// Question 2: which worker the target names.
check("Dashpot's Sub-agent key is the worker's thread ID: `SubagentStart` and `SubagentStop` carry it as `agent_id`, the worker's shell holds it as `CODEX_THREAD_ID`, and a thread-ID target is that same string", () => {
  assert.equal(starts(workerA).length, 1);
  assert.equal(starts(workerA)[0].scenario, "v2-spawn");
  assert.equal(shell("wa.0").env.CODEX_THREAD_ID, workerA);
  assert.equal(shell("wb.0").env.CODEX_THREAD_ID, workerB);
  assert.equal(followups.find((call) => call.label === "v2-id").target, workerA);
});

check("A path target is not an `agent_id`. The worker transcript named by `SubagentStart`'s `transcript_path`, and by `SubagentStop`'s `agent_transcript_path`, has its thread ID in its file name and, in its session metadata, that ID and the agent path the lead spawned it at; a relative target is that path's last segment under the lead at `/root`", () => {
  for (const [agent, agentPath] of [[workerA, "/root/worker_a"], [workerB, "/root/worker_b"]]) {
    const [start] = starts(agent);
    assert.deepEqual(start.payloadKeys, ["session_id", "turn_id", "transcript_path", "cwd", "hook_event_name", "model", "permission_mode", "agent_id", "agent_type"]);
    assert.equal(start.transcript.meta.id, agent);
    assert.equal(start.transcript.meta.nameHasAgentId, true);
    assert.equal(start.transcript.meta.threadSpawn.agent_path, agentPath);
    assert.equal(start.transcript.meta.threadSpawn.parent_thread_id, leadV2);
    for (const stop of lifecycle.filter((record) => record.event === "SubagentStop" && record.payload.agent_id === agent)) {
      assert(stop.payloadKeys.includes("agent_transcript_path"));
      assert.equal(stop.transcript.meta.id, leadV2);
      assert.equal(stop.agentTranscript.meta.id, agent);
      assert.equal(stop.agentTranscript.meta.threadSpawn.agent_path, agentPath);
    }
  }
  const spawned = all.filter((record) => record.event === "PostToolUse" && record.payload.tool_name === "collaborationspawn_agent");
  assert.deepEqual(spawned.map((record) => [record.toolResponse.json.keys, record.toolResponse.json.identity.task_name]), [[["task_name"], "/root/worker_a"], [["task_name"], "/root/worker_b"]]);
  // No hook payload, of any event, carries an agent path beside an ID.
  for (const record of hooks) assert(!record.payloadKeys.some((key) => /path|task_name/.test(key) && !["transcript_path", "agent_transcript_path"].includes(key)), `hook ${record.receipt}`);
});

const followupScenarios = [["v2-path", workerA, "wa-path.0"], ["v2-relative", workerA, "wa-relative.0"], ["v2-id", workerA, "wa-id.0"],
  ["v2-evicted", workerA, "wa-evicted.0"], ["v2-limit", workerA, "wa-long.0"], ["v2-evicted-id", workerB, "wb-evicted-id.0"],
  ["v2-restored", workerB, "wb-restored.0"], ["v2-restored-id", workerA, "wa-restored-id.0"]];
check("Each successful follow-up, by absolute path, relative path or ID, ran in the worker the target names: its shell's `CODEX_THREAD_ID` and its `SubagentStop`'s `agent_id` are the thread `SubagentStart` reported at the spawn", () => {
  for (const [scenario, agent, label] of followupScenarios) {
    assert.equal(shell(label).env.CODEX_THREAD_ID, agent, scenario);
    assert.equal(stops(agent, scenario).length, 1, `${scenario}: one SubagentStop`);
  }
});

check("That holds for a worker Codex evicted, and for one restored from disk after the app-server restarted and the lead was resumed", () => {
  assert.equal(residency("v2-evicted").threads.a.loaded, false);
  assert.equal(residency("v2-reloaded").threads.a.loaded, true);
  assert.equal(residency("v2-reloaded").threads.b.loaded, false);
  assert.equal(one("thread.resume").resumed, leadV2);
  assert.deepEqual(residency("v2-resumed").loaded, [leadV2]);
  assert.equal(residency("v2-restored").threads.b.loaded, true);
  assert(of("rpc.event", (record) => record.server === "v2-second").length > 0);
  assert.equal(shell("wb-restored.0").env.CODEX_THREAD_ID, workerB);
});

check("A thread-ID target reaches an unloaded worker as a path does: evicted B, reloaded by its ID, and A, restored from disk by its ID after the restart", () => {
  assert.equal(residency("v2-limited").threads.b.loaded, false);
  assert.equal(followups.find((call) => call.label === "v2-evicted-id").target, workerB);
  assert.equal(residency("v2-reloaded-id").threads.b.loaded, true);
  assert.equal(shell("wb-evicted-id.0").env.CODEX_THREAD_ID, workerB);
  assert.equal(residency("v2-restored").threads.a.loaded, false);
  assert.equal(followups.find((call) => call.label === "v2-restored-id").target, workerA);
  assert.equal(residency("v2-restored-id").threads.a.loaded, true);
  assert.equal(shell("wa-restored-id.0").env.CODEX_THREAD_ID, workerA);
});

// Question 3: a failed `followup_task`.
const failedFollowups = followups.filter(failedFollowup);
// The hooks a failed call left: only its `PreToolUse` and the lead's own
// turn. No worker stopped in `v2-unknown`, `v1-unknown` or `v1-closed`, and
// in `v2-limit` only A did.
const workerStopsIn = (scenario) => lifecycle.filter((record) => record.event === "SubagentStop" && record.scenario === scenario).map((record) => record.payload.agent_id);
check("A failed `followup_task` fires `PreToolUse` and no other hook: no `PostToolUse`, and no worker event. That held for the unknown path, the unknown thread ID, and the follow-up to evicted B while A ran the only worker turn. The lead learns the failure only from the tool's reply", () => {
  assert.deepEqual(workerStopsIn("v2-unknown"), []);
  assert.deepEqual(workerStopsIn("v2-limit"), [workerA]);
  assert.deepEqual(lifecycle.filter((record) => record.payload.agent_id === workerB && ["v2-limit", "v2-unknown"].includes(record.scenario)), []);
  assert.deepEqual(lifecycle.filter((record) => record.payload.agent_id && record.scenario === "v2-unknown"), []);
  const expected = { "/root/nobody": "live agent path `/root/nobody` not found", [outcome.unknownId]: `agent with id ${outcome.unknownId} not found`,
    "/root/worker_b": "collab tool failed: agent thread limit reached" };
  assert.deepEqual(failedFollowups.map((call) => call.target).sort(), Object.keys(expected).sort());
  for (const call of failedFollowups) {
    assert.equal(toolHooks("PreToolUse", call.callId).length, 1);
    assert.deepEqual(hooks.filter((record) => record.event === "PostToolUse" && record.payload.tool_use_id === call.callId), []);
    assert.equal(replyTo(call), expected[call.target]);
  }
  assert.deepEqual(requests.filter((record) => record.label === "wb-limit" || record.label === "nobody"), []);
});

check("A follow-up to a worker already running its turn succeeds and joins that turn: A ran both follow-ups of `v2-limit`, and published one `SubagentStop` for them", () => {
  const busy = followups.filter((call) => call.label === "v2-limit" && call.target === "/root/worker_a");
  assert.equal(busy.length, 2);
  for (const call of busy) assert.equal(toolHooks("PostToolUse", call.callId).length, 1);
  assert(shell("wa-long.0").receipt < shell("wa-busy.0").receipt);
  assert.equal(stops(workerA, "v2-limit").length, 1);
  assert(stops(workerA, "v2-limit")[0].receipt > shell("wa-busy.0").receipt);
});

// Question 4: v1 `send_input`.
const sends = calls("send_input");
check("v1 `send_input` fires `PreToolUse` as `multi_agent_v1send_input` with `tool_input` `{target, message}`; its target must be a thread ID, the `agent_id` `spawn_agent` returned, `SubagentStart` reported and the worker's shell holds; on success `PostToolUse` follows with `tool_response` JSON `{submission_id}`", () => {
  assert.equal(workerVFromSpawn, workerV);
  assert.equal(shell("wv.0").env.CODEX_THREAD_ID, workerV);
  assert.equal(starts(workerV, "v1-spawn").length, 1);
  const spawned = all.find((record) => record.event === "PostToolUse" && record.payload.tool_name === "spawn_agent" && record.payload.session_id === leadV1);
  assert.equal(spawned.toolResponse.json.identity.agent_id, workerV);
  assert.equal(sends.length, 4);
  for (const call of sends) {
    const [pre] = toolHooks("PreToolUse", call.callId);
    assert.equal(pre.payload.tool_name, "multi_agent_v1send_input");
    assert.equal(pre.payload.session_id, leadV1);
    assert.deepEqual(pre.toolInput.keys, ["target", "message"]);
    assert.equal(pre.toolInput.identity.target, call.target);
  }
  const ok = sends.find((call) => call.label === "v1-send");
  const [post] = toolHooks("PostToolUse", ok.callId);
  assert.equal(post.toolResponse.type, "string");
  assert.deepEqual(post.toolResponse.json.keys, ["submission_id"]);
  assert.equal(shell("wv-send.0").env.CODEX_THREAD_ID, workerV);
  assert.equal(stops(workerV, "v1-send").length, 1);
});

check("A failed `send_input` fires `PreToolUse` and no other hook: no `PostToolUse`, and no worker event. That held for an unknown ID, a target that is not an ID, and the worker the lead closed", () => {
  for (const scenario of ["v1-unknown", "v1-closed"]) {
    assert.deepEqual(workerStopsIn(scenario), []);
    assert.deepEqual(lifecycle.filter((record) => record.payload.agent_id && record.scenario === scenario), []);
  }
  const failed = sends.filter((call) => call.label !== "v1-send");
  const expected = [[outcome.unknownId, `agent with id ${outcome.unknownId} not found`], ["worker_v", /^invalid agent id worker_v: /], [workerV, `agent with id ${workerV} not found`]];
  assert.equal(failed.length, expected.length);
  failed.forEach((call, index) => {
    assert.equal(call.target, expected[index][0]);
    assert.equal(toolHooks("PreToolUse", call.callId).length, 1);
    assert.deepEqual(hooks.filter((record) => record.event === "PostToolUse" && record.payload.tool_use_id === call.callId), []);
    if (typeof expected[index][1] === "string") assert.equal(replyTo(call), expected[index][1]);
    else assert.match(replyTo(call), expected[index][1]);
  });
  const close = calls("close_agent")[0];
  assert.equal(toolHooks("PostToolUse", close.callId).length, 1);
  assert(close.receipt < failed[2].receipt);
  assert.deepEqual(requests.filter((record) => record.label === "wv-closed"), []);
});

// Question 5: the follow-up turn's start.
check("No follow-up turn publishes `SubagentStart`: v2 workers A and B published one each, at the spawn, and v1 worker V one, at its spawn, though each later published a `SubagentStop` per follow-up", () => {
  assert.deepEqual(lifecycle.filter((record) => record.event === "SubagentStart").map((record) => [record.payload.agent_id, record.scenario]),
    [[workerA, "v2-spawn"], [workerB, "v2-evict"], [workerV, "v1-spawn"]]);
  for (const [scenario, agent] of [...followupScenarios.map(([scenario, agent]) => [scenario, agent]), ["v1-send", workerV]]) {
    assert.deepEqual(starts(agent, scenario), []);
    assert.equal(stops(agent, scenario).length, 1);
  }
});

check("A v1 worker's turn, spawned or resumed by `send_input`, publishes `UserPromptSubmit` carrying its `agent_id`; a v2 worker's turn publishes none", () => {
  const childPrompts = lifecycle.filter((record) => record.event === "UserPromptSubmit" && record.payload.agent_id);
  assert.deepEqual(childPrompts.map((record) => [record.payload.agent_id, record.scenario]), [[workerV, "v1-spawn"], [workerV, "v1-send"]]);
  assert(childPrompts.every((record) => record.payloadKeys.includes("agent_type")));
});

// Question 6: matchers.
check("A matcher selects these calls only by the flattened hook name: `followup_task` and `send_input` matched nothing; `collaborationfollowup_task` and `multi_agent_v1send_input` each matched every hook of its tool and nothing else; the regular expression `followup_task$|send_input$` matched both and nothing else", () => {
  const tagged = (tag) => hooks.filter((record) => record.tag === tag);
  const ofTool = (tool) => all.filter((record) => record.payload.tool_name === tool).map((record) => [record.event, record.payload.tool_use_id]).sort();
  const pairs = (list) => list.map((record) => [record.event, record.payload.tool_use_id]).sort();
  assert.deepEqual(tagged("matcher:followup_task"), []);
  assert.deepEqual(tagged("matcher:send_input"), []);
  assert.deepEqual(pairs(tagged("matcher:collaborationfollowup_task")), ofTool("collaborationfollowup_task"));
  assert.deepEqual(pairs(tagged("matcher:multi_agent_v1send_input")), ofTool("multi_agent_v1send_input"));
  assert.deepEqual(pairs(tagged("matcher:followup_task$|send_input$")), [...ofTool("collaborationfollowup_task"), ...ofTool("multi_agent_v1send_input")].sort());
  assert.equal(ofTool("collaborationfollowup_task").length, 21);
  assert.equal(ofTool("multi_agent_v1send_input").length, 5);
  // Without a matcher the same events also ran for every other tool call.
  const otherTools = new Set(all.map((record) => record.payload.tool_name));
  for (const tool of ["Bash", "collaborationspawn_agent", "collaborationwait_agent", "collaborationlist_agents", "spawn_agent", "multi_agent_v1wait_agent", "multi_agent_v1close_agent"]) {
    assert(otherTools.has(tool), tool);
  }
});

// Dashpot's own subscription and what its publisher made of it (ADR 0161).
const listing = (record, session) => record.dashpotStore.find((stored) => stored.sessionId === session);
check("Dashpot's matched subscription, the joined exact names, ran once for each accepted follow-up and `send_input`, on `PostToolUse` alone, and for no other tool call", () => {
  const accepted = all.filter((record) => record.event === "PostToolUse" && ["collaborationfollowup_task", "multi_agent_v1send_input"].includes(record.payload.tool_name));
  assert.equal(accepted.length, succeeded.length + 1);
  assert.deepEqual(dashpotMatched.map((record) => record.payload.tool_use_id).sort(), accepted.map((record) => record.payload.tool_use_id).sort());
  assert(dashpotMatched.every((record) => record.event === "PostToolUse"));
});

const byId = [["v2-id", leadV2, workerA], ["v2-evicted-id", leadV2, workerB], ["v2-restored-id", leadV2, workerA], ["v1-send", leadV1, workerV]];
check("Dashpot listed the worker an ID-addressed follow-up named, resident, evicted or restored, v2 or v1, from the lead's `PostToolUse` until that worker's `SubagentStop`, which ended the listing; the lead's record was the one that listed it", () => {
  for (const [scenario, lead, worker] of byId) {
    const [post] = dashpotMatched.filter((record) => record.scenario === scenario);
    assert.equal(dashpotMatched.filter((record) => record.scenario === scenario).length, 1, scenario);
    assert.equal(post.payload.session_id, lead);
    assert(listing(post, lead).liveSubagents.includes(worker), `${scenario}: listed after the follow-up`);
    const [stop] = stops(worker, scenario);
    assert(stop.receipt > post.receipt);
    assert(!listing(stop, lead).liveSubagents.includes(worker), `${scenario}: unlisted at its stop`);
  }
});

const byPath = ["v2-path", "v2-relative", "v2-evicted", "v2-limit", "v2-restored"];
check("A follow-up addressed by path listed nothing: at each such `PostToolUse` the lead's record listed no Sub-agent", () => {
  const pathed = dashpotMatched.filter((record) => byPath.includes(record.scenario));
  assert.equal(pathed.length, 6);
  for (const record of pathed) assert.deepEqual(listing(record, leadV2).liveSubagents, [], `${record.scenario} ${record.receipt}`);
});

check("A worker's own tool calls fire `PreToolUse` and `PostToolUse` with its `agent_id`, under the lead's `session_id`", () => {
  const workerTools = all.filter((record) => record.payload.agent_id);
  assert(workerTools.length > 0);
  assert(workerTools.every((record) => record.payload.tool_name === "Bash" && [leadV2, leadV1].includes(record.payload.session_id)));
  // Each worker call fired both, once, with the same `agent_id`.
  const byCall = Map.groupBy(workerTools, (record) => record.payload.tool_use_id);
  for (const [callId, list] of byCall) {
    assert.deepEqual(list.map((record) => record.event), ["PreToolUse", "PostToolUse"], callId);
    assert.equal(new Set(list.map((record) => record.payload.agent_id)).size, 1, callId);
  }
  // Every worker shell the fixture ran was such a call.
  assert.equal(byCall.size, of("command", (record) => record.phase === "start").length);
  assert(workerTools.some((record) => record.payload.agent_id === workerA && record.scenario === "v2-evicted"));
});

// Source facts the spike cites, at rust-v0.166.0.
if (codexSource) {
  const commit = execFileSync("git", ["-C", codexSource, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  assert.equal(commit, "6ff1e1ca3b30fc8b914720681fcf5fe62e95f856", "the rust-v0.166.0 commit");
  const source = (file) => readFileSync(path.join(codexSource, "codex-rs", file), "utf8");
  // Each pattern is matched in the file the spike cites, not at its line.
  check("Source: `PostToolUse` runs only for a call whose result is a success; the hook name joins a tool's namespace and name with nothing between, except `spawn_agent`'s, bare both without a namespace and in `multi_agent_v1`; a matcher of letters, digits, `_` and `|` is a set of exact names, an empty one or `*` matches every tool, and any other is an unanchored regular expression", () => {
    const registry = source("core/src/tools/registry.rs");
    assert.match(registry, /let post_tool_use_payload = if success \{/);
    assert.match(registry, /Err\(_\) => false,/);
    assert.match(registry, /fn function_hook_tool_name\(invocation: &ToolInvocation\) -> HookToolName \{\s*if invocation\.tool_name\.name == "spawn_agent"\s*&& \(invocation\.tool_name\.is_default_namespace\(\)\s*\|\| invocation\.tool_name\.namespace\.as_deref\(\) == Some\(MULTI_AGENT_V1_NAMESPACE\)\)\s*\{\s*return HookToolName::spawn_agent\(\);\s*\}\s*HookToolName::new\(flat_tool_name\(&invocation\.tool_name\)\.into_owned\(\)\)/);
    const flat = source("core/src/tools/mod.rs");
    assert.match(flat, /name\.push_str\(namespace\);\s*name\.push_str\(&tool_name\.name\);/);
    const matcher = source("hooks/src/engine/matcher.rs");
    assert.match(matcher, /if pattern\.is_empty\(\) \|\| pattern == "\*" \{\s*Ok\(Self::All/);
    assert.match(matcher, /ch\.is_ascii_alphanumeric\(\) \|\| ch == '_' \|\| ch == '\|'\)\s*\{\s*Ok\(Self::Exact/);
    assert.match(matcher, /\} else \{\s*regex::Regex::new\(pattern\)\.map\(Self::Regex\)/);
    assert.match(matcher, /pattern\.split\('\|'\)\.any\(\|candidate\| candidate == input\)/);
    assert.match(matcher, /Self::Regex\(regex\) => input\.is_some_and\(\|input\| regex\.is_match\(input\)\)/);
  });
  check("Source: v2 tools sit in the `collaboration` namespace and v1 tools in `multi_agent_v1`; a v2 target that parses as a thread ID is taken as one, and any other is an agent path, absolute when it starts with `/` and otherwise appended to the caller's path, `/root` for a root lead; `send_input` takes only a thread ID; `agents.max_threads` N gives v2 a session limit of N + 1, so N workers", () => {
    assert.match(source("core/src/config/mod.rs"), /DEFAULT_MULTI_AGENT_V2_TOOL_NAMESPACE: &str = "collaboration"/);
    assert.match(source("core/src/config/mod.rs"), /\.map\(\|max_threads\| max_threads\.saturating_add\(1\)\)/);
    assert.match(source("core/src/tools/handlers/multi_agents_spec.rs"), /MULTI_AGENT_V1_NAMESPACE: &str = "multi_agent_v1"/);
    const api = source("core/src/agent/control/api.rs");
    assert.match(api, /if let Ok\(thread_id\) = ThreadId::from_string\(target\) \{\s*return Ok\(thread_id\);/);
    const target = source("core/src/agent/control/target.rs");
    assert.match(target, /let current_agent_path = current_session_source\s*\.get_agent_path\(\)\s*\.unwrap_or_else\(AgentPath::root\);/);
    assert.match(target, /let agent_path = current_agent_path\s*\.resolve\(agent_reference\)/);
    assert.match(target, /live agent path `\{\}` not found/);
    const agentPath = source("protocol/src/agent_path.rs");
    assert.match(agentPath, /if reference\.starts_with\('\/'\) \{\s*return Self::try_from\(reference\);\s*\}/);
    assert.match(agentPath, /Self::from_string\(format!\("\{self\}\/\{reference\}"\)\)/);
    assert.match(source("core/src/tools/handlers/multi_agents/send_input.rs"), /parse_agent_id_target\(&args\.target\)/);
    assert.match(source("core/src/tools/handlers/multi_agents_v2/message_tool.rs"), /Ok\(FunctionToolOutput::from_text\(String::new\(\), Some\(true\)\)\)/);
  });
  check("Source: a thread ID parses as a UUID does, so its simple, hyphenated, braced and `urn:uuid:` spellings name one thread, which Codex displays hyphenated", () => {
    const threadId = source("protocol/src/thread_id.rs");
    assert.match(threadId, /pub fn from_string\(s: &str\) -> Result<Self, uuid::Error> \{\s*Ok\(Self \{\s*uuid: Uuid::parse_str\(s\)\?,/);
    assert.match(threadId, /impl Display for ThreadId \{\s*fn fmt\(&self, f: &mut std::fmt::Formatter<'_>\) -> std::fmt::Result \{\s*Display::fmt\(&self\.uuid, f\)/);
  });
} else {
  console.log("Codex source facts not checked: pass --codex-source <rust-v0.166.0 checkout>.");
}

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
