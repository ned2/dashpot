// The shell command the fixture model asks Codex to run: try each write a
// lead or a worker of the execute-issues skill would make, and one commit,
// from inside Codex's sandbox, then print one `PROBE` line of outcomes. The
// line reaches the runner as the tool output in the agent's next model
// request, since the sandbox may refuse every other channel.
//
//   node probe.mjs <label> <main checkout> <worktree> <outside directory>
import { spawnSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const [label, main, worktree, outside] = process.argv.slice(2);
const skillState = (checkout) => path.join(checkout, ".dashpot", "state", "skills", "dashpot-execute-issues");
const mail = path.join(skillState(main), "arcs", "fixture", "mail");
const short = (text) => String(text ?? "").split("\n").filter(Boolean).slice(0, 2).join(" | ").slice(0, 200);
const attempt = (action) => {
  try { const detail = action(); return { ok: true, ...(detail ? { detail } : {}) }; } catch (error) { return { ok: false, error: error.code ?? short(error.message) }; }
};
const git = (...args) => {
  const ran = spawnSync("git", ["-C", worktree, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", ...args], { encoding: "utf8", timeout: 20000 });
  return { ok: ran.status === 0, status: ran.status, ...(ran.status === 0 ? {} : { error: short(ran.stderr || ran.error?.message) }) };
};
const gitDir = spawnSync("git", ["-C", worktree, "rev-parse", "--absolute-git-dir"], { encoding: "utf8" }).stdout.trim();
const status = (() => { try { return readFileSync("/proc/self/status", "utf8"); } catch { return ""; } })();
const field = (name) => status.match(new RegExp(`^${name}:\\s*(\\S+)`, "m"))?.[1] ?? null;
const worktreeStateExisted = existsSync(path.join(worktree, ".dashpot", "state"));

const results = {
  // The mail directory proposed for #637 inside an Arc's ledger directory
  // in the lead's checkout: a worker's own mailbox file, and the broadcast
  // file the runner wrote there for reading.
  mainLedgerWrite: attempt(() => { mkdirSync(mail, { recursive: true }); appendFileSync(path.join(mail, `${label}.md`), `## 1 ${label}\n-- end 1\n`); }),
  mainLedgerRead: attempt(() => readFileSync(path.join(mail, "broadcast.md"), "utf8").includes("BROADCAST") ? "marker" : "no-marker"),
  mainTracked: attempt(() => appendFileSync(path.join(main, "README.md"), `${label}\n`)),
  mainGit: attempt(() => writeFileSync(path.join(main, ".git", `probe-${label}`), label)),
  // A hook an unsandboxed `git` would later run: whether a writable Git
  // directory lets a sandboxed agent plant one. The name is not a hook's.
  mainGitHooks: attempt(() => writeFileSync(path.join(main, ".git", "hooks", `probe-${label}`), label)),
  // The location `references/harnesses.md` uses for the status and
  // broadcast files today: the Worktree's own Git directory.
  worktreeGitDir: attempt(() => writeFileSync(path.join(gitDir, "execute-issues-status"), label)),
  worktreeTracked: attempt(() => appendFileSync(path.join(worktree, "README.md"), `${label}\n`)),
  // A status file in the Worktree's own ignored state, created from nothing
  // with the self-ignoring `.gitignore` Dashpot writes, and whether Git then
  // ignores it.
  worktreeState: attempt(() => {
    const state = path.join(worktree, ".dashpot", "state");
    mkdirSync(skillState(worktree), { recursive: true });
    if (!existsSync(path.join(state, ".gitignore"))) writeFileSync(path.join(state, ".gitignore"), "*\n");
    appendFileSync(path.join(skillState(worktree), "status.md"), `## 1 ${label}\n-- end 1\n`);
  }),
  worktreeStateIgnored: git("check-ignore", "-q", path.join(".dashpot", "state", "skills", "dashpot-execute-issues", "status.md")),
  worktreeAdd: git("add", "README.md"),
  worktreeCommit: git("commit", "-m", `Probe ${label}`),
  // A control outside every writable root, which shows the sandbox applies.
  outside: attempt(() => writeFileSync(path.join(outside, `probe-${label}`), label)),
};
const report = { label, cwd: process.cwd(), gitDir, worktreeStateExisted, thread: process.env.CODEX_THREAD_ID ?? null,
  sandboxEnv: process.env.CODEX_SANDBOX ?? null, networkDisabled: process.env.CODEX_SANDBOX_NETWORK_DISABLED ?? null,
  noNewPrivs: field("NoNewPrivs"), seccomp: field("Seccomp"), results };
console.log(`PROBE ${JSON.stringify(report)}`);
