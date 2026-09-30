// Independent verifier for a Claude Code 345 experiment trace.
// Checks the recorded hook, shell, listing, opener and model-request evidence
// against the claims for 2.1.285, or for the 2.1.280 comparison run, without
// importing the runner or publisher.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const expectedVersion = process.argv[3] ?? "2.1.285";
assert(["2.1.280", "2.1.285"].includes(expectedVersion), "claims are recorded for 2.1.280 and 2.1.285 only");
const current = expectedVersion === "2.1.285";
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
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
const subagentRequests = (name) => {
  let inside = false;
  return records.filter((record) => {
    if (record.kind === "scenario") inside = record.name === name;
    return inside && record.kind === "model.request" && !record.classifier;
  });
};
for (const outcome of of("subagent.outcome")) {
  assert.equal(outcome.status, 0, `${outcome.name} exits 0`);
  assert.equal(outcome.isError, false, `${outcome.name} succeeds`);
  const starts = outcome.pairs.filter((pair) => pair.event === "SubagentStart");
  assert.equal(starts.length, 1, `${outcome.name} starts one sub-agent`);
  const agent = starts[0].agentId;
  const stops = outcome.pairs.filter((pair) => pair.event === "SubagentStop");
  assert(stops.length >= 1 && stops.every((stop) => stop.agentId === agent), `${outcome.name} stops name the started agent`);
  assert(outcome.pairs.every((pair) => pair.agentType === "general-purpose"), `${outcome.name} names the agent type`);
  const events = outcome.sequence.map((entry) => entry[0]);
  // In `-p` the parent's first Stop arrives while the sub-agent still runs:
  // the session's liveness depends on the sub-agent set, not on Stop.
  const firstStop = events.indexOf("Stop");
  assert(firstStop < events.indexOf("SubagentStop"), `${outcome.name}: the main Stop precedes SubagentStop`);
  // The sub-agent's report reaches the parent as a new turn before the end.
  assert.deepEqual(events.slice(-2), ["Stop", "SessionEnd"], `${outcome.name} ends after a second Stop`);
  // 2.1.280 answers a handed-back report in auto mode with a second,
  // redundant turn; 2.1.285 and every other case take one.
  const handedBack = outcome.mode === "auto" && outcome.label !== "delegate-plain";
  const notifications = events.slice(firstStop).filter((event) => event === "UserPromptSubmit").length;
  assert.equal(notifications, handedBack && !current ? 2 : 1, `${outcome.name} notification turns`);
  assert.equal(events.slice(firstStop).filter((event) => event === "Stop").length, notifications + 1, `${outcome.name}: each notification turn ends in Stop`);
  const parentPid = Number(hooks.find((hook) => hook.payload.session_id === outcome.session).env.CLAUDE_PID);
  assert(outcome.childCommands.length && outcome.childCommands.every(([, , pid]) => pid === parentPid), `${outcome.name} child runs in the parent process`);
  const handback = outcome.childRequests.filter((request) => request.tool === "SubagentHandback");
  if (outcome.mode === "bypass") {
    assert(handback.every((request) => request.available === false), `${outcome.name}: SubagentHandback is not offered under bypass`);
    assert.deepEqual(outcome.stopHookActive, [false], `${outcome.name} stops once`);
  } else if (outcome.label === "delegate-plain") {
    // A child that ends without handing back is re-prompted three times, each
    // ending in another SubagentStop for the same agent.
    assert.deepEqual(outcome.stopHookActive, [false, true, true, true], `${outcome.name} enforcement stops`);
    assert.equal(outcome.childRequests.filter((request) => request.enforced).length, 3, `${outcome.name} re-prompts three times`);
  } else {
    assert(handback.length && handback.every((request) => request.available === true), `${outcome.name}: SubagentHandback is offered in auto mode`);
    assert.deepEqual(outcome.stopHookActive, [false], `${outcome.name} stops once after handing back`);
    // 2.1.285 ends the child at its handback and drops the parent's extra
    // reply; 2.1.280 takes one more turn in each.
    const child = subagentRequests(outcome.name).filter((request) => request.label.startsWith("child"));
    const parent = subagentRequests(outcome.name).filter((request) => request.label === outcome.label);
    assert.equal(child.length, current ? 2 : 3, `${outcome.name} child requests`);
    assert.equal(parent.length, current ? 3 : 4, `${outcome.name} parent requests`);
  }
}

// Scenario 2: nothing fires after an interactive turn's Stop, with or without
// the prompt-suggestion flag, and in auto mode.
for (const outcome of of("interactive.outcome")) {
  const events = outcome.newHooks.map((event) => event[0]);
  assert.deepEqual(events, ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"], `${outcome.name} hook sequence`);
  assert.deepEqual(outcome.afterStop, [], `${outcome.name}: no hook after Stop`);
  assert.deepEqual(outcome.requestsAfterStop, [], `${outcome.name}: no model request after Stop`);
}

// Scenario 3: resuming a session that runs in the background.
const job = one("background.job").job;
assert.equal(job.kind, "background");
// The terminal draws with cursor moves, so screens are compared without spaces.
const squash = (text) => text.replace(/\s+/g, "");
const refusal = current ? /Thatsessionisrunninginthebackground/ : /isrunningasabackgroundsession/;
for (const outcome of of("resume.interactive")) {
  assert.equal(outcome.exited?.status, 1, `interactive resume ${outcome.variant} exits 1`);
  assert.match(squash(outcome.screen), refusal, `interactive resume ${outcome.variant} refuses`);
  assert.deepEqual(outcome.newHooks, [], `interactive resume ${outcome.variant} fires no hook`);
  assert.equal(outcome.workerAlive, true);
  assert.equal(outcome.command, null);
}
// The refused headless resume ends the live session's id from its own pid.
const headless = one("resume.headless");
assert.equal(headless.status, 1);
assert.match(squash(headless.stderr), refusal);
assert.equal(headless.workerAlive, true);
assert.equal(headless.command, null);
assert.deepEqual(headless.newHooks, [["SessionEnd", job.sessionId, null, "other", String(headless.headlessPid)]]);
assert.notEqual(headless.headlessPid, job.pid);
// `--bg --resume` of a running session starts a fork under a new id.
const copy = one("resume.background");
assert.equal(copy.status, 0);
assert.match(copy.stderr, /already running in the background, so this started a copy/);
assert.notEqual(copy.command.session, job.sessionId);
assert.notEqual(copy.command.claudePid, job.pid);
assert.deepEqual(copy.newHooks[0].slice(0, 4), ["SessionStart", copy.command.session, null, "fork"]);
assert(copy.newHooks.every((event) => event[1] === copy.command.session), "the copy's hooks name only the copy");
// After `claude stop`, the worker ends the session and an interactive resume
// opens it in the terminal's own `claude` process.
const stopped = one("resume.stopped");
assert.equal(stopped.stopStatus, 0);
assert.deepEqual(stopped.newHooks[0], ["SessionEnd", job.sessionId, null, "other", String(job.pid)]);
assert.deepEqual(stopped.newHooks[1], ["SessionStart", job.sessionId, null, "resume", String(stopped.terminalClaudePid)]);
assert.equal(stopped.command.session, job.sessionId);
assert.equal(stopped.command.claudePid, stopped.terminalClaudePid);
assert.equal(stopped.command.ancestry.find(([pid]) => pid === stopped.terminalClaudePid)[1], "claude");
// A background worker runs the versioned executable, not `claude`.
const workerHook = hooks.find((hook) => hook.payload.session_id === job.sessionId && hook.event === "SessionStart");
assert.equal(workerHook.ancestry.find((entry) => entry.pid === job.pid).comm, expectedVersion);

// Scenario 4: `--desktop` is new in 2.1.285 and, on Linux, refuses without
// launching anything.
for (const outcome of of("desktop.outcome")) {
  const text = outcome.name === "desktop-redirected" ? outcome.stderr : outcome.screen;
  const status = outcome.name === "desktop-redirected" ? outcome.status : outcome.exited?.status;
  assert.equal(status, 1, `${outcome.name} exits 1`);
  if (!current) assert.match(text, /unknown option '--desktop'/);
  else if (outcome.name === "desktop-redirected") assert.match(text, /can't run non-interactively/);
  else assert.match(squash(text), /--desktopisn'tavailableonthisplatform/);
  assert.deepEqual(outcome.openers, [], `${outcome.name} launches nothing`);
  assert.deepEqual(outcome.newHooks, [], `${outcome.name} fires no hook`);
}

// Scenario 5: a non-interactive `--bg` inherits trust inside the Repository
// and in its sibling linked Worktree; 2.1.285 refuses an untrusted Repository.
const trust = (name) => one("bg-trust.outcome", (record) => record.name === name);
for (const name of ["bg-trust-nested", "bg-trust-sibling"]) {
  assert.equal(trust(name).status, 0);
  assert.equal(trust(name).ran, true, `${name} runs its command`);
}
for (const name of ["bg-trust-unrelated", "bg-trust-unrelated-default-mode"]) {
  const outcome = trust(name);
  if (current) {
    assert.equal(outcome.status, 1, `${name} exits 1`);
    assert.match(outcome.stderr, /Workspace not trusted/);
    assert.equal(outcome.ran, false);
    assert(!outcome.newHooks.some((event) => event[0] === "SessionStart"), `${name} starts no session`);
  } else {
    assert.equal(outcome.status, 0, `${name} is dispatched`);
    assert(outcome.newHooks.some((event) => event[0] === "SessionStart"), `${name} starts a session and runs its hooks`);
  }
}
assert.equal(trust("bg-trust-unrelated").ran, !current, "the bypass session in the untrusted Repository runs only before 2.1.281");

// Scenario 6: without the user source, neither a headless session nor a
// directly dispatched worker runs the user-scope hooks.
for (const outcome of of("sources.outcome")) {
  assert.equal(outcome.status, 0);
  assert.equal(outcome.ran, true, `${outcome.name} runs its command`);
  assert.deepEqual(outcome.hooksForSession, [], `${outcome.name} runs no user hook`);
}

// The trace holds metadata only: no transcripts, tokens or prompts.
const text = readFileSync(tracePath, "utf8");
assert(!text.includes("CLAUDE_CODE_MESSAGING_TOKEN"), "messaging token not retained");
assert(!/"transcript_path":/.test(text) && !/last_assistant_message":/.test(text), "transcripts and messages not retained");
console.log(`Verified ${records.length} records: ${hooks.length} hooks, ${commands.length} commands, ${scenarios.length} scenarios on ${expectedVersion}.`);
