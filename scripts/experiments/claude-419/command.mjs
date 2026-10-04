// The Bash command the fixture model asks Claude Code to run. It reports the
// shell's identity claims, location, and ancestry to the runner's sink, then
// does one of three things:
//   node command.mjs <label> [hold ms]         holds for that long (default 200)
//   node command.mjs <label> wait <gate>       holds until the runner opens the gate
//   node command.mjs <label> -- <dashpot args> runs Dashpot from this shell, as
//                                              the Issue-work skill does
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { ancestry } from "./ancestry.mjs";

// The Claude Code variables that say which session and process a shell or
// hook belongs to; the rest are the fixture's own settings, recorded once.
const identityEnv = ["CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_CHILD_SESSION",
  "CLAUDE_JOB_DIR", "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"];
const label = process.argv[2] ?? "unlabelled";
const dashpot = process.argv[3] === "--" ? process.argv.slice(4) : null;
const gate = process.argv[3] === "wait" ? process.argv[4] : null;
const holdMs = dashpot || gate ? 0 : Number(process.argv[3] ?? 200);
const record = {
  kind: "command", label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, gate: gate ?? undefined,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => identityEnv.includes(key))),
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm }) => ({ pid, ppid, comm })),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
if (dashpot) {
  const result = spawnSync(process.env.SPIKE_DASHPOT, dashpot, { encoding: "utf8", timeout: 60000 });
  const outcome = { args: dashpot, status: result.status, stdout: result.stdout?.slice(0, 2000), stderr: result.stderr?.slice(-2000) };
  await post("end", { dashpot: outcome });
  console.log(JSON.stringify({ label, status: outcome.status }));
} else if (gate) {
  // A gate the runner never opens ends the hold after two minutes, so an
  // abandoned shell cannot outlive the run for long.
  const file = path.join(process.env.SPIKE_GATES, gate);
  const end = Date.now() + 120000;
  while (!existsSync(file) && Date.now() < end) await new Promise((resolve) => setTimeout(resolve, 100));
  await post("end", { opened: existsSync(file) });
  console.log(JSON.stringify({ label, gate, opened: existsSync(file) }));
} else {
  await new Promise((resolve) => setTimeout(resolve, holdMs));
  await post("end");
  console.log(JSON.stringify({ label, pid: record.pid, session: record.env.CLAUDE_CODE_SESSION_ID ?? null }));
}
