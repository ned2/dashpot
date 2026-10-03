// The shell command the fixture model asks OpenCode to run. It reports the
// shell's identity variables, location and nearest ancestors to the runner's
// sink, and holds for the given time.
//
// Usage: node command.mjs <label> [holdMs]
import { ancestry } from "./ancestry.mjs";

const NAMES = ["OPENCODE_SESSION_ID", "OPENCODE", "AGENT", "AI_AGENT", "SPIKE_HOST_PID", "SPIKE_PLUGIN_INSTANCE",
  "SPIKE_V1_REFUSED", "DASHPOT_AGENT_SESSION", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"];
const label = process.argv[2] ?? "unlabelled";
const holdMs = Number(process.argv[3] ?? 0);
const record = {
  label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid,
  // Absent and empty are different facts.
  env: Object.fromEntries(NAMES.map((name) => [name, process.env[name] ?? null])),
  ancestry: ancestry(process.ppid, 3).map(({ pid, comm, outside }) => ({ pid, comm, outside })),
};
const post = (phase) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ ...record, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
await new Promise((resolve) => setTimeout(resolve, holdMs));
await post("end");
console.log(JSON.stringify({ label }));
