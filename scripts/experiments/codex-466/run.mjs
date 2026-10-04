// Live background-terminal run for Issue #466: what becomes of a Codex
// command that `exec_command` leaves running as a background terminal when
// the turn that started it ends, when the person runs `/cd` to another
// Worktree or `/clear`, when a standalone terminal exits, when a terminal
// attached to the managed daemon exits and the daemon unloads the thread, and
// when a headless `codex exec` finishes, and whether Dashpot's `process`
// Cleanup blocker (ADR 0104) names the command in the Worktree it runs in
// after each. Drives a pinned Codex CLI against a loopback Responses API
// fixture with an isolated CODEX_HOME, whose daemon updater is off, and
// Dashpot's own Codex hook publisher, in a disposable Dashpot Project with two
// linked Worktrees. After each action the runner records the command's
// process, the session's stored hook record, and `dashpot worktree check
// --json` of both Worktrees, as a metadata-only trace.
//
//   node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [--strict]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.160.0";
const selected = process.env.SPIKE_SCENARIOS ? new Set(process.env.SPIKE_SCENARIOS.split(",")) : null;
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.join(checkout, ".venv", "bin");
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-466-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const worktreeA = path.join(root, "repository.worktrees", "a");
const worktreeB = path.join(root, "repository.worktrees", "b");
const gates = path.join(root, "gates");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const retained = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(home, "$HOME").replace(hostName, "<host>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};

// The pinned release runs through a fixture-local `codex` on PATH.
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
symlinkSync(binary, path.join(fixtureBin, "codex"));
// The hook events `dashpot integrate codex` subscribes, each routed through
// the metadata wrapper to Dashpot's real publisher.
const hookEvents = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks);
const env = {
  PATH: `${fixtureBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  SPIKE_PUBLISHER: publisher,
  SPIKE_GATES: gates,
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, gates, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project and its two linked Worktrees.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
writeFileSync(path.join(fixture, "issues", ".keep"), "");
const initialized = spawnSync(dashpotCommand, ["init", "--markdown", "issues"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.dashpot/state/\n");
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
for (const [name, worktree] of [["a", worktreeA], ["b", worktreeB]]) git("worktree", "add", "-b", name, worktree);

const listen = async (handler) => {
  const server = http.createServer(async (req, res) => {
    try { await handler(req, res); } catch (error) {
      trace("server.error", { path: req.url, error: String(error?.stack ?? error) });
      if (!res.headersSent) res.writeHead(500);
      res.end();
    }
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return { server, url: `http://127.0.0.1:${server.address().port}` };
};
const body = async (req) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
};
const sink = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  trace(url.pathname === "/hook" ? "hook" : "command", await body(req));
  res.end("{}");
});
const stripAnsi = (text) => text.replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "").replace(/\u001b[()][0-9A-Za-z]|\u001b[=>78]/g, "");
env.SPIKE_SINK = sink.url;

// The fixture model. The latest input item that is not a tool call and
// carries `SPIKE:<label>` selects the plan `plans[label]`, and each request
// of that thread under that label takes the plan's next step. The one step
// is an `exec_command` that yields after a second, which leaves the command
// running as a background terminal; then the model answers `DONE:<label>`.
const commandScript = path.join(here, "command.mjs");
const markerPattern = /SPIKE:([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const stepCounters = new Map();
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/responses")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "not_found", message: "fixture" } }));
    return;
  }
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const input = payload.input ?? [];
  let label = null;
  input.forEach((item) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)];
    if (found.length) label = found.at(-1)[1];
  });
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  // The terminal also sends each prompt to a side thread of its own, offered
  // no shell; it gets text only.
  const sideThread = !offered("exec_command");
  const counterKey = `${thread}:${label}`;
  const stepIndex = stepCounters.get(counterKey) ?? 0;
  stepCounters.set(counterKey, stepIndex + 1);
  const background = label && !sideThread && stepIndex === 0 && label.endsWith("-start");
  const scenarioPrefix = label?.replace(/-start$/, "");
  const tool = offered("exec_command");
  const item = background && tool ? { type: "function_call", call_id: `call_${label}_${records.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name: "exec_command",
    arguments: JSON.stringify({ cmd: `node ${commandScript} ${scenarioPrefix}-bg ${scenarioPrefix}-go`, login: false, yield_time_ms: 1000 }) } : null;
  const latestOutput = input.findLast((entry) => /_call_output$/.test(entry.type ?? ""));
  trace("model.request", { thread, label, step: stepIndex, sideThread, action: item ? "exec_command" : null,
    // Whether the latest tool output says the command is still running; its text stays out.
    lastOutputRunning: latestOutput ? /running|session/i.test(String(latestOutput.output ?? "")) : null });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 15 }] }]])),
}, null, 2));
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"
check_for_update_on_startup = false

[features]
hooks = true
plugins = false
apps = false

[analytics]
enabled = false

[model_providers.fixture]
name = "Fixture"
base_url = "${model.url}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0

${[fixture, worktreeA, worktreeB].map((dir) => `[projects."${dir}"]\ntrust_level = "trusted"\n`).join("\n")}`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run only lists its entries, by name, and never
// removes any.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

// Every process whose environment names the fixture's gates or CODEX_HOME.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || Number(name) === process.pid) continue;
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`) && !environ.includes(`SPIKE_GATES=${gates}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
// The managed daemon names itself in its pid file; its command line is the
// copy it installs under CODEX_HOME, so the pid file is the reliable record.
const daemonPidPath = path.join(env.CODEX_HOME, "app-server-daemon", "daemon.pid");
const daemonPid = () => { const pid = parseJson(existsSync(daemonPidPath) ? readFileSync(daemonPidPath, "utf8") : "")?.pid; return pid && existsSync(`/proc/${pid}`) ? pid : null; };
const hooks = () => records.filter((record) => record.kind === "hook");
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const settle = async (predicate, label, timeout) => {
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};
const mark = () => records.length;
const hookSince = (since, predicate) => hooks().find((record) => record.receipt > since && predicate(record));
const open = (gate) => { writeFileSync(path.join(gates, gate), ""); trace("gate", { gate }); };

const processState = (pid) => {
  let stat;
  try { stat = readFileSync(`/proc/${pid}/stat`, "utf8"); } catch { return { pid, alive: false }; }
  const close = stat.lastIndexOf(")");
  const fields = stat.slice(close + 2).split(" ");
  if (fields[0] === "Z") return { pid, alive: false, zombie: true };
  let cwd = null;
  try { cwd = retained(readlinkSync(`/proc/${pid}/cwd`)); } catch {}
  return { pid, alive: true, comm: stat.slice(stat.indexOf("(") + 1, close), ppid: Number(fields[1]), pgid: Number(fields[2]), sid: Number(fields[3]), cwd };
};
const check = (worktree) => {
  const ran = spawnSync(dashpotCommand, ["worktree", "check", worktree, "--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  const parsed = parseJson(ran.stdout);
  if (!parsed) return { status: ran.status, stderr: retained(ran.stderr ?? "").slice(-400) };
  return { status: ran.status, removable: parsed.removable, uncheckedProcesses: parsed.uncheckedProcesses,
    blockers: parsed.obstacles.map((obstacle) => ({ kind: obstacle.kind,
      session: obstacle.detail.match(/session ([0-9a-f-]{36})/)?.[1] ?? null,
      processes: obstacle.kind === "process" ? [...obstacle.detail.matchAll(/pid (\d+) \(([^)]*)\) at (\S+?)(?=; |\. Removing)/g)].map((match) => ({ pid: Number(match[1]), comm: match[2], cwd: retained(match[3]) })) : undefined,
      command: obstacle.kind === "process" ? obstacle.command : undefined })) };
};
// Every hook record Dashpot holds for a session, in each checkout's store.
const storedSession = (session) => [["main", fixture], ["a", worktreeA], ["b", worktreeB]].flatMap(([name, checkoutPath]) => {
  const directory = path.join(checkoutPath, ".dashpot", "state", "sessions");
  let names = [];
  try { names = readdirSync(directory).filter((file) => file.endsWith(".json")); } catch { return []; }
  return names.flatMap((file) => {
    const record = parseJson(readFileSync(path.join(directory, file), "utf8"));
    if (!record || record.sessionId !== session) return [];
    return [{ store: name, event: record.event, state: record.state, cwd: retained(record.cwd ?? ""), turnStartedAt: record.turnStartedAt ?? null }];
  });
});
const probe = (p, label, sessions) => {
  const started = command(`${p}-bg`, "start");
  return trace("probe", { scenario: p, label,
    command: started ? processState(started.pid) : null,
    shell: started ? processState(started.ppid) : null,
    commandEnded: Boolean(command(`${p}-bg`)),
    stored: Object.fromEntries(sessions.filter(Boolean).map((session) => [session, storedSession(session)])),
    checks: { a: check(worktreeA), b: check(worktreeB) } });
};

// An interactive terminal hosted by `script`. Its screen goes to a log in
// the fixture root; the trace keeps only a labelled tail of it.
const terminals = [];
const terminal = async (name, args, cwd = worktreeA) => {
  const child = spawn("script", ["-qfec", ["codex", ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  const logPath = path.join(root, `terminal-${name}.log`);
  let screen = "";
  const handle = { name, child, exited: null,
    type: async (text) => { trace("terminal.type", { name, text: retained(text) }); child.stdin.write(text); await delay(700); child.stdin.write("\r"); await delay(300); },
    key: (text) => child.stdin.write(text),
    screen: (label) => trace("screen", { name, label, tail: retained(screen.slice(-900)).replace(/\s+/g, " ") }) };
  const keep = (chunk) => { const text = stripAnsi(String(chunk)); appendFileSync(logPath, text); screen = (screen + text).slice(-20000); };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(handle);
  trace("terminal.start", { name, args: args.map(retained), scriptPid: child.pid, cwd: retained(cwd) });
  return handle;
};
const exitTerminal = async (handle) => {
  if (handle.exited) return;
  await handle.type("/exit");
  if (!(await settle(() => handle.exited, `${handle.name} exit`, 15000))) {
    handle.screen(`${handle.name}-exit`);
    handle.key("\u0003"); await delay(500); handle.key("\u0003");
    await settle(() => handle.exited, `${handle.name} interrupt exit`, 10000);
  }
};
// The terminal's first prompt starts the background command; its turn ends.
const startBackground = async (p, args, cwd) => {
  const since = mark();
  const tui = await terminal(p, [...args, "-C", worktreeA, `SPIKE:${p}-start`], cwd);
  await waitFor(() => command(`${p}-bg`, "start"), `${p}-bg start`, 90000);
  await settle(() => hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id), `${p}-start Stop`, 30000);
  await delay(1500);
  const session = hookSince(since, (record) => record.event === "SessionStart")?.payload.session_id ?? null;
  return { tui, session, since };
};
const release = async (p) => {
  const since = mark();
  open(`${p}-go`);
  await settle(() => command(`${p}-bg`), `${p}-bg end`, 20000);
  // Whether the command's end starts a turn of its own.
  await settle(() => hookSince(since, (record) => record.event === "UserPromptSubmit" || record.event === "Stop"), `${p} turn after the end`, 10000);
};
const standalone = ["--disable", "daemon_auto_start"];

const scenarios = [];
const scenario = (name, run) => scenarios.push({ name, run });

scenario("turn-end", async () => {
  const p = "te";
  const { tui, session } = await startBackground(p, standalone);
  tui.screen(`${p}-after-turn`);
  probe(p, "after-turn", [session]);
  await release(p);
  probe(p, "after-release", [session]);
  await exitTerminal(tui);
});

// `/cd` to Worktree `b` while the background terminal runs in `a`, then a
// prompt whose hook shows where the session's turn runs. After the command
// ends, the same `/cd` and a second prompt.
const promptTurn = async (tui, label) => {
  const since = mark();
  await tui.type(`SPIKE:${label}`);
  const submittedAt = () => hookSince(since, (record) => record.event === "UserPromptSubmit" && record.labels?.includes(label));
  await settle(() => submittedAt() && hookSince(submittedAt().receipt, (record) => record.event === "Stop"), `${label} Stop`, 30000);
  const submitted = submittedAt();
  return trace("prompt.turn", { label, session: submitted?.payload.session_id ?? null, cwd: submitted?.payload.cwd ?? null, submitted: Boolean(submitted) });
};
scenario("cd", async () => {
  const p = "cd";
  const { tui, session } = await startBackground(p, standalone);
  await tui.type(`/cd ${worktreeB}`);
  await delay(3000);
  tui.screen(`${p}-after-cd`);
  await promptTurn(tui, `${p}-after-cd`);
  probe(p, "after-cd", [session]);
  await release(p);
  await tui.type(`/cd ${worktreeB}`);
  await delay(3000);
  await promptTurn(tui, `${p}-after-release-cd`);
  probe(p, "after-release-cd", [session]);
  await exitTerminal(tui);
});

// `/clear` while the background terminal runs, then a prompt: the cleared
// conversation's first turn names the session that follows.
scenario("clear", async () => {
  const p = "cl";
  const { tui, session, since } = await startBackground(p, standalone);
  const clearAt = mark();
  await tui.type("/clear");
  await delay(3000);
  await promptTurn(tui, `${p}-after-clear`);
  await settle(() => hookSince(clearAt, (record) => record.event === "SessionStart"), `${p} SessionStart`, 15000);
  const cleared = hookSince(clearAt, (record) => record.event === "SessionStart")?.payload.session_id ?? null;
  probe(p, "after-clear", [session, cleared]);
  await release(p);
  probe(p, "after-release", [session, cleared]);
  await exitTerminal(tui);
  trace("clear.outcome", { since, session, cleared });
});

scenario("exit", async () => {
  const p = "ex";
  const { tui, session } = await startBackground(p, standalone);
  await exitTerminal(tui);
  await delay(2000);
  tui.screen(`${p}-after-exit`);
  probe(p, "after-exit", [session]);
  await release(p);
  probe(p, "after-release", [session]);
});

// A terminal attached to the managed daemon exits; the daemon keeps the
// thread loaded, then unloads it.
scenario("daemon", async () => {
  const p = "dm";
  const started = spawnSync("codex", ["app-server", "daemon", "start"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.start", { status: started.status });
  await waitFor(() => existsSync(socketPath) && daemonPid(), "daemon control socket", 30000);
  const pid = daemonPid();
  trace("daemon.ready", { pid, process: processState(pid) });
  const { tui, session } = await startBackground(p, ["--remote", `unix://${socketPath}`]);
  probe(p, "after-turn", [session]);
  const exitAt = mark();
  await exitTerminal(tui);
  await delay(2000);
  probe(p, "after-client-exit", [session]);
  await settle(() => hookSince(exitAt, (record) => record.event === "SessionEnd" && record.payload.session_id === session), `${p} unload SessionEnd`, 120000);
  await delay(2000);
  probe(p, "after-unload", [session]);
  await release(p);
  const stopped = spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.stop", { status: stopped.status });
  await settle(() => !existsSync(`/proc/${pid}`), "daemon gone", 20000);
});

// A headless `codex exec` whose only turn starts the command.
scenario("exec", async () => {
  const p = "hx";
  const since = mark();
  const child = spawn("codex", ["exec", "-C", worktreeA, `SPIKE:${p}-start`], { cwd: worktreeA, env, stdio: ["ignore", "pipe", "pipe"] });
  let exited = null;
  child.stdout.on("data", () => {});
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { exited = { status, signal }; trace("client.exit", { name: p, status, signal }); });
  trace("client.spawn", { name: p, mode: "exec", pid: child.pid, cwd: retained(worktreeA) });
  await waitFor(() => command(`${p}-bg`, "start"), `${p}-bg start`, 90000);
  await settle(() => exited, `${p} exit while the command runs`, 30000);
  await delay(2000);
  const session = hookSince(since, (record) => record.event === "SessionStart")?.payload.session_id ?? null;
  probe(p, "after-turn", [session]);
  await release(p);
  await settle(() => exited, `${p} exit`, 30000);
  if (!exited) { child.kill("SIGTERM"); await settle(() => exited, `${p} exit after SIGTERM`, 10000); }
  probe(p, "after-release", [session]);
});

const scripts = ["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"];
const modules = ["sessions/hook_publish.py", "sessions/hook_records.py", "sessions/hook_scan.py", "sessions/working_directories.py", "repository/cleanup/obstacles.py"].map((file) => `src/dashpot/${file}`);
const digests = () => Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
  .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")]));
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: retained(execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim()),
    dashpot: { head: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      dirtySource: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean) },
    hookEvents, fixture, worktrees: { a: worktreeA, b: worktreeB }, scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name)),
    sharedDaemonDirBefore: sharedBefore.length, sourceSHA256: digests() });

  // Setup: trust the fixture hooks through the ledger on a loopback server.
  const probePort = net.createServer();
  probePort.listen(0, "127.0.0.1");
  await once(probePort, "listening");
  const port = probePort.address().port;
  probePort.close();
  const trustServer = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let trustBanner = "";
  trustServer.stderr.on("data", (chunk) => { trustBanner += chunk; });
  trustServer.stdout.on("data", () => {});
  await waitFor(() => trustBanner.includes("listening on"), "trust server listening", 20000);
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(socket, "open");
  let nextId = 0;
  const pending = new Map();
  socket.addEventListener("message", (message) => { const parsed = parseJson(message.data); if (parsed?.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); } });
  const call = (method, params = {}) => new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); });
  await call("initialize", { clientInfo: { name: "dashpot-466-trust", version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  const listed = await call("hooks/list", { cwds: [fixture] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  socket.close();
  trustServer.kill("SIGTERM");
  await once(trustServer, "exit");
  await delay(500);

  for (const { name, run } of scenarios) {
    if (selected && !selected.has(name)) continue;
    trace("scenario", { name });
    try { await run(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 600) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
    for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
    await delay(500);
    for (const entry of fixtureProcesses()) { trace("scenario.kill", { scenario: name, pid: entry.pid, comm: entry.comm }); try { process.kill(entry.pid, "SIGKILL"); } catch {} }
    await delay(1000);
  }
  trace("sources.after", { sourceSHA256: digests() });
  console.log(`Scenarios completed: ${root}`);
} catch (error) {
  trace("runner.error", { error: retained(String(error?.stack ?? error)).slice(0, 2000) });
  throw error;
} finally {
  for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
  if (daemonPid()) spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, timeout: 60000 });
  await delay(1000);
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid) });
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  writeFileSync(path.join(root, "done"), "");
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
