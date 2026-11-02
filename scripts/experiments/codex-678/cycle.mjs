// The shell command the fixture model asks a worker to run in its Worktree:
// one full Worker cycle, each step attempted whatever the step before it did,
// with nothing added to the environment the worker's shell was given. It
// prepares the environment with `uv sync --locked`, edits a tracked file, runs
// the repository's gate, commits with the tracked hooks running, pushes to
// the fixture's loopback remote, and appends to its Arc Ledger file in the
// main checkout. The fixture's tracked pre-commit hook prints the two cache
// variables it was given as a `HOOKENV` line, which the commit step keeps.
// Prints one `CYCLE` line, which reaches the runner as the tool output in the
// worker's next model request.
//
//   node cycle.mjs <label> <main checkout> <ledger file>
import { spawnSync } from "node:child_process";
import { appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const [label, main, ledger] = process.argv.slice(2);
// A refused write shows as one of these errors; each path on such a line is
// one the step tried to write.
const refusal = /Read-only file system|Permission denied|Operation not permitted|os error (?:30|13|1)\b|EROFS|EACCES|EPERM/;
const refusedPaths = (text) => [...new Set(text.split("\n").filter((line) => refusal.test(line))
  .flatMap((line) => [...line.matchAll(/\/(?:[^\s'"`:,()]+\/?)+/g)].map((match) => match[0].replace(/[.\/]+$/, ""))))];
const tail = (text) => text.replace(/\s+/g, " ").trim().slice(-400);
const run = (command, args) => {
  const started = Date.now();
  const ran = spawnSync(command, args, { encoding: "utf8", timeout: 240000, maxBuffer: 1 << 26 });
  const output = `${ran.stdout ?? ""}\n${ran.stderr ?? ""}${ran.error ? `\n${ran.error.message}` : ""}`;
  const hookEnv = /HOOKENV (\{.*\})/.exec(output)?.[1];
  return { ok: ran.status === 0, status: ran.status, ms: Date.now() - started, refused: refusedPaths(output), tail: tail(output.replace(/HOOKENV \{.*\}/g, "")),
    ...(hookEnv ? { hookEnv: JSON.parse(hookEnv) } : {}) };
};
const write = (action) => {
  try { action(); return { ok: true }; } catch (error) { return { ok: false, error: error.code ?? String(error.message).slice(0, 200), refused: error.path ? [error.path] : [] }; }
};

const steps = {
  prepare: run("uv", ["sync", "--locked", "--group", "dev"]),
  edit: write(() => appendFileSync("README.md", `Edited by ${label}.\n`)),
  gate: run("uv", ["run", "--locked", "pre-commit", "run", "--all-files"]),
  commit: (() => {
    const added = run("git", ["add", "README.md"]);
    return added.ok ? run("git", ["commit", "-m", `Cycle ${label}`]) : { ...added, step: "add" };
  })(),
  push: run("git", ["push", "origin", `HEAD:refs/heads/${label}`]),
  report: write(() => { mkdirSync(path.dirname(ledger), { recursive: true }); appendFileSync(ledger, `### ${label}\nCycle finished.\n-- end\n`); }),
};
const report = { label, cwd: process.cwd(), main, thread: process.env.CODEX_THREAD_ID ?? null,
  // The cache locations and terminal marker the worker's shell was given.
  inherited: { UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? null, PRE_COMMIT_HOME: process.env.PRE_COMMIT_HOME ?? null, terminal: process.env.SPIKE_TERMINAL ?? null },
  sandboxEnv: process.env.CODEX_SANDBOX ?? null, networkDisabled: process.env.CODEX_SANDBOX_NETWORK_DISABLED ?? null, steps };
console.log(`CYCLE ${JSON.stringify(report)}`);
