// The shell command the fixture model asks a Codex thread to run: report the
// thread's identity from its environment to the runner's sink, then hold for
// the requested time, so a worker's turn stays running while its lead acts.
//
//   node command.mjs <label> <hold ms>
const label = process.argv[2] ?? "unlabelled";
const holdMs = Number(process.argv[3] ?? 200);
const record = { label, pid: process.pid, ppid: process.ppid,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX_"))) };
const post = (phase) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body: JSON.stringify({ ...record, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
await new Promise((resolve) => setTimeout(resolve, holdMs));
await post("end");
console.log(JSON.stringify({ label, thread: record.env.CODEX_THREAD_ID ?? null }));
