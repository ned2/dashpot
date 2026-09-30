// Independent verifier for a Claude Code 345 experiment trace.
// Checks the recorded hook, shell, process, listing, opener and model-request
// evidence against the claims for 2.1.285, or for the 2.1.280 comparison run,
// without importing the runner or publisher. Each claim is recomputed from the
// raw records inside its scenario; the runner's summaries must agree with them.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const expectedVersion = process.argv[3] ?? "2.1.285";
assert(["2.1.280", "2.1.285"].includes(expectedVersion), "claims are recorded for 2.1.280 and 2.1.285 only");
const is285 = expectedVersion === "2.1.285";
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind, from = records) => from.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true, from = records) => {
  const found = of(kind, from).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const hooks = of("hook");
const commands = of("command").filter((record) => record.phase === "start");
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `${expectedVersion} (Claude Code)`);
const scenarios = of("scenario").map((record) => record.name);
const expected = ["delegate", "delegate-bg", "delegate-plain"].flatMap((label) => [`subagent-bypass-${label}`, `subagent-auto-${label}`])
  .concat(["interactive-flag-off", "interactive-flag-on", "interactive-flag-on-auto", "resume-running-background",
    "desktop-redirected", "desktop-terminal", "desktop-terminal-resume",
    "bg-trust-nested", "bg-trust-sibling", "bg-trust-unrelated", "bg-trust-unrelated-default-mode", "sources-headless", "sources-bg"]);
for (const name of expected) assert(scenarios.includes(name), `scenario ${name} ran`);
assert(!of("server.error").length, "the fixture servers raised no error");

// The records from a scenario's marker to the next marker, and the records
// strictly between two records.
const within = (name) => {
  const start = records.findIndex((record) => record.kind === "scenario" && record.name === name);
  const next = records.findIndex((record, index) => index > start && record.kind === "scenario");
  return records.slice(start + 1, next === -1 ? undefined : next);
};
const between = (first, last) => records.slice(records.indexOf(first) + 1, records.indexOf(last));
// A hook reduced to the fields the claims name.
const shape = (hook) => ({ event: hook.event, session: hook.payload.session_id, agentId: hook.payload.agent_id ?? null, agentType: hook.payload.agent_type ?? null,
  source: hook.payload.source ?? null, reason: hook.payload.reason ?? null, claudePid: hook.env.CLAUDE_PID });
const hooksIn = (from) => of("hook", from).map(shape);
const events = (shaped) => shaped.map((hook) => hook.event);
const summaryAgrees = (summary, raw, label) => assert.deepEqual(summary, raw, `${label}: the runner's summary matches the raw hooks`);

// Every hook and every Bash command carries the session claim and descends
// from the process CLAUDE_PID names.
for (const hook of hooks) {
  assert.equal(hook.env.CLAUDE_CODE_SESSION_ID, hook.payload.session_id, `hook ${hook.event} claim matches payload`);
  assert(hook.ancestry.some((entry) => entry.pid === Number(hook.env.CLAUDE_PID)), `hook ${hook.event} descends from CLAUDE_PID`);
}
for (const command of commands) {
  assert(command.env.CLAUDE_CODE_SESSION_ID, `command ${command.label} claims a session`);
  assert(command.ancestry.some((entry) => entry.pid === Number(command.env.CLAUDE_PID)), `command ${command.label} descends from CLAUDE_PID`);
}

// Scenario 1: every SubagentStart meets a SubagentStop for the same agent in
// the parent's session; a sub-agent that hands its report back stops once.
for (const outcome of of("subagent.outcome")) {
  const scope = within(outcome.name);
  const run = one("action.claude", (record) => record.args[0] === "-p", scope);
  assert.equal(run.status, 0, `${outcome.name} exits 0`);
  // The runner keeps the tail of stdout, which holds the result's closing fields.
  assert.match(run.stdout, /"is_error":false,"num_turns"/, `${outcome.name} succeeds`);
  const session = one("hook", (record) => record.event === "SessionStart", scope).payload.session_id;
  assert.equal(outcome.session, session);
  const sessionHooks = of("hook", scope).filter((record) => record.payload.session_id === session);
  const sequence = events(sessionHooks.map(shape));
  assert.deepEqual(outcome.sequence.map((entry) => entry[0]), sequence, `${outcome.name}: the runner's sequence matches the raw hooks`);
  const starts = sessionHooks.filter((record) => record.event === "SubagentStart");
  assert.equal(starts.length, 1, `${outcome.name} starts one sub-agent`);
  const agent = starts[0].payload.agent_id;
  const stops = sessionHooks.filter((record) => record.event === "SubagentStop");
  assert(stops.length >= 1 && stops.every((stop) => stop.payload.agent_id === agent), `${outcome.name} stops name the started agent`);
  assert([...starts, ...stops].every((record) => record.payload.agent_type === "general-purpose"), `${outcome.name} names the agent type`);
  const stopHookActive = stops.map((record) => record.payload.stop_hook_active ?? null);
  assert.deepEqual(outcome.stopHookActive, stopHookActive, `${outcome.name}: the runner's stop_hook_active values match the raw hooks`);
  // In `-p` the parent's first Stop arrives while the sub-agent still runs:
  // the session's liveness depends on the sub-agent set, not on Stop.
  const firstStop = sequence.indexOf("Stop");
  assert(firstStop < sequence.indexOf("SubagentStop"), `${outcome.name}: the main Stop precedes SubagentStop`);
  // The sub-agent's report reaches the parent as a new turn before the end.
  assert.deepEqual(sequence.slice(-2), ["Stop", "SessionEnd"], `${outcome.name} ends after a second Stop`);
  // 2.1.280 answers a handed-back report in auto mode with a second,
  // redundant turn; 2.1.285 and every other case take one.
  const handedBack = outcome.mode === "auto" && outcome.label !== "delegate-plain";
  const notifications = sequence.slice(firstStop).filter((event) => event === "UserPromptSubmit").length;
  assert.equal(notifications, handedBack && !is285 ? 2 : 1, `${outcome.name} notification turns`);
  assert.equal(sequence.slice(firstStop).filter((event) => event === "Stop").length, notifications + 1, `${outcome.name}: each notification turn ends in Stop`);
  const parentPid = starts[0].env.CLAUDE_PID;
  const childCommands = of("command", scope).filter((record) => record.env.CLAUDE_CODE_SESSION_ID === session);
  assert(childCommands.length && childCommands.every((record) => record.env.CLAUDE_PID === parentPid), `${outcome.name} child runs in the parent process`);
  const requests = of("model.request", scope).filter((record) => !record.classifier);
  const child = requests.filter((request) => request.label?.startsWith("child"));
  const handback = child.filter((request) => request.tool === "SubagentHandback");
  const enforced = child.filter((request) => /handback-send-enforce/.test(request.lastUserHead ?? ""));
  if (outcome.mode === "bypass") {
    assert(handback.every((request) => request.available === false), `${outcome.name}: SubagentHandback is not offered under bypass`);
    assert.deepEqual(stopHookActive, [false], `${outcome.name} stops once`);
  } else if (outcome.label === "delegate-plain") {
    // A child that ends without handing back is re-prompted three times, each
    // ending in another SubagentStop for the same agent.
    assert.deepEqual(stopHookActive, [false, true, true, true], `${outcome.name} enforcement stops`);
    assert.equal(enforced.length, 3, `${outcome.name} re-prompts three times`);
  } else {
    assert(handback.length && handback.every((request) => request.available === true), `${outcome.name}: SubagentHandback is offered in auto mode`);
    assert.deepEqual(stopHookActive, [false], `${outcome.name} stops once after handing back`);
    // 2.1.285 ends the child at its handback and drops the parent's extra
    // reply; 2.1.280 takes one more turn in each.
    const parent = requests.filter((request) => request.label === outcome.label);
    assert.equal(child.length, is285 ? 2 : 3, `${outcome.name} child requests`);
    assert.equal(parent.length, is285 ? 3 : 4, `${outcome.name} parent requests`);
  }
}

// Scenario 2: nothing fires after an interactive turn's Stop, with or without
// the cached prompt-suggestion flag read, and in auto mode. The terminal is
// closed after the outcome is recorded, so its SessionEnd is left out.
for (const outcome of of("interactive.outcome")) {
  const scope = between(one("terminal", (record) => record.name === outcome.name), outcome);
  const raw = hooksIn(scope);
  summaryAgrees(outcome.newHooks, raw, outcome.name);
  assert.deepEqual(events(raw), ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"], `${outcome.name} hook sequence`);
  const stopAt = one("hook", (record) => record.event === "Stop", scope).receiptTime;
  assert.deepEqual(of("hook", scope).filter((record) => record.receiptTime > stopAt), [], `${outcome.name}: no hook after Stop`);
  assert.deepEqual(of("model.request", scope).filter((record) => record.receiptTime > stopAt), [], `${outcome.name}: no model request after Stop`);
}

// Scenario 3: resuming a session that runs in the background.
const resume = within("resume-running-background");
const job = one("background.job", () => true, resume).job;
assert.equal(job.kind, "background");
const worker = one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === job.sessionId && record.payload.source === "startup", resume);
assert.equal(Number(worker.env.CLAUDE_PID), job.pid, "the listing names the worker that started the session");
// A background worker runs the versioned executable, not `claude`.
assert.equal(worker.ancestry.find((entry) => entry.pid === job.pid).comm, expectedVersion);
const workerAncestry = (record) => record.ancestry.find((entry) => entry.pid === job.pid);
// The terminal draws with cursor moves, so screens are compared without spaces.
const squash = (text) => text.replace(/\s+/g, "");
const refusal = is285 ? /Thatsessionisrunninginthebackground/ : /isrunningasabackgroundsession/;
// 3a: with a session-configuring flag, an interactive resume is refused.
for (const outcome of of("resume.interactive", resume)) {
  const name = `resume-interactive-${outcome.variant}`;
  const scope = between(one("terminal", (record) => record.name === name), outcome);
  assert(one("terminal", (record) => record.name === name).args.some((arg) => ["--model", "--dangerously-skip-permissions"].includes(arg)), `${name} carries a session-configuring flag`);
  assert.equal(one("terminal.exit", (record) => record.name === name).status, 1, `interactive resume ${outcome.variant} exits 1`);
  assert.match(squash(outcome.screen), refusal, `interactive resume ${outcome.variant} refuses`);
  summaryAgrees(outcome.newHooks, hooksIn(scope), name);
  assert.deepEqual(hooksIn(scope), [], `interactive resume ${outcome.variant} fires no hook`);
  assert.equal(of("command", scope).length, 0, `${name} runs nothing`);
  assert.equal(outcome.workerAlive, true);
}
// 3b: the refused headless resume ends the live session's id from its own pid.
const headless = one("resume.headless", () => true, resume);
const headlessRun = one("action.claude", (record) => record.args[0] === "-p" && record.args.includes("--resume"), resume);
assert.equal(headlessRun.status, 1);
assert.match(squash(headlessRun.stderr), refusal);
assert.notEqual(headlessRun.pid, job.pid);
const headlessHooks = hooksIn(between(one("resume.interactive-exit", (record) => record.variant === "default-mode", resume), headless));
summaryAgrees(headless.newHooks, headlessHooks, "headless resume");
assert.deepEqual(headlessHooks, [{ event: "SessionEnd", session: job.sessionId, agentId: null, agentType: null, source: null, reason: "other", claudePid: String(headlessRun.pid) }]);
assert(!commands.some((record) => record.label === "resumed-headless"), "the headless resume runs nothing");
assert.equal(headless.workerAlive, true);
// 3c: `--bg --resume` of a running session starts a fork under a new id.
const copy = one("resume.background", () => true, resume);
const copyRun = one("action.claude", (record) => record.args[0] === "--bg" && record.args.includes("--resume"), resume);
assert.equal(copyRun.status, 0);
assert.match(copyRun.stderr, /already running in the background, so this started a copy/);
const copyCommand = one("command", (record) => record.label === "resumed-bg" && record.phase === "start");
assert.notEqual(copyCommand.env.CLAUDE_CODE_SESSION_ID, job.sessionId);
assert.notEqual(Number(copyCommand.env.CLAUDE_PID), job.pid);
const copyHooks = hooksIn(between(headless, copy));
summaryAgrees(copy.newHooks, copyHooks, "background resume");
assert.deepEqual([copyHooks[0].event, copyHooks[0].session, copyHooks[0].source], ["SessionStart", copyCommand.env.CLAUDE_CODE_SESSION_ID, "fork"]);
assert(copyHooks.every((hook) => hook.session === copyCommand.env.CLAUDE_CODE_SESSION_ID), "the copy's hooks name only the copy");
// 3d: with no session-configuring flag, 2.1.285 opens the running session in
// place: the terminal's process becomes an attached client, the turn runs in
// the worker, and the worker publishes its hooks.
const opens = of("resume.open", resume);
assert.deepEqual(opens.map((record) => record.variant), ["open-prompt", "open-bare"]);
for (const outcome of opens) {
  const name = `resume-interactive-${outcome.variant}`;
  const label = `resumed-${outcome.variant}`;
  const started = one("terminal", (record) => record.name === name);
  assert.deepEqual(started.args.slice(0, 2), ["--resume", job.sessionId]);
  assert(started.args.slice(2).every((arg) => !arg.startsWith("-")), `${name} carries no flag`);
  const scope = between(started, outcome);
  const raw = hooksIn(scope);
  summaryAgrees(outcome.newHooks, raw, name);
  const exit = one("resume.open-exit", (record) => record.variant === outcome.variant, resume);
  const exitHooks = hooksIn(between(outcome, exit));
  summaryAgrees(exit.newHooks, exitHooks, `${name} exit`);
  if (is285) {
    const client = one("processes", (record) => record.label === `${name} open`, resume).processes.find((entry) => entry.pid === outcome.terminalClaudePid);
    assert.equal(client.comm, expectedVersion, `${name}: the client runs the versioned executable`);
    assert.match(client.cmdline, new RegExp(` attach ${job.id}$`), `${name}: the terminal's process attaches to the job`);
    assert.deepEqual(events(raw), ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"], `${name}: the turn's hooks, without a SessionStart`);
    assert(raw.every((hook) => hook.session === job.sessionId && hook.claudePid === String(job.pid)), `${name}: the worker publishes every hook`);
    const command = one("command", (record) => record.label === label && record.phase === "start");
    assert.equal(command.env.CLAUDE_CODE_SESSION_ID, job.sessionId);
    assert.equal(Number(command.env.CLAUDE_PID), job.pid, `${name}: the command runs in the worker`);
    assert.equal(workerAncestry(command).comm, expectedVersion);
    // `/exit` returns the client to the agents view rather than detaching; the
    // worker's session publishes nothing when the client goes.
    assert.equal(exit.exitedOnExit, null, `${name}: /exit leaves the client running`);
    assert.match(exit.clientAfterExit.cmdline, / agents$/, `${name}: the client shows the agents view`);
    assert(!exitHooks.some((hook) => hook.session === job.sessionId), `${name}: closing the client publishes nothing for the worker's session`);
    const clientEnd = exitHooks.filter((hook) => hook.claudePid === String(outcome.terminalClaudePid));
    assert.deepEqual(clientEnd.map((hook) => [hook.event, hook.reason]), [["SessionEnd", "other"]], `${name}: the client ends a session of its own`);
    assert(!hooks.some((hook) => hook.event === "SessionStart" && hook.payload.session_id === clientEnd[0].session), `${name}: the client's own session never started`);
    // The agents view runs a pre-warmed spare's session, which ends by the
    // time the client has closed.
    const spare = of("hook", between(outcome, exit)).filter((record) => record.env.CLAUDE_PID !== String(outcome.terminalClaudePid));
    assert.deepEqual(spare.map((record) => [record.event, record.payload.source ?? record.payload.reason]), [["SessionStart", "startup"], ["SessionEnd", "other"]],
      `${name}: the agents view starts and ends one other session`);
    assert(spare.every((record) => record.payload.session_id === spare[0].payload.session_id && / bg-spare /.test(record.ancestry.find((entry) => entry.pid === Number(record.env.CLAUDE_PID)).cmdline)), `${name}: a pre-warmed spare publishes it`);
  } else {
    // 2.1.280 refuses the same resume, naming `claude attach` instead.
    assert.equal(one("terminal.exit", (record) => record.name === name).status, 1, `${name} exits 1`);
    assert.match(squash(outcome.screen), refusal, `${name} refuses`);
    assert.match(squash(outcome.screen), new RegExp(`Run\`claudeattach${job.id}\`toopenit`), `${name} names claude attach`);
    assert.deepEqual([...raw, ...exitHooks], [], `${name} fires no hook`);
    assert.equal(of("command", scope).length, 0, `${name} runs nothing`);
    assert.equal(outcome.workerAlive, true);
  }
}
// 3e: after `claude stop`, the worker ends the session and an interactive
// resume opens it in the terminal's own `claude` process.
const stopped = one("resume.stopped", () => true, resume);
const stopRun = one("action.claude", (record) => record.args[0] === "stop", resume);
assert.equal(stopRun.status, 0);
const stoppedHooks = hooksIn(between(stopRun, stopped));
summaryAgrees(stopped.newHooks, stoppedHooks, "stopped resume");
const stoppedCommand = one("command", (record) => record.label === "resumed-stopped" && record.phase === "start");
const terminalPid = stoppedCommand.env.CLAUDE_PID;
assert.deepEqual(stoppedHooks[0], { event: "SessionEnd", session: job.sessionId, agentId: null, agentType: null, source: null, reason: "other", claudePid: String(job.pid) });
assert.deepEqual([stoppedHooks[1].event, stoppedHooks[1].session, stoppedHooks[1].source, stoppedHooks[1].claudePid], ["SessionStart", job.sessionId, "resume", terminalPid]);
assert.equal(stoppedCommand.env.CLAUDE_CODE_SESSION_ID, job.sessionId);
assert.equal(stoppedCommand.ancestry.find((entry) => entry.pid === Number(terminalPid)).comm, "claude");

// Scenario 4: `--desktop` is new in 2.1.285 and, on Linux, refuses without
// launching anything.
for (const outcome of of("desktop.outcome")) {
  const scope = within(outcome.name);
  const redirected = outcome.name === "desktop-redirected";
  const text = redirected ? one("action.claude", () => true, scope).stderr : outcome.screen;
  const status = redirected ? one("action.claude", () => true, scope).status : one("terminal.exit", (record) => record.name === outcome.name).status;
  assert.equal(status, 1, `${outcome.name} exits 1`);
  if (!is285) assert.match(text, /unknown option '--desktop'/);
  else if (redirected) assert.match(text, /can't run non-interactively/);
  else assert.match(squash(text), /--desktopisn'tavailableonthisplatform/);
  assert.deepEqual(of("opener", scope), [], `${outcome.name} launches nothing`);
  assert.deepEqual(outcome.openers, [], `${outcome.name}: the runner's summary records no launch`);
  assert.deepEqual(hooksIn(scope), [], `${outcome.name} fires no hook`);
}

// Scenario 5: a non-interactive `--bg` inherits trust in a directory nested in
// the trusted main working tree and in its sibling linked Worktree; 2.1.285
// refuses a directory outside it.
const trust = (name) => {
  const scope = within(name);
  const run = one("action.claude", (record) => record.args[0] === "--bg", scope);
  const raw = hooksIn(scope);
  const outcome = one("bg-trust.outcome", () => true, scope);
  // A dispatched worker can publish before its dispatching client exits.
  summaryAgrees(outcome.newHooks, hooksIn(between(one("scenario", (record) => record.name === name), outcome)), name);
  return { status: run.status, stderr: run.stderr, ran: of("command", scope).some((record) => record.label === name), started: raw.some((hook) => hook.event === "SessionStart") };
};
for (const name of ["bg-trust-nested", "bg-trust-sibling"]) {
  const outcome = trust(name);
  assert.equal(outcome.status, 0);
  assert.equal(outcome.ran, true, `${name} runs its command`);
  assert.equal(outcome.started, true, `${name} starts a session`);
}
for (const name of ["bg-trust-unrelated", "bg-trust-unrelated-default-mode"]) {
  const outcome = trust(name);
  if (is285) {
    assert.equal(outcome.status, 1, `${name} exits 1`);
    assert.match(outcome.stderr, /Workspace not trusted/);
    assert.equal(outcome.ran, false);
    assert.equal(outcome.started, false, `${name} starts no session`);
  } else {
    assert.equal(outcome.status, 0, `${name} is dispatched`);
    assert.equal(outcome.started, true, `${name} starts a session and runs its hooks`);
  }
}
assert.equal(trust("bg-trust-unrelated").ran, !is285, "the bypass session in the untrusted directory runs only before 2.1.281");

// Scenario 6: without the user source, neither a headless session nor a
// directly dispatched worker runs the user-scope hooks.
for (const outcome of of("sources.outcome")) {
  const scope = within(outcome.name);
  assert.equal(one("action.claude", (record) => record.args.includes("--setting-sources"), scope).status, 0);
  const ran = one("command", (record) => record.label === outcome.name && record.phase === "start", scope);
  assert.equal(outcome.session, ran.env.CLAUDE_CODE_SESSION_ID);
  assert.deepEqual(hooksIn(scope).filter((hook) => hook.session === ran.env.CLAUDE_CODE_SESSION_ID), [], `${outcome.name} runs no user hook`);
}

// The trace holds metadata only: no transcripts, tokens or prompts.
const text = readFileSync(tracePath, "utf8");
assert(!text.includes("CLAUDE_CODE_MESSAGING_TOKEN"), "messaging token not retained");
assert(!/"transcript_path":/.test(text) && !/last_assistant_message":/.test(text), "transcripts and messages not retained");
console.log(`Verified ${records.length} records: ${hooks.length} hooks, ${commands.length} commands, ${scenarios.length} scenarios on ${expectedVersion}.`);
