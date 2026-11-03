// Independent verifier for a Codex 649 goal-driven Lead trace. Checks the
// recorded model requests, app-server notifications, hooks, shells, goal
// replies and Dashpot's own views against the claims the spike makes for the
// pinned release, without importing the runner or Dashpot. With
// `--codex-source`, it also checks each Codex source fact the spike cites
// against a `rust-v0.166.0` checkout.
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
const one = (kind, predicate = () => true) => {
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
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "server", "l1-skill-goal", "l2-client-goal", "l3-unload", "l4-empty-responses", "l5-turn-error", "server-stop"]);

const requests = of("model.request");
const events = of("rpc.event");
const hooks = of("hook");
const outcome = (name) => one(`${name}.outcome`);
const view = (label) => one("dashpot.view", (record) => record.label === label);
const runFor = (label, issue) => view(label).agentRuns.filter((run) => run.issueId === issue);
const goalGet = (label) => one("goal.get", (record) => record.label === label).goal;
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const requestsOf = (thread) => requests.filter((record) => record.thread === thread);
const goalRequests = (thread) => requestsOf(thread).filter((record) => record.goalTurn);
const turnsStarted = (thread) => events.filter((record) => record.thread === thread && record.method === "turn/started");
const completed = (turn) => events.find((record) => record.method === "turn/completed" && record.turn === turn) ?? null;
const goalStatuses = (thread) => events.filter((record) => record.thread === thread && record.method === "thread/goal/updated").map((record) => record.goal.status);
const hooksOf = (thread, event) => hooks.filter((record) => record.payload.session_id === thread && record.event === event && !record.payload.agent_id);
const turnsOfRequests = (list) => [...new Set(list.map((record) => record.turn))];
const messagesIn = (record) => record.agentMessages.flatMap(([, , , markers]) => markers);
const l1 = outcome("l1");
const l2 = outcome("l2");
const l3 = outcome("l3");
const l4 = outcome("l4");
const l5 = outcome("l5");

check("The run used the pinned release through a fixture-local symlink, with the fixture daemon's updater off, every fixture hook trusted, Dashpot's real publisher succeeding for every hook, no derived entry in the shared daemon directory before or after, and no fixture process left", () => {
  assert.match(environment.binaryTarget, /\/\.codex\/packages\/standalone\/releases\/0\.166\.0-[^/]+\/(bin\/)?codex$/);
  assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
  assert.equal(environment.updater.updater.autoUpdateEnabled, false);
  assert(one("hooks.list").after.every(([, trust, enabled]) => trust === "trusted" && enabled));
  assert(hooks.length > 0 && hooks.every((record) => record.publisher.status === 0));
  assert.deepEqual(of("server.error"), []);
  assert.deepEqual(of("server.request"), []);
  assert.deepEqual(environment.ownDaemonEntriesBefore, []);
  const summary = one("summary");
  assert.deepEqual([summary.processes, summary.ownDaemonEntriesAfter], [[], []]);
  assert.deepEqual(of("cleanup.kill"), []);
});

check("Goals are on by default: the fixture configuration names no `goals` feature, and every request, the Workers' included, offers `get_goal`, `create_goal` and `update_goal`", () => {
  assert(!/\bgoals\b/.test(environment.config));
  assert(requests.length > 0 && requests.every((record) => record.goalTools.join() === "get_goal,create_goal,update_goal"));
  for (const worker of [l1.workerA, l1.workerB, l2.workerC, l3.workerD]) assert(requestsOf(worker).length > 0);
});

check("A skill's instruction reaches the model as a user message, not in its instructions, and the runtime accepts the `create_goal` the Lead makes on it: the goal is active before the Workers spawn", () => {
  const start = requests.filter((record) => record.label === "l1-start");
  assert(start.length >= 4 && start.every((record) => record.skill.inInput.length === 1 && record.skill.inInput[0][1] === "message" && record.skill.inInput[0][2] === "user" && !record.skill.inInstructions));
  const create = start.find((record) => record.action === "create_goal");
  const spawn = start.find((record) => record.action === "spawn_agent");
  const active = events.find((record) => record.thread === l1.lead && record.method === "thread/goal/updated" && record.goal.status === "active");
  assert(create.receipt < active.receipt && active.receipt < spawn.receipt);
  assert.equal(active.goal.objectiveLabel, "SPIKE:l1-goal");
  assert.match(spawn.lastOutput, /"goal":\{"threadId":"[0-9a-f-]{36}","objective":"SPIKE:l1-goal /);
});

check("With an active goal, Codex starts the next turn as soon as the Lead's turn ends: every L1 turn after its first is a `goal` turn whose input ends with Codex's continuation as a user message, the first starting while both Workers still ran", () => {
  const turns = turnsStarted(l1.lead).map((record) => record.turn);
  assert.equal(turns[0], l1.startTurn);
  assert(turns.length >= 10);
  for (const turn of turns.slice(1)) {
    const first = requests.find((record) => record.turn === turn);
    assert.equal(first.metadata.turn_trigger, "goal");
    assert.equal(first.directiveAt, first.inputItems - 1);
    assert.deepEqual(first.continuation.at(-1), [first.directiveAt, "message", "user"]);
  }
  assert(requestsOf(l1.lead).filter((record) => record.turn === l1.startTurn).every((record) => record.metadata.turn_trigger === undefined));
  const firstGoal = goalRequests(l1.lead)[0];
  assert(firstGoal.receiptTime - l1.startCompletedAt < 1000);
  assert(firstGoal.receipt < shell("wa.0", "end").receipt && firstGoal.receipt < shell("wb.0", "end").receipt);
});

check("A Worker's message and its completion start no turn: with a goal, they reached L1 inside a running goal turn's `wait_agent`, which returned early; without one, L2 made no request and started no turn after its Worker messaged and finished, and its first goal turn carried both", () => {
  const waits = goalRequests(l1.lead).filter((record) => record.phase === "workers" && record.step === 1);
  assert(waits.length >= 3);
  assert(waits.every((record) => /"message":"Wait completed\.","timed_out":false/.test(record.lastOutput)));
  const seen = waits.map(messagesIn);
  assert(seen.some((markers) => markers.at(-1) === "NOTE:wa") && seen.some((markers) => markers.at(-1) === "DONE:wa") && seen.some((markers) => markers.at(-1) === "DONE:wb"));
  assert.deepEqual([l2.idleRequests, l2.idleTurns], [[], 0]);
  assert(shell("wc.2", "end").receiptTime < l2.goalSetAt);
  const firstGoal = goalRequests(l2.lead)[0];
  assert.deepEqual(messagesIn(firstGoal), ["NOTE:wc", "DONE:wc"]);
  assert.equal(firstGoal.metadata.turn_trigger, "goal");
  assert(firstGoal.receiptTime - l2.goalSetAt < 1000);
});

check("A goal turn runs no `UserPromptSubmit` hook and one `Stop`: each of L1's, L2's and L3's goal turns has a Stop with its turn id and no UserPromptSubmit, while each Lead's first turn has both; a resumed Lead's goal turn runs `SessionStart` and no UserPromptSubmit", () => {
  for (const lead of [l1.lead, l2.lead, l3.lead]) {
    const prompts = hooksOf(lead, "UserPromptSubmit");
    assert.equal(prompts.length, 1);
    const goalTurns = turnsOfRequests(goalRequests(lead));
    assert(goalTurns.length >= 3);
    assert(!goalTurns.includes(prompts[0].payload.turn_id));
    for (const turn of goalTurns) assert.equal(hooksOf(lead, "Stop").filter((record) => record.payload.turn_id === turn).length, 1, `one Stop for goal turn ${turn}`);
  }
  assert.equal(hooksOf(l3.lead, "SessionStart").filter((record) => record.receiptTime > l3.resumedAt).length, 1);
});

check("Dashpot shows a Lead in a goal turn as `waiting` once its Workers have stopped: L1 read `running` while its Workers ran, then `waiting` while a goal turn's command ran, and L3 read `waiting` while an unsubscribed goal turn's command ran", () => {
  const running = runFor("l1-goal-turn-workers-running", "I_fixture_1");
  assert.equal(running.length, 1);
  assert.equal(running[0].state, "running");
  const during = view("l1-goal-turn-after-workers");
  const label = of("command").find((record) => record.phase === "start" && record.label.startsWith("l1-goal-t") && record.receiptTime > l1.observeSince).label;
  assert(shell(label).receipt < during.receipt && during.receipt < shell(label, "end").receipt);
  assert(hooks.filter((record) => record.event === "SubagentStop" && [l1.workerA, l1.workerB].includes(record.payload.agent_id)).every((record) => record.receipt < during.receipt));
  assert.deepEqual(runFor("l1-goal-turn-after-workers", "I_fixture_1").map((run) => run.state), ["waiting"]);
  const unsubscribed = view("l3-unsubscribed-goal-active");
  const l3Command = of("command").filter((record) => record.phase === "start" && record.label.startsWith("l3-goal-t") && record.receipt < unsubscribed.receipt).at(-1).label;
  assert(shell(l3Command, "end").receipt > unsubscribed.receipt);
  assert.deepEqual(runFor("l3-unsubscribed-goal-active", "I_fixture_2").map((run) => run.state), ["waiting"]);
});

check("Waiting with no Workers left does not block the goal: at least four L1 goal turns whose `wait_agent` timed out and whose final message was empty left it active; the model's `update_goal` to `blocked` took effect at once, and no turn started after it", () => {
  const idle = goalRequests(l1.lead).filter((record) => record.phase === "noprogress");
  const idleTurns = turnsOfRequests(idle);
  assert(idleTurns.length >= 4);
  for (const turn of idleTurns) {
    const [wait, final] = idle.filter((record) => record.turn === turn);
    assert.equal(wait.action, "wait_agent");
    assert.match(final.lastOutput, /"timed_out":true/);
    assert.equal(final.response, "empty");
  }
  assert.equal(goalGet("l1-after-no-progress").status, "active");
  const block = one("model.request", (record) => record.thread === l1.lead && record.action === "update_goal");
  assert.equal(block.phase, "block");
  const blocked = events.find((record) => record.thread === l1.lead && record.method === "thread/goal/updated" && record.goal.status === "blocked");
  assert(blocked.receipt > block.receipt);
  assert.equal(goalStatuses(l1.lead).filter((status) => status !== "active").join(), "blocked");
  assert.equal(l1.turnsAfterBlocked, 0);
  assert.equal(goalGet("l1-blocked").status, "blocked");
});

check("The runtime blocks a goal after three automatic turns with empty answers and no tool call, and at once on a turn error, whose turn runs no Stop hook", () => {
  const empty = goalRequests(l4.lead);
  assert.equal(empty.length, 3);
  assert(empty.every((record) => record.response === "empty" && record.action === null));
  assert.equal(l4.turns.length, 3);
  assert.equal(goalStatuses(l4.lead).at(-1), "blocked");
  assert(goalStatuses(l4.lead).slice(0, -1).every((status) => status === "active"));
  assert.equal(goalGet("l4-after").status, "blocked");
  assert.equal(l5.requests, 1);
  assert.equal(l5.turns.length, 1);
  assert.equal(completed(l5.turns[0]).status, "failed");
  assert.equal(goalStatuses(l5.lead).at(-1), "blocked");
  assert.deepEqual(hooksOf(l5.lead, "Stop"), []);
  assert.equal(goalGet("l5-after").status, "blocked");
});

check("An active goal keeps an unsubscribed Lead loaded and working: for 80 s after its client left, L3 stayed loaded, its goal turns kept running, and it had no SessionEnd; once the goal was paused, the app-server unloaded it about 60 s after its last turn and Dashpot ended its bound run", () => {
  assert.equal(l3.loadedPolls.length, 8);
  assert(l3.loadedPolls.every(([, loaded, , ended]) => loaded && !ended));
  assert(l3.loadedPolls.every(([, , count], index) => index === 0 || count > l3.loadedPolls[index - 1][2]));
  assert(l3.goalTurnsWhileUnsubscribed >= 10);
  const ended = one("hook", (record) => record.event === "SessionEnd" && record.payload.session_id === l3.lead && record.receiptTime < l3.resumedAt);
  const lastStop = hooksOf(l3.lead, "Stop").filter((record) => record.receiptTime < ended.receiptTime).at(-1);
  assert(lastStop.receiptTime > l3.pausedAt);
  assert(ended.receiptTime - lastStop.receiptTime > 55000 && ended.receiptTime - lastStop.receiptTime < 70000);
  assert.equal(l3.loadedAfterUnload, false);
  assert.equal(runFor("l3-unsubscribed-goal-active", "I_fixture_2").length, 1);
  assert.deepEqual(runFor("l3-unloaded", "I_fixture_2"), []);
});

check("A goal does not reload an unloaded Lead: setting L3's goal active while it was unloaded made no request, loaded nothing and ran no hook; resuming it started a goal turn at once, which Dashpot showed as a new, unbound run", () => {
  const set = one("goal.set", (record) => record.label === "l3-set-active-unloaded");
  assert.equal(set.goal.status, "active");
  assert.deepEqual(l3.afterReactivate, { requests: 0, loaded: false, sessionStarts: 0 });
  assert.equal(goalGet("l3-unloaded-reactivated").status, "active");
  assert.equal(hooks.filter((record) => record.payload.session_id === l3.lead && record.receiptTime > l3.reactivatedAt && record.receiptTime < l3.resumedAt).length, 0);
  const [first] = requestsOf(l3.lead).filter((record) => record.receiptTime > l3.resumedAt);
  assert(first.goalTurn && first.action === "update_goal" && first.receiptTime - l3.resumedAt < 3000);
  assert.equal(goalGet("l3-resumed").status, "complete");
  const resumed = view("l3-resumed").agentRuns.filter((run) => run.processOrSession.startsWith(l3.lead));
  assert.equal(resumed.length, 1);
  assert.equal(resumed[0].issueId, null);
});

// Source facts the spike cites, at rust-v0.166.0.
if (codexSource) {
  const commit = execFileSync("git", ["-C", codexSource, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  assert.equal(commit, "6ff1e1ca3b30fc8b914720681fcf5fe62e95f856", "the rust-v0.166.0 commit");
  const source = (file) => readFileSync(path.join(codexSource, "codex-rs", file), "utf8");
  // Each pattern is matched in the file the spike cites, not at its line.
  check("Source: `goals` is a stable feature on by default; an idle thread's goal continuation needs the live thread and starts a turn with trigger `goal`; the goal tools are hidden only from a review sub-agent", () => {
    assert.match(source("features/src/lib.rs"), /id: Feature::Goals,\s*key: "goals",\s*stage: Stage::Stable,\s*default_enabled: true,/);
    const runtime = source("ext/goal/src/runtime.rs");
    assert.match(runtime, /let Ok\(thread\) = thread_manager\.get_thread\(self\.inner\.thread_id\)\.await else \{\s*tracing::debug!\("skipping goal continuation because live thread is unavailable"\);\s*return Ok\(\(\)\);/);
    assert.match(runtime, /\.start_turn_if_idle\(\s*TurnInputRequest::new\(TurnInput::ResponseItem\(item\)\)\.on_start\(TurnStartOptions \{\s*turn_trigger: Some\("goal"\.to_string\(\)\),/);
    const extension = source("ext/goal/src/extension.rs");
    assert.match(extension, /fn on_thread_idle[\s\S]*?runtime\.continue_if_idle\(\)\.await/);
    assert.match(extension, /let tools_visible_for_thread = !matches!\(\s*input\.session_source,\s*SessionSource::SubAgent\(SubAgentSource::Review\)\s*\);/);
  });
  check("Source: the runtime blocks a goal on a turn error other than a usage limit, after three automatic turns with an empty answer and no activity, and after three turns whose `exec` failed with no tool succeeding; any tool outcome counts as activity; `update_goal` sets `blocked` without counting turns, and the three-turn rule is the tool's instruction to the model", () => {
    const extension = source("ext/goal/src/extension.rs");
    assert.match(extension, /CodexErrorInfo::UsageLimitExceeded => ActiveGoalStopReason::UsageLimit,[\s\S]*?_ => ActiveGoalStopReason::TurnError,/);
    const runtime = source("ext/goal/src/runtime.rs");
    assert.match(runtime, /ActiveGoalStopReason::TurnError => \{\s*\("turn-error", codex_state::ThreadGoalStatus::Blocked, None\)/);
    assert.match(runtime, /"empty-response",\s*codex_state::ThreadGoalStatus::Blocked,/);
    assert.match(runtime, /"execution-unavailable",\s*codex_state::ThreadGoalStatus::Blocked,/);
    const accounting = source("ext/goal/src/accounting.rs");
    assert.match(accounting, /let empty = automatic && !turn\.has_activity && \(turn\.empty_final \|\| interrupted\);/);
    assert.match(accounting, /\(inner\.consecutive_empty_turns >= 3\)\.then_some\(goal_id\)/);
    assert.match(accounting, /pub\(crate\) fn record_tool_outcome\([\s\S]*?inner\.consecutive_empty_turns = 0;[\s\S]*?turn\.has_activity = true;/);
    assert.match(accounting, /if tool_name\.is_default_namespace\(\) && tool_name\.name == "exec" => \{\s*turn\.failed_execution = true;/);
    assert.match(accounting, /\(inner\.consecutive_execution_failure_turns >= 3\)\.then_some\(goal_id\)/);
    const tool = source("ext/goal/src/tool.rs");
    const updateAt = tool.indexOf("async fn handle_update(");
    const update = tool.slice(updateAt, tool.indexOf("self.metrics", updateAt));
    assert(updateAt >= 0 && update.length > 0 && !/consecutive|three/.test(update));
    const spec = source("ext/goal/src/spec.rs");
    assert.match(spec, /Create a goal only when explicitly requested by the user or system\/developer instructions; do not infer goals from ordinary tasks\./);
    assert.match(spec, /Set to `blocked` only after the same blocking condition has recurred for at least three consecutive goal turns/);
    assert.match(source("ext/goal/templates/goals/continuation.md"), /A verified wait polls a specific process, session, job, or tool handle confirmed live now\./);
  });
  check("Source: only user input runs `UserPromptSubmit`; a Worker's completion does not trigger a turn and waking on agent messages is off by default; `wait_agent` waits 30 s by default, from 10 s to an hour; a resumed thread emits its idle lifecycle, which continues an active goal; the app-server unloads a thread with no subscribers once it has been inactive for `thread_unload_delay_secs`, 60 by default", () => {
    assert.match(source("core/src/hook_runtime.rs"), /pub\(crate\) async fn inspect_pending_input\([\s\S]*?match pending_input_item \{\s*TurnInput::UserInput \{ content, \.\. \} => \{\s*let request = UserPromptSubmitRequest \{/);
    assert.match(source("core/src/agent/control/completion.rs"), /\/\*trigger_turn\*\/ false,/);
    assert.match(source("features/src/lib.rs"), /id: Feature::WakeOnAgentMessages,\s*key: "wake_on_agent_messages",\s*stage: Stage::UnderDevelopment,\s*default_enabled: false,/);
    const config = source("core/src/config/mod.rs");
    assert.match(config, /DEFAULT_MULTI_AGENT_V2_MIN_WAIT_TIMEOUT_MS: i64 = 10_000;\s*pub\(crate\) const DEFAULT_MULTI_AGENT_V2_MAX_WAIT_TIMEOUT_MS: i64 = 3600 \* 1000;\s*pub\(crate\) const DEFAULT_MULTI_AGENT_V2_DEFAULT_WAIT_TIMEOUT_MS: i64 = 30_000;/);
    assert.match(config, /cfg\.thread_unload_delay_secs\.unwrap_or\(\/\*default\*\/ 60\)/);
    assert.match(source("app-server/src/request_processors/thread_processor.rs"), /\.emit_resume_goal_snapshot\(thread_id\)\s*\.await;\s*codex_thread\s*\.emit_thread_idle_lifecycle_if_idle\(ThreadIdleCause::Completed\)/);
    assert.match(source("app-server/src/request_processors/thread_lifecycle.rs"), /\(\(false, has_no_subscribers_since\), \(false, is_inactive_since\)\) => \{\s*std::cmp::max\(has_no_subscribers_since, is_inactive_since\)\.checked_add\(self\.delay\)/);
  });
} else {
  console.log("Codex source facts not checked: pass --codex-source <rust-v0.166.0 checkout>.");
}

assert(checks.length > 0, "no claim was checked");
for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
