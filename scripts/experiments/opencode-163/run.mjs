// Real-harness acceptance run for Issue #163: OpenCode sessions observed
// through Dashpot's managed plugin, publisher generations and command-scoped
// claims (ADR 0077, ADR 0078, ADR 0080). It drives a pinned OpenCode release
// against a loopback OpenAI-compatible model fixture, in disposable
// configuration and state. Dashpot is built from this checkout and installed
// into a fixture environment, and `dashpot integrate opencode` from that
// installation writes the plugin and skill the run exercises, so the plugin
// and helper are exactly what an installation runs. The sessions' shells run
// that installation's `dashpot work` commands, as the Issue-work skill does.
// Between steps the runner records what `dashpot --json` and
// `dashpot worktree check` observe, and OpenCode's own session events. The
// trace is metadata only; the runner asserts only what it needs to keep
// going, and the independent verifier checks the trace against the
// documented claims.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode binary> [expected version] > log 2>&1
// It is done when it prints "All scenarios completed".
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import {
  appendFileSync, chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, renameSync,
  rmSync, symlinkSync, writeFileSync,
} from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
// A harness above the runner would be the Host Process Dashpot finds for any
// fixture process it does not recognise, so the runner refuses to start below
// one; `setsid -f` detaches it.
const host = ancestry(process.ppid, 64, 1).find((entry) => ["claude", "codex", "opencode"].includes(entry.comm) || /\/claude\/versions\//.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the OpenCode binary");
const expectedVersion = process.argv[3] ?? "1.18.30";
const uv = execFileSync("sh", ["-c", "command -v uv"], { encoding: "utf8" }).trim();

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-163-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree, where the shared backend runs; a sibling
// linked Worktree with a session of that backend; and a linked Worktree an
// ordinary TUI runs in. Both linked Worktrees are removable, so Cleanup can
// be asked about them.
const fixture = path.join(root, "repository");
const sibling = path.join(root, "repository.worktrees", "sibling");
const tuiTree = path.join(root, "repository.worktrees", "tui");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root, this directory, the
// checkout, and the operator's home by placeholder.
// A slice cut inside the fixture's path keeps only its temporary parent.
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(path.dirname(root), "$TMPDIR").replaceAll(here, "$EXPERIMENT")
  .replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const sha256 = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");

// Dashpot, built from this checkout and installed outside every Worktree, as
// a person's installation is; its helper is what the plugin is bound to.
const venv = path.join(root, "venv");
execFileSync(uv, ["build", "-q", "--wheel", "-o", path.join(root, "dist"), checkout], { stdio: "pipe" });
const [wheel] = readdirSync(path.join(root, "dist")).filter((name) => name.endsWith(".whl"));
execFileSync(uv, ["venv", "-q", "--python", path.join(checkout, ".venv", "bin", "python"), venv], { stdio: "pipe" });
execFileSync(uv, ["pip", "install", "-q", "--offline", "--python", path.join(venv, "bin", "python"), path.join(root, "dist", wheel)], { stdio: "pipe" });
const dashpot = path.join(venv, "bin", "dashpot");
const helper = path.join(venv, "bin", "dashpot-opencode-hook");
const installed = execFileSync(path.join(venv, "bin", "python"), ["-c", "import dashpot, os; print(os.path.dirname(dashpot.__file__))"], { encoding: "utf8" }).trim();
// The Dashpot sources the run exercises; the installed copies must be them.
const exercised = ["plugins/opencode.js", "sessions/opencode_publish.py", "sessions/opencode_publishers.py", "sessions/hook_claims.py",
  "sessions/hook_scan.py", "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/harnesses.py", "sessions/work.py",
  "sessions/integrate.py", "repository/cleanup/obstacles.py", "hook.py"];

// OpenCode starts through a launcher named `opencode`, as a person's does.
const launcherDirectory = path.join(root, "bin");
mkdirSync(launcherDirectory);
symlinkSync(binary, path.join(launcherDirectory, "opencode"));
const env = {
  PATH: `${launcherDirectory}:${path.join(venv, "bin")}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  OPENCODE_DISABLE_PROJECT_CONFIG: "true",
  OPENCODE_DISABLE_DEFAULT_PLUGINS: "true",
  OPENCODE_DISABLE_AUTOUPDATE: "true",
  OPENCODE_DISABLE_MODELS_FETCH: "true",
  OPENCODE_DISABLE_LSP_DOWNLOAD: "true",
  OPENCODE_DISABLE_FFF: "true",
  OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER: "true",
  // Sessions outside a configured checkout would publish here.
  DASHPOT_STATE_DIR: path.join(root, "dashpot-state"),
  // Ancestry walks from shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_DASHPOT: dashpot,
  SPIKE_HELPER: helper,
};
const configHome = path.join(env.XDG_CONFIG_HOME, "opencode");
for (const dir of [fixture, env.HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, configHome]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, expectedVersion, `unexpected OpenCode version: ${version}`);

// A Dashpot Project with a markdown Issue Source, one Issue per binding.
mkdirSync(path.join(fixture, ".dashpot"), { recursive: true });
mkdirSync(path.join(fixture, "issues"), { recursive: true });
writeFileSync(path.join(fixture, ".dashpot", "config.json"), JSON.stringify({ projectId: "project:fixture", displayLabel: "Fixture", repositoryId: "repository:fixture", issueSource: { kind: "markdown", path: "issues" } }));
for (let number = 1; number <= 12; number++) {
  const front = { id: `I_fixture_${number}`, number, reference: `issue-${number}`, state: "open", stateReason: null, labels: [], assignees: [], author: "fixture",
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `issue-${number}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
}
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "sibling", sibling);
git("worktree", "add", "-b", "tui", tuiTree);

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
const sink = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  trace(url.pathname === "/replay" ? "replay" : "command", await body(req));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model: a `PROBE:<label>` text in the latest user turn selects a
// tool sequence, built when the model is asked so it can name sessions the
// runner learns later, and the turn ends once every step has a tool result.
const commandScript = path.join(here, "command.mjs");
const known = {};
const bash = (command, workdir) => ({ name: "bash", arguments: { command, description: "Fixture step", ...(workdir ? { workdir } : {}) } });
const report = (label, hold = 200) => bash(`node ${commandScript} ${label} ${hold}`);
const work = (label, ...args) => bash(`node ${commandScript} ${label} 0 -- work ${args.join(" ")}`);
const delegate = (child, background = false) => ({ name: "task", arguments: { description: `Fixture ${child}`, prompt: `PROBE:${child}`, subagent_type: "general", ...(background ? { background: true } : {}) } });
const sequences = {
  "bind-1": () => [work("s1-start", "start", "issue-1"), work("s1-show", "show")],
  "bind-2": () => [work("s2-start", "start", "issue-2"), work("s2-show", "show")],
  "bind-3": () => [work("s3-start", "start", "issue-3"), work("s3-show", "show")],
  "hold-1": () => [report("s1-hold", 6000)],
  "switch-1": () => [work("s1-switch", "start", "issue-4"), work("s1-switched-show", "show")],
  "stop-2": () => [work("s2-stop", "stop"), work("s2-stopped-show", "show")],
  "refusals-2": () => [
    bash(`cd ${sibling} && node ${commandScript} s2-cd-sibling 0 -- work start issue-5`),
    bash(`node ${commandScript} s2-workdir-sibling 0 -- work start issue-5`, sibling),
    bash(`DASHPOT_OPENCODE_SESSION_ID= DASHPOT_OPENCODE_GENERATION= DASHPOT_OPENCODE_PID= DASHPOT_AGENT_SESSION=opencode:${known.s2} node ${commandScript} s2-explicit 0 -- work start issue-5`),
  ],
  "attached-show": () => [work("s3-attached-show", "show")],
  "detach-hold": () => [report("s3-detach-hold", 8000)],
  "reattached": () => [work("s3-reattached-show", "show")],
  "tui-attached": () => [work("s3-tui-attached-show", "show")],
  "delegate-1": () => [delegate("child-hold")],
  "child-hold": () => [report("child-hold", 5000), work("child-start", "start", "issue-6")],
  "fork": () => [work("fork-show", "show"), work("fork-start", "start", "issue-7"), work("fork-show-bound", "show")],
  "retry": () => [report("s3-retried")],
  "interrupt": () => [report("s3-interrupted", 20000)],
  "refused": () => [],
  "after-replace": () => [work("s1-after-replace", "show"),
    bash(`DASHPOT_OPENCODE_GENERATION=${known.retired} node ${commandScript} s1-retired-claim 0 -- work start issue-4`)],
  "unplugged": () => [work("s1-unplugged-start", "start", "issue-8")],
  "restored": () => [work("s1-restored-show", "show")],
  "missing-helper": () => [report("s2-missing-helper")],
  "stalled-helper": () => [report("s2-stalled-helper")],
  "helper-back": () => [report("s2-helper-back")],
  "idle-d": () => [report("d-plain")],
  "bind-4": () => [work("s4-start", "start", "issue-10"), work("s4-show", "show")],
  "replay": () => [bash(`node ${path.join(here, "replay.mjs")} ${known.d} ${known.retired} ${known.s1}`)],
  "resumed-3": () => [work("s3-resumed-show", "show"), work("s3-resumed-start", "start", "issue-3"), work("s3-resumed-show-bound", "show")],
  "tui-bind": () => [work("tui-start", "start", "issue-9"), work("tui-show", "show")],
  "tui-resumed": () => [work("tui-resumed-show", "show"), work("tui-resumed-start", "start", "issue-9")],
  "tui-elsewhere": () => [report("tui-elsewhere")],
  "bg-delegate": () => [delegate("bg-child", true)],
  "bg-child": () => [report("bg-child", 8000)],
};
const toolRequests = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const lastUser = messages.findLastIndex((message) => message.role === "user");
  const content = JSON.stringify(messages[lastUser]?.content ?? "");
  const label = content.match(/PROBE:([a-z0-9-]+)/)?.[1] ?? null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const step = messages.slice(lastUser + 1).filter((message) => message.role === "tool").length;
  // A title request carries no tools; only a turn's own requests count.
  const count = tools.length ? (toolRequests.get(label) ?? 0) + 1 : 0;
  if (tools.length) toolRequests.set(label, count);
  if (label === "skills" && tools.length) {
    // Which skills OpenCode offers this session, from where: discovery evidence.
    const offered = JSON.stringify([payload.tools, messages.filter((message) => message.role === "system")]);
    trace("skills", { tools, mentions: [...offered.matchAll(/.{0,160}(dashpot-issue-work|Not Dashpot's skill).{0,160}/g)].map((match) => match[0]) });
  }
  const sequence = (label && sequences[label]?.()) || [];
  const tool = tools.length ? sequence[step] : undefined;
  trace("model.request", { label, step, tool: tool?.name ?? null, count, titled: tools.length === 0 });
  if (label === "retry" && count === 1) {
    res.writeHead(503, { "content-type": "application/json", "retry-after-ms": "3000" });
    res.end(JSON.stringify({ error: { message: "fixture retry", type: "server_error" } }));
    return;
  }
  if (label === "refused" && tools.length) {
    // A request the provider refuses outright: OpenCode does not retry it.
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: "fixture refusal", type: "invalid_request_error" } }));
    return;
  }
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (tool) chunk({ role: "assistant", tool_calls: [{ index: 0, id: `call_${label}_${step}_${count}`, type: "function", function: { name: tool.name, arguments: JSON.stringify(tool.arguments) } }] });
  else chunk({ role: "assistant", content: tools.length ? "Fixture complete." : "Fixture title" });
  chunk({}, tool ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});
const opencodeConfig = JSON.stringify({
  $schema: "https://opencode.ai/config.json", model: "fixture/fixture", small_model: "fixture/fixture",
  enabled_providers: ["fixture"],
  provider: { fixture: { npm: "@ai-sdk/openai-compatible", name: "Local fixture", options: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", limit: { context: 16000, output: 2000 }, tool_call: true } } } },
  permission: "allow", share: "disabled", snapshot: false, autoupdate: false, lsp: false,
}, null, 2);

// --- Observation -------------------------------------------------------------

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, { cwd: options.cwd ?? fixture, env: options.env ?? env, encoding: "utf8", timeout: 60000 });
  return { status: result.status, stdout: retained(result.stdout ?? ""), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const integrate = (label, args, options = {}) => trace("integrate", { label, args, ...run(dashpot, ["integrate", ...args], options) });
// What a person's dashboard reads: the headless snapshot of the Project.
const observe = (label) => {
  const result = run(dashpot, ["--json"]);
  let snapshot = null;
  try { snapshot = JSON.parse(result.stdout); } catch {}
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((project) => project.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: String(message).slice(0, 400) }));
  return trace("observation", { label, error: snapshot ? null : result.stderr, runs, diagnostics });
};
// What Cleanup says about one linked Worktree.
const check = (label, worktree) => {
  const result = run(dashpot, ["worktree", "check", worktree, "--json"]);
  let report = null;
  try { report = JSON.parse(result.stdout); } catch {}
  return trace("cleanup", { label, worktree, status: result.status, report: report ?? result.stdout.slice(0, 2000), stderr: report ? undefined : result.stderr });
};
// Every hook and publisher record in the fixture's stores, by file.
const stateFiles = (label) => {
  const files = {};
  const walk = (dir) => {
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) { if (entry.name !== "events") walk(full); } else if (entry.name.endsWith(".json")) {
        try { files[full] = JSON.parse(readFileSync(full, "utf8")); } catch {}
      }
    }
  };
  for (const worktree of [fixture, sibling, tuiTree]) walk(path.join(worktree, ".dashpot", "state"));
  walk(env.DASHPOT_STATE_DIR);
  return trace("state", { label, files });
};
// Every Runtime Event the fixture's Dashpot processes recorded.
const eventLog = () => {
  const events = [];
  for (const directory of [...[fixture, sibling, tuiTree].map((worktree) => path.join(worktree, ".dashpot", "state", "events")), path.join(env.XDG_STATE_HOME, "dashpot", "events")]) {
    let names = [];
    try { names = readdirSync(directory); } catch { continue; }
    for (const name of names) {
      for (const line of readFileSync(path.join(directory, name), "utf8").split("\n")) {
        if (!line) continue;
        const flat = {};
        const merge = (value) => { for (const [key, item] of Object.entries(value)) { if (item && typeof item === "object" && !Array.isArray(item)) merge(item); else flat[key] = item; } };
        try { merge(JSON.parse(line)); } catch { continue; }
        events.push(flat);
      }
    }
  }
  return events;
};
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(50); }
  throw new Error(`Timed out: ${label}`);
};
// Every process whose environment names the fixture configuration, so the
// operator's own sessions are never observed or signalled.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`XDG_CONFIG_HOME=${env.XDG_CONFIG_HOME}\0`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const processes = (label) => trace("processes", { label, processes: fixtureProcesses().map(({ pid, ppid, comm, cmdline }) => ({ pid, ppid, comm, cmdline })) });
// Helper processes, sampled while the run lasts: their parent is the process
// that loaded the plugin. And when each hook or publisher record first
// appeared, for publication latency.
const helpers = new Map();
const seen = new Set();
const sampler = setInterval(() => {
  for (const worktree of [fixture, sibling, tuiTree]) {
    for (const store of ["sessions", path.join("sessions", "opencode")]) {
      const directory = path.join(worktree, ".dashpot", "state", store);
      let names = [];
      try { names = readdirSync(directory).filter((name) => name.endsWith(".json")); } catch { continue; }
      for (const name of names) {
        const file = path.join(directory, name);
        let record;
        try { record = JSON.parse(readFileSync(file, "utf8")); } catch { continue; }
        // A publisher record is new for each generation it makes active.
        const key = `${file}:${record.active ?? ""}`;
        if (seen.has(key) || (record.backend && !record.active)) continue;
        seen.add(key);
        trace("record.seen", { file, pid: record.backend?.pid ?? record.sessionProcess?.pid ?? null, generation: record.active ?? null, state: record.state ?? null });
      }
    }
  }
  for (const entry of fixtureProcesses()) {
    if (!entry.cmdline.includes("dashpot-opencode-hook") || helpers.has(entry.pid)) continue;
    let parent = null;
    try { parent = describe(entry.ppid); } catch {}
    helpers.set(entry.pid, { pid: entry.pid, ppid: entry.ppid, parentComm: parent?.comm ?? null, parentCmdline: parent?.cmdline ?? null, seenAt: Date.now() });
  }
}, 25);

// --- Backends and clients ------------------------------------------------------

// OpenCode's own session events, from a backend's global event stream.
const subscribe = (backend) => {
  const controller = new AbortController();
  (async () => {
    try {
      const response = await fetch(backend.url + "/global/event", { signal: controller.signal });
      const decoder = new TextDecoder();
      let buffer = "";
      for await (const chunk of response.body) {
        buffer += decoder.decode(chunk, { stream: true });
        let at;
        while ((at = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, at);
          buffer = buffer.slice(at + 2);
          let event;
          try { event = JSON.parse(block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5)).join("")); } catch { continue; }
          const payload = event.payload ?? event;
          const properties = payload.properties ?? {};
          if (!/^session\.(status|created|deleted|idle)$|^server\.instance\.disposed$/.test(payload.type ?? "")) continue;
          trace("native", { backend: backend.name, directory: event.directory ?? null, type: payload.type,
            sessionID: properties.sessionID ?? properties.info?.id ?? null, status: properties.status?.type ?? null,
            parentID: properties.info?.parentID ?? null });
        }
      }
    } catch {}
  })();
  return controller;
};
const backends = [];
const serve = async (name, extra = {}) => {
  const child = spawn("opencode", ["serve", "--hostname", "127.0.0.1", "--port", "0"], { cwd: fixture, env: { ...env, ...extra }, stdio: ["ignore", "pipe", "pipe"] });
  let output = "";
  child.stdout.on("data", (chunk) => { output += chunk; });
  child.stderr.on("data", (chunk) => { output += chunk; });
  const backend = { name, child, pid: child.pid, url: null, exited: null };
  child.on("exit", (code, signal) => { backend.exited = { code, signal }; trace("backend.exit", { name, pid: child.pid, code, signal }); });
  await waitFor(() => (backend.url = output.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0] ?? null) || backend.exited, `${name} listening`, 30000);
  assert(backend.url, `${name} did not start: ${output.slice(-2000)}`);
  backend.events = subscribe(backend);
  backends.push(backend);
  trace("backend.start", { name, pid: child.pid, process: describe(child.pid), inherited: Object.keys(extra) });
  return backend;
};
const stop = async (backend, signal) => {
  const started = Date.now();
  const exited = backend.exited ? Promise.resolve() : once(backend.child, "exit");
  backend.child.kill(signal);
  await exited;
  backend.events.abort();
  trace("backend.stopped", { name: backend.name, pid: backend.pid, signal, ms: Date.now() - started });
};
const api = async (backend, method, route, data, directory = fixture) => {
  const response = await fetch(backend.url + route, { method,
    headers: { "content-type": "application/json", "x-opencode-directory": directory },
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(90000) });
  const raw = await response.text();
  assert(response.ok, `${method} ${route}: ${response.status} ${raw.slice(0, 700)}`);
  return raw ? JSON.parse(raw) : null;
};
const session = async (backend, title, directory = fixture) => {
  const created = await api(backend, "POST", "/session", { title }, directory);
  trace("session", { backend: backend.name, title, sessionID: created.id, directory: created.directory, parentID: created.parentID ?? null });
  return created.id;
};
const prompt = async (backend, id, label, directory = fixture) => {
  const started = Date.now();
  const reply = await api(backend, "POST", `/session/${id}/message`, { model: { providerID: "fixture", modelID: "fixture" }, parts: [{ type: "text", text: `PROBE:${label}` }] }, directory);
  trace("turn", { backend: backend.name, sessionID: id, label, ms: Date.now() - started, error: reply?.info?.error?.name ?? null });
};
// A client process: an attached CLI request, or a TUI on a pseudo-terminal.
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007\u001b]*(\u0007|\u001b\\)/g, "").replace(/\u001b[()][A-Z0-9]/g, "");
const clients = [];
const client = (name, args, { terminal = false, cwd = fixture } = {}) => {
  const child = terminal
    ? spawn("script", ["-qfec", ["opencode", ...args].join(" "), "/dev/null"], { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] })
    : spawn("opencode", args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  const state = { name, child, exited: null, output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.stderr.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.on("exit", (code, signal) => { state.exited = { code, signal, at: Date.now() }; trace("client.exit", { name, code, signal, tail: terminal ? null : state.output.slice(-300) }); });
  clients.push(state);
  trace("client.spawn", { name, args, cwd, terminal, pid: child.pid });
  return state;
};
// The `opencode` process a terminal client runs, below its `script`.
const opencodeOf = (state) => {
  const all = fixtureProcesses();
  const below = (entry) => {
    for (let current = entry; current;) {
      if (current.ppid === state.child.pid) return true;
      current = all.find((other) => other.pid === current.ppid);
    }
    return false;
  };
  return all.find((entry) => entry.comm === "opencode" && below(entry)) ?? null;
};
// Type a prompt into a TUI, again if the TUI was not ready to take it.
const type = async (state, label) => {
  for (let attempt = 1; attempt <= 4; attempt++) {
    const before = toolRequests.get(label) ?? 0;
    state.child.stdin.write(`PROBE:${label}`);
    await delay(500);
    state.child.stdin.write("\r");
    trace("typed", { client: state.name, label, attempt });
    try { await waitFor(() => (toolRequests.get(label) ?? 0) > before, `${state.name} ${label} reached the model`, 8000); return; } catch {}
    state.child.stdin.write("\u0015");
    await delay(500);
  }
  throw new Error(`${state.name} never sent ${label}`);
};
const quit = async (state, label) => {
  const started = Date.now();
  for (let attempt = 0; attempt < 3 && !state.exited; attempt++) {
    state.child.stdin.write("\u0003");
    try { await waitFor(() => state.exited, `${state.name} quit`, 5000); } catch {}
  }
  assert(state.exited, `${state.name} did not quit`);
  trace("tui.quit", { label, client: state.name, ms: state.exited.at - started });
};
const hookRecord = (worktree, id) => {
  try { return JSON.parse(readFileSync(path.join(worktree, ".dashpot", "state", "sessions", `${id}.json`), "utf8")); } catch { return null; }
};
// End each orphaned Agent Run the way Cleanup says to.
const stopOrphans = (label, worktree) => {
  const obstacles = check(`${label}-before-stop`, worktree).report?.obstacles?.filter((item) => item.kind === "agent-run") ?? [];
  assert(obstacles.length, `${label}: Cleanup names no orphaned Agent Run to stop`);
  for (const obstacle of obstacles) {
    const key = obstacle.command?.match(/--session (\S+)/)?.[1];
    assert(key, `${label}: ${obstacle.detail}`);
    trace("work-stop", { label, ...run(dashpot, ["work", "stop", "--session", key], { cwd: worktree }) });
  }
  return check(`${label}-stopped`, worktree);
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, fixture, sibling, tuiTree, wheel,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))),
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    installedMatchesSource: exercised.every((file) => sha256(path.join(installed, file)) === sha256(path.join(checkout, "src", "dashpot", file))),
    sourceSHA256: Object.fromEntries([
      ...["run.mjs", "verify.mjs", "command.mjs", "replay.mjs", "ancestry.mjs"].map((file) => [file, path.join(here, file)]),
      ...exercised.map((file) => [`src/dashpot/${file}`, path.join(checkout, "src", "dashpot", file)]),
    ].map(([name, file]) => [name, sha256(file)])) });

  // Scenario 1: installer round trips beside unrelated configuration, plugins
  // and skills, and the status diagnostics.
  trace("scenario", { name: "installer" });
  writeFileSync(path.join(configHome, "opencode.json"), opencodeConfig);
  mkdirSync(path.join(configHome, "plugins"), { recursive: true });
  writeFileSync(path.join(configHome, "plugins", "unrelated.js"), "// Not Dashpot's.\nexport const Unrelated = async () => ({});\n");
  mkdirSync(path.join(env.HOME, ".agents", "skills", "unrelated"), { recursive: true });
  writeFileSync(path.join(env.HOME, ".agents", "skills", "unrelated", "SKILL.md"), "---\nname: unrelated\ndescription: Not Dashpot's skill.\n---\n\nUnrelated.\n");
  // A Claude Code installation whose skill OpenCode also discovers.
  mkdirSync(path.join(env.HOME, ".claude"), { recursive: true });
  integrate("claude-code", ["claude-code"]);
  const pluginFile = path.join(configHome, "plugins", "dashpot.js");
  const claudeSkill = path.join(env.HOME, ".claude", "skills", "dashpot-issue-work", "SKILL.md");
  const files = (label) => trace("files", { label,
    unrelated: Object.fromEntries([path.join(configHome, "opencode.json"), path.join(configHome, "plugins", "unrelated.js"),
      path.join(env.HOME, ".agents", "skills", "unrelated", "SKILL.md"), claudeSkill].map((file) => [file, existsSync(file) ? sha256(file) : null])),
    plugin: existsSync(pluginFile) ? sha256(pluginFile) : null,
    skill: existsSync(path.join(configHome, "skills", "dashpot-issue-work", "SKILL.md")) });
  files("before");
  integrate("install", ["opencode"]);
  integrate("status", ["opencode", "--status"]);
  files("installed");
  integrate("reinstall", ["opencode"]);
  files("reinstalled");
  integrate("remove", ["opencode", "--remove"]);
  files("removed");
  integrate("status-removed", ["opencode", "--status"]);
  // A plugin of the same name that is the user's own is refused and kept.
  writeFileSync(pluginFile, "// The user's own plugin.\nexport const Mine = async () => ({});\n");
  integrate("foreign-plugin", ["opencode"]);
  integrate("foreign-plugin-remove", ["opencode", "--remove"]);
  trace("foreign", { kept: readFileSync(pluginFile, "utf8").startsWith("// The user's own plugin.") });
  rmSync(pluginFile);
  // A helper path left by a removed installation, then repaired.
  integrate("install-again", ["opencode"]);
  const bound = readFileSync(pluginFile, "utf8");
  assert(bound.includes(JSON.stringify(helper)), "the plugin names the installed helper");
  writeFileSync(pluginFile, bound.replace(JSON.stringify(helper), JSON.stringify(path.join(root, "removed", "bin", "dashpot-opencode-hook"))));
  integrate("status-stale-helper", ["opencode", "--status"]);
  integrate("repair", ["opencode"]);
  // A release other than the measured one, a second copy of the plugin, a
  // differing Claude Code skill copy, and OPENCODE_PURE.
  const fakeDirectory = path.join(root, "fake-bin");
  mkdirSync(fakeDirectory);
  writeFileSync(path.join(fakeDirectory, "opencode"), "#!/bin/sh\necho 1.18.31\n");
  chmodSync(path.join(fakeDirectory, "opencode"), 0o755);
  integrate("status-other-release", ["opencode", "--status"], { env: { ...env, PATH: `${fakeDirectory}:${env.PATH}` } });
  mkdirSync(path.join(env.HOME, ".opencode", "plugins"), { recursive: true });
  copyFileSync(pluginFile, path.join(env.HOME, ".opencode", "plugins", "copy.js"));
  appendFileSync(claudeSkill, "\nA local edit.\n");
  integrate("status-duplicates-pure", ["opencode", "--status"], { env: { ...env, OPENCODE_PURE: "1" } });
  rmSync(path.join(env.HOME, ".opencode"), { recursive: true });
  integrate("claude-code-repair", ["claude-code"]);
  integrate("status-final", ["opencode", "--status"]);
  files("final");

  // Scenario 2: one backend, launched where another harness's claims are in
  // its environment, serving three root sessions: two in the main Worktree
  // and one in a sibling. Each starts, switches or stops its own Issue work.
  trace("scenario", { name: "shared-backend" });
  const b1 = await serve("b1", { CODEX_THREAD_ID: "inherited-codex-thread", CLAUDE_CODE_SESSION_ID: "inherited-claude-session", DASHPOT_AGENT_SESSION: "codex:inherited" });
  const s1 = known.s1 = await session(b1, "S1");
  const s2 = known.s2 = await session(b1, "S2");
  const s3 = known.s3 = await session(b1, "S3", sibling);
  await prompt(b1, s1, "skills");
  await prompt(b1, s1, "bind-1");
  await prompt(b1, s2, "bind-2");
  await prompt(b1, s3, "bind-3", sibling);
  await delay(1500);
  stateFiles("three-bound");
  observe("three-bound");
  check("sibling-live", sibling);
  const holding = prompt(b1, s1, "hold-1");
  await waitFor(() => command("s1-hold", "start"), "s1 hold started");
  await delay(1500);
  observe("s1-holding");
  await holding;
  await prompt(b1, s1, "switch-1");
  await prompt(b1, s2, "stop-2");
  await delay(1500);
  observe("switched-and-stopped");

  // Scenario 3: commands that cannot be corroborated fail safely.
  trace("scenario", { name: "refusals" });
  await prompt(b1, s2, "refusals-2");
  const pty = await api(b1, "POST", "/pty", { command: process.execPath, args: [commandScript, "pty", "0", "--", "work", "start", "issue-5"], cwd: fixture });
  await waitFor(() => command("pty"), "PTY command");
  await api(b1, "DELETE", `/pty/${pty.id}`).catch(() => {});
  await delay(1000);
  observe("refusals");

  // Scenario 4: attached clients on the sibling session: a CLI request, one
  // detached mid-command, one reattached, and a TUI attached on a
  // pseudo-terminal, then closed.
  trace("scenario", { name: "attached-clients" });
  const attachedArgs = (label) => ["run", "--attach", b1.url, "--dir", sibling, "--session", s3, "--model", "fixture/fixture", "--format", "json", `PROBE:${label}`];
  const shown = client("cli-show", attachedArgs("attached-show"));
  await waitFor(() => shown.exited, "attached CLI exit");
  const detached = client("cli-detach", attachedArgs("detach-hold"));
  await waitFor(() => command("s3-detach-hold", "start"), "detach hold started");
  detached.child.kill("SIGTERM");
  await waitFor(() => detached.exited, "detached CLI exit", 10000);
  await delay(1000);
  observe("s3-detached-mid-command");
  check("sibling-detached", sibling);
  await waitFor(() => command("s3-detach-hold"), "detach hold ended", 30000);
  await waitFor(() => hookRecord(sibling, s3)?.state === "waiting", "s3 waiting after detached turn", 30000);
  observe("s3-detached-turn-ended");
  const reattached = client("cli-reattach", attachedArgs("reattached"));
  await waitFor(() => reattached.exited, "reattached CLI exit");
  const attachedTui = client("tui-attach", ["attach", b1.url, "--dir", sibling, "--session", s3], { terminal: true });
  await delay(5000);
  await type(attachedTui, "tui-attached");
  await waitFor(() => command("s3-tui-attached-show"), "attached TUI command");
  await delay(1500);
  processes("attached-tui");
  attachedTui.child.kill("SIGTERM");
  const attachedProcess = opencodeOf(attachedTui);
  if (attachedProcess) process.kill(attachedProcess.pid, "SIGTERM");
  await waitFor(() => attachedTui.exited, "attached TUI exit", 10000);
  await delay(1500);
  observe("attached-tui-closed");
  check("sibling-attached-tui-closed", sibling);

  // Scenario 5: a native child of a bound session, then a fork of it.
  trace("scenario", { name: "child-and-fork" });
  const delegating = prompt(b1, s1, "delegate-1");
  await waitFor(() => command("child-hold", "start"), "child hold started");
  await delay(1500);
  stateFiles("child-working");
  observe("child-working");
  await delegating;
  await delay(1500);
  observe("child-finished");
  const forked = await api(b1, "POST", `/session/${s1}/fork`, {});
  known.fork = forked.id;
  trace("fork", { sessionID: forked.id, parentID: forked.parentID ?? null, of: s1 });
  await prompt(b1, forked.id, "fork");
  await delay(1500);
  observe("forked");

  // Scenario 6: retry, interrupt, and a provider refusal on the sibling session.
  trace("scenario", { name: "retry-interrupt" });
  const retrying = prompt(b1, s3, "retry", sibling);
  await waitFor(() => (toolRequests.get("retry") ?? 0) >= 1, "retry refused once");
  await delay(1000);
  stateFiles("s3-retrying");
  observe("s3-retrying");
  await retrying;
  const interrupted = prompt(b1, s3, "interrupt", sibling).catch((error) => trace("turn.error", { label: "interrupt", error: String(error).slice(0, 300) }));
  await waitFor(() => command("s3-interrupted", "start"), "interrupt hold started", 30000);
  await delay(1000);
  observe("s3-before-abort");
  const aborted = Date.now();
  await api(b1, "POST", `/session/${s3}/abort`, {}, sibling);
  await interrupted;
  await waitFor(() => hookRecord(sibling, s3)?.state === "waiting", "s3 waiting after abort", 20000);
  trace("aborted", { ms: Date.now() - aborted, commandEnded: Boolean(command("s3-interrupted")) });
  observe("s3-aborted");
  await prompt(b1, s3, "refused", sibling).catch((error) => trace("turn.error", { label: "refused", error: String(error).slice(0, 300) }));
  await delay(2000);
  observe("s3-refused");

  // Scenario 7: the main instance's plugin replaced, removed and restored
  // while its backend and sessions live on.
  trace("scenario", { name: "plugin-replacement" });
  known.retired = command("s1-switch", "start").env.DASHPOT_OPENCODE_GENERATION;
  await api(b1, "POST", "/instance/dispose", {});
  await delay(2500);
  stateFiles("main-disposed");
  observe("main-disposed");
  await prompt(b1, s1, "after-replace");
  await delay(1500);
  stateFiles("main-replaced");
  observe("main-replaced");
  integrate("remove-live", ["opencode", "--remove"]);
  await api(b1, "POST", "/instance/dispose", {});
  await delay(2500);
  await prompt(b1, s1, "unplugged");
  await delay(1500);
  observe("main-unplugged");
  integrate("restore", ["opencode"]);
  await api(b1, "POST", "/instance/dispose", {});
  await prompt(b1, s1, "restored");
  await delay(1500);
  observe("main-restored");
  // The sibling instance's plugin replaced too: its session reads unknown
  // until its next publication, and Cleanup says why.
  await api(b1, "POST", "/instance/dispose", {}, sibling);
  await delay(2500);
  stateFiles("sibling-disposed");
  observe("sibling-disposed");
  check("sibling-disposed", sibling);

  // Scenario 8: the helper missing, then stalled, then back.
  trace("scenario", { name: "unavailable-helper" });
  const parked = `${helper}.parked`;
  renameSync(helper, parked);
  integrate("status-missing-helper", ["opencode", "--status"]);
  await prompt(b1, s2, "missing-helper");
  writeFileSync(helper, "#!/bin/sh\nexec sleep 30\n");
  chmodSync(helper, 0o755);
  await prompt(b1, s2, "stalled-helper");
  renameSync(parked, helper);
  await delay(4000);
  await prompt(b1, s2, "helper-back");
  await delay(1500);
  observe("helper-back");

  // Scenario 9: deletion, from the backend and from the CLI, then late and
  // duplicate publications replayed through the installed helper.
  trace("scenario", { name: "deletion-and-replay" });
  known.d = await session(b1, "D");
  await prompt(b1, known.d, "idle-d");
  await delay(1000);
  await api(b1, "DELETE", `/session/${s1}`);
  await delay(2500);
  stateFiles("s1-deleted");
  observe("s1-deleted");
  // Bound sessions deleted by `opencode session delete`, which loads the
  // plugin in its own process for the directory it runs in: a sibling
  // session from the sibling, and the main Worktree's fork from the sibling.
  const s4 = known.s4 = await session(b1, "S4", sibling);
  await prompt(b1, s4, "bind-4", sibling);
  await delay(1000);
  check("sibling-s4-bound", sibling);
  const deleting = client("cli-delete-here", ["session", "delete", s4], { cwd: sibling });
  await waitFor(() => deleting.exited, "CLI delete exit", 30000);
  await delay(2500);
  stateFiles("s4-deleted-by-cli");
  observe("s4-deleted-by-cli");
  const deleted = check("sibling-s4-deleted-by-cli", sibling);
  // Its run, still bound to the backend that serves no such session now:
  // the command Cleanup names for it, tried while that backend runs.
  const s4Run = deleted.report?.obstacles?.find((item) => item.kind === "agent-run" && /issue-10/.test(item.detail));
  const s4Key = s4Run?.command?.match(/--session (\S+)/)?.[1];
  assert(s4Key, `the deleted session's run names no stop command: ${s4Run?.detail}`);
  trace("work-stop", { label: "s4-deleted-by-cli", ...run(dashpot, ["work", "stop", "--session", s4Key], { cwd: sibling }) });
  const elsewhereDelete = client("cli-delete-elsewhere", ["session", "delete", forked.id], { cwd: sibling });
  await waitFor(() => elsewhereDelete.exited, "CLI delete exit", 30000);
  await delay(2500);
  stateFiles("fork-deleted-by-cli-elsewhere");
  observe("fork-deleted-by-cli-elsewhere");
  await prompt(b1, s2, "replay");
  await delay(1000);
  observe("replayed");

  // Scenario 10: the shared backend ended without disposing its instances.
  // Its bound runs are orphaned and its sessions gone; a resumed session
  // continues Issue work only by `work start`.
  trace("scenario", { name: "backend-replacement" });
  await stop(b1, "SIGTERM");
  await delay(1500);
  stateFiles("b1-stopped");
  observe("b1-stopped");
  check("sibling-b1-stopped", sibling);
  const b2 = await serve("b2");
  await prompt(b2, s3, "resumed-3", sibling);
  await delay(1500);
  observe("s3-resumed");
  await stop(b2, "SIGKILL");
  await delay(1000);
  observe("b2-killed");
  check("sibling-b2-killed", sibling);
  stopOrphans("sibling-orphan", sibling);
  observe("s3-orphan-stopped");

  // Scenario 11: the ordinary local TUI in its own linked Worktree: startup,
  // a bound turn, a `!` shell command, quitting, resuming, resuming from
  // another Worktree, and a terminal closed under it.
  trace("scenario", { name: "local-tui" });
  const tuiStarted = Date.now();
  const tui = client("tui", [], { terminal: true, cwd: tuiTree });
  await waitFor(() => opencodeOf(tui), "TUI process", 30000);
  const tuiPid = opencodeOf(tui).pid;
  // OpenCode starts the TUI's instance, and with it the plugin, when the TUI
  // first asks for it; the TUI is typed into once its screen has settled.
  trace("tui.started", { pid: tuiPid, ms: Date.now() - tuiStarted });
  await delay(6000);
  await type(tui, "tui-bind");
  await waitFor(() => command("tui-show"), "TUI bound");
  const tuiSession = known.tui = command("tui-start", "start").env.DASHPOT_OPENCODE_SESSION_ID;
  await waitFor(() => hookRecord(tuiTree, tuiSession)?.state === "waiting", "TUI turn ended", 30000);
  trace("tui.session", { sessionID: tuiSession, pid: tuiPid });
  tui.child.stdin.write("!");
  await delay(300);
  tui.child.stdin.write(`node ${commandScript} tui-bang 0 -- work show`);
  await delay(500);
  tui.child.stdin.write("\r");
  try { await waitFor(() => command("tui-bang"), "TUI shell command", 20000); } catch (error) { trace("tui.bang-missing", { screen: tui.output.slice(-1500) }); }
  processes("tui");
  stateFiles("tui-bound");
  observe("tui-bound");
  check("tui-live", tuiTree);
  await quit(tui, "ctrl-c");
  await delay(1500);
  stateFiles("tui-quit");
  observe("tui-quit");
  check("tui-quit", tuiTree);
  const resumed = client("tui-resumed", ["--session", tuiSession], { terminal: true, cwd: tuiTree });
  await waitFor(() => opencodeOf(resumed), "resumed TUI process", 30000);
  await delay(5000);
  await type(resumed, "tui-resumed");
  await waitFor(() => command("tui-resumed-start"), "resumed TUI bound");
  await delay(1500);
  observe("tui-resumed");
  await quit(resumed, "resumed-ctrl-c");
  await delay(1500);
  observe("tui-resumed-quit");
  // Resumed from the main Worktree, the session stays where it was created.
  const elsewhere = client("tui-elsewhere", ["--session", tuiSession], { terminal: true, cwd: fixture });
  await waitFor(() => opencodeOf(elsewhere), "elsewhere TUI process", 30000);
  await delay(5000);
  await type(elsewhere, "tui-elsewhere");
  await waitFor(() => command("tui-elsewhere"), "elsewhere command");
  await delay(1500);
  stateFiles("tui-elsewhere");
  observe("tui-elsewhere");
  check("tui-elsewhere", tuiTree);
  // A terminal closed under the TUI.
  const hungUp = opencodeOf(elsewhere);
  const hangup = Date.now();
  process.kill(hungUp.pid, "SIGHUP");
  await waitFor(() => elsewhere.exited, "elsewhere TUI hangup", 15000);
  trace("tui.quit", { label: "sighup", client: elsewhere.name, ms: elsewhere.exited.at - hangup });
  await delay(1500);
  stateFiles("tui-hangup");
  observe("tui-hangup");
  check("tui-hangup", tuiTree);
  stopOrphans("tui-orphan", tuiTree);

  // Scenario 12: a background child, which OpenCode runs only under an
  // experimental flag, outliving its parent's turn.
  trace("scenario", { name: "background-child" });
  const b3 = await serve("b3", { OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS: "true" });
  const g = known.g = await session(b3, "G");
  await prompt(b3, g, "bg-delegate");
  await waitFor(() => command("bg-child", "start"), "background child started", 30000);
  await delay(1500);
  stateFiles("background-working");
  observe("background-working");
  await waitFor(() => command("bg-child"), "background child ended", 30000);
  await delay(3000);
  observe("background-finished");
  await stop(b3, "SIGTERM");
  await delay(1000);
  observe("b3-stopped");
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: String(error?.stack ?? error) });
  console.error(error);
} finally {
  clearInterval(sampler);
  trace("helpers", { processes: [...helpers.values()] });
  // The helper's own record of each run: outcomes by kind, the slowest run,
  // and every outcome that did not succeed.
  const outcomes = eventLog().filter((event) => String(event["dashpot.process.kind"] ?? "").startsWith("hook:opencode"));
  const summary = {};
  for (const event of outcomes) {
    const entry = summary[event["dashpot.process.kind"]] ??= { runs: 0, results: {}, slowestSeconds: 0 };
    if (event["event.name"] === "process.end") {
      entry.runs += 1;
      entry.slowestSeconds = Math.max(entry.slowestSeconds, event["dashpot.duration_seconds"] ?? 0);
    }
    if (event["event.name"] === "hook.outcome") entry.results[event["dashpot.outcome.result"]] = (entry.results[event["dashpot.outcome.result"]] ?? 0) + 1;
  }
  trace("events", { summary, unsuccessful: outcomes.filter((event) => event["event.name"] === "hook.outcome" && event["dashpot.outcome.result"] !== "succeeded")
    .map((event) => ({ time: event.time ?? null, kind: event["dashpot.process.kind"], result: event["dashpot.outcome.result"], error: event["error.type"] ?? null })) });
  for (const state of clients) if (!state.exited) state.child.kill("SIGKILL");
  for (const backend of backends) if (!backend.exited) await stop(backend, "SIGTERM").catch(() => {});
  await delay(1000);
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
  process.exit(0);
}
