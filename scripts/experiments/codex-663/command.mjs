// The shell command the fixture model asks Codex to run, inside the session's
// sandbox. It reports the shell's directory and identity claims, optionally
// runs one `dashpot work` command and keeps its outcome, tries to write each
// target file, and tries to connect to the fixture model's loopback port.
// It prints one `PROBE <json>` line, which reaches the runner as the tool
// output the model's next request carries: the sandbox may refuse the
// network, so the command never posts anything itself.
//
//   node command.mjs <label> <dashpot> <work> <port> [write target ...]
// <work> is `-`, `start-<issue>`, `show`, or `relocate:<path>`.
import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import net from "node:net";

const [label, dashpot, work, port, ...targets] = process.argv.slice(2);
const report = { label, cwd: process.cwd(), thread: process.env.CODEX_THREAD_ID ?? null, session: process.env.CODEX_SESSION_ID ?? null };
if (work && work !== "-") {
  const args = work.startsWith("start-") ? ["work", "start", work.slice("start-".length)]
    : work.startsWith("relocate:") ? ["work", "relocate", work.slice("relocate:".length)] : ["work", work];
  const ran = spawnSync(dashpot, args, { encoding: "utf8", timeout: 60000 });
  // Dashpot's own text about the fixture's Issues and Worktrees.
  report.work = { args, status: ran.status, signal: ran.signal, stdout: (ran.stdout ?? "").slice(0, 1500), stderr: (ran.stderr ?? "").slice(0, 800),
    error: ran.error ? String(ran.error) : null };
}
report.writes = targets.map((target) => {
  try { writeFileSync(target, label); return [target, { ok: true }]; } catch (error) { return [target, { ok: false, code: error.code ?? String(error) }]; }
});
report.network = await new Promise((resolve) => {
  const socket = net.connect(Number(port), "127.0.0.1");
  const timer = setTimeout(() => { socket.destroy(); resolve({ ok: false, code: "timeout" }); }, 3000);
  socket.on("connect", () => { clearTimeout(timer); socket.destroy(); resolve({ ok: true }); });
  socket.on("error", (error) => { clearTimeout(timer); resolve({ ok: false, code: error.code ?? String(error) }); });
});
console.log(`PROBE ${JSON.stringify(report)}`);
