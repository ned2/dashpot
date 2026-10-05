// The guard every `opencode api` call in the run goes through, from a Lead's
// or a Worker's shell or from the runner. `opencode api` finds the shared
// service through the registration under `$XDG_STATE_HOME`, and starts one if
// none is registered, so before it runs the guard checks that:
//
// - HOME, XDG_STATE_HOME and XDG_CONFIG_HOME are inside the fixture;
// - `opencode` on PATH is the fixture's copy of the pinned binary;
// - the registration exists, names the fixture's private port, and its pid is
//   a live process whose environment names the fixture's configuration.
//
// Any failed check refuses the call: nothing runs, and the refusal is
// reported. The guard reports the checks, the call's exit status, duration
// and output head to the runner's sink, and prints the call's output, so the
// fixture model can read the session or request id it names.
//
// Usage: node guard.mjs <label> -- <program> [arguments...]
import { spawnSync } from "node:child_process";
import { accessSync, constants, readFileSync } from "node:fs";
import path from "node:path";

const label = process.argv[2] ?? "unlabelled";
const split = process.argv.indexOf("--");
const [program, ...args] = split >= 0 ? process.argv.slice(split + 1) : [];
const root = process.env.SPIKE_ROOT;
const inside = (value) => Boolean(root && value && (value === root || value.startsWith(root + path.sep)));
const resolve = (name) => {
  for (const directory of (process.env.PATH ?? "").split(":")) {
    const candidate = path.join(directory, name);
    try { accessSync(candidate, constants.X_OK); return candidate; } catch {}
  }
  return null;
};
let registration = null;
try { registration = JSON.parse(readFileSync(path.join(process.env.XDG_STATE_HOME ?? "", "opencode", "service.json"), "utf8")); } catch {}
let port = null;
try { port = Number(new URL(registration?.url).port); } catch {}
let servicePid = Number(registration?.pid);
let serviceInFixture = false;
try { serviceInFixture = readFileSync(`/proc/${servicePid}/environ`, "utf8").includes(`XDG_CONFIG_HOME=${process.env.SPIKE_CONFIG_MARK}\0`); } catch {}
const checks = {
  homeInFixture: inside(process.env.HOME),
  stateInFixture: inside(process.env.XDG_STATE_HOME),
  configInFixture: inside(process.env.XDG_CONFIG_HOME) && process.env.XDG_CONFIG_HOME === process.env.SPIKE_CONFIG_MARK,
  binaryIsFixtureCopy: program === "opencode" && resolve("opencode") === process.env.SPIKE_OPENCODE,
  registered: Boolean(registration),
  registrationFields: registration ? Object.keys(registration).toSorted() : null,
  portIsFixtures: port !== null && port === Number(process.env.SPIKE_SERVICE_PORT),
  serviceInFixture,
  noOtherServer: !args.includes("--standalone") && !args.includes("--server"),
};
const ok = checks.homeInFixture && checks.stateInFixture && checks.configInFixture && checks.binaryIsFixtureCopy && checks.registered
  && checks.portIsFixtures && checks.serviceInFixture && checks.noOtherServer;
const report = (fields) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ label, phase: "end", guarded: true, cwd: process.cwd(), pid: process.pid, servicePid, checks, ok,
    sessionClaim: process.env.OPENCODE_SESSION_ID ?? null, serverPid: process.env.DASHPOT_OPENCODE_PID ?? null, ...fields }),
  signal: AbortSignal.timeout(3000) }).catch(() => {});
if (!ok) {
  await report({ refused: true });
  console.log(`GUARD REFUSED ${label}: ${JSON.stringify(checks)}`);
  process.exit(3);
}
const started = Date.now();
// A long wait or event stream sets its own limit, above the deadline it probes.
const result = spawnSync(resolve("opencode"), args, { encoding: "utf8", timeout: Number(process.env.SPIKE_GUARD_TIMEOUT ?? 60000), maxBuffer: 64 * 1024 * 1024 });
await report({ exec: { args, status: result.status, signal: result.signal, ms: Date.now() - started,
  stdout: (result.stdout ?? "").slice(0, 1500), stderr: (result.stderr ?? "").slice(-800) } });
process.stdout.write(result.stdout ?? "");
process.stderr.write(result.stderr ?? "");
process.exit(result.status ?? 1);
