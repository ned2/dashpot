// Independent verifier for the Issue #448 trace: checks each finding about
// the `SessionStart` Claude Code publishes on a live session with a working
// background Sub-agent — compaction (manual, automatic, headless), `/clear`,
// `/resume <id>` and `/branch` — against the recorded hook, shell,
// model-request and hook-store evidence, and that the trace came from the
// runner retained beside this file. With --sequences it also prints each
// scenario's hook sequence from the action on.
//
// Usage: node verify.mjs <trace.jsonl> [--strict] [--sequences]
//
// The Dashpot sources the trace hashes keep changing after the run, and the
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

// One scenario's records, its lead, and what happened after its action.
const scenario = (name) => {
  const start = records.findIndex((record) => record.kind === "scenario" && record.name === name);
  assert(start >= 0, `scenario ${name}`);
  const end = records.findIndex((record, index) => index > start && record.kind === "scenario.end" && record.name === name);
  assert(end > start, `scenario ${name} ended`);
  assert.equal(records[end].ok, true, `scenario ${name}: ${records[end].error}`);
  const span = records.slice(start, end + 1);
  const spawned = span.find((record) => record.kind === "client.spawn" && record.mode !== "single");
  const hooks = span.filter((record) => record.kind === "hook");
  const first = hooks.find((record) => record.event === "SessionStart" && record.payload.source === "startup"
    && (record.hostPid === spawned.pid || record.ancestry.some((entry) => entry.pid === spawned.pid)));
  assert(first, `${name} startup SessionStart`);
  const host = first.hostPid;
  const action = span.find((record) => record.kind === "action");
  assert(action, `${name} action`);
  const lead = hooks.filter((record) => record.hostPid === host);
  const after = lead.filter((record) => record.receipt > action.receipt);
  const p = action.scenario;
  const command = (label, phase = "end") => {
    const found = span.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
    assert(found, `${name}: command ${label} ${phase}`);
    return found;
  };
  const started = lead.find((record) => record.event === "SubagentStart" && record.receipt < action.receipt);
  assert(started, `${name}: the worker's SubagentStart before the action`);
  const sessionStart = after.find((record) => record.event === "SessionStart");
  assert(sessionStart, `${name}: a SessionStart after the action`);
  const gate = span.find((record) => record.kind === "gate" && record.gate === `${p}-go`);
  assert(gate, `${name}: worker gate`);
  return { name, p, span, hooks, lead, host, session: first.payload.session_id, action, after, command, worker: started.payload.agent_id,
    workerStart: started.receipt, sessionStart, gate, workerCheck: span.find((record) => record.kind === "worker.check") };
};
const between = (run, from, to) => run.lead.filter((record) => record.receipt > from && record.receipt < to);
const mine = (record, session = record.payload.session_id) => (record.store ?? []).find((entry) => entry.sessionId === session);
const workerStop = (run) => run.after.find((record) => record.event === "SubagentStop" && record.payload.agent_id === run.worker);

// The run itself.
const environment = records[0];
check("the trace is of the pinned Claude Code release", () => {
  assert.equal(environment.kind, "environment");
  assert.equal(environment.version, `${pinned} (Claude Code)`);
  assert.match(environment.binary, new RegExp(`/claude/versions/${pinned.replaceAll(".", "\\.")}$`));
});
check("the trace came from the helpers retained beside this verifier", () => {
  for (const [name, hash] of Object.entries(environment.experimentSHA256)) if (name !== "run.mjs")
    assert.equal(createHash("sha256").update(readFileSync(path.join(here, name))).digest("hex"), hash, `${name} changed since the run`);
});
if (createHash("sha256").update(readFileSync(path.join(here, "run.mjs"))).digest("hex") !== environment.experimentSHA256["run.mjs"]) {
  console.log("note - runner changed since this trace was recorded: run.mjs");
  assert(!flags.has("--strict"), "runner changed under --strict");
}
check("the hooks were subscribed as `dashpot integrate claude-code` subscribes them, with PreCompact and PostCompact observed only", () => {
  assert.deepEqual(environment.subscriptions.events, ["SessionStart", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "SessionEnd"]);
  assert.deepEqual(environment.subscriptions.observedOnly, ["PreCompact", "PostCompact"]);
  for (const record of records.filter((entry) => entry.kind === "hook")) {
    if (environment.subscriptions.observedOnly.includes(record.event)) assert.equal(record.publisher, null);
    else assert.equal(record.publisher?.status, 0, `publisher failed at #${record.receipt}`);
  }
});
check("the publisher ran the committed HEAD source, except in compact-worktree", () => {
  assert.equal(environment.publishers.head, "$ROOT/dashpot-head/src/dashpot/sessions/hook_records.py");
  assert.equal(environment.publishers.worktree, "$CHECKOUT/src/dashpot/sessions/hook_records.py");
  const spawned = records.filter((record) => record.kind === "client.spawn" && record.extraEnv?.length);
  assert.deepEqual(spawned.map((record) => record.name), ["cw"]);
});
const checkoutRoot = path.resolve(here, "..", "..", "..");
const drift = Object.entries(environment.worktreeSourceSHA256).filter(([name, hash]) => {
  try { return createHash("sha256").update(readFileSync(path.join(checkoutRoot, name))).digest("hex") !== hash; } catch { return true; }
}).map(([name]) => name);
if (drift.length) {
  console.log(`note - working-tree sources changed since the run: ${drift.join(", ")}`);
  assert(!flags.has("--strict"), "sources changed under --strict");
}

// A worker that is still working across the action, and finishes afterwards.
const survives = (run, sessionAfter) => {
  assert.equal(run.workerCheck.holdAlive, true, "worker's held Bash call alive after the SessionStart");
  assert.equal(run.workerCheck.holdEnded, false, "worker's held Bash call had not ended");
  assert(run.workerCheck.receipt > run.sessionStart.receipt);
  const hold = run.command(`${run.p}-w-hold`);
  assert.equal(hold.opened, true);
  assert(hold.receipt > run.gate.receipt, "the hold ended only once the gate opened");
  const continued = run.command(`${run.p}-w-after`);
  assert.equal(continued.env.CLAUDE_CODE_SESSION_ID, sessionAfter, "the worker's next shell names the session the process now hosts");
  const stop = workerStop(run);
  assert(stop, "the worker's SubagentStop");
  assert(stop.receipt > run.gate.receipt);
  assert.equal(stop.payload.session_id, sessionAfter, "the worker's SubagentStop names the session the process now hosts");
  assert.equal(stop.hostPid, run.host);
  // Its completion reaches the lead as a task notification, in that session.
  const notified = run.after.find((record) => record.event === "UserPromptSubmit" && record.prompt?.taskNotification);
  assert(notified && notified.receipt > stop.receipt);
  assert.equal(notified.payload.session_id, sessionAfter);
  const requests = run.span.filter((record) => record.kind === "model.request" && record.label === `${run.p}-worker` && record.receipt > run.gate.receipt);
  assert(requests.length);
  for (const request of requests) assert.equal(request.sessionHeaders["x-claude-code-session-id"], sessionAfter, "worker requests carry the hosted session's id");
};

// Compaction: the same session goes on in the same process; no SessionEnd.
const compaction = (name, trigger) => {
  const run = scenario(name);
  check(`${name}: PreCompact(${trigger}), then SessionStart(compact) with no SessionEnd, same session_id, Host Process and cwd`, () => {
    const before = between(run, run.action.receipt, run.sessionStart.receipt);
    assert(!before.some((record) => record.event === "SessionEnd"), "no SessionEnd before the SessionStart");
    assert(!run.after.some((record) => record.event === "SessionEnd" && record.receipt < run.gate.receipt));
    const pre = before.find((record) => record.event === "PreCompact");
    assert(pre, "PreCompact");
    assert.equal(pre.payload.trigger, trigger);
    assert.equal(run.sessionStart.payload.source, "compact");
    assert.equal(run.sessionStart.payload.session_id, run.session);
    assert.equal(run.sessionStart.hostPid, run.host);
    assert.equal(run.sessionStart.payload.cwd, fixture);
    assert.equal(mine(run.sessionStart).processPid, run.host, "Dashpot names the same Host Process");
    const post = run.after.find((record) => record.event === "PostCompact");
    assert(post && post.receipt > run.sessionStart.receipt, "PostCompact follows the SessionStart");
    assert.equal(post.payload.trigger, trigger);
    assert.equal(run.after.filter((record) => record.event === "SessionStart").length, 1, "one SessionStart");
  });
  check(`${name}: the compaction's summarizer publishes a SubagentStop with an empty agent_type and no SubagentStart`, () => {
    const pre = run.after.find((record) => record.event === "PreCompact");
    const stops = between(run, pre.receipt, run.sessionStart.receipt).filter((record) => record.event === "SubagentStop");
    assert.equal(stops.length, 1);
    assert.equal(stops[0].payload.agent_type, "");
    assert.notEqual(stops[0].payload.agent_id, run.worker);
    assert(!run.hooks.some((record) => record.event === "SubagentStart" && record.payload.agent_id === stops[0].payload.agent_id));
  });
  check(`${name}: the worker keeps working across the compaction and stops afterwards in the same session`, () => survives(run, run.session));
  return run;
};
const manual = (name) => {
  const run = compaction(name, "manual");
  check(`${name}: a manual /compact publishes no UserPromptSubmit and no Stop`, () => {
    const until = run.gate.receipt;
    assert(!between(run, run.action.receipt, until).some((record) => ["UserPromptSubmit", "Stop"].includes(record.event) && !record.payload.agent_id));
  });
  return run;
};
const cp = manual("compact");
check("compact (HEAD publisher): SessionStart(compact) empties liveSubagents and leaves the session running with no Stop to follow", () => {
  const before = cp.lead.filter((record) => record.receipt < cp.sessionStart.receipt).at(-1);
  assert.deepEqual(mine(before, cp.session).liveSubagents, [cp.worker]);
  const record = mine(cp.sessionStart);
  assert.deepEqual(record.liveSubagents, []);
  assert.equal(record.state, "running");
  // Nothing moves it until the worker's own completion wakes the lead.
  assert(!between(cp, cp.sessionStart.receipt, cp.gate.receipt).some((entry) => entry.event === "Stop"));
  assert.deepEqual(mine(workerStop(cp)).liveSubagents, []);
});
const cw = manual("compact-worktree");
const cwCarried = (() => {
  const record = mine(cw.sessionStart);
  return record.liveSubagents.includes(cw.worker);
})();
check(`compact-worktree (working-tree publisher): SessionStart(compact) ${cwCarried ? "keeps" : "drops"} the worker in liveSubagents`, () => {
  const record = mine(cw.sessionStart);
  assert.equal(record.state, "running");
  if (cwCarried) {
    assert.deepEqual(record.liveSubagents, [cw.worker]);
    assert.deepEqual(mine(workerStop(cw)).liveSubagents, [], "its SubagentStop removes it");
  } else assert.deepEqual(record.liveSubagents, []);
});

const ac = compaction("auto-compact", "auto");
check("auto-compact: the compaction falls inside the lead's turn: no UserPromptSubmit, and the turn's Stop follows", () => {
  const stop = ac.after.find((record) => record.event === "Stop" && !record.payload.agent_id);
  assert(stop && stop.receipt > ac.sessionStart.receipt && stop.receipt < ac.gate.receipt);
  assert(!between(ac, ac.action.receipt, stop.receipt).some((record) => record.event === "UserPromptSubmit"));
  const inflated = ac.span.find((record) => record.kind === "model.request" && record.inflate);
  assert(inflated && inflated.receipt < ac.action.receipt, "the fixture reported near-window usage before the action");
});
check("auto-compact (HEAD publisher): the session reads waiting with no live Sub-agent while the worker still works", () => {
  const stop = ac.after.find((record) => record.event === "Stop" && !record.payload.agent_id);
  assert.deepEqual(mine(stop), { ...mine(stop), state: "waiting", liveSubagents: [] });
  assert(ac.workerCheck.receipt > stop.receipt && ac.workerCheck.holdAlive);
});
const hc = manual("headless-compact");
check("headless-compact (HEAD publisher): SessionStart(compact) empties liveSubagents", () => {
  assert.deepEqual(mine(hc.sessionStart).liveSubagents, []);
});

// A switch of session within the same process: SessionEnd, then SessionStart.
const switched = (name, reason, source, expect) => {
  const run = scenario(name);
  const next = run.sessionStart.payload.session_id;
  check(`${name}: SessionEnd(${reason}) of the lead's session, then SessionStart(${source}) of ${expect} in the same Host Process`, () => {
    const end = between(run, run.action.receipt, run.sessionStart.receipt).filter((record) => record.event === "SessionEnd");
    assert.equal(end.length, 1);
    assert.equal(end[0].payload.reason, reason);
    assert.equal(end[0].payload.session_id, run.session);
    assert.equal(end[0].hostPid, run.host);
    assert.equal(run.sessionStart.payload.source, source);
    assert.equal(run.sessionStart.hostPid, run.host);
    assert.equal(mine(run.sessionStart).processPid, run.host, "Dashpot names the same Host Process");
    assert.equal(end[0].payload.cwd, fixture);
    assert.equal(run.sessionStart.payload.cwd, fixture);
    assert.notEqual(next, run.session);
    if (expect === "the prior session") assert.equal(next, run.span.find((record) => record.kind === "prior").session);
    else assert(!records.some((record) => record.kind === "hook" && record.payload.session_id === next && record.receipt < run.sessionStart.receipt), "a new session_id");
    assert(!between(run, run.action.receipt, run.gate.receipt).some((record) => ["UserPromptSubmit", "Stop", "PreCompact"].includes(record.event)));
  });
  check(`${name}: the worker survives and goes on under the new session_id, which its SubagentStop names`, () => survives(run, next));
  check(`${name} (HEAD publisher): the old session's ended record keeps the worker, its SubagentStop under the new id never clears it`, () => {
    const end = between(run, run.action.receipt, run.sessionStart.receipt).find((record) => record.event === "SessionEnd");
    assert.deepEqual(mine(end, run.session), { ...mine(end, run.session), state: "ended", liveSubagents: [run.worker] });
    assert.deepEqual(mine(run.sessionStart).liveSubagents, []);
    const last = run.after.at(-1);
    assert.deepEqual(mine(last, run.session)?.liveSubagents, [run.worker], "still listed after the lead exits");
  });
  return run;
};
switched("clear", "clear", "clear", "a new session");
switched("resume-switch", "resume", "resume", "the prior session");
switched("branch", "resume", "fork", "a new session");
switched("headless-clear", "clear", "clear", "a new session");

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} checks passed`);

if (flags.has("--sequences")) {
  const names = new Map();
  const short = (id) => { if (!id) return "-"; if (!names.has(id)) names.set(id, `S${names.size + 1}`); return names.get(id); };
  for (const record of records.filter((entry) => entry.kind === "scenario")) {
    const run = scenario(record.name);
    console.log(`\n${record.name}: lead ${short(run.session)} host ${run.host} worker ${run.worker}; action #${run.action.receipt} ${run.action.action}; gate #${run.gate.receipt}; worker check #${run.workerCheck.receipt} alive=${run.workerCheck.holdAlive}`);
    for (const hook of run.lead.filter((entry) => entry.receipt >= run.workerStart)) {
      const stored = mine(hook);
      const detail = hook.payload.source ?? hook.payload.reason ?? hook.payload.trigger ?? "";
      console.log(`  #${hook.receipt} ${hook.event}${detail ? `(${detail})` : ""} ${short(hook.payload.session_id)}${hook.payload.agent_id ? ` agent=${hook.payload.agent_id}${hook.payload.agent_type === "" ? " type=''" : ""}` : ""}${hook.prompt?.taskNotification ? " task-notification" : ""}`
        + (stored ? ` -> store ${stored.state} ${JSON.stringify(stored.liveSubagents)}` : hook.observeOnly ? " (observed only)" : " -> store: no record"));
    }
  }
  console.log(`\n${[...names].map(([id, label]) => `${label}=${id}`).join("\n")}`);
}
