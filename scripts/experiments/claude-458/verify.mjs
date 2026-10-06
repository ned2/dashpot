// Independent verifier for the Issue #458 trace: checks each finding about a
// Claude Code `/resume` driven through its interactive picker while a
// background Sub-agent works, and what Dashpot's hook record store held with
// ADR 0101's rule, against the recorded hook, shell, model-request and
// hook-store evidence; that `/fork` was described, not run; and that the
// trace came from the runner retained beside this file. With --sequences it
// also prints the switch's hook sequence from the worker's start on.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]  [--sequences]
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
const span = (name) => {
  const start = records.findIndex((record) => record.kind === "scenario" && record.name === name);
  assert(start >= 0, `scenario ${name}`);
  const end = records.findIndex((record, index) => index > start && record.kind === "scenario.end" && record.name === name);
  assert(end > start, `scenario ${name} ended`);
  assert.equal(records[end].ok, true, `scenario ${name}: ${records[end].error}`);
  return records.slice(start, end + 1);
};
const stored = (record, session) => (record.store ?? []).find((entry) => entry.sessionId === session);
const listing = (record, agent) => (record.store ?? []).filter((entry) => (entry.liveSubagents ?? []).includes(agent)).map((entry) => entry.sessionId);

// The run itself.
const environment = records[0];
check("the trace is of the pinned Claude Code release", () => {
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
check("the publisher ran this checkout's working-tree source", () => {
  assert.equal(environment.publisher, "$CHECKOUT/src/dashpot/sessions/hook_records.py");
  assert.deepEqual(environment.scenarios, ["resume-picker", "fork-menu"]);
});
const checkoutRoot = path.resolve(here, "..", "..", "..");
const drift = Object.entries(environment.worktreeSourceSHA256).filter(([name, hash]) => {
  try { return createHash("sha256").update(readFileSync(path.join(checkoutRoot, name))).digest("hex") !== hash; } catch { return true; }
}).map(([name]) => name);
if (drift.length) {
  console.log(`note - working-tree sources changed since the run: ${drift.join(", ")}`);
  assert(!flags.has("--strict"), "sources changed under --strict");
}

// `/resume` through the picker.
const rp = span("resume-picker");
const hooks = rp.filter((record) => record.kind === "hook");
const prior = rp.find((record) => record.kind === "prior").session;
const leadSpawn = rp.filter((record) => record.kind === "client.spawn" && record.mode === "interactive").at(-1);
assert.equal(leadSpawn.name, "rp");
const first = hooks.find((record) => record.event === "SessionStart" && record.payload.source === "startup" && record.ancestry.some((entry) => entry.pid === leadSpawn.pid));
assert(first, "the lead's startup SessionStart");
const host = first.hostPid;
const lead = first.payload.session_id;
const action = rp.find((record) => record.kind === "action");
const chosen = rp.find((record) => record.kind === "action.choose");
const gate = rp.find((record) => record.kind === "gate" && record.gate === "rp-go");
const started = hooks.find((record) => record.event === "SubagentStart" && record.hostPid === host);
const worker = started.payload.agent_id;
const after = hooks.filter((record) => record.hostPid === host && record.receipt > action.receipt);
const end = after.find((record) => record.event === "SessionEnd");
const start = after.find((record) => record.event === "SessionStart");
const stop = after.find((record) => record.event === "SubagentStop" && record.payload.agent_id === worker);
const workerCheck = rp.find((record) => record.kind === "worker.check");
const command = (label, phase = "end") => {
  const found = rp.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
  assert(found, `command ${label} ${phase}`);
  return found;
};

check("resume-picker: the prior session is an interactive one of another Host Process, which ended before the lead started", () => {
  const priorStart = hooks.find((record) => record.event === "SessionStart" && record.payload.session_id === prior);
  assert.equal(priorStart.payload.source, "startup");
  assert.notEqual(priorStart.hostPid, host);
  const priorEnd = hooks.find((record) => record.event === "SessionEnd" && record.payload.session_id === prior);
  assert(priorEnd.receipt < first.receipt);
  assert.notEqual(prior, lead);
});
check("resume-picker: the picker opened, listed the prior session, and the switch came only once it was chosen", () => {
  const picker = rp.find((record) => record.kind === "screen" && record.label === "rp-picker");
  assert.match(picker.tail, /Resume session/);
  const search = rp.find((record) => record.kind === "screen" && record.label === "rp-picker-search");
  assert.match(search.tail, /SPIKE:rp-prior/);
  assert(started.receipt < action.receipt && action.receipt < chosen.receipt);
  assert(!after.some((record) => record.receipt < chosen.receipt && ["SessionEnd", "SessionStart"].includes(record.event)));
});
check("resume-picker: SessionEnd(resume) of the lead's session, then SessionStart(resume) of the prior session in the same Host Process", () => {
  assert(end && start && end.receipt < start.receipt);
  assert.equal(after.filter((record) => record.event === "SessionEnd" && record.receipt < gate.receipt).length, 1);
  assert.equal(end.payload.reason, "resume");
  assert.equal(end.payload.session_id, lead);
  assert.equal(start.payload.source, "resume");
  assert.equal(start.payload.session_id, prior);
  assert.equal(start.hostPid, host);
  assert.equal(end.payload.cwd, fixture);
  assert.equal(start.payload.cwd, fixture);
  assert.equal(stored(start, prior).processPid, host, "Dashpot names the same Host Process");
  assert(!after.some((record) => record.receipt < gate.receipt && ["UserPromptSubmit", "Stop"].includes(record.event)));
});
check("resume-picker: the worker survives and goes on under the prior session's id, which its SubagentStop names", () => {
  assert.equal(workerCheck.holdAlive, true);
  assert.equal(workerCheck.holdEnded, false);
  assert(workerCheck.receipt > start.receipt);
  const hold = command("rp-w-hold");
  assert.equal(hold.opened, true);
  assert.equal(hold.env.CLAUDE_CODE_SESSION_ID, lead);
  assert(hold.receipt > gate.receipt);
  assert.equal(command("rp-w-after").env.CLAUDE_CODE_SESSION_ID, prior);
  assert(stop && stop.receipt > gate.receipt);
  assert.equal(stop.payload.session_id, prior);
  assert.equal(stop.hostPid, host);
  const requests = rp.filter((record) => record.kind === "model.request" && record.label === "rp-worker" && record.receipt > gate.receipt);
  assert(requests.length);
  for (const request of requests) assert.equal(request.sessionHeaders["x-claude-code-session-id"], prior);
  const notified = after.find((record) => record.event === "UserPromptSubmit" && record.prompt?.taskNotification);
  assert(notified && notified.receipt > stop.receipt);
  assert.equal(notified.payload.session_id, prior);
});
check("resume-picker (ADR 0101): the end keeps the worker, and the switch's start takes it over from the record it leaves", () => {
  assert.deepEqual(stored(end, lead), { ...stored(end, lead), state: "ended", reason: "resume", liveSubagents: [worker] });
  assert.equal(stored(start, lead), undefined, "the ended record the switch left is gone");
  assert.deepEqual(stored(start, prior), { ...stored(start, prior), state: "running", liveSubagents: [worker] });
  assert.deepEqual(listing(start, worker), [prior]);
});
check("resume-picker (ADR 0101): the worker's SubagentStop leaves no record listing it, and the lead's next Stop reads waiting", () => {
  assert.deepEqual(listing(stop, worker), []);
  assert.deepEqual(stored(stop, prior).liveSubagents, []);
  const stopped = after.find((record) => record.event === "Stop" && record.receipt > stop.receipt);
  assert.equal(stored(stopped, prior).state, "waiting");
});

// `/fork`, described and not run.
const fm = span("fork-menu");
check("fork-menu: this release's /fork copies the conversation into a new background session, and typing it without Enter publishes nothing", () => {
  const menu = fm.find((record) => record.kind === "screen" && record.label === "fm-menu");
  assert.match(menu.tail.replace(/\s+/g, ""), /Copythisconversationintoanewbackground/);
  const fmHooks = fm.filter((record) => record.kind === "hook");
  const fmStart = fmHooks.find((record) => record.event === "SessionStart");
  assert.equal(fmStart.payload.source, "startup");
  const menuAt = menu.receipt;
  assert(!fmHooks.some((record) => record.receipt > fmStart.receipt && record.receipt < menuAt));
  assert.equal(fmHooks.filter((record) => record.event === "SessionStart").length, 1);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} checks passed`);

if (flags.has("--sequences")) {
  const names = new Map([[lead, "lead"], [prior, "prior"]]);
  for (const hook of hooks.filter((entry) => entry.hostPid === host && entry.receipt >= started.receipt)) {
    const detail = hook.payload.source ?? hook.payload.reason ?? "";
    const store = (hook.store ?? []).map((entry) => `${names.get(entry.sessionId) ?? entry.sessionId} ${entry.state} ${JSON.stringify(entry.liveSubagents)}`).join("; ");
    console.log(`#${hook.receipt} ${hook.event}${detail ? `(${detail})` : ""} ${names.get(hook.payload.session_id) ?? hook.payload.session_id}${hook.payload.agent_id ? ` agent=${hook.payload.agent_id}` : ""} -> ${store || "no records"}`);
  }
}
