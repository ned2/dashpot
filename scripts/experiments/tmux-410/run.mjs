// Dropped SSH client experiment for Issue #410: how long tmux keeps counting
// a client attached, in the `#{session_attached}` the Unattended Pause's probe
// reads (ADR 0068), after the SSH connection carrying the only attached client
// ends in each way a person's connection does. A private, non-root sshd on a
// loopback port runs `tmux attach` as its forced command against a private tmux
// server, whose pane writes a line every 15 seconds as a dashboard's redraw
// does. The runner then kills the client's `ssh`, closes the pseudo-terminal
// `ssh` runs in, as a terminal emulator closing does, or drops the
// connection's packets in both directions without a FIN, as a laptop going to
// sleep or losing its network does, with and without sshd's
// ClientAliveInterval. A control drops a session whose pane and status line
// are silent, under the same ClientAliveInterval. It probes each session every
// second until it reports no client attached. The trace is metadata only; the
// verifier checks the claims against it.
//
// The drop scenarios run concurrently after the others, since each can take
// a quarter of an hour. Through `sudo -n nft` they share one nftables table,
// each adding two rules that match only its own connection's ports on the
// loopback interface and deleting them when it ends; the table is deleted
// when the run ends. Credentials must already be cached (`sudo -v`).
// SPIKE_SCENARIOS names a comma-separated subset to run.
//
// Usage: node run.mjs [expected tmux version]
import assert from "node:assert/strict";
import { spawn, spawnSync, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const expectedVersion = process.argv[2] ?? "tmux 3.6";
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-tmux-410-"));
console.log(`Isolated fixture: ${root}`);
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const user = new RegExp(`\\b${os.userInfo().username}\\b`, "g");
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(os.homedir(), "$HOME").replace(user, "$USER");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};

const table = "dashpot_410";
// The pane's workload: a line every 15 seconds, the local Refresh Period, so
// tmux has output for the client as it does while a dashboard redraws. The
// quiet control writes nothing, and its status line is off.
const workload = "while :; do date +%T; sleep 15; done";
const quiet = "exec sleep infinity";
const probeMs = 1_000;
const socketSampleMs = 15_000;
const scenarios = [
  { name: "kill-ssh", end: "kill", workload, capMs: 60_000 },
  { name: "close-terminal", end: "close", workload, capMs: 60_000 },
  // sshd sends a client-alive probe only after a whole interval with nothing
  // to read, so a pane that writes more often than the interval defers it.
  { name: "drop-client-alive-quiet", end: "drop", workload: quiet, status: false, clientAlive: { interval: 60, countMax: 3 }, capMs: 10 * 60_000 },
  { name: "drop-client-alive", end: "drop", workload, clientAlive: { interval: 60, countMax: 3 }, capMs: 40 * 60_000 },
  // ServerAliveInterval makes the client give up; the server never sees it.
  { name: "drop", end: "drop", workload, serverAlive: { interval: 5, countMax: 2 }, capMs: 40 * 60_000 },
];
const selected = process.env.SPIKE_SCENARIOS?.split(",") ?? scenarios.map((scenario) => scenario.name);
for (const name of selected) assert(scenarios.some((scenario) => scenario.name === name), `unknown scenario ${name}`);
const chosen = scenarios.filter((scenario) => selected.includes(scenario.name));

const read = (file) => readFileSync(file, "utf8").trim();
const sysctl = (name) => read(`/proc/sys/net/ipv4/${name}`);
const run = (file, args, options = {}) => execFileSync(file, args, { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"], ...options });
const sudo = (args, input) => run("sudo", ["-n", ...args], { input });
const tmuxVersion = run("tmux", ["-V"]).trim();
assert.equal(tmuxVersion, expectedVersion);
if (chosen.some((scenario) => scenario.end === "drop")) {
  try {
    sudo(["true"]);
  } catch {
    assert.fail("The drop scenarios need cached sudo credentials: run `sudo -v` first");
  }
  assert.throws(() => sudo(["nft", "list", "table", "inet", table]), undefined, `nftables table inet ${table} already exists`);
  // The drop scenarios outlast sudo's default 15-minute credential cache,
  // and their rules must still be deletable when they end.
  setInterval(() => {
    try {
      sudo(["-v"]);
    } catch (error) {
      console.error(`Could not refresh sudo credentials: ${error.message}`);
    }
  }, 60_000).unref();
}
trace("environment", {
  runner: createHash("sha256").update(readFileSync(fileURLToPath(import.meta.url))).digest("hex"),
  tmux: tmuxVersion,
  openssh: spawnSync("ssh", ["-V"], { encoding: "utf8" }).stderr.trim(),
  platform: process.platform,
  release: os.release(),
  arch: process.arch,
  node: process.version,
  sysctl: Object.fromEntries(["tcp_retries2", "tcp_keepalive_time", "tcp_keepalive_intvl", "tcp_keepalive_probes"].map((name) => [name, Number(sysctl(name))])),
  probeMs,
  scenarios: chosen,
});

run("ssh-keygen", ["-q", "-t", "ed25519", "-N", "", "-f", path.join(root, "host")]);
run("ssh-keygen", ["-q", "-t", "ed25519", "-N", "", "-f", path.join(root, "client")]);
writeFileSync(path.join(root, "authorized_keys"), read(path.join(root, "client.pub")) + "\n");

const freePort = () => new Promise((resolve, reject) => {
  const server = net.createServer();
  server.once("error", reject);
  server.listen(0, "127.0.0.1", () => {
    const { port } = server.address();
    server.close(() => resolve(port));
  });
});
const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

// What every scenario leaves running, for the exit handler to stop.
const running = new Set();
const stop = (cleanups) => {
  while (cleanups.length) {
    try {
      cleanups.pop()();
    } catch {
      // Already gone.
    }
  }
};
let nftAdded = false;
const addTable = () => {
  if (nftAdded) return;
  sudo(["nft", "-f", "-"], `table inet ${table} {\n  chain input {\n    type filter hook input priority filter - 10; policy accept;\n  }\n}\n`);
  nftAdded = true;
};
const removeTable = () => {
  if (!nftAdded) return;
  try {
    sudo(["nft", "delete", "table", "inet", table]);
    nftAdded = false;
  } catch (error) {
    console.error(`Could not delete nftables table inet ${table}: ${error.message}`);
  }
};
process.on("exit", () => {
  removeTable();
  for (const cleanups of running) stop(cleanups);
});
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) process.on(signal, () => process.exit(130));

async function measure(scenario) {
  const directory = path.join(root, scenario.name);
  mkdirSync(directory);
  const socket = path.join(directory, "tmux.sock");
  const tmux = (...args) => run("tmux", ["-S", socket, ...args]).trim();
  const port = await freePort();
  const cleanups = [];
  running.add(cleanups);
  tmux("-f", "/dev/null", "new-session", "-d", "-s", "fixture", "-x", "120", "-y", "40", scenario.workload);
  cleanups.push(() => tmux("kill-server"));
  if (scenario.status === false) tmux("set-option", "-g", "status", "off");
  const config = [
    `Port ${port}`,
    "ListenAddress 127.0.0.1",
    `HostKey ${path.join(root, "host")}`,
    `PidFile ${path.join(directory, "sshd.pid")}`,
    `AuthorizedKeysFile ${path.join(root, "authorized_keys")}`,
    "UsePAM no",
    "StrictModes no",
    "PasswordAuthentication no",
    "KbdInteractiveAuthentication no",
    "PrintMotd no",
    "PrintLastLog no",
    "LogLevel VERBOSE",
    "TCPKeepAlive yes",
    `ClientAliveInterval ${scenario.clientAlive?.interval ?? 0}`,
    `ClientAliveCountMax ${scenario.clientAlive?.countMax ?? 3}`,
    `ForceCommand exec tmux -S ${socket} attach-session -t fixture`,
  ];
  writeFileSync(path.join(directory, "sshd_config"), config.join("\n") + "\n");
  const start = Date.now();
  const since = () => Date.now() - start;
  const sshd = spawn("/usr/sbin/sshd", ["-D", "-e", "-f", path.join(directory, "sshd_config")], { stdio: ["ignore", "ignore", "pipe"] });
  cleanups.push(() => sshd.kill("SIGTERM"));
  const lines = (stream, source) => {
    let buffer = "";
    stream.setEncoding("utf8");
    stream.on("data", (chunk) => {
      buffer += chunk;
      const parts = buffer.split("\n");
      buffer = parts.pop();
      for (const line of parts) if (line.trim()) trace("log", { scenario: scenario.name, source, t: since(), line: line.trim() });
    });
  };
  lines(sshd.stderr, "sshd");
  for (let attempt = 0; attempt < 50 && !run("ss", ["-Htln", `( sport = :${port} )`]).trim(); attempt += 1) await delay(100);

  const sshArgs = [
    "-F", "/dev/null", "-tt", "-p", String(port), "-i", path.join(root, "client"),
    "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
    "-o", `UserKnownHostsFile=${path.join(root, "known_hosts")}`,
    ...(scenario.serverAlive ? ["-o", `ServerAliveInterval=${scenario.serverAlive.interval}`, "-o", `ServerAliveCountMax=${scenario.serverAlive.countMax}`] : []),
    "127.0.0.1",
  ];
  const env = { ...process.env, TERM: "xterm-256color" };
  // `script` holds the pseudo-terminal `ssh` runs in, as a terminal emulator
  // does, so killing it closes the terminal under `ssh`.
  const client = scenario.end === "close"
    ? spawn("script", ["-qfec", ["ssh", ...sshArgs].map((arg) => `'${arg}'`).join(" "), "/dev/null"], { env, stdio: ["pipe", "ignore", "pipe"] })
    : spawn("ssh", sshArgs, { env, stdio: ["pipe", "ignore", "pipe"] });
  cleanups.push(() => client.kill("SIGKILL"));
  lines(client.stderr, scenario.end === "close" ? "script" : "ssh");
  let clientExit = null;
  client.on("exit", (code, signal) => {
    clientExit = { t: since(), code, signal };
    trace("client.exit", { scenario: scenario.name, ...clientExit });
  });

  const attached = () => {
    try {
      return Number(tmux("display-message", "-p", "-t", "fixture", "#{session_attached}"));
    } catch (error) {
      return `error: ${error.stderr?.trim() || error.message}`;
    }
  };
  for (let attempt = 0; attempt < 100 && attached() !== 1; attempt += 1) await delay(100);
  assert.equal(attached(), 1, `${scenario.name}: the client never attached`);
  const tmuxClient = Number(tmux("list-clients", "-F", "#{client_pid}"));
  const connection = run("ss", ["-Htn", "state", "established", `( dport = :${port} )`]).trim().split(/\s+/);
  const clientPort = Number(connection.at(-2).split(":").at(-1));
  const sshPid = scenario.end === "close" ? Number(run("pgrep", ["-P", String(client.pid), "-x", "ssh"]).trim()) : client.pid;
  trace("attached", { scenario: scenario.name, t: since(), port, clientPort, tmuxClient, sshPid, clientPid: client.pid });
  // Let the pane write at least once with the client attached.
  await delay(16_000);

  const ended = since();
  if (scenario.end === "kill") {
    process.kill(sshPid, "SIGKILL");
  } else if (scenario.end === "close") {
    client.kill("SIGKILL");
  } else {
    addTable();
    const rules = [[clientPort, port], [port, clientPort]].map(([from, to]) => {
      const rule = `iifname "lo" tcp sport ${from} tcp dport ${to} drop`;
      const echoed = sudo(["nft", "--echo", "--handle", "add", "rule", "inet", table, "input", ...rule.split(" ")]);
      const handle = Number(echoed.match(/# handle (\d+)/)[1]);
      cleanups.push(() => sudo(["nft", "delete", "rule", "inet", table, "input", "handle", String(handle)]));
      return rule;
    });
    trace("nft", { scenario: scenario.name, table, rules });
  }
  trace("end", { scenario: scenario.name, t: ended, how: scenario.end });

  let last = null;
  let lastSocket = -Infinity;
  let detached = null;
  while (since() - ended <= scenario.capMs) {
    const sample = { attached: attached(), tmuxClient: alive(tmuxClient), ssh: alive(sshPid), sshd: sshd.exitCode === null };
    const changed = JSON.stringify(sample) !== JSON.stringify(last);
    if (changed) trace("sample", { scenario: scenario.name, t: since(), afterEnd: since() - ended, ...sample });
    last = sample;
    if (scenario.end === "drop" && since() - lastSocket >= socketSampleMs) {
      lastSocket = since();
      const state = run("ss", ["-Htnoi", "state", "all", `( sport = :${port} and dport = :${clientPort} )`]).trim().replace(/\s+/g, " ");
      trace("socket", { scenario: scenario.name, t: since(), afterEnd: since() - ended, state });
    }
    if (sample.attached === 0) {
      detached = since() - ended;
      break;
    }
    await delay(probeMs);
  }
  trace("detached", { scenario: scenario.name, afterEnd: detached, capMs: scenario.capMs, clientExit });
  console.log(`${scenario.name}: ${detached === null ? `still attached after ${scenario.capMs / 1000} s` : `detached ${(detached / 1000).toFixed(1)} s after the connection ended`}`);
  // Let sshd log how the session closed before the fixture is torn down.
  await delay(2_000);
  stop(cleanups);
  running.delete(cleanups);
  await delay(500);
}

for (const scenario of chosen.filter((item) => item.end !== "drop")) await measure(scenario);
await Promise.all(chosen.filter((item) => item.end === "drop").map(measure));
removeTable();
console.log(`Trace: ${tracePath}`);
