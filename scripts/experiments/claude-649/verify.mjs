// Independent verifier for a Claude Code 649 goal-driven lead trace. Checks
// the recorded model and evaluator requests, hooks, shells, client notices
// and Dashpot's own views against the claims the spike makes for the pinned
// release, without importing the runner or Dashpot.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const strict = argv.includes("--strict");
const [tracePath, expectedVersion = "2.1.317"] = argv.filter((argument) => !argument.startsWith("--"));
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
assert.equal(environment.version, `${expectedVersion} (Claude Code)`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "verify.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "hook_records.py", "work.py", "work_reconciliation.py"].map((file) => `src/dashpot/sessions/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.deepEqual(of("scenario").map((record) => record.name), ["c1-background-workers", "c2-never-met", "c3-check-in"]);

const hooks = of("hook");
const requests = of("model.request");
const evaluations = of("model.evaluator");
const outcome = (name) => one(`${name}.outcome`);
const c1 = outcome("c1");
const c2 = outcome("c2");
const c3 = outcome("c3");
const view = (label) => one("observation", (record) => record.label === label);
const runsOf = (label, session) => view(label).runs.filter((run) => run.issueId === "I_fixture_1" || run.processOrSession.startsWith(session));
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const leadHooks = (session, event) => hooks.filter((record) => record.payload.session_id === session && record.event === event && !record.payload.agent_id);
const evaluationsOf = (lead) => evaluations.filter((record) => record.lead === lead);
const between = (list, from, to) => list.filter((record) => record.receipt > from && record.receipt < to);
const condition = (lead) => `SPIKE:${lead}-goal`;

check("The run used the pinned release through a fixture-local symlink with its updater off, the hooks subscribed exactly as `dashpot integrate claude-code` subscribes them, Dashpot's real publisher succeeding for every hook, every lead exiting, no fixture process left, and nothing gained in the shared daemon directory", () => {
  assert.equal(environment.binaryTarget, `~/.local/share/claude/versions/${expectedVersion}`);
  assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
  assert.equal(environment.flags.DISABLE_AUTOUPDATER, "1");
  assert.equal(environment.flags.ANTHROPIC_DEFAULT_HAIKU_MODEL, "fixture-evaluator");
  assert.deepEqual([...environment.subscriptions.events].sort(), ["SessionEnd", "SessionStart", "Stop", "SubagentStart", "SubagentStop", "UserPromptSubmit"]);
  assert(hooks.length > 0 && hooks.every((record) => record.publisher.status === 0));
  assert.deepEqual(of("server.error"), []);
  assert.deepEqual(of("client.exit").map((record) => [record.name, record.status]), [["c1", 0], ["c2", 0], ["c3", 0]]);
  const summary = one("summary");
  assert.deepEqual([summary.processes, summary.daemonEntriesGained], [[], 0]);
  assert.deepEqual(of("cleanup.kill"), []);
  assert(requests.every((record) => record.available !== false), "every scripted tool was offered");
});

check("`/goal` evaluates its condition on the small fast model with no tools: each evaluator request goes to the model `ANTHROPIC_DEFAULT_HAIKU_MODEL` names, offers no tool, asks for a JSON schema with `ok`, `reason` and `impossible`, names all three answers in its system prompt, quotes the condition verbatim, and quotes the Stop hook's input, `background_tasks` included", () => {
  assert(evaluations.length >= 20);
  for (const record of evaluations) {
    assert.equal(record.tools, 0);
    assert.equal(record.format, "json_schema");
    assert.deepEqual(record.schemaKeys, ["impossible", "ok", "reason"]);
    assert.deepEqual(record.systemNamesShapes, [true, true, true]);
    assert.equal(record.conditionVerbatim, true);
    assert.equal(record.hookInput.event, "Stop");
    for (const key of ["background_tasks", "last_assistant_message", "session_id", "stop_hook_active"]) assert(record.hookInput.keys.includes(key), key);
  }
  const starts = requests.filter((record) => record.directiveKind === "goal-start");
  assert.deepEqual([...new Set(starts.map((record) => record.label))].sort(), ["c1-goal", "c2-goal", "c3-goal"]);
});

check("Claude Code defers the evaluator while a background worker runs: in C1 the goal's start turn and a notification turn each ended with a worker still running and no evaluation, and every evaluation came after the last worker had finished, with an empty `background_tasks` in the hook input", () => {
  const stops = leadHooks(c1.session, "Stop").filter((record) => record.receiptTime > c1.goalAt);
  const busy = stops.filter((record) => record.backgroundTasks.count > 0);
  assert.deepEqual(busy.map((record) => record.backgroundTasks.count), [2, 1]);
  const first = evaluationsOf("c1")[0];
  assert(busy.every((record) => record.receipt < first.receipt));
  assert(first.receipt > shell("wb", "end").receipt && first.receipt > shell("wa", "end").receipt);
  assert(evaluations.every((record) => record.hookInput.backgroundTasks === 0));
  assert.equal(view("c1-workers-running").evaluations, 0);
  assert.equal(view("c1-notification-turn").evaluations, 0);
  assert(evaluationsOf("c3").every((record) => record.receipt > shell("wd", "end").receipt));
});

check("A background worker's completion notice starts a turn that runs `UserPromptSubmit`, and Dashpot shows the lead `running` while its background workers run", () => {
  const notifications = requests.filter((record) => record.session === c1.session && record.directiveKind === "task-notification");
  assert(notifications.length >= 2);
  const notified = shell("c1-notified");
  const prompts = leadHooks(c1.session, "UserPromptSubmit");
  assert(between(prompts, shell("wa", "end").receipt, notified.receipt).length >= 1);
  assert(between(prompts, shell("wb", "end").receipt, evaluationsOf("c1")[0].receipt).length >= 1);
  for (const label of ["c1-workers-running", "c1-notification-turn"]) assert.deepEqual(runsOf(label, c1.session).map((run) => run.state), ["running"]);
  assert.deepEqual(runsOf("c3-waiting", c3.session).map((run) => run.state), ["running"]);
});

check("A \"not met\" verdict continues the turn with the evaluator's feedback as a user message, after the Stop hook has run and without `UserPromptSubmit`, so Dashpot shows the lead `waiting` while that continuation works; the Stop that ends it carries `stop_hook_active`", () => {
  const notMet = evaluationsOf("c1").find((record) => !record.verdict.ok);
  assert.equal(notMet.phase, "continue");
  const feedback = requests.find((record) => record.session === c1.session && record.directiveKind === "goal-feedback");
  assert(feedback.receipt > notMet.receipt && feedback.tool === "Bash");
  assert(of("client.synthetic", (record) => record.client === "c1").some((record) => record.opening.startsWith(`Stop hook feedback:\n[${condition("c1")} `)));
  const continuation = shell("c1-continuation");
  // The command hook's record lands just after the evaluator's request: both
  // are the same turn end's Stop hooks, run side by side.
  const stopBefore = leadHooks(c1.session, "Stop").find((record) => record.receipt > notMet.receipt);
  assert(stopBefore.receipt < feedback.receipt && stopBefore.receiptTime - notMet.receiptTime < 1000);
  assert.equal(stopBefore.payload.stop_hook_active, false);
  assert.deepEqual(between(leadHooks(c1.session, "UserPromptSubmit"), notMet.receipt, continuation.receipt), []);
  const during = view("c1-continuation-running");
  assert(continuation.receipt < during.receipt && during.receipt < shell("c1-continuation", "end").receipt);
  assert.deepEqual(runsOf("c1-continuation-running", c1.session).map((run) => run.state), ["waiting"]);
  const stopAfter = leadHooks(c1.session, "Stop").find((record) => record.receipt > continuation.receipt);
  assert.equal(stopAfter.payload.stop_hook_active, true);
});

check("A \"met\" verdict clears the goal: after it, the turn ended and a later prompt in C1 had no evaluation", () => {
  const met = evaluationsOf("c1").filter((record) => record.verdict.ok);
  assert.equal(met.length, 1);
  assert.equal(met[0].hookInput.stopHookActive, true);
  assert.deepEqual(evaluationsOf("c1").filter((record) => record.receiptTime > c1.afterMetAt), []);
  assert.equal(evaluationsOf("c1").at(-1), met[0]);
  assert(leadHooks(c1.session, "Stop").some((record) => record.receiptTime > c1.afterMetAt));
});

// Consecutive "not met" verdicts with no tool call between them, in order.
const blockRuns = (session, lead, from, to) => {
  const ordered = [...requests.filter((record) => record.session === session && record.tool), ...evaluationsOf(lead).filter((record) => !record.verdict.ok)]
    .filter((record) => record.receipt > from && record.receipt < to).sort((a, b) => a.receipt - b.receipt);
  const runs = [0];
  for (const record of ordered) { if (record.kind === "model.request") runs.push(0); else runs[runs.length - 1] += 1; }
  return runs;
};

check("A goal turn may continue past nine \"not met\" verdicts while the lead keeps calling tools, but nine in a row with no tool call make Claude Code end the turn with its block-cap notice", () => {
  const progress = of("command", (record) => record.label === "c2-progress" && record.phase === "end");
  assert.equal(progress.length, 12);
  const cap = one("client.system", (record) => record.client === "c2" && record.key === "stop-hook-block-cap");
  assert(progress.at(-1).receipt < cap.receipt);
  assert(of("client.result", (record) => record.client === "c2").every((record) => record.receipt < progress[0].receipt || record.receipt > cap.receipt));
  assert.match(cap.text, /^A hook blocked the turn from ending 9 consecutive times/);
  const goal = one("client.send", (record) => record.client === "c2" && record.text.startsWith("/goal")).receipt;
  const runs = blockRuns(c2.session, "c2", goal, cap.receipt);
  // One run per tool call, after the goal's start: one verdict after each
  // command but the last, then nine with no tool call.
  assert.equal(runs[0], 0);
  assert.equal(runs.length - 1, progress.length);
  assert(runs.slice(1, -1).every((count) => count === 1));
  assert.equal(runs.at(-1), 9);
  const ended = of("client.result", (record) => record.client === "c2" && record.receipt > cap.receipt)[0];
  assert(ended.receipt < one("client.send", (record) => record.text === "SPIKE:c2-after").receipt);
});

check("The block cap ends the turn but keeps the goal: C2's next prompt was evaluated again; an \"impossible\" verdict then cleared it, and the prompt after had no evaluation", () => {
  const verdicts = evaluationsOf("c2").filter((record) => record.receiptTime > c2.c2AfterAt && record.receiptTime < c2.finalAt);
  assert.deepEqual(verdicts.map((record) => [record.verdict.ok, record.verdict.impossible ?? false]), [[false, false], [false, true]]);
  assert.deepEqual(evaluationsOf("c2").filter((record) => record.receiptTime > c2.finalAt), []);
  assert(leadHooks(c2.session, "Stop").some((record) => record.receiptTime > c2.finalAt));
});

check("In a headless lead, a goal check-in waits for a turn to end with background work still running: with a one-minute interval, C3 made no lead request in the 80 s before its first worker finished; the notification turn that then ended with the second still running was continued by a \"Goal check-in\" user message, after its Stop hook and with no `UserPromptSubmit` or evaluation, and no further check-in came in the 30 s before the second finished", () => {
  // A worker's requests carry the lead's session; its directive is its own prompt.
  const lead = requests.filter((record) => record.session === c3.session && !["wc", "wd"].includes(record.label));
  const start = lead.filter((record) => record.directiveKind === "goal-start").at(-1);
  const firstDone = shell("wc", "end");
  const after = lead.filter((record) => record.receipt > start.receipt);
  assert(firstDone.receiptTime - start.receiptTime > 75000);
  assert(after[0].receipt > firstDone.receipt && after[0].directiveKind === "task-notification");
  const checkIns = lead.filter((record) => record.directiveKind === "other");
  assert.equal(checkIns.length, 1);
  const [checkIn] = checkIns;
  assert.match(checkIn.opening, /^Goal check-in: «SPIKE:c3-goal Every fixture Worker's pull request is open and its CI checks are green\.» is still active, and evaluation has been deferred for 1 /);
  assert(of("client.synthetic", (record) => record.client === "c3").some((record) => record.opening.startsWith("Goal check-in: «SPIKE:c3-goal ")));
  const stops = leadHooks(c3.session, "Stop");
  const ended = stops.filter((record) => record.receipt > after[0].receipt && record.receipt < checkIn.receipt);
  assert.deepEqual(ended.map((record) => [record.backgroundTasks.count, record.payload.stop_hook_active]), [[1, false]]);
  assert.deepEqual(between(leadHooks(c3.session, "UserPromptSubmit"), after[0].receipt, checkIn.receipt), []);
  const secondDone = shell("wd", "end");
  assert(checkIn.receipt < secondDone.receipt && secondDone.receiptTime - checkIn.receiptTime > 25000);
  assert.equal(stops.find((record) => record.receipt > checkIn.receipt).payload.stop_hook_active, true);
  assert.equal(evaluationsOf("c3").length, 1);
  assert(evaluationsOf("c3")[0].receipt > secondDone.receipt && evaluationsOf("c3")[0].verdict.ok);
});

check("Dashpot shows an Agent Session with no Issue Binding as an unbound run: C2 and C3 never bound an Issue", () => {
  assert.deepEqual(runsOf("c2-turn-ended", c2.session).map((run) => [run.state, run.issueId]), [["waiting", null]]);
  assert.deepEqual(runsOf("c3-goal-met", c3.session).map((run) => [run.state, run.issueId]), [["waiting", null]]);
});

assert(checks.length > 0, "no claim was checked");
for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
