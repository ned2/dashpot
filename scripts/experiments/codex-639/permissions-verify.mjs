// Independently verify the retained Issue #665 trace against current sources.
// This verifier imports neither the runner nor its probe implementation.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "../../..");
const tracePath = process.argv[2];
assert(tracePath, "Pass trace.jsonl");
const bytes = readFileSync(tracePath);
const source = bytes[0] === 0x1f && bytes[1] === 0x8b ? gunzipSync(bytes).toString("utf8") : bytes.toString("utf8");
const records = source.trim().split("\n").map(JSON.parse);
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const matches = of(kind).filter(predicate); assert.equal(matches.length, 1, `${kind}: exactly one matching record`); return matches[0];
};
records.forEach((record, index) => {
  assert.equal(record.receipt, index + 1, "unbroken receipt order");
  if (index) assert(record.receiptTime >= records[index - 1].receiptTime, "monotonic receipt times");
});
const env = one("environment");
assert.equal(env.version, "codex-cli 0.162.0");
assert.equal(env.platform, "linux");
assert.equal(env.updater.updater.autoUpdateEnabled, false);
assert(env.config.includes('check_for_update_on_startup = false'));
assert(!env.ancestry.some((entry) => /^(codex|claude|opencode)/.test(entry.comm)), "fixture detached from all harnesses");
const binary = process.argv[3] ?? env.binary.replace(/^~(?=\/)/, os.homedir());
assert.equal(createHash("sha256").update(readFileSync(binary)).digest("hex"), env.binarySHA256, "retained release bytes");
const fixtureSources = ["ancestry.mjs", "permissions-hook.mjs", "permissions-probe.mjs", "permissions-reconnect.mjs", "permissions-run.mjs", "permissions-verify.mjs"];
assert.deepEqual(Object.keys(env.sourceSHA256).sort(), fixtureSources, "complete fixture source identity");
const pythonSources = (directory) => readdirSync(directory).flatMap((name) => {
  const file = path.join(directory, name);
  if (statSync(file).isDirectory()) return name === "__pycache__" ? [] : pythonSources(file);
  return name.endsWith(".py") ? [path.relative(checkout, file)] : [];
});
assert.deepEqual(Object.keys(env.dashpotSHA256).sort(), pythonSources(path.join(checkout, "src/dashpot")).sort(), "complete publisher source identity");
assert.deepEqual(env.fixtureHomes, ["$ROOT/codex-home", "$ROOT/reconnect-workspace", "$ROOT/reconnect-full"], "all isolated homes belong to cleanup");
for (const [file, digest] of Object.entries(env.sourceSHA256)) assert.equal(createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex"), digest, file);
for (const [file, digest] of Object.entries(env.dashpotSHA256)) assert.equal(createHash("sha256").update(readFileSync(path.join(checkout, file))).digest("hex"), digest, file);
assert.equal(of("failure").length, 0, "fixture completed without failures");
assert.equal(of("server.error").length, 0);
assert.deepEqual(one("completed").selected.sort(), ["approve", "background", "decline", "default", "interrupt", "reconnect", "strict"]);
assert.equal(one("cleanup").fixtureProcesses, 0, "no fixture processes left for forced cleanup");
assert(of("terminal.exit").every((r) => r.status === 0 && r.signal === null), "each fixture terminal exited normally");

const strings = (value) => {
  if (typeof value === "string") { let decoded; try { decoded = JSON.parse(value); } catch {} return decoded ? strings(decoded) : [value]; }
  return value && typeof value === "object" ? Object.values(value).flatMap(strings) : [];
};
const requests = (label) => of("model.request").filter((r) => r.label === label && !r.side && !r.guardian);
const final = (label) => {
  const rows = requests(label); assert(rows.length, label); assert.equal(rows.at(-1).action, null, `${label} reached its final request`); return rows.at(-1);
};
const rawProbes = new Map();
for (const r of of("model.request")) for (const text of strings(r.outputs)) for (const match of text.matchAll(/PROBE (\{[^\n]*\})/g)) {
  const report = JSON.parse(match[1]);
  if (rawProbes.has(report.label)) assert.deepEqual(rawProbes.get(report.label), report, "stable raw probe report");
  rawProbes.set(report.label, report);
}
const probe = (label) => {
  const report = one("probe", (r) => r.report.label === label).report;
  assert.deepEqual(report, rawProbes.get(label), `${label}: summary is backed by actual tool output`);
  assert.equal(report.noNewPrivs, "1"); assert.equal(report.seccomp, "2");
  assert.deepEqual(report.deniedRead, { ok: false, code: "EACCES" });
  assert.deepEqual(report.network, { ok: false, code: "EPERM" });
  return report;
};
const output = (label) => final(label).outputs.map((r) => typeof r.output === "string" ? r.output : JSON.stringify(r.output)).join("\n");
const mail = (label) => final(label).messages;
const hook = (event, session) => of("hook").filter((r) => r.event === event && r.payload.session_id === session);
const observed = (label) => one("observation", (r) => r.label === label);
const stored = (observation) => {
  const rows = observation.stored.filter((r) => r.sessionId === observation.lead); assert.equal(rows.length, 1); return rows[0];
};
const workerFor = (session) => {
  const rows = hook("SubagentStart", session); assert.equal(rows.length, 1, "exactly one native Worker start"); return rows[0].payload.agent_id;
};
const subagentBlocker = (observation, worker, present) => {
  assert.equal(observation.idleCleanup.status, 0);
  const blockers = observation.idleCleanup.result.obstacles.filter((o) => o.kind === "sub-agent" && o.agents.includes(worker));
  assert.equal(blockers.length > 0, present, `${observation.label}: relevant Worker Cleanup blocker`);
};
const activity = (observation, worker, state) => {
  assert.equal(observation.snapshot.status, 0);
  const runs = observation.snapshot.result.agentRuns.filter((r) => r.workers.some((w) => w.workerId === worker));
  assert.equal(runs.length, 1);
  assert.equal(runs[0].workers.find((w) => w.workerId === worker).state, state);
};

// Approving and declining the same explicitly escalated write while the
// parent is in wait_agent have different hand-back and hook outcomes.
for (const [name, approved] of [["waiting-approve", true], ["waiting-decline", false]]) {
  const label = `lead-${name}`, session = requests(label)[0].thread, worker = workerFor(session);
  const waiting = requests(label).find((r) => r.action === "wait_agent"); assert(waiting);
  const answer = one("approval.answer", (r) => r.name === name);
  assert(waiting.receipt < answer.receipt);
  assert.equal(requests(label).filter((r) => r.receipt > waiting.receipt && r.receipt < answer.receipt).length, 0,
    "the parent model remains in its wait until the person answers");
  const screen = one("screen", (r) => r.name === name && r.label === "approval-pending").text.replace(/\s+/g, " ");
  assert.match(screen, /Would you like to run/); assert.match(screen, /Thread:\s*Agent/);
  assert.match(screen, /o to open thread/);
  assert.equal(probe(`plain-worker-${name}`).write.ok, false, "an ordinary command does not escalate itself");
  assert.match(output(label), approved ? /"timed_out":false/ : /"timed_out":true/);
  assert.match(output(label), approved ? /"completed":"DONE:worker-waiting-approve"/ : /"agent_status":"interrupted"/);
  assert.equal(mail(label).length, approved ? 1 : 0, "actual parent hand-back messages");
  assert.equal(hook("SubagentStop", session).length, approved ? 1 : 0, "actual lifecycle stop, independent of mail");
  if (approved) assert.equal(probe(`worker-${name}`).write.ok, true, "approved writes broaden while read/network restrictions remain");
  else assert(!rawProbes.has(`worker-${name}`), "declined command never executed");
  const pending = observed(`${name}-pending`), after = observed(`${name}-after`), exited = observed(`${name}-exited`);
  assert(stored(pending).liveSubagents.includes(worker));
  activity(pending, worker, "running"); subagentBlocker(pending, worker, true);
  assert.equal(stored(after).liveSubagents.includes(worker), !approved);
  activity(after, worker, approved ? null : "running"); subagentBlocker(after, worker, !approved);
  subagentBlocker(exited, worker, false);
  if (!approved) assert(stored(exited).liveSubagents.includes(worker), "ended hook record retains its stale child listing");
}
assert.equal(one("command-allow-rule").written, false, "a command allow rule does not widen writes");
assert.match(env.allowRule, /decision = "allow"/);
for (const label of ["lead-waiting-approve", "lead-waiting-decline"]) assert.match(output(label), /command-allow-rule.*Read-only file system/);

// Explicit launch overrides are a local TUI/protocol measurement. Workspace
// omission is retained as a boundary, not silently interpreted as a grant.
for (const mode of ["workspace", "full"]) {
  const disconnect = one("reconnect.disconnect", (r) => r.mode === mode);
  const rows = of("reconnect.rpc").filter((r) => r.mode === mode);
  const start = rows.find((r) => r.message.method === "thread/start");
  assert(start && start.receipt < disconnect.receipt);
  assert.equal(start.message.params.approvalPolicy, "never");
  assert.equal(start.message.params.sandbox, mode === "full" ? "danger-full-access" : "workspace-write");
  assert(rows.some((r) => r.message.method === "thread/resume" && r.receipt > disconnect.receipt), "actual reconnect resume");
  const defaults = one("reconnect.server-defaults", (r) => r.mode === mode && r.method === "thread/resume");
  assert.equal(defaults.approvalPolicy, "on-request"); assert.equal(defaults.sandbox.type, "readOnly");
  const submitted = one("reconnect.outcome", (r) => r.mode === mode).submitted;
  assert.equal(submitted.input[0].text, "SPIKE:reconnect-after", "preserved draft submitted");
  assert.equal(submitted.approvalPolicy, "never"); assert.equal(submitted.approvalsReviewer, "user");
  assert.deepEqual(submitted.sandboxPolicy, mode === "full" ? { type: "dangerFullAccess" } : null);
  assert.equal(submitted.permissions, null);
}

// Each code-mode cell executes after a real completed turn boundary. Both
// positive retention and negative borrowing checks must be present.
const background = one("background.outcome");
assert.notEqual(background.firstTurn, background.nextTurn);
const grants = of("permission.grant"); assert.equal(grants.length, 2);
assert.deepEqual(grants.map((r) => [r.thread, r.turn, r.scope, r.permissions.fileSystem.write]), [
  [background.thread, background.firstTurn, "turn", ["$ROOT/grant-a"]],
  [background.thread, background.nextTurn, "turn", ["$ROOT/grant-b"]],
]);
const events = of("rpc.event").map((r) => ({ ...r.message, receipt: r.receipt }));
const firstComplete = events.find((r) => r.method === "turn/completed" && r.params.turn.id === background.firstTurn);
const nextStart = of("rpc.result").find((r) => r.method === "turn/start" && r.result.result?.turn.id === background.nextTurn);
assert(firstComplete && nextStart && firstComplete.receipt < nextStart.receipt);
for (const name of ["background-before", "background-after", "next-own"]) assert.equal(probe(name).write.ok, true);
for (const name of ["background-after", "next-own"]) assert.deepEqual(probe(name).laterWrite, { ok: false, code: "EROFS" });
assert.deepEqual(background.files, { before: true, after: true, own: true, borrowedA: false, borrowedB: false });
assert.match(output("background-next"), /Script completed/); assert(!output("background-next").includes("Script failed"));

// Three harmless fixture denials stop each Guardian child. Only the strict
// stop produces mail and wakes the wait; all interruption controls preserve
// missing SubagentStop and the resulting stale running attribution.
for (const [setting, notified] of [["strict", true], ["default", false]]) {
  const label = `lead-guardian-${setting}`, last = final(label), session = requests(label)[0].thread, worker = workerFor(session);
  const start = one("scenario", (r) => r.name === `guardian-${setting}`);
  const end = one("observation", (r) => r.label === `guardian-${setting}`);
  assert.equal(of("guardian.review").filter((r) => r.receipt > start.receipt && r.receipt < end.receipt && r.decision.outcome === "deny").length, 3);
  assert.match(output(label), /"agent_status":"interrupted"/);
  assert.match(output(label), notified ? /"timed_out":false/ : /"timed_out":true/);
  assert.equal(last.messages.length, notified ? 1 : 0);
  if (notified) {
    const notification = strings(last.messages).join("\n");
    assert.match(notification, /Agent interrupted by Guardian:.*3 consecutive/);
    assert.match(notification, /Do not resume this agent or retry its blocked work until the user explicitly confirms/);
  }
  assert.equal(hook("SubagentStop", session).length, 0);
  assert(stored(end).liveSubagents.includes(worker)); activity(end, worker, "running");
  subagentBlocker(end, worker, true); subagentBlocker(observed(`guardian-${setting}-exited`), worker, false);
  assert(stored(observed(`guardian-${setting}-exited`)).liveSubagents.includes(worker));
}
const ordinary = observed("ordinary-interrupt"), session = ordinary.lead, worker = workerFor(session);
assert.match(output("lead-interrupt"), /"previous_status":"running"/);
assert.match(output("lead-interrupt"), /"agent_status":"interrupted"/);
assert.match(output("lead-interrupt"), /"timed_out":true/);
assert.equal(mail("lead-interrupt").length, 0); assert.equal(hook("SubagentStop", session).length, 0);
activity(ordinary, worker, "running"); subagentBlocker(ordinary, worker, true);
subagentBlocker(observed("ordinary-interrupt-exited"), worker, false);
assert(stored(observed("ordinary-interrupt-exited")).liveSubagents.includes(worker));
assert(of("hook").every((r) => r.publisher.status === 0 && r.publisher.signal === null), "real publisher processed every captured hook");

// Codex's own turn records corroborate every real-server thread's baseline.
const threads = one("rollouts").threads;
for (const [label, code] of [["lead-waiting-decline", null], ["lead-guardian-strict", "too_many_denials"], ["lead-guardian-default", null], ["lead-interrupt", null]]) {
  const worker = workerFor(requests(label)[0].thread);
  const aborted = threads.find((t) => t.session === worker)?.aborted;
  assert.equal(aborted?.length, 1);
  assert.equal(aborted[0].reason, "interrupted");
  assert.equal(aborted[0].error?.codex_error_info ?? null, code, "strict Guardian alone publishes typed TooManyDenials");
}
for (const rows of of("model.request").filter((r) => !r.side && !r.guardian && r.thread)) {
  const thread = threads.find((r) => r.session === rows.thread); assert(thread?.turns.length, "each real thread has recorded turn context");
  for (const turn of thread.turns) {
    assert.equal(turn.approval_policy, "on-request");
    assert.deepEqual(turn.permission_profile, { type: "managed", network: "restricted", file_system: { type: "restricted", entries: [
      { path: { type: "path", path: "$ROOT/denied.txt" }, access: "deny" },
      { path: { type: "path", path: "$ROOT/repository" }, access: "write" },
      { path: { type: "path", path: "$ROOT/repository.worktrees/worker" }, access: "write" },
      { path: { type: "special", value: { kind: "root" } }, access: "read" },
    ] } }, "exact baseline roots, read denial and network policy");
  }
}
console.log(JSON.stringify({ verified: tracePath, version: env.version, scenarios: one("completed").selected, threads: threads.length,
  workspaceReconnect: "approval preserved; sandbox override omitted", subagentStop: "approval only; absent for interruptions" }));
