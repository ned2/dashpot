// Independent verifier for the Issue #423 trace: checks each claim
// docs/spikes/opencode-v2-self-relocation-acceptance.md makes about a root
// OpenCode 2.0.22 session moving itself as the dashpot-issue-work skill
// describes, against the recorded model requests, shell commands, hook and
// Work Store records, observations and Cleanup reports.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
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
// A flow can run one label again in a later turn; `shells` lists every run.
const shells = (label) => kind("command").filter((record) => record.label === label && record.phase === "end");
const shell = (label) => { const found = shells(label); assert.equal(found.length, 1, `${label} ran once`); return found[0]; };
const started = (label) => one("command", (record) => record.label === label && record.phase === "start");
const output = (record) => `${record.dashpot?.stdout ?? ""}${record.dashpot?.stderr ?? ""}`;
const identity = (record) => output(record).split("\n").find((line) => line.startsWith("Agent Session identity claimed here:"));
const sessionOf = (title) => one("session", (record) => record.title === title).sessionID;
const info = (label) => labelled("session.info", label);
// The model's turn for one label, step by step: what it saw, what it did.
const turn = (label) => kind("model.request").filter((record) => !record.titled && record.label === label);
const decisions = (label) => turn(label).filter((record) => record.decision).map((record) => record.decision);
const moves = (label) => turn(label).filter((record) => record.previous?.kind === "move").map((record) => record.previous);
const ranLabels = (label) => turn(label).filter((record) => record.previous?.label).map((record) => record.previous.label);
// The Work Store's runs in one state snapshot, by Issue.
const runsAt = (label) => {
  const found = {};
  for (const [file, run] of Object.entries(labelled("state", label).runs)) (found[run.issue] ??= []).push({ worktree: file.slice(0, file.lastIndexOf("/")), ...run });
  return found;
};
const blockers = (label) => labelled("cleanup", label).obstacles.map((obstacle) => obstacle.kind);
const confirmedAt = (record, directory) => record.cwd === directory
  && identity(record) === `Agent Session identity claimed here: OpenCode session ${started(record.label).env.OPENCODE_SESSION_ID} (from OpenCode environment), confirmed by its live hook record`;
const moveAccepted = (result, directory) => { const answer = JSON.parse(result); return answer.directory === directory && /^ses_\w+$/.test(answer.sessionID); };

const environment = one("environment");
// The runner's scripts change only with a new trace, so they must match;
// Dashpot's sources keep changing after the trace is retained, so a
// difference is reported, and fails only under --strict.
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
const treeDigestOf = (directory) => {
  if (!existsSync(directory)) return null;
  const hash = createHash("sha256");
  for (const name of readdirSync(directory, { recursive: true }).map(String).toSorted()) {
    try { hash.update(name + "\0" + readFileSync(path.join(directory, name))); } catch {}
  }
  return hash.digest("hex");
};
for (const file of ["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs"]) {
  assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
}
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => (file.endsWith("/") ? treeDigestOf : digestOf)(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot sources differ from the run's: ${drifted.join(", ")}`);

const bound = sessionOf("Bound");
const unbound = sessionOf("Unbound");
const workers = sessionOf("Workers");

check("the trace names no path outside the fixture's placeholders", () => {
  assert.deepEqual(text.match(/(?<![\w$])\/(?:tmp|home)\/[^"\s]*/g) ?? [], []);
});
check("the pinned OpenCode release, driving the installed copy of this checkout's plugin, helper and skill", () => {
  assert.equal(environment.version, "opencode v2.0.22");
  assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
  assert.equal(environment.installedMatchesSource, true);
  assert.equal(labelled("integrate", "install").status, 0);
  assert.equal(labelled("files", "installed").skillMatchesSource, true);
  assert.equal(labelled("files", "installed").workerAgent, true);
});
check("every scenario completed and no fixture process outlived the run", () => {
  assert.deepEqual(kind("failure"), []);
  assert.deepEqual(kind("server.error"), []);
  assert.deepEqual(kind("scenario").map((record) => record.name), ["installer", "bound", "unbound", "finish", "switch", "same-step",
    "refused-destination", "unwritable", "denied", "asked", "workers", "default-permissions"]);
  assert.equal(kind("done").length, 1);
  assert.deepEqual(one("cleanup.remaining").pids, []);
});

// Dispatch of a bound session.
check("bound dispatch: the session moves itself with the tool alone in its step, whose result arrives before the move", () => {
  assert.deepEqual(ranLabels("bound-dispatch"), ["bound-show", "bound-check", "bound-arrived"]);
  const step = turn("bound-dispatch").find((record) => record.tools.includes("execute"));
  assert.deepEqual(step.tools, ["execute"]);
  assert.equal(moves("bound-dispatch").length, 1);
  assert(moveAccepted(moves("bound-dispatch")[0].result, tree("a")));
  const movedAt = one("server.event", (record) => record.type === "session.moved" && record.sessionID === bound && record.to === tree("a")).receipt;
  const answered = turn("bound-dispatch").find((record) => record.previous?.kind === "move").receipt;
  assert(movedAt < answered, "the move took effect at the end of the step, before the next step");
});
check("bound dispatch: the next step confirms the session at the Worktree with pwd and --status, and keeps its native identity", () => {
  const confirm = shell("bound-check");
  assert(confirmedAt(confirm, tree("a")));
  assert.equal(started("bound-check").env.OPENCODE_SESSION_ID, bound);
  assert.equal(started("bound-bind").env.OPENCODE_SESSION_ID, bound);
  assert.equal(info("bound-after").location, tree("a"));
});
check("bound dispatch: the Agent Run moves with it, keeping its identity, start and Issue Binding, and no work start runs there", () => {
  const before = runsAt("bound-before")["issue-1"];
  const after = runsAt("bound-after")["issue-1"];
  assert.equal(before.length, 1);
  assert.equal(after.length, 1);
  assert.equal(before[0].worktree, main);
  assert.equal(after[0].worktree, tree("a"));
  assert.equal(after[0].startedAt, before[0].startedAt);
  assert.equal(after[0].session, bound);
  assert.equal(after[0].workingDirectory, tree("a"));
  assert.match(output(shell("bound-arrived")), new RegExp(`: issue-1 \\(I_fixture_1\\) since ${before[0].startedAt.replaceAll(".", "\\.")}`));
  assert.deepEqual(decisions("bound-dispatch"), ["bound: retained the Agent Run"]);
  assert.equal(shells("bound-start").length, 0);
  assert.deepEqual(blockers("tree-a-bound-after"), ["agent-session", "agent-run"]);
});
check("bound dispatch: the conversation continues in the same session after the move", () => {
  const next = turn("bound-again")[0];
  assert.equal(next.sessionID, bound);
  assert.deepEqual(next.probes, ["bound-bind", "bound-dispatch", "bound-again"]);
  assert(next.messages > turn("bound-dispatch").at(-1).messages);
  assert.equal(shell("bound-again").cwd, tree("a"));
});

// Dispatch of an unbound session.
check("unbound dispatch: nothing moves with the session, so it runs work start at the Worktree", () => {
  assert.deepEqual(ranLabels("unbound-dispatch"), ["unbound-show", "unbound-check", "unbound-arrived", "unbound-start", "unbound-verify"]);
  assert(confirmedAt(shell("unbound-check"), tree("b")));
  assert.match(output(shell("unbound-arrived")), /^no active Issue work at this worktree/);
  assert.equal(shell("unbound-start").cwd, tree("b"));
  assert.match(output(shell("unbound-verify")), /: issue-2 \(I_fixture_2\) since /);
  assert.equal(runsAt("unbound-after")["issue-2"][0].worktree, tree("b"));
  assert.equal(info("unbound-after").location, tree("b"));
});

// Finish and switch.
check("finish: work stop, then the move to the main Worktree, frees the Issue Worktree for Cleanup", () => {
  assert.deepEqual(ranLabels("finish"), ["finish-stop", "finish-show", "finish-check"]);
  assert.match(output(shell("finish-show")), /^no active Issue work at this worktree/);
  assert(moveAccepted(moves("finish")[0].result, main));
  assert(confirmedAt(shell("finish-check"), main));
  assert.deepEqual(decisions("finish"), ["finish: finished"]);
  assert.equal(runsAt("finish-after")["issue-1"], undefined);
  assert.equal(info("finish-after").location, main);
  assert.deepEqual(blockers("tree-a-before-finish"), ["agent-session", "agent-run"]);
  assert.deepEqual(blockers("tree-a-after-finish"), []);
});
check("switch: the run on the current Issue ends, the session returns to the main Worktree, then dispatches to the next", () => {
  assert.deepEqual(ranLabels("switch"), ["switch-finish-stop", "switch-finish-show", "switch-finish-check", "switch-into-show",
    "switch-into-check", "switch-into-arrived", "switch-into-start", "switch-into-verify"]);
  assert.deepEqual(moves("switch").map((move) => move.target), [main, tree("c")]);
  assert(confirmedAt(shell("switch-finish-check"), main));
  assert(confirmedAt(shell("switch-into-check"), tree("c")));
  assert.match(output(shell("switch-into-arrived")), /^no active Issue work at this worktree/);
  const after = runsAt("switch-after");
  assert.equal(after["issue-2"], undefined);
  assert.equal(after["issue-3"][0].worktree, tree("c"));
  assert.equal(after["issue-3"][0].session, unbound);
  assert.deepEqual(blockers("tree-b-after-switch"), []);
});

// Timing.
check("same step: a call beside the move runs where the session was; the next step runs at the destination", () => {
  assert.deepEqual(turn("same-step").find((record) => record.step === 0).tools, ["execute", "shell"]);
  assert.equal(shell("same-step-beside").cwd, main);
  assert.equal(shell("same-step-next").cwd, tree("b"));
  assert(confirmedAt(shell("same-step-check"), tree("b")));
});

// Failures.
check("refused destinations: a missing path and a file fail the tool at once, and the session and its run stay put", () => {
  assert.equal(moves("missing-dispatch")[0].result, `Unable to move session to ${tree("missing")}`);
  assert.equal(moves("file-dispatch")[0].result, `Unable to move session to ${tree("not-a-directory")}`);
  assert.deepEqual(decisions("missing-dispatch"), ["missing: handoff, the move failed"]);
  assert.deepEqual(decisions("file-dispatch"), ["file: handoff, the move failed"]);
  assert.equal(info("missing-after").location, main);
  assert.equal(info("file-after").location, main);
  assert.equal(runsAt("refused-after")["issue-4"][0].worktree, main);
});
check("missing evidence: a move Dashpot could not record reads elsewhere, so the session hands off and runs no work start", () => {
  assert(moveAccepted(moves("unwritable-dispatch")[0].result, tree("e")));
  assert.equal(info("unwritable-after").location, tree("e"));
  const confirm = shell("unwritable-check");
  assert.equal(confirm.cwd, tree("e"));
  assert.match(identity(confirm), new RegExp(`, elsewhere: its freshest hook record, live, places it at \\$ROOT/repository, not here$`));
  assert.deepEqual(decisions("unwritable-dispatch"), ["unwritable: handoff, the move is not confirmed"]);
  assert.equal(shells("unwritable-start").length, 0);
  assert.deepEqual(one("events").unsuccessful, [{ kind: "hook:opencode:event", result: "failed", reason: null, error: "EACCES", session: sessionOf("Unwritable") }]);
});
check("a session whose permissions deny the move does not have the tool", () => {
  assert.match(moves("denied-dispatch")[0].result, /^Unknown tool 'opencode\.session_move'/);
  assert.deepEqual(decisions("denied-dispatch"), ["denied: handoff, the move failed"]);
  assert.equal(info("denied-after").location, main);
});
check("OpenCode asks the person nothing before a move: neither an ask rule nor a default configuration stops it", () => {
  assert.deepEqual(labelled("permissions", "asked-dispatch").asked, []);
  assert.equal(info("asked-after").location, tree("d"));
  assert.deepEqual(labelled("permissions", "default-dispatch").asked, []);
  assert.equal(info("default-after").location, tree("d"));
  assert.deepEqual(decisions("default-dispatch"), ["default: bound"]);
});

// Work the session started.
check("workers: a lead waits while work show lists its worker, and moves once the worker has ended", () => {
  const [first, second] = shells("workers-show");
  assert.match(output(first), /has 1 sub-agent listed as working/);
  assert.doesNotMatch(output(second), /listed as working/);
  assert(first.receipt < shell("worker-hold").receipt && shell("worker-hold").receipt < second.receipt);
  assert.deepEqual(decisions("workers-dispatch"), ["workers: waiting for this session's workers", "workers: retained the Agent Run"]);
  assert.equal(info("workers-while-running").location, main);
  assert.equal(info("workers-after").location, tree("d"));
  assert(confirmedAt(shells("workers-check").at(-1), tree("d")));
  const after = Object.entries(labelled("state", "workers-after").sessions).filter(([file]) => file.endsWith(`/${workers}.json`));
  assert(after.length && after.every(([, record]) => record.subagents.length === 0));
  assert(blockers("tree-d-workers-after").includes("agent-session"));
  assert(!blockers("tree-d-workers-after").includes("sub-agent"));
});

for (const item of checks) console.log(`ok - ${item}`);
console.log(`${checks.length} claims verified`);
console.log(drifted.length ? `Dashpot sources changed since the run: ${drifted.join(", ")}` : `Dashpot sources match the run's (${environment.dashpotHead})`);
