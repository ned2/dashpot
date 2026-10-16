// Probe disposable filesystem and loopback network boundaries for Issue #665.
// The caller supplies only fixture paths; reports retain outcomes, never bytes
// read from a denied file. A successful read is a failed boundary assertion.
import { readFileSync, writeFileSync } from "node:fs";
import net from "node:net";

const [label, writable, denied, port, later] = process.argv.slice(2);
const attempt = (operation) => {
  try { operation(); return { ok: true }; }
  catch (error) { return { ok: false, code: error.code }; }
};
const network = await new Promise((resolve) => {
  const socket = net.connect({ host: "127.0.0.1", port: Number(port) });
  const finish = (result) => { socket.destroy(); resolve(result); };
  socket.setTimeout(1500, () => finish({ ok: false, code: "TIMEOUT" }));
  socket.once("connect", () => finish({ ok: true }));
  socket.once("error", (error) => finish({ ok: false, code: error.code }));
});
console.log("PROBE " + JSON.stringify({ label,
  noNewPrivs: /^NoNewPrivs:\s+(\d+)/m.exec(readFileSync("/proc/self/status", "utf8"))?.[1],
  seccomp: /^Seccomp:\s+(\d+)/m.exec(readFileSync("/proc/self/status", "utf8"))?.[1],
  write: attempt(() => writeFileSync(writable, "fixture\n")),
  deniedRead: attempt(() => readFileSync(denied)), network,
  laterWrite: later ? attempt(() => writeFileSync(later, "fixture\n")) : null }));
