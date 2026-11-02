// The write-free probe for Issue #678, run both inside a Codex session, by
// the checks a lead runs, and under `codex sandbox`, as the read-only
// preflight proposed in Issue #679 would run it. It writes nothing: `test -w`
// asks the kernel whether a write would be allowed, the denied-read attempt
// keeps only its outcome, never a byte, and `git ls-remote` only reads the
// loopback remote. Run as a script, it prints one `PROBE` line; the checks
// call `probe` in their own process instead, since a Node child of Node
// prints nothing in a sandbox whose network is restricted (`nestedNode`).
//
//   node probe.mjs <label> <main checkout> <Worktree Root> <uv cache> <pre-commit cache> <outside directory> <denied file>
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const short = (text) => String(text ?? "").split("\n").filter(Boolean).slice(-2).join(" | ").slice(-240);

export const probe = (label, main, worktreeRoot, uvCache, preCommitCache, outside, denied) => {
  const sh = (command) => {
    const ran = spawnSync("sh", ["-c", command], { cwd: main, encoding: "utf8", timeout: 30000 });
    return { ok: ran.status === 0, status: ran.status, ...(ran.status === 0 ? {} : { error: short(ran.stderr || ran.stdout || ran.error?.message) }) };
  };
  const gitDir = spawnSync("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd: main, encoding: "utf8" }).stdout.trim();
  const status = (() => { try { return readFileSync("/proc/self/status", "utf8"); } catch { return ""; } })();
  const field = (name) => status.match(new RegExp(`^${name}:\\s*(\\S+)`, "m"))?.[1] ?? null;
  // Only whether the read succeeded, and the error code if not.
  const deniedRead = (() => { try { readFileSync(denied); return { ok: true }; } catch (error) { return { ok: false, code: error.code ?? null }; } })();
  // Whether a Node child of this process runs and prints.
  const nested = spawnSync(process.execPath, ["-e", "process.stdout.write('ok')"], { encoding: "utf8", timeout: 30000 });
  return {
    label, cwd: process.cwd(), gitDir,
    testW: {
      worktreeRoot: sh(`test -w ${worktreeRoot}`).ok,
      gitDir: sh(`test -w ${gitDir}`).ok,
      uvCache: sh(`test -w ${uvCache}`).ok,
      preCommitCache: sh(`test -w ${preCommitCache}`).ok,
      outside: sh(`test -w ${outside}`).ok,
    },
    network: sh("git ls-remote --exit-code origin HEAD"),
    deniedRead,
    env: { UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? null, PRE_COMMIT_HOME: process.env.PRE_COMMIT_HOME ?? null,
      terminal: process.env.SPIKE_TERMINAL ?? null, sandbox: process.env.CODEX_SANDBOX ?? null,
      networkDisabled: process.env.CODEX_SANDBOX_NETWORK_DISABLED ?? null, thread: process.env.CODEX_THREAD_ID ?? null },
    nestedNode: { printed: nested.stdout === "ok", status: nested.status, error: nested.error?.code ?? null },
    noNewPrivs: field("NoNewPrivs"), seccomp: field("Seccomp"), pid: process.pid, ppid: process.ppid,
  };
};

if (process.argv[1] === fileURLToPath(import.meta.url)) console.log(`PROBE ${JSON.stringify(probe(...process.argv.slice(2)))}`);
