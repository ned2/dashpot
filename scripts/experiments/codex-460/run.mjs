// Standalone-resume run for Issue #460: drives a pinned Codex CLI against a
// loopback Responses API fixture with an isolated CODEX_HOME, whose daemon
// updater is off, in a disposable Dashpot Project with one linked Worktree.
// In each scenario the managed daemon hosts a lead that has spawned a
// multi-agent v2 worker running long commands; while the worker works, a
// second terminal resumes the lead, either plainly, which attaches to the
// daemon, or with `--no-daemon`, which would be its own Host Process beside
// the daemon. The terminal is given a minute for a turn, stays open until the
// worker stops, and exits. A control then resumes a lead with `--no-daemon`
// after the daemon has stopped. After each step the run records Dashpot's
// stored hook record and what `dashpot worktree check` says of the linked
// Worktree. Every hook goes through a metadata wrapper to a Dashpot publisher
// built from a named source and installed outside every Worktree; the
// scenario runs once per publisher, so one trace holds the base's behaviour
// and the change's.
//
//   SPIKE_PUBLISHERS=base=<git revision>[,fix=worktree] node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
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
import { connectUnixWebSocket } from "./uds-websocket.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.160.0";
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
// Each publisher is `name=<git revision>` or `name=worktree`.
const publisherSpecs = (process.env.SPIKE_PUBLISHERS ?? "base=HEAD").split(",").map((spec) => {
  const [name, source] = spec.split("=");
  assert(/^[a-z]+$/.test(name) && source, `publisher spec ${spec}`);
  return { name, source };
});
const uv = execFileSync("sh", ["-c", "command -v uv"], { encoding: "utf8" }).trim();

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-460-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const treeA = path.join(root, "repository.worktrees", "a");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name, the checkout and the fixture's
// temporary root never enter the trace; a hook's or shell's ancestry keeps
// the processes up to the runner's own child.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~").replace(hostName, "<host>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 5) } : record;
  appendFileSync(tracePath, retained(JSON.stringify(kept)) + "\n");
  return record;
};
const sha256 = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;

// Each publisher is built into a wheel and installed in its own environment
// outside every Worktree, so an edit to the checkout during the run changes
// nothing the run executes.
const exercised = ["hook.py", "sessions/hook_records.py", "sessions/hook_publish.py", "sessions/hook_scan.py", "sessions/harnesses.py",
  "sessions/processes.py", "sessions/agent_runs.py", "repository/cleanup/obstacles.py"];
const publishers = publisherSpecs.map(({ name, source }) => {
  const build = path.join(root, `build-${name}`);
  let revision = null;
  let buildSource = checkout;
  let dirty = [];
  if (source === "worktree") {
    revision = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
    dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean);
  } else {
    revision = execFileSync("git", ["-C", checkout, "rev-parse", source], { encoding: "utf8" }).trim();
    buildSource = path.join(build, "source");
    mkdirSync(buildSource, { recursive: true });
    execFileSync("sh", ["-c", 'git -C "$1" archive "$2" | tar -x -C "$3"', "sh", checkout, revision, buildSource], { stdio: "pipe" });
  }
  const dist = path.join(build, "dist");
  execFileSync(uv, ["build", "-q", "--wheel", "-o", dist, buildSource], { stdio: "pipe" });
  const [wheel] = readdirSync(dist).filter((file) => file.endsWith(".whl"));
  const venv = path.join(build, "venv");
  execFileSync(uv, ["venv", "-q", "--python", path.join(checkout, ".venv", "bin", "python"), venv], { stdio: "pipe" });
  execFileSync(uv, ["pip", "install", "-q", "--offline", "--python", path.join(venv, "bin", "python"), path.join(dist, wheel)], { stdio: "pipe" });
  const installed = execFileSync(path.join(venv, "bin", "python"), ["-c", "import dashpot, os; print(os.path.dirname(dashpot.__file__))"], { encoding: "utf8" }).trim();
  const digests = () => Object.fromEntries(exercised.map((file) => [file, sha256(path.join(installed, file))]));
  const built = digests();
  // The installed copies are the source's.
  for (const file of exercised) assert.equal(built[file], sha256(path.join(buildSource, "src", "dashpot", file)), `${name}: installed ${file} is its source's`);
  return { name, source, revision, dirty, dashpot: path.join(venv, "bin", "dashpot"), hook: path.join(venv, "bin", "dashpot-codex-hook"), digests, built };
});

// The pinned release runs through a fixture-local `codex` on PATH.
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
symlinkSync(binary, path.join(fixtureBin, "codex"));
const hookEvents = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks);
const env = {
  PATH: `${fixtureBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  // Dashpot's machine-local state, like Codex's, stays inside the fixture.
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  SPIKE_ROOT: root,
  SPIKE_SUBSCRIBED: hookEvents.join(","),
  SPIKE_SESSIONS_DIR: path.join(fixture, ".dashpot", "state", "sessions"),
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);
let current = publishers[0];
const usePublisher = (publisher) => {
  current = publisher;
  writeFileSync(path.join(root, "publisher"), `${publisher.name}\t${publisher.hook}\n`);
};
usePublisher(publishers[0]);

// The disposable Dashpot Project: one Local Issue Markdown Issue, and one
// linked Worktree that Cleanup is asked about.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
const metadata = { id: "I_fixture_1", number: 1, reference: "fixture-1", state: "open", stateReason: null, labels: [], assignees: [], author: null,
  relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
  createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
writeFileSync(path.join(fixture, "issues", "1.md"), `---\n${JSON.stringify(metadata, null, 2)}\n---\n# Fixture Issue 1\n\nDisposable.\n`);
const dashpot = (args, cwd = fixture) => {
  const ran = spawnSync(current.dashpot, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "" };
};
const initialized = dashpot(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "a", treeA);

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
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
env.SPIKE_SINK = sink.url;

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` selects the plan `plans[label]`,
// and each request of that thread under that label takes the plan's next
// step. Each step becomes one tool call; when the plan runs out, the model
// answers `DONE:<label>`.
const commandScript = path.join(here, "command.mjs");
const exec = (hold) => ({ exec: { hold } });
const plans = {};
// How the second terminal resumes the lead: plainly, which attaches to the
// running daemon, or with `--no-daemon`, its own Host Process.
const variants = [
  { tag: "a", name: "attached", args: (lead, label) => ["resume", "-m", "fixture-v2", "-C", fixture, lead, `SPIKE:${label}`] },
  { tag: "n", name: "no-daemon", args: (lead, label) => ["--no-daemon", "resume", "-m", "fixture-v2", "-C", fixture, lead, `SPIKE:${label}`] },
];
publishers.forEach((_publisher, index) => {
  for (const variant of variants) {
    // Lead R spawns worker W, whose six commands hold 15 s each.
    plans[`r${index}${variant.tag}-spawn`] = [{ spawn: [`worker_${index}${variant.tag}`, `w${index}${variant.tag}`] }];
    plans[`w${index}${variant.tag}`] = Array.from({ length: 6 }, () => exec(15000));
    plans[`r${index}${variant.tag}-resumed`] = [];
  }
});
// The control resumes a lead after the daemon has stopped.
plans["control-resumed"] = [];
const markerPattern = /(SPIKE|DONE|SUMMARY):([a-z0-9_-]+)/g;
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
    const found = [...JSON.stringify(item).matchAll(markerPattern)].filter((match) => match[1] === "SPIKE");
    if (found.length) label = found.at(-1)[2];
  });
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const counterKey = `${thread}:${label}`;
  const stepIndex = stepCounters.get(counterKey) ?? 0;
  stepCounters.set(counterKey, stepIndex + 1);
  // The terminal also sends each prompt to a side thread of its own, offered
  // no shell and publishing no hooks; it gets text only, so it spawns nothing.
  const sideThread = !offered("exec_command");
  const plan = label && !sideThread ? plans[label] ?? [] : [];
  const step = plan[stepIndex] ?? null;
  const call = (name, args) => {
    const tool = offered(name);
    return tool && { type: "function_call", call_id: `call_${label}_${stepIndex}_${records.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.exec) {
    action = "exec_command";
    item = call("exec_command", { cmd: `node ${commandScript} ${label}.${stepIndex} ${step.exec.hold}`, login: false, yield_time_ms: 120000 });
  } else if (step?.spawn) {
    const [taskName, child] = step.spawn;
    action = "spawn_agent";
    item = call("spawn_agent", { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" });
  }
  trace("model.request", { thread, label, step: stepIndex, sideThread, action, missing: Boolean(step && !item), v2: Boolean(offered("list_agents")) });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  const text = label ? `DONE:${label}` : "Fixture complete.";
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 15 }] }]])),
}, null, 2));

// The fixture catalog names `fixture-v2`, a copy of a bundled entry without
// a tool set or code mode, declaring multi-agent v2, as in the #420 run.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));

const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-v2"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"
check_for_update_on_startup = false

[features]
hooks = true
multi_agent = true
# The curated plugin marketplace sync clones a GitHub repository at startup.
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

[projects."${fixture}"]
trust_level = "trusted"

[projects."${treeA}"]
trust_level = "trusted"
`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const daemonSettings = () => {
  try { return JSON.parse(readFileSync(daemonSettingsPath, "utf8")); } catch (error) { return { unreadable: String(error) }; }
};
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run only lists its entries, by name, and never
// removes any.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

// Every process whose environment names the fixture CODEX_HOME.
const codexProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let entry;
    try { entry = describe(Number(name)); } catch { continue; }
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`)) continue;
    if (entry.pid === process.pid) continue;
    found.push(entry);
  }
  return found;
};
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.replaceAll(root, "<root>").slice(0, 240)];
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const daemons = () => codexProcesses().filter(isDaemon);
const isSettler = (entry) => / -m dashpot\.hook settle /.test(entry.cmdline);
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
// What each terminal-hosted Codex process is doing: its scheduler state, the
// kernel function it waits in, and the files it holds open inside the
// fixture, by fixture-relative path.
const standaloneState = (label) => trace("standalone.state", { label, processes: codexProcesses().filter((entry) => entry.comm.startsWith("codex") && !isDaemon(entry)).map((entry) => {
  const read = (file) => { try { return readFileSync(`/proc/${entry.pid}/${file}`, "utf8").trim(); } catch { return null; } };
  let open = [];
  try { open = [...new Set(readdirSync(`/proc/${entry.pid}/fd`).map((fd) => { try { return readlinkSync(`/proc/${entry.pid}/fd/${fd}`); } catch { return null; } })
    .filter((target) => target?.startsWith(root)).map((target) => target.replace(root, "$ROOT")))].sort(); } catch {}
  return { pid: entry.pid, ppid: entry.ppid, state: read("status")?.match(/^State:\s*(.*)$/m)?.[1] ?? null, wchan: read("wchan"), threads: Number(read("status")?.match(/^Threads:\s*(\d+)/m)?.[1] ?? 0), open };
}) });
const processes = (label) => trace("processes", { label, processes: codexProcesses().map(brief), daemons: daemons().map((entry) => entry.pid), socketExists: existsSync(socketPath),
  daemonSettings: daemonSettings() });
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const settlersDone = async (label) => {
  await delay(500);
  await quietly(waitFor(() => !codexProcesses().some(isSettler), `${label}: settlers exit`, 15000));
};
const hookSince = (since, predicate) => hooks().find((record) => record.receipt > since && predicate(record));
const stopped = (agent) => hooks().some((record) => record.event === "SubagentStop" && record.payload.agent_id === agent);
const mark = () => records.length;
// The Codex process above a hook: the Host Process that ran it.
const hostOf = (record) => record.ancestry.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const threadOf = (label) => command(label)?.env.CODEX_THREAD_ID ?? null;

// Dashpot's stored hook record for a session, read from the fixture's
// project store; Dashpot keys a Codex record by its native session id, or by
// the scoped key when another harness claims that id.
const storedPath = (sessionId) => [sessionId, `codex-session-${createHash("sha256").update(sessionId).digest("hex")}`]
  .map((key) => path.join(env.SPIKE_SESSIONS_DIR, `${key}.json`)).find((file) => existsSync(file)) ?? path.join(env.SPIKE_SESSIONS_DIR, `${sessionId}.json`);
const stored = (label, sessionId) => {
  const record = parseJson(existsSync(storedPath(sessionId)) ? readFileSync(storedPath(sessionId), "utf8") : "null");
  return trace("stored", { label, publisher: current.name, session: sessionId, record: record && { event: record.event ?? null, source: record.source ?? null, state: record.state ?? null,
    liveSubagents: record.liveSubagents ?? null, subagentProcesses: record.subagentProcesses ?? null,
    sessionProcess: record.sessionProcess ? { pid: record.sessionProcess.pid, startedAt: record.sessionProcess.startedAt } : null } });
};
// What Cleanup says about the linked Worktree, through the scenario's own
// publisher's Dashpot.
const check = (label) => {
  const result = dashpot(["worktree", "check", treeA, "--json"]);
  const assessment = parseJson(result.stdout);
  return trace("cleanup", { label, publisher: current.name, status: result.status,
    obstacles: assessment ? (assessment.obstacles ?? []).map(({ kind, detail }) => ({ kind, detail: retained(String(detail ?? "")).slice(0, 400) })) : null,
    error: assessment ? undefined : retained(result.stdout + result.stderr).slice(0, 1500) });
};

// One-shot Codex commands, launched by name through the fixture PATH.
const codex = async (args, label, { cwd = fixture, timeout = 60000 } = {}) => {
  const child = spawn("codex", args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const clean = (text) => stripAnsi(text).replaceAll(root, "<root>");
  const statusLines = (text) => clean(text).split("\n").filter((line) => /^(OpenAI Codex v|warning: |hook: |Installing |Error: )/.test(line)).join("\n");
  trace("codex.command", { label, args: args.map((arg) => arg.replaceAll(root, "<root>")), status, signal, stdout: clean(stdout).slice(-600), stderr: statusLines(stderr).slice(-1200) });
  return { status, signal, stdout, stderr };
};

// An interactive terminal hosted by `script`. Its screen goes to a log in the
// fixture root for diagnosis, never into the trace.
const terminals = [];
const terminal = async (name, args) => {
  const child = spawn("script", ["-qfec", ["codex", ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd: fixture, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  const logPath = path.join(root, `terminal-${name}.log`);
  // The composer treats a burst of keys as a paste, so Enter follows the text
  // after a pause.
  const handle = { name, child, exited: null,
    type: async (text) => { trace("terminal.type", { name, text }); child.stdin.write(text); await delay(700); child.stdin.write("\r"); await delay(300); },
    key: (text) => child.stdin.write(text) };
  child.stdout.on("data", (chunk) => { appendFileSync(logPath, stripAnsi(String(chunk))); });
  child.stderr.on("data", (chunk) => { appendFileSync(logPath, stripAnsi(String(chunk))); });
  // Only the screen's status notices enter the trace, never its transcript.
  const notices = () => { try { return [...new Set(readFileSync(logPath, "utf8").split(/[\r\n]+/).map((line) => line.replace(/\u001b[^a-zA-Z]*[a-zA-Z]/g, "").trim())
    .filter((line) => /read-only|another (process|session)|lock|disconnect|daemon|background server|already|resum/i.test(line) && !line.includes("SPIKE:")))].map(retained).slice(0, 20); } catch { return []; } };
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; trace("terminal.exit", { name, status, signal, notices: notices() }); });
  terminals.push(handle);
  trace("terminal.start", { name, args: args.map((arg) => arg.replaceAll(root, "<root>")), scriptPid: child.pid });
  return handle;
};
const exitTerminal = async (handle) => {
  if (handle.exited) return;
  await handle.type("/exit");
  if (!(await quietly(waitFor(() => handle.exited, `${handle.name} exit`, 10000)))) {
    handle.key("\u0003"); await delay(500); handle.key("\u0003");
    await quietly(waitFor(() => handle.exited, `${handle.name} interrupt exit`, 10000));
  }
};

const freePort = async () => {
  const probe = net.createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const port = probe.address().port;
  probe.close();
  return port;
};
// A JSON-RPC client over a WebSocket: loopback TCP, or the daemon's control
// socket, which speaks WebSocket over a Unix domain socket.
const rpcClient = async (name, socket) => {
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  const onMessage = (text) => {
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method?.startsWith("thread/") || parsed.method?.startsWith("turn/")) {
      const { threadId, turn, status, thread } = parsed.params ?? {};
      notifications.push({ method: parsed.method, threadId: threadId ?? thread?.id, turnId: turn?.id ?? parsed.params?.turnId, status: status ?? turn?.status, receivedAt: Date.now() });
    }
  };
  socket.on(onMessage);
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-460-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, transport: socket.transport, error: init.error ?? null });
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, notifications, close: () => socket.close() };
};
const tcpClient = async (name, port) => {
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(socket, "open");
  return rpcClient(name, { transport: "loopback-websocket", on: (listener) => socket.addEventListener("message", (message) => listener(message.data)), send: (text) => socket.send(text), close: () => socket.close() });
};
const daemonClient = async (name) => {
  const socket = await connectUnixWebSocket(socketPath);
  return rpcClient(name, { transport: "unix-websocket", on: (listener) => socket.on("message", listener), send: (text) => socket.send(text), close: () => socket.close() });
};
const completedTurn = (client, turnId) => client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
const runTurn = async (client, threadId, text) => {
  const since = mark();
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  await waitFor(() => completedTurn(client, turnId), `turn ${text} completed`);
  await quietly(waitFor(() => hookSince(since, (record) => record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000));
  trace("turn.completed", { client: client.name, threadId, turnId, status: completedTurn(client, turnId).status });
};
const startThread = async (client, name) => {
  const started = await client.call("thread/start", { cwd: fixture, model: "fixture-v2" });
  const thread = started.result?.thread;
  trace("thread.start", { name, thread: thread && { id: thread.id, cwd: thread.cwd ?? null, status: thread.status }, error: started.error ?? null });
  assert(thread?.id, `${name} started: ${JSON.stringify(started.error)}`);
  return thread.id;
};
// Whether a worker was still at work at a point: its last command had not
// ended and it had not stopped.
const working = (label, worker) => ({ worker, stopped: stopped(worker), commandsStarted: commands().filter((record) => record.phase === "start" && record.label.startsWith(`${label}.`)).length,
  commandsEnded: commands().filter((record) => record.phase === "end" && record.label.startsWith(`${label}.`)).length, at: Date.now() });

// The runner's own scripts; the verifier is versioned with the trace in Git.
const scripts = ["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const scriptDigests = () => Object.fromEntries(scripts.map((file) => [file, sha256(path.join(here, file))]));
let controllers = [];
let daemonPid = null;
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(os.homedir(), "~"),
    publishers: publishers.map(({ name, source, revision, dirty, built }) => ({ name, source, revision, dirtySource: dirty, sourceSHA256: built })),
    hookEvents, socketPath, sharedDaemonDirBefore: sharedBefore, scriptSHA256: scriptDigests() });

  // Setup: trust the fixture hooks through the ledger on a loopback server.
  trace("scenario", { name: "hook-trust" });
  const port = await freePort();
  const trustServer = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let trustBanner = "";
  trustServer.stderr.on("data", (chunk) => { trustBanner += chunk; });
  trustServer.stdout.on("data", () => {});
  await waitFor(() => trustBanner.includes("listening on"), "trust server listening", 20000);
  const trust = await tcpClient("trust", port);
  const listed = await trust.call("hooks/list", { cwds: [fixture] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await trust.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  trust.close();
  trustServer.kill("SIGTERM");
  await once(trustServer, "exit");
  await delay(500);

  trace("scenario", { name: "daemon" });
  await codex(["app-server", "daemon", "start"], "daemon-start", { timeout: 60000 });
  await waitFor(() => existsSync(socketPath) && daemons().length === 1, "daemon control socket", 30000);
  processes("daemon-started");
  daemonPid = daemons()[0].pid;
  const c1 = await daemonClient("controller-1");
  controllers.push(c1);

  // Scenario, once per publisher and variant: the daemon hosts lead R, whose
  // worker W works; a second terminal resumes R and is given 60 s for a turn,
  // then stays open until W stops and 30 s past it, and exits.
  for (const [index, publisher] of publishers.entries()) {
    usePublisher(publisher);
    for (const variant of variants) {
      const label = `r${index}${variant.tag}`;
      const workerLabel = `w${index}${variant.tag}`;
      trace("scenario", { name: "second-terminal-resume", variant: variant.name, publisher: publisher.name, index });
      const since = mark();
      const lead = await startThread(c1, `lead-${index}${variant.tag}`);
      await runTurn(c1, lead, `SPIKE:${label}-spawn`);
      await waitFor(() => command(`${workerLabel}.0`), `worker ${label}'s first command`);
      const worker = threadOf(`${workerLabel}.0`);
      await delay(1000);
      stored("before", lead);
      check("before");
      const resumeAt = mark();
      const tui = await terminal(`${label}-${variant.name}`, variant.args(lead, `${label}-resumed`));
      await quietly(waitFor(() => hookSince(resumeAt, (record) => record.event === "Stop" && !record.payload.agent_id && record.payload.session_id === lead) || tui.exited,
        `${label} resumed Stop`, 60000));
      await delay(1500);
      const resumeWorking = working(workerLabel, worker);
      processes(`${label}-resumed`);
      standaloneState(`${label}-resumed`);
      stored("resumed-turn", lead);
      check("resumed-turn");
      await quietly(waitFor(() => stopped(worker), `worker ${label} stops`, 120000));
      const workerStopAt = mark();
      await delay(30000);
      standaloneState(`${label}-after-worker`);
      stored("worker-stopped", lead);
      check("worker-stopped");
      const exitAt = mark();
      await exitTerminal(tui);
      await quietly(waitFor(() => hookSince(exitAt, (record) => record.event === "SessionEnd" && record.payload.session_id === lead), `${label} SessionEnd`, 10000));
      await delay(2000);
      await settlersDone(`${label} exit`);
      stored("terminal-exited", lead);
      check("terminal-exited");
      const leadHooks = hooks().filter((record) => record.receipt > resumeAt && record.payload.session_id === lead);
      trace("second-terminal-resume.outcome", { variant: variant.name, publisher: publisher.name, index, lead, worker, daemonPid, resumeAt, workerStopAt, exitAt, resumeWorking,
        hooks: hooks().filter((record) => record.receipt > since).map((record) => record.receipt),
        hostsAfterResume: [...new Set(leadHooks.map(hostOf))] });
    }
  }

  trace("scenario", { name: "daemon-stop" });
  for (const client of controllers) client.close();
  controllers = [];
  await codex(["app-server", "daemon", "stop"], "daemon-stop", { timeout: 60000 });
  await quietly(waitFor(() => !existsSync(`/proc/${daemonPid}`), "daemon gone", 20000));
  await settlersDone("daemon stop");
  processes("after-daemon-stop");

  // Control: with no daemon running, `--no-daemon resume` of the last lead
  // starts its own Host Process and publishes a turn, so a silent terminal
  // above is the daemon's hold on the thread, not this harness.
  trace("scenario", { name: "control-resume" });
  const controlLead = records.filter((record) => record.kind === "second-terminal-resume.outcome").at(-1).lead;
  const controlAt = mark();
  const control = await terminal("control", ["--no-daemon", "resume", "-m", "fixture-v2", "-C", fixture, controlLead, "SPIKE:control-resumed"]);
  await quietly(waitFor(() => hookSince(controlAt, (record) => record.event === "Stop" && !record.payload.agent_id && record.payload.session_id === controlLead) || control.exited,
    "control Stop", 60000));
  await delay(1500);
  standaloneState("control-resumed");
  stored("control-resumed", controlLead);
  await exitTerminal(control);
  await quietly(waitFor(() => hookSince(controlAt, (record) => record.event === "SessionEnd" && record.payload.session_id === controlLead), "control SessionEnd", 10000));
  await settlersDone("control exit");
  trace("control-resume.outcome", { lead: controlLead, hooks: hooks().filter((record) => record.receipt > controlAt).map((record) => record.receipt),
    hosts: [...new Set(hooks().filter((record) => record.receipt > controlAt).map(hostOf))] });
  trace("sources.after", { scriptSHA256: scriptDigests(), publishers: publishers.map(({ name, digests }) => ({ name, sourceSHA256: digests() })) });
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("runner.error", { error: String(error?.stack ?? error).slice(0, 2000) });
  throw error;
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
  for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
  if (daemons().length > 0) await codex(["app-server", "daemon", "stop"], "cleanup-stop").catch(() => {});
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)), removed: sharedBefore.filter((name) => !sharedAfter.includes(name)) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
