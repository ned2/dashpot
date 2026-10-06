// The shell command the fixture model asks a lead to run: the three checks
// the execute-issues skill's Codex section has a lead run before it binds,
// word for word, then `git worktree add` for each worker Worktree the lead
// will dispatch, and a control write outside every writable root. Prints one
// `CHECKS` line of outcomes, which reaches the runner as the tool output in
// the lead's next model request.
//
//   node checks.mjs <label> <main checkout> <Worktree Root> <outside directory> [worktree name ...]
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const [label, main, worktreeRoot, outside, ...worktrees] = process.argv.slice(2);
const short = (text) => String(text ?? "").split("\n").filter(Boolean).slice(-3).join(" | ").slice(-300);
const sh = (command, cwd = main) => {
  const ran = spawnSync("sh", ["-c", command], { cwd, encoding: "utf8", timeout: 60000 });
  return { ok: ran.status === 0, status: ran.status, ...(ran.status === 0 ? {} : { error: short(ran.stderr || ran.stdout || ran.error?.message) }) };
};
const gitDir = spawnSync("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd: main, encoding: "utf8" }).stdout.trim();
const status = (() => { try { return readFileSync("/proc/self/status", "utf8"); } catch { return ""; } })();
const field = (name) => status.match(new RegExp(`^${name}:\\s*(\\S+)`, "m"))?.[1] ?? null;

const results = {
  worktreeRoot: sh(`touch ${worktreeRoot}/.execute-issues-check && rm ${worktreeRoot}/.execute-issues-check`),
  gitDir: sh(`touch ${gitDir}/execute-issues-check && rm ${gitDir}/execute-issues-check`),
  network: sh("git ls-remote --exit-code origin HEAD"),
  outside: sh(`touch ${outside}/check-${label}`),
  ...Object.fromEntries(worktrees.map((name) => [`worktreeAdd:${name}`, sh(`git worktree add -b ${name} ${path.join(worktreeRoot, name)}`)])),
};
const report = { label, cwd: process.cwd(), gitDir, thread: process.env.CODEX_THREAD_ID ?? null,
  sandboxEnv: process.env.CODEX_SANDBOX ?? null, networkDisabled: process.env.CODEX_SANDBOX_NETWORK_DISABLED ?? null,
  noNewPrivs: field("NoNewPrivs"), seccomp: field("Seccomp"), results };
console.log(`CHECKS ${JSON.stringify(report)}`);
