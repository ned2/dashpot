// The shell command the fixture model asks OpenCode to run. It reports the
// session identity OpenCode gave the shell, its location and ancestry to the
// runner's sink when it starts, holds for the given time, and reports again
// when it ends, so the trace shows when a Sub-agent was executing.
//
// Usage: node command.mjs <label> [holdMs]
import { ancestry } from "./ancestry.mjs";

const label = process.argv[2] ?? "unlabelled";
const holdMs = Number(process.argv[3] ?? 0);
const record = {
  label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, startedAt: Date.now(),
  env: { OPENCODE_SESSION_ID: process.env.OPENCODE_SESSION_ID ?? null, DASHPOT_OPENCODE_PID: process.env.DASHPOT_OPENCODE_PID ?? null },
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm, outside }) => ({ pid, ppid, comm, outside })),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
await new Promise((resolve) => setTimeout(resolve, holdMs));
await post("end", { endedAt: Date.now() });
console.log(JSON.stringify({ label }));
