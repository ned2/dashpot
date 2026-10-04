// A call a worker's shell makes on the OpenCode service's HTTP API, as any
// process of the user can: it reads the service registration the client
// reads, authenticates with its password, and reports to the runner's sink
// which registration fields it found (never their values), the response
// status, and the response's head.
//
// Usage: node api.mjs <label> <METHOD> <route> [json body]
import { readFileSync } from "node:fs";
import path from "node:path";

const [label, method, route, raw] = process.argv.slice(2);
const report = (fields) => fetch(process.env.SPIKE_SINK + "/command", { method: "POST",
  body: JSON.stringify({ label, phase: "end", cwd: process.cwd(), pid: process.pid, ...fields }), signal: AbortSignal.timeout(3000) }).catch(() => {});
let registration = null;
try { registration = JSON.parse(readFileSync(path.join(process.env.XDG_STATE_HOME ?? path.join(process.env.HOME, ".local", "state"), "opencode", "service.json"), "utf8")); } catch {}
const url = registration?.url ?? (registration?.port ? `http://${registration.hostname ?? "127.0.0.1"}:${registration.port}` : null);
const fields = registration ? Object.keys(registration).toSorted() : null;
if (!url || !registration?.password) {
  await report({ api: { method, route, registration: fields, status: null, error: "no usable registration" } });
} else {
  const started = Date.now();
  const response = await fetch(url.replace(/\/$/, "") + route, { method, body: raw,
    headers: { "content-type": "application/json", authorization: "Basic " + Buffer.from(`opencode:${registration.password}`).toString("base64") },
    signal: AbortSignal.timeout(30000) }).catch((error) => ({ status: null, text: async () => String(error) }));
  const text = await response.text();
  await report({ api: { method, route, registration: fields, status: response.status, ms: Date.now() - started, body: text.slice(0, 300) } });
}
console.log(JSON.stringify({ label }));
