// Sandbox run for Issue #639: resumes a real Codex session through the
// interactive `codex resume` entry point with the command the execute-issues
// skill gives a person, and has a sandboxed worker of that session run one
// full Worker cycle in its own linked Worktree. Drives a pinned Codex CLI
// against a loopback Responses API fixture, with an isolated CODEX_HOME whose
// daemon updater is off, in a disposable uv project outside the system
// temporary directory, whose tracked pre-commit hook runs `uv run --locked
// pre-commit`, and whose `origin` is a bare repository served by
// `git http-backend` on loopback.
//
// A seed terminal starts the session, and its lead runs the skill's three
// checks. The session is then resumed, one terminal at a time, with:
//   - the skill's command: the lead checks again, adds two Worktrees, and
//     spawns two v2 workers, one running the cycle as it is and one with
//     every refused cache directory moved inside the Worktree Root by an
//     environment override;
//   - the skill's command and `--add-dir` for the cache directory instead;
//   - `--sandbox read-only` with the same `--add-dir` options;
//   - the skill's command under `-a on-request`, where the lead and a worker
//     each try a write outside every writable root, then the same write with
//     escalation requested.
// Codex's own session records give the sandbox each thread ran under, and
// its TUI log the app-server mode each terminal chose. Each step's model
// requests, reports and screens are recorded as a metadata-only trace.
//
//   node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [expected version]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.160.0";
// A fixture below a harness session would run inside that session's own
// sandbox, if it has one, and its processes would join that session's tree.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const uvBinary = execFileSync("sh", ["-c", "command -v uv"], { encoding: "utf8" }).trim();
assert(path.isAbsolute(uvBinary), "uv is on PATH");

// `workspace-write` makes `/tmp` and TMPDIR writable by default, so the
// fixture lives under `/var/tmp`, as a person's checkout lives outside them,
// and the sandbox keeps its default temporary directories.
const root = mkdtempSync(path.join("/var/tmp", "dashpot-codex-639-"));
console.log(`Isolated fixture: ${root}`);
const main = path.join(root, "repository");
const worktreeRoot = path.join(root, "repository.worktrees");
const remote = path.join(root, "remote.git");
// A directory outside every writable root: the control write.
const outside = path.join(root, "outside");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's root never
// enter the trace; the fixture's own home directory appears as `$HOME`.
const home = os.homedir();
const fixtureHome = path.join(root, "home");
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
// A terminal's partial redraw can break a path, as `/vr/tmp/<fixture>`, so
// the fixture root's own name is replaced wherever it is left.
const clean = (text) => String(text).replaceAll(fixtureHome, "$HOME").replaceAll(root, "$ROOT").replaceAll(path.basename(root), "<fixture>")
  .replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~").replace(hostName, "<host>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, clean(JSON.stringify(record)) + "\n");
  return record;
};
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const stripAnsi = (text) => text.replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "").replace(/\u001b[()][0-9A-Za-z]|\u001b[=>78]/g, "");

// The pinned release runs through a fixture-local `codex` on PATH, beside
// the operator's uv, which the fixture's gate and hook run.
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
symlinkSync(binary, path.join(fixtureBin, "codex"));
symlinkSync(uvBinary, path.join(fixtureBin, "uv"));
// No XDG directory and no TMPDIR is set: every tool keeps its default
// location under the fixture's HOME or in `/tmp`.
const env = {
  PATH: `${fixtureBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: fixtureHome,
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  LANG: "C.UTF-8",
};
for (const dir of [main, worktreeRoot, outside, env.HOME, path.join(env.HOME, ".cache"), env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable repository: a uv project with no package of its own, one
// locked development dependency, a pre-commit configuration whose one hook
// is local, and a tracked hook that runs it as this Repository's
// `.githooks/pre-commit` does.
const git = (...args) => execFileSync("git", ["-C", main, ...args], { env, stdio: "pipe", encoding: "utf8" });
git("init", "--initial-branch=main");
writeFileSync(path.join(main, "README.md"), "Disposable fixture.\n");
writeFileSync(path.join(main, ".gitignore"), ".venv/\n");
writeFileSync(path.join(main, "pyproject.toml"), `[project]
name = "fixture"
version = "0"
requires-python = ">=3.10"

[dependency-groups]
dev = ["pre-commit"]

[tool.uv]
package = false
exclude-newer = "2026-09-01T00:00:00Z"
`);
writeFileSync(path.join(main, ".pre-commit-config.yaml"), `repos:
  - repo: local
    hooks:
      - id: readme-names-fixture
        name: README names the fixture
        language: system
        entry: grep -q Disposable
        files: ^README\\.md$
`);
mkdirSync(path.join(main, ".githooks"));
writeFileSync(path.join(main, ".githooks", "pre-commit"), `#!/bin/sh
set -e
hook_dir="$(cd "$(dirname "$0")" && pwd)"
exec uv run --locked pre-commit hook-impl \\
    --config=.pre-commit-config.yaml --hook-type=pre-commit --hook-dir "$hook_dir" \\
    -- "$@"
`, { mode: 0o755 });
// The lock is resolved outside the sandbox, against the cutoff the project
// names, with a cache of the runner's own; the fixture's HOME keeps no uv
// cache.
const runnerCache = path.join(root, "runner-uv-cache");
execFileSync("uv", ["lock"], { cwd: main, env: { ...env, UV_CACHE_DIR: runnerCache }, stdio: "pipe" });
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("config", "core.hooksPath", ".githooks");
git("config", "user.name", "Fixture");
git("config", "user.email", "fixture@example.invalid");
const ledgerOf = (label) => path.join(main, ".dashpot", "state", "skills", "dashpot-execute-issues", "arcs", "fixture", "workers", `${label}.md`);
mkdirSync(path.join(main, ".dashpot", "state"), { recursive: true });
writeFileSync(path.join(main, ".dashpot", "state", ".gitignore"), "*\n");
execFileSync("git", ["init", "--bare", "--initial-branch=main", remote], { env, stdio: "pipe" });
execFileSync("git", ["-C", remote, "config", "http.receivepack", "true"], { env, stdio: "pipe" });
git("push", remote, "main");

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
const raw = async (req) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks);
};

// The disposable remote: `git http-backend` behind a loopback HTTP server,
// so a push is a network connection, as a push to a forge is, while the
// remote's own writes happen here, outside the sandbox.
const remoteServer = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const input = await raw(req);
  const cgi = spawn("git", ["http-backend"], { env: { PATH: env.PATH, HOME: env.HOME, GIT_PROJECT_ROOT: root, GIT_HTTP_EXPORT_ALL: "1",
    REQUEST_METHOD: req.method, PATH_INFO: url.pathname, QUERY_STRING: url.search.slice(1), CONTENT_TYPE: req.headers["content-type"] ?? "",
    CONTENT_LENGTH: String(input.length), HTTP_CONTENT_ENCODING: req.headers["content-encoding"] ?? "", GIT_PROTOCOL: req.headers["git-protocol"] ?? "",
    REMOTE_ADDR: "127.0.0.1" }, stdio: ["pipe", "pipe", "pipe"] });
  cgi.stdin.end(input);
  const out = [];
  cgi.stdout.on("data", (chunk) => out.push(chunk));
  cgi.stderr.on("data", () => {});
  await once(cgi, "close");
  const response = Buffer.concat(out);
  const crlf = response.indexOf("\r\n\r\n");
  const split = crlf >= 0 ? crlf : response.indexOf("\n\n");
  const separator = crlf >= 0 ? 4 : 2;
  const headers = response.subarray(0, split).toString("utf8").split(/\r?\n/).map((line) => [line.slice(0, line.indexOf(":")), line.slice(line.indexOf(":") + 1).trim()]);
  const statusLine = headers.find(([name]) => name.toLowerCase() === "status")?.[1] ?? "200 OK";
  const status = Number(statusLine.split(" ")[0]);
  // The runner's own fetch, before the environment record, is setup.
  if (records.some((record) => record.kind === "environment")) trace("remote.request", { method: req.method, path: url.pathname, service: url.searchParams.get("service"), status });
  res.writeHead(status, Object.fromEntries(headers.filter(([name]) => name && name.toLowerCase() !== "status")));
  res.end(response.subarray(split + separator));
});
git("remote", "add", "origin", `${remoteServer.url}/remote.git`);
// The fetch runs asynchronously: this process serves the remote.
const fetched = spawn("git", ["-C", main, "fetch", "origin"], { env, stdio: "ignore" });
const [fetchStatus] = await once(fetched, "exit");
assert.equal(fetchStatus, 0, "the fixture fetches its loopback remote");

// The fixture model is scripted per directive, as in the codex-637 run. The
// latest input item that is not a tool call and carries `SPIKE:<label>`
// selects the plan `plans[label]`; the number of tool outputs after that item,
// polls aside, selects the step. When the plan runs out, the model answers
// `DONE:<label>`. A command still running when its call yields is polled
// with `write_stdin` until it exits.
const checksScript = path.join(here, "checks.mjs");
const cycleScript = path.join(here, "cycle.mjs");
const uvOverride = `UV_CACHE_DIR=${path.join(worktreeRoot, ".cache", "uv")}`;
const cacheOverrides = [uvOverride, `PRE_COMMIT_HOME=${path.join(worktreeRoot, ".cache", "pre-commit")}`];
const nameValue = (pair) => [pair.slice(0, pair.indexOf("=")), pair.slice(pair.indexOf("=") + 1)];
const grantWorkers = ["worker-default", "worker-uv", "worker-override"];
const plans = {
  seed: [{ checks: [] }],
  "lead-grant": [{ checks: grantWorkers }, { spawn: ["worker_default", "worker-default"] },
    { spawn: ["worker_uv", "worker-uv"] }, { spawn: ["worker_override", "worker-override"] }],
  "worker-default": [{ cycle: [] }],
  // uv's cache moved alone, so the next refusal shows.
  "worker-uv": [{ cycle: [uvOverride] }],
  "worker-override": [{ cycle: cacheOverrides }],
  "lead-adddir": [{ checks: ["worker-adddir"] }, { spawn: ["worker_adddir", "worker-adddir"] }],
  "worker-adddir": [{ cycle: [] }],
  "lead-env": [{ checks: ["worker-env"] }, { spawn: ["worker_env", "worker-env"] }],
  "worker-env": [{ cycle: [] }],
  "lead-readonly": [{ checks: [] }],
  "lead-ask": [{ outside: "plain" }, { outside: "escalated" }, { spawn: ["worker_ask", "worker-ask"] }],
  "worker-ask": [{ outside: "plain" }, { outside: "escalated" }],
};
const markerPattern = /(SPIKE|DONE):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const outputText = (item) => typeof item.output === "string" ? item.output : JSON.stringify(item.output ?? "");
const reports = new Map();
const modelRequests = [];
const done = new Set();
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
// The sandbox, approval and permission text Codex puts in a request, by tag.
const contextTags = /<(sandbox_mode|network_access|writable_roots|approval_policy|permissions instructions|cwd)>([\s\S]*?)<\/\1>/g;
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const text = (await raw(req)).toString("utf8");
  const payload = text ? JSON.parse(text) : {};
  if (!url.pathname.endsWith("/responses")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "not_found", message: "fixture" } }));
    return;
  }
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const input = payload.input ?? [];
  let directiveAt = -1;
  let label = null;
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].filter((match) => match[1] === "SPIKE");
    if (found.length) { directiveAt = index; label = found.at(-1)[2]; }
  });
  for (const item of input.filter(isCallOutput)) {
    for (const match of outputText(item).matchAll(/(CHECKS|CYCLE) (\{.*\})/g)) {
      const report = parseJson(match[2]);
      const key = `${match[1]}:${report?.label}`;
      if (report && !reports.has(key)) { reports.set(key, report); trace(match[1].toLowerCase(), { thread, report }); }
    }
  }
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name, nested]) : [[null, tool.name ?? tool.type, tool]]);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  // The terminal also sends each prompt to side threads, offered no shell;
  // they get text only.
  const sideThread = !offered("exec_command");
  const execParams = Object.keys(offered("exec_command")?.[2]?.parameters?.properties ?? {}).sort();
  const v2 = Boolean(offered("list_agents"));
  const callNames = new Map(input.filter((item) => item.type === "function_call").map((item) => [item.call_id, item.name]));
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const planned = outputs.filter((item) => callNames.get(item.call_id) !== "write_stdin");
  const latestOutput = outputs.at(-1);
  const running = latestOutput && /Process running with session ID (\d+)/.exec(outputText(latestOutput));
  const plan = label && !sideThread ? plans[label] ?? [] : [];
  const step = running ? { poll: Number(running[1]) } : plan[planned.length] ?? null;
  const toolCall = (name, args) => {
    const tool = offered(name);
    return tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  const exec = (cmd, extra = {}) => toolCall("exec_command", { cmd, login: false, yield_time_ms: 30000, ...extra });
  let item = null;
  let action = null;
  if (step?.poll) {
    action = "write_stdin";
    item = toolCall("write_stdin", { session_id: step.poll, chars: "", yield_time_ms: 30000 });
  } else if (step?.checks) {
    action = "exec_command";
    item = exec(`node ${checksScript} ${label} ${main} ${worktreeRoot} ${outside} ${step.checks.join(" ")}`.trim());
  } else if (step?.cycle) {
    action = "exec_command";
    // A worker reaches its Worktree by a per-command `cd`, as a brief tells it to.
    item = exec(`cd ${path.join(worktreeRoot, label)} && node ${cycleScript} ${label} ${main} ${ledgerOf(label)} ${step.cycle.join(" ")}`.trim());
  } else if (step?.outside) {
    action = `exec_command:${step.outside}`;
    const cmd = `touch ${outside}/${step.outside}-${label}`;
    item = exec(cmd, step.outside === "escalated" ? { sandbox_permissions: "require_escalated", justification: "Fixture: write outside every writable root" } : {});
  } else if (step?.spawn) {
    const [taskName, child] = step.spawn;
    action = "spawn_agent";
    item = toolCall("spawn_agent", v2 ? { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" } : { message: `SPIKE:${child}` });
  }
  if (label && !sideThread && !item && !step) done.add(label);
  const contexts = [...new Map(input.filter((entry) => !isCall(entry)).flatMap((entry) => [...JSON.stringify(entry).matchAll(contextTags)])
    .map((match) => [match[1], match[2].replace(/\\n/g, " ").replace(/\s+/g, " ").trim().slice(0, 300)])).entries()];
  const request = trace("model.request", { thread, label, step: planned.length, polls: outputs.length - planned.length, inputItems: input.length, directiveAt,
    action, missing: Boolean(step && !item), v2, sideThread, execParams, contexts: Object.fromEntries(contexts),
    lastOutput: latestOutput ? clean(outputText(latestOutput)).replace(/\s+/g, " ").slice(-700) : null });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// The model catalog: `fixture-v2` declares multi-agent v2, so the lead and
// its workers get the collaboration tools.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));

// The configuration sets no sandbox: the seed runs Codex's default for a
// trusted project, and each resume sets its own on the command line.
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-v2"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
model_provider = "fixture"
check_for_update_on_startup = false

[features]
multi_agent = true
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

[projects."${main}"]
trust_level = "trusted"
`);
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
const daemonPidPath = path.join(env.CODEX_HOME, "app-server-daemon", "daemon.pid");
const daemonPid = () => { const pid = parseJson(existsSync(daemonPidPath) ? readFileSync(daemonPidPath, "utf8") : "")?.pid; return pid && existsSync(`/proc/${pid}`) ? pid : null; };

// Every process whose environment names the fixture CODEX_HOME.
const codexProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || Number(name) === process.pid) continue;
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
// A runner stopped by a signal still stops the fixture's Codex processes.
for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => {
    for (const entry of codexProcesses()) { try { process.kill(entry.pid, "SIGKILL"); } catch {} }
    process.exit(1);
  });
}
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(200); }
  throw new Error(`Timed out: ${label}`);
};
const settle = async (predicate, label, timeout) => {
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};

// An interactive terminal hosted by `script`. Its screen goes to a log in
// the fixture root; the trace keeps labelled tails of it.
const terminals = [];
const quote = (arg) => `'${arg.replace(/'/g, "'\\''")}'`;
const terminal = (name, args) => {
  const child = spawn("script", ["-qfec", `stty cols 160 rows 50; exec ${["codex", ...args].map(quote).join(" ")}`, "/dev/null"],
    { cwd: main, env: { ...env, TERM: "xterm-256color" }, stdio: ["pipe", "pipe", "pipe"] });
  const logPath = path.join(root, `terminal-${name}.log`);
  let screen = "";
  const handle = { name, child, exited: null, seen: 0,
    text: () => screen,
    type: async (text) => { trace("terminal.type", { name, text }); child.stdin.write(text); await delay(700); child.stdin.write("\r"); await delay(300); },
    key: (text, label) => { trace("terminal.key", { name, key: label }); child.stdin.write(text); },
    screen: (label, length = 1500) => trace("screen", { name, label, tail: screen.slice(-length).replace(/\s+/g, " ") }) };
  const keep = (chunk) => { const text = stripAnsi(String(chunk)); appendFileSync(logPath, text); screen += text; };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(handle);
  trace("terminal.start", { name, args, daemonBefore: daemonPid() !== null });
  return handle;
};
const exitTerminal = async (handle) => {
  if (handle.exited) return;
  await handle.type("/exit");
  if (!(await settle(() => handle.exited, `${handle.name} exit`, 15000))) {
    handle.screen("exit-refused");
    handle.key("\u0003", "ctrl-c"); await delay(500); handle.key("\u0003", "ctrl-c");
    await settle(() => handle.exited, `${handle.name} interrupt exit`, 10000);
  }
};
// A resumed terminal shows a read-only transcript while another runtime
// still holds the thread, and a person presses `r` to retry. The runner
// records that screen, then retries every 10 s, as a person might. A retry
// that resumes the thread without sending the prompt given on the command
// line has the prompt typed.
const leadAsked = (label) => modelRequests.some((record) => record.label === label && !record.sideThread);
const leadStarted = async (handle, label, timeout = 180000) => {
  const started = Date.now();
  let conflicts = 0;
  let retries = 0;
  let typed = false;
  while (Date.now() - started < timeout && !handle.exited) {
    if (leadAsked(label)) {
      const host = codexProcesses().find((entry) => entry.ppid === handle.child.pid);
      return trace("lead.started", { name: handle.name, label, conflicts, retries, typed, ms: Date.now() - started, hostPid: host?.pid ?? null, daemonPid: daemonPid() });
    }
    const fresh = handle.text().slice(handle.seen);
    if (/open in another app/i.test(fresh)) {
      conflicts += 1;
      if (conflicts === 1) handle.screen("conflict", 700);
      handle.seen = handle.text().length;
      await delay(10000);
      handle.key("r", "r");
      retries += 1;
      await delay(5000);
      if (!leadAsked(label) && !/open in another app/i.test(handle.text().slice(handle.seen))) { typed = true; await handle.type(`SPIKE:${label}`); }
      continue;
    }
    await delay(250);
  }
  return trace("lead.started", { name: handle.name, label, conflicts, retries, typed, ms: Date.now() - started, met: false, exited: handle.exited });
};
const reported = (kind, label, timeout) => settle(() => reports.has(`${kind}:${label}`), `${kind} ${label}`, timeout);
const finished = (label, timeout = 60000) => settle(() => done.has(label), `${label} done`, timeout);

// The approval asks a terminal shows while `watch` runs. Each is recorded
// once and answered by the command it asks about: the lead's with `y`, "Yes,
// proceed", so its turn goes on to spawn its worker, and the worker's with
// Escape, the overlay's "No, and tell Codex what to do differently". Only
// the fixture's `outside` directory is written by an approved command.
const asks = /Would you like to run the following command\?/;
const watchAsks = (handle) => {
  let stop = false;
  const answered = [];
  const loop = (async () => {
    while (!stop) {
      const fresh = handle.text().slice(handle.seen);
      const asked = asks.test(fresh) && ["lead", "worker"].find((who) => !answered.includes(who) && fresh.includes(`escalated-${who}-ask`));
      if (asked) {
        await delay(1000);
        handle.screen(`ask-${asked}`, 2500);
        handle.seen = handle.text().length;
        answered.push(asked);
        if (asked === "lead") handle.key("y", "y"); else handle.key("\u001b", "escape");
        await delay(1500);
        handle.screen(`answered-${asked}`, 1200);
        continue;
      }
      await delay(250);
    }
  })();
  return async () => { stop = true; await loop; trace("asks", { answered }); };
};

// Codex's own record of each thread: its session metadata and, per turn,
// the sandbox, approval policy and directory it ran with.
const rolloutFiles = (dir) => {
  let entries = [];
  try { entries = readdirSync(dir); } catch { return []; }
  return entries.flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? rolloutFiles(full) : entry.endsWith(".jsonl") ? [full] : [];
  });
};
// A permission profile as each entry's path and access, with the network.
const compactProfile = (profile) => profile && { type: profile.type, network: profile.network ?? null,
  entries: (profile.file_system?.entries ?? []).map((entry) => [entry.path?.path ?? entry.path?.value?.kind ?? null, entry.access]) };
const rollouts = () => rolloutFiles(path.join(env.CODEX_HOME, "sessions")).map((file) => {
  const lines = readFileSync(file, "utf8").trim().split("\n").map(parseJson).filter(Boolean);
  const meta = lines.find((line) => line.type === "session_meta")?.payload ?? {};
  return { file: path.basename(file), id: meta.id ?? null, cwd: meta.cwd ?? null, source: meta.source ?? null,
    metaKeys: Object.keys(meta).sort(),
    // A turn a person's answer ended, and each tool call it cut short.
    aborted: lines.filter((line) => line.payload?.type === "turn_aborted").map((line) => line.payload.reason ?? null),
    abortedCalls: lines.filter((line) => line.payload?.type === "function_call_output" && /aborted by user$/.test(String(line.payload.output ?? ""))).length,
    turns: lines.filter((line) => line.type === "turn_context").map((line) => ({ timestamp: line.timestamp ?? null, cwd: line.payload?.cwd ?? null,
      approval_policy: line.payload?.approval_policy ?? null, sandbox_policy: line.payload?.sandbox_policy ?? null,
      permissions: compactProfile(line.payload?.permission_profile) })) };
});
// Codex's own log of which process served each thread request, over which
// transport, and when a host unloaded an idle thread or refused one another
// process still wrote.
const codexLog = () => {
  const db = new DatabaseSync(path.join(env.CODEX_HOME, "logs_2.sqlite"), { readOnly: true });
  const rows = db.prepare(`select ts, level, target, feedback_log_body as body, process_uuid as process from logs
    where target = 'codex_app_server::request_processors::thread_lifecycle' or feedback_log_body like '%active writer%'
      or feedback_log_body like '%rpc.method="thread/resume"%' or feedback_log_body like '%rpc.method="thread/start"%' order by id`).all();
  db.close();
  const seen = new Set();
  return rows.flatMap((row) => {
    const body = String(row.body ?? "");
    const entry = { ts: row.ts, level: row.level, pid: Number(String(row.process).match(/^pid:(\d+)/)?.[1] ?? 0),
      method: body.match(/rpc\.method="([^"]+)"/)?.[1] ?? null, transport: body.match(/rpc\.transport="([^"]+)"/)?.[1] ?? null,
      message: body.slice(body.lastIndexOf("}: ") >= 0 ? body.lastIndexOf("}: ") + 3 : 0).slice(0, 240) };
    const key = JSON.stringify([entry.pid, entry.method, entry.transport, entry.level === "ERROR" || entry.method === null ? entry.message : null]);
    if (seen.has(key)) return [];
    seen.add(key);
    return [entry];
  });
};

const scripts = ["ancestry.mjs", "checks.mjs", "cycle.mjs", "run.mjs", "verify.mjs"];
const leadOf = (label) => modelRequests.find((record) => record.label === label && !record.sideThread)?.thread ?? null;
const gitDir = path.join(main, ".git");
const grant = ["-C", main, "--sandbox", "workspace-write", "--add-dir", worktreeRoot, "--add-dir", gitDir, "-c", "sandbox_workspace_write.network_access=true"];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain"], { encoding: "utf8" }).trim() !== "";
  let bwrap = null;
  try { bwrap = execFileSync("bwrap", ["--version"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim(); } catch {}
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, bwrap,
    uv: execFileSync("uv", ["--version"], { env, encoding: "utf8" }).trim(), git: execFileSync("git", ["--version"], { encoding: "utf8" }).trim(),
    python: execFileSync("python3", ["--version"], { env, encoding: "utf8" }).trim(),
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), dashpot: { head, dirty },
    main, worktreeRoot, gitDir, outside, remote: remoteServer.url, cacheOverrides, sharedDaemonDirBefore: sharedBefore.length,
    lockSHA256: createHash("sha256").update(readFileSync(path.join(main, "uv.lock"))).digest("hex"),
    sourceSHA256: Object.fromEntries(scripts.map((file) => [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  // The session, started with no sandbox options: its lead runs the skill's
  // checks under Codex's default.
  trace("scenario", { name: "seed" });
  const seed = terminal("seed", ["-C", main, "SPIKE:seed"]);
  await leadStarted(seed, "seed");
  await reported("CHECKS", "seed", 90000);
  await finished("seed");
  seed.screen("seed-done");
  await exitTerminal(seed);
  const session = leadOf("seed");
  trace("session", { id: session });
  assert(session, "the seed's lead thread");

  // The skill's resume command, word for word.
  trace("scenario", { name: "grant" });
  const granted = terminal("grant", ["resume", session, ...grant, "SPIKE:lead-grant"]);
  await leadStarted(granted, "lead-grant");
  await reported("CHECKS", "lead-grant", 90000);
  await finished("lead-grant");
  for (const label of grantWorkers) await reported("CYCLE", label, 300000);
  for (const label of grantWorkers) await finished(label);
  await delay(1500);
  granted.screen("grant-done");
  await exitTerminal(granted);

  // The skill's command with the cache directory added as a writable root.
  trace("scenario", { name: "adddir" });
  const added = terminal("adddir", ["resume", session, ...grant, "--add-dir", path.join(env.HOME, ".cache"), "SPIKE:lead-adddir"]);
  await leadStarted(added, "lead-adddir");
  await reported("CHECKS", "lead-adddir", 90000);
  await finished("lead-adddir");
  await reported("CYCLE", "worker-adddir", 300000);
  await finished("worker-adddir");
  await delay(1500);
  added.screen("adddir-done");
  await exitTerminal(added);

  // The skill's command, with the session's shells given both cache
  // locations by configuration instead.
  trace("scenario", { name: "env" });
  // Each value is a TOML string, as the skill's shell-quoted option passes it.
  const shellEnv = cacheOverrides.map(nameValue).flatMap(([name, value]) => ["-c", `shell_environment_policy.set.${name}="${value}"`]);
  const configured = terminal("env", ["resume", session, ...grant, ...shellEnv, "SPIKE:lead-env"]);
  await leadStarted(configured, "lead-env");
  await reported("CHECKS", "lead-env", 90000);
  await finished("lead-env");
  await reported("CYCLE", "worker-env", 300000);
  await finished("worker-env");
  await delay(1500);
  configured.screen("env-done");
  await exitTerminal(configured);

  // `--add-dir` under an effective `read-only` sandbox.
  trace("scenario", { name: "readonly" });
  const readOnly = terminal("readonly", ["resume", session, "-C", main, "--sandbox", "read-only", "--add-dir", worktreeRoot, "--add-dir", gitDir,
    "-c", "sandbox_workspace_write.network_access=true", "SPIKE:lead-readonly"]);
  const readOnlyLead = await leadStarted(readOnly, "lead-readonly", 30000);
  if (readOnlyLead.met !== false) { await reported("CHECKS", "lead-readonly", 90000); await finished("lead-readonly"); }
  readOnly.screen("readonly-done", 4000);
  await exitTerminal(readOnly);

  // A refused write, plain and escalated, under `on-request`.
  trace("scenario", { name: "ask" });
  const asking = terminal("ask", ["resume", session, ...grant, "-a", "on-request", "SPIKE:lead-ask"]);
  await leadStarted(asking, "lead-ask");
  const stopWatching = watchAsks(asking);
  await finished("lead-ask", 120000);
  await finished("worker-ask", 120000);
  await delay(3000);
  await stopWatching();
  asking.screen("ask-done", 3000);
  await exitTerminal(asking);

  trace("reports.outcome", { reports: Object.fromEntries(reports) });
  trace("outside", { entries: readdirSync(outside).sort() });
  trace("remote.refs", { refs: execFileSync("git", ["-C", remote, "for-each-ref", "--format=%(refname)"], { encoding: "utf8" }).trim().split("\n") });
  trace("ledger", { files: [...grantWorkers, "worker-adddir", "worker-env"].filter((label) => existsSync(ledgerOf(label))) });
  trace("rollouts", { threads: rollouts() });
  trace("codex.log", { entries: codexLog() });
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const handle of terminals) await exitTerminal(handle).catch(() => {});
  if (daemonPid()) spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: main, env, timeout: 60000 });
  await delay(500);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length });
  model.server.closeAllConnections(); model.server.close();
  remoteServer.server.closeAllConnections(); remoteServer.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
