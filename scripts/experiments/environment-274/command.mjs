// The probe a fixture model or a fixture shell runs. It reports the traced
// variables in its own environment, its working directory, its harness identity
// variables, and its ancestry with each fixture ancestor's markers, so the
// trace shows which process's environment the command inherited. The sink,
// the fixture's configuration directory and the runner's pid come as
// arguments rather than from the environment, which a harness may filter.
//
// Usage: node command.mjs <label> <sink url> <fixture XDG_CONFIG_HOME> <runner pid>
import { ancestry, TRACED } from "./ancestry.mjs";

const [label, sink, configHome, stop] = process.argv.slice(2);
const IDENTITY = ["CODEX_THREAD_ID", "OPENCODE_SESSION_ID"];
const record = {
  label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, at: Date.now(),
  env: Object.fromEntries([...TRACED, ...IDENTITY].map((name) => [name, process.env[name] ?? null])),
  ancestry: ancestry(process.ppid, configHome, Number(stop)),
};
await fetch(`${sink}/command`, { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(5000) }).catch(() => {});
console.log(`PROBED:${label}`);
