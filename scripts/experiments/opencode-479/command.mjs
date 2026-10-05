// The shell command the fixture model asks OpenCode to run. It reports the
// command's identity variables, location, ancestry and a few environment
// markers to the runner's sink when it starts, holds for the given time, and
// then either runs the given Dashpot command from that shell, as the
// Issue-work skill does (`-- work show`), or runs another program
// (`-- exec opencode run ...`); it reports the exit status, output and
// duration when it ends.
//
// Copied from opencode-421/command.mjs, with the environment markers added:
// whether a Lead's exported variables, a replaced environment's marker, a
// `gh` token and the fixture's cache directory reached this shell. The token
// is reported as present or absent only.
//
// Usage: node command.mjs <label> [holdMs] [-- dashpot arguments... | -- exec program arguments...]
import { spawnSync } from "node:child_process";
import { ancestry } from "./ancestry.mjs";

const NAMES = ["OPENCODE_SESSION_ID", "OPENCODE", "DASHPOT_OPENCODE_PID", "DASHPOT_OPENCODE_REFUSAL",
  "DASHPOT_AGENT_SESSION", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "LEAD_MARK", "PUT_MARK"];
const PRESENT = ["GH_TOKEN", "XDG_CACHE_HOME", "SPIKE_SINK", "XDG_STATE_HOME"];
const label = process.argv[2] ?? "unlabelled";
const split = process.argv.indexOf("--");
const rest = split >= 0 ? process.argv.slice(split + 1) : null;
const holdMs = Number((split >= 0 ? process.argv.slice(3, split) : process.argv.slice(3))[0] ?? 0);
const record = {
  label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, startedAt: Date.now(),
  // Absent and blanked are different facts: the plugin blanks inherited claims.
  env: Object.fromEntries(NAMES.map((name) => [name, process.env[name] ?? null])),
  present: Object.fromEntries(PRESENT.map((name) => [name, name in process.env])),
  path: process.env.PATH ?? null,
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm, outside }) => ({ pid, ppid, comm, outside })),
};
const post = (phase, extra = {}) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ ...record, ...extra, phase }), signal: AbortSignal.timeout(3000) }).catch(() => {});
await post("start");
await new Promise((resolve) => setTimeout(resolve, holdMs));
if (rest?.[0] === "exec") {
  const started = Date.now();
  const result = spawnSync(rest[1], rest.slice(2), { encoding: "utf8", timeout: 90000 });
  // Whole, not cut: the runner redacts the fixture's paths, and a cut path
  // would escape it.
  await post("end", { endedAt: Date.now(), exec: { args: rest.slice(1), status: result.status, signal: result.signal,
    ms: Date.now() - started, stdout: result.stdout, stderr: result.stderr } });
  process.stdout.write(result.stdout ?? "");
} else if (rest) {
  const result = spawnSync(process.env.SPIKE_DASHPOT, rest, { encoding: "utf8", timeout: 60000 });
  await post("end", { endedAt: Date.now(), dashpot: { args: rest, status: result.status, stdout: result.stdout, stderr: result.stderr } });
} else {
  await post("end", { endedAt: Date.now() });
}
console.log(JSON.stringify({ label }));
