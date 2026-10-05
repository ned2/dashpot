// The Bash command the fixture model asks Claude Code to run. It reports the
// shell's identity claims, the Lead-link probe variables, its location and
// ancestry to the runner's sink, then:
//   node command.mjs <label> [hold ms]        holds for that long (default 200)
//   node command.mjs <label> wait <gate>      holds until the runner opens the gate
//   node command.mjs <label> -- <dashpot args> runs that Dashpot command from this
//                                              shell, as the Issue-work skill does
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { ancestry } from "./ancestry.mjs";

const label = process.argv[2] ?? "unlabelled";
const dashpot = process.argv[3] === "--" ? process.argv.slice(4) : null;
const gate = process.argv[3] === "wait" ? process.argv[4] : null;
const holdMs = dashpot || gate ? 0 : Number(process.argv[3] ?? 200);
const probeEnv = (key) => (key.startsWith("CLAUDE") && key !== "CLAUDE_CODE_MESSAGING_TOKEN") || key.startsWith("DASHPOT_LEAD") || key.startsWith("DASHPOT_479_") || key === "SPIKE_STAMP";
const record = {
  kind: "command", label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, gate: gate ?? undefined,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => probeEnv(key))),
  ancestry: ancestry(process.ppid),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
if (dashpot) {
  const result = spawnSync(process.env.SPIKE_DASHPOT, dashpot, { encoding: "utf8", timeout: 60000 });
  const outcome = { args: dashpot, status: result.status, stdout: result.stdout?.slice(0, 2000), stderr: result.stderr?.slice(-2000) };
  await post("end", { dashpot: outcome });
  console.log(JSON.stringify({ label, status: outcome.status }));
} else if (gate) {
  // A gate the runner never opens ends the hold after four minutes.
  const file = path.join(process.env.SPIKE_GATES, gate);
  const started = Date.now();
  while (!existsSync(file) && Date.now() < started + 240000) await new Promise((resolve) => setTimeout(resolve, 100));
  await post("end", { opened: existsSync(file), heldMs: Date.now() - started });
  console.log(JSON.stringify({ label, gate, opened: existsSync(file) }));
} else {
  await new Promise((resolve) => setTimeout(resolve, holdMs));
  await post("end");
  console.log(JSON.stringify({ label, pid: record.pid, session: record.env.CLAUDE_CODE_SESSION_ID ?? null }));
}
