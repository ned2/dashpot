// The shell command the fixture model asks Codex to run. It reports the
// shell's identity claims, process group, session and ancestry to the
// runner's sink, then holds until the runner opens its gate:
//   node command.mjs <label> <gate>
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { ancestry } from "./ancestry.mjs";

const label = process.argv[2] ?? "unlabelled";
const gate = process.argv[3];
const stat = readFileSync("/proc/self/stat", "utf8");
const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
const record = {
  kind: "command", label, gate, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, pgid: Number(fields[2]), sid: Number(fields[3]),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX"))),
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm }) => ({ pid, ppid, comm })),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
// A gate the runner never opens ends the hold after four minutes, so an
// abandoned command cannot outlive the run for long.
const file = path.join(process.env.SPIKE_GATES, gate);
const started = Date.now();
while (!existsSync(file) && Date.now() < started + 240000) await new Promise((resolve) => setTimeout(resolve, 100));
await post("end", { opened: existsSync(file), heldMs: Date.now() - started });
console.log(JSON.stringify({ label, gate, opened: existsSync(file) }));
