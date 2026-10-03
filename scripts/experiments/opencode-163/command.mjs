// The shell command the fixture model asks OpenCode to run, or the runner
// runs as a user shell or opens in an OpenCode terminal. It reports the
// command's identity variables, location and ancestry to the runner's sink
// when it starts, holds for the given time, and with `--` runs the given
// Dashpot command from that shell, as the Issue-work skill does, reporting
// its exit status and output when it ends.
//
// Usage: node command.mjs <label> [holdMs] [-- dashpot arguments...]
import { spawnSync } from "node:child_process";
import { ancestry } from "./ancestry.mjs";

const NAMES = ["OPENCODE_SESSION_ID", "OPENCODE", "DASHPOT_OPENCODE_PID", "DASHPOT_OPENCODE_REFUSAL",
  "DASHPOT_AGENT_SESSION", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"];
const label = process.argv[2] ?? "unlabelled";
const split = process.argv.indexOf("--");
const dashpot = split >= 0 ? process.argv.slice(split + 1) : null;
const holdMs = Number((split >= 0 ? process.argv.slice(3, split) : process.argv.slice(3))[0] ?? 0);
const record = {
  label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, startedAt: Date.now(),
  // Absent and blanked are different facts: the plugin blanks inherited claims.
  env: Object.fromEntries(NAMES.map((name) => [name, process.env[name] ?? null])),
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm, cmdline, outside }) => ({ pid, ppid, comm, cmdline, outside })),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
await new Promise((resolve) => setTimeout(resolve, holdMs));
if (dashpot) {
  const result = spawnSync(process.env.SPIKE_DASHPOT, dashpot, { encoding: "utf8", timeout: 60000 });
  // Whole, not cut: the runner redacts the fixture's paths, and a cut path
  // would escape it.
  await post("end", { endedAt: Date.now(), dashpot: { args: dashpot, status: result.status, stdout: result.stdout, stderr: result.stderr } });
} else {
  await post("end", { endedAt: Date.now() });
}
console.log(JSON.stringify({ label }));
