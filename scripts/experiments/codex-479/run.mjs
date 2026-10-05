// Root-thread Worker run for Issue #479: can a Codex Lead run each Worker as
// a root thread of its own, a detached `codex exec -C <worktree>` its shell
// starts in an Issue Worktree, and coordinate with `codex queue`? Drives a
// pinned Codex CLI against a loopback Responses API fixture with an isolated
// HOME, CODEX_HOME, XDG directories and TMPDIR, whose daemon updater is off,
// and Dashpot's own Codex hook publisher, in a disposable Dashpot Project with
// Local Issue Markdown and nine linked Worktrees. The Lead is a thread on the
// fixture's managed daemon, driven by a controller that keeps a subscriber
// open. The scenarios are those of the Codex evidence note's proposed
// experiment (docs/proposals/lead-worker-codex-evidence.md): launch and
// binding, `codex queue` to an idle, a busy and an unloaded Lead, a queue to
// a running `exec` Worker, `exec resume`, signals, a daemon restart mid-wave,
// a controller thread whose ask has no subscriber, a Lead in the
// workspace-write sandbox, and a Worker under `--approve-for-me`; and, from
// the source review, `codex queue` with configuration overrides, a queue to a
// thread another app-server process holds, and the sandbox and approval
// posture a resumed `exec` Worker runs under. Each step's
// hooks, shells, `codex queue` results, model requests, protocol messages,
// Worker processes and Dashpot's own published view go to a metadata-only
// trace.
//
//   node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset, and
// SPIKE_FIXTURE_PARENT names the directory the fixture is made in.
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

const fixtureParent = process.env.SPIKE_FIXTURE_PARENT ?? os.tmpdir();
mkdirSync(fixtureParent, { recursive: true });
const root = mkdtempSync(path.join(fixtureParent, "dashpot-codex-479-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const worktreeNames = ["a", "b", "c", "d", "e", "f", "g", "h", "i"];
const worktrees = { main: fixture, ...Object.fromEntries(worktreeNames.map((name) => [name, path.join(root, "repository.worktrees", name)])) };
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
  SPIKE_PUBLISHER: publisher,
  SPIKE_DASHPOT: dashpotCommand,
  SPIKE_GATES: gates,
  SPIKE_OUTSIDE: path.join(root, "outside"),
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
// Shell reports a sandbox keeps from the sink, and every Worker's output
// files, live in TMPDIR, which a workspace-write sandbox may write.
env.SPIKE_RECORDS = path.join(env.TMPDIR, "records");
const outDir = path.join(env.TMPDIR, "out");
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
env.SPIKE_DAEMON_SOCKET = socketPath;
for (const dir of [fixture, gates, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME,
  env.SPIKE_OUTSIDE, env.SPIKE_RECORDS, outDir]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: nine Local Issue Markdown Issues, the main
// working tree, and nine linked Worktrees.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of [1, 2, 3, 4, 5, 6, 7, 8, 9]) {
  const metadata = { id: `I_fixture_${number}`, number, reference: `fixture-${number}`, state: "open", stateReason: null, labels: [], assignees: [], author: null,
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `${number}.md`), `---\n${JSON.stringify(metadata, null, 2)}\n---\n# Fixture Issue ${number}\n\nDisposable.\n`);
}
const dashpot = (args, cwd = fixture) => {
  const ran = spawnSync(dashpotCommand, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "" };
};
const initialized = dashpot(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.dashpot/state/\n/.spike-out/\n/.spike-records/\n");
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
for (const name of worktreeNames) git("worktree", "add", "-b", name, worktrees[name]);

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
const stripAnsi = (text) => String(text ?? "").replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "");
env.SPIKE_SINK = sink.url;
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };

// Runner state the fixture model's plans read when a request arrives.
const state = {};

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` (a prompt, a brief, or a
// queued message) selects the plan `plans[label]`; the number of tool outputs
// after that item selects the step. Each step becomes one `exec_command`
// call running command.mjs, optionally followed by a shell launch; when the
// plan runs out, the model answers `DONE:<label>`. Every request records the
// fixture markers its input carries, where and in which kind of item, which
// is how the trace shows when a queued message reached a thread.
const commandScript = path.join(here, "command.mjs");
const encode = (spec) => Buffer.from(JSON.stringify(spec)).toString("base64url");
const run = (spec = {}, extra = {}) => ({ spec, ...extra });
// A long hold is several 20 s holds, since Codex returns an exec call after
// 30 s at most; once the gate is open the rest return at once.
const hold = (gate, count = 3) => Array.from({ length: count }, () => run({ gate, gateMs: 20000 }));
// The detached launch a Lead's shell runs: `setsid -f` so that the Worker
// outlives the command, with its streams in TMPDIR and its exit status
// written when it exits.
// A launch from a sandboxed shell keeps its streams in the launching
// Worktree, since the sandbox leaves TMPDIR read-only.
const outDirs = {};
const launch = (label, { worktree = null, cd = null, resume = null, stamp = false, flags = [], resumeFlags = [], out: dir = outDir, after = "" } = {}) => () => {
  outDirs[label] = dir;
  const out = (ext) => path.join(dir, `${label}.${ext}`);
  const prompt = `SPIKE:${label}/LEAD:${state.lead ?? "none"}`;
  const args = ["exec", ...flags, ...(worktree ? ["-C", worktree] : []), ...(resume ? ["resume", ...resumeFlags, state[resume]] : []), "--json", "-o", out("last"), prompt];
  const inner = `codex ${args.join(" ")} > ${out("jsonl")} 2> ${out("err")} < /dev/null; echo $? > ${out("status")}`;
  return `${dir === outDir ? "" : `mkdir -p ${dir} ; `}${cd ? `cd ${cd} && ` : ""}${stamp ? 'DASHPOT_LEAD="$CODEX_THREAD_ID" ' : ""}setsid -f sh -c '${inner}' < /dev/null > /dev/null 2>&1${after}`;
};
const sandboxOut = path.join(worktrees.main, ".spike-out");
// A detached process with no Codex in it, which shows whether a sandboxed
// command's detached descendants outlive the command.
const sleeper = ` ; setsid -f sh -c 'echo started > ${sandboxOut}/sleeper.started ; sleep 15 ; echo alive > ${sandboxOut}/sleeper.status' < /dev/null > /dev/null 2>&1`;
const toLead = (label, note) => () => ({ queue: { thread: state.lead, message: `SPIKE:${label} NOTE:${note}` } });
const plans = {
  // Lead L, bound to Issue 1 in the main Worktree.
  "l-bind": [run({ work: "start 1" })],
  "l-launch": [run({}, { shell: launch("wa", { worktree: worktrees.a, stamp: true }) }), run({}, { shell: launch("wb", { worktree: worktrees.b }) })],
  "l-show": [run({ work: "show" })],
  "l-to-b": [run(() => ({ queue: { thread: state.wb, message: "NOTE:to-wb" } }))],
  "l-busy": hold("l-busy-go", 3),
  "l-resume": [run({}, { shell: launch("wa-r", { cd: worktrees.a, resume: "wa" }) }), run({}, { shell: launch("wb-r", { worktree: worktrees.b, resume: "wb" }) })],
  "l-signal": [run({}, { shell: launch("wc", { worktree: worktrees.c }) }), run({}, { shell: launch("wd", { worktree: worktrees.d }) }),
    run({}, { shell: launch("we", { worktree: worktrees.e }) })],
  "l-approve": [run({}, { shell: launch("wg", { worktree: worktrees.g, flags: ["--approve-for-me"] }) })],
  "l-wave": [run({}, { shell: launch("wf", { worktree: worktrees.f }) })],
  // A Worker launched into the workspace-write sandbox, then resumed bare,
  // with `exec -s` before `resume`, and with `-c sandbox_mode` after it.
  "l-posture": [run({}, { shell: launch("wp", { worktree: worktrees.i, flags: ["-s", "workspace-write"] }) })],
  "l-posture-r1": [run({}, { shell: launch("wp-r1", { worktree: worktrees.i, resume: "wp" }) })],
  "l-posture-r2": [run({}, { shell: launch("wp-r2", { worktree: worktrees.i, resume: "wp", flags: ["-s", "workspace-write"] }) })],
  "l-posture-r3": [run({}, { shell: launch("wp-r3", { worktree: worktrees.i, resume: "wp", resumeFlags: ["-c", "sandbox_mode=workspace-write"] }) })],
  wp: [run({ probe: true })], "wp-r1": [run({ probe: true })], "wp-r2": [run({ probe: true })], "wp-r3": [run({ probe: true })],
  // A thread a separate stdio app-server holds.
  "x-first": [run({})],
  // Messages queued to the Lead each name a plan with no steps.
  ...Object.fromEntries(["l-mail-a", "l-mail-b", "l-mail-f", "l-mail-g", "l-mail-s", "l-mail-s0", "l-mail-o1", "l-mail-o2", "l-mail-o3", "u-first", "u-mail", "x-mail1", "x-mail2"].map((label) => [label, []])),
  // Workers.
  wa: [run({ work: "start 2" }), run({ work: "show" }), ...hold("a-hold", 7), run({ work: "stop" }), run(toLead("l-mail-a", "wa-done"))],
  wb: [run({ work: "start 3" }), run({ work: "show" }), ...hold("b-hold", 6), run(toLead("l-mail-b", "wb-done"))],
  "wa-r": [run({ work: "start 2" }), run({ work: "show" })],
  "wb-r": [run({ work: "start 3" }), run({ work: "show" }), run({ work: "stop" })],
  wc: [run({ work: "start 4" }), ...hold("sig-go", 3)],
  wd: [run({ work: "start 5" }), ...hold("sig-go", 3)],
  we: [run({ work: "start 6" }), ...hold("sig-go", 3)],
  wf: [run({ work: "start 7" }), ...hold("f-hold", 12), run(toLead("l-mail-f", "wf-done"))],
  wg: [run(() => ({ work: "start 8", probe: true, ...toLead("l-mail-g", "wg")() }))],
  // Controller threads whose policy asks.
  "k1-ask": [run({})], "k2-ask": [run({})],
  // Lead S, in the workspace-write sandbox: a probe, an ordinary launch, then
  // the same launch with escalation, of a Worker that is itself sandboxed.
  "s-launch": [run(() => ({ probe: true, ...toLead("l-mail-s0", "s-probe")() })), run({}, { shell: launch("wsx", { worktree: worktrees.h, out: sandboxOut, after: sleeper }) }),
    run({}, { shell: launch("ws", { worktree: worktrees.h, flags: ["-s", "workspace-write"], out: sandboxOut }), escalate: true })],
  ws: [run(() => ({ work: "start 9", probe: true, ...toLead("l-mail-s", "ws")() }))],
  wsx: [run({ probe: true })],
};
const markerPattern = /(SPIKE|NOTE|DONE):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const modelRequests = [];
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const seenThreads = new Set();
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
  const session = payload.client_metadata?.session_id ?? req.headers["session_id"] ?? null;
  const input = payload.input ?? [];
  let directiveAt = -1;
  let label = null;
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].filter((match) => match[1] === "SPIKE");
    if (found.length) { directiveAt = index; label = found.at(-1)[2]; }
  });
  const markers = input.flatMap((item, index) => [...new Set([...JSON.stringify(item).matchAll(markerPattern)].map((match) => match[0]))]
    .map((marker) => [index, item.type ?? null, item.role ?? null, marker]));
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name, nested]) : [[null, tool.name ?? tool.type, tool]]);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const execTool = offered("exec_command");
  // The shell tool's parameters, once per thread: the escalation the
  // sandboxed Lead uses is one of them.
  const firstForThread = !seenThreads.has(thread);
  seenThreads.add(thread);
  const execParams = firstForThread && execTool ? Object.fromEntries(Object.entries(execTool[2].parameters?.properties ?? {}).map(([key, value]) => [key, value.enum ?? value.type ?? null])) : undefined;
  const plan = label ? plans[label] ?? [] : [];
  let step = plan[outputs.length] ?? null;
  let item = null;
  let action = null;
  if (step && execTool) {
    const spec = typeof step.spec === "function" ? step.spec() : step.spec;
    const shellText = `node ${commandScript} ${encode({ label: `${label}.${outputs.length}`, ...spec })}${step.shell ? ` ; ${step.shell()}` : ""}`;
    action = step.shell ? "launch" : "exec_command";
    item = { type: "function_call", call_id: `call_${label}_${outputs.length}_${records.length}`, ...(execTool[0] ? { namespace: execTool[0] } : {}), name: "exec_command",
      arguments: JSON.stringify({ cmd: shellText, login: false, yield_time_ms: 30000,
        ...(step.escalate ? { sandbox_permissions: "require_escalated", justification: "Launch an Issue Worker outside the sandbox" } : {}) }) };
  }
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const request = trace("model.request", { thread, session, model: payload.model ?? null, label, step: outputs.length, inputItems: input.length, directiveAt, markers, action,
    escalate: Boolean(step?.escalate), missing: Boolean(step && !item), execParams,
    // Whether the latest tool output reports a sandbox refusal; its text stays out.
    lastOutputDenied: latestOutput ? /denied|not permitted|Operation not permitted|EACCES|EPERM|sandbox/i.test(String(latestOutput.output ?? "")) : null,
    tail: input.slice(-3).map((entry) => [entry.type ?? null, entry.role ?? null]) });
  modelRequests.push(request);
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
writeFileSync(configPath, `model = "fixture-model"
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

# The fixture lives under /tmp, which workspace-write would otherwise leave
# writable, and CODEX_HOME with it; an operator's ~/.codex is not.
[sandbox_workspace_write]
exclude_slash_tmp = true
exclude_tmpdir_env_var = true

[model_providers.fixture]
name = "Fixture"
base_url = "${model.url}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
${Object.values(worktrees).map((dir) => `\n[projects."${dir}"]\ntrust_level = "trusted"\n`).join("")}`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const daemonSettings = () => parseJson(existsSync(daemonSettingsPath) ? readFileSync(daemonSettingsPath, "utf8") : "") ?? { unreadable: true };
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run only counts its entries and never removes any.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

// Every process whose environment names the fixture's CODEX_HOME or gates.
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
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, retained(entry.cmdline).slice(0, 200), entry.cwd ? retained(entry.cwd) : null];
// The managed daemon names itself in its pid file.
const daemonPidPath = path.join(env.CODEX_HOME, "app-server-daemon", "daemon.pid");
const daemonPid = () => { const pid = parseJson(existsSync(daemonPidPath) ? readFileSync(daemonPidPath, "utf8") : "")?.pid; return pid && existsSync(`/proc/${pid}`) ? pid : null; };
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
const hooks = () => records.filter((record) => record.kind === "hook");
const mark = () => records.length;
const hooksSince = (since, predicate = () => true) => hooks().filter((record) => record.receipt > since && predicate(record));
const command = (label, phase = "start") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const threadOf = (label) => command(label)?.env.CODEX_THREAD_ID ?? null;
// A Worker's `codex exec` process: the nearest Codex process above its shell.
const execPidOf = (label) => command(label)?.ancestry.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const settle = async (predicate, label, timeout) => {
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};
const open = (gate) => { writeFileSync(path.join(gates, gate), ""); trace("gate", { gate }); };
const requestsOf = (thread, since = 0) => modelRequests.filter((record) => record.thread === thread && record.receipt > since);
// Hooks in a window, as [receipt, event, session, turn, cwd, markers, nearest Codex pid].
const timeline = (since, sessions = null) => hooksSince(since, (record) => !sessions || sessions.includes(record.payload.session_id))
  .map((record) => [record.receipt, record.event, record.payload.session_id, record.payload.turn_id ?? null, record.payload.cwd ?? null, record.markers ?? null,
    record.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null, record.receiptTime]);

// A Worker's own output: its exit status, the `--json` event types and
// thread, and whether `-o` wrote a last message, never the message itself.
const workerOutput = (label) => {
  const read = (ext) => { try { return readFileSync(path.join(outDirs[label] ?? outDir, `${label}.${ext}`), "utf8"); } catch { return null; } };
  const events = (read("jsonl") ?? "").split("\n").filter(Boolean).map(parseJson).filter(Boolean);
  const stderr = stripAnsi(read("err") ?? "").split("\n").filter((line) => /^(warning|Error|error|ERROR|WARN|hook)/i.test(line.trim())).slice(-8).map((line) => line.slice(0, 240));
  return { status: read("status")?.trim() ?? null, eventTypes: events.map((event) => event.type), thread: events.find((event) => event.type === "thread.started")?.thread_id ?? null,
    lastMessageMarkers: read("last") === null ? null : [...(read("last") ?? "").matchAll(markerPattern)].map((match) => match[0]), stderr };
};
// Records a sandboxed shell kept in files, traced once each.
const ingested = new Set();
const ingest = () => {
  for (const dir of [env.SPIKE_RECORDS, ...Object.values(worktrees).map((worktree) => path.join(worktree, ".spike-records"))]) {
    let files = [];
    try { files = readdirSync(dir).sort(); } catch { continue; }
    for (const file of files) {
      if (ingested.has(file)) continue;
      ingested.add(file);
      const record = parseJson(readFileSync(path.join(dir, file), "utf8"));
      if (record) trace("command", { ...record, viaFile: true });
    }
  }
};

// Dashpot's published view: its Agent Runs, diagnostics, and each named
// Worktree's Cleanup check.
const check = (worktree) => {
  const ran = spawnSync(dashpotCommand, ["worktree", "check", worktree, "--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  const parsed = parseJson(ran.stdout);
  if (!parsed) return { status: ran.status, stderr: retained(ran.stderr ?? "").slice(-400) };
  return { status: ran.status, removable: parsed.removable,
    blockers: parsed.obstacles.map((obstacle) => ({ kind: obstacle.kind,
      sessions: [...new Set([...obstacle.detail.matchAll(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/g)].map((match) => match[1]))],
      processes: obstacle.kind === "process" ? [...obstacle.detail.matchAll(/pid (\d+) \(([^)]*)\)/g)].map((match) => [Number(match[1]), match[2]]) : undefined,
      detail: retained(obstacle.detail).slice(0, 500) })) };
};
const snapshot = (label, names = []) => {
  const ran = dashpot(["--compact-json"]);
  const parsed = parseJson(ran.stdout);
  return trace("snapshot", { label, status: ran.status, stderr: retained(ran.stderr).slice(0, 300),
    agentRuns: (parsed?.agentRuns ?? []).map((agentRun) => ({ issueId: agentRun.issueId, state: agentRun.state, host: agentRun.processOrSession, workingDirectory: agentRun.workingDirectory,
      orphaned: agentRun.orphaned, startedAt: agentRun.startedAt, id: agentRun.id })),
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: retained(String(diagnostic.message ?? "")).slice(0, 300) })),
    checks: Object.fromEntries(names.map((name) => [name, check(worktrees[name])])),
    processes: fixtureProcesses().map(brief), daemon: daemonPid() });
};

// One-shot Codex commands, launched by name through the fixture PATH.
const codex = async (args, label, { cwd = fixture, timeout = 60000 } = {}) => {
  const startedAt = Date.now();
  const child = spawn("codex", args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const statusLines = (text) => stripAnsi(text).split("\n").filter((line) => /^(warning: |Error: |error: |WARNING)/.test(line)).join("\n");
  return trace("codex.command", { label, args: args.map(retained), status, signal, startedAt, endedAt: Date.now(), stdout: retained(stripAnsi(stdout)).slice(-600), stderr: retained(statusLines(stderr)).slice(-1200) });
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
// socket, which speaks WebSocket over a Unix domain socket. A server request,
// such as an approval, is traced, and answered when `answer` returns a result.
const relevant = (method) => /^turn\/(started|completed)$|^thread\/(closed|started|status\/changed)$|queue|serverRequest/i.test(method);
const rpcClient = async (name, socket, answer = () => null) => {
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  const requests = [];
  socket.on((text) => {
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && parsed.method === undefined) { pending.get(parsed.id)?.(parsed); pending.delete(parsed.id); return; }
    const params = parsed.params ?? {};
    if (parsed.id !== undefined) {
      const entry = { client: name, method: parsed.method, requestId: parsed.id, threadId: params.threadId ?? params.conversationId ?? null, turnId: params.turnId ?? null,
        itemId: params.itemId ?? params.callId ?? null, paramKeys: Object.keys(params).sort(), receivedAt: Date.now() };
      requests.push(entry);
      const result = answer(entry);
      trace("server.request", { ...entry, answered: result ?? null });
      if (result) socket.send(JSON.stringify({ id: parsed.id, result }));
      return;
    }
    if (!parsed.method || !relevant(parsed.method)) return;
    const entry = { client: name, method: parsed.method, threadId: params.threadId ?? params.thread?.id ?? null, turnId: params.turn?.id ?? params.turnId ?? null,
      status: params.status?.type ?? params.status ?? params.turn?.status ?? null, receivedAt: Date.now() };
    notifications.push(entry);
    trace("notification", entry);
  });
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-479-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, transport: socket.transport, error: init.error ?? null });
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, notifications, requests, close: () => socket.close() };
};
const daemonClient = async (name, answer) => {
  const socket = await connectUnixWebSocket(socketPath);
  return rpcClient(name, { transport: "unix-websocket", on: (listener) => socket.on("message", listener), send: (text) => socket.send(text), close: () => socket.close() }, answer);
};
const accept = (entry) => /requestApproval$/.test(entry.method) ? { decision: "accept" } : /^(execCommandApproval|applyPatchApproval)$/.test(entry.method) ? { decision: "approved" } : null;
const completedTurn = (client, turnId) => client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
const runTurn = async (client, threadId, text, options = {}) => {
  const since = mark();
  const startedAt = Date.now();
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, status: started.result?.turn?.status ?? null, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  if (options.detached) return { turnId, since, startedAt };
  await waitFor(() => completedTurn(client, turnId), `turn ${text} completed`, options.timeout ?? 60000);
  await settle(() => hooksSince(since).some((record) => record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000);
  return { turnId, since, startedAt, status: completedTurn(client, turnId).status, completedAt: completedTurn(client, turnId).receivedAt };
};
const startThread = async (client, name, params = {}) => {
  const started = await client.call("thread/start", { cwd: fixture, model: "fixture-model", ...params });
  const thread = started.result?.thread;
  trace("thread.start", { client: client.name, name, params: { ...params, cwd: params.cwd ?? fixture }, thread: thread && { id: thread.id, cwd: thread.cwd, status: thread.status },
    error: started.error ?? null });
  assert(thread?.id, `${name} started: ${JSON.stringify(started.error)}`);
  return thread.id;
};
const loadedThreads = async (client) => (await client.call("thread/loaded/list", {})).result?.data ?? [];
const exited = (label) => existsSync(path.join(outDirs[label] ?? outDir, `${label}.status`));
const sessionEnded = (since, session) => hooksSince(since).some((record) => record.event === "SessionEnd" && record.payload.session_id === session);

const scenarios = [];
const scenario = (name, body) => scenarios.push({ name, body });
let c1 = null;
let controllers = [];

// 1. The Lead's shell starts two detached `codex exec -C` Workers, A in
// Worktree a with the Lead's thread stamped as DASHPOT_LEAD, and B in b. Each
// binds its own Issue with `work start`, reads `work show`, and holds.
scenario("launch", async () => {
  const since = mark();
  const launched = await runTurn(c1, state.lead, "SPIKE:l-launch");
  await waitFor(() => command("wa.2") && command("wb.2"), "both Workers hold", 90000);
  state.wa = threadOf("wa.0");
  state.wb = threadOf("wb.0");
  await delay(1500);
  const shown = await runTurn(c1, state.lead, "SPIKE:l-show");
  const held = snapshot("launch-held", ["main", "a", "b"]);
  trace("launch.outcome", { lead: state.lead, workerA: state.wa, workerB: state.wb, launchTurn: launched.turnId, showTurn: shown.turnId,
    execPids: { wa: execPidOf("wa.0"), wb: execPidOf("wb.0") }, exec: { wa: processState(execPidOf("wa.0")), wb: processState(execPidOf("wb.0")) },
    shells: ["l-launch.0", "l-launch.1", "wa.0", "wa.1", "wb.0", "wb.1", "l-show.0"].map((label) => command(label)?.receipt ?? null),
    hooks: timeline(since), snapshot: held.receipt });
});

// 3. The Lead queues a message to running Worker B, which holds a command;
// B's later requests show whether and when the message reaches it.
scenario("lead-to-worker", async () => {
  const since = mark();
  const turn = await runTurn(c1, state.lead, "SPIKE:l-to-b");
  await waitFor(() => command("l-to-b.0", "queue"), "the Lead's queue result", 30000);
  // Long enough for a 10 s poll, and for one of B's holds to return.
  await delay(24000);
  trace("lead-to-worker.outcome", { turn: turn.turnId, queue: command("l-to-b.0", "queue")?.queue ?? null, workerRequests: requestsOf(state.wb, since).map((record) => record.receipt) });
});

// 2. Worker B queues to the Lead while the Lead's turn holds a command.
scenario("queue-busy", async () => {
  const since = mark();
  const busy = await runTurn(c1, state.lead, "SPIKE:l-busy", { detached: true });
  await waitFor(() => command("l-busy.0"), "the Lead holds", 30000);
  open("b-hold");
  await waitFor(() => records.some((record) => record.kind === "command" && record.phase === "queue" && record.label.startsWith("wb.")), "B's queue to the busy Lead", 60000);
  const queued = records.find((record) => record.kind === "command" && record.phase === "queue" && record.label.startsWith("wb.") && record.receipt > since);
  await delay(15000);
  const beforeRelease = mark();
  open("l-busy-go");
  await waitFor(() => completedTurn(c1, busy.turnId), "the busy turn completes", 90000);
  // A turn the queued message may start once the busy one ends.
  await delay(15000);
  trace("queue-busy.outcome", { busyTurn: busy.turnId, queue: queued?.queue ?? null, queuedReceipt: queued?.receipt ?? null, releasedAt: records[beforeRelease]?.receiptTime ?? null,
    leadRequests: requestsOf(state.lead, since).map((record) => record.receipt), turns: c1.notifications.filter((entry) => entry.threadId === state.lead && entry.receivedAt > busy.startedAt)
      .map((entry) => [entry.method, entry.turnId, entry.status, entry.receivedAt]), hooks: timeline(since, [state.lead]) });
  await settle(() => exited("wb"), "Worker B exits", 60000);
});

// 2. Worker A stops its run and queues to the idle Lead, whose controller
// still subscribes.
scenario("queue-idle", async () => {
  const since = mark();
  open("a-hold");
  await waitFor(() => records.some((record) => record.kind === "command" && record.phase === "queue" && record.label.startsWith("wa.")), "A's queue to the idle Lead", 60000);
  const queued = records.find((record) => record.kind === "command" && record.phase === "queue" && record.label.startsWith("wa.") && record.receipt > since);
  await settle(() => c1.notifications.some((entry) => entry.method === "turn/completed" && entry.threadId === state.lead && entry.receivedAt > queued.queue.startedAt), "the queued turn completes", 40000);
  await settle(() => exited("wa"), "Worker A exits", 60000);
  await delay(3000);
  trace("queue-idle.outcome", { queue: queued?.queue ?? null, queuedReceipt: queued?.receipt ?? null,
    turns: c1.notifications.filter((entry) => entry.threadId === state.lead && entry.receivedAt > queued.queue.startedAt).map((entry) => [entry.method, entry.turnId, entry.status, entry.receivedAt]),
    leadRequests: requestsOf(state.lead, since).map((record) => [record.receipt, record.label, record.receiptTime]), hooks: timeline(since),
    workers: { wa: workerOutput("wa"), wb: workerOutput("wb") }, exec: { wa: processState(execPidOf("wa.0")), wb: processState(execPidOf("wb.0")) },
    workerBRequests: requestsOf(state.wb).map((record) => [record.receipt, record.step, record.markers.filter(([, , , marker]) => marker.startsWith("NOTE")).map(([index, type, role, marker]) => [index, type, role, marker])]) });
  snapshot("after-wave", ["main", "a", "b"]);
});

// From the source review: `codex queue` with a configuration override that is
// not a feature flag uses an embedded app-server, which it refuses while a
// daemon runs; a feature-flag override and `--no-daemon` beside it.
scenario("queue-overrides", async () => {
  const since = mark();
  const attempts = {
    o1: ["queue", "-c", 'model="fixture-model"', "--thread", state.lead, "--message", "SPIKE:l-mail-o1 NOTE:o1"],
    o2: ["queue", "-c", "features.hooks=true", "--thread", state.lead, "--message", "SPIKE:l-mail-o2 NOTE:o2"],
    o3: ["queue", "--no-daemon", "--thread", state.lead, "--message", "SPIKE:l-mail-o3 NOTE:o3"],
  };
  const results = {};
  for (const [name, args] of Object.entries(attempts)) {
    results[name] = await codex(args, `queue-${name}`);
    await delay(2000);
  }
  await delay(15000);
  trace("queue-overrides.outcome", { results: Object.fromEntries(Object.entries(results).map(([name, ran]) => [name, { status: ran.status, stdout: ran.stdout, stderr: ran.stderr, receipt: ran.receipt }])),
    leadRequests: requestsOf(state.lead, since).map((record) => [record.receipt, record.label, record.receiptTime]) });
});

// 4. The Lead's shell resumes A by `cd a && codex exec resume`, and B by
// `codex exec -C b resume` from the Lead's own directory.
scenario("resume", async () => {
  const since = mark();
  await runTurn(c1, state.lead, "SPIKE:l-resume");
  await settle(() => exited("wa-r") && exited("wb-r"), "both resumed Workers exit", 90000);
  await delay(3000);
  trace("resume.outcome", { workerA: state.wa, workerB: state.wb, workers: { "wa-r": workerOutput("wa-r"), "wb-r": workerOutput("wb-r") },
    shells: ["wa-r.0", "wa-r.1", "wb-r.0", "wb-r.1", "wb-r.2"].map((label) => command(label)?.receipt ?? null), hooks: timeline(since, [state.wa, state.wb]),
    requests: { wa: requestsOf(state.wa, since).map((record) => [record.receipt, record.label, record.step]), wb: requestsOf(state.wb, since).map((record) => [record.receipt, record.label, record.step,
      record.markers.filter(([, , , marker]) => marker.startsWith("NOTE")).map(([, , , marker]) => marker)]) } });
  snapshot("after-resume", ["a", "b"]);
});

// From the source review: Worker P starts under `exec -s workspace-write`,
// then is resumed bare, with `exec -s workspace-write` before `resume`, and
// with `-c sandbox_mode=workspace-write` after it; each turn's probe shows
// the posture its shell runs under.
const postureLabels = ["wp", "wp-r1", "wp-r2", "wp-r3"];
scenario("resume-posture", async () => {
  const since = mark();
  await runTurn(c1, state.lead, "SPIKE:l-posture");
  await settle(() => exited("wp"), "Worker P exits", 60000);
  state.wp = workerOutput("wp").thread;
  for (const label of postureLabels.slice(1)) {
    await runTurn(c1, state.lead, `SPIKE:l-posture-${label.slice(3)}`);
    await settle(() => exited(label), `${label} exits`, 60000);
  }
  await delay(2000);
  ingest();
  trace("resume-posture.outcome", { thread: state.wp, workers: Object.fromEntries(postureLabels.map((label) => [label, workerOutput(label)])),
    probes: Object.fromEntries(postureLabels.map((label) => [label, records.filter((record) => record.kind === "command" && record.label === `${label}.0` && record.phase === "end")
      .map((record) => ({ receipt: record.receipt, probe: record.probe ?? null, viaFile: Boolean(record.viaFile), postError: record.postError ?? null }))])),
    hooks: hooksSince(since, (record) => record.payload.session_id === state.wp).map((record) => [record.receipt, record.event, record.payload.turn_id ?? null, record.payload.permission_mode ?? null, record.markers ?? null]) });
});

// 2. A message queued to a Lead the daemon has unloaded: thread U was left by
// its last client at setup.
scenario("queue-unloaded", async () => {
  const since = mark();
  await settle(() => sessionEnded(0, state.unloaded), "U unloads", 120000);
  const loadedBefore = await loadedThreads(c1);
  const queued = await codex(["queue", "--thread", state.unloaded, "--message", "SPIKE:u-mail NOTE:u"], "queue-unloaded");
  await delay(25000);
  const loadedAfterQueue = await loadedThreads(c1);
  const quiet = { hooks: timeline(since, [state.unloaded]), requests: requestsOf(state.unloaded, since).map((record) => record.receipt) };
  const resumedAt = Date.now();
  const resumed = await c1.call("thread/resume", { threadId: state.unloaded });
  trace("thread.resume", { client: c1.name, threadId: state.unloaded, error: resumed.error ?? null, status: resumed.result?.thread?.status ?? null });
  await settle(() => requestsOf(state.unloaded, since).some((record) => record.label === "u-mail"), "the queued message reaches U", 40000);
  await delay(3000);
  trace("queue-unloaded.outcome", { thread: state.unloaded, leftAt: state.unloadedLeftAt, queue: { status: queued.status, startedAt: queued.startedAt, endedAt: queued.endedAt },
    loadedBefore: loadedBefore.includes(state.unloaded), loadedAfterQueue: loadedAfterQueue.includes(state.unloaded), beforeResume: quiet, resumedAt,
    afterResume: { hooks: timeline(since, [state.unloaded]).filter((entry) => entry[7] >= resumedAt), requests: requestsOf(state.unloaded, since).filter((record) => record.receiptTime >= resumedAt).map((record) => [record.receipt, record.label, record.receiptTime]),
      turns: c1.notifications.filter((entry) => entry.threadId === state.unloaded && entry.receivedAt >= resumedAt).map((entry) => [entry.method, entry.turnId, entry.status, entry.receivedAt]) } });
  await c1.call("thread/unsubscribe", { threadId: state.unloaded });
});

// From the source review: a message queued to a thread that a separate
// stdio app-server holds, not the daemon, reaches it through that server's
// 10 s poll of the queue store.
scenario("queue-cross-process", async () => {
  const server = spawn("codex", ["app-server"], { cwd: fixture, env, stdio: ["pipe", "pipe", "pipe"] });
  server.stderr.on("data", () => {});
  let buffer = "";
  const listeners = [];
  server.stdout.on("data", (chunk) => {
    buffer += chunk;
    let index;
    while ((index = buffer.indexOf("\n")) >= 0) { const line = buffer.slice(0, index); buffer = buffer.slice(index + 1); for (const listener of listeners) listener(line); }
  });
  const sx = await rpcClient("stdio-server", { transport: "stdio", on: (listener) => listeners.push(listener), send: (text) => server.stdin.write(text + "\n"), close: () => server.stdin.end() }, accept);
  const x = await startThread(sx, "x");
  await runTurn(sx, x, "SPIKE:x-first");
  const samples = [];
  for (const n of [1, 2]) {
    await delay(n === 1 ? 3000 : 6500);
    const before = mark();
    const queued = await codex(["queue", "--thread", x, "--message", `SPIKE:x-mail${n} NOTE:x${n}`], `queue-x${n}`);
    const startedOn = () => sx.notifications.find((entry) => entry.method === "turn/started" && entry.threadId === x && entry.receivedAt >= queued.startedAt);
    await settle(() => startedOn() || requestsOf(x, before).length, `the queued x-mail${n} runs`, 30000);
    await settle(() => sx.notifications.some((entry) => entry.method === "turn/completed" && entry.threadId === x && entry.receivedAt >= queued.startedAt), `x-mail${n} completes on the stdio server`, 15000);
    const turn = startedOn();
    samples.push({ n, queue: { status: queued.status, startedAt: queued.startedAt, endedAt: queued.endedAt, stdout: queued.stdout, stderr: queued.stderr },
      turnStartedAt: turn?.receivedAt ?? null, latencyMs: turn ? turn.receivedAt - queued.endedAt : null, daemonLoaded: (await loadedThreads(c1)).includes(x),
      requests: requestsOf(x, before).map((record) => [record.receipt, record.label, record.receiptTime]), hooks: timeline(before, [x]) });
  }
  trace("queue-cross-process.outcome", { thread: x, serverPid: server.pid, daemon: daemonPid(), samples });
  sx.close();
  await Promise.race([once(server, "exit"), delay(5000)]);
  if (server.exitCode === null) server.kill("SIGTERM");
});

// 5. SIGINT, SIGTERM and SIGKILL to three `exec` Workers while each holds a
// command after binding its Issue.
scenario("signals", async () => {
  const since = mark();
  await runTurn(c1, state.lead, "SPIKE:l-signal");
  await waitFor(() => command("wc.1") && command("wd.1") && command("we.1"), "the three Workers hold", 90000);
  await delay(1500);
  const workers = { wc: "SIGINT", wd: "SIGTERM", we: "SIGKILL" };
  const pids = Object.fromEntries(Object.keys(workers).map((label) => [label, { exec: execPidOf(`${label}.1`), shell: command(`${label}.1`).ppid, command: command(`${label}.1`).pid }]));
  snapshot("signals-held", ["c", "d", "e"]);
  const sentAt = {};
  for (const [label, signal] of Object.entries(workers)) { sentAt[label] = Date.now(); process.kill(pids[label].exec, signal); trace("signal", { label, signal, pid: pids[label].exec }); }
  await delay(8000);
  const after = Object.fromEntries(Object.keys(workers).map((label) => [label, { exec: processState(pids[label].exec), shell: processState(pids[label].shell), command: processState(pids[label].command),
    status: workerOutput(label).status }]));
  snapshot("signals-after", ["c", "d", "e"]);
  await delay(12000);
  snapshot("signals-settled", ["c", "d", "e"]);
  open("sig-go");
  await delay(4000);
  const released = Object.fromEntries(Object.keys(workers).map((label) => [label, { command: processState(pids[label].command), ended: Boolean(command(`${label}.1`, "end")) }]));
  snapshot("signals-released", ["c", "d", "e"]);
  trace("signals.outcome", { workers, pids, sentAt, after, released, threads: Object.fromEntries(Object.keys(workers).map((label) => [label, threadOf(`${label}.0`)])),
    outputs: Object.fromEntries(Object.keys(workers).map((label) => [label, workerOutput(label)])), hooks: timeline(since, Object.keys(workers).map((label) => threadOf(`${label}.0`))) });
});

// 7. Controller threads whose policy asks: K1 and K2 each ask before their
// first command while client 3 subscribes, and client 3 leaves without
// answering. Client 4 resumes K1 20 s later and answers what it is sent; K2
// is left to the unload, and client 5 resumes it afterwards.
scenario("asking-controller", async () => {
  const since = mark();
  const c3 = await daemonClient("controller-3");
  const k1 = await startThread(c3, "k1", { approvalPolicy: "untrusted" });
  const k2 = await startThread(c3, "k2", { approvalPolicy: "untrusted" });
  const t1 = await runTurn(c3, k1, "SPIKE:k1-ask", { detached: true });
  const t2 = await runTurn(c3, k2, "SPIKE:k2-ask", { detached: true });
  await settle(() => c3.requests.some((entry) => entry.threadId === k1) && c3.requests.some((entry) => entry.threadId === k2), "both asks reach client 3", 30000);
  c3.close();
  const leftAt = Date.now();
  trace("client.close", { client: c3.name });
  await delay(20000);
  const c4 = await daemonClient("controller-4", accept);
  controllers.push(c4);
  const resumed = await c4.call("thread/resume", { threadId: k1 });
  trace("thread.resume", { client: c4.name, threadId: k1, error: resumed.error ?? null, status: resumed.result?.thread?.status ?? null,
    turns: (resumed.result?.thread?.turns ?? []).map((turn) => [turn.id, turn.status]) });
  await settle(() => c4.requests.some((entry) => entry.threadId === k1), "the ask is replayed to client 4", 10000);
  await settle(() => command("k1-ask.0", "end"), "K1's command runs once answered", 20000);
  await settle(() => sessionEnded(since, k2), "K2 unloads with its ask pending", 110000);
  const k2EndedAt = hooksSince(since).find((record) => record.event === "SessionEnd" && record.payload.session_id === k2)?.receiptTime ?? null;
  const loaded = await loadedThreads(c1);
  const c5 = await daemonClient("controller-5", () => null);
  controllers.push(c5);
  const late = await c5.call("thread/resume", { threadId: k2 });
  trace("thread.resume", { client: c5.name, threadId: k2, error: late.error ?? null, status: late.result?.thread?.status ?? null,
    turns: (late.result?.thread?.turns ?? []).map((turn) => [turn.id, turn.status]) });
  await delay(6000);
  trace("asking-controller.outcome", { k1, k2, turns: { k1: t1.turnId, k2: t2.turnId }, leftAt, k2EndedAt, k2Loaded: loaded.includes(k2), k1Loaded: loaded.includes(k1),
    asked: { c3: c3.requests.map((entry) => [entry.method, entry.threadId, entry.turnId, entry.itemId, entry.requestId]), c4: c4.requests.map((entry) => [entry.method, entry.threadId, entry.turnId, entry.itemId, entry.requestId]),
      c5: c5.requests.map((entry) => [entry.method, entry.threadId, entry.turnId, entry.itemId, entry.requestId]) },
    commands: { k1: Boolean(command("k1-ask.0")), k2: Boolean(command("k2-ask.0")) }, hooks: timeline(since, [k1, k2]),
    notifications: [c4, c5].flatMap((client) => client.notifications.filter((entry) => [k1, k2].includes(entry.threadId)).map((entry) => [client.name, entry.method, entry.threadId, entry.turnId, entry.status])) });
  await c4.call("thread/unsubscribe", { threadId: k1 });
  await c5.call("thread/unsubscribe", { threadId: k2 });
});

// 8. Lead S runs in the workspace-write sandbox with an on-request policy:
// it probes what its shell reaches, launches a Worker as Lead L does, then
// launches one with escalation, which its controller approves; that Worker
// is itself sandboxed and queues to Lead L.
scenario("sandboxed-lead", async () => {
  const since = mark();
  const leadS = await startThread(c1, "lead-s", { sandbox: "workspace-write", approvalPolicy: "on-request" });
  state.leadS = leadS;
  const turn = await runTurn(c1, leadS, "SPIKE:s-launch", { timeout: 90000 });
  await settle(() => exited("ws") && exited("wsx"), "both sandboxed launches exit", 60000);
  await delay(4000);
  // The sleeper's 15 s, counted from the end of the launching turn.
  while (Date.now() < turn.completedAt + 18000) await delay(500);
  const sleeper = { started: existsSync(path.join(sandboxOut, "sleeper.started")), alive: existsSync(path.join(sandboxOut, "sleeper.status")) };
  ingest();
  trace("sandboxed-lead.outcome", { lead: leadS, turn: turn.turnId, status: turn.status, sleeper, asks: c1.requests.filter((entry) => entry.threadId === leadS).map((entry) => [entry.method, entry.turnId, entry.itemId]),
    requests: requestsOf(leadS, since).map((record) => [record.receipt, record.step, record.action, record.escalate, record.lastOutputDenied]),
    workers: { ws: workerOutput("ws"), wsx: workerOutput("wsx") }, threads: { ws: threadOf("ws.0"), wsx: threadOf("wsx.0") },
    shells: ["s-launch.0", "s-launch.1", "s-launch.2", "ws.0", "wsx.0"].map((label) => records.filter((record) => record.kind === "command" && record.label === label).map((record) => [record.phase, record.receipt, Boolean(record.viaFile)])),
    hooks: timeline(since) });
  snapshot("after-sandboxed-lead", ["main", "h"]);
});

// 9. A Worker under `--approve-for-me`: what its shell reaches, and whether
// it binds and queues.
scenario("approve-for-me", async () => {
  const since = mark();
  await runTurn(c1, state.lead, "SPIKE:l-approve");
  await settle(() => exited("wg"), "Worker G exits", 60000);
  await delay(4000);
  ingest();
  trace("approve-for-me.outcome", { worker: workerOutput("wg"), thread: threadOf("wg.0"), shell: records.filter((record) => record.kind === "command" && record.label === "wg.0").map((record) => [record.phase, record.receipt, Boolean(record.viaFile)]),
    requests: modelRequests.filter((record) => record.receipt > since && record.thread !== state.lead).map((record) => [record.receipt, record.thread, record.model, record.label, record.step]),
    hooks: timeline(since) });
  snapshot("after-approve-for-me", ["g"]);
});

// 6. `codex app-server daemon restart` while Worker F holds a command, bound
// to Issue 7; then F queues its completion to the Lead. The restart drains
// the old daemon for up to its 60 s shutdown grace, which K2's unanswered ask
// holds open. If the queued message does not start a turn on its own, client
// 6 resumes the Lead.
scenario("daemon-restart", async () => {
  const since = mark();
  await runTurn(c1, state.lead, "SPIKE:l-wave");
  await waitFor(() => command("wf.1"), "Worker F holds", 60000);
  const execF = execPidOf("wf.1");
  const oldDaemon = daemonPid();
  const loadedBefore = await loadedThreads(c1);
  snapshot("restart-before", ["main", "f"]);
  const restarted = await codex(["app-server", "daemon", "restart"], "daemon-restart", { timeout: 240000 });
  await waitFor(() => daemonPid() && daemonPid() !== oldDaemon && existsSync(socketPath), "the replacement daemon", 30000);
  controllers = controllers.filter((client) => client !== c1);
  await delay(3000);
  const c6 = await daemonClient("controller-6");
  controllers.push(c6);
  const reloaded = await loadedThreads(c6);
  snapshot("restart-after", ["main", "f"]);
  const workerAlive = processState(execF);
  const beforeQueue = mark();
  open("f-hold");
  await waitFor(() => command("wf.6", "queue") ?? records.find((record) => record.kind === "command" && record.phase === "queue" && record.label.startsWith("wf.")), "F's queue", 60000);
  const delivered = await settle(() => requestsOf(state.lead, beforeQueue).some((record) => record.label === "l-mail-f"), "the reloaded Lead runs the queued turn", 40000);
  let resumedLead = null;
  if (!delivered) {
    const resumed = await c6.call("thread/resume", { threadId: state.lead });
    resumedLead = { at: Date.now(), error: resumed.error ?? null, status: resumed.result?.thread?.status ?? null };
    trace("thread.resume", { client: c6.name, threadId: state.lead, ...resumedLead });
    await settle(() => requestsOf(state.lead, beforeQueue).some((record) => record.label === "l-mail-f"), "the resumed Lead runs the queued turn", 30000);
    await c6.call("thread/unsubscribe", { threadId: state.lead });
  }
  await settle(() => exited("wf"), "Worker F exits", 60000);
  await delay(4000);
  snapshot("restart-queued", ["main", "f"]);
  const queued = records.find((record) => record.kind === "command" && record.phase === "queue" && record.label.startsWith("wf."));
  trace("daemon-restart.outcome", { oldDaemon, newDaemon: daemonPid(), restart: { status: restarted.status, startedAt: restarted.startedAt, endedAt: restarted.endedAt },
    loadedBefore, loadedAfter: reloaded, reloaded: reloaded.includes(state.lead), delivered, resumedLead, workerExec: execF, workerAlive, worker: workerOutput("wf"), thread: threadOf("wf.0"), queue: queued?.queue ?? null,
    leadRequests: requestsOf(state.lead, beforeQueue).map((record) => [record.receipt, record.label, record.receiptTime]), hooks: timeline(since) });
  // The reloaded Lead, which no client holds, unloads in turn.
  await settle(() => hooksSince(beforeQueue).some((record) => record.event === "SessionEnd" && record.payload.session_id === state.lead), "the reloaded Lead unloads", 90000);
  await delay(12000);
  snapshot("restart-unloaded", ["main", "f"]);
});

const scripts = ["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "deferred_end.py", "work_reconciliation.py", "hook_records.py", "work.py", "hook_scan.py", "processes.py", "working_directories.py"]
  .map((file) => `src/dashpot/sessions/${file}`).concat(["src/dashpot/repository/cleanup/obstacles.py"]);
const digests = () => Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
  .map(([name, file]) => [name, existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null]));
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: retained(execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim()),
    binarySHA256: createHash("sha256").update(readFileSync(binary)).digest("hex"),
    dashpot: { head: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      dirtySource: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean) },
    hookEvents, worktrees, socketPath, scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name)),
    sharedDaemonDirBefore: sharedBefore.length, sourceSHA256: digests() });

  // Setup: trust the fixture hooks through the ledger on a loopback server.
  trace("scenario", { name: "hook-trust" });
  const port = await freePort();
  const trustServer = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let trustBanner = "";
  trustServer.stderr.on("data", (chunk) => { trustBanner += chunk; });
  trustServer.stdout.on("data", () => {});
  await waitFor(() => trustBanner.includes("listening on"), "trust server listening", 20000);
  const trustSocket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(trustSocket, "open");
  const trust = await rpcClient("trust", { transport: "loopback-websocket", on: (listener) => trustSocket.addEventListener("message", (message) => listener(message.data)),
    send: (text) => trustSocket.send(text), close: () => trustSocket.close() });
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

  // The fixture's own managed daemon: its pid file, socket and environment
  // must all name the fixture's CODEX_HOME before any scenario runs.
  trace("scenario", { name: "daemon" });
  await codex(["app-server", "daemon", "start"], "daemon-start");
  await waitFor(() => existsSync(socketPath) && daemonPid(), "daemon control socket", 30000);
  const daemon = daemonPid();
  const daemonEnviron = readFileSync(`/proc/${daemon}/environ`, "utf8").split("\0");
  const isolation = { daemon, ownsFixtureHome: daemonEnviron.includes(`CODEX_HOME=${env.CODEX_HOME}`), socketUnderFixture: socketPath.startsWith(env.CODEX_HOME),
    cmdline: retained(describe(daemon).cmdline), settings: daemonSettings() };
  trace("daemon.isolation", isolation);
  assert(isolation.ownsFixtureHome && isolation.socketUnderFixture, "the daemon is the fixture's own");
  c1 = await daemonClient("controller-1", accept);
  controllers.push(c1);

  // Lead L binds Issue 1 in the main Worktree.
  trace("scenario", { name: "lead" });
  state.lead = await startThread(c1, "lead");
  const bound = await runTurn(c1, state.lead, "SPIKE:l-bind");
  trace("lead.outcome", { lead: state.lead, turn: bound.turnId, shell: command("l-bind.0")?.receipt ?? null });
  // Thread U is left by its last client now, so that the daemon has unloaded
  // it by the time a message is queued to it.
  if (!selected || selected.has("queue-unloaded")) {
    const c2 = await daemonClient("controller-2");
    state.unloaded = await startThread(c2, "unloaded");
    await runTurn(c2, state.unloaded, "SPIKE:u-first");
    await c2.call("thread/unsubscribe", { threadId: state.unloaded });
    c2.close();
    state.unloadedLeftAt = Date.now();
    trace("client.close", { client: c2.name });
  }

  for (const { name, body } of scenarios) {
    if (selected && !selected.has(name)) continue;
    trace("scenario", { name });
    try { await body(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 800) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
  }
  ingest();
  trace("scenario", { name: "daemon-stop" });
  for (const client of controllers) { try { client.close(); } catch {} }
  controllers = [];
  const lastDaemon = daemonPid();
  await codex(["app-server", "daemon", "stop"], "daemon-stop");
  await settle(() => !lastDaemon || !existsSync(`/proc/${lastDaemon}`), "daemon gone", 20000);
  await delay(12000);
  snapshot("after-daemon-stop", ["main", ...worktreeNames]);

  // Dashpot's Event Log for the fixture, metadata only.
  const events = dashpot(["events", "--json"]);
  const eventList = parseJson(events.stdout);
  const fields = ["time", "event.name", "dashpot.process.kind", "dashpot.agent_session.id", "dashpot.worktree.path", "dashpot.issue.id", "dashpot.hook.event",
    "dashpot.outcome.result", "dashpot.agent_session.state", "dashpot.work_store.change", "dashpot.subcommand"];
  trace("dashpot.events", { status: events.status, stderr: events.stderr.slice(0, 300),
    events: (eventList?.events ?? []).filter((event) => event["event.name"] !== "process.start" && event["event.name"] !== "process.end")
      .map((event) => Object.fromEntries(fields.filter((field) => event[field] !== undefined && event[field] !== null).map((field) => [field, retained(event[field])]))) });
  trace("sources.after", { sourceSHA256: digests() });
  console.log(`Scenarios completed: ${root}`);
} catch (error) {
  trace("runner.error", { error: retained(String(error?.stack ?? error)).slice(0, 2000) });
  console.log(`Runner failed: ${error}`);
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
  for (const gate of ["a-hold", "b-hold", "l-busy-go", "sig-go", "f-hold"]) { try { writeFileSync(path.join(gates, gate), ""); } catch {} }
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
