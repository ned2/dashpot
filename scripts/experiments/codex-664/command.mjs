// The shell command the fixture model asks Codex to run: report the shell's
// identity claims, location, and ancestry to the runner's sink, optionally
// run one `dashpot work` command inside the session and report its outcome,
// then hold for the requested time so a worker stays live while the runner
// observes its lead.
import { spawnSync } from "node:child_process";
import { ancestry } from "./ancestry.mjs";

const label = process.argv[2] ?? "unlabelled";
const holdMs = Number(process.argv[3] ?? 200);
// `start-<n>`, `show`, `stop`, or `relocate` (to the shell's own directory):
// the `dashpot work` subcommand to run.
const work = process.argv[4] && process.argv[4] !== "-" ? process.argv[4] : null;
const record = {
  kind: "command", label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX"))),
  ancestry: ancestry(process.ppid),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
if (work) {
  const args = work.startsWith("start-") ? ["work", "start", work.slice("start-".length)] : work === "relocate" ? ["work", "relocate", "."] : ["work", work];
  const ran = spawnSync(process.env.SPIKE_DASHPOT, args, { encoding: "utf8", timeout: 30000 });
  // Dashpot's own output about the fixture's Issues and Worktrees.
  await post("work", { work: { args, status: ran.status, signal: ran.signal, stdout: (ran.stdout ?? "").slice(0, 1500), stderr: (ran.stderr ?? "").slice(0, 800) } });
}
await new Promise((resolve) => setTimeout(resolve, holdMs));
await post("end");
console.log(JSON.stringify({ label, pid: record.pid, thread: record.env.CODEX_THREAD_ID ?? null, session: record.env.CODEX_SESSION_ID ?? null }));
