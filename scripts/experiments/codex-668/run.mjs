// Managed-worktree run for Issue #668: can Codex's managed-worktree tools
// help Dashpot prepare or recover a Worktree, or explain which task a
// checkout belongs to, and can an integration reach them without private
// internals? Drives a pinned Codex CLI against a loopback Responses API
// fixture with an isolated CODEX_HOME, whose daemon updater is off, under
// the `workspace-write` sandbox, with Dashpot's own Codex hook publisher, in
// a disposable Dashpot Project with a bare `origin`. A fixture-local `git`
// on PATH logs every Git command Codex runs and can hold one managed
// `worktree add` until the runner releases it. It records:
//
// - the tools Codex offers a root thread, and what `tool_search` finds for
//   "worktree", in a standalone terminal, a daemon-hosted terminal, a
//   terminal in an explicitly untrusted project, `codex exec`, and a thread
//   an app-server client starts;
// - `create_worktree` while a creation is held: the pending reply, a
//   duplicate request, status polls, the created checkout, its base, Branch
//   state, files, owner record, the session's directory and write
//   permissions, and `list_worktrees`;
// - a second creation after the first completed, at an explicit `ref`, and
//   one at a ref that does not exist;
// - a creation interrupted by killing the terminal, then the attachments an
//   independent app-server reads, and the resumed thread's status and list;
// - a registration that fails because the thread holds its limit of
//   attachments, on the daemon, and the attachments after the daemon
//   restarts;
// - `codex exec --worktree`: where it creates, and what it records;
// - `dashpot worktree create` and `dashpot worktree check` in the same
//   Repository, for comparison.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
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
const expectedVersion = process.argv[3] ?? "0.166.0";
const selected = process.env.SPIKE_SCENARIOS ? new Set(process.env.SPIKE_SCENARIOS.split(",")) : null;
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

// Outside every Dashpot Project and outside `/tmp`, whose shared Codex
// daemon directory belongs to the operator's own sessions; short enough for
// the daemon's Unix socket path.
const root = mkdtempSync(path.join("/var/tmp", "dashpot-668-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const untrusted = path.join(root, "untrusted");
const origin = path.join(root, "origin.git");
const tracePath = path.join(root, "trace.jsonl");
const holdDir = path.join(root, "git-hold");
const gitLog = path.join(root, "git-commands.log");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's temporary root
// never enter the trace.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const retained = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~").replace(hostName, "<host>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 5) } : record;
  appendFileSync(tracePath, retained(JSON.stringify(kept)) + "\n");
  return record;
};
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };

// The pinned release runs through a fixture-local `codex` on PATH, beside a
// fixture-local `git` that logs each command and can hold a managed add.
const realGit = execFileSync("sh", ["-c", "command -v git"], { env: { PATH: "/usr/bin:/bin" }, encoding: "utf8" }).trim();
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
mkdirSync(holdDir);
symlinkSync(binary, path.join(fixtureBin, "codex"));
// Each command is logged as its directory and arguments, separated by the
// unit separator. Codex's own Git commands carry `-c core.fsmonitor=`. When
// `hold` exists, a `worktree add --detach --no-checkout` runs, then waits for
// `release`, so the creation stays pending after Git registered the
// checkout and before Codex populated it.
writeFileSync(path.join(fixtureBin, "git"), `#!/bin/sh
printf '%s\\037' "$PWD" "$@" >> '${gitLog}'
printf '\\n' >> '${gitLog}'
case " $* " in
  *" worktree add --detach --no-checkout "*)
    '${realGit}' "$@"
    status=$?
    if [ -e '${holdDir}/hold' ]; then
      : > '${holdDir}/held'
      i=0
      while [ ! -e '${holdDir}/release' ] && [ $i -lt 1800 ]; do sleep 0.1; i=$((i+1)); done
      rm -f '${holdDir}/held'
    fi
    exit $status;;
esac
exec '${realGit}' "$@"
`);
chmodSync(path.join(fixtureBin, "git"), 0o755);
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
  SPIKE_PUBLISHER: publisher,
  // Ancestry walks from hooks end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, untrusted, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const pool = path.join(env.CODEX_HOME, "worktrees");
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project. `origin/main` is the Repository's default
// Branch; local `main` is one commit ahead of it, and `feature` one commit
// off it. The source checkout holds an ignored file, an untracked file and
// an uncommitted change, and a post-checkout hook that would leave a marker.
const commitEnv = ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null"];
const git = (...args) => execFileSync(realGit, ["-C", fixture, ...args], { env, stdio: "pipe", encoding: "utf8" }).trim();
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
const metadata = { id: "I_fixture_1", number: 1, reference: "fixture-1", state: "open", stateReason: null, labels: [], assignees: [], author: null,
  relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
  createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
writeFileSync(path.join(fixture, "issues", "1.md"), `---\n${JSON.stringify(metadata, null, 2)}\n---\n# Fixture Issue 1\n\nDisposable.\n`);
const dashpot = (args, cwd = fixture) => {
  const started = Date.now();
  const ran = spawnSync(dashpotCommand, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "", ms: Date.now() - started };
};
const initialized = dashpot(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
writeFileSync(path.join(fixture, ".gitignore"), "/.dashpot/state/\nignored.txt\n");
writeFileSync(path.join(fixture, "tracked.txt"), "committed\n");
git("add", "-A");
git(...commitEnv, "commit", "-m", "Disposable fixture");
execFileSync(realGit, ["init", "--bare", "--initial-branch=main", origin], { env, stdio: "pipe" });
git("remote", "add", "origin", origin);
git("push", "-q", "origin", "main");
git("remote", "set-head", "origin", "main");
git("switch", "-q", "-c", "feature");
writeFileSync(path.join(fixture, "feature.txt"), "feature\n");
git("add", "feature.txt");
git(...commitEnv, "commit", "-m", "Feature commit");
git("switch", "-q", "main");
writeFileSync(path.join(fixture, "ahead.txt"), "ahead\n");
git("add", "ahead.txt");
git(...commitEnv, "commit", "-m", "Local commit ahead of origin");
const refs = { originMain: git("rev-parse", "origin/main"), localMain: git("rev-parse", "main"), feature: git("rev-parse", "feature") };
writeFileSync(path.join(fixture, "ignored.txt"), "ignored\n");
writeFileSync(path.join(fixture, "untracked.txt"), "untracked\n");
writeFileSync(path.join(fixture, "tracked.txt"), "uncommitted change\n");
const hookMarker = path.join(root, "post-checkout-ran");
writeFileSync(path.join(fixture, ".git", "hooks", "post-checkout"), `#!/bin/sh\n: > '${hookMarker}'\n`);
chmodSync(path.join(fixture, ".git", "hooks", "post-checkout"), 0o755);
mkdirSync(path.join(fixture, ".dashpot", "state"), { recursive: true });
execFileSync(realGit, ["-C", untrusted, "init", "--initial-branch=main"], { env, stdio: "pipe" });
writeFileSync(path.join(untrusted, "file.txt"), "untrusted\n");
execFileSync(realGit, ["-C", untrusted, "add", "-A"], { env, stdio: "pipe" });
execFileSync(realGit, ["-C", untrusted, ...commitEnv, "commit", "-m", "Untrusted fixture"], { env, stdio: "pipe" });

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
  trace("hook", await body(req));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;
const stripAnsi = (text) => text.replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "").replace(/\u001b[()][0-9A-Za-z]|\u001b[=>78]/g, "");

// The fixture model. The latest input item that is not a tool call and
// carries `SPIKE:<label>` selects the plan `plans[label]`, a function of the
// tool outputs that followed it. It returns the next action: a
// `tool_search` call, a call of a tool found by an earlier search, a probe,
// or nothing, when the model answers `DONE:<label>`. An action may ask for a
// delay before the model answers, so a poll does not spin. Each request
// records the tools offered and the sources `tool_search` lists (once per
// thread, and again when they change), and the latest output it received:
// a search's tool names, or a managed-worktree reply Codex composed.
const probeScript = path.join(here, "probe.mjs");
const plans = {};
const plan = (label, decide) => { plans[label] = decide; };
const markerPattern = /SPIKE:([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output|tool_search_output)$/.test(item.type ?? "");
const isOutput = (item) => /(_call_output|tool_search_output)$/.test(item.type ?? "");
const probeOf = (text) => {
  const line = String(text ?? "").split("\n").find((entry) => entry.startsWith("PROBE "));
  return line ? parseJson(line.slice("PROBE ".length)) : null;
};
const outputText = (output) => {
  if (typeof output === "string") return output;
  if (Array.isArray(output)) return output.map((item) => item.text ?? "").join("");
  if (output && typeof output === "object") return outputText(output.content ?? output.body ?? "");
  return "";
};
// A managed-worktree reply is one JSON object, after the `Output:` line Codex
// prefixes to an MCP tool's text, sometimes inside a list of content blocks.
const replyOf = (text) => {
  const at = String(text).indexOf("Output:");
  let parsed = parseJson(at < 0 ? text : String(text).slice(at + "Output:".length));
  if (Array.isArray(parsed)) parsed = parseJson(parsed.map((item) => item.text ?? "").join(""));
  return parsed && typeof parsed === "object" ? parsed : null;
};
const searchedTools = (tools) => (tools ?? []).flatMap((tool) => tool.type === "namespace"
  ? (tool.tools ?? []).map((nested) => ({ namespace: tool.name, name: nested.name, deferLoading: nested.defer_loading ?? null }))
  : [{ namespace: tool.namespace ?? null, name: tool.name ?? tool.type, deferLoading: tool.defer_loading ?? null }]);
const toolSearchSources = (description) => {
  const listed = String(description ?? "").split("following sources:\n")[1];
  return listed ? listed.split("\n").filter((line) => line.startsWith("- ")).map((line) => line.slice(2).split(":")[0]) : null;
};
const modelRequests = [];
const lastToolsByThread = new Map();
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
  let directiveAt = -1;
  let label = null;
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].map((match) => match[1]);
    if (found.length) { directiveAt = index; label = found.at(-1); }
  });
  const offeredTools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? (tool.tools ?? []).map((nested) => [tool.name, nested.name ?? nested.type]) : [[null, tool.name ?? tool.type]]);
  const toolNames = offeredTools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const searchTool = (payload.tools ?? []).find((tool) => tool.type === "tool_search");
  const sources = searchTool ? toolSearchSources(searchTool.description) : null;
  const toolsKey = JSON.stringify([toolNames, sources]);
  const toolsChanged = lastToolsByThread.get(thread) !== toolsKey;
  lastToolsByThread.set(thread, toolsKey);
  // Every call in the input, by call id, so each output names its tool.
  const calls = new Map();
  for (const item of input) if (/_call$/.test(item.type ?? "") && item.call_id) calls.set(item.call_id, item);
  // Tools found by every search the thread made, latest first.
  const found = input.filter((item) => item.type === "tool_search_output").flatMap((item) => searchedTools(item.tools)).reverse();
  const outputs = input.slice(directiveAt + 1).filter(isOutput).map((item) => {
    const call = calls.get(item.call_id);
    if (item.type === "tool_search_output") return { kind: "search", tools: searchedTools(item.tools) };
    const text = outputText(item.output);
    const name = call?.name ?? null;
    if (name === "exec_command") return { kind: "probe", probe: probeOf(text) };
    return { kind: "reply", name, success: item.output?.success ?? null, reply: replyOf(text), text: replyOf(text) ? undefined : text.slice(0, 300) };
  });
  const ctx = { outputs, last: outputs.at(-1) ?? null, offered: (name) => offeredTools.some(([, toolName]) => toolName === name), thread };
  const decided = label && plans[label] ? plans[label](ctx) : null;
  let item = null;
  let missing = false;
  const callId = `call_${label}_${outputs.length}_${modelRequests.length}`;
  if (decided?.search) {
    item = { type: "tool_search_call", call_id: callId, execution: "client", status: "completed", arguments: { query: decided.search, limit: 8 } };
  } else if (decided?.call) {
    const tool = found.find((entry) => entry.name === decided.call) ?? (offeredTools.find(([, toolName]) => toolName === decided.call) ? { namespace: offeredTools.find(([, toolName]) => toolName === decided.call)[0], name: decided.call } : null);
    if (tool) item = { type: "function_call", call_id: callId, ...(tool.namespace ? { namespace: tool.namespace } : {}), name: decided.call, arguments: JSON.stringify(decided.args ?? {}) };
    else missing = true;
  } else if (decided?.probe) {
    const tool = offeredTools.find(([, toolName]) => toolName === "exec_command");
    if (tool) item = { type: "function_call", call_id: callId, ...(tool[0] ? { namespace: tool[0] } : {}), name: "exec_command",
      arguments: JSON.stringify({ cmd: `node ${probeScript} ${decided.probe} ${decided.targets.join(" ")}`, login: false, yield_time_ms: 30000 }) };
    else missing = true;
  }
  const latest = ctx.last;
  const request = trace("model.request", { thread, label, step: outputs.length,
    action: item ? (decided.search ? `search:${decided.search}` : decided.call ? `call:${decided.call}` : `probe:${decided.probe}`) : null,
    namespace: item?.namespace ?? null, args: decided?.call ? decided.args ?? {} : undefined, missing,
    tools: toolsChanged ? toolNames : undefined, toolSearchSources: toolsChanged ? sources : undefined,
    latest: latest ? JSON.parse(retained(JSON.stringify(latest))) : null,
    session: payload.client_metadata?.session_id ?? req.headers["session_id"] ?? null });
  request.parsed = latest;
  modelRequests.push(request);
  if (decided?.wait) await delay(decided.wait);
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

// The model catalog names `fixture` only, a copy of a bundled entry without a
// tool set or code mode.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture", display_name: "Fixture", prefer_websockets: false }] }, null, 2));

// The `workspace-write` sandbox without network and no approval ever asked
// (`never`). The source checkout is trusted, the second repository
// explicitly untrusted, and Codex's managed-worktree pool keeps its default
// place under CODEX_HOME.
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "workspace-write"
model_provider = "fixture"
check_for_update_on_startup = false

[sandbox_workspace_write]
exclude_slash_tmp = true
exclude_tmpdir_env_var = true

[features]
hooks = true
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

[projects."${untrusted}"]
trust_level = "untrusted"
`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run only counts its entries and never removes any.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

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
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const daemonPid = () => codexProcesses().find(isDaemon)?.pid ?? null;
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
// Codex names a control socket's entry in the shared daemon directory by the
// SHA-256 of the socket's path, so the fixture's own entries are attributable
// while other sessions on the machine add and remove theirs.
const fixtureEntry = createHash("sha256").update(socketPath).digest("hex");
const hooks = () => records.filter((record) => record.kind === "hook");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const settle = async (predicate, label, timeout) => {
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};
const mark = () => records.length;
const hookSince = (since, predicate) => hooks().find((record) => record.receipt > since && predicate(record));

// What exists on disk and in Git: the managed pool's checkouts, the
// Repository's Worktree records, and one checkout's state, all read from
// outside the session with the real Git.
const realGitIn = (cwd, ...args) => {
  const ran = spawnSync(realGit, ["-C", cwd, ...args], { env, encoding: "utf8" });
  return { status: ran.status, stdout: (ran.stdout ?? "").trim() };
};
const poolCheckouts = () => {
  if (!existsSync(pool)) return [];
  return readdirSync(pool).filter((bucket) => /^[0-9a-f]{4}$/.test(bucket)).flatMap((bucket) =>
    readdirSync(path.join(pool, bucket)).map((name) => path.join(pool, bucket, name))).sort();
};
const inventory = () => {
  const listed = realGitIn(fixture, "worktree", "list", "--porcelain").stdout;
  return listed.split("\n\n").filter(Boolean).map((entry) => {
    const fields = Object.fromEntries(entry.split("\n").map((line) => { const at = line.indexOf(" "); return at < 0 ? [line, true] : [line.slice(0, at), line.slice(at + 1)]; }));
    return { path: retained(fields.worktree), head: fields.HEAD ?? null, branch: fields.branch ?? null, detached: Boolean(fields.detached) };
  });
};
const ownerRecord = (checkoutRoot) => {
  const located = realGitIn(checkoutRoot, "rev-parse", "--path-format=absolute", "--git-path", "codex-thread.json");
  if (located.status !== 0) return { located: false };
  const file = located.stdout;
  return { located: true, file: retained(file), exists: existsSync(file), record: existsSync(file) ? parseJson(readFileSync(file, "utf8")) : null };
};
const inspect = (checkoutRoot) => {
  if (!checkoutRoot || !existsSync(checkoutRoot)) return { exists: false };
  const files = readdirSync(checkoutRoot).filter((name) => name !== ".git").sort();
  const configWorktree = realGitIn(checkoutRoot, "rev-parse", "--path-format=absolute", "--git-path", "config.worktree");
  return {
    exists: true,
    path: retained(checkoutRoot),
    inPool: path.relative(pool, checkoutRoot).split(path.sep).length === 2 && /^[0-9a-f]{4}$/.test(path.relative(pool, checkoutRoot).split(path.sep)[0]),
    name: path.basename(checkoutRoot),
    head: realGitIn(checkoutRoot, "rev-parse", "HEAD").stdout || null,
    symbolicRef: realGitIn(checkoutRoot, "symbolic-ref", "-q", "HEAD"),
    clean: realGitIn(checkoutRoot, "status", "--porcelain").stdout === "",
    files,
    tracked: existsSync(path.join(checkoutRoot, "tracked.txt")) ? readFileSync(path.join(checkoutRoot, "tracked.txt"), "utf8").trim() : null,
    ignoredCopied: existsSync(path.join(checkoutRoot, "ignored.txt")),
    untrackedCopied: existsSync(path.join(checkoutRoot, "untracked.txt")),
    projectConfig: existsSync(path.join(checkoutRoot, ".dashpot")) && readdirSync(path.join(checkoutRoot, ".dashpot")).sort(),
    coreWorktree: configWorktree.status === 0 ? retained(realGitIn(checkoutRoot, "config", "--file", configWorktree.stdout, "core.worktree").stdout) : null,
    owner: ownerRecord(checkoutRoot),
  };
};
// Codex's own Git commands since a log offset: every command carrying
// `-c core.fsmonitor=`, without its `-c` options.
const gitLogLines = () => existsSync(gitLog) ? readFileSync(gitLog, "utf8").split("\n").filter(Boolean) : [];
const codexGitSince = (offset) => gitLogLines().slice(offset).map((line) => line.split("\u001f").slice(0, -1))
  .filter((fields) => fields.includes("core.fsmonitor="))
  .map(([cwd, ...args]) => {
    const kept = [];
    for (let index = 0; index < args.length; index++) { if (args[index] === "-c") { index++; continue; } kept.push(args[index]); }
    return { cwd: retained(cwd), args: kept.map(retained) };
  });

// An interactive terminal hosted by `script`, started outside the checkouts.
// Its screen goes to a log in the fixture root; the trace keeps only a
// labelled tail.
const terminals = [];
const terminal = async (name, args, cwd = root) => {
  const child = spawn("script", ["-qfec", ["codex", ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "160", LINES: "50" }, stdio: ["pipe", "pipe", "pipe"] });
  const logPath = path.join(root, `terminal-${name}.log`);
  let screen = "";
  const handle = { name, child, exited: null,
    type: async (text) => { trace("terminal.type", { name, text: retained(text) }); child.stdin.write(text); await delay(700); child.stdin.write("\r"); await delay(300); },
    key: (text) => child.stdin.write(text),
    screen: (label) => trace("screen", { name, label, tail: retained(screen.slice(-1500)).replace(/\s+/g, " ") }) };
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
const submitted = (since, label) => hookSince(since, (record) => record.event === "UserPromptSubmit" && retained(JSON.stringify(record)).includes(label))
  ?? hookSince(since, (record) => record.event === "UserPromptSubmit");
const turnEnded = (since, session) => hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id && (!session || record.payload.session_id === session));
const promptTurn = async (tui, label, timeout = 90000) => {
  const since = mark();
  await tui.type(`SPIKE:${label}`);
  await settle(() => submitted(since, label) && turnEnded(submitted(since, label).receipt, submitted(since, label).payload.session_id), `${label} Stop`, timeout);
  const prompt = submitted(since, label);
  return trace("prompt.turn", { label, session: prompt?.payload.session_id ?? null, cwd: retained(prompt?.payload.cwd ?? ""), submitted: Boolean(prompt), since });
};
const firstTurn = async (name, args, label, cwd = root) => {
  const since = mark();
  const tui = await terminal(name, [...args, `SPIKE:${label}`], cwd);
  await settle(() => turnEnded(since), `${label} Stop`, 90000);
  await delay(1000);
  const start = hookSince(since, (record) => record.event === "SessionStart");
  const session = start?.payload.session_id ?? null;
  trace("first.turn", { name, label, session, cwd: retained(start?.payload.cwd ?? ""), since });
  return { tui, session, since };
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
  socket.on((text) => {
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method) notifications.push({ method: parsed.method, params: parsed.params, receivedAt: Date.now() });
  });
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-668-${name}`, version: "0" }, capabilities: {} });
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
// A `codex app-server` on a loopback WebSocket, sharing the fixture's
// CODEX_HOME and so its thread store.
const loopbackServer = async (name) => {
  const port = await freePort();
  const server = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let banner = "";
  server.stderr.on("data", (chunk) => { banner += chunk; });
  server.stdout.on("data", () => {});
  await waitFor(() => banner.includes("listening on"), `${name} server listening`, 20000);
  const client = await tcpClient(name, port);
  trace("app-server.start", { name, pid: server.pid });
  return { client, stop: async () => { client.close(); server.kill("SIGTERM"); await once(server, "exit"); trace("app-server.stop", { name }); await delay(500); } };
};
// Every attachment a stored thread holds, read through the documented
// `thread/attachment/list`, and the owners `thread/attachmentOwner/list`
// returns for each worktree identity.
const attachmentsOf = async (client, threadId) => {
  const data = [];
  let cursor = null;
  let pages = 0;
  let error = null;
  do {
    const page = await client.call("thread/attachment/list", { threadId, cursor, limit: 100 });
    if (page.error) { error = page.error.message ?? JSON.stringify(page.error); break; }
    data.push(...page.result.data);
    cursor = page.result.nextCursor;
    pages++;
  } while (cursor && pages < 10);
  const worktrees = data.filter((entry) => /worktree/.test(entry.attachmentType));
  const owners = {};
  for (const entry of worktrees) {
    const owned = await client.call("thread/attachmentOwner/list", { attachmentType: entry.attachmentType, identityKey: entry.identityKey });
    owners[retained(entry.identityKey)] = owned.result?.data ?? { error: owned.error ?? null };
  }
  return { threadId, error, count: data.length, types: [...new Set(data.map((entry) => entry.attachmentType))].sort(),
    worktrees: worktrees.map((entry) => ({ type: entry.attachmentType, identityKey: retained(entry.identityKey), payload: JSON.parse(retained(JSON.stringify(entry.payload))) })), owners };
};
const ownersOf = async (client, checkoutRoot) => {
  const owned = await client.call("thread/attachmentOwner/list", { attachmentType: "worktree", identityKey: checkoutRoot });
  return owned.result?.data ?? { error: owned.error ?? null };
};

// The fixture model's plans. `search` finds the managed-worktree tools;
// `poll` repeats get_worktree_creation_status while the creation is pending.
const repliesOf = (ctx, name) => ctx.outputs.filter((output) => output.kind === "reply" && output.name === name);
const searchFirst = (ctx) => ctx.outputs.length === 0 ? (ctx.offered("tool_search") ? { search: "worktree" } : null) : undefined;
const pendingId = (ctx) => repliesOf(ctx, "create_worktree").map((output) => output.reply?.operationId).find(Boolean);
const poll = (ctx, limit = 240) => {
  const status = repliesOf(ctx, "get_worktree_creation_status");
  const latest = status.at(-1)?.reply;
  if (status.length && (!latest || latest.type !== "pending")) return undefined;
  if (status.length >= limit) return undefined;
  return { call: "get_worktree_creation_status", args: { operationId: pendingId(ctx) }, wait: status.length ? 500 : 0 };
};
const created = (ctx) => repliesOf(ctx, "get_worktree_creation_status").map((output) => output.reply).findLast((reply) => reply && reply.type !== "pending") ?? null;
const steps = (...deciders) => (ctx) => {
  for (const decide of deciders) {
    const action = decide(ctx);
    if (action === undefined) continue;
    return action;
  }
  return null;
};
// Plans count their own calls by name, which keeps each step taken once.
const callOnce = (name, args, nth = 1) => (ctx) => repliesOf(ctx, name).length < nth ? { call: name, args: typeof args === "function" ? args(ctx) : args } : undefined;
// list_worktrees returns one attachment a page: follow nextCursor to its end.
const listAll = (ctx) => {
  const pages = repliesOf(ctx, "list_worktrees");
  if (!pages.length) return { call: "list_worktrees", args: {} };
  const cursor = pages.at(-1).reply?.nextCursor;
  return cursor && pages.length < 12 ? { call: "list_worktrees", args: { cursor } } : undefined;
};
const probeOnce = (label, targets) => (ctx) => ctx.outputs.some((output) => output.kind === "probe") ? undefined : { probe: label, targets: targets(ctx) };
const workspaceOf = (ctx) => created(ctx)?.worktree?.workspaceRoot ?? null;
const availability = (label) => plan(label, steps(searchFirst));

const scenarios = [];
const scenario = (name, run) => scenarios.push({ name, run });
const standalone = ["--disable", "daemon_auto_start"];
let controllers = [];
const state = {};
const hold = () => { rmSync(path.join(holdDir, "release"), { force: true }); writeFileSync(path.join(holdDir, "hold"), ""); trace("git.hold", {}); };
const release = () => { writeFileSync(path.join(holdDir, "release"), ""); rmSync(path.join(holdDir, "hold"), { force: true }); trace("git.release", {}); };
const outcome = (label) => modelRequests.filter((record) => record.label === label).map((record) => ({ step: record.step, action: record.action, namespace: record.namespace, latest: record.latest && JSON.parse(retained(JSON.stringify(record.latest))) }));
const createdRoot = (label) => modelRequests.filter((record) => record.label === label).map((record) => record.parsed)
  .filter((output) => output?.kind === "reply" && output.name === "get_worktree_creation_status" && output.reply?.worktree?.root).map((output) => output.reply.worktree.root).at(-1) ?? null;
const newCheckouts = (before) => poolCheckouts().filter((entry) => !before.includes(entry));

// A standalone terminal in the trusted source checkout: what it offers, a
// held creation with a duplicate request, a second creation at `feature`,
// one at a missing ref, and one interrupted by killing the terminal.
scenario("standalone", async () => {
  const p = "sa";
  availability(`${p}-avail`);
  plan(`${p}-create`, steps(searchFirst, callOnce("create_worktree", { allowAsync: true }), callOnce("create_worktree", { allowAsync: true }, 2),
    poll, probeOnce(`${p}-create`, (ctx) => [path.join(fixture, ".dashpot", "state", `probe-${p}`), path.join(workspaceOf(ctx) ?? root, `probe-${p}`)]),
    listAll));
  plan(`${p}-again`, steps(searchFirst, callOnce("create_worktree", { allowAsync: true, ref: "feature" }), poll, listAll));
  plan(`${p}-missing`, steps(searchFirst, callOnce("create_worktree", { allowAsync: true, ref: "no-such-ref" }), poll));
  plan(`${p}-interrupt`, steps(searchFirst, callOnce("create_worktree", { allowAsync: true }), poll));
  const { tui, session } = await firstTurn(p, [...standalone, "-C", fixture], `${p}-avail`);
  state.standaloneSession = session;
  trace(`${p}.avail`, { session, requests: outcome(`${p}-avail`) });

  // Held after Git registered the checkout, so the creation stays pending.
  let before = poolCheckouts();
  let gitAt = gitLogLines().length;
  hold();
  const createAt = mark();
  await tui.type(`SPIKE:${p}-create`);
  await settle(() => existsSync(path.join(holdDir, "held")), `${p} creation held`, 45000);
  await settle(() => modelRequests.some((record) => record.label === `${p}-create` && record.step >= 4), `${p} duplicate and status sent`, 45000);
  const heldState = { pool: newCheckouts(before).map(retained), inventory: inventory(), ownerWhileHeld: newCheckouts(before).map((entry) => ownerRecord(entry)) };
  release();
  await settle(() => turnEnded(createAt, session), `${p}-create Stop`, 90000);
  await delay(1000);
  const first = createdRoot(`${p}-create`);
  state.firstRoot = first;
  trace(`${p}.create`, { session, held: heldState, requests: outcome(`${p}-create`), created: newCheckouts(before).map(retained),
    checkout: inspect(first), inventory: inventory(), git: codexGitSince(gitAt), hookMarker: existsSync(hookMarker),
    sourceWorktreeConfig: realGitIn(fixture, "config", "--get", "extensions.worktreeConfig"), refs,
    hooks: hooks().filter((record) => record.receipt > createAt).map((record) => [record.event, record.payload.session_id, retained(record.payload.cwd ?? "")]) });

  before = poolCheckouts();
  gitAt = gitLogLines().length;
  await promptTurn(tui, `${p}-again`);
  const second = createdRoot(`${p}-again`);
  state.secondRoot = second;
  trace(`${p}.again`, { session, requests: outcome(`${p}-again`), created: newCheckouts(before).map(retained), checkout: inspect(second), git: codexGitSince(gitAt) });

  before = poolCheckouts();
  gitAt = gitLogLines().length;
  await promptTurn(tui, `${p}-missing`);
  trace(`${p}.missing`, { session, requests: outcome(`${p}-missing`), created: newCheckouts(before).map(retained), buckets: existsSync(pool) ? readdirSync(pool).length : 0, git: codexGitSince(gitAt) });

  // Interrupted: the terminal's Codex process is killed while Git holds.
  before = poolCheckouts();
  gitAt = gitLogLines().length;
  hold();
  const interruptAt = mark();
  await tui.type(`SPIKE:${p}-interrupt`);
  await settle(() => existsSync(path.join(holdDir, "held")), `${p} interrupt held`, 45000);
  await settle(() => modelRequests.some((record) => record.label === `${p}-interrupt` && record.step >= 3), `${p} interrupt polled`, 45000);
  // `script` runs the terminal's Codex through a shell: kill Codex itself.
  const below = (entry, ancestor) => { for (let at = entry, hops = 0; at && hops < 6; hops++) { if (at.ppid === ancestor) return true; try { at = describe(at.ppid); } catch { return false; } } return false; };
  const tuiProcess = codexProcesses().find((entry) => entry.comm.startsWith("codex") && below(entry, tui.child.pid));
  trace(`${p}.kill`, { pid: tuiProcess?.pid ?? null, comm: tuiProcess?.comm ?? null });
  if (tuiProcess) process.kill(tuiProcess.pid, "SIGKILL");
  await settle(() => tui.exited, `${p} terminal gone`, 15000);
  release();
  await delay(2000);
  const orphan = newCheckouts(before)[0] ?? null;
  state.orphanRoot = orphan;
  state.interruptOperation = modelRequests.filter((record) => record.label === `${p}-interrupt`).map((record) => record.parsed?.reply?.operationId).find(Boolean) ?? null;
  trace(`${p}.interrupt`, { session, requests: outcome(`${p}-interrupt`), created: newCheckouts(before).map(retained), checkout: inspect(orphan), inventory: inventory(), git: codexGitSince(gitAt),
    hooks: hooks().filter((record) => record.receipt > interruptAt).map((record) => [record.event, record.payload.session_id, retained(record.payload.cwd ?? "")]) });
});

// After the terminal is gone: an independent app-server reads the thread's
// attachments; then the thread is resumed in a new terminal, which asks for
// the interrupted operation and lists its worktrees.
scenario("restart", async () => {
  const p = "rs";
  const session = state.standaloneSession;
  const reader = await loopbackServer("reader");
  const read = await attachmentsOf(reader.client, session);
  const owners = { first: await ownersOf(reader.client, state.firstRoot), second: await ownersOf(reader.client, state.secondRoot), orphan: await ownersOf(reader.client, state.orphanRoot) };
  trace(`${p}.read`, { session, attachments: read, owners });
  await reader.stop();
  plan(`${p}-resume`, steps(searchFirst, callOnce("get_worktree_creation_status", { operationId: state.interruptOperation ?? "none" }), listAll));
  const since = mark();
  const tui = await terminal(p, ["resume", session, ...standalone, "-C", fixture]);
  await delay(6000);
  const turn = await promptTurn(tui, `${p}-resume`);
  trace(`${p}.resume`, { session, resumedSession: turn.session, requests: outcome(`${p}-resume`),
    starts: hooks().filter((record) => record.receipt > since && record.event === "SessionStart").map((record) => [record.payload.session_id, record.payload.source]) });
  await exitTerminal(tui);
});

// Availability elsewhere: an explicitly untrusted project, `codex exec`, and
// a thread an app-server client starts for itself.
// The turn's end is the fixture model's last request rather than `Stop`,
// since a restricted session's lifecycle hooks are not assumed to run.
scenario("untrusted", async () => {
  availability("ut-avail");
  const since = mark();
  const tui = await terminal("ut", [...standalone, "-C", untrusted, "SPIKE:ut-avail"]);
  // A saved untrusted folder holds the session at folder consent, whose
  // highlighted choice, "Open restricted", keeps the folder's trust setting.
  const consentHeld = !(await settle(() => modelRequests.some((record) => record.label === "ut-avail"), "ut-avail first request", 15000));
  if (consentHeld) tui.key("\r");
  await settle(() => modelRequests.some((record) => record.label === "ut-avail" && record.step > 0 && record.action === null), "ut-avail done", 90000);
  await delay(2000);
  const threads = [...new Set(modelRequests.filter((record) => record.label === "ut-avail").map((record) => record.thread))];
  trace("ut.avail", { consentHeld, hooks: hooks().filter((record) => record.receipt > since).map((record) => record.event), threads: threads.length, requests: outcome("ut-avail") });
  await exitTerminal(tui);
});
// `codex exec` asks this process's fixture model for every turn, so it runs
// asynchronously: a synchronous child would block the event loop that serves it.
const runAsync = async (command, args, timeout) => {
  const child = spawn(command, args, { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGKILL"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  return { status, signal, stdout, stderr };
};
const execRun = async (name, args, label) => {
  const since = mark();
  const before = poolCheckouts();
  const gitAt = gitLogLines().length;
  const ran = await runAsync("codex", ["exec", ...args, `SPIKE:${label}`], 120000);
  await delay(1500);
  const start = hookSince(since, (record) => record.event === "SessionStart");
  return { status: ran.status, signal: ran.signal, session: start?.payload.session_id ?? null, cwd: retained(start?.payload.cwd ?? ""), created: newCheckouts(before), git: codexGitSince(gitAt),
    stderrTail: retained(ran.stderr ?? "").split("\n").filter((line) => /worktree|error/i.test(line)).slice(-5) };
};
scenario("exec", async () => {
  availability("ex-avail");
  const ran = await execRun("ex", ["-C", fixture], "ex-avail");
  trace("ex.avail", { ...ran, created: ran.created.map(retained), requests: outcome("ex-avail") });
});
scenario("exec-worktree", async () => {
  plan("cw-run", steps(probeOnce("cw-run", () => [path.join(fixture, ".dashpot", "state", "probe-cw"), "@cwd/probe-cw"])));
  const ran = await execRun("cw", ["--worktree", "-C", fixture], "cw-run");
  const made = ran.created[0] ?? null;
  state.execRoot = made;
  const reader = await loopbackServer("cw-reader");
  const read = ran.session ? await attachmentsOf(reader.client, ran.session) : null;
  const owners = made ? await ownersOf(reader.client, made) : null;
  await reader.stop();
  trace("cw.run", { ...ran, created: ran.created.map(retained), checkout: inspect(made), requests: outcome("cw-run"), attachments: read, owners, refs });
});
scenario("app-server-client", async () => {
  availability("as-avail");
  const server = await loopbackServer("integration");
  const started = await server.client.call("thread/start", { cwd: fixture });
  const threadId = started.result?.thread?.id ?? null;
  const turn = threadId ? await server.client.call("turn/start", { threadId, input: [{ type: "text", text: "SPIKE:as-avail" }] }) : null;
  await settle(() => modelRequests.some((record) => record.label === "as-avail" && record.action === null), "as-avail done", 45000);
  await delay(1500);
  trace("as.avail", { threadId, startError: started.error ?? null, turnError: turn?.error ?? null, requests: outcome("as-avail") });
  await server.stop();
});

// The managed daemon: what a daemon-hosted terminal offers, a creation, and
// a creation whose registration fails because the thread already holds the
// limit of attachments, which a controller filled through the documented
// `thread/attachment/add`. Then the attachments after the daemon restarts.
scenario("daemon", async () => {
  const p = "dm";
  const started = spawnSync("codex", ["app-server", "daemon", "start"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.start", { status: started.status });
  await waitFor(() => existsSync(socketPath) && daemonPid(), "daemon control socket", 30000);
  trace("daemon.socket", { fixtureEntryPresent: sharedEntries().includes(fixtureEntry) });
  availability(`${p}-avail`);
  plan(`${p}-create`, steps(searchFirst, callOnce("create_worktree", { allowAsync: true }), poll, listAll));
  plan(`${p}-full`, steps(searchFirst, callOnce("create_worktree", { allowAsync: true }), poll));
  const { tui, session } = await firstTurn(p, ["-C", fixture], `${p}-avail`);
  trace(`${p}.avail`, { session, requests: outcome(`${p}-avail`) });
  let before = poolCheckouts();
  await promptTurn(tui, `${p}-create`);
  const createdHere = createdRoot(`${p}-create`);
  trace(`${p}.create`, { session, requests: outcome(`${p}-create`), created: newCheckouts(before).map(retained), checkout: inspect(createdHere) });

  const controller = await daemonClient("controller");
  controllers.push(controller);
  const existing = (await controller.call("thread/attachment/list", { threadId: session, limit: 100 })).result?.data?.length ?? 0;
  const fills = [];
  for (let index = 0; index < 100 - existing; index++) {
    const added = await controller.call("thread/attachment/add", { threadId: session, attachmentType: "fixture_marker", identityKey: `fixture-${index}`, payload: { index } });
    fills.push(added.result?.outcome ?? added.error?.message ?? null);
  }
  const overflow = await controller.call("thread/attachment/add", { threadId: session, attachmentType: "fixture_marker", identityKey: "fixture-overflow", payload: {} });
  trace(`${p}.fill`, { existing, added: fills.filter((entry) => entry === "created").length, other: [...new Set(fills.filter((entry) => entry !== "created"))], overflow: overflow.error?.message ?? overflow.result?.outcome ?? null });
  before = poolCheckouts();
  await promptTurn(tui, `${p}-full`);
  const failedRoot = newCheckouts(before)[0] ?? null;
  trace(`${p}.full`, { session, requests: outcome(`${p}-full`), created: newCheckouts(before).map(retained), checkout: inspect(failedRoot),
    attachments: await attachmentsOf(controller, session), owners: { created: await ownersOf(controller, createdHere), failed: await ownersOf(controller, failedRoot) } });
  for (let index = 0; index < 100; index++) await controller.call("thread/attachment/remove", { threadId: session, attachmentType: "fixture_marker", identityKey: `fixture-${index}` });
  controller.close();
  controllers = controllers.filter((client) => client !== controller);
  const exitAt = mark();
  await exitTerminal(tui);
  await settle(() => hookSince(exitAt, (record) => record.event === "SessionEnd" && record.payload.session_id === session), `${p} SessionEnd`, 100000);

  const restarted = spawnSync("codex", ["app-server", "daemon", "restart"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.restart", { status: restarted.status });
  await delay(1000);
  await waitFor(() => existsSync(socketPath) && daemonPid(), "daemon control socket after restart", 30000);
  const after = await daemonClient("after-restart");
  trace(`${p}.restart`, { session, daemonPid: daemonPid(), attachments: await attachmentsOf(after, session), owners: { created: await ownersOf(after, createdHere), failed: await ownersOf(after, failedRoot) } });
  after.close();
  const pid = daemonPid();
  const stopped = spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.stop", { status: stopped.status });
  await settle(() => !pid || !existsSync(`/proc/${pid}`), "daemon gone", 20000);
});

// Dashpot's own preparation in the same Repository, and Dashpot's Cleanup
// check of a Codex-managed checkout and of its own Issue Worktree.
scenario("dashpot", async () => {
  const hookMarkerBefore = existsSync(hookMarker);
  const dry = dashpot(["worktree", "create", "fixture-1", "--dry-run", "--json"]);
  const made = dashpot(["worktree", "create", "fixture-1", "--json"]);
  const plan = parseJson(made.stdout);
  const issuePath = plan?.path ?? null;
  const summary = (result) => { const parsed = parseJson(result.stdout); return parsed ? JSON.parse(retained(JSON.stringify(parsed))) : { status: result.status, stderr: retained(result.stderr).slice(-400) }; };
  const check = (target) => {
    if (!target) return null;
    const ran = dashpot(["worktree", "check", target, "--json"]);
    const parsed = parseJson(ran.stdout);
    return parsed ? { status: ran.status, removable: parsed.removable, kinds: parsed.obstacles.map((obstacle) => obstacle.kind), details: parsed.obstacles.map((obstacle) => retained(obstacle.detail).slice(0, 200)) }
      : { status: ran.status, stderr: retained(ran.stderr).slice(-400) };
  };
  trace("dashpot.compare", { dryRun: summary(dry), create: summary(made), createMs: made.ms, issueCheckout: issuePath ? { head: realGitIn(issuePath, "rev-parse", "HEAD").stdout, branch: realGitIn(issuePath, "symbolic-ref", "-q", "HEAD").stdout,
    ignoredCopied: existsSync(path.join(issuePath, "ignored.txt")), untrackedCopied: existsSync(path.join(issuePath, "untracked.txt")) } : null,
    checks: { managed: check(state.firstRoot), orphan: check(state.orphanRoot), execWorktree: check(state.execRoot), issue: check(issuePath) }, inventory: inventory(), refs, hookMarkerBefore, hookMarker: existsSync(hookMarker) });
  // The same managed checkout as a person sees it: the check's own lines, and
  // the Cleanup preview `worktree remove --dry-run` shows before any removal.
  // The run reads the managed checkout's attachment again afterwards, so the
  // preview is shown against a checkout Codex still holds.
  const lines = dashpot(["worktree", "check", state.firstRoot]);
  const preview = dashpot(["worktree", "remove", state.firstRoot, "--dry-run", "--json"]);
  const reader = await loopbackServer("cleanup-reader");
  const owners = await ownersOf(reader.client, state.firstRoot);
  await reader.stop();
  trace("dashpot.cleanup", { target: retained(state.firstRoot), checkStatus: lines.status, checkLines: retained(lines.stdout).trim().split("\n"),
    previewStatus: preview.status, preview: summary(preview), stillExists: existsSync(state.firstRoot), owners });
});

const scripts = ["run.mjs", "hook.mjs", "probe.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["sessions/hook_publish.py", "sessions/hook_records.py", "repository/worktrees/create.py", "repository/cleanup/obstacles.py"].map((file) => `src/dashpot/${file}`);
const digests = () => Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
  .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")]));
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, git: execFileSync(realGit, ["--version"], { encoding: "utf8" }).trim(),
    binaryTarget: retained(execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim()),
    binarySHA256: createHash("sha256").update(readFileSync(binary)).digest("hex"),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      dirtySource: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean) },
    hookEvents, fixture: retained(fixture), untrusted: retained(untrusted), pool: retained(pool), refs,
    scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name)),
    sharedDaemonDirBefore: sharedBefore.length, sourceSHA256: digests() });

  // Setup: trust the fixture hooks through the ledger on a loopback server.
  trace("scenario", { name: "hook-trust" });
  const trust = await loopbackServer("trust");
  const listed = await trust.client.call("hooks/list", { cwds: [fixture, untrusted] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  const keyed = new Map((listed.result?.data ?? []).flatMap((entry) => entry.hooks ?? []).map((entry) => [entry.key, entry.currentHash]));
  appendFileSync(configPath, "\n" + [...keyed].map(([key, hash]) => `[hooks.state.${JSON.stringify(key)}]\ntrusted_hash = ${JSON.stringify(hash)}\n`).join("\n"));
  const relisted = (await trust.client.call("hooks/list", { cwds: [fixture, untrusted] })).result?.data ?? [];
  trace("hooks.list", { keys: keyed.size, after: relisted.map((entry) => (entry.hooks ?? []).map((hook) => [hook.eventName, hook.trustStatus, hook.enabled])) });
  assert((relisted[0]?.hooks ?? []).every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  await trust.stop();

  for (const { name, run } of scenarios) {
    if (selected && !selected.has(name)) continue;
    trace("scenario", { name });
    try { await run(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 600) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
    for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
    if (existsSync(path.join(holdDir, "hold"))) release();
    await delay(500);
  }
  trace("sources.after", { sourceSHA256: digests() });
  console.log(`Scenarios completed: ${root}`);
} catch (error) {
  trace("runner.error", { error: retained(String(error?.stack ?? error)).slice(0, 2000) });
  throw error;
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
  for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
  writeFileSync(path.join(holdDir, "release"), "");
  if (daemonPid()) spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, timeout: 60000 });
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: codexProcesses().map((entry) => entry.pid) });
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length,
    fixtureEntriesBefore: sharedBefore.filter((name) => name.startsWith(fixtureEntry)).length, fixtureEntriesAfter: sharedAfter.filter((name) => name.startsWith(fixtureEntry)).length });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  writeFileSync(path.join(root, "done"), "");
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
