// Independent verifier for the Issue #379 trace: checks each claim
// docs/spikes/opencode-v2-background-permissions-spike.md makes about
// OpenCode 2.0.22's background shell commands, `opencode run` under default
// permissions, and retried and failed executions, against the recorded
// server events, model requests, shell commands, processes, observations and
// Cleanup reports.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace");
const text = readFileSync(tracePath, "utf8");
const records = text.trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };
const main = "$ROOT/repository";
const tree = (name) => `$ROOT/repository.worktrees/${name}`;

const kind = (name) => records.filter((record) => record.kind === name);
const one = (name, predicate = () => true) => {
  const found = records.find((record) => record.kind === name && predicate(record));
  assert(found, `no ${name} record`);
  return found;
};
const labelled = (name, label) => one(name, (record) => record.label === label);
const started = (label) => one("command", (record) => record.label === label && record.phase === "start");
const ended = (label) => records.find((record) => record.kind === "command" && record.label === label && record.phase === "end");
const sessionOf = (title) => one("session", (record) => record.title === title).sessionID;
const events = (sessionID, type) => kind("server.event").filter((record) => record.sessionID === sessionID && record.type === type);
const between = (list, from, to) => list.filter((record) => record.receipt > from && record.receipt < to);
const requests = (label) => kind("model.request").filter((record) => !record.titled && record.label === label);
const freshNotices = (label, of) => requests(label).flatMap((record) => (record.notices ?? []).filter((notice) => notice.fresh && notice.of === of)
  .map((notice) => ({ ...notice, receipt: record.receipt })));
// The Agent Run an observation lists for one Issue.
const runFor = (label, issue) => labelled("observation", label).runs.filter((run) => run.issueId === issue);
const blockers = (label) => labelled("cleanup", label).obstacles.map((obstacle) => obstacle.kind);
const processAt = (label) => labelled("process", label);
const exitOf = (name) => one("client.exit", (record) => record.name === name);

const environment = one("environment");
// The runner's scripts change only with a new trace, so they must match;
// Dashpot's sources keep changing after the trace is retained, so a
// difference is reported, and fails only under --strict.
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
for (const file of ["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs"]) {
  assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
}
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot sources differ from the run's: ${drifted.join(", ")}`);

const [firstService, restarted] = kind("service");

check("the trace names no path outside the fixture's placeholders", () => {
  assert.deepEqual(text.match(/(?<![\w$])\/(?:tmp|home)\/[^"\s]*/g) ?? [], []);
});
check("the pinned OpenCode release, driving the installed copy of this checkout's plugin and helper", () => {
  assert.equal(environment.version, "opencode v2.0.22");
  assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
  assert.equal(environment.installedMatchesSource, true);
  assert.equal(labelled("integrate", "install").status, 0);
  assert.equal(labelled("files", "installed").workerAgent, true);
});
check("every scenario completed, every helper run succeeded, and no fixture process outlived the run", () => {
  assert.deepEqual(kind("failure"), []);
  assert.deepEqual(kind("server.error"), []);
  assert.deepEqual(kind("scenario").map((record) => record.name), ["installer", "background", "background-move", "background-interrupt",
    "background-delete", "retry", "failed", "background-stop", "run-default", "ask-pending", "worker-report", "standalone-background"]);
  assert.equal(kind("done").length, 1);
  assert.deepEqual(one("events").unsuccessful, []);
  assert.deepEqual(one("cleanup.remaining").pids, []);
});

// Background shell commands on the shared service.
const bg = sessionOf("Background");
check("background: the shell call returns at once, and the execution that made it succeeds while the command still runs", () => {
  const [, answered] = requests("bg-launch");
  assert.match(answered.lastTool, /^Command moved to the background \(shell ID: sh_\w+\)\./);
  const launched = labelled("turn", "bg-launch").receipt;
  const succeeded = events(bg, "session.execution.succeeded").find((record) => record.receipt > launched - 3);
  assert(succeeded && succeeded.receipt < ended("bg-hold").receipt, "the execution ended before the command did");
  assert.equal(processAt("bg-running").alive, true);
});
check("background: the command is a child of the service in a process group and session of its own, in the session's Worktree", () => {
  const sampled = processAt("bg-running");
  assert.equal(sampled.cwd, tree("a"));
  assert.equal(sampled.pgrp, sampled.pid);
  assert.equal(sampled.sid, sampled.pid);
  const [parent] = started("bg-hold").ancestry;
  assert.equal(parent.comm, "opencode");
  assert.equal(parent.pid, firstService.pid);
});
check("background: while it runs, Dashpot shows the bound run waiting, and Cleanup names the live session and its run", () => {
  assert.deepEqual(runFor("bg-running", "I_fixture_1").map((run) => [run.state, run.workingDirectory]), [["waiting", tree("a")]]);
  assert.deepEqual(blockers("tree-a-bg-running"), ["agent-session", "agent-run"]);
});
check("background: OpenCode's shell API lists the running command, with its session and pid, at the location it started in, after a move or deletion too", () => {
  for (const [label, reporter, title, directory] of [["bg-running", "bg-hold", "Background", tree("a")],
    ["bg-move-running-old", "bg-move-hold", "BackgroundMove", tree("b")], ["bg-del-running", "bg-del-hold", "BackgroundDelete", tree("c")]]) {
    const listed = labelled("shells", label);
    assert.equal(listed.byHeader.status, 200);
    assert.deepEqual(listed.byHeader.shells.map(({ status, cwd, pid, session }) => ({ status, cwd, pid, session })),
      [{ status: "running", cwd: directory, pid: started(reporter).pid, session: sessionOf(title) }]);
    // The `directory` query does not select the location; the header does.
    assert.deepEqual(listed.byQuery.shells, []);
  }
  assert.deepEqual(labelled("shells", "bg-move-running-new").byHeader.shells, []);
});
check("background: the command's end wakes the idle session with a new execution carrying a completed shell notice", () => {
  const end = ended("bg-hold").receipt;
  assert.equal(between(events(bg, "session.execution.started"), end, Infinity).length, 1);
  const [notice] = freshNotices("bg-launch", "shell");
  assert.equal(notice.state, "completed");
  assert(notice.receipt > end);
  assert.deepEqual(runFor("bg-after", "I_fixture_1").map((run) => run.state), ["waiting"]);
});

const bgMove = sessionOf("BackgroundMove");
check("background-move: the session moves while its command runs on in Worktree b; the run moves with it, and Cleanup of b names nothing", () => {
  assert.equal(labelled("move", "bg-move").status, 204);
  assert.equal(labelled("session.info", "bg-move-moved").location, main);
  const sampled = processAt("bg-move-running");
  assert.equal(sampled.alive, true);
  assert.equal(sampled.cwd, tree("b"));
  assert.deepEqual(runFor("bg-move-running", "I_fixture_2").map((run) => [run.state, run.workingDirectory]), [["waiting", main]]);
  assert.deepEqual(blockers("tree-b-bg-move-running"), []);
});
check("background-move: the command's end wakes the session at its new location", () => {
  const end = ended("bg-move-hold").receipt;
  assert.equal(between(events(bgMove, "session.execution.started"), end, Infinity).length, 1);
  assert.equal(freshNotices("bg-move-launch", "shell")[0].state, "completed");
});

const bgInt = sessionOf("BackgroundInterrupt");
check("background-interrupt: interrupting the session kills its foreground command but not its background one, whose end wakes it", () => {
  assert.equal(labelled("interrupt", "bg-int").body.interrupted, true);
  assert.equal(events(bgInt, "session.execution.interrupted")[0].reason, "user");
  assert.equal(processAt("bg-int-busy-after-interrupt").alive, false);
  assert.equal(ended("bg-int-busy"), undefined);
  assert.equal(processAt("bg-int-hold-after-interrupt").alive, true);
  assert(ended("bg-int-hold"));
  assert.equal(labelled("woken", "bg-int").woke, true);
  assert.equal(freshNotices("bg-int-launch", "shell")[0].state, "completed");
});

const bgDel = sessionOf("BackgroundDelete");
check("background-delete: the command outlives its deleted session; Dashpot ends the run, Cleanup of c names nothing, and no notice is delivered", () => {
  assert.equal(labelled("session.delete", "bg-del").status, 0);
  assert.equal(labelled("session.info", "bg-del-deleted").missing, 404);
  const sampled = processAt("bg-del-running");
  assert.equal(sampled.alive, true);
  assert.equal(sampled.cwd, tree("c"));
  assert.deepEqual(runFor("bg-del-running", "I_fixture_3"), []);
  assert.deepEqual(blockers("tree-c-bg-del-running"), []);
  assert(ended("bg-del-hold"), "the command ran to its end");
  assert.equal(labelled("woken", "bg-del").woke, false);
  assert.equal(events(bgDel, "session.execution.started").length, 2);
});

// Retried and failed executions.
const retry = sessionOf("Retry");
check("retry: a 500 is retried within one execution, and Dashpot shows the run running through the retries", () => {
  const begun = requests("retry")[0].receipt;
  const [first] = between(events(retry, "session.execution.started"), begun - 3, Infinity);
  const done = events(retry, "session.execution.succeeded").find((record) => record.receipt > first.receipt);
  const retries = between(events(retry, "session.retry.scheduled"), first.receipt, done.receipt);
  assert.deepEqual(retries.map((record) => record.error), [{ type: "provider.internal", status: 500 }, { type: "provider.internal", status: 500 }]);
  assert.equal(between(events(retry, "session.execution.started"), first.receipt, done.receipt).length, 0);
  assert.deepEqual(requests("retry").map((record) => record.failure ?? null), [500, 500, null, null]);
  assert.deepEqual(runFor("retry-waiting", "I_fixture_5").map((run) => run.state), ["running"]);
  assert(labelled("observation", "retry-waiting").receipt < done.receipt);
  assert.deepEqual(runFor("retry-after", "I_fixture_5").map((run) => run.state), ["waiting"]);
});
check("failed: a 400 fails the execution without a retry; Dashpot shows the run waiting and keeps its Issue Binding", () => {
  const failed = events(retry, "session.execution.failed");
  assert.equal(failed.length, 1);
  assert.deepEqual(failed[0].error, { type: "provider.invalid-request", status: 400 });
  assert.equal(requests("fail").length, 1);
  assert.equal(between(events(retry, "session.retry.scheduled"), requests("fail")[0].receipt, Infinity).length, 0);
  assert.deepEqual(runFor("fail-after", "I_fixture_5").map((run) => run.state), ["waiting"]);
});
check("failed: an `opencode run` whose execution fails exits 1", () => {
  assert.equal(exitOf("run-fail").code, 1);
  assert.match(exitOf("run-fail").output, /Error: Fixture failure 400/);
});

// The service stopped while a background command runs.
const bgStop = sessionOf("BackgroundStop");
check("background-stop: stopping the service kills the command; the new service neither resumes it nor wakes the session", () => {
  assert.equal(processAt("bg-stop-after-stop").alive, false);
  assert.equal(ended("bg-stop-hold"), undefined);
  assert.notEqual(restarted.pid, firstService.pid);
  assert.equal(labelled("woken", "bg-stop-restart").woke, false);
});
check("background-stop: the session's next turn carries a cancelled notice that the server restarted", () => {
  const [notice] = freshNotices("bg-stop-again", "shell");
  assert.equal(notice.state, "cancelled");
  assert.match(notice.head, /^Command cancelled because the server restarted/);
  assert.equal(events(bgStop, "session.execution.started").at(-1).receipt > restarted.receipt, true);
});

// `opencode run` under a person's default permission rules.
const runAsk = one("known").sessions.runAsk;
check("run-default: without --auto, run rejects the read the default rules ask for, the turn goes on, and run exits 0", () => {
  const [asked] = events(runAsk, "permission.asked");
  assert.equal(asked.action, "read");
  assert.deepEqual(events(runAsk, "permission.replied").map((record) => record.reply), ["reject"]);
  assert.match(requests("run-ask").find((record) => record.step === 3).lastTool, /"type":"permission.rejected"/);
  assert(ended("run-ask-after"));
  assert.equal(exitOf("run-ask").code, 0);
  assert.match(exitOf("run-ask").output, /permission requested: read \(\.env\); auto-rejecting/);
});
check("run-default: the run's session stays bound in Worktree c, waiting, and keeps the Worktree from Cleanup after run exits", () => {
  assert.deepEqual(runFor("run-ask-after", "I_fixture_6").map((run) => [run.state, run.workingDirectory, run.orphaned]), [["waiting", tree("c"), false]]);
  assert.deepEqual(blockers("tree-c-run-ask-after"), ["agent-session", "agent-run"]);
});
check("run-default: with --auto, run approves the read once", () => {
  const spawned = one("client.spawn", (record) => record.name === "run-auto").receipt;
  const runAuto = one("server.event", (record) => record.type === "permission.asked" && record.receipt > spawned).sessionID;
  assert.deepEqual(events(runAuto, "permission.replied").map((record) => record.reply), ["once"]);
  assert.equal(exitOf("run-auto").code, 0);
});

const ask = sessionOf("Ask");
check("ask-pending: while an ask waits for its answer, Dashpot shows the run running; the answer resumes the turn, which then waits", () => {
  assert.deepEqual(labelled("permissions.pending", "ask-pending").asks.map((item) => item.action), ["read"]);
  assert.deepEqual(runFor("ask-pending", "I_fixture_7").map((run) => [run.state, run.workingDirectory]), [["running", tree("a")]]);
  assert.equal(events(ask, "session.execution.succeeded").filter((record) => record.receipt > labelled("observation", "ask-pending").receipt
    && record.receipt < labelled("permission.reply", "ask-pending").receipt).length, 0);
  assert.deepEqual(events(ask, "permission.replied").map((record) => record.reply), ["once"]);
  assert(ended("ask-after"));
  assert.deepEqual(runFor("ask-after", "I_fixture_7").map((run) => run.state), ["waiting"]);
});

const lead = sessionOf("Lead");
check("worker-report: a worker's `opencode run --session <lead>` report rejects the ask of the lead turn it starts, which goes on without the action", () => {
  const worker = started("worker-report").env.OPENCODE_SESSION_ID;
  assert.notEqual(worker, lead);
  assert.equal(one("server.event", (record) => record.type === "session.created" && record.sessionID === worker).parentID, lead);
  assert.equal(events(lead, "permission.asked")[0].action, "read");
  assert.deepEqual(events(lead, "permission.replied").map((record) => record.reply), ["reject"]);
  assert(started("lead-ask-after").env.OPENCODE_SESSION_ID === lead && ended("lead-ask-after"));
  const report = ended("worker-report").exec;
  assert.equal(report.status, 0);
  assert.match(report.stderr, /permission requested: read \(\.env\); auto-rejecting/);
  assert.deepEqual(labelled("permissions.pending", "lead-after-report").asks, []);
  assert.deepEqual(runFor("lead-after-report", "I_fixture_8").map((run) => run.state), ["waiting"]);
});

// A `--standalone` run.
check("standalone-background: run --standalone exits when its turn ends, and its background command dies with the private server", () => {
  const hold = started("sa-bg-hold");
  assert(hold.receipt < exitOf("sa-bg").receipt);
  const [parent, client] = hold.ancestry;
  assert.equal(parent.comm, "opencode");
  assert.notEqual(parent.pid, restarted.pid);
  assert.equal(client.comm, "opencode");
  assert.equal(processAt("sa-bg-running").alive, true);
  assert.equal(exitOf("sa-bg").code, 0);
  assert.equal(processAt("sa-bg-after-exit").alive, false);
  assert.equal(ended("sa-bg-hold"), undefined);
  assert.equal(labelled("standalone.ended", "sa-bg").reported, false);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(drifted.length ? `Dashpot sources differ from the run's: ${drifted.join(", ")}` : "Dashpot sources match the run's");
