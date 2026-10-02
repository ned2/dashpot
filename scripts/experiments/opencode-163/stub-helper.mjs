// A stand-in for the Dashpot OpenCode helper: it forwards each request, with
// its own process facts, to the runner's receiver and prints the receiver's
// acknowledgment. It never writes Dashpot state.
import { execFileSync } from "node:child_process";

let raw = "";
for await (const chunk of process.stdin) raw += chunk;
const parent = execFileSync("ps", ["-o", "comm=,args=", "-p", String(process.ppid)], { encoding: "utf8" }).trim();
const response = await fetch(process.env.PROBE_SINK + "/helper", {
  method: "POST",
  body: JSON.stringify({ request: JSON.parse(raw), pid: process.pid, ppid: process.ppid, parent, startedAt: Date.now() }),
});
process.stdout.write((await response.text()) + "\n");
