// Independent verifier for the Issue #448 trace: checks each finding about
// which OpenCode 2.0.22 actions make Dashpot write a `SessionStart` for a
// live root session while its child session (a Sub-agent) executes, against
// the events the probe plugin received, the hook events the helper wrote,
// the hook records after each write, the shells' hold windows and Cleanup.
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
const MAIN = "$ROOT/repository/.dashpot/state/sessions/";
const OTHER = "$ROOT/other/.dashpot/state/sessions/";

const kind = (name) => records.filter((record) => record.kind === name);
const one = (name, predicate = () => true) => {
  const found = records.find((record) => record.kind === name && predicate(record));
  assert(found, `no ${name} record`);
  return found;
};
const labelled = (name, label) => one(name, (record) => record.label === label);
const shell = (label, phase = "end") => one("command", (record) => record.label === label && record.phase === phase);
const environment = one("environment");
const known = one("known").sessions;
// Every hook event the helper wrote for a root, in order, with the record
// read after the write and the time the request began.
const writes = (root) => kind("publication").filter((record) => record.request?.session?.root === root)
  .flatMap((record) => record.writes.map((write) => ({ ...write, receipt: record.receipt, startedAt: record.startedAt,
    type: record.request.event?.type ?? null, id: record.request.session.id, pid: record.request.pid })));
const events = (sessionID) => kind("plugin.event").filter((record) => record.sessionID === sessionID);
// The child's hold: from its shell's start to its end.
const hold = (prefix) => [shell(`${prefix}-child-hold`, "start").startedAt, shell(`${prefix}-child-hold`).endedAt];
const within = (prefix, at) => { const [start, end] = hold(prefix); return at > start && at < end; };
const live = (write) => write.record?.liveSubagents ?? null;
const state = (label, file) => labelled("state", label).sessions[`$ROOT/${file}`];
const blockers = (label) => labelled("cleanup", label).obstacles.map((obstacle) => obstacle.kind);
// The root's publications written while its child held.
const duringHold = (prefix) => writes(known[prefix]).filter((write) => within(prefix, write.at));
const sessionStartsDuringHold = (prefix) => duringHold(prefix).filter((write) => write.name === "SessionStart");
// The child's stop: written after its hold ended, leaving no live Sub-agent.
const childStop = (prefix) => writes(known[prefix]).find((write) => write.name === "SubagentStop" && write.agentId === known[`${prefix}-child`]);

// The runner's scripts change only with a new trace, so they must match;
// Dashpot's sources keep changing after the trace is retained, so a
// difference is reported, and fails only under --strict.
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
for (const file of ["run.mjs", "command.mjs", "ancestry.mjs", "probe-plugin.js", "helper_probe.py"]) {
  assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
}
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot sources differ from the run's: ${drifted.join(", ")}`);

check("the trace names no path outside the fixture's placeholders", () => {
  assert.deepEqual(text.match(/(?<![\w$])\/(?:tmp|home)\/[^"\s]*/g) ?? [], []);
});
check("the pinned OpenCode release, its plugins on 2.0.22, driving the installed copy of the Dashpot build with only the helper rebound", () => {
  assert.equal(environment.version, "opencode v2.0.22");
  assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
  assert.equal(environment.installedMatchesSource, true);
  assert.equal(labelled("integrate", "install").status, 0);
  assert.equal(one("files").onlyHelperChanged, true);
  assert(kind("plugin.setup").length > 0 && kind("plugin.setup").every((record) => record.version === "2.0.22"));
});
check("every scenario completed, every helper run succeeded, and no fixture process outlived the run", () => {
  assert.deepEqual(kind("failure"), []);
  assert.deepEqual(kind("missing"), []);
  assert.deepEqual(kind("scenario").map((record) => record.name), ["installer", "compact", "compact-busy", "auto-compact", "overflow-compact",
    "others", "reload", "move-other-project", "standalone"]);
  assert.equal(kind("done").length, 1);
  assert.deepEqual(one("events").unsuccessful, []);
  assert(kind("publication").every((record) => record.code === 0 && record.acknowledgment?.result === "accepted"));
  assert.deepEqual(one("cleanup.remaining").pids, []);
});
check("every child held its shell across its scenario's action, and its later stop was written after the hold", () => {
  for (const prefix of ["c", "cb", "a", "o", "x", "r", "m", "s"]) {
    for (const action of kind("action").filter((record) => record.label.startsWith(`${prefix}-`) && "childHolding" in record)) {
      assert.equal(action.childHolding, true, `${action.label}: the child held`);
    }
    const [, end] = hold(prefix);
    assert(shell(`${prefix}-child-after`, "start").startedAt >= end, `${prefix}: the child went on after its hold`);
    assert(childStop(prefix).startedAt > end, `${prefix}: the child's stop came after its hold`);
  }
});

// Compaction.
const compactions = (prefix) => events(known[prefix]).filter((record) => record.type.startsWith("session.compaction."));
// The root's execution the compaction ran inside: the last to start before
// it, with no end until the compaction ended.
const enclosing = (prefix) => {
  const [started, ended] = compactions(prefix);
  const executions = events(known[prefix]).filter((record) => record.type.startsWith("session.execution."));
  const opened = executions.filter((record) => record.receipt < started.receipt).at(-1);
  assert.equal(opened?.type, "session.execution.started");
  assert(!executions.some((record) => record.receipt > opened.receipt && record.receipt < ended.receipt && record.type !== "session.execution.started"));
  return opened;
};
const childCreated = (prefix) => one("plugin.event", (record) => record.type === "session.created" && record.sessionID === known[`${prefix}-child`]);
const compactionChecks = (prefix, reason) => {
  const root = known[prefix];
  enclosing(prefix);
  const seen = compactions(prefix);
  assert.deepEqual(seen.map((record) => [record.type, record.reason]), [["session.compaction.started", reason], ["session.compaction.ended", reason]]);
  for (const record of seen) assert(within(prefix, record.at), `${prefix}: ${record.type} while the child held`);
  // No new incarnation of the root: OpenCode sends no creation or fork for it
  // after its first, and Dashpot writes no SessionStart while the child holds.
  assert.equal(events(root).filter((record) => record.type === "session.created").length <= 1, true);
  assert.equal(events(root).filter((record) => record.type === "session.forked").length, 0);
  assert.deepEqual(sessionStartsDuringHold(prefix), []);
  assert(duringHold(prefix).every((write) => ["UserPromptSubmit", "Stop", "SubagentStart"].includes(write.name)));
  // The compaction's own events are not published: the helper only ever
  // receives the plugin's eight session event types.
  assert(kind("publication").every((record) => !record.request.event || !record.request.event.type.startsWith("session.compaction")));
  assert.deepEqual(state(`${prefix}-after`, `repository/${root}.json`).liveSubagents, [known[`${prefix}-child`]]);
  assert.equal(state(`${prefix}-after`, `repository/${root}.json`).state, "running");
  assert(blockers(`${prefix}-after`).includes("sub-agent"));
  assert.deepEqual(live(childStop(prefix)), []);
  assert.deepEqual(blockers(`${prefix}-child-ended`), []);
};
check("compact: a manual compaction of an idle root runs as an execution of its own (UserPromptSubmit, Stop) and writes no SessionStart; the child stays listed until its own stop", () => {
  compactionChecks("c", "manual");
  const root = known.c;
  const action = one("action", (record) => record.label === "c-compact" && record.phase === "start");
  const answered = one("action", (record) => record.label === "c-compact" && record.phase === "end");
  assert.equal(answered.status, 200);
  assert.match(answered.body, /"type":"compaction".*"delivery":"steer"/);
  const [started, ended] = compactions("c");
  assert(enclosing("c").receipt > action.receipt);
  // The request is queued in the root's inbox and delivered as a new
  // execution of the root; nothing creates or forks it.
  const between = events(root).filter((record) => record.receipt > action.receipt && record.receipt < started.receipt).map((record) => record.type);
  assert.deepEqual(between.filter((type) => type.startsWith("session.execution.") || /^session\.(created|forked)$/.test(type)), ["session.execution.started"]);
  assert(between.includes("session.inbox.enqueued") && between.includes("session.inbox.delivered"));
  assert(events(root).some((record) => record.type === "session.execution.succeeded" && record.receipt > ended.receipt && within("c", record.at)));
  const names = duringHold("c").filter((write) => write.startedAt > action.receiptTime).map((write) => write.name);
  assert.deepEqual(names, ["UserPromptSubmit", "Stop"]);
});
check("compact-busy: a manual compaction requested during the root's own turn is steered into that execution, starts none, and writes no SessionStart", () => {
  compactionChecks("cb", "manual");
  const action = labelled("action", "cb-compact");
  const [, ended] = compactions("cb");
  assert.deepEqual(events(known.cb).filter((record) => record.receipt > action.receipt && record.receipt < ended.receipt
    && record.type === "session.execution.started"), []);
  assert(shell("cb-root-hold").endedAt > labelled("action", "cb-compact").receiptTime);
  assert(enclosing("cb").receipt < childCreated("cb").receipt);
});
check("auto-compact: a step reporting 120000 of 128000 context tokens compacts the root automatically before its next step, inside the execution, and writes no SessionStart", () => {
  compactionChecks("a", "auto");
  const high = one("model.request", (record) => record.highUsage && record.sessionID === known.a);
  const [started] = compactions("a");
  assert(high.receipt < started.receipt);
  assert(one("model.request", (record) => record.request === "compaction" && record.sessionID === known.a));
  assert(enclosing("a").receipt < childCreated("a").receipt);
});
check("overflow-compact: a provider's context_length_exceeded answer compacts the root automatically, inside the execution, and writes no SessionStart", () => {
  compactionChecks("o", "auto");
  const overflow = one("model.request", (record) => record.request === "overflow" && record.sessionID === known.o);
  assert(overflow.receipt < compactions("o")[0].receipt);
  assert(enclosing("o").receipt < childCreated("o").receipt);
});

// Other ways a live root might start again.
check("others: a fork starts only the fork's own record; a second client's `opencode run --session` from another Worktree and a TUI attaching write no SessionStart for the root", () => {
  const fork = known["x-fork"];
  const forked = one("plugin.event", (record) => record.type === "session.forked" && record.sessionID === fork);
  assert.equal(forked.source, known.x);
  assert.deepEqual(writes(fork).map((write) => write.name), ["SessionStart"]);
  assert.deepEqual(live(writes(fork)[0]), []);
  assert.deepEqual(sessionStartsDuringHold("x"), []);
  assert.deepEqual(state("x-after-fork", `repository/${known.x}.json`).liveSubagents, [known["x-child"]]);
  assert.equal(labelled("action", "x-attach").status, 0);
  assert(shell("x-attach", "start").env.OPENCODE_SESSION_ID === known.x);
  assert.deepEqual(state("x-after-attach", `repository/${known.x}.json`).liveSubagents, [known["x-child"]]);
  assert.deepEqual(state("x-after-tui", `repository/${known.x}.json`).liveSubagents, [known["x-child"]]);
  assert(blockers("x-after-tui").includes("sub-agent"));
  // Every plugin event of the scenario came from the service's own process.
  const service = one("service").pid;
  const scenario = one("scenario", (record) => record.name === "others").receipt;
  const next = one("scenario", (record) => record.name === "reload").receipt;
  assert(kind("plugin.event").filter((record) => record.receipt > scenario && record.receipt < next).every((record) => record.pid === service));
});
check("reload: `opencode reload` sets the plugin instances up again in the same process; their registrations write nothing, nothing is marked unobserved, and the root's list survives the reload and its next turn", () => {
  const action = labelled("action", "r-reload");
  assert.equal(action.status, 0);
  const service = one("service").pid;
  const after = kind("plugin.setup").filter((record) => record.receipt > action.receipt && within("r", record.at));
  assert(after.length >= 1 && after.every((record) => record.pid === service));
  const registers = kind("publication").filter((record) => record.request.kind === "register" && record.receipt > action.receipt && within("r", record.startedAt));
  assert(registers.length >= 1 && registers.every((record) => record.writes.length === 0));
  assert(!kind("publication").some((record) => record.request.kind === "unobserved" && within("r", record.startedAt)));
  assert.deepEqual(sessionStartsDuringHold("r"), []);
  assert.deepEqual(state("r-after-reload", `repository/${known.r}.json`).liveSubagents, [known["r-child"]]);
  assert.deepEqual(state("r-after-turn", `repository/${known.r}.json`).liveSubagents, [known["r-child"]]);
});
check("move-other-project: a live root moved to another Project gets a SessionStart, with no Sub-agents, in that Project's store at its next publication, while its child holds; the child's stop lands there, and the old store keeps the child listed", () => {
  const root = known.m;
  const child = known["m-child"];
  const moved = writes(root).find((write) => write.name === "SessionMoved");
  assert(moved.path.startsWith(MAIN) && within("m", moved.startedAt));
  assert.deepEqual(live(moved), [child]);
  const starts = sessionStartsDuringHold("m");
  assert.equal(starts.length, 1);
  assert(starts[0].path.startsWith(OTHER));
  assert.deepEqual(live(starts[0]), []);
  assert.equal(starts[0].record.hostPid, one("service").pid);
  assert(childStop("m").path.startsWith(OTHER));
  assert.deepEqual(live(childStop("m")), []);
  const stale = state("m-child-ended", `repository/${root}.json`);
  assert.equal(stale.event, "SessionMoved");
  assert.deepEqual(stale.liveSubagents, [child]);
});
check("standalone: `opencode run --standalone --session` on the live root is another Host Process; it writes SessionStart naming itself with no Sub-agents while the service's child holds, marks the root unobserved on exit, and the child's stop then writes SessionStart again naming the service", () => {
  const root = known.s;
  const service = one("service").pid;
  const action = labelled("action", "s-standalone");
  assert.equal(action.status, 0);
  const starts = sessionStartsDuringHold("s");
  assert.equal(starts.length, 1);
  assert.notEqual(starts[0].pid, service);
  assert.equal(starts[0].record.hostPid, starts[0].pid);
  assert.deepEqual(live(starts[0]), []);
  const unobserved = one("publication", (record) => record.request.kind === "unobserved" && record.request.pid === starts[0].pid);
  assert(unobserved.rewrites.some((rewrite) => rewrite.change === "_mark_unobserved_record" && rewrite.changed !== false));
  const after = state("s-after-standalone", `repository/${root}.json`);
  assert.equal(after.hostPid, starts[0].pid);
  assert.deepEqual(after.liveSubagents, []);
  assert.equal(after.unobservable, "opencode-no-live-instance");
  assert.deepEqual(blockers("s-after-standalone"), []);
  const stop = kind("publication").find((record) => record.request.session?.id === known["s-child"] && record.request.event?.type === "session.execution.succeeded");
  assert.deepEqual(stop.written, ["SessionStart", "SubagentStop"]);
  assert.equal(stop.request.pid, service);
  assert.equal(stop.writes[0].record.hostPid, service);
});
check("across every scenario, a root's SessionStart while its child held came only from a move to another Project's store or from another Host Process", () => {
  const service = one("service").pid;
  for (const prefix of ["c", "cb", "a", "o", "x", "r", "m", "s"]) {
    for (const start of sessionStartsDuringHold(prefix)) {
      assert(start.path.startsWith(OTHER) || start.pid !== service, `${prefix}: SessionStart at ${start.receipt}`);
    }
  }
});

for (const claim of checks) console.log(`ok - ${claim}`);
if (drifted.length) console.log(`note - Dashpot sources changed since the run: ${drifted.join(", ")}`);
console.log(`${checks.length} claims verified`);
