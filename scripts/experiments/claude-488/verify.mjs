// Independent verifier for the Issue #488 trace, with #490's `/fork`: checks
// each finding about a Claude Code session that starts and is not prompted
// (opened, resumed at launch, headless, or `/clear`ed with no worker), about
// `/fork` while a background Sub-agent works, and about what Dashpot's hook
// record store held with ADR 0106's rule, against the recorded hook, shell,
// model-request, `claude agents` and hook-store evidence; and that the trace
// came from the runner retained beside this file. With --sequences it also
// prints every scenario's hook sequence.
//
// Usage: node verify.mjs <trace.jsonl> [--strict] [--sequences]
//
// The Dashpot sources the trace hashes may change after the run, and the
// runner may be edited after it, so a difference in either from this
// checkout is reported, and fails only under --strict.
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
const pinned = "2.1.289";
const fixture = "$ROOT/repository";
// The wait each idle scenario left the session unprompted, in milliseconds.
const idleMs = 20000;
const span = (name) => {
  const start = records.findIndex((record) => record.kind === "scenario" && record.name === name);
  assert(start >= 0, `scenario ${name}`);
  const end = records.findIndex((record, index) => index > start && record.kind === "scenario.end" && record.name === name);
  assert(end > start, `scenario ${name} ended`);
  assert.equal(records[end].ok, true, `scenario ${name}: ${records[end].error}`);
  return records.slice(start, end + 1);
};
const hooksOf = (scope) => scope.filter((record) => record.kind === "hook");
const stored = (record, session) => (record.store ?? []).find((entry) => entry.sessionId === session);
const listing = (record, agent) => (record.store ?? []).filter((entry) => (entry.liveSubagents ?? []).includes(agent)).map((entry) => entry.sessionId);
const one = (scope, predicate, what) => {
  const found = scope.filter(predicate);
  assert.equal(found.length, 1, `exactly one ${what}`);
  return found[0];
};
// A waiting record with no turn clock, as a session nobody has prompted.
const unprompted = (entry) => {
  assert(entry, "the session's record");
  assert.equal(entry.state, "waiting");
  assert.equal(entry.turnStartedAt, null);
  assert.deepEqual(entry.liveSubagents, []);
};
// The idle wait: nothing was typed or sent, it lasted the full wait, and no
// hook arrived during it.
const quiet = (scope, label) => {
  const start = one(scope, (record) => record.kind === "idle.start" && record.label === label, `${label} start`);
  const end = one(scope, (record) => record.kind === "idle.end" && record.label === label, `${label} end`);
  assert.equal(start.ms, idleMs);
  assert(end.receiptTime - start.receiptTime >= idleMs, `${label} lasted the wait`);
  const between = scope.filter((record) => record.receipt > start.receipt && record.receipt < end.receipt);
  assert(!between.some((record) => record.kind.startsWith("turn") || record.kind.startsWith("action")), `${label}: nothing typed`);
  return { start, end, hooks: hooksOf(between) };
};

// The run itself.
const environment = records[0];
check("the trace is of the pinned Claude Code release, with the updater off and an isolated configuration", () => {
  assert.equal(environment.kind, "environment");
  assert.equal(environment.version, `${pinned} (Claude Code)`);
  assert.match(environment.binary, new RegExp(`/claude/versions/${pinned.replaceAll(".", "\\.")}$`));
  assert.equal(environment.flags.DISABLE_AUTOUPDATER, "1");
  assert.equal(environment.flags.CLAUDE_CONFIG_DIR, "$ROOT/home/.claude");
});
check("the trace came from the helpers retained beside this verifier", () => {
  assert.deepEqual(Object.keys(environment.experimentSHA256).sort(), ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs"]);
  for (const [name, hash] of Object.entries(environment.experimentSHA256)) if (name !== "run.mjs")
    assert.equal(createHash("sha256").update(readFileSync(path.join(here, name))).digest("hex"), hash, `${name} changed since the run`);
});
if (createHash("sha256").update(readFileSync(path.join(here, "run.mjs"))).digest("hex") !== environment.experimentSHA256["run.mjs"]) {
  console.log("note - runner changed since this trace was recorded: run.mjs");
  assert(!flags.has("--strict"), "runner changed under --strict");
}
check("the hooks were subscribed as `dashpot integrate claude-code` subscribes them, and every publish succeeded", () => {
  assert.deepEqual(environment.subscriptions.events, ["SessionStart", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "SessionEnd"]);
  for (const record of records.filter((entry) => entry.kind === "hook")) {
    if (environment.subscriptions.observedOnly.includes(record.event)) assert.equal(record.publisher, null);
    else assert.equal(record.publisher?.status, 0, `publisher failed at #${record.receipt}`);
  }
});
check("the publisher ran this checkout's working-tree source, and every scenario ran", () => {
  assert.equal(environment.publisher, "$CHECKOUT/src/dashpot/sessions/hook_records.py");
  assert.deepEqual(environment.scenarios, ["idle-startup", "idle-resume", "idle-headless", "clear-idle", "fork-worker"]);
});
const checkoutRoot = path.resolve(here, "..", "..", "..");
const drift = Object.entries(environment.worktreeSourceSHA256).filter(([name, hash]) => {
  try { return createHash("sha256").update(readFileSync(path.join(checkoutRoot, name))).digest("hex") !== hash; } catch { return true; }
}).map(([name]) => name);
if (drift.length) {
  console.log(`note - working-tree sources changed since the run: ${drift.join(", ")}`);
  assert(!flags.has("--strict"), "sources changed under --strict");
}

// An interactive session opened with no prompt.
const is = span("idle-startup");
const isStart = one(hooksOf(is), (record) => record.event === "SessionStart", "SessionStart");
const idleSession = isStart.payload.session_id;
check("idle-startup: an interactive session opened with no prompt publishes SessionStart(startup) and nothing else while left idle", () => {
  assert.equal(isStart.payload.source, "startup");
  const { start, hooks } = quiet(is, "is-idle");
  assert(isStart.receipt < start.receipt);
  assert.deepEqual(hooks, []);
  assert(!hooksOf(is).some((record) => record.receipt < start.receipt && record.event !== "SessionStart"));
});
check("idle-startup (ADR 0106): the SessionStart stores the session waiting with no turn clock; its first prompt runs it, its Stop waits", () => {
  unprompted(stored(isStart, idleSession));
  const prompt = one(hooksOf(is), (record) => record.event === "UserPromptSubmit", "prompt");
  assert.deepEqual(prompt.prompt.labels, ["is-turn"]);
  const running = stored(prompt, idleSession);
  assert.equal(running.state, "running");
  assert(running.turnStartedAt > stored(isStart, idleSession).lastSessionStartAt, "the turn clock starts at the prompt");
  const stop = one(hooksOf(is), (record) => record.event === "Stop", "Stop");
  assert.equal(stored(stop, idleSession).state, "waiting");
});

// The same session resumed at launch.
const ir = span("idle-resume");
check("idle-resume: `claude --resume <id>` publishes SessionStart(resume) for that session from a new Host Process, and nothing else while left idle", () => {
  const spawned = one(ir, (record) => record.kind === "client.spawn", "spawn");
  assert.deepEqual(spawned.extraArgs, ["--resume", idleSession]);
  const start = one(hooksOf(ir), (record) => record.event === "SessionStart", "SessionStart");
  assert.equal(start.payload.source, "resume");
  assert.equal(start.payload.session_id, idleSession);
  assert.notEqual(start.hostPid, isStart.hostPid);
  assert.deepEqual(quiet(ir, "ir-idle").hooks, []);
  unprompted(stored(start, idleSession));
});

// A headless stream-json session sent no user turn.
const ih = span("idle-headless");
check("idle-headless: a stream-json `claude -p` publishes SessionStart(startup) before any input, and nothing else while left idle", () => {
  const { start, end, hooks } = quiet(ih, "ih-idle");
  assert.deepEqual(hooks.map((record) => record.event), ["SessionStart"]);
  const [session] = hooks;
  assert.equal(session.payload.source, "startup");
  assert(!ih.some((record) => record.kind === "turn.sent" && record.receipt < end.receipt));
  assert(start.receipt < session.receipt);
  unprompted(stored(session, session.payload.session_id));
  const prompt = one(hooksOf(ih), (record) => record.event === "UserPromptSubmit", "prompt");
  assert.equal(stored(prompt, session.payload.session_id).state, "running");
});

// `/clear` with no worker.
const ci = span("clear-idle");
check("clear-idle: `/clear` with no worker publishes SessionEnd(clear), then SessionStart(clear) of a new session in the same Host Process, and nothing else while left idle", () => {
  const action = one(ci, (record) => record.kind === "action", "action");
  const after = hooksOf(ci).filter((record) => record.receipt > action.receipt);
  const [end, start] = after;
  assert.equal(end.event, "SessionEnd");
  assert.equal(end.payload.reason, "clear");
  assert.equal(start.event, "SessionStart");
  assert.equal(start.payload.source, "clear");
  assert.notEqual(start.payload.session_id, end.payload.session_id);
  assert.equal(start.hostPid, end.hostPid);
  const { start: idleStart, hooks } = quiet(ci, "ci-idle");
  assert(start.receipt < idleStart.receipt);
  assert.deepEqual(hooks, []);
  assert.deepEqual(after.filter((record) => record.receipt < idleStart.receipt).map((record) => record.event), ["SessionEnd", "SessionStart"]);
});
check("clear-idle (ADR 0106): the cleared session's record goes, and the new session is stored waiting with no turn clock", () => {
  const action = one(ci, (record) => record.kind === "action", "action");
  const [end, start] = hooksOf(ci).filter((record) => record.receipt > action.receipt);
  assert.equal(stored(end, end.payload.session_id), undefined);
  assert.equal(stored(start, end.payload.session_id), undefined);
  unprompted(stored(start, start.payload.session_id));
});

// `/fork` while a background worker works.
const fw = span("fork-worker");
const fwHooks = hooksOf(fw);
const leadStart = one(fwHooks, (record) => record.event === "SessionStart" && record.payload.source === "startup", "lead start");
const lead = leadStart.payload.session_id;
const leadHost = leadStart.hostPid;
const workerStart = one(fwHooks, (record) => record.event === "SubagentStart", "worker start");
const worker = workerStart.payload.agent_id;
const forkAction = one(fw, (record) => record.kind === "action" && record.action === "/fork", "/fork");
const gate = one(fw, (record) => record.kind === "gate" && record.gate === "fw-go", "gate");
const forkStart = one(fwHooks, (record) => record.event === "SessionStart" && record.receipt > forkAction.receipt, "fork SessionStart");
const fork = forkStart.payload.session_id;
const forkHost = forkStart.hostPid;
const stop = one(fwHooks, (record) => record.event === "SubagentStop", "SubagentStop");
const daemonStop = one(fw, (record) => record.kind === "action.claude" && record.label === "fw-daemon-stop", "daemon stop");
const command = (label, phase = "end") => one(fw, (record) => record.kind === "command" && record.label === label && record.phase === phase, `command ${label} ${phase}`);

check("fork-worker: the lead's background worker was working, and listed, when `/fork` ran", () => {
  assert(workerStart.receipt < forkAction.receipt);
  assert.equal(command("fw-w-hold", "start").env.CLAUDE_CODE_SESSION_ID, lead);
  const before = fwHooks.filter((record) => record.receipt < forkAction.receipt).at(-1);
  assert.equal(before.event, "Stop");
  assert.deepEqual(stored(before, lead), { ...stored(before, lead), state: "running", liveSubagents: [worker], turnStartedAt: null });
  const menu = one(fw, (record) => record.kind === "screen" && record.label === "fw-menu", "menu");
  assert.match(menu.tail.replace(/\s+/g, ""), /Copythisconversationintoanewbackgroundsessionandkeepworkinghere/);
});
check("fork-worker: `/fork` publishes no SessionEnd for the lead, and no other event of it, before the gate opens", () => {
  const between = fwHooks.filter((record) => record.receipt > forkAction.receipt && record.receipt < gate.receipt);
  assert.deepEqual(between.map((record) => record.event), ["SessionStart"]);
  assert(!fwHooks.some((record) => record.event === "SessionEnd" && record.payload.session_id === lead && record.receipt < daemonStop.receipt));
});
check("fork-worker: `/fork` publishes SessionStart(fork) with a new session id from another Host Process, the background session the fixture's own daemon runs", () => {
  assert.equal(forkStart.payload.source, "fork");
  assert.notEqual(fork, lead);
  assert.notEqual(forkHost, leadHost);
  assert.equal(forkStart.env.CLAUDE_PID, String(forkHost));
  assert.equal(forkStart.env.CLAUDE_CODE_SESSION_ID, fork);
  assert.equal(forkStart.payload.cwd, fixture);
  assert.equal(stored(forkStart, fork).processPid, forkHost, "Dashpot names the fork's own Host Process");
  // The fork's process runs under the daemon the lead started, not in the lead.
  assert.equal(forkStart.ancestry[1].pid, forkHost);
  assert.equal(forkStart.ancestry[1].comm, pinned);
  assert(forkStart.ancestry.findIndex((entry) => entry.pid === leadHost) > 2);
  const agents = one(fw, (record) => record.kind === "action.claude" && record.label === "fw-agents", "agents").agents;
  const background = one(agents, (entry) => entry.kind === "background", "background session");
  assert.deepEqual([background.sessionId, background.pid], [fork, forkHost]);
  const interactive = one(agents, (entry) => entry.kind === "interactive", "interactive session");
  assert.deepEqual([interactive.sessionId, interactive.pid], [lead, leadHost]);
});
check("fork-worker: the fork begins no turn: no prompt, Stop or Sub-agent event of it at all, only its SessionEnd(other) once its daemon stops", () => {
  const forkHooks = fwHooks.filter((record) => record.payload.session_id === fork || record.hostPid === forkHost);
  assert.deepEqual(forkHooks.map((record) => record.event), ["SessionStart", "SessionEnd"]);
  const [, end] = forkHooks;
  assert.equal(end.payload.reason, "other");
  assert(end.receipt > daemonStop.receipt);
  assert.deepEqual(quiet(fw, "fw-idle").hooks, []);
});
check("fork-worker: the worker goes on in the lead's Host Process under the lead's session id, and its SubagentStop names the lead's session", () => {
  const checked = one(fw, (record) => record.kind === "worker.check", "worker check");
  assert.equal(checked.holdAlive, true);
  assert.equal(checked.holdEnded, false);
  assert(checked.receipt > forkStart.receipt);
  const hold = command("fw-w-hold");
  assert.equal(hold.opened, true);
  assert(hold.receipt > gate.receipt);
  for (const shell of [hold, command("fw-w-after")]) {
    assert.equal(shell.env.CLAUDE_CODE_SESSION_ID, lead);
    assert.equal(shell.env.CLAUDE_PID, String(leadHost));
  }
  const requests = fw.filter((record) => record.kind === "model.request" && record.label === "fw-worker" && record.receipt > forkAction.receipt);
  assert(requests.length);
  for (const request of requests) assert.equal(request.sessionHeaders["x-claude-code-session-id"], lead);
  assert(stop.receipt > gate.receipt);
  assert.equal(stop.payload.agent_id, worker);
  assert.equal(stop.payload.session_id, lead);
  assert.equal(stop.hostPid, leadHost);
  const notified = one(fwHooks, (record) => record.event === "UserPromptSubmit" && record.prompt?.taskNotification, "notification");
  assert(notified.receipt > stop.receipt);
  assert.equal(notified.payload.session_id, lead);
});
check("fork-worker (ADR 0101, ADR 0106): the fork takes nothing over and is stored waiting; the lead keeps the worker until its stop, which leaves no record listing it", () => {
  unprompted(stored(forkStart, fork));
  assert.deepEqual(stored(forkStart, lead), { ...stored(forkStart, lead), state: "running", liveSubagents: [worker] });
  assert.deepEqual(listing(forkStart, worker), [lead]);
  assert.deepEqual(listing(stop, worker), []);
  assert.equal(stored(stop, lead).state, "waiting");
  unprompted(stored(stop, fork));
});
check("fork-worker: the fork's daemon was the fixture's own, alongside the user's, and was gone once stopped; no fixture process outlived the run", () => {
  const directories = (label) => one(records, (record) => record.kind === "daemon.directories" && record.label === label, label);
  const before = directories("fw-before");
  const forked = directories("fw-forked");
  const after = directories("fw-daemon-stopped");
  assert.deepEqual(before.added, []);
  assert.equal(forked.added.length, 1);
  for (const entry of [before, forked, after, directories("cleanup")]) {
    assert.equal(entry.preexistingKept, true);
    assert.deepEqual(entry.removed, []);
  }
  assert.deepEqual(after.added, []);
  assert.equal(daemonStop.status, 0);
  assert.deepEqual(records.find((record) => record.kind === "cleanup.remaining").pids, []);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} checks passed`);

if (flags.has("--sequences")) {
  const names = new Map();
  const name = (session) => {
    if (!names.has(session)) names.set(session, `S${names.size}`);
    return names.get(session);
  };
  for (const hook of records.filter((entry) => entry.kind === "hook")) {
    const detail = hook.payload.source ?? hook.payload.reason ?? "";
    const store = (hook.store ?? []).map((entry) => `${name(entry.sessionId)} ${entry.state} ${JSON.stringify(entry.liveSubagents)}`).join("; ");
    console.log(`#${hook.receipt} ${hook.event}${detail ? `(${detail})` : ""} ${name(hook.payload.session_id)} pid=${hook.hostPid}${hook.payload.agent_id ? ` agent=${hook.payload.agent_id}` : ""} -> ${store || "no records"}`);
  }
}
