// Verifier for Issue #466's rerun of the unchanged Issue #379 OpenCode runner
// (scripts/experiments/opencode-379/run.mjs) against ADR 0104's `process`
// Cleanup blocker: checks that the trace came from that runner as retained,
// and that a background shell command which outlives its session's move or
// deletion is named by the blocker in the Worktree it works in, that only
// OpenCode's own shell listing names its owning session, and that the
// command's end wakes a session that still exists. The #379 verifier's
// claims that Cleanup named nothing after a move or delete predate ADR 0104,
// which is why this trace has a verifier of its own.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
//
// The Dashpot sources the trace hashes may change after the run, and the #379
// runner and its verifier may be edited after it, so a difference in either
// from this checkout is reported, and fails only under --strict.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const runner = path.resolve(here, "..", "opencode-379");
const strict = process.argv.includes("--strict");
const [tracePath] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace");
const text = readFileSync(tracePath, "utf8");
const records = text.trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => {
  try { test(); } catch (error) { console.error(`not ok - ${claim}`); throw error; }
  checks.push(claim);
};
const main = "$ROOT/repository";
const tree = (name) => `$ROOT/repository.worktrees/${name}`;
const one = (kind, predicate = () => true) => {
  const found = records.filter((record) => record.kind === kind && predicate(record));
  assert.equal(found.length, 1, `exactly one ${kind}`);
  return found[0];
};
const labelled = (kind, label) => one(kind, (record) => record.label === label);
const started = (label) => one("command", (record) => record.label === label && record.phase === "start");
const ended = (label) => one("command", (record) => record.label === label && record.phase === "end");
const sessionOf = (title) => one("session", (record) => record.title === title).sessionID;
// The pids a Cleanup report's `process` blocker names, from its detail.
const processPids = (obstacle) => [...obstacle.detail.matchAll(/pid (\d+) \(/g)].map((match) => Number(match[1]));
// The model requests after a command's end that carry a fresh notice of
// its shell's completion: the session woken by that end.
const wokenBy = (hold, session) => records.filter((record) => record.kind === "model.request" && record.sessionID === session && record.receipt > ended(hold).receipt
  && (record.notices ?? []).some((notice) => notice.of === "shell" && notice.fresh && notice.state === "completed"));

const environment = one("environment");
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
const editable = ["run.mjs", "verify.mjs"];
check("the trace came from the #379 runner's helpers unchanged, with the pinned OpenCode release and the installed copy of this checkout's plugin", () => {
  for (const file of ["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs"]) {
    if (!editable.includes(file)) assert.equal(digestOf(path.join(runner, file)), environment.sourceSHA256[file], `opencode-379/${file} matches the hash the run recorded`);
  }
  assert.equal(environment.version, "opencode v2.0.22");
  assert.equal(environment.installedMatchesSource, true);
  assert.deepEqual(text.match(/(?<![\w$])\/(?:tmp|home)\/[^"\s]*/g) ?? [], [], "no path outside the fixture's placeholders");
  assert.deepEqual(records.filter((record) => record.kind === "failure"), []);
  assert.deepEqual(one("cleanup.remaining").pids, []);
});
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
if (drifted.length) {
  console.log(`note - working-tree sources changed since the run: ${drifted.join(", ")}`);
  assert(!strict, "sources changed under --strict");
}
const runnerChanged = editable.filter((file) => digestOf(path.join(runner, file)) !== environment.sourceSHA256[file]);
if (runnerChanged.length) {
  console.log(`note - runner changed since this trace was recorded: ${runnerChanged.map((file) => `opencode-379/${file}`).join(", ")}`);
  assert(!strict, "runner changed under --strict");
}

check("background: while the session that started it waits, the `process` blocker names the command beside the session's own blockers", () => {
  const hold = started("bg-hold");
  assert.equal(hold.cwd, tree("a"));
  assert.equal(labelled("process", "bg-running").alive, true);
  const stored = Object.values(labelled("state", "bg-running").sessions).filter((entry) => entry.session === sessionOf("Background"));
  assert.deepEqual(stored.map((entry) => entry.state), ["waiting"]);
  const obstacles = labelled("cleanup", "tree-a-bg-running").obstacles;
  assert.deepEqual(obstacles.map((obstacle) => obstacle.kind), ["agent-session", "agent-run", "process"]);
  assert.deepEqual(processPids(obstacles[2]), [hold.pid]);
});
check("background-move: once the session has moved to the main checkout, Worktree b's only blocker is the `process` one naming the command", () => {
  const hold = started("bg-move-hold");
  assert.equal(hold.cwd, tree("b"));
  assert.equal(labelled("session.info", "bg-move-moved").location, main);
  const sampled = labelled("process", "bg-move-running");
  assert.equal(sampled.alive, true);
  assert.equal(sampled.cwd, tree("b"));
  const obstacles = labelled("cleanup", "tree-b-bg-move-running").obstacles;
  assert.deepEqual(obstacles.map((obstacle) => obstacle.kind), ["process"]);
  assert.deepEqual(processPids(obstacles[0]), [hold.pid]);
  assert(!obstacles[0].detail.includes(sessionOf("BackgroundMove")), "the blocker names no session");
});
check("background-delete: once the session is deleted, Worktree c's only blocker is the `process` one naming the command, by pid and command name", () => {
  const hold = started("bg-del-hold");
  assert.equal(hold.cwd, tree("c"));
  assert.equal(labelled("session.delete", "bg-del").status, 0);
  assert.equal(labelled("session.info", "bg-del-deleted").missing, 404);
  assert.equal(labelled("process", "bg-del-running").alive, true);
  const obstacles = labelled("cleanup", "tree-c-bg-del-running").obstacles;
  assert.deepEqual(obstacles.map((obstacle) => obstacle.kind), ["process"]);
  assert.deepEqual(processPids(obstacles[0]), [hold.pid]);
  assert(!obstacles[0].detail.includes(sessionOf("BackgroundDelete")), "the blocker names no session");
});
check("only OpenCode's shell listing, asked with the Worktree as its location header, names the command's session, and it still does after the session is deleted", () => {
  for (const [label, hold, title] of [["bg-running", "bg-hold", "Background"], ["bg-move-running-old", "bg-move-hold", "BackgroundMove"], ["bg-del-running", "bg-del-hold", "BackgroundDelete"]]) {
    const shells = labelled("shells", label);
    assert.deepEqual(shells.byQuery.shells, [], `${label}: the location query lists nothing`);
    const listed = shells.byHeader.shells.filter((shell) => shell.pid === started(hold).pid);
    assert.equal(listed.length, 1, `${label}: the header listing names the command`);
    assert.equal(listed[0].session, sessionOf(title));
    assert.equal(listed[0].status, "running");
  }
});
check("the command's end wakes a session that still exists, moved or not, and wakes nothing once its session is deleted", () => {
  assert(wokenBy("bg-hold", sessionOf("Background")).length > 0, "the waiting session is woken");
  assert(wokenBy("bg-move-hold", sessionOf("BackgroundMove")).length > 0, "the moved session is woken");
  assert.deepEqual(wokenBy("bg-del-hold", sessionOf("BackgroundDelete")), []);
  const deleted = labelled("woken", "bg-del");
  assert.equal(deleted.woke, false);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} checks passed`);
