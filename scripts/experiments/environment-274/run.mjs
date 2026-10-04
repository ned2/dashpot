// Environment propagation run for Issue #274: which environment a model-run
// tool command sees when its Agent Session runs in a linked Worktree, for a
// pinned Codex CLI's managed daemon and a pinned OpenCode's shared service,
// with the Host Process started before and after the client's environment
// is set, and for the resume and move paths the Issue-work skill uses. A
// shell part first measures what direnv supplies in a linked Worktree, with
// and without a Worktree Root `.envrc`.
//
// Every environment value the run sets is a synthetic fixture label in
// DASHPOT_274_MARKER and DASHPOT_274_TOKEN, never a credential; the second
// name contains TOKEN, as GH_TOKEN does, to show any name-based filtering.
// The fixture's own `.envrc` files hold only those labels. The run builds
// every process's environment from scratch, with isolated HOME, XDG
// directories and CODEX_HOME, so the fixture's managed daemon, shared
// service and direnv allow list are its own. The OpenCode service listens
// on a private port. The models are loopback fixtures, and the trace is
// metadata only: each probe reports the markers and DIRENV_DIR in its own
// environment and in each fixture ancestor's, and its own harness identity
// variables (CODEX_THREAD_ID, OPENCODE_SESSION_ID), never any other
// variable.
//
// Usage, outside every harness session and every Dashpot Project:
//   TMPDIR=<private dir> setsid -f node run.mjs <absolute codex 0.160.0 binary> \
//     <absolute opencode 2.0.22 binary> > run.log 2>&1
//   node verify.mjs <trace.jsonl>
// It is done when it prints "All scenarios completed". SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, inFixture, markers } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// A harness above the runner would be an ancestor of every client the run
// starts, so the runner refuses to start below one; `setsid -f` detaches it.
const above = [];
for (let pid = process.ppid; pid > 1 && above.length < 64;) { try { const entry = describe(pid); above.push(entry); pid = entry.ppid; } catch { break; } }
const harness = above.find((entry) => /^(claude|codex|opencode)/.test(entry.comm) || /\/claude\/versions\//.test(entry.cmdline));
assert(!harness, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harness?.pid} is ${harness?.comm}`);
const [codexBinary, opencodeBinary] = process.argv.slice(2);
assert(codexBinary && path.isAbsolute(codexBinary), "Pass the absolute path to the Codex 0.160.0 binary");
assert(opencodeBinary && path.isAbsolute(opencodeBinary), "Pass the absolute path to the OpenCode 2.0.22 binary");

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-env-274-"));
console.log(`Isolated fixture: ${root}`);
// direnv searches every ancestor of a directory for an `.envrc`; one above
// the fixture would be an operator's, which the run must never load. Only
// existence is checked: nothing is read.
for (let dir = path.dirname(root); ; dir = path.dirname(dir)) {
  assert(!existsSync(path.join(dir, ".envrc")), `An .envrc above the fixture, in ${dir}: choose another TMPDIR`);
  if (dir === path.dirname(dir)) break;
}
const main = path.join(root, "repository");
const pool = path.join(root, "repository.worktrees");
const tree = (name) => path.join(pool, name);
const treeNames = ["a", "b", "c", "d", "e", "f", "g", "h"];
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the fixture root, the binaries' directories,
// this directory and the operator's home by placeholder.
const retained = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(path.dirname(root), "$TMPDIR")
  .replaceAll(path.dirname(codexBinary), "$CODEX_DIR").replaceAll(path.dirname(opencodeBinary), "$OPENCODE_DIR")
  .replaceAll(here, "$EXPERIMENT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const shortened = (key, value) => key === "cmdline" && typeof value === "string" ? retained(value).slice(0, 240) : value;
  appendFileSync(tracePath, retained(JSON.stringify(record, shortened)) + "\n");
  return record;
};
const sha256 = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");

// --- The fixture environment -------------------------------------------------

const home = path.join(root, "home");
const configHome = path.join(root, "config");
const fixtureBin = path.join(root, "bin");
// Both pinned releases run read-only through fixture-local symlinks,
// OpenCode's where its curl installer puts it.
const opencodeBin = path.join(home, ".opencode", "bin");
const env = {
  HOME: home,
  XDG_CONFIG_HOME: configHome,
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  PATH: `${fixtureBin}:${opencodeBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  SHELL: "/bin/bash",
  LANG: "C.UTF-8",
  TERM: "dumb",
  OPENCODE_DISABLE_AUTOUPDATE: "1",
  OPENCODE_DISABLE_MODELS_FETCH: "1",
  OPENCODE_DISABLE_PROJECT_CONFIG: "1",
  // Nothing but loopback is reachable.
  HTTP_PROXY: "http://127.0.0.1:9", HTTPS_PROXY: "http://127.0.0.1:9", http_proxy: "http://127.0.0.1:9", https_proxy: "http://127.0.0.1:9",
  NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost",
};
for (const dir of [main, pool, home, configHome, fixtureBin, opencodeBin, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME,
  path.join(configHome, "opencode")]) mkdirSync(dir, { recursive: true });
symlinkSync(codexBinary, path.join(fixtureBin, "codex"));
symlinkSync(opencodeBinary, path.join(opencodeBin, "opencode"));
const versions = {
  codex: execFileSync("codex", ["--version"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim(),
  opencode: execFileSync("opencode", ["--version"], { env, encoding: "utf8" }).trim(),
  direnv: execFileSync("direnv", ["version"], { env, encoding: "utf8" }).trim(),
  bash: execFileSync("bash", ["-c", "echo $BASH_VERSION"], { env, encoding: "utf8" }).trim(),
};
assert.equal(versions.codex, "codex-cli 0.160.0", `unexpected Codex version: ${versions.codex}`);
assert.equal(versions.opencode, "opencode v2.0.22", `unexpected OpenCode version: ${versions.opencode}`);

// A person's interactive bash with direnv's hook, as direnv's setup asks;
// a login shell reads it too.
writeFileSync(path.join(home, ".bashrc"), `PS1='fixture$ '\neval "$(direnv hook bash)"\n`);
writeFileSync(path.join(home, ".bash_profile"), "[ -f ~/.bashrc ] && . ~/.bashrc\n");

// The Repository: a main checkout with the checkout-scoped `.envrc` the
// Issue describes, ignored, and linked Worktrees in the sibling Worktree
// Root, `repository.worktrees`.
const git = (...args) => execFileSync("git", ["-C", main, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
writeFileSync(path.join(main, "README.md"), "Disposable fixture.\n");
git("add", "README.md");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
for (const name of treeNames) git("worktree", "add", "-q", "-b", name, tree(name));
appendFileSync(path.join(main, ".git", "info", "exclude"), ".envrc\n");
const checkoutEnvrc = "# Synthetic markers for the #274 experiment; never credentials.\nexport DASHPOT_274_MARKER=checkout-envrc\nexport DASHPOT_274_TOKEN=checkout-envrc\n";
writeFileSync(path.join(main, ".envrc"), checkoutEnvrc);
const direnv = (...args) => spawnSync("direnv", args, { env, encoding: "utf8", timeout: 30000 });
assert.equal(direnv("allow", main).status, 0, "direnv allows the fixture checkout's .envrc");
// The operator-local remedy the Issue names, added after the shell part's
// first scenarios: one `.envrc` in the Worktree Root.
const poolEnvrc = `source_env ${path.join(main, ".envrc")}\n`;
const addPoolEnvrc = () => {
  writeFileSync(path.join(pool, ".envrc"), poolEnvrc);
  assert.equal(direnv("allow", pool).status, 0, "direnv allows the fixture Worktree Root's .envrc");
  trace("pool-envrc", { path: path.join(pool, ".envrc"), content: poolEnvrc });
};

// --- Servers -----------------------------------------------------------------

const listen = async (handler) => {
  const server = http.createServer(async (req, res) => {
    try { await handler(req, res); } catch (error) {
      trace("server.error", { path: req.url, error: retained(String(error?.stack ?? error)).slice(0, 1000) });
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
// The sink keeps only the probe's records.
const sink = await listen(async (req, res) => {
  let record = null;
  try { record = await body(req); } catch {}
  if (req.url === "/command" && typeof record?.label === "string") trace("probe", record);
  else trace("sink.foreign", { method: req.method, url: retained(String(req.url)).slice(0, 80) });
  res.end("{}");
});
const commandScript = path.join(here, "command.mjs");
const probeCommand = (label) => `${process.execPath} ${commandScript} ${label} ${sink.url} ${configHome} ${process.pid}`;
const probes = () => records.filter((record) => record.kind === "probe");
const probe = (label) => probes().findLast((record) => record.label === label);

const waitFor = async (predicate, label, timeout = 60000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || Number(name) === process.pid) continue;
    if (!inFixture(name, configHome)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const markersOf = (pid) => { try { return markers(pid); } catch { return null; } };
const brief = (entry) => ({ pid: entry.pid, ppid: entry.ppid, comm: entry.comm, cmdline: retained(entry.cmdline).slice(0, 200), markers: markersOf(entry.pid) });
const descendants = (pid) => {
  const all = fixtureProcesses();
  const found = [];
  const frontier = [pid];
  while (frontier.length) {
    const parent = frontier.shift();
    for (const entry of all.filter((item) => item.ppid === parent)) { found.push(entry); frontier.push(entry.pid); }
  }
  return found;
};

// --- Clients -----------------------------------------------------------------

const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007\u001b]*(\u0007|\u001b\\)/g, "").replace(/\u001b[()][A-Z0-9]/g, "");
const quote = (arg) => /^[\w./:=@,+-]+$/.test(arg) ? arg : `'${arg.replaceAll("'", "'\\''")}'`;
const clients = [];
// A client launched as a person would: in `cwd`, with `set` added to the
// base environment, optionally through `direnv exec <cwd>`, as a launcher
// wrapper would, and optionally on a pseudo-terminal. The screen goes to a
// log in the fixture root, never into the trace.
const launch = (name, argv, { cwd = main, set = {}, through = null, terminal = false } = {}) => {
  const full = through === "direnv" ? ["direnv", "exec", cwd, ...argv] : argv;
  const launchEnv = { ...env, ...set, PWD: cwd };
  // `opencode run` reads a message from a piped stdin, so a client off a
  // terminal gets none.
  const child = terminal
    ? spawn("script", ["-qfec", full.map(quote).join(" "), "/dev/null"], { cwd, env: { ...launchEnv, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] })
    : spawn(full[0], full.slice(1), { cwd, env: launchEnv, stdio: ["ignore", "pipe", "pipe"] });
  const state = { name, child, exited: null, output: "" };
  const log = path.join(root, `client-${name}.log`);
  const keep = (chunk) => { const text = stripAnsi(String(chunk)); state.output += text; appendFileSync(log, text); };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  child.on("exit", (code, signal) => { state.exited = { code, signal, at: Date.now() }; trace("client.exit", { name, code, signal }); });
  clients.push(state);
  trace("launch", { name, argv: full, cwd, set, through, terminal, pid: child.pid });
  return state;
};
// The harness client process a launch started, and the markers in its
// environment: what the person's terminal handed the client.
const clientOf = (state, pattern, exclude) => {
  let own = [];
  try { own = [describe(state.child.pid)]; } catch {}
  return [...own, ...descendants(state.child.pid)].find((entry) => pattern.test(entry.comm) && !(exclude?.test(entry.cmdline)));
};
const recordClient = async (state, pattern, exclude) => {
  let found = null;
  await quietly(waitFor(() => (found = clientOf(state, pattern, exclude)), `${state.name} client process`, 15000));
  return trace("client", { name: state.name, process: found ? brief(found) : null });
};
const type = async (state, text) => { state.child.stdin.write(text); await delay(700); state.child.stdin.write("\r"); await delay(300); };
const finished = (state, timeout = 90000) => waitFor(() => state.exited, `${state.name} exit`, timeout);

// --- Part 1: what direnv supplies in a linked Worktree -----------------------

// A command run directly, through `direnv exec`.
const direct = (label, directory, cwd = directory) => {
  const ran = spawnSync("direnv", ["exec", directory, "sh", "-c", probeCommand(label)], { cwd, env: { ...env, PWD: cwd }, encoding: "utf8", timeout: 30000 });
  trace("direnv.exec", { label, directory, cwd, status: ran.status, stderr: retained(ran.stderr).slice(0, 400) });
};
// An interactive shell on a pseudo-terminal, given lines to run one prompt
// after another.
const interactive = async (name, command, cwd, lines) => {
  const state = launch(name, command, { cwd, terminal: true });
  await delay(1500);
  for (const line of lines) {
    const label = line.label;
    state.child.stdin.write((line.prefix ?? "") + probeCommand(label) + "\n");
    await waitFor(() => probe(label), `${label} probe`, 20000);
    await delay(500);
  }
  state.child.stdin.write("exit\n");
  await finished(state, 15000);
};

// --- Part 2: Codex -----------------------------------------------------------

const markerPattern = /SPIKE:([a-z0-9-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const codexSteps = new Map();
const codexModel = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/responses")) {
    trace("codex.model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "not_found", message: "fixture" } }));
    return;
  }
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const input = payload.input ?? [];
  let label = null;
  for (const item of input) {
    if (isCall(item)) continue;
    const found = [...JSON.stringify(item).matchAll(markerPattern)];
    if (found.length) label = found.at(-1)[1];
  }
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => nested.name) : [tool.name ?? tool.type]);
  const key = `${thread}:${label}`;
  const step = codexSteps.get(key) ?? 0;
  codexSteps.set(key, step + 1);
  // One probe per directive, by whichever shell tool the model is offered:
  // 0.160.0 offers `exec_command`, and the other two keep the fixture usable
  // on a release that offers an older tool. A request offered none, such as
  // the terminal's side thread, gets text.
  let item = null;
  let tool = null;
  if (label && step === 0) {
    const command = probeCommand(label);
    const call = (name, args) => ({ type: "function_call", call_id: `call_${label}_${records.length}`, name, arguments: JSON.stringify(args) });
    if (tools.includes("exec_command")) { tool = "exec_command"; item = call(tool, { cmd: command, yield_time_ms: 30000 }); }
    else if (tools.includes("shell_command")) { tool = "shell_command"; item = call(tool, { command }); }
    else if (tools.includes("shell")) { tool = "shell"; item = call(tool, { command: ["bash", "-lc", command] }); }
  }
  trace("codex.model.request", { thread, label, step, tool, toolCount: tools.length });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const id = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture", display_name: "Fixture", prefer_websockets: false }] }, null, 2));
writeFileSync(path.join(env.CODEX_HOME, "config.toml"), `model = "fixture"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"
check_for_update_on_startup = false

[features]
# The curated plugin marketplace sync clones a GitHub repository at startup.
plugins = false
apps = false

[analytics]
enabled = false

[model_providers.fixture]
name = "Fixture"
base_url = "${codexModel.url}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0

${[main, ...treeNames.map(tree)].map((directory) => `[projects."${directory}"]\ntrust_level = "trusted"\n`).join("\n")}`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network and could replace or restart the daemon.
const daemonSettings = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettings), { recursive: true });
writeFileSync(daemonSettings, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run records how many entries it held and which it
// added or removed, and removes none itself.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

const isDaemon = (entry) => /^codex/.test(entry.comm) && / app-server /.test(entry.cmdline) && /--managed-daemon/.test(entry.cmdline);
const daemons = () => fixtureProcesses().filter(isDaemon);
// Codex runs its managed daemon from its own copy of the release in
// CODEX_HOME, so each daemon's executable is hashed against the pinned one.
const exeSHA256 = (pid) => { try { return sha256(`/proc/${pid}/exe`); } catch { return null; } };
const recordDaemons = (label) => trace("codex.daemons", { label, daemons: daemons().map((entry) => ({ ...brief(entry), exeSHA256: exeSHA256(entry.pid) })) });
const codexCommand = (label, args, set = {}) => {
  const ran = spawnSync("codex", args, { cwd: main, env: { ...env, ...set, PWD: main }, encoding: "utf8", timeout: 60000 });
  return trace("codex.command", { label, args, set, status: ran.status, stdout: retained(stripAnsi(ran.stdout ?? "")).slice(-400), stderr: retained(stripAnsi(ran.stderr ?? "")).split("\n").filter((line) => /^(Error|error|warning)/.test(line)).join("\n").slice(-600) });
};
const stopDaemon = async (label) => {
  const pids = daemons().map((entry) => entry.pid);
  codexCommand(`${label}-stop`, ["app-server", "daemon", "stop"]);
  await waitFor(() => pids.every((pid) => !alive(pid)) && daemons().length === 0, `${label}: daemon stopped`, 30000);
  recordDaemons(`${label}-stopped`);
};
// A Codex terminal: launch, wait for the turn's probe, record the client
// and any daemon, then `/exit`.
const codexTerminal = async (name, args, options) => {
  const state = launch(name, ["codex", ...args], { ...options, terminal: true });
  await recordClient(state, /^codex/, / app-server /);
  await waitFor(() => probe(name) || state.exited, `${name} probe`, 90000);
  assert(probe(name), `${name}: no probe, client exited: ${JSON.stringify(state.exited)}; ${state.output.slice(-600)}`);
  recordDaemons(name);
  await delay(1500);
  await type(state, "/exit");
  if (!(await quietly(finished(state, 10000)))) {
    state.child.stdin.write("\u0003"); await delay(500); state.child.stdin.write("\u0003");
    await quietly(finished(state, 10000));
  }
  return probe(name);
};

// --- Part 3: OpenCode --------------------------------------------------------

const opencodeSteps = new Map();
const opencodeSequences = {
  // The skill's move: `session_move` through `execute`, alone in its step,
  // and the probe in the next step.
  "opencode-move": () => [{ name: "execute", arguments: { code: `return await tools.opencode.session_move(${JSON.stringify({ directory: tree("e") })})` } }],
};
const textOf = (message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "");
const opencodeModel = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const anchor = messages.findLastIndex((message) => message.role === "user" && /PROBE:/.test(textOf(message)));
  const label = anchor >= 0 ? [...textOf(messages[anchor]).matchAll(/PROBE:([a-z0-9-]+)/g)].at(-1)[1] : null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const titled = /title generator/i.test(system) || !tools.length;
  const step = messages.slice(anchor + 1).filter((message) => message.role === "assistant").length;
  const planned = [...(opencodeSequences[label]?.() ?? []), { name: "shell", arguments: { command: probeCommand(label) } }];
  const call = !titled && label ? planned[step] ?? null : null;
  trace("opencode.model.request", { label, step, titled, tool: call?.name ?? null, sessionID: req.headers["x-opencode-session-id"] ?? null,
    previous: !titled && step > 0 ? retained(messages.filter((message) => message.role === "tool").map(textOf).at(-1) ?? "").slice(0, 300) : undefined });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (call) chunk({ role: "assistant", tool_calls: [{ index: 0, id: `call_${label}_${step}_${records.length}`, type: "function", function: { name: call.name, arguments: JSON.stringify(call.arguments) } }] });
  else chunk({ role: "assistant", content: titled ? "Fixture title" : `DONE:${label}` });
  chunk({}, call ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});
const freePort = async () => {
  const server = net.createServer().listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  server.close();
  return port;
};
const servicePort = await freePort();
const password = "fixture-password";
writeFileSync(path.join(configHome, "opencode", "service.json"), JSON.stringify({ hostname: "127.0.0.1", port: servicePort, password }));
writeFileSync(path.join(configHome, "opencode", "opencode.json"), JSON.stringify({
  model: "loop/fixture", update: "disable", share: "disabled", snapshots: false, lsp: false, formatter: false,
  providers: { loop: { name: "Loop", package: "aisdk:@ai-sdk/openai-compatible",
    settings: { baseURL: opencodeModel.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 128000, output: 4096 } } } } },
  permissions: [{ action: "*", resource: "*", effect: "allow" }],
}, null, 2));
const registration = () => { try { return JSON.parse(readFileSync(path.join(env.XDG_STATE_HOME, "opencode", "service.json"), "utf8")); } catch { return null; } };
const authorization = "Basic " + Buffer.from(`opencode:${password}`).toString("base64");
const sessionLocation = async (id) => {
  try {
    const response = await fetch(`http://127.0.0.1:${servicePort}/api/session/${id}`, { headers: { authorization }, signal: AbortSignal.timeout(10000) });
    const parsed = JSON.parse(await response.text());
    return (parsed?.data ?? parsed)?.location?.directory ?? null;
  } catch { return null; }
};
// The HTTP API, as a controller with no environment of its own to send:
// a session created through it, and a prompt sent through it.
const api = async (method, route, data) => {
  const response = await fetch(`http://127.0.0.1:${servicePort}${route}`, { method, headers: { "content-type": "application/json", authorization },
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(120000) });
  const raw = await response.text();
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch {}
  assert(response.status >= 200 && response.status < 300, `${method} ${route}: ${response.status} ${raw.slice(0, 300)}`);
  return parsed?.data ?? parsed;
};
const apiSession = async (label, directory) => {
  const made = await api("POST", "/api/session", { title: label, location: { directory }, model: { id: "fixture", providerID: "loop" } });
  trace("opencode.api.session", { label, sessionID: made.id, directory: made.location?.directory ?? null });
  return made.id;
};
const apiPrompt = async (label, id) => {
  await api("POST", `/api/session/${id}/prompt`, { text: `PROBE:${label}` });
  await api("POST", `/api/experimental/session/${id}/wait`, {});
  assert(probe(label), `${label}: no probe`);
  trace("opencode.api.prompt", { label, sessionID: id });
  recordService(label);
  return probe(label);
};
const recordService = (label) => {
  const found = registration();
  const running = found?.pid && alive(found.pid) ? describe(found.pid) : null;
  return trace("opencode.service", { label, registered: Boolean(found), process: running ? brief(running) : null,
    servers: fixtureProcesses().filter((entry) => /^opencode/.test(entry.comm) && / serve /.test(` ${entry.cmdline} `)).map(brief) });
};
const opencodeCli = (label, args, set = {}) => {
  const ran = spawnSync("opencode", args, { cwd: main, env: { ...env, ...set, PWD: main }, encoding: "utf8", timeout: 60000 });
  return trace("opencode.command", { label, args, set, status: ran.status, stdout: retained(ran.stdout ?? "").slice(-400), stderr: retained(ran.stderr ?? "").slice(-600) });
};
const stopService = async (label) => {
  const pid = registration()?.pid;
  opencodeCli(`${label}-stop`, ["service", "stop"]);
  if (pid) await waitFor(() => !alive(pid), `${label}: service stopped`, 20000);
  recordService(`${label}-stopped`);
};
// `opencode run`, to completion.
const opencodeRun = async (name, args, options) => {
  const state = launch(name, ["opencode", "run", ...args], options);
  await recordClient(state, /^opencode/, / serve /);
  await finished(state, 90000);
  assert(probe(name), `${name}: no probe; ${state.output.slice(-600)}`);
  recordService(name);
  return probe(name);
};
// The TUI, with `--prompt`, quit once the turn's probe ran.
const opencodeTui = async (name, args, options) => {
  const state = launch(name, ["opencode", ...args], { ...options, terminal: true });
  await recordClient(state, /^opencode/, / serve /);
  await waitFor(() => probe(name) || state.exited, `${name} probe`, 90000);
  assert(probe(name), `${name}: no probe; ${state.output.slice(-600)}`);
  recordService(name);
  await delay(1500);
  for (let attempt = 0; attempt < 4 && !state.exited; attempt++) {
    state.child.stdin.write("\u0003");
    await quietly(finished(state, 3000));
  }
  if (!state.exited) { state.child.stdin.write("/exit\r"); await quietly(finished(state, 5000)); }
  assert(state.exited, `${name} did not quit`);
  return probe(name);
};

// --- The run -----------------------------------------------------------------

const scripts = ["run.mjs", "command.mjs", "ancestry.mjs"];
let failed = null;
try {
  trace("environment", { versions, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    codexBinary, codexTarget: execFileSync("readlink", ["-f", codexBinary], { encoding: "utf8" }).trim(), codexSHA256: sha256(codexBinary),
    opencodeBinary, opencodeSHA256: sha256(opencodeBinary), main, pool, trees: Object.fromEntries(treeNames.map((name) => [name, tree(name)])),
    baseEnvironment: Object.keys(env).sort(), checkoutEnvrc, servicePort, sharedDaemonDirEntriesBefore: sharedBefore.length,
    sourceSHA256: Object.fromEntries(scripts.map((file) => [file, sha256(path.join(here, file))])) });

  // Part 1. Without a Worktree Root `.envrc`, direnv loads nothing in a
  // linked Worktree; the main checkout's `.envrc` loads only for a command
  // inside the main checkout, and an interactive shell with the hook drops
  // it at the first prompt outside.
  trace("scenario", { name: "shell" });
  direct("shell-exec-main", main);
  direct("shell-exec-worktree", tree("a"));
  await interactive("shell-main-into-worktree-hook", ["direnv", "exec", main, "bash", "-i"], tree("a"), [{ label: "shell-main-into-worktree-hook" }]);
  await interactive("shell-main-into-worktree-nohook", ["direnv", "exec", main, "bash", "--norc", "-i"], tree("a"), [{ label: "shell-main-into-worktree-nohook" }]);
  await interactive("shell-cd-from-main", ["bash", "-i"], main, [
    { label: "shell-cd-at-main" }, { label: "shell-cd-same-line", prefix: `cd ${tree("a")} && ` }, { label: "shell-cd-next-prompt" }]);
  await interactive("shell-worktree-hook", ["bash", "-i"], tree("a"), [{ label: "shell-worktree-hook" }]);
  addPoolEnvrc();
  direct("shell-pool-exec-worktree", tree("a"));
  await interactive("shell-pool-worktree-hook", ["bash", "-i"], tree("a"), [{ label: "shell-pool-worktree-hook" }]);
  await interactive("shell-pool-wrapper-hook", ["direnv", "exec", tree("a"), "bash", "-i"], tree("a"), [{ label: "shell-pool-wrapper-hook" }]);

  // Part 2. Codex: a terminal with no daemon hosts its own thread; with the
  // daemon, the daemon runs every thread's tools, in the environment it
  // started with.
  trace("scenario", { name: "codex" });
  const marked = (label) => ({ DASHPOT_274_MARKER: label, DASHPOT_274_TOKEN: label });
  recordDaemons("codex-start");
  assert.equal(daemons().length, 0, "no fixture daemon before the Codex part");
  await codexTerminal("codex-standalone", ["--disable", "daemon_auto_start", "-C", tree("a"), "SPIKE:codex-standalone"], { cwd: tree("a"), set: marked("codex-standalone-client") });
  assert.equal(daemons().length, 0, "the standalone terminal starts no daemon");
  // The daemon starts under a client whose environment has no markers.
  await codexTerminal("codex-first", ["-C", main, "SPIKE:codex-first"], { cwd: main });
  const firstThread = probe("codex-first").env.CODEX_THREAD_ID;
  assert(firstThread, "codex-first's thread id");
  await codexTerminal("codex-later-direnv", ["-C", tree("b"), "SPIKE:codex-later-direnv"], { cwd: tree("b"), through: "direnv" });
  await codexTerminal("codex-later-set", ["-C", tree("c"), "SPIKE:codex-later-set"], { cwd: tree("c"), set: marked("codex-later-client") });
  await codexTerminal("codex-resume", ["resume", firstThread, "-C", tree("d"), "SPIKE:codex-resume"], { cwd: tree("d"), through: "direnv" });
  await stopDaemon("codex-first-daemon");
  // The daemon starts under a client launched through direnv in a linked
  // Worktree, and every later client's tools run in its environment.
  await codexTerminal("codex-autostart-direnv", ["-C", tree("e"), "SPIKE:codex-autostart-direnv"], { cwd: tree("e"), through: "direnv" });
  await codexTerminal("codex-inherited", ["-C", main, "SPIKE:codex-inherited"], { cwd: main });
  await codexTerminal("codex-resume-inherited", ["resume", firstThread, "-C", tree("f"), "SPIKE:codex-resume-inherited"], { cwd: main });
  await stopDaemon("codex-direnv-daemon");
  // `app-server daemon start`, run with markers, then a client without.
  codexCommand("codex-daemon-start", ["app-server", "daemon", "start"], marked("codex-daemon-start"));
  await waitFor(() => daemons().length === 1, "explicitly started daemon", 30000);
  recordDaemons("codex-daemon-started");
  await codexTerminal("codex-after-daemon-start", ["-C", tree("g"), "SPIKE:codex-after-daemon-start"], { cwd: tree("g") });
  await stopDaemon("codex-explicit-daemon");
  // With no daemon, a resume with daemon autostart off hosts the thread in
  // the resuming client.
  await codexTerminal("codex-standalone-resume", ["resume", "--disable", "daemon_auto_start", firstThread, "-C", tree("h"), "SPIKE:codex-standalone-resume"],
    { cwd: tree("h"), set: marked("codex-standalone-resume-client") });
  assert.equal(daemons().length, 0, "the standalone resume starts no daemon");

  // Part 3. OpenCode: a `--standalone` client's private server runs its
  // tools; otherwise the shared service does. A client of the service sends
  // its own environment as the session's variables
  // (`PUT /api/session/:id/environment`); the API scenarios show what a
  // prompt that sends none runs in.
  trace("scenario", { name: "opencode" });
  recordService("opencode-start");
  assert(!registration(), "no fixture service before the OpenCode part");
  await opencodeRun("opencode-standalone", ["--standalone", "PROBE:opencode-standalone"], { cwd: tree("a"), set: marked("opencode-standalone-client") });
  // The service starts under a TUI whose environment has no markers.
  await opencodeTui("opencode-first", [main, "--prompt", "PROBE:opencode-first"], { cwd: main });
  const firstSession = probe("opencode-first").env.OPENCODE_SESSION_ID;
  assert(firstSession, "opencode-first's session id");
  await opencodeRun("opencode-later-direnv", ["PROBE:opencode-later-direnv"], { cwd: tree("b"), through: "direnv" });
  // A prompt through the API to the session the direnv client created.
  await apiPrompt("opencode-api-prompt", probe("opencode-later-direnv").env.OPENCODE_SESSION_ID);
  await opencodeTui("opencode-later-tui", [tree("c"), "--prompt", "PROBE:opencode-later-tui"], { cwd: tree("c"), through: "direnv" });
  await opencodeRun("opencode-continue", ["--session", firstSession, "PROBE:opencode-continue"], { cwd: tree("d"), through: "direnv" });
  trace("opencode.session", { label: "opencode-continue", sessionID: firstSession, location: await sessionLocation(firstSession) });
  await opencodeRun("opencode-move", ["--session", firstSession, "PROBE:opencode-move"], { cwd: tree("d"), through: "direnv" });
  trace("opencode.session", { label: "opencode-move", sessionID: firstSession, location: await sessionLocation(firstSession) });
  await stopService("opencode-first-service");
  // The service starts under a TUI launched through direnv in a linked
  // Worktree, and later clients without markers prompt it.
  await opencodeTui("opencode-service-direnv", [tree("f"), "--prompt", "PROBE:opencode-service-direnv"], { cwd: tree("f"), through: "direnv" });
  await opencodeRun("opencode-inherited", ["PROBE:opencode-inherited"], { cwd: main });
  await opencodeRun("opencode-moved-inherited", ["--session", firstSession, "PROBE:opencode-moved-inherited"], { cwd: main });
  // A session created and prompted through the API, which sends no
  // environment, on a service that has the markers.
  await apiPrompt("opencode-api-session", await apiSession("opencode-api-session", tree("h")));
  await stopService("opencode-direnv-service");
  // `opencode service start`, run with markers, then a client without.
  opencodeCli("opencode-service-start", ["service", "start"], marked("opencode-service-start"));
  await waitFor(() => registration()?.pid && alive(registration().pid), "explicitly started service", 30000);
  recordService("opencode-service-started");
  await opencodeRun("opencode-after-service-start", ["PROBE:opencode-after-service-start"], { cwd: tree("g") });
  // The direnv client's session, prompted through the API once the service
  // has restarted with other markers: whether the session's variables
  // outlive the service that received them.
  await apiPrompt("opencode-api-after-restart", probe("opencode-later-direnv").env.OPENCODE_SESSION_ID);
  await stopService("opencode-explicit-service");
  console.log("All scenarios completed");
} catch (error) {
  failed = error;
  trace("runner.error", { error: retained(String(error?.stack ?? error)).slice(0, 2000) });
} finally {
  for (const state of clients) { if (!state.exited) { try { state.child.kill("SIGTERM"); } catch {} } }
  if (daemons().length) codexCommand("cleanup-daemon-stop", ["app-server", "daemon", "stop"]);
  if (registration()?.pid && alive(registration().pid)) opencodeCli("cleanup-service-stop", ["service", "stop"]);
  await delay(1500);
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)), removed: sharedBefore.filter((name) => !sharedAfter.includes(name)) });
  for (const server of [sink, codexModel, opencodeModel]) { server.server.closeAllConnections(); server.server.close(); }
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1" && !failed) rmSync(root, { recursive: true });
  if (failed) { console.error(failed); process.exitCode = 1; }
}
