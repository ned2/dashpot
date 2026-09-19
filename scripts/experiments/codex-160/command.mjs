// The shell command the fixture model asks Codex to run: report the shell's
// identity claims, location, and ancestry to the runner's sink, then hold for
// the requested time so a client can leave or interrupt mid-command.
import { ancestry } from "./ancestry.mjs";

const label = process.argv[2] ?? "unlabelled";
const holdMs = Number(process.argv[3] ?? 200);
const record = {
  kind: "command", label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX"))),
  ancestry: ancestry(process.ppid),
};
const post = (phase) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
await new Promise((resolve) => setTimeout(resolve, holdMs));
await post("end");
console.log(JSON.stringify({ label, pid: record.pid, thread: record.env.CODEX_THREAD_ID ?? null, session: record.env.CODEX_SESSION_ID ?? null }));
