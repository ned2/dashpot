// The shell command the fixture model asks a Codex thread to run: report the
// thread's identity from its environment to the runner's sink, optionally run
// one `dashpot work` command inside the fixture's session and report its
// outcome, then hold for the requested time, so a turn stays running while
// the runner interrupts it. A signal the process can catch is reported before
// it exits; one it cannot, such as SIGKILL, leaves no `end`.
//
//   node command.mjs <label> <hold ms> [start-<n> | show | -]
import { spawnSync } from "node:child_process";

const label = process.argv[2] ?? "unlabelled";
const holdMs = Number(process.argv[3] ?? 200);
const work = process.argv[4] && process.argv[4] !== "-" ? process.argv[4] : null;
const record = { label, pid: process.pid, ppid: process.ppid, cwd: process.cwd(),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX_"))) };
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, async () => { await post("signal", { signal }); process.exit(128); });
}
await post("start");
if (work) {
  const args = work.startsWith("start-") ? ["work", "start", work.slice("start-".length)] : ["work", work];
  const ran = spawnSync(process.env.SPIKE_DASHPOT, args, { encoding: "utf8", timeout: 30000 });
  // Dashpot's own output about the fixture's Issues and Worktrees.
  await post("work", { work: { args, status: ran.status, signal: ran.signal, stdout: (ran.stdout ?? "").slice(0, 1500), stderr: (ran.stderr ?? "").slice(0, 800) } });
}
await new Promise((resolve) => setTimeout(resolve, holdMs));
await post("end");
console.log(JSON.stringify({ label, thread: record.env.CODEX_THREAD_ID ?? null }));
