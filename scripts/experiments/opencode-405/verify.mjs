// Check a #405 measurement trace against the claims the plugin rewrite
// relies on, each named as the spike document states it.
//
// Usage: node verify.mjs <trace.jsonl>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const file = process.argv[2];
assert(file, "Pass the trace to verify");
const records = readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind, predicate = () => true) => records.filter((record) => record.kind === kind && predicate(record));
const environment = of("environment")[0];
const checks = [];
const check = (claim, test) => {
  try { test(); checks.push(["ok", claim]); } catch (error) { checks.push(["FAILED", `${claim}: ${error.message}`]); }
};
const command = (label) => of("command", (record) => record.label === label && record.phase === "start")[0];
const v2 = (record) => record.pid === of("service")[0]?.pid;
const session = (title) => of("session", (record) => record.title === title)[0]?.sessionID;

check("the run completed against 2.0.22 and 1.18.30", () => {
  assert.equal(environment.version, "opencode v2.0.22");
  assert.equal(environment.v1Version, "1.18.30");
  assert(of("done").length === 1 && !of("failure").length);
});

check("every v2 instance of one Host Process finds one registry on globalThis, across a file edit and `opencode reload`", () => {
  const setups = of("plugin.setup", v2);
  assert(setups.length >= 8);
  assert.equal(new Set(setups.map((record) => record.registry)).size, 1);
  for (const label of ["hot-reload", "cli-reload", "recovery-reload"]) {
    const mark = of("mark", (record) => record.label === label)[0].receipt;
    assert(setups.some((record) => record.receipt > mark), `no instance set up after ${label}`);
  }
});

check("each instance is its own module evaluation, so module state is not shared", () => {
  const setups = of("plugin.setup", v2);
  assert.equal(new Set(setups.map((record) => record.evaluation)).size, setups.length);
});

check("`opencode reload` cleans every instance up before setting any up, so the Host Process has no live instance between", () => {
  for (const label of ["cli-reload", "recovery-reload"]) {
    const mark = of("mark", (record) => record.label === label)[0].receipt;
    const next = of("plugin.setup", (record) => v2(record) && record.receipt > mark)[0].receipt;
    const emptied = of("plugin.cleanup", (record) => record.receipt > mark && record.receipt < next && record.live === 0);
    assert.equal(emptied.length, 1, `${label} never emptied the registry`);
  }
});

check("every session event carries an id and a durable envelope whose aggregate is its session", () => {
  const events = of("plugin.event");
  assert(events.length > 50);
  for (const event of events) {
    assert.match(event.id ?? "", /^evt_/);
    assert.equal(event.durable?.aggregateID, event.sessionID, `${event.type} ${event.receipt}`);
    assert(Number.isInteger(event.durable.seq));
  }
});

check("each event id reaches several instances and is admitted first exactly once", () => {
  const byId = new Map();
  for (const event of of("plugin.event")) byId.set(event.id, [...(byId.get(event.id) ?? []), event]);
  assert([...byId.values()].some((copies) => copies.length > 1));
  for (const copies of byId.values()) assert.equal(copies.filter((event) => event.first).length, 1);
});

check("a session's durable sequence rises with every admitted event", () => {
  const last = new Map();
  for (const event of of("plugin.event", (record) => record.first)) {
    const previous = last.get(event.sessionID) ?? -1;
    assert(event.durable.seq > previous, `${event.type} ${event.receipt}: ${event.durable.seq} after ${previous}`);
    last.set(event.sessionID, event.durable.seq);
  }
});

check("a Sub-agent's session.created names its parent, and ctx.session.get agrees", () => {
  const parent = session("Parent");
  const child = of("plugin.event", (record) => record.type === "session.created" && record.parentID === parent)[0];
  assert(child, "no child session.created");
  const read = of("plugin.get", (record) => record.sessionID === child.sessionID && record.found)[0];
  assert.equal(read.parentID, parent);
  assert.equal(command("child").env.OPENCODE_SESSION_ID, child.sessionID);
});

check("a fork publishes session.forked, not session.created, and reads as a root naming its source", () => {
  const fork = of("fork")[0];
  const forked = of("plugin.event", (record) => record.type === "session.forked" && record.first)[0];
  assert.equal(forked.sessionID, fork.sessionID);
  assert.equal(forked.parentID, fork.source);
  assert(!of("plugin.event", (record) => record.type === "session.created" && record.sessionID === fork.sessionID).length);
  const read = of("plugin.get", (record) => record.sessionID === fork.sessionID)[0];
  assert.equal(read.parentID, null);
  assert.equal(read.fork.sessionID, fork.source);
  assert.equal(command("fork-turn").env.OPENCODE_SESSION_ID, fork.sessionID);
});

check("session.moved names the old location in its envelope and the new one in its data, wherever it goes", () => {
  const mover = session("Mover");
  const moves = of("move", (record) => record.sessionID === mover);
  const moved = of("plugin.event", (record) => record.type === "session.moved" && record.first);
  assert.equal(moved.length, moves.length);
  let from = of("session", (record) => record.title === "Mover")[0].directory;
  moves.forEach((move, index) => {
    assert.equal(moved[index].location, from);
    assert.equal(moved[index].to, move.to);
    from = move.to;
  });
});

check("after a move, the session's shells run at the new location, under an instance set up there", () => {
  for (const [label, directory] of [["after-move-other", "$ROOT/other"], ["after-move-plain", "$ROOT/plain"]]) {
    const shell = command(label);
    assert.equal(shell.cwd, directory);
    const prepared = of("plugin.setup", (record) => record.instance === shell.env.SPIKE_PLUGIN_INSTANCE)[0];
    assert.equal(prepared.location, directory);
  }
});

check("ctx.session.get answers within 500 ms, and a deleted or never-issued session rejects with Session.NotFoundError", () => {
  const reads = of("plugin.get");
  assert(reads.every((record) => record.ms < 500 && !record.timedOut));
  const probe = of("probe")[0];
  const recovery = of("plugin.get", (record) => record.why === "recovery");
  assert(recovery.length >= 6);
  for (const record of recovery) {
    if (record.sessionID === probe.live) assert.equal(record.found, true);
    else assert.equal(record.error?.tag, "Session.NotFoundError", record.sessionID);
  }
});

check("create.before receives no session; deleting OPENCODE_SESSION_ID and OPENCODE there leaves a model-driven shell with both set by OpenCode", () => {
  for (const record of of("plugin.shell")) assert.deepEqual(record.invocation, ["command", "cwd", "timeout", "shell", "env"]);
  const shells = of("command", (record) => record.phase === "start" && record.label !== "v1-shell");
  for (const shell of shells) {
    assert.match(shell.env.OPENCODE_SESSION_ID ?? "", /^ses_/);
    assert.equal(shell.env.OPENCODE, "1");
    assert.equal(Number(shell.env.SPIKE_HOST_PID), shell.ppid);
  }
});

check("OpenCode 1.18.30 calls the module's v1 `server` entry, whose shell variable reaches the shell", () => {
  assert.equal(of("v1.server").length, 1);
  const shell = command("v1-shell");
  assert.equal(shell.env.SPIKE_V1_REFUSED, "opencode-v1");
  assert.equal(shell.env.OPENCODE_SESSION_ID, null);
});

check("OpenCode 1.18.30 also calls `setup`, with no ctx.app, and the v2 API absent", () => {
  const v1 = of("v1.server")[0].pid;
  const setup = of("plugin.setup", (record) => record.pid === v1)[0];
  assert(setup, "1.18.30 did not call setup");
  assert(setup.app == null, "1.18.30 gave setup a ctx.app");
  assert(of("plugin.stream-error", (record) => record.pid === v1).length === 1);
});

for (const [status, claim] of checks) console.log(`${status}: ${claim}`);
process.exit(checks.some(([status]) => status !== "ok") ? 1 : 0);
