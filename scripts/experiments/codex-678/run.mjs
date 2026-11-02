// Launch qualification run for Issue #678: resumes and starts a real Codex
// session through the interactive entry points a person uses, with the
// execute-issues skill's measured resume command and with a profile file,
// `$CODEX_HOME/<name>.config.toml` selected by `--profile`, whose named
// permissions profile sets no legacy sandbox key. Each lead runs the skill's
// four checks, a control write and the write-free probe; in the launches a
// skill could offer, a sandboxed v2 worker of that lead then runs one full
// Worker cycle in its own linked Worktree, with nothing added to its
// environment. Between launches the runner probes the same grants with
// `codex sandbox`, as the read-only preflight proposed in Issue #679 would.
//
// Drives a pinned Codex CLI against a loopback Responses API fixture and
// Dashpot's real Codex hook publisher, with an isolated HOME, XDG
// directories and CODEX_HOME, whose daemon updater is off, in a disposable uv
// project under `/var/tmp`, outside the directories `workspace-write` grants
// by default. The project's tracked pre-commit hook runs `uv run --locked
// pre-commit` and reports the two cache variables it was given; its `origin`
// is a bare repository served by `git http-backend` on loopback, so a push
// needs the network. Codex's own session records give the permissions each
// turn ran under; the hooks' ancestry gives the process that hosted each
// launch. Metadata only.
//
//   node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [expected version] [--codex-source <rust-v0.166.0 checkout>]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.166.0";
// A fixture below a harness session would run inside that session's own
// sandbox, if it has one, and its hooks would attach to that session.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const uvBinary = execFileSync("sh", ["-c", "command -v uv"], { encoding: "utf8" }).trim();
assert(path.isAbsolute(uvBinary), "uv is on PATH");
const publisher = path.join(checkout, ".venv", "bin", "dashpot-codex-hook");
assert(existsSync(publisher), `Dashpot's Codex hook publisher is installed in ${path.dirname(publisher)}`);

// `workspace-write` makes `/tmp` and TMPDIR writable by default, so the
// fixture lives under `/var/tmp`, as a person's checkout lives outside them.
const root = mkdtempSync(path.join("/var/tmp", "dashpot-codex-678-"));
console.log(`Isolated fixture: ${root}`);
const main = path.join(root, "repository");
const worktreeRoot = path.join(root, "repository.worktrees");
const gitDir = path.join(main, ".git");
const uvCache = path.join(worktreeRoot, ".cache", "uv");
const preCommitCache = path.join(worktreeRoot, ".cache", "pre-commit");
const remote = path.join(root, "remote.git");
// A directory outside every writable root, for the control write, and a file
// a permissions profile denies reading.
const outside = path.join(root, "outside");
const denied = path.join(root, "denied.txt");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's root never
// enter the trace; the fixture's own home directory appears as `$HOME`.
const home = os.homedir();
const fixtureHome = path.join(root, "home");
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
// A terminal's partial redraw can break a path, so the fixture root's own
// name is replaced wherever it is left.
const clean = (text) => String(text).replaceAll(fixtureHome, "$HOME").replaceAll(root, "$ROOT").replaceAll(path.basename(root), "<fixture>")
  .replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~").replace(hostName, "<host>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, clean(JSON.stringify(record)) + "\n");
  return record;
};
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const sha = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
const stripAnsi = (text) => text.replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "").replace(/\u001b[()][0-9A-Za-z]|\u001b[=>78]/g, "");

// The pinned release runs through a fixture-local `codex` on PATH, beside
// the operator's uv, which the fixture's gate and hook run.
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
symlinkSync(binary, path.join(fixtureBin, "codex"));
symlinkSync(uvBinary, path.join(fixtureBin, "uv"));
// No TMPDIR is set, so `/tmp` is every tool's temporary directory.
const env = {
  PATH: `${fixtureBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: fixtureHome,
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  // Dashpot's machine-local state, where the publisher writes a session
  // record outside every configured checkout, stays inside the fixture.
  XDG_STATE_HOME: path.join(root, "state"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  LANG: "C.UTF-8",
  SPIKE_PUBLISHER: publisher,
  // Ancestry walks from hooks end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [main, worktreeRoot, uvCache, preCommitCache, outside, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
writeFileSync(denied, "Disposable denied-read sentinel.\n");
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable repository: a uv project with no package of its own, one
// locked development dependency, a pre-commit configuration whose one hook
// is local, and a tracked hook that reports its cache variables, then runs
// pre-commit as this Repository's `.githooks/pre-commit` does.
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
node -e 'console.error("HOOKENV " + JSON.stringify({ UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? null, PRE_COMMIT_HOME: process.env.PRE_COMMIT_HOME ?? null }))'
hook_dir="$(cd "$(dirname "$0")" && pwd)"
exec uv run --locked pre-commit hook-impl \\
    --config=.pre-commit-config.yaml --hook-type=pre-commit --hook-dir "$hook_dir" \\
    -- "$@"
`, { mode: 0o755 });
// The lock is resolved outside the sandbox, against the cutoff the project
// names, with a cache of the runner's own.
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
// so a push is a network connection while the remote's own writes happen
// here, outside the sandbox.
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
  if (records.some((record) => record.kind === "environment")) trace("remote.request", { method: req.method, path: url.pathname, service: url.searchParams.get("service"), status });
  res.writeHead(status, Object.fromEntries(headers.filter(([name]) => name && name.toLowerCase() !== "status")));
  res.end(response.subarray(split + separator));
});
git("remote", "add", "origin", `${remoteServer.url}/remote.git`);
// The fetch runs asynchronously: this process serves the remote.
const fetched = spawn("git", ["-C", main, "fetch", "origin"], { env, stdio: "ignore" });
const [fetchStatus] = await once(fetched, "exit");
assert.equal(fetchStatus, 0, "the fixture fetches its loopback remote");

// The hook sink.
const hookRecords = [];
const sink = await listen(async (req, res) => {
  const record = parseJson((await raw(req)).toString("utf8")) ?? {};
  hookRecords.push(trace("hook", record));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` selects the plan `plans[label]`;
// the number of tool outputs after that item, polls aside, selects the step.
// When the plan runs out, the model answers `DONE:<label>`. A command still
// running when its call yields is polled with `write_stdin` until it exits.
const checksScript = path.join(here, "checks.mjs");
const cycleScript = path.join(here, "cycle.mjs");
const probeScript = path.join(here, "probe.mjs");
const plans = {};
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
  // A terminal also sends each prompt to side threads, offered no shell;
  // they get text only.
  const sideThread = !offered("exec_command");
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
  const exec = (cmd) => toolCall("exec_command", { cmd, login: false, yield_time_ms: 30000 });
  let item = null;
  let action = null;
  if (step?.poll) {
    action = "write_stdin";
    item = toolCall("write_stdin", { session_id: step.poll, chars: "", yield_time_ms: 30000 });
  } else if (step?.checks) {
    action = "exec_command";
    item = exec(`node ${checksScript} ${label} ${main} ${worktreeRoot} ${outside} ${denied} ${step.checks.join(" ")}`.trim());
  } else if (step?.cycle) {
    action = "exec_command";
    // A worker reaches its Worktree by a per-command `cd`, as a brief tells it to.
    item = exec(`cd ${path.join(worktreeRoot, label)} && node ${cycleScript} ${label} ${main} ${ledgerOf(label)}`);
  } else if (step?.spawn) {
    const [taskName, child] = step.spawn;
    action = "spawn_agent";
    item = toolCall("spawn_agent", v2 ? { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" } : { message: `SPIKE:${child}` });
  }
  if (label && !sideThread && !item && !step) done.add(label);
  const contexts = [...new Map(input.filter((entry) => !isCall(entry)).flatMap((entry) => [...JSON.stringify(entry).matchAll(contextTags)])
    .map((match) => [match[1], match[2].replace(/\\n/g, " ").replace(/\s+/g, " ").trim().slice(0, 400)])).entries()];
  const request = trace("model.request", { thread, label, step: planned.length, polls: outputs.length - planned.length, inputItems: input.length, directiveAt,
    action, missing: Boolean(step && !item), v2, sideThread, contexts: Object.fromEntries(contexts),
    lastOutput: latestOutput ? clean(outputText(latestOutput)).replace(/\s+/g, " ").slice(-500) : null });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// The hook events `dashpot integrate codex` subscribes, each routed through
// the metadata wrapper to Dashpot's real publisher.
const hookEvents = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks);
const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 15 }] }]])),
}, null, 2));

// The model catalog: `fixture-v2` declares multi-agent v2, so the lead and
// its workers get the collaboration tools.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));

// The base user configuration sets no sandbox and no permissions profile
// until the base-profile phase, which selects one with `default_permissions`
// and a deny rule. Hook trust, once recorded, is kept in every version.
const configPath = path.join(env.CODEX_HOME, "config.toml");
let hookTrust = "";
const basePermissions = `default_permissions = "base"
`;
const basePermissionsTable = `
[permissions.base.filesystem]
":root" = "read"
":workspace_roots" = "write"
":slash_tmp" = "write"
":tmpdir" = "write"
${JSON.stringify(denied)} = "deny"

[permissions.base.network]
enabled = true
`;
const writeConfig = (withBaseProfile) => writeFileSync(configPath, `${withBaseProfile ? basePermissions : ""}model = "fixture-v2"
model_catalog_json = ${JSON.stringify(catalogPath)}
approval_policy = "never"
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

[projects.${JSON.stringify(main)}]
trust_level = "trusted"
${withBaseProfile ? basePermissionsTable : ""}${hookTrust}`);
writeConfig(false);
// The profile files: one launch configuration with a named permissions
// profile that grants the Worktree Root and the main checkout's Git
// directory explicitly, turns the network on, and moves both caches into the
// Worktree Root; and the same without the Git directory's rule.
const profileFile = (name, withGitDir) => `default_permissions = "${name}"

[permissions.${name}.filesystem]
":root" = "read"
":workspace_roots" = "write"
":slash_tmp" = "write"
":tmpdir" = "write"
${JSON.stringify(worktreeRoot)} = "write"
${withGitDir ? `${JSON.stringify(gitDir)} = "write"\n` : ""}
[permissions.${name}.network]
enabled = true

[shell_environment_policy.set]
UV_CACHE_DIR = ${JSON.stringify(uvCache)}
PRE_COMMIT_HOME = ${JSON.stringify(preCommitCache)}
`;
// A third extends the base configuration's own permissions profile, which
// exists only in the base-profile phase, and adds the two grants to it.
const extendingProfile = `default_permissions = "dashpot-arc-extends"

[permissions.dashpot-arc-extends]
extends = "base"

[permissions.dashpot-arc-extends.filesystem]
${JSON.stringify(worktreeRoot)} = "write"
${JSON.stringify(gitDir)} = "write"

[shell_environment_policy.set]
UV_CACHE_DIR = ${JSON.stringify(uvCache)}
PRE_COMMIT_HOME = ${JSON.stringify(preCommitCache)}
`;
const profiles = { "dashpot-arc": profileFile("dashpot-arc", true), "dashpot-arc-nogit": profileFile("dashpot-arc-nogit", false),
  "dashpot-arc-extends": extendingProfile };
for (const [name, text] of Object.entries(profiles)) writeFileSync(path.join(env.CODEX_HOME, `${name}.config.toml`), text);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run only counts its entries, and never removes any.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();
// The fixture daemon's own socket there is named by the SHA-256 of its
// control socket path under the fixture CODEX_HOME, so the run can tell it
// from every other entry.
const ownSocket = createHash("sha256").update(path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock")).digest("hex");

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
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, clean(entry.cmdline).slice(0, 200)];
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && /--managed-daemon|daemon/.test(entry.cmdline);
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

// One-shot Codex commands, launched by name through the fixture PATH.
const codex = (args, label, { extraEnv = {}, timeout = 120000 } = {}) => {
  const ran = spawnSync("codex", args, { cwd: main, env: { ...env, ...extraEnv }, encoding: "utf8", timeout, maxBuffer: 1 << 24 });
  const lines = (text) => stripAnsi(text ?? "").split("\n").filter((line) => line.trim() && !/^\s*$/.test(line)).slice(-12).join("\n").slice(-1500);
  return { label, status: ran.status, signal: ran.signal, stdout: ran.stdout ?? "", stderr: lines(ran.stderr) };
};

// An interactive terminal hosted by `script`. Its screen goes to a log in
// the fixture root; the trace keeps labelled tails of it. Each terminal's
// environment carries its own marker, so a command shows which client's
// environment reached it.
const terminals = [];
const quote = (arg) => `'${arg.replace(/'/g, "'\\''")}'`;
const terminal = (name, args) => {
  const child = spawn("script", ["-qfec", `stty cols 160 rows 50; exec ${["codex", ...args].map(quote).join(" ")}`, "/dev/null"],
    { cwd: main, env: { ...env, TERM: "xterm-256color", SPIKE_TERMINAL: name }, stdio: ["pipe", "pipe", "pipe"] });
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
  trace("terminal.start", { name, args, daemons: codexProcesses().filter(isDaemon).map((entry) => entry.pid) });
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
    if (leadAsked(label)) return trace("lead.started", { name: handle.name, label, conflicts, retries, typed, ms: Date.now() - started });
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
  handle.screen("lead-not-started", 3000);
  return trace("lead.started", { name: handle.name, label, conflicts, retries, typed, ms: Date.now() - started, met: false, exited: handle.exited });
};
const reported = (kind, label, timeout) => settle(() => reports.has(`${kind}:${label}`), `${kind} ${label}`, timeout);
const finished = (label, timeout = 60000) => settle(() => done.has(label), `${label} done`, timeout);
const leadOf = (label) => modelRequests.find((record) => record.label === label && !record.sideThread)?.thread ?? null;

// Dashpot's own hook records, from the machine-local store the publisher
// writes outside every configured checkout: each session's state and the
// Host Process it names.
const dashpotRecords = () => {
  const walk = (dir) => { try { return readdirSync(dir).flatMap((name) => { const full = path.join(dir, name); return statSync(full).isDirectory() ? walk(full) : name.endsWith(".json") ? [full] : []; }); } catch { return []; } };
  return walk(path.join(env.XDG_STATE_HOME, "dashpot")).map((file) => {
    const record = parseJson(readFileSync(file, "utf8")) ?? {};
    const process = record.sessionProcess ?? record.session_process ?? null;
    return { file: path.relative(env.XDG_STATE_HOME, file), sessionId: record.sessionId ?? record.session_id ?? null, state: record.state ?? null, event: record.event ?? null,
      cwd: record.cwd ?? null, process: process && { pid: process.pid, command: process.command, arguments: String(process.arguments ?? "").slice(0, 300) },
      unobservable: record.sessionProcessUnobservable ?? record.session_process_unobservable ?? null, keys: Object.keys(record).sort() };
  });
};

// Codex's own record of each thread: per turn, the permissions it ran with.
const rolloutFiles = (dir) => {
  let entries = [];
  try { entries = readdirSync(dir); } catch { return []; }
  return entries.flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? rolloutFiles(full) : entry.endsWith(".jsonl") ? [full] : [];
  });
};
const permissionKeys = /sandbox|permission|approv|network|cwd|writable|reviewer/i;
const rollouts = () => rolloutFiles(path.join(env.CODEX_HOME, "sessions")).map((file) => {
  const lines = readFileSync(file, "utf8").trim().split("\n").map(parseJson).filter(Boolean);
  const meta = lines.find((line) => line.type === "session_meta")?.payload ?? {};
  return { file: path.basename(file), id: meta.id ?? null, cwd: meta.cwd ?? null, source: meta.source ?? null,
    turns: lines.filter((line) => line.type === "turn_context").map((line) => ({ timestamp: line.timestamp ?? null, payloadKeys: Object.keys(line.payload ?? {}).sort(),
      ...Object.fromEntries(Object.entries(line.payload ?? {}).filter(([key]) => permissionKeys.test(key))) })) };
});
// Codex's own log of which process served each thread request, when one
// could read it.
const codexLog = () => {
  const files = readdirSync(env.CODEX_HOME).filter((name) => /^logs_\d+\.sqlite$/.test(name));
  return files.map((name) => {
    try {
      const db = new DatabaseSync(path.join(env.CODEX_HOME, name), { readOnly: true });
      const rows = db.prepare(`select ts, level, target, feedback_log_body as body, process_uuid as process from logs
        where feedback_log_body like '%active writer%' or feedback_log_body like '%rpc.method="thread/resume"%' or feedback_log_body like '%rpc.method="thread/start"%' order by id`).all();
      db.close();
      const seen = new Set();
      return { name, entries: rows.flatMap((row) => {
        const body = String(row.body ?? "");
        const entry = { ts: row.ts, level: row.level, pid: Number(String(row.process).match(/^pid:(\d+)/)?.[1] ?? 0),
          method: body.match(/rpc\.method="([^"]+)"/)?.[1] ?? null, transport: body.match(/rpc\.transport="([^"]+)"/)?.[1] ?? null,
          message: body.slice(body.lastIndexOf("}: ") >= 0 ? body.lastIndexOf("}: ") + 3 : 0).slice(0, 200) };
        const key = JSON.stringify([entry.pid, entry.method, entry.transport, entry.level === "ERROR" || entry.method === null ? entry.message : null]);
        if (seen.has(key)) return [];
        seen.add(key);
        return [entry];
      }) };
    } catch (error) { return { name, error: String(error).slice(0, 200) }; }
  });
};

// Every file under CODEX_HOME, with its size and modification time, so a
// probe's writes there show.
const codexHomeFiles = () => {
  const walk = (dir) => readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    const stat = statSync(full, { throwIfNoEntry: false });
    if (!stat) return [];
    return stat.isDirectory() ? [[path.relative(env.CODEX_HOME, full) + "/", "dir"], ...walk(full)] : [[path.relative(env.CODEX_HOME, full), `${stat.size}:${stat.mtimeMs}`]];
  });
  return new Map(walk(env.CODEX_HOME));
};
// The write-free probe under `codex sandbox`, with the options a preflight
// would give it. No Codex session and no daemon runs meanwhile, so every
// change under CODEX_HOME is the probe's own. It runs asynchronously: this
// process serves the loopback remote the probe reads. The probe's output
// goes through `cat`: Node prints nothing to a socket standard output, as
// this runner's pipes are, in a sandbox whose network is restricted.
const sandboxProbe = async (name, options) => {
  assert.deepEqual(codexProcesses(), [], `${name}: no fixture Codex process runs beside the probe`);
  const before = codexHomeFiles();
  const child = spawn("codex", ["sandbox", ...options, "--", "sh", "-c", '"$0" "$@" | cat', process.execPath, probeScript, name, main, worktreeRoot, uvCache, preCommitCache, outside, denied],
    { cwd: main, env: { ...env, SPIKE_TERMINAL: name }, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGKILL"), 120000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const ran = { status, signal, stdout, stderr: stripAnsi(stderr).split("\n").filter((line) => line.trim()).slice(-12).join("\n").slice(-1500) };
  const after = codexHomeFiles();
  const changes = { added: [...after.keys()].filter((file) => !before.has(file)).sort(),
    removed: [...before.keys()].filter((file) => !after.has(file)).sort(),
    changed: [...after.keys()].filter((file) => before.has(file) && before.get(file) !== after.get(file) && before.get(file) !== "dir").sort() };
  return trace("sandbox.probe", { name, options, status: ran.status, signal: ran.signal, probe: parseJson(/PROBE (\{.*\})/.exec(ran.stdout)?.[1] ?? "null"),
    stderr: ran.stderr, codexHomeChanges: changes });
};

// One launch: a terminal whose lead runs its checks, then each worker's
// cycle, then exits. The hooks and Dashpot's records of the launch follow.
const launch = async (name, args, label, workers = [], { checksTimeout = 120000 } = {}) => {
  trace("scenario", { name, args });
  const handle = terminal(name, args);
  const started = await leadStarted(handle, label);
  if (started.met !== false) {
    await reported("CHECKS", label, checksTimeout);
    if (workers.length) await finished(label, 90000);
    // A worker whose cycle never ran (its Worktree missing) finishes
    // without a report.
    for (const worker of workers) await settle(() => reports.has(`CYCLE:${worker}`) || done.has(worker), `CYCLE ${worker}`, 420000);
    for (const worker of workers) await finished(worker);
    await finished(label);
  }
  await delay(1500);
  const processes = codexProcesses().map(brief);
  // The publisher removes a session's record when the session ends, so the
  // live records are read before the terminal exits.
  const live = dashpotRecords();
  handle.screen(`${name}-done`, 2500);
  await exitTerminal(handle);
  const thread = leadOf(label);
  await settle(() => hookRecords.some((record) => record.event === "SessionEnd" && record.payload?.session_id === thread && record.receiptTime > started.receiptTime),
    `${name} SessionEnd`, 15000);
  trace("launch", { name, label, thread, processes, dashpot: live, afterExit: dashpotRecords() });
  return thread;
};

// The skill's measured resume command, word for word.
const measured = (session) => ["resume", session, "-C", main, "--sandbox", "workspace-write", "--add-dir", worktreeRoot, "--add-dir", gitDir,
  "-c", "sandbox_workspace_write.network_access=true", "-c", `shell_environment_policy.set.UV_CACHE_DIR="${uvCache}"`,
  "-c", `shell_environment_policy.set.PRE_COMMIT_HOME="${preCommitCache}"`];
// The same grants as `codex sandbox` options, as Issue #671's probe passed them.
const legacySandbox = ["-c", 'sandbox_mode="workspace-write"', "-c", `sandbox_workspace_write.writable_roots=${JSON.stringify([worktreeRoot, gitDir])}`,
  "-c", "sandbox_workspace_write.network_access=true", "-c", `shell_environment_policy.set.UV_CACHE_DIR="${uvCache}"`,
  "-c", `shell_environment_policy.set.PRE_COMMIT_HOME="${preCommitCache}"`];
const lead = (label, workers) => [{ checks: workers }, ...workers.map((worker) => ({ spawn: [worker.replaceAll("-", "_"), worker] }))];
const define = (label, workers = []) => { plans[label] = lead(label, workers); for (const worker of workers) plans[worker] = [{ cycle: true }]; };
const stopDaemon = async (label) => {
  const stopped = codex(["app-server", "daemon", "stop"], label);
  await settle(() => !codexProcesses().some(isDaemon), `${label}: daemon gone`, 30000);
  await delay(1000);
  trace("daemon.stop", { label, status: stopped.status, stderr: stopped.stderr.slice(-400), remaining: codexProcesses().map(brief) });
};

// The verifier is written from a trace, so it is not among the sources the
// trace fixes.
const scripts = ["ancestry.mjs", "checks.mjs", "cycle.mjs", "hook.mjs", "probe.mjs", "run.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "hook_records.py", "processes.py"].map((file) => `src/dashpot/sessions/${file}`);
const selected = new Set((process.env.SPIKE_SCENARIOS ?? "all").split(","));
const wanted = (name) => selected.has("all") || selected.has(name);
let controllers = [];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain"], { encoding: "utf8" }).trim() !== "";
  let bwrap = null;
  try { bwrap = execFileSync("bwrap", ["--version"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim(); } catch {}
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, bwrap,
    uv: execFileSync("uv", ["--version"], { env, encoding: "utf8" }).trim(), git: execFileSync("git", ["--version"], { encoding: "utf8" }).trim(),
    python: execFileSync("python3", ["--version"], { env, encoding: "utf8" }).trim(),
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), binarySHA256: sha(binary),
    dashpot: { head, dirty }, selected: [...selected],
    main, worktreeRoot, gitDir, uvCache, preCommitCache, outside, denied, remote: remoteServer.url, sharedDaemonDirBefore: sharedBefore.length,
    hookEvents, profiles, basePermissions: basePermissions + basePermissionsTable,
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, sha(file)])) });

  // Setup: trust the fixture hooks through the ledger, from a loopback
  // app-server that reads only the fixture CODEX_HOME.
  trace("scenario", { name: "hook-trust" });
  const port = await new Promise((resolve) => { const probe = net.createServer(); probe.listen(0, "127.0.0.1", () => { const { port } = probe.address(); probe.close(() => resolve(port)); }); });
  const trustServer = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: main, env, stdio: ["ignore", "pipe", "pipe"] });
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
  const init = await call("initialize", { clientInfo: { name: "dashpot-678-trust", version: "0" }, capabilities: { experimentalApi: true } });
  assert(init.result, `trust client initialized: ${JSON.stringify(init.error)}`);
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  const listed = await call("hooks/list", { cwds: [main] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  hookTrust = "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n");
  writeConfig(false);
  const relisted = (await call("hooks/list", { cwds: [main] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  socket.close();
  trustServer.kill("SIGTERM");
  await once(trustServer, "exit");
  await delay(500);

  // Two sessions, each started as a person starts one, with no option: the
  // managed daemon hosts both. Their leads run the checks under Codex's
  // default for a trusted project.
  define("seed-a");
  define("seed-b");
  const sessionA = await launch("seed-a", ["-C", main, "SPIKE:seed-a"], "seed-a");
  const sessionB = await launch("seed-b", ["-C", main, "SPIKE:seed-b"], "seed-b");
  trace("sessions", { a: sessionA, b: sessionB });
  assert(sessionA && sessionB, "both seed sessions started");

  // 1. The control: the skill's measured resume command, no base profile.
  define("lead-control", ["w-control"]);
  if (wanted("control")) await launch("control", [...measured(sessionA), "SPIKE:lead-control"], "lead-control", ["w-control"]);
  // 2. A fresh launch and a resume with the profile file alone.
  define("lead-pfresh", ["w-pfresh"]);
  if (wanted("pfresh")) await launch("pfresh", ["-C", main, "--profile", "dashpot-arc", "SPIKE:lead-pfresh"], "lead-pfresh", ["w-pfresh"]);
  define("lead-presume", ["w-presume"]);
  if (wanted("presume")) await launch("presume", ["resume", sessionB, "-C", main, "--profile", "dashpot-arc", "SPIKE:lead-presume"], "lead-presume", ["w-presume"]);
  // The same resume, naming the profile's permissions profile as a launch
  // override too.
  define("lead-ppin", ["w-ppin"]);
  if (wanted("ppin")) await launch("ppin", ["resume", sessionB, "-C", main, "--profile", "dashpot-arc", "-c", 'default_permissions="dashpot-arc"', "SPIKE:lead-ppin"], "lead-ppin", ["w-ppin"]);
  // 6. The profile without the Git directory's explicit rule: the lead
  // tries its Worktree, and no worker is spawned.
  plans["lead-nogit"] = [{ checks: ["w-nogit"] }];
  if (wanted("nogit")) await launch("nogit", ["-C", main, "--profile", "dashpot-arc-nogit", "SPIKE:lead-nogit"], "lead-nogit");
  // 5. The profile with `--approve-for-me`, then with `--sandbox`.
  define("lead-approve");
  if (wanted("approve")) await launch("approve", ["resume", sessionA, "-C", main, "--profile", "dashpot-arc", "--approve-for-me", "SPIKE:lead-approve"], "lead-approve");
  define("lead-psandbox");
  if (wanted("psandbox")) await launch("psandbox", ["resume", sessionA, "-C", main, "--profile", "dashpot-arc", "--sandbox", "workspace-write", "SPIKE:lead-psandbox"], "lead-psandbox");

  // 8. `codex sandbox`, with no session or daemon running.
  await stopDaemon("before-sandbox-probes");
  trace("scenario", { name: "sandbox-probes" });
  await sandboxProbe("sandbox-default", []);
  await sandboxProbe("sandbox-arc-file", ["--profile", "dashpot-arc"]);
  await sandboxProbe("sandbox-legacy", legacySandbox);
  await sandboxProbe("sandbox-arc", ["--profile", "dashpot-arc", "-P", "dashpot-arc", "-C", main]);
  await sandboxProbe("sandbox-arc-nogit", ["--profile", "dashpot-arc-nogit", "-P", "dashpot-arc-nogit", "-C", main]);
  await sandboxProbe("sandbox-workspace", ["-P", ":workspace", "-C", main]);

  // 3 and 4. The base configuration selects its own permissions profile, with
  // a deny rule and the network on.
  writeConfig(true);
  trace("scenario", { name: "base-profile-probes" });
  await sandboxProbe("base-sandbox-default", []);
  await sandboxProbe("base-sandbox-legacy", legacySandbox);
  await sandboxProbe("base-sandbox-base", ["-P", "base", "-C", main]);
  await sandboxProbe("base-sandbox-arc", ["--profile", "dashpot-arc", "-P", "dashpot-arc", "-C", main]);
  await sandboxProbe("base-sandbox-extends", ["--profile", "dashpot-arc-extends", "-P", "dashpot-arc-extends", "-C", main]);
  define("lead-base");
  if (wanted("base")) await launch("base", ["-C", main, "SPIKE:lead-base"], "lead-base");
  define("lead-bmeasured", ["w-bmeasured"]);
  if (wanted("bmeasured")) await launch("bmeasured", [...measured(sessionA), "SPIKE:lead-bmeasured"], "lead-bmeasured", ["w-bmeasured"]);
  define("lead-bpfresh", ["w-bpfresh"]);
  if (wanted("bpfresh")) await launch("bpfresh", ["-C", main, "--profile", "dashpot-arc", "SPIKE:lead-bpfresh"], "lead-bpfresh", ["w-bpfresh"]);
  define("lead-bpextends", ["w-bpextends"]);
  if (wanted("bpextends")) await launch("bpextends", ["-C", main, "--profile", "dashpot-arc-extends", "SPIKE:lead-bpextends"], "lead-bpextends", ["w-bpextends"]);
  define("lead-bpresume");
  if (wanted("bpresume")) await launch("bpresume", ["resume", sessionA, "-C", main, "--profile", "dashpot-arc", "SPIKE:lead-bpresume"], "lead-bpresume");
  await stopDaemon("final");

  trace("outside", { entries: readdirSync(outside).sort() });
  trace("remote.refs", { refs: execFileSync("git", ["-C", remote, "for-each-ref", "--format=%(refname)"], { encoding: "utf8" }).trim().split("\n") });
  trace("ledger", { files: Object.keys(plans).filter((label) => label.startsWith("w-") && existsSync(ledgerOf(label))) });
  trace("rollouts", { threads: rollouts() });
  trace("codex.log", { files: codexLog() });
  trace("dashpot.records", { records: dashpotRecords() });
  // Dashpot's Event Log: each hook's outcome, by session and event.
  const eventDir = path.join(env.XDG_STATE_HOME, "dashpot", "events");
  const events = (existsSync(eventDir) ? readdirSync(eventDir) : []).flatMap((file) => readFileSync(path.join(eventDir, file), "utf8").trim().split("\n").map(parseJson))
    .filter((event) => event?.["event.name"] === "hook.outcome")
    .map((event) => ({ session: event["dashpot.agent_session.id"], hook: event["dashpot.hook.event"], result: event["dashpot.outcome.result"], state: event["dashpot.agent_session.state"] ?? null }));
  trace("dashpot.events", { outcomes: events });
  const finalSources = Object.fromEntries(scripts.map((file) => [file, sha(path.join(here, file))]));
  for (const file of scripts) assert.equal(finalSources[file], records[0].sourceSHA256[file], `${file} stayed fixed during measurement`);
  trace("completed", { selected: [...selected] });
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: String(error?.stack ?? error).slice(0, 2000) });
  process.exitCode = 1;
} finally {
  for (const handle of terminals) await exitTerminal(handle).catch(() => {});
  if (codexProcesses().some(isDaemon)) spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: main, env, timeout: 60000 });
  await delay(500);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  // The fixture daemon removes its socket when it stops; one it left, named
  // by the fixture's own hash, is removed, and nothing else there.
  const leftover = sharedEntries().filter((name) => name === ownSocket || name === `${ownSocket}.lock`);
  for (const name of leftover) rmSync(path.join(sharedDaemonDir, name), { force: true });
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length,
    ownLeft: leftover, ownAfter: sharedAfter.filter((name) => name.startsWith(ownSocket)) });
  for (const server of [model, remoteServer, sink]) { server.server.closeAllConnections(); server.server.close(); }
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
