// The shell command the fixture model asks OpenCode to run, or the runner
// opens in an OpenCode terminal. With a hold, it reports the command's
// identity claims, location and ancestry to the runner's sink; with `--` it
// runs the given Dashpot command from that shell, as the Issue-work skill
// does, and reports its exit status and output too.
//
// Usage: node command.mjs <label> [holdMs] [-- dashpot arguments...]
import { spawnSync } from "node:child_process";
import { ancestry } from "./ancestry.mjs";

const CLAIMS = ["DASHPOT_OPENCODE_SESSION_ID", "DASHPOT_OPENCODE_GENERATION", "DASHPOT_OPENCODE_PID",
  "DASHPOT_OPENCODE_UNCORROBORATED", "DASHPOT_AGENT_SESSION", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"];
const label = process.argv[2] ?? "unlabelled";
const split = process.argv.indexOf("--");
const dashpot = split >= 0 ? process.argv.slice(split + 1) : null;
const holdMs = Number((split >= 0 ? process.argv.slice(3, split) : process.argv.slice(3))[0] ?? 0);
const record = {
  label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, startedAt: Date.now(),
  // Absent and blanked are different facts: the plugin blanks inherited claims.
  env: Object.fromEntries(CLAIMS.map((name) => [name, process.env[name] ?? null])),
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm, cmdline }) => ({ pid, ppid, comm, cmdline })),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
await new Promise((resolve) => setTimeout(resolve, holdMs));
if (dashpot) {
  const result = spawnSync(process.env.SPIKE_DASHPOT, dashpot, { encoding: "utf8", timeout: 60000 });
  await post("end", { dashpot: { args: dashpot, status: result.status, stdout: result.stdout?.slice(0, 2000), stderr: result.stderr?.slice(-2000) } });
} else {
  await post("end");
}
console.log(JSON.stringify({ label }));
