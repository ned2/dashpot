// The shell command the fixture model asks Codex to run for Issue #681. It
// runs inside the session's sandbox, which has no network, so it reports by
// printing one `PROBE {...}` line that Codex returns to the fixture model as
// the call's output. It records where the command runs, which thread it
// belongs to, whether it may write in each fixture checkout, and whether the
// session's own commands can reach the app-server daemon's control socket.
// A connection that succeeds is closed at once: nothing is sent over it.
//
//   node probe.mjs <label> <gate path or -> <write target>...
import { accessSync, constants, existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const [label, gate, ...targets] = process.argv.slice(2);
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const before = process.cwd();
// A held command waits for the runner to open its gate, so the runner can act
// on the session while this command is still running.
if (gate && gate !== "-") {
  const end = Date.now() + 120000;
  while (!existsSync(gate) && Date.now() < end) await delay(100);
}
const attempt = (operation) => {
  try { operation(); return { ok: true }; } catch (error) { return { ok: false, code: error.code ?? String(error) }; }
};
// Each target is a file under a checkout's ignored `.dashpot/state/`; a write
// that succeeds is removed at once, so no checkout is left changed.
const writes = targets.map((target) => {
  const result = attempt(() => writeFileSync(target, "probe\n"));
  if (result.ok) rmSync(target, { force: true });
  return [target, result];
});
const controlSocket = path.join(process.env.CODEX_HOME ?? "", "app-server-control", "app-server-control.sock");
const sharedDirectory = `/tmp/codex-daemon-${os.userInfo().uid}`;
const connect = (socketPath) => new Promise((resolve) => {
  const socket = net.connect(socketPath);
  const finish = (result) => { socket.destroy(); resolve(result); };
  socket.setTimeout(1500, () => finish({ ok: false, code: "TIMEOUT" }));
  socket.once("connect", () => finish({ ok: true }));
  socket.once("error", (error) => finish({ ok: false, code: error.code }));
});
const status = readFileSync("/proc/self/status", "utf8");
console.log("PROBE " + JSON.stringify({
  label,
  cwdBefore: before,
  cwd: process.cwd(),
  thread: process.env.CODEX_THREAD_ID ?? null,
  seccomp: /^Seccomp:\s+(\d+)/m.exec(status)?.[1] ?? null,
  writes,
  controlSocket: { exists: existsSync(controlSocket), connect: await connect(controlSocket) },
  sharedDaemonDirectory: { read: attempt(() => accessSync(sharedDirectory, constants.R_OK | constants.X_OK)) },
}));
