// Independent verifier for a Codex 637 sandbox trace. Checks the recorded
// probe outcomes and model requests against the claims the spike makes for
// the pinned release, without importing the runner.
//
//   node verify.mjs <trace.jsonl> [expected version]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const [tracePath, expectedVersion = "0.160.0"] = process.argv.slice(2);
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};

// The trace names the exact sources that produced it, this file included.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "probe.mjs", "run.mjs", "verify.mjs"];
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), scripts);
for (const file of scripts) {
  assert.equal(createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex"), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
}
assert.deepEqual(of("scenario").map((record) => record.name), ["default", "roots", "git-roots", "linked-lead", "message"]);
assert.deepEqual(of("server.error"), []);

// Every lead ran `workspace-write` with network access, the system
// temporary directory and TMPDIR all excluded, and the writable roots its
// scenario names.
const worktrees = environment.worktreesDir;
const gitDir = `${environment.main}/.git`;
const rootsOf = { "lead-v2": [], "lead-v1": [], "lead-roots": [worktrees], "lead-v1-roots": [worktrees], "lead-git": [worktrees, gitDir], "lead-linked": [], "lead-message": [] };
for (const [name, roots] of Object.entries(rootsOf)) {
  assert.deepEqual(one("thread.start", (record) => record.name === name).sandbox,
    { type: "workspaceWrite", writableRoots: roots, networkAccess: false, excludeTmpdirEnvVar: true, excludeSlashTmp: true }, `${name}'s sandbox`);
}

// 1 and 2. Where each probe could write, and whether it could commit. A
// worker's probe ran in its own Worktree; every probe has the same targets.
const { missing, probes } = one("probes.outcome");
assert.deepEqual(missing, []);
const targets = ["mainLedgerWrite", "mainLedgerRead", "mainTracked", "mainGit", "mainGitHooks", "worktreeGitDir", "worktreeTracked", "worktreeState",
  "worktreeStateIgnored", "worktreeAdd", "worktreeCommit", "outside"];
const allowed = (...names) => Object.fromEntries(targets.map((target) => [target, names.includes(target)]));
const fromMain = allowed("mainLedgerWrite", "mainLedgerRead", "mainTracked");
const withWorktrees = allowed("mainLedgerWrite", "mainLedgerRead", "mainTracked", "worktreeTracked", "worktreeState", "worktreeStateIgnored");
const withGit = allowed(...targets.filter((target) => target !== "outside"));
const expected = {
  "lead-v2": fromMain, "worker-v2": fromMain, "worker-v1": fromMain,
  "lead-roots": withWorktrees, "worker-roots": withWorktrees, "worker-v1-roots": withWorktrees,
  "lead-git": withGit, "worker-git": withGit,
  // A lead bound in a linked Worktree reads the main checkout's mail but
  // cannot write it.
  "lead-linked": allowed("mainLedgerRead", "worktreeTracked", "worktreeState", "worktreeStateIgnored"),
};
assert.deepEqual(Object.keys(probes).sort(), Object.keys(expected).sort());
for (const [label, outcomes] of Object.entries(expected)) {
  const report = probes[label];
  assert.deepEqual(Object.fromEntries(targets.map((target) => [target, report.results[target].ok])), outcomes, `${label}'s outcomes`);
  assert.equal(report.worktreeStateExisted, false, `${label}'s Worktree had no .dashpot/state/ before its probe`);
  assert.equal(report.networkDisabled, "1", `${label} ran under the sandbox`);
  assert.equal(report.noNewPrivs, "1");
  assert.equal(report.cwd, label.startsWith("worker") || label === "lead-linked" ? `${worktrees}/${label}` : environment.main);
}
// A read-only Git directory refuses the commit at its first lock file, in
// the main checkout's `.git/worktrees/<name>/`.
for (const label of ["lead-v2", "worker-v2", "worker-v1", "lead-roots", "worker-roots", "worker-v1-roots", "lead-linked"]) {
  assert.equal(probes[label].results.worktreeAdd.error, `fatal: Unable to create '${gitDir}/worktrees/${label}/index.lock': Read-only file system`);
}
assert.equal(probes["lead-v2"].results.mainLedgerRead.detail, "marker", "the probe read the lead's broadcast");

// 5. A v2 lead's `send_message` to a running worker: the worker's command
// runs to its end, and the message is in the worker's next model request,
// after that command's output.
const message = one("message.outcome");
const sent = message.lead_requests.find((record) => record.action === "send_message");
const [first, second, last] = message.worker_requests;
const carries = (record) => record.markers.some(([, type, , marker]) => type === "agent_message" && marker === "NOTE:to-worker");
assert(first.receiptTime < sent.receiptTime && !carries(first), "the worker was running its command when the lead sent");
assert(second.receiptTime - first.receiptTime >= 8000, "the lead's message did not cut the worker's 8 s command short");
assert(carries(second) && carries(last), "the message reached the worker's next model request");
assert.deepEqual(second.tail, [["function_call", null], ["function_call_output", null], ["agent_message", null]]);
assert.match(message.lead_requests.at(-1).lastOutput, /"timed_out":false/);
assert.deepEqual(of("cleanup.kill"), []);

console.log(JSON.stringify({ verified: tracePath, version: environment.version, probes: Object.keys(probes).length }));
