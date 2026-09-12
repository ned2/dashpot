import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Check observable outcomes without importing the publisher or receiver.
const rows = readFileSync(process.argv[2], "utf8").trim().split("\n").map(JSON.parse);
const actions = (kind) => rows.filter((r) => r.kind === `action.${kind}`);
const applied = rows.filter((r) => r.kind === "receiver.applied" && r.accepted);
const pubs = applied.map((r) => ({ ...r.publication, receipt: r.receipt, receiptTime: r.receiptTime }));
const commandRows = rows.filter((r) => r.kind === "command");
const commands = commandRows.filter((r) => r.phase === "start");
const environment = rows.find((r) => r.kind === "environment");
const { a, b } = actions("sessions")[0];
assert.equal(environment.version, "1.18.30");
assert.notEqual(a, b);
const starts = [a, b].map((id) => commands.find((r) => r.claim === `opencode:${id}`));
const ends = starts.map((start) => commandRows.find((r) => r.pid === start.pid && r.phase === "end"));
assert(starts.every((r) => r.evidence && r.bootstrapAck === "true"));
assert(Math.max(...starts.map((r) => r.receiptTime)) < Math.min(...ends.map((r) => r.receiptTime)));
assert.equal(starts[0].ppid, starts[1].ppid);
assert.equal(starts[0].ppid, pubs[0].pid);
const bIdle = pubs.find((r) => r.sessionID === b && r.activity === "idle");
assert(bIdle.sourceTime < ends[0].receiptTime, "B must settle independently while A runs");
assert(pubs.some((r) => r.sessionID === a && r.activity === "busy" && r.sourceTime <= starts[0].receiptTime));

const located = pubs.find((r) => r.kind === "shell.bootstrap" && r.shellCwd === environment.other);
assert.equal(located.sessionID, a);
assert.equal(located.sessionDirectory, environment.fixture);
assert.equal(located.directory, environment.fixture);
assert.equal(actions("location-after")[0].directory, environment.fixture);
const detach = actions("client-detach")[0];
const reconnect = actions("client-attach").find((r) => r.label === "A-reconnected");
assert(!pubs.some((r) => r.receipt > detach.receipt && r.receipt < reconnect.receipt && ["session.deleted", "plugin.dispose"].includes(r.kind)));
const cliDetach = actions("cli-detach")[0];
assert.notEqual(cliDetach.pid, cliDetach.backendPID);
const detachedCommand = commands.findLast((r) => r.receipt < cliDetach.receipt);
assert(commandRows.some((r) => r.pid === detachedCommand.pid && r.phase === "end" && r.receipt > cliDetach.receipt));
assert.equal(actions("cli-reconnected")[0].sessionID, a);
const fork = actions("fork")[0];
assert.notEqual(fork.sessionID, a);
assert.equal(fork.parentID, undefined);
assert(commands.some((r) => r.claim === `opencode:${fork.sessionID}`));

const children = pubs.filter((r) => r.kind === "session.created" && r.parentID);
assert.equal(children.length, 2);
for (const child of children) {
  const command = commands.find((r) => r.claim === `opencode:${child.sessionID}`);
  assert(command && command.claim !== `opencode:${child.parentID}`);
  const childIdle = pubs.find((r) => r.sessionID === child.sessionID && r.activity === "idle");
  const parentIdles = pubs.filter((r) => r.sessionID === child.parentID && r.activity === "idle" && r.sourceTime > child.sourceTime);
  if (child.parentID === a) assert(parentIdles[0].sourceTime >= childIdle.sourceTime, "Foreground waits for child");
  if (child.parentID === b) {
    assert(parentIdles[0].sourceTime < childIdle.sourceTime, "Background parent becomes idle first");
    assert(pubs.some((r) => r.sessionID === b && r.activity === "busy" && r.sourceTime >= childIdle.sourceTime));
  }
}
const retry = pubs.find((r) => r.sessionID === a && r.activity === "retry");
assert.equal(retry.attempt, 1);
assert(pubs.some((r) => r.sessionID === a && r.activity === "busy" && r.sequence > retry.sequence));
const abort = actions("abort")[0];
assert(pubs.some((r) => r.sessionID === a && r.activity === "idle" && r.sourceTime >= abort.receiptTime));
assert(commands.some((r) => r.claim === `opencode:${a}` && r.receipt > abort.receipt));
assert(pubs.some((r) => r.kind === "shell.identity-missing" && !r.sessionID));

for (const command of commands.filter((r) => r.bootstrapAck === "true")) {
  assert(command.evidence);
  const proof = pubs.find((r) => r.kind === "shell.bootstrap" && `opencode:${r.sessionID}` === command.claim && r.instance === command.instance && r.receipt < command.receipt);
  assert(proof, "Acknowledged command must see an earlier accepted bootstrap");
}
for (const kind of ["failure-completed", "timeout-completed"]) {
  const action = actions(kind)[0];
  assert(action.milliseconds < 10000, "Injected receiver failure must remain bounded");
  const command = commands.find((r) => r.claim === `opencode:${action.sessionID}`);
  assert(command && !command.evidence && command.bootstrapAck === "false");
  assert(rows.some((r) => r.kind === "publisher.diagnostic" && r.publication.sessionID === action.sessionID));
}
const sequences = new Map();
for (const publication of pubs) {
  const key = `${publication.instance}:${publication.sessionID ?? "instance"}`;
  assert(publication.sequence > (sequences.get(key) ?? 0), "Accepted per-session order must increase");
  sequences.set(key, publication.sequence);
}
assert.equal(actions("replay").length, 3);
for (const replay of actions("replay")) {
  const result = rows.find((r) => r.kind === "receiver.applied" && r.receipt > replay.receipt &&
    r.publication.instance === replay.instance && r.publication.sequence === replay.sequence);
  assert.equal(result.accepted, false, replay.label);
}
const reload = actions("reload")[0];
assert.equal(reload.sessionID, a);
assert.equal(reload.pid, starts[0].ppid);
assert(pubs.some((r) => r.kind === "plugin.dispose" && r.receipt < reload.receipt));
const loss = actions("observation-loss")[0];
assert(loss.sessionSurvived);
assert(commands.some((r) => r.claim === null && r.ppid === loss.pid && r.receipt < loss.receipt));
assert(commands.some((r) => r.claim === `opencode:${a}` && r.receipt > loss.receipt));
assert(pubs.some((r) => r.kind === "session.deleted" && r.sessionID === fork.sessionID));
const restart = actions("restart-resume")[0];
assert.equal(restart.sessionID, a);
assert.notEqual(restart.pid, restart.oldPID);
assert.equal(restart.directory, environment.fixture);
assert(commands.some((r) => r.claim === `opencode:${a}` && r.ppid === restart.pid));
assert.deepEqual(actions("backend-exit").map((r) => r.signal), ["SIGTERM", "SIGKILL"]);
for (const exit of actions("backend-exit")) {
  const lastInit = pubs.findLast((r) => r.kind === "plugin.init" && r.pid === exit.pid && r.receipt < exit.receipt);
  assert(!pubs.some((r) => r.kind === "plugin.dispose" && r.instance === lastInit.instance), "Signal exits emitted no final disposal in this tested mode");
}
console.log(`Verified ${rows.length} metadata records: identity, location, lifecycle, ordering and failure outcomes.`);
