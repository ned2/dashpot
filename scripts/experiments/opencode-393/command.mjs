// The shell command the fixture model asks OpenCode to run, or the runner
// asks it to run as a user shell or terminal. It reports the shell's identity
// variables, location and ancestry to the runner's sink when it starts, holds
// for the given time, and reports again when it ends. With SPIKE_CHATTY it
// prints a line every minute of the hold, so the shell's output streams.
//
// Usage: node command.mjs <label> [holdMs] [SPIKE_CLEAR | SPIKE_CHATTY]
import { ancestry, describe } from "./ancestry.mjs";

const NAMES = ["OPENCODE_SESSION_ID", "OPENCODE_PID", "OPENCODE", "AGENT", "AI_AGENT", "OPENCODE_TERMINAL",
  "SPIKE_PLUGIN_INSTANCE", "SPIKE_CLIENT", "PWD"];
const label = process.argv[2] ?? "unlabelled";
const holdMs = Number(process.argv[3] ?? 0);
const self = describe(process.pid);
const record = {
  label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, pgrp: self.pgrp, sid: self.sid, startedAt: Date.now(),
  // Absent and empty are different facts.
  env: Object.fromEntries(NAMES.map((name) => [name, process.env[name] ?? null])),
  ancestry: ancestry(process.ppid),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
const chatter = process.argv.includes("SPIKE_CHATTY") ? setInterval(() => console.log(`${label} still running`), 60000) : null;
await new Promise((resolve) => setTimeout(resolve, holdMs));
clearInterval(chatter);
await post("end", { endedAt: Date.now() });
console.log(JSON.stringify({ label }));
