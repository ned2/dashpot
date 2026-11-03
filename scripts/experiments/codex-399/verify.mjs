// Independent verifier for a Codex 399 interruption trace. Checks the
// recorded hooks, shells, model requests, rollout turn events, agent picker
// rows, thread reads and Dashpot observations against the claims the spike
// makes for the pinned release, without importing the runner or Dashpot.
// With `--codex-source`, it also checks each Codex source fact the spike
// cites against a `rust-v0.166.0` checkout.
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
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs", "verify.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "hook_records.py", "hook_scan.py", "processes.py", "session_exits.py", "work.py"].map((file) => `src/dashpot/sessions/${file}`)
  .concat(["src/dashpot/repository/cleanup/obstacles.py"]);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
// The musl standalone 0.166.0 release the spike names.
assert.equal(environment.binarySHA256, "b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8");
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "daemon-esc", "daemon-picker", "interrupt-agent", "daemon-stop", "standalone-esc", "standalone-picker"]);

const hooks = of("hook");
const requests = of("model.request");
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const signalled = (label) => of("command", (record) => record.label === label && record.phase === "signal");
const hooksOf = (predicate) => hooks.filter(predicate);
const leadHooks = (event, lead) => hooksOf((record) => record.event === event && record.payload.session_id === lead && !record.payload.agent_id);
const childHooks = (child) => hooksOf((record) => record.payload.agent_id === child);
const interruptIn = (scenario) => one("interrupt", (record) => record.scenario === scenario);
const outcomeOf = (scenario) => one(`${scenario}.outcome`);
const afterEsc = (scenario) => one("screen.after-esc", (record) => record.scenario === scenario);
const viewAt = (label) => one("dashpot.view", (record) => record.label === label);
const checkAt = (label) => one("dashpot.worktree-check", (record) => record.label === label);
const runFor = (label, issue) => (viewAt(label).agentRuns ?? []).filter((run) => run.issueId === issue);
const subagentBlockers = (label) => (checkAt(label).result?.obstacles ?? []).filter((obstacle) => obstacle.kind === "sub-agent");
const turnsOf = (outcome, thread) => outcome.rollouts[thread]?.turns ?? null;
const aborts = (outcome, thread) => turnsOf(outcome, thread).filter((turn) => turn.type === "turn_aborted");
const workOf = (label) => shell(label, "work").work;
// The reply Codex composed for a lead's call: the request that follows it.
const replyAt = (lead, step) => requests.find((record) => record.thread === lead && record.step === step && record.lastOutput !== null)?.lastOutput;

const daemonPid = one("processes", (record) => record.label === "daemon-esc-running").daemons[0];
// A child's one `SubagentStart`, before the interrupt, under the lead's
// session and with the child's own thread as `agent_id`.
const startedAsChild = (lead, child, label, interruptedAt) => {
  const started = childHooks(child).filter((record) => record.event === "SubagentStart");
  assert.equal(started.length, 1, `${child} has one SubagentStart`);
  assert.equal(started[0].payload.session_id, lead);
  assert(started[0].receiptTime < interruptedAt);
  assert.equal(shell(label).env.CODEX_THREAD_ID, child);
  assert.equal(shell(label).env.CODEX_SESSION_ID, lead);
};
// The runner wrote the window's end; the outcome record, stamped when it
// was written, shows that observation ran at least that long.
const windowObserved = (outcome) => assert(outcome.receiptTime >= outcome.windowEnd, "the outcome follows its window");

check("The run used the pinned release through a fixture-local symlink, outside every harness session, with the fixture daemon's updater off, no entry of the fixture's left in the shared daemon directory, every fixture hook trusted, every hook's publisher exiting 0, approval `never` and sandbox `danger-full-access`, and hooks reporting `bypassPermissions`", () => {
  assert.match(environment.binaryTarget, /\/\.codex\/packages\/standalone\/releases\/0\.166\.0-[^/]+\/(bin\/)?codex$/);
  assert(environment.runnerAncestry.every((entry) => !entry.harness));
  assert.equal(environment.updater.updater.autoUpdateEnabled, false);
  assert(of("processes").every((record) => record.daemonSettings.updater.autoUpdateEnabled === false));
  assert.deepEqual(of("failure"), []);
  assert.equal(one("outcome").completed, true);
  // Other processes' entries come and go there; the fixture's are named.
  const shared = one("shared-daemon-dir");
  assert.deepEqual([shared.fixtureNameKnown, shared.fixtureEntries], [true, 0]);
  const listed = one("hooks.list").after;
  assert.equal(listed.length, environment.hookEvents.length);
  assert(listed.every(([, trust, enabled]) => trust === "trusted" && enabled));
  assert(hooks.length > 0 && hooks.every((record) => record.publisher.status === 0 && record.publisher.signal === null));
  assert.match(environment.config, /^approval_policy = "never"$/m);
  assert.match(environment.config, /^sandbox_mode = "danger-full-access"$/m);
  assert.match(environment.config, /^multi_agent_v2 = true$/m);
  const modes = new Set(hooks.filter((record) => "permission_mode" in record.payload).map((record) => record.payload.permission_mode));
  assert.deepEqual([...modes], ["bypassPermissions"]);
});

check("Hosting: the three daemon scenarios' shells are children of one managed daemon, the first terminal's child, that every daemon-attached thread shares, whose control socket is bound in the shared daemon directory with its lock until the daemon stops; the standalone terminals run with no daemon and no control socket there or in the fixture, and each thread's shell is a child of its own terminal's process", () => {
  const running = one("processes", (record) => record.label === "daemon-esc-running");
  assert.equal(running.daemons.length, 1);
  assert(running.socketExists);
  const daemon = running.processes.find(([pid]) => pid === daemonPid);
  assert.match(daemon[3], / app-server .*--managed-daemon/);
  assert.equal(daemon[1], one("terminal.start", (record) => record.scenario === "daemon-esc").panePid);
  for (const label of ["de.0", "dc.0", "dp.0", "dpp.0", "dps.0", "ia.0", "iae.0"]) assert.equal(shell(label).ppid, daemonPid, `${label} runs under the daemon`);
  for (const [scenario, labels] of [["standalone-esc", ["se.0", "sex.0"]], ["standalone-picker", ["sp.0", "spq.0", "spr.0"]]]) {
    const terminal = one("terminal.start", (record) => record.scenario === scenario);
    assert(terminal.args.includes("--no-daemon"));
    for (const label of labels) assert.equal(shell(label).ppid, terminal.panePid, `${label} runs under its terminal`);
  }
  assert.deepEqual(running.fixtureShared, { socket: true, lock: true });
  assert.deepEqual(one("processes", (record) => record.label === "after-daemon-stop").fixtureShared, { socket: false, lock: false });
  const standalone = one("processes", (record) => record.label === "standalone-esc-running");
  assert.deepEqual([standalone.daemons, standalone.socketExists, standalone.fixtureShared], [[], false, { socket: false, lock: false }]);
  assert(!standalone.processes.some(([, , , cmdline]) => /--managed-daemon/.test(cmdline)));
});

// The two Esc scenarios with the lead's own thread on screen.
for (const [scenario, leadLabel, childLabel, issue] of [["daemon-esc", "de.0", "dc.0", "I_fixture_1"], ["standalone-esc", "se.0", "sex.0", "I_fixture_4"]]) {
  check(`${scenario}: with the lead's own thread on screen (\`Main [default]\`) while its turn waits, Esc publishes the lead's \`Interrupt\` and aborts only the lead's turn; the child's command runs its full hold, the child asks the model again and publishes \`SubagentStop\`, the \`sub-agent\` blocker clears and the run reads waiting`, () => {
    const interrupt = interruptIn(scenario);
    const outcome = outcomeOf(scenario);
    const lead = shell(leadLabel).env.CODEX_THREAD_ID;
    const child = shell(childLabel).env.CODEX_THREAD_ID;
    assert.deepEqual([interrupt.lead, interrupt.child, interrupt.how], [lead, child, "esc"]);
    startedAsChild(lead, child, childLabel, interrupt.receiptTime);
    windowObserved(outcome);
    assert.deepEqual([interrupt.viewing, interrupt.inputDisabled], ["Main [default]", false]);
    const screen = afterEsc(scenario);
    assert.deepEqual([screen.viewing, screen.interruptedNotice], ["Main [default]", true]);
    assert(requests.some((record) => record.thread === lead && record.action === "wait_agent" && record.receiptTime < interrupt.receiptTime));
    const interrupted = leadHooks("Interrupt", lead);
    assert.equal(interrupted.length, 1);
    assert(interrupted[0].receiptTime > interrupt.receiptTime && interrupted[0].receiptTime - interrupt.receiptTime < 5000);
    assert.deepEqual(aborts(outcome, lead).map((turn) => turn.reason), ["interrupted"]);
    assert.deepEqual(aborts(outcome, child), []);
    assert(turnsOf(outcome, child).some((turn) => turn.type === "task_complete"));
    assert.equal(outcome.rollouts[child].parent, lead);
    const start = shell(childLabel);
    const end = shell(childLabel, "end");
    assert.deepEqual(signalled(childLabel), []);
    assert(end.receiptTime > interrupt.receiptTime && end.receiptTime - start.receiptTime >= 19500);
    assert(requests.some((record) => record.thread === child && record.receiptTime > end.receiptTime));
    const stops = childHooks(child).filter((record) => record.event === "SubagentStop");
    assert.equal(stops.length, 1);
    assert(stops[0].receiptTime > end.receiptTime && stops[0].payload.session_id === lead);
    assert.deepEqual(subagentBlockers(`${scenario}-before`).map((obstacle) => [obstacle.sessionId, obstacle.agents]), [[lead, [child]]]);
    assert.deepEqual(subagentBlockers(`${scenario}-after`), []);
    assert.deepEqual(runFor(`${scenario}-before`, issue).map((run) => run.state), ["running"]);
    assert.deepEqual(runFor(`${scenario}-after`, issue).map((run) => run.state), ["waiting"]);
  });
}

check("daemon-esc: a controller's `thread/read` shows the lead and child active before Esc and idle after", () => {
  const outcome = outcomeOf("daemon-esc");
  assert.deepEqual([outcome.before.lead.status.type, outcome.before.child.status.type], ["active", "active"]);
  assert.deepEqual([outcome.after.lead.status.type, outcome.after.child.status.type], ["idle", "idle"]);
});

// The two picker scenarios: a child selected in `/subagents`, then Esc.
for (const { scenario, prefix, childName, siblingName, number, hosting } of [
  { scenario: "daemon-picker", prefix: "dp", childName: "worker_p", siblingName: "worker_s", number: 2, hosting: "daemon" },
  { scenario: "standalone-picker", prefix: "sp", childName: "worker_q", siblingName: "worker_r", number: 5, hosting: "standalone" },
]) {
  const issue = `I_fixture_${number}`;
  const childLabel = `${prefix}${childName.at(-1)}.0`;
  const siblingLabel = `${prefix}${siblingName.at(-1)}.0`;
  const siblingLast = `${prefix}${siblingName.at(-1)}.1`;
  const lead = shell(`${prefix}.0`).env.CODEX_THREAD_ID;
  const child = shell(childLabel).env.CODEX_THREAD_ID;
  const sibling = shell(siblingLabel).env.CODEX_THREAD_ID;
  const interrupt = interruptIn(scenario);
  const outcome = outcomeOf(scenario);

  check(`${scenario}: \`/subagents\` lists \`Main [default]\` (current) and each child by agent path and thread ID; choosing a child's row puts that thread on screen, its status line naming the agent path and its composer saying direct input is disabled, and Esc there shows \`Conversation interrupted\` with the child still on screen`, () => {
    const opened = one("picker.opened", (record) => record.scenario === scenario);
    assert.deepEqual(opened.rows.map((row) => [row.name, row.current, row.thread]),
      [["Main [default]", true, lead], [`/root/${childName}`, false, child], [`/root/${siblingName}`, false, sibling]]);
    assert.equal(opened.rows.find((row) => row.selected).thread, lead);
    assert.equal(one("picker.chosen", (record) => record.scenario === scenario).rows.find((row) => row.selected).thread, child);
    const selected = one("picker.selected", (record) => record.scenario === scenario);
    assert.deepEqual([selected.pickerClosed, selected.viewing, selected.inputDisabled], [true, `/root/${childName}`, true]);
    assert.deepEqual([interrupt.how, interrupt.lead, interrupt.child, interrupt.sibling, interrupt.viewing, interrupt.inputDisabled],
      ["picker-esc", lead, child, sibling, `/root/${childName}`, true]);
    const screen = afterEsc(scenario);
    assert.deepEqual([screen.viewing, screen.inputDisabled, screen.interruptedNotice], [`/root/${childName}`, true, true]);
  });

  check(`${scenario}: Esc on the selected child aborts that child's turn alone, within the lead's turn; the child's command is not signalled and runs its full hold, and after the interrupt the child asks the model nothing and publishes no hook, through at least 15 s after its command ended and to the end of the run`, () => {
    startedAsChild(lead, child, childLabel, interrupt.receiptTime);
    startedAsChild(lead, sibling, siblingLabel, interrupt.receiptTime);
    windowObserved(outcome);
    assert.deepEqual(aborts(outcome, child).map((turn) => turn.reason), ["interrupted"]);
    const leadTurn = turnsOf(outcome, lead).find((turn) => turn.type === "task_started")?.turn;
    assert(leadTurn);
    assert.equal(aborts(outcome, child)[0].rootTurn, leadTurn);
    assert.deepEqual([outcome.rollouts[child].parent, outcome.rollouts[child].agentPath], [lead, `/root/${childName}`]);
    const start = shell(childLabel);
    const end = shell(childLabel, "end");
    assert.deepEqual(signalled(childLabel), []);
    assert.equal(outcome.childEnd, end.receiptTime);
    assert(end.receiptTime > interrupt.receiptTime && end.receiptTime - start.receiptTime >= 19500);
    assert(outcome.windowEnd - end.receiptTime >= 15000);
    assert.deepEqual(requests.filter((record) => record.thread === child && record.receiptTime > interrupt.receiptTime), []);
    assert.deepEqual(childHooks(child).filter((record) => record.receiptTime > interrupt.receiptTime), []);
    assert.deepEqual(childHooks(child).filter((record) => record.event === "SubagentStop"), []);
  });

  check(`${scenario}: the lead is not interrupted — no \`Interrupt\` hook and no abort in its rollout — and its \`wait_agent\` does not return on the child's interruption: the lead's next request comes after the sibling's last command ended, with \`Wait completed.\`; \`list_agents\` then reports the child \`interrupted\` and the sibling completed, and the lead's \`Stop\` follows the sibling's \`SubagentStop\``, () => {
    assert.deepEqual(leadHooks("Interrupt", lead), []);
    assert.deepEqual(aborts(outcome, lead), []);
    const siblingEnd = shell(siblingLast, "end");
    const next = requests.filter((record) => record.thread === lead && record.receiptTime > interrupt.receiptTime);
    assert(next.length > 0 && next.every((record) => record.receiptTime > siblingEnd.receiptTime));
    assert.equal(next[0].action, "list_agents");
    assert.deepEqual(JSON.parse(next[0].lastOutput), { message: "Wait completed.", timed_out: false });
    const listed = JSON.parse(replyAt(lead, 5));
    assert.deepEqual(listed.agents.map((agent) => [agent.agent_name, typeof agent.agent_status === "string" ? agent.agent_status : Object.keys(agent.agent_status)[0]]),
      [["/root", "running"], [`/root/${childName}`, "interrupted"], [`/root/${siblingName}`, "completed"]]);
    const siblingStops = childHooks(sibling).filter((record) => record.event === "SubagentStop");
    assert.equal(siblingStops.length, 1);
    assert(siblingStops[0].receiptTime > interrupt.receiptTime);
    const stops = leadHooks("Stop", lead);
    assert.equal(stops.length, 1);
    assert(stops[0].receiptTime > siblingStops[0].receiptTime);
  });

  check(`${scenario}: Dashpot keeps the interrupted child listed — the run stays running after the lead's \`Stop\`, the \`sub-agent\` blocker names only that child after the sibling stopped, and the sibling's \`work show\` reports the session's run and both children as working`, () => {
    assert.deepEqual(runFor(`${scenario}-after`, issue).map((run) => run.state), ["running"]);
    assert.deepEqual(subagentBlockers(`${scenario}-before`).map((obstacle) => [obstacle.sessionId, [...obstacle.agents].sort()]), [[lead, [child, sibling].sort()]]);
    assert.deepEqual(subagentBlockers(`${scenario}-after`).map((obstacle) => [obstacle.sessionId, obstacle.agents]), [[lead, [child]]]);
    assert.equal(checkAt(`${scenario}-after`).result.removable, false);
    const show = workOf(siblingLast);
    assert.deepEqual(show.args, ["work", "show"]);
    assert.equal(show.status, 0);
    assert.match(show.stdout, new RegExp(`^codex pid \\d+: fixture-${number} \\(${issue}\\) since `, "m"));
    assert.match(show.stdout, new RegExp(`has 2 sub-agents listed as working \\((${child}, ${sibling}|${sibling}, ${child})\\)`));
    if (hosting === "daemon") assert.match(show.stdout, new RegExp(`^codex pid ${daemonPid}: fixture-${number} `, "m"));
  });
}

check("daemon-picker: a controller's `thread/read` shows the lead, child and sibling active before Esc and all idle after; the interrupted child reads idle like the completed sibling", () => {
  const outcome = outcomeOf("daemon-picker");
  assert.deepEqual(["lead", "child", "sibling"].map((role) => outcome.before[role].status.type), ["active", "active", "active"]);
  assert.deepEqual(["lead", "child", "sibling"].map((role) => outcome.after[role].status.type), ["idle", "idle", "idle"]);
});

check("standalone-picker: the terminal's exit publishes the lead's `SessionEnd`, which ends the run, and with its process gone the `sub-agent` blocker clears", () => {
  const lead = shell("sp.0").env.CODEX_THREAD_ID;
  const interrupt = interruptIn("standalone-picker");
  const ends = leadHooks("SessionEnd", lead);
  assert.equal(ends.length, 1);
  assert(ends[0].receiptTime > interrupt.receiptTime);
  assert.equal(one("terminal.exit", (record) => record.name === "standalone-picker").exited, true);
  assert.deepEqual(runFor("after-standalone-exit", "I_fixture_5"), []);
  assert.deepEqual(subagentBlockers("after-standalone-exit"), []);
  assert.equal(checkAt("after-standalone-exit").result.removable, true);
});

check("interrupt-agent (the 0.160.0 regression check): the lead model's `interrupt_agent` on a working child replies `previous_status` `running` and aborts the child's turn; the child's command is not signalled and runs its full hold; after the interrupt the child asks the model nothing and publishes no hook, never `SubagentStop`; `list_agents` reports it `interrupted`, the lead's own turn stops, and Dashpot keeps the run running with the blocker naming the child", () => {
  const lead = shell("ia.0").env.CODEX_THREAD_ID;
  const child = shell("iae.0").env.CODEX_THREAD_ID;
  const interrupt = interruptIn("interrupt-agent");
  const outcome = outcomeOf("interrupt-agent");
  assert.deepEqual([interrupt.how, interrupt.lead, interrupt.child], ["interrupt_agent", lead, child]);
  const call = one("model.request", (record) => record.thread === lead && record.action === "interrupt_agent");
  assert(call.receiptTime <= interrupt.receiptTime);
  startedAsChild(lead, child, "iae.0", call.receiptTime);
  windowObserved(outcome);
  assert.deepEqual(JSON.parse(replyAt(lead, 4)), { previous_status: "running" });
  assert.deepEqual(aborts(outcome, child).map((turn) => turn.reason), ["interrupted"]);
  assert.deepEqual(aborts(outcome, lead), []);
  const start = shell("iae.0");
  const end = shell("iae.0", "end");
  assert.deepEqual(signalled("iae.0"), []);
  assert(end.receiptTime > call.receiptTime && end.receiptTime - start.receiptTime >= 19500);
  assert(outcome.windowEnd - end.receiptTime >= 15000);
  assert.deepEqual(requests.filter((record) => record.thread === child && record.receiptTime > call.receiptTime), []);
  assert.deepEqual(childHooks(child).filter((record) => record.receiptTime > call.receiptTime), []);
  assert.deepEqual(childHooks(child).filter((record) => record.event === "SubagentStop"), []);
  const listed = JSON.parse(replyAt(lead, 5));
  assert.deepEqual(listed.agents.map((agent) => [agent.agent_name, agent.agent_status]), [["/root", "running"], ["/root/worker_e", "interrupted"]]);
  assert.deepEqual(leadHooks("Interrupt", lead), []);
  const stops = leadHooks("Stop", lead);
  assert.equal(stops.length, 1);
  assert(stops[0].receiptTime > call.receiptTime);
  assert.deepEqual([outcome.after.lead.status.type, outcome.after.child.status.type], ["idle", "idle"]);
  assert.deepEqual(runFor("interrupt-agent-after", "I_fixture_3").map((run) => run.state), ["running"]);
  assert.deepEqual(subagentBlockers("interrupt-agent-after").filter((obstacle) => obstacle.sessionId === lead).map((obstacle) => obstacle.agents), [[child]]);
});

check("daemon-picker: once its terminal exits, the daemon unloads the lead about 60 s later with `SessionEnd` and keeps running; Dashpot ends the run, but the ended session keeps the interrupted child listed, so the `sub-agent` blocker stays, now saying the session ended with it listed and naming `dashpot work forget-subagents`", () => {
  const lead = shell("dp.0").env.CODEX_THREAD_ID;
  const child = shell("dpp.0").env.CODEX_THREAD_ID;
  const exit = one("terminal.exit", (record) => record.name === "daemon-picker");
  assert.equal(exit.exited, true);
  const ends = leadHooks("SessionEnd", lead);
  assert.equal(ends.length, 1);
  assert.equal(ends[0].scenario, "daemon-picker");
  const unloadAfter = ends[0].receiptTime - exit.receiptTime;
  assert(unloadAfter >= 55000 && unloadAfter <= 70000, `unload ${unloadAfter} ms after the exit`);
  const unload = one("daemon-picker.unload");
  assert.deepEqual([unload.lead, unload.unloaded, unload.daemons], [lead, true, [daemonPid]]);
  assert.deepEqual(runFor("daemon-picker-unloaded", "I_fixture_2"), []);
  const blockers = subagentBlockers("daemon-picker-unloaded");
  assert.deepEqual(blockers.map((obstacle) => [obstacle.sessionId, obstacle.agents]), [[lead, [child]]]);
  assert.match(blockers[0].detail, /ended with 1 sub-agent listed as working/);
  assert.match(blockers[0].command, new RegExp(`dashpot work forget-subagents ${lead} --harness codex$`));
});

check("daemon-stop: stopping the daemon publishes `SessionEnd` for the thread it still hosted, whose run reads unknown and orphaned; the control lead had unloaded earlier like the picker lead; with the daemon gone, no `sub-agent` blocker remains, the ended session's interrupted child included", () => {
  const stop = one("daemon.stop");
  assert.equal(stop.status, 0);
  const iaEnds = leadHooks("SessionEnd", shell("ia.0").env.CODEX_THREAD_ID);
  assert.equal(iaEnds.length, 1);
  assert.equal(iaEnds[0].scenario, "daemon-stop");
  const controlEnds = leadHooks("SessionEnd", shell("de.0").env.CODEX_THREAD_ID);
  assert.equal(controlEnds.length, 1);
  assert(controlEnds[0].receiptTime < stop.receiptTime);
  const controlUnload = controlEnds[0].receiptTime - one("terminal.exit", (record) => record.name === "daemon-esc").receiptTime;
  assert(controlUnload >= 55000 && controlUnload <= 70000, `control unload ${controlUnload} ms after the exit`);
  assert.deepEqual(runFor("after-daemon-stop", "I_fixture_3").map((run) => [run.state, run.orphaned]), [["unknown", true]]);
  assert.deepEqual(runFor("after-daemon-stop", "I_fixture_2"), []);
  assert.deepEqual(subagentBlockers("after-daemon-stop"), []);
  assert.equal(checkAt("after-daemon-stop").result.removable, true);
  const after = one("processes", (record) => record.label === "after-daemon-stop");
  assert.deepEqual([after.daemons, after.socketExists], [[], false]);
});

check("Every lead's `work start` from its own shell bound its Issue", () => {
  for (const [label, number] of [["de.0", 1], ["dp.0", 2], ["ia.0", 3], ["se.0", 4], ["sp.0", 5]]) {
    const work = workOf(label);
    assert.deepEqual([work.args, work.status], [["work", "start", String(number)], 0]);
    assert.match(work.stdout, new RegExp(`^started work on fixture-${number} \\(I_fixture_${number}\\)`));
  }
});

// Source facts the spike cites, at rust-v0.166.0.
if (codexSource) {
  const commit = execFileSync("git", ["-C", codexSource, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  assert.equal(commit, "6ff1e1ca3b30fc8b914720681fcf5fe62e95f856", "the rust-v0.166.0 commit");
  const source = (file) => readFileSync(path.join(codexSource, "codex-rs", file), "utf8");
  // Each pattern is matched in the file the spike cites, not at its line.
  check("Source: a turn's stop hooks run only when the turn finishes without a follow-up, `Stop` for a root turn and `SubagentStop` for a spawned child's; an interrupted turn's hooks return at once for any sub-agent", () => {
    assert.match(source("core/src/session/turn.rs"), /if !needs_follow_up \{\s*last_agent_message = sampling_request_last_agent_message;\s*let stop_outcome = run_turn_stop_hooks\(/);
    const runtime = source("core/src/hook_runtime.rs");
    assert.match(runtime, /Root turns run Stop; thread-spawned child turns run SubagentStop\./);
    assert.match(runtime, /pub\(crate\) async fn run_turn_interrupt_hooks\([^)]*\) \{\s*if matches!\(&turn_context\.session_source, SessionSource::SubAgent\(_\)\) \{\s*return;\s*\}/);
  });
  check("Source: `/subagents` opens the agent picker, choosing a row selects that agent thread, and the terminal sends an interrupt to its active thread as `turn/interrupt` naming that thread and its turn; `--no-daemon` runs without the shared background server", () => {
    assert.match(source("tui/src/slash_command.rs"), /#\[strum\(serialize = "subagents"\)\]\s*MultiAgents,/);
    assert.match(source("tui/src/chatwidget/slash_dispatch.rs"), /SlashCommand::MultiAgents => \{\s*self\.app_event_tx\.send\(AppEvent::OpenAgentPicker\);/);
    assert.match(source("tui/src/app/event_dispatch.rs"), /AppEvent::SelectAgentThread\(thread_id\) => \{\s*self\.select_agent_thread\(tui, app_server, thread_id\)/);
    const routing = source("tui/src/app/thread_routing.rs");
    assert.match(routing, /pub\(super\) async fn submit_active_thread_op\([^)]*\) -> Result<\(\)> \{\s*let Some\(thread_id\) = self\.active_thread_id else \{/);
    assert.match(routing, /AppCommand::Interrupt => \{\s*let mut turn_id = self\s*\.active_turn_id_for_thread\(thread_id\)/);
    assert.match(routing, /ClientRequest::TurnInterrupt \{\s*request_id,\s*params: TurnInterruptParams \{\s*thread_id: thread_id\.to_string\(\),\s*turn_id: turn_id\.clone\(\),/);
    assert.match(source("tui/src/cli.rs"), /Run without the shared background server, even if it is already running\.\s*#\[arg\([^)]*\)\]\s*pub no_daemon: bool,/);
  });
  check("Source: a daemon's control socket is bound in `/tmp/codex-daemon-<uid>`, whatever `TMPDIR` or `CODEX_HOME` say, named by the SHA-256 of the advertised socket path with its parent canonicalized, beside a `.lock`", () => {
    const directory = source("uds/src/daemon_directory.rs");
    assert.match(directory, /It must not depend on HOME, TMPDIR, CODEX_HOME, or command settings\./);
    assert.match(directory, /let temporary_root = fs::canonicalize\("\/tmp"\)\?;\s*let uid = unsafe \{ libc::geteuid\(\) \};\s*Ok\(temporary_root\.join\(format!\("codex-daemon-\{uid\}"\)\)\)/);
    const transport = source("app-server-transport/src/transport/unix_socket.rs");
    assert.match(transport, /let path = std::fs::canonicalize\(parent\)\?\.join\(name\);\s*let hash = Sha256::digest\(path\.as_os_str\(\)\.as_bytes\(\)\);\s*Ok\(codex_uds::shared_daemon_socket_directory\(\)\?\.join\(format!\("\{hash:x\}"\)\)\)/);
    assert.match(transport, /physical_path\.with_extension\("lock"\)/);
  });
  check("Source: `interrupt_agent` replies with the target's status before the interrupt", () => {
    const tool = source("core/src/tools/handlers/multi_agents_v2/interrupt_agent.rs");
    assert.match(tool, /let previous_status = snapshot\.status\(\)\.cloned\(\)\.unwrap_or\(AgentStatus::NotFound\);/);
    assert.match(tool, /Ok\(InterruptAgentResult \{ previous_status \}\)/);
  });
} else {
  console.log("Codex source facts not checked: pass --codex-source <rust-v0.166.0 checkout>.");
}

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
