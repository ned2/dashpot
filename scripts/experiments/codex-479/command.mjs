// The shell command the fixture model asks Codex to run, in a Lead's or a
// Worker's shell. It reports the shell's identity claims, location, process
// group and ancestry to the runner's sink, then, as its spec asks, runs one
// `dashpot work` command, holds until the runner opens a gate, queues a
// message to a thread with `codex queue`, and probes what the shell's sandbox
// allows. A shell whose sandbox refuses the loopback sink writes each report
// to a file in TMPDIR instead, or, where the sandbox leaves TMPDIR read-only,
// in its working directory, and the runner reads it back.
//   node command.mjs <base64url JSON spec>
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { ancestry } from "./ancestry.mjs";

const spec = JSON.parse(Buffer.from(process.argv[2] ?? "e30", "base64url").toString("utf8"));
const { label = "unlabelled", gate = null, gateMs = 25000, work = null, queue = null, probe = false } = spec;
const stat = readFileSync("/proc/self/stat", "utf8");
const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
const stripAnsi = (text) => String(text ?? "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "");
const record = {
  kind: "command", label, cwd: process.cwd(), pid: process.pid, ppid: process.ppid, pgid: Number(fields[2]), sid: Number(fields[3]),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX") || key.startsWith("DASHPOT"))),
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm, cmdline, cwd }) => ({ pid, ppid, comm, cmdline: cmdline.slice(0, 160), cwd })),
};
const results = {};
const post = async (phase, extra = {}) => {
  const body = JSON.stringify({ ...record, ...extra, phase, at: Date.now() });
  try {
    const response = await fetch(process.env.SPIKE_SINK + "/command", { method: "POST", body, signal: AbortSignal.timeout(3000) });
    if (!response.ok) throw new Error(`status ${response.status}`);
  } catch (error) {
    // The sandbox may refuse the loopback sink: keep the report in a file.
    const kept = (dir) => {
      mkdirSync(dir, { recursive: true });
      writeFileSync(path.join(dir, `${label}.${phase}.${process.pid}.json`), JSON.stringify({ ...JSON.parse(body), postError: String(error?.cause?.code ?? error?.code ?? error).slice(0, 80), keptIn: dir === process.env.SPIKE_RECORDS ? "tmpdir" : "cwd" }));
    };
    try { kept(process.env.SPIKE_RECORDS); } catch { try { kept(path.join(process.cwd(), ".spike-records")); } catch {} }
  }
};
await post("start");
if (work) {
  const args = ["work", ...work.split(" ")];
  const startedAt = Date.now();
  const ran = spawnSync(process.env.SPIKE_DASHPOT, args, { encoding: "utf8", timeout: 30000 });
  results.work = { args, status: ran.status, signal: ran.signal, ms: Date.now() - startedAt, stdout: (ran.stdout ?? "").slice(0, 1500), stderr: (ran.stderr ?? "").slice(0, 800) };
  await post("work", { work: results.work });
}
if (gate) {
  const file = path.join(process.env.SPIKE_GATES, gate);
  const startedAt = Date.now();
  while (!existsSync(file) && Date.now() < startedAt + gateMs) await new Promise((resolve) => setTimeout(resolve, 100));
  results.gate = { gate, opened: existsSync(file), heldMs: Date.now() - startedAt };
}
if (queue) {
  const startedAt = Date.now();
  const ran = spawnSync("codex", ["queue", "--thread", queue.thread, "--message", queue.message], { encoding: "utf8", timeout: 30000 });
  results.queue = { thread: queue.thread, message: queue.message, status: ran.status, signal: ran.signal, error: ran.error ? `${ran.error.code ?? ran.error} ${ran.error.syscall ?? ""}`.trim() : null,
    startedAt, endedAt: Date.now(), stdout: stripAnsi(ran.stdout).slice(-400), stderr: stripAnsi(ran.stderr).split("\n").filter((line) => line && !/^\s*$/.test(line)).slice(-6).join("\n").slice(-600) };
  await post("queue", { queue: results.queue });
}
if (probe) {
  // What the shell may reach: a write outside its workspace, the loopback
  // TCP sink, and the fixture daemon's Unix control socket.
  const outside = { };
  try { writeFileSync(path.join(process.env.SPIKE_OUTSIDE, `${label}.probe`), "x"); outside.write = "ok"; } catch (error) { outside.write = String(error.code ?? error); }
  const connect = (options) => new Promise((resolve) => {
    const socket = net.connect(options);
    const done = (result) => { socket.destroy(); resolve(result); };
    socket.once("connect", () => done("ok"));
    socket.once("error", (error) => done(String(error.code ?? error)));
    setTimeout(() => done("timeout"), 3000);
  });
  const sink = new URL(process.env.SPIKE_SINK);
  outside.tcp = await connect({ host: sink.hostname, port: Number(sink.port) });
  outside.daemonSocket = await connect({ path: process.env.SPIKE_DAEMON_SOCKET });
  // A Unix socket path that does not exist: ENOENT when the sandbox allows
  // Unix sockets at all, so that a refused daemon socket is the mask's doing.
  outside.unixMissing = await connect({ path: path.join(process.cwd(), ".no-such-socket") });
  try { statSync(process.env.SPIKE_DAEMON_SOCKET); outside.daemonSocketStat = "ok"; } catch (error) { outside.daemonSocketStat = String(error.code ?? error); }
  const shared = `/tmp/codex-daemon-${process.getuid()}`;
  try { outside.sharedDaemonDir = `entries:${readdirSync(shared).length}`; } catch (error) { outside.sharedDaemonDir = String(error.code ?? error); }
  try { writeFileSync(path.join(process.env.CODEX_HOME, `.probe-${label}`), "x"); outside.codexHomeWrite = "ok"; } catch (error) { outside.codexHomeWrite = String(error.code ?? error); }
  results.probe = outside;
}
await post("end", results);
console.log(JSON.stringify({ label, pid: record.pid, thread: record.env.CODEX_THREAD_ID ?? null }));
