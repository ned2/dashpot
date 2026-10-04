// The Bash command the fixture model asks Claude Code to run, in the
// foreground or with `run_in_background`. It reports the shell's identity
// claims, process group, session and ancestry to the runner's sink, then:
//   node command.mjs <label> [hold ms]    holds for that long (default 200)
//   node command.mjs <label> wait <gate>  holds until the runner opens the gate
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { ancestry } from "./ancestry.mjs";

const identityEnv = ["CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_CHILD_SESSION"];
const label = process.argv[2] ?? "unlabelled";
const gate = process.argv[3] === "wait" ? process.argv[4] : null;
const holdMs = gate ? 0 : Number(process.argv[3] ?? 200);
// The process group and session this command runs in, from /proc/self/stat.
const stat = readFileSync("/proc/self/stat", "utf8");
const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
const record = {
  kind: "command", label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, pgid: Number(fields[2]), sid: Number(fields[3]),
  gate: gate ?? undefined,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => identityEnv.includes(key))),
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm }) => ({ pid, ppid, comm })),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
if (gate) {
  // A gate the runner never opens ends the hold after four minutes, so an
  // abandoned command cannot outlive the run for long.
  const file = path.join(process.env.SPIKE_GATES, gate);
  const started = Date.now();
  const end = started + 240000;
  while (!existsSync(file) && Date.now() < end) await new Promise((resolve) => setTimeout(resolve, 100));
  await post("end", { opened: existsSync(file), heldMs: Date.now() - started });
  console.log(JSON.stringify({ label, gate, opened: existsSync(file) }));
} else {
  await new Promise((resolve) => setTimeout(resolve, holdMs));
  await post("end");
  console.log(JSON.stringify({ label, pid: record.pid, session: record.env.CLAUDE_CODE_SESSION_ID ?? null }));
}
