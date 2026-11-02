// The shell command the fixture model asks a lead to run: the four checks
// the execute-issues skill's Codex section has a lead run before it binds,
// word for word, a control write outside every writable root, the write-free
// probe the read-only preflight would run, then `git worktree add` for each
// worker Worktree the lead will dispatch. Prints one `CHECKS` line of
// outcomes, which reaches the runner as the tool output in the lead's next
// model request.
//
//   node checks.mjs <label> <main checkout> <Worktree Root> <outside directory> <denied file> [worktree name ...]
import { spawnSync } from "node:child_process";
import path from "node:path";
import { probe as runProbe } from "./probe.mjs";

const [label, main, worktreeRoot, outside, denied, ...worktrees] = process.argv.slice(2);
const short = (text) => String(text ?? "").split("\n").filter(Boolean).slice(-3).join(" | ").slice(-300);
const sh = (command, cwd = main) => {
  const ran = spawnSync("sh", ["-c", command], { cwd, encoding: "utf8", timeout: 60000 });
  return { ok: ran.status === 0, status: ran.status, stdout: (ran.stdout ?? "").trim().slice(0, 400),
    ...(ran.status === 0 ? {} : { error: short(ran.stderr || ran.stdout || ran.error?.message) }) };
};
const gitDir = spawnSync("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd: main, encoding: "utf8" }).stdout.trim();
const uvCache = path.join(worktreeRoot, ".cache", "uv");
const preCommitCache = path.join(worktreeRoot, ".cache", "pre-commit");
// The fourth check passes when both variables name a directory inside the
// Worktree Root, where the grant puts the caches.
const fourth = sh('echo "UV_CACHE_DIR=$UV_CACHE_DIR PRE_COMMIT_HOME=$PRE_COMMIT_HOME"');
const inside = (value) => Boolean(value) && value.startsWith(`${worktreeRoot}/`);
const named = Object.fromEntries(fourth.stdout.split(" ").map((pair) => [pair.slice(0, pair.indexOf("=")), pair.slice(pair.indexOf("=") + 1)]));
// The probe runs before the checks write anything.
const probe = runProbe(label, main, worktreeRoot, uvCache, preCommitCache, outside, denied);

const results = {
  worktreeRoot: sh(`touch ${worktreeRoot}/.execute-issues-check && rm ${worktreeRoot}/.execute-issues-check`),
  gitDir: sh(`touch ${gitDir}/execute-issues-check && rm ${gitDir}/execute-issues-check`),
  network: sh("git ls-remote --exit-code origin HEAD"),
  caches: { ...fourth, ok: fourth.ok && inside(named.UV_CACHE_DIR) && inside(named.PRE_COMMIT_HOME) },
  outside: sh(`touch ${outside}/check-${label}`),
  ...Object.fromEntries(worktrees.map((name) => [`worktreeAdd:${name}`, sh(`git worktree add -b ${name} ${path.join(worktreeRoot, name)}`)])),
};
const report = { label, cwd: process.cwd(), gitDir, results, probe };
console.log(`CHECKS ${JSON.stringify(report)}`);
