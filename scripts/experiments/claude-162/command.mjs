// The Bash command the fixture model asks Claude Code to run. With a hold, it
// reports the shell's identity claims, location, and ancestry to the runner's
// sink; with `--` it runs the given Dashpot command from that shell, as the
// Issue-work skill does, and reports its exit status and output too.
import { spawnSync } from "node:child_process";
import { ancestry } from "./ancestry.mjs";

const label = process.argv[2] ?? "unlabelled";
const dashpot = process.argv[3] === "--" ? process.argv.slice(4) : null;
const holdMs = dashpot ? 0 : Number(process.argv[3] ?? 200);
const record = {
  kind: "command", label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CLAUDE") && key !== "CLAUDE_CODE_MESSAGING_TOKEN")),
  ancestry: ancestry(process.ppid),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
if (dashpot) {
  const result = spawnSync(process.env.SPIKE_DASHPOT, dashpot, { encoding: "utf8", timeout: 60000 });
  const outcome = { args: dashpot, status: result.status, stdout: result.stdout?.slice(0, 2000), stderr: result.stderr?.slice(-2000) };
  await post("end", { dashpot: outcome });
  console.log(JSON.stringify({ label, status: outcome.status }));
} else {
  await new Promise((resolve) => setTimeout(resolve, holdMs));
  await post("end");
  console.log(JSON.stringify({ label, pid: record.pid, session: record.env.CLAUDE_CODE_SESSION_ID ?? null }));
}
