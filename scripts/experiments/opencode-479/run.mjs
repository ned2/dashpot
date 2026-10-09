// Measurement run for Issue #479: whether an OpenCode 2.0.22 Lead can run its
// Workers as root sessions on the shared service, made with `opencode api
// POST /api/session` at their Issue Worktree and prompted with `/prompt`,
// and coordinate with them through `POST /api/session/<id>/synthetic`. The
// scenarios are the "Proposed experiment" of
// docs/proposals/lead-worker-opencode-evidence.md, with a few extras:
//
//   placement       where a root lands with no location, and a child given one
//   dispatch        a Lead's shell makes and prompts Worker A with metadata
//   notice          synthetic notices to an idle Lead, a busy Lead (steer and
//                   queue), a repeated id, and a Lead whose own ask waits
//   worker-ask      a Worker's ask, listed and answered by the Lead's shell;
//                   the `dashpot-worker` agent chosen for a root session
//   fork            a Worker forked: its parent, fork fields and metadata
//   replies         what `reject` and a reply's `message` do to a Worker's
//                   asks
//   reviewer        a Worker's own Sub-agent at the default depth
//   finish          a Worker's `work stop` and move back to the main Worktree
//   interrupt       a Worker interrupted, then deleted
//   delete-lead     a Lead deleted while its Worker runs
//   move-lead       a Lead moved while its Worker runs
//   option-b        a Worker dispatched with a background `opencode run`
//   service-restart the service stopped while two sessions are mid-turn, one
//                   waits on an ask, one was interrupted and one is idle;
//                   started again by `opencode api`; which turns resume, and
//                   a `work start` from a resumed turn
//   standalone      a `--standalone` Lead dispatching through `opencode api`
//   long-wait       an `opencode api` wait and event stream held past five
//                   minutes
//   always          an ask allowed `always`: where the rule lands, who it
//                   answers, and its removal
//
// Copied from the worker mechanics run (opencode-421) and cut to these
// scenarios. It drives OpenCode 2.0.22, copied into the fixture, against a
// loopback OpenAI-compatible model fixture, in disposable configuration and
// state, with the background service on a private port, so the operator's
// own OpenCode service is never contacted. Every `opencode api` call, from a
// Lead's shell, a Worker's or the runner, goes through guard.mjs, which
// refuses it unless it resolves the fixture's registration and binary.
// Dashpot is built from this checkout and installed into a fixture
// environment; `dashpot integrate opencode` from that installation writes
// the plugin, skills and `dashpot-worker` agent the run exercises. A
// fixture-only probe plugin beside Dashpot's reports what a plugin receives
// for each session's creation. The trace is metadata only; the runner
// asserts only what it needs to keep going, and verify.mjs checks the trace.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode 2.0.22 binary> > log 2>&1
// It is done when it prints "All scenarios completed". SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, rmSync, statSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, inFixture } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
// A harness above the runner would be an ancestor of every client the run
// starts, and the Host Process Dashpot finds for a process it does not
// recognise, so the runner refuses to start below one; `setsid -f` detaches it.
const above = [];
for (let pid = process.ppid; pid > 1 && above.length < 64;) { try { const entry = describe(pid); above.push(entry); pid = entry.ppid; } catch { break; } }
const host = above.find((entry) => /^(claude|codex|opencode|opencode2|opencode\.exe)$/.test(entry.comm) || /\/claude\/versions\//.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const [binary] = process.argv.slice(2);
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the OpenCode 2.0.22 binary");
const uv = execFileSync("sh", ["-c", "command -v uv"], { encoding: "utf8" }).trim();

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-479-"));
console.log(`Isolated fixture: ${root}`);
// No directory above the fixture may hold configuration a harness or Dashpot
// would read: the fixture is outside every Dashpot Project.
const ancestorsFound = [];
for (let directory = path.dirname(root); ; directory = path.dirname(directory)) {
  for (const name of [".opencode", ".dashpot", ".claude", ".agents", ".git", "opencode.json", "opencode.jsonc", "AGENTS.md", "CLAUDE.md"]) {
    if (existsSync(path.join(directory, name)) && directory !== os.homedir()) ancestorsFound.push(path.join(directory, name));
  }
  if (directory === path.dirname(directory)) break;
}
assert.deepEqual(ancestorsFound, [], "a directory above the fixture holds configuration");
// The Repository's main Worktree and eleven linked Worktrees.
const fixture = path.join(root, "repository");
const tree = Object.fromEntries(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"].map((name) => [name, path.join(root, "repository.worktrees", name)]));
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root, the binary's
// directory, this directory, the checkout, and the operator's home by
// placeholder.
const retained = (text) => String(text).replaceAll(path.dirname(binary), "$BINARY_DIR").replaceAll(root, "$ROOT").replaceAll(path.dirname(root), "$TMPDIR")
  .replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const sha256 = (file) => !existsSync(file) ? null : createHash("sha256").update(readFileSync(file)).digest("hex");
const sha256Tree = (directory) => {
  if (!existsSync(directory)) return null;
  const hash = createHash("sha256");
  for (const name of readdirSync(directory, { recursive: true }).map(String).toSorted()) {
    const file = path.join(directory, name);
    try { hash.update(name + "\0" + readFileSync(file)); } catch {}
  }
  return hash.digest("hex");
};

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
const exercised = ["plugins/opencode.js", "agents/dashpot-worker.md", "sessions/opencode_publish.py", "sessions/opencode_publisher_records.py", "sessions/hook_claims.py",
  "sessions/hook_scan.py", "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/harnesses.py", "sessions/work.py",
  "sessions/integrate/across.py", "sessions/integrate/agent_copies.py", "sessions/integrate/arguments.py",
  "sessions/integrate/diagnostics.py", "sessions/integrate/environment.py", "sessions/integrate/harness.py",
  "sessions/integrate/installer.py", "sessions/integrate/opencode_plugin.py", "sessions/integrate/publisher.py",
  "sessions/integrate/registry.py", "sessions/integrate/skill_copies.py", "sessions/integrate/writes.py", "sessions/agent_bindings.py",
  "repository/cleanup/obstacles.py", "hook.py"];
const bundledSkill = path.join("skills", "dashpot-issue-work");
const experimentFiles = ["run.mjs", "verify.mjs", "command.mjs", "guard.mjs", "ancestry.mjs", "probe-plugin.js"];

const env = {
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  SHELL: "/bin/bash",
  LANG: "C.UTF-8",
  OPENCODE_DISABLE_AUTOUPDATE: "1",
  OPENCODE_DISABLE_MODELS_FETCH: "1",
  OPENCODE_DISABLE_PROJECT_CONFIG: "1",
  // Nothing but loopback is reachable: a model OpenCode chose over the
  // fixture's would otherwise be a hosted one.
  HTTP_PROXY: "http://127.0.0.1:9", HTTPS_PROXY: "http://127.0.0.1:9", http_proxy: "http://127.0.0.1:9", https_proxy: "http://127.0.0.1:9",
  NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost",
  // Sessions outside a configured checkout would publish here.
  DASHPOT_STATE_DIR: path.join(root, "dashpot-state"),
  // Ancestry walks from shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_DASHPOT: dashpot,
  SPIKE_HELPER: helper,
  // What guard.mjs checks every `opencode api` call against.
  SPIKE_ROOT: root,
};
env.SPIKE_CONFIG_MARK = env.XDG_CONFIG_HOME;
// OpenCode installed as its curl installer does, at ~/.opencode/bin/opencode,
// as a copy: nothing the fixture does can reach the operator's binary.
const curlBin = path.join(env.HOME, ".opencode", "bin");
const opencode = path.join(curlBin, "opencode");
env.SPIKE_OPENCODE = opencode;
const configHome = path.join(env.XDG_CONFIG_HOME, "opencode");
for (const dir of [fixture, env.HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, curlBin, configHome]) mkdirSync(dir, { recursive: true });
copyFileSync(binary, opencode);
chmodSync(opencode, 0o755);
const basePath = `${path.dirname(process.execPath)}:/usr/bin:/bin`;
env.PATH = `${curlBin}:${basePath}`;
const version = execFileSync(opencode, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, "opencode v2.0.22", `unexpected OpenCode version: ${version}`);

// A Dashpot Project with a markdown Issue Source, one Issue per binding.
const project = (directory, name, issues) => {
  mkdirSync(path.join(directory, ".dashpot"), { recursive: true });
  mkdirSync(path.join(directory, "issues"), { recursive: true });
  writeFileSync(path.join(directory, ".dashpot", "config.json"), JSON.stringify({ projectId: `project:${name}`, displayLabel: name,
    repositoryId: `repository:${name}`, issueSource: { kind: "markdown", path: "issues" } }));
  for (let number = 1; number <= issues; number++) {
    const front = { id: `I_${name}_${number}`, number, reference: `issue-${number}`, state: "open", stateReason: null, labels: [], assignees: [],
      author: "fixture", relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
      createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
    writeFileSync(path.join(directory, "issues", `issue-${number}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
  }
  const git = (...args) => execFileSync("git", ["-C", directory, ...args], { env, stdio: "pipe" });
  git("init", "--initial-branch=main");
  git("add", ".");
  git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
  return git;
};
const git = project(fixture, "fixture", 20);
for (const [name, directory] of Object.entries(tree)) git("worktree", "add", "-b", name, directory);
const worktrees = [fixture, ...Object.values(tree)];

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
const known = {};
// A guarded call's output names the session or request it made.
const idIn = (text, prefix) => String(text ?? "").match(new RegExp(`\\\\?"id\\\\?"\\s*:\\s*\\\\?"(${prefix}_[A-Za-z0-9]+)`))?.[1] ?? null;
const sink = await listen(async (req, res) => {
  const reported = await body(req);
  if (req.url === "/plugin") {
    trace("plugin.event", reported);
  } else {
    if (reported.exec) reported.exec = { ...reported.exec, stdout: retained(reported.exec.stdout ?? "").slice(0, 1500), stderr: retained(reported.exec.stderr ?? "").slice(-800) };
    trace("command", reported);
  }
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model. The latest user turn holding a `PROBE:<label>` text
// selects a sequence of steps, built when the model is asked so it can name
// sessions the runner or an earlier step learned; a step is one tool call or
// several made at once, and the turn ends with a text naming the label once
// every step has run. A label with no sequence runs one shell command of
// that name. A message holding no label, such as a synthetic notice,
// neither restarts nor ends the sequence it arrives in; a `NOTICE:<key>` in
// any message the model reads, other than a tool result or its own, is
// recorded with the message's role and position.
const commandScript = path.join(here, "command.mjs");
const guardScript = path.join(here, "guard.mjs");
const shell = (command, options = {}) => ({ name: "shell", arguments: { command, ...options } });
const report = (label, hold = 0) => shell(`node ${commandScript} ${label} ${hold}`);
const work = (label, ...args) => shell(`node ${commandScript} ${label} 0 -- work ${args.join(" ")}`);
const bind = (prefix, issue) => [work(`${prefix}-start`, "start", issue), work(`${prefix}-show`, "show")];
const quote = (value) => `'${typeof value === "string" ? value : JSON.stringify(value)}'`;
const guarded = (label, args) => `node ${guardScript} ${label} -- opencode ${args.join(" ")}`;
// One `opencode api` call from the model's shell, through the guard.
const oc = (label, ...args) => shell(guarded(label, args));
const LEAD_EXPORTS = "export LEAD_MARK=lead-shell GH_TOKEN=fixture-not-a-token;";
const subagent = (child, { background = true, agent = "general" } = {}) => ({ name: "subagent", arguments: {
  agent, description: `Reviewer ${child}`, prompt: `PROBE:${child}`, ...(background ? { background: true } : {}) } });
const execute = (code) => ({ name: "execute", arguments: { code } });
const moveSession = (directory) => execute(`return await tools.opencode.session_move(${JSON.stringify({ directory })})`);
const readEnv = () => ({ name: "read", arguments: { path: ".env" } });
const readSecret = () => ({ name: "read", arguments: { path: ".secret" } });
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const commandsOf = (label, phase = "start") => records.filter((record) => record.kind === "command" && record.label === label && record.phase === phase);
const createdBy = (label) => idIn(command(label)?.exec?.stdout, "ses");
const MODEL = { id: "fixture", providerID: "loop" };
const workerBody = (directory, title, issue, lead, extra = {}) => ({ location: { directory }, title, model: MODEL,
  metadata: { "dashpot.lead": lead, "dashpot.issue": issue }, ...extra });
const synthetic = (id, key, delivery, extra = "") => ({ ...(id ? { id } : {}), text: `NOTICE:${key} <worker state="progress">fixture notice</worker>${extra}`,
  description: `Worker notice ${key}`, ...(delivery ? { delivery } : {}) });
const sequences = {
  "ask-probe": () => [readEnv()],
  "lead-bind": () => bind("lead", "issue-1"),
  // Scenario dispatch: the Lead's shell makes Worker A at Worktree a with the
  // Lead in its metadata, then prompts it.
  "lead-dispatch-a": () => [
    shell(`${LEAD_EXPORTS} ${guarded("lead-create-a", ["api", "POST", "/api/session", "-d", quote(workerBody(tree.a, "Worker A", "issue-2", known.lead))])}`),
    shell(`${LEAD_EXPORTS} ${guarded("lead-prompt-a", ["api", "POST", `/api/session/${createdBy("lead-create-a")}/prompt`, "-d", quote({ text: "PROBE:wa" })])}`),
    report("lead-after-dispatch")],
  "wa": () => [report("wa-start"), work("wa-start-work", "start", "issue-2"), work("wa-show", "show"), oc("wa-info", "api", "GET", "/api/info"),
    report("wa-hold", 6000),
    oc("wa-notice-1", "api", "POST", `/api/session/${known.lead}/synthetic`, "-d", quote(synthetic("msg_dashpotwa0001", "wa-idle-1", "steer"))),
    oc("wa-notice-1-again", "api", "POST", `/api/session/${known.lead}/synthetic`, "-d", quote(synthetic("msg_dashpotwa0001", "wa-idle-1-again", "steer"))),
    report("wa-between", 3000),
    oc("wa-notice-2", "api", "POST", `/api/session/${known.lead}/synthetic`, "-d", quote(synthetic("msg_dashpotwa0002", "wa-idle-queue", "queue"))),
    report("wa-after-notice")],
  // Scenario notice: the Lead busy in its own shell while a notice arrives.
  "lead-busy-steer": () => [report("lead-busy-steer-hold", 8000), report("lead-busy-steer-after")],
  "lead-busy-queue": () => [report("lead-busy-queue-hold", 8000), report("lead-busy-queue-after")],
  "lead-ask": () => [readEnv(), report("lead-ask-after")],
  // Scenario worker-ask: Worker B, made with the `dashpot-worker` agent and a
  // replaced environment, asks; the Lead lists and answers its ask.
  "wb": () => [report("wb-start"), work("wb-start-work", "start", "issue-3"), readEnv(), report("wb-after-ask"), moveSession(tree.g), report("wb-after-move")],
  "lead-answer": () => [
    oc("lead-list-session", "api", "GET", `/api/session/${known.wb}/permission`),
    oc("lead-list-default", "api", "GET", "/api/permission/request"),
    shell(`cd ${tree.b} && ${guarded("lead-list-cwd", ["api", "GET", "/api/permission/request"])}`),
    oc("lead-list-location", "api", "GET", quote(`/api/permission/request?location[directory]=${encodeURIComponent(tree.b)}`)),
    oc("lead-reply", "api", "POST", `/api/session/${known.wb}/permission/${idIn(command("lead-list-session")?.exec?.stdout, "per")}/reply`, "-d", quote({ decision: "once" })),
    report("lead-after-answer")],
  // Scenario replies: Worker J's asks, two at once, then one at a time.
  "wj-two": () => [[readEnv(), readSecret()], report("wj-two-after")],
  "wj-message": () => [readEnv(), report("wj-message-after")],
  "wj-always": () => [readEnv(), report("wj-always-after")],
  "wj-again": () => [readEnv(), report("wj-again-after")],
  "lead-read": () => [readEnv(), report("lead-read-after")],
  "wj-removed": () => [readEnv(), report("wj-removed-after")],
  "wj-restarted": () => [readEnv(), report("wj-restarted-after")],
  // Scenario reviewer: Worker A's own Sub-agent, in the foreground.
  "wa-review": () => [subagent("reviewer", { background: false }), report("wa-after-review")],
  "reviewer": () => [report("reviewer-start"), work("reviewer-work-start", "start", "issue-9"), report("reviewer-hold", 5000)],
  // Scenario finish: Worker A ends its run and moves itself back.
  "wa-finish": () => [work("wa-stop", "stop"), moveSession(fixture), report("wa-after-move"), work("wa-after-move-show", "show")],
  // Scenario interrupt.
  "wc": () => [work("wc-start-work", "start", "issue-4"), report("wc-hold", 20000), report("wc-after")],
  // Scenario delete-lead: Lead 2 dispatches Worker D and is deleted.
  "lead2-bind": () => bind("lead2", "issue-5"),
  "lead2-dispatch": () => [
    oc("lead2-create-d", "api", "POST", "/api/session", "-d", quote(workerBody(tree.d, "Worker D", "issue-6", known.lead2))),
    oc("lead2-prompt-d", "api", "POST", `/api/session/${createdBy("lead2-create-d")}/prompt`, "-d", quote({ text: "PROBE:wd" }))],
  "wd": () => [work("wd-start-work", "start", "issue-6"), report("wd-hold", 10000),
    oc("wd-notice", "api", "POST", `/api/session/${known.lead2}/synthetic`, "-d", quote(synthetic("msg_dashpotwd0001", "wd-done", "steer"))), report("wd-after")],
  // Scenario move-lead: the Lead dispatches Worker E, and is moved meanwhile.
  "lead-dispatch-e": () => [
    oc("lead-create-e", "api", "POST", "/api/session", "-d", quote(workerBody(tree.e, "Worker E", "issue-7", known.lead))),
    oc("lead-prompt-e", "api", "POST", `/api/session/${createdBy("lead-create-e")}/prompt`, "-d", quote({ text: "PROBE:we" }))],
  "we": () => [work("we-start-work", "start", "issue-7"), report("we-hold", 8000),
    oc("we-notice", "api", "POST", `/api/session/${known.lead}/synthetic`, "-d", quote(synthetic("msg_dashpotwe0001", "we-done", "steer"))), report("we-after")],
  "lead-back": () => [work("lead-back-show", "show")],
  // Scenario option-b: a background `opencode run` from the Lead's shell.
  "lead-run-b": () => [
    shell(`${LEAD_EXPORTS} cd ${tree.f} && ${guarded("lead-run-f", ["run", "--title", "WorkerF", "-m", "loop/fixture", "PROBE:wf"])}`, { background: true }),
    report("lead-after-run-b")],
  "wf": () => [report("wf-start"), work("wf-start-work", "start", "issue-8"), work("wf-show", "show"), report("wf-hold", 3000)],
  // Scenario service-restart: a turn the restart resumes goes on to its next
  // step, so the resumed turn itself runs `work start`.
  "wb-long": () => [report("wb-long-hold", 30000), report("wb-resumed-hold", 6000), work("wb-resumed-start", "start", "issue-3"), work("wb-resumed-show", "show"), report("wb-resumed-env")],
  "lead-long": () => [report("lead-long-hold", 30000), work("lead-resumed-start", "start", "issue-1"), work("lead-resumed-show", "show")],
  "wb-recover": () => [work("wb-recover-start", "start", "issue-3"), work("wb-recover-show", "show")],
  "wh": () => [work("wh-start-work", "start", "issue-11"), readEnv(), report("wh-after-ask")],
  "wi": () => [work("wi-start-work", "start", "issue-12"), report("wi-hold", 20000), report("wi-after")],
  "we-idle": () => [report("we-idle")],
  // Scenario long-wait: Worker K's ask holds its turn open.
  "wk": () => [readEnv(), report("wk-after")],
  // Scenario standalone: a `--standalone` Lead dispatches through `opencode api`.
  "sa-lead": () => [oc("sa-info", "api", "GET", "/api/info"),
    oc("sa-create", "api", "POST", "/api/session", "-d", quote(workerBody(tree.g, "Worker SA", "issue-10", command("sa-info")?.sessionClaim ?? null))),
    oc("sa-prompt", "api", "POST", `/api/session/${createdBy("sa-create")}/prompt`, "-d", quote({ text: "PROBE:wsa" })),
    report("sa-lead-hold", 10000), report("sa-lead-after")],
  "wsa": () => [report("wsa-start"),
    oc("wsa-notice", "api", "POST", `/api/session/${command("sa-info")?.sessionClaim}/synthetic`, "-d",
      quote(synthetic("msg_dashpotsa0001", "wsa-done", "steer", " PROBE:sa-woken"))), report("wsa-after")],
  "sa-woken": () => [report("sa-woken")],
};
const text = (message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "");
// A shell's completion notice quotes its command, which can hold another
// session's label, so it never selects a sequence.
const probes = (message) => /<shell id=/.test(text(message)) ? [] : [...text(message).matchAll(/PROBE:([a-z0-9-]+)/g)].map((match) => match[1]);
const SUBAGENT_NOTICE = /<subagent sessionID=\\?"(ses_\w+)\\?" state=\\?"(\w+)\\?"/g;
const SHELL_NOTICE = /<shell id=\\?"([^"\\]+)\\?" state=\\?"(\w+)\\?"[^>]*>(?:\\n|\n)?([^<]{0,200})/g;
const SYNTHETIC_NOTICE = /NOTICE:([a-z0-9-]+)/g;
const modelRequests = new Map();
const some = (list) => list.length ? list : undefined;
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const anchor = messages.findLastIndex((message) => message.role === "user" && probes(message).length);
  const label = anchor >= 0 ? probes(messages[anchor]).at(-1) : null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const titled = /title generator/i.test(system) || !tools.length;
  const lastAssistant = messages.findLastIndex((message) => message.role === "assistant");
  const step = messages.slice(anchor + 1).filter((message) => message.role === "assistant").length;
  const count = titled ? 0 : (modelRequests.get(label) ?? 0) + 1;
  if (!titled) modelRequests.set(label, count);
  const last = messages.at(-1);
  const lastTool = last?.role === "tool" ? text(last) : null;
  const sequence = (label && (sequences[label]?.() ?? [report(label)])) || [];
  const planned = titled ? undefined : sequence[step];
  const calls = planned === undefined ? [] : Array.isArray(planned) ? planned : [planned];
  const notices = titled ? [] : messages.flatMap((message, index) => message.role === "tool" || message.role === "assistant" ? [] : [
    ...[...text(message).matchAll(SUBAGENT_NOTICE)].map(([, id, state]) => ({ of: "subagent", id, state, fresh: index > lastAssistant, role: message.role, index })),
    ...[...text(message).matchAll(SHELL_NOTICE)].map(([, id, state, head]) => ({ of: "shell", id, state, fresh: index > lastAssistant, role: message.role, index,
      head: retained(head.replaceAll("\\n", " ")).trim().slice(0, 160) })),
    ...[...text(message).matchAll(SYNTHETIC_NOTICE)].map(([, key]) => ({ of: "synthetic", id: key, fresh: index > lastAssistant, role: message.role, index,
      head: retained(text(message)).slice(0, 220) })),
  ]);
  trace("model.request", { label, step, tools: calls.map((call) => call.name), count, titled,
    sessionID: req.headers["x-opencode-session-id"] ?? null, parentID: req.headers["x-opencode-parent-session-id"] ?? null,
    messages: messages.length, roles: titled ? undefined : messages.map((message) => message.role[0]).join(""),
    probes: titled ? undefined : messages.filter((message) => message.role === "user").flatMap(probes),
    notices: notices.length ? notices : undefined,
    // A user message OpenCode added after the label with no label or notice of
    // its own, such as a restarted service's resumption, and the tool results
    // this request answers, such as a rejected ask's.
    appended: titled ? undefined : some(messages.slice(anchor + 1).filter((message) => message.role === "user" && !probes(message).length
      && !/NOTICE:|<shell id=|<subagent /.test(text(message))).map((message) => retained(text(message)).slice(0, 300))),
    results: titled ? undefined : some(messages.slice(lastAssistant + 1).filter((message) => message.role === "tool").map((message) => retained(text(message)).slice(0, 300))),
    lastTool: titled || !lastTool ? undefined : retained(lastTool).slice(0, 500) });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (calls.length) {
    chunk({ role: "assistant", tool_calls: calls.map((call, index) => ({ index, id: `call_${label}_${step}_${count}_${index}`, type: "function",
      function: { name: call.name, arguments: JSON.stringify(call.arguments) } })) });
  } else chunk({ role: "assistant", content: titled ? "Fixture title" : `Fixture complete: ${label}.` });
  chunk({}, calls.length ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});

// The native configuration: the fixture model only, every tool allowed but
// `read`, which asks, and the background service on a private port with a
// known password. The `dashpot-worker` agent is the one `integrate` installs.
const freePort = async () => {
  const server = net.createServer().listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  server.close();
  return port;
};
const servicePort = await freePort();
env.SPIKE_SERVICE_PORT = String(servicePort);
const password = "fixture-password";
writeFileSync(path.join(configHome, "service.json"), JSON.stringify({ hostname: "127.0.0.1", port: servicePort, password }));
const opencodeConfig = JSON.stringify({
  model: "loop/fixture", update: "disable", share: "disabled", snapshots: false, lsp: false, formatter: false,
  providers: { loop: { name: "Loop", package: "aisdk:@ai-sdk/openai-compatible",
    settings: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 128000, output: 4096 } } } } },
  permissions: [{ action: "*", resource: "*", effect: "allow" }, { action: "read", resource: "*", effect: "ask" }],
}, null, 2);

// --- Observation -------------------------------------------------------------

const run = (program, args, { cwd = fixture, extra = {} } = {}) => {
  const result = spawnSync(program, args, { cwd, env: { ...env, PWD: cwd, ...extra }, encoding: "utf8", timeout: 60000 });
  return { status: result.status, stdout: retained(result.stdout ?? ""), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const integrate = (label, args, options = {}) => trace("integrate", { label, args, ...run(dashpot, ["integrate", ...args], options) });
// What a person's dashboard reads: the headless snapshot of the Project.
const observe = (label, cwd = fixture) => {
  const result = run(dashpot, ["--json"], { cwd });
  let snapshot = null;
  try { snapshot = JSON.parse(result.stdout); } catch {}
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned, workers }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned, workers: workers?.length ? workers : undefined }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((item) => item.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: String(message).slice(0, 400) }));
  return trace("observation", { label, error: snapshot ? null : result.stderr, runs, diagnostics });
};
// What Cleanup says about one linked Worktree.
const check = (label, worktree) => {
  const result = run(dashpot, ["worktree", "check", worktree, "--json"]);
  let assessment = null;
  try { assessment = JSON.parse(result.stdout); } catch {}
  return trace("cleanup", { label, worktree, status: result.status,
    obstacles: assessment ? (assessment.obstacles ?? []).map(({ kind, detail }) => ({ kind, detail: String(detail ?? "").slice(0, 400) })) : null,
    error: assessment ? undefined : (result.stdout + result.stderr).slice(0, 1500) });
};
const storeOf = (worktree) => path.join(worktree, ".dashpot", "state", "sessions");
const readJson = (file) => { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return null; } };
// The hook record of each session the Agent Session list names, by
// Worktree: its location, state and live children.
const stateFiles = (label) => {
  const sessions = {};
  for (const worktree of worktrees) {
    let names = [];
    try { names = readdirSync(storeOf(worktree)).filter((name) => name.endsWith(".json")); } catch { continue; }
    for (const name of names) {
      const record = readJson(path.join(storeOf(worktree), name));
      if (!record) continue;
      sessions[`${worktree}/${name}`] = { state: record.state ?? null, event: record.event ?? null, cwd: record.cwd ?? null, ended: record.ended ?? record.endedAt ?? undefined,
        subagents: record.subagents ?? record.liveSubagents ?? null, keys: Object.keys(record) };
    }
  }
  return trace("state", { label, sessions });
};
// Every Runtime Event the fixture's Dashpot processes recorded, flattened.
const eventLog = () => {
  const events = [];
  const directories = [...worktrees.map((worktree) => path.join(worktree, ".dashpot", "state", "events")), path.join(env.XDG_STATE_HOME, "dashpot", "events"),
    path.join(env.DASHPOT_STATE_DIR, "events")];
  for (const directory of directories) {
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
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(50); }
  throw new Error(`Timed out: ${label}`);
};
// A wait whose timeout is itself a finding: recorded, and the run goes on.
const soft = async (predicate, label, timeout) => {
  try { return await waitFor(predicate, label, timeout); } catch (error) { trace("missing", { label, error: String(error.message) }); return false; }
};
const settle = (ms = 1500) => delay(ms);
// Model requests of one session that carry a fresh notice of one kind and key.
const noticedBy = (sessionID, of, key, after = 0) => records.filter((record) => record.kind === "model.request" && record.sessionID === sessionID && record.receipt > after
  && record.notices?.some((notice) => notice.fresh && notice.of === of && (!key || notice.id === key)));
// Every process whose environment names the fixture configuration, so the
// operator's own processes are never observed or signalled.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    if (!inFixture(name, env.XDG_CONFIG_HOME)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
// The operator's own OpenCode service, observed without reading its
// registration's content: the registration file's modification time, and
// every `opencode serve --service` outside the fixture.
const operator = (label) => {
  let registrationMtime = null;
  try { registrationMtime = statSync(path.join(os.homedir(), ".local", "state", "opencode", "service.json")).mtimeMs; } catch {}
  const services = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || inFixture(name, env.XDG_CONFIG_HOME)) continue;
    try { const entry = describe(Number(name)); if (/serve --service/.test(entry.cmdline)) services.push({ pid: entry.pid, startTime: entry.startTime }); } catch {}
  }
  return trace("operator", { label, registrationMtime, services });
};

// --- The background service and its clients -----------------------------------

const registration = () => readJson(path.join(env.XDG_STATE_HOME, "opencode", "service.json"));
const service = { url: `http://127.0.0.1:${servicePort}`, pid: null, events: null };
const authorization = "Basic " + Buffer.from(`opencode:${password}`).toString("base64");
const request = async (method, route, data, { directory } = {}) => {
  const headers = { "content-type": "application/json", authorization };
  if (directory) headers["x-opencode-directory"] = encodeURIComponent(directory);
  const response = await fetch(service.url + route, { method, headers, body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(120000) });
  const raw = await response.text();
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = raw.slice(0, 500); }
  return { status: response.status, body: parsed?.data ?? parsed };
};
const api = async (method, route, data, options) => {
  const answer = await request(method, route, data, options);
  assert(answer.status >= 200 && answer.status < 300, `${method} ${route}: ${answer.status} ${JSON.stringify(answer.body).slice(0, 700)}`);
  return answer.body;
};
// OpenCode's server event stream as a client sees it: session lifecycle,
// executions, moves, metadata, inbox and synthetic input, and permissions.
const STREAMED = /^(session\.(created|deleted|moved|execution\.|metadata|synthetic|inbox|prompt|input|steer|queue)|permission\.)/;
const eventTypes = new Set();
const subscribe = (name) => {
  const controller = new AbortController();
  (async () => {
    try {
      const response = await fetch(service.url + "/api/event", { headers: { authorization }, signal: controller.signal });
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
          eventTypes.add(event.type ?? "?");
          if (!STREAMED.test(event.type ?? "")) continue;
          const data = event.data ?? {};
          trace("server.event", { name, type: event.type, location: event.location?.directory ?? null, sessionID: data.sessionID ?? null,
            parentID: data.parentID ?? null, reason: data.reason ?? null, to: event.type === "session.moved" ? data.location?.directory ?? null : undefined,
            action: data.action ?? undefined, reply: data.reply ?? data.decision ?? undefined, requestID: event.type.startsWith("permission.") ? data.id ?? data.requestID ?? undefined : undefined,
            messageID: data.messageID ?? (event.type.startsWith("permission.") ? undefined : data.id) ?? undefined, delivery: data.delivery ?? undefined,
            metadata: data.metadata ?? undefined, keys: Object.keys(data).toSorted() });
        }
      }
    } catch {}
  })();
  return controller;
};
const awaitService = async (label, { subscribeAgain = true } = {}) => {
  let info = null;
  await waitFor(() => (info = registration()) && alive(info.pid), `${label}: service registered`, 60000);
  let ready = false;
  for (let attempt = 0; attempt < 200 && !ready; attempt++) {
    ready = (await request("GET", "/api/info").catch(() => null))?.status === 200;
    if (!ready) await delay(100);
  }
  assert(ready, `${label}: service never ready`);
  service.pid = info.pid;
  if (subscribeAgain) {
    service.events?.abort();
    service.events = subscribe(label);
  }
  await settle(500);
  let cmdline = null;
  try { cmdline = describe(info.pid).cmdline; } catch {}
  trace("service", { label, pid: info.pid, version: info.version ?? null, cmdline: retained(cmdline ?? ""), registration: Object.keys(info).toSorted() });
  return info;
};
// The runner's own `opencode` CLI calls, always the fixture's copy in the
// fixture's environment.
const cli = (args, { cwd = fixture } = {}) => {
  // A command that reaches the running service may reach only the fixture's.
  if (args[0] !== "service") {
    const found = registration();
    assert(found && Number(new URL(found.url).port) === servicePort && inFixture(found.pid, env.XDG_CONFIG_HOME), `opencode ${args[0]}: not the fixture's service`);
  }
  const result = spawnSync(opencode, args, { cwd, env: { ...env, PWD: cwd }, encoding: "utf8", timeout: 60000 });
  return { args, status: result.status, stdout: retained(result.stdout ?? "").slice(0, 1500), stderr: retained(result.stderr ?? "").slice(-1500) };
};
// A guarded `opencode` call from the runner, as a Lead's shell would make
// it, without blocking the sink and model fixture it may need.
const guardedCall = (label, args, { cwd = fixture, extra = {} } = {}) => new Promise((resolve) => {
  const child = spawn(process.execPath, [guardScript, label, "--", "opencode", ...args], { cwd, env: { ...env, PWD: cwd, ...extra }, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.on("exit", (status) => resolve({ status, stdout }));
});
const stripAnsi = (value) => value.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007\u001b]*(\u0007|\u001b\\)/g, "").replace(/\u001b[()][A-Z0-9]/g, "");
const clients = [];
// A CLI client run in the background, stdin closed, as a script runs it.
const client = (name, args, { cwd = fixture } = {}) => {
  const child = spawn(opencode, args, { cwd, env: { ...env, PWD: cwd, SPIKE_CLIENT: name }, stdio: ["ignore", "pipe", "pipe"] });
  const state = { name, child, exited: null, output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.stderr.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.on("exit", (code, signal) => { state.exited = { code, signal, at: Date.now() };
    trace("client.exit", { name, code, signal, output: retained(state.output).slice(-1200) }); });
  clients.push(state);
  trace("client.spawn", { name, args, cwd, pid: child.pid });
  return state;
};
const session = async (title, directory, extra = {}) => {
  const made = await api("POST", "/api/session", { title, ...(directory ? { location: { directory } } : {}), model: MODEL, ...extra });
  trace("session", { title, sessionID: made.id, directory: made.location?.directory ?? null, parentID: made.parentID ?? null, agent: made.agent ?? null,
    metadata: made.metadata ?? null });
  return made.id;
};
const send = (id, label, extra = {}) => api("POST", `/api/session/${id}/prompt`, { text: `PROBE:${label}`, ...extra });
const idle = async (id, label) => {
  const waited = await request("POST", `/api/experimental/session/${id}/wait`, {});
  if (!(waited.status >= 200 && waited.status < 300)) trace("missing", { label: `${label}: wait`, status: waited.status });
};
const prompt = async (id, label, extra) => {
  const started = Date.now();
  await send(id, label, extra);
  await idle(id, label);
  trace("turn", { sessionID: id, label, ms: Date.now() - started });
};
// What OpenCode says of one session: placement, parent, agent, metadata, and
// the outcome and idle time of its last execution.
const sessionInfo = async (label, id) => {
  const answer = await request("GET", `/api/session/${id}`);
  const item = answer.body ?? {};
  return trace("session.info", { label, sessionID: id, ...(answer.status === 200 ? { location: item.location?.directory ?? null, parentID: item.parentID ?? null,
    agent: item.agent ?? null, metadata: item.metadata ?? null, outcome: item.outcome ?? null, idleAt: item.time?.idle ?? null, updatedAt: item.time?.updated ?? null }
    : { missing: answer.status }) });
};
const move = async (id, directory, label) => {
  const answer = await request("POST", `/api/session/${id}/move`, { directory });
  await settle();
  trace("move", { label, sessionID: id, to: directory, status: answer.status });
  return sessionInfo(`${label}-after`, id);
};
const active = async (label) => {
  const answer = (await request("GET", "/api/session/active")).body ?? {};
  return trace("active", { label, sessions: Array.isArray(answer) ? answer.map((item) => item?.id ?? item?.sessionID ?? item) : Object.keys(answer) });
};
const pending = async (label, id) => {
  const answer = await request("GET", `/api/session/${id}/permission`);
  const list = Array.isArray(answer.body) ? answer.body : [];
  return trace("permissions.pending", { label, sessionID: id, status: answer.status, asks: list.map((item) => ({ id: item.id, action: item.action ?? null,
    resources: item.resources ?? null })) });
};
const inbox = async (label, id) => {
  const answer = await request("GET", `/api/session/${id}/inbox`);
  const list = Array.isArray(answer.body) ? answer.body : [];
  return trace("inbox", { label, sessionID: id, status: answer.status, items: list.map((item) => ({ id: item.id, type: item.type, delivery: item.delivery ?? null })) });
};
const asked = (sessionID, after = 0) => records.find((record) => record.kind === "server.event" && record.type === "permission.asked" && record.sessionID === sessionID && record.receipt > after);
const replied = (sessionID, after = 0) => records.filter((record) => record.kind === "server.event" && record.type === "permission.replied" && record.sessionID === sessionID && record.receipt > after);
const executions = (sessionID, after = 0) => records.filter((record) => record.kind === "server.event" && record.type === "session.execution.started" && record.sessionID === sessionID && record.receipt > after).length;
// The Dashpot plugin's hook outcomes for the given sessions since a time: what
// Dashpot was told about them.
const hookOutcomes = (sessions, since) => eventLog().filter((event) => event["event.name"] === "hook.outcome" && sessions.includes(event["dashpot.agent_session.id"])
  && Date.parse(event.time) >= since).map((event) => ({ session: event["dashpot.agent_session.id"], hook: event["dashpot.hook.event"] ?? null,
  state: event["dashpot.agent_session.state"] ?? null, result: event["dashpot.outcome.result"] ?? null, change: event["dashpot.work_store.change"] ?? null,
  pid: event["process.pid"] ?? null, time: Date.parse(event.time) })).toSorted((left, right) => left.time - right.time);
// What the probe plugin, inside the service, saw of one session since a receipt.
const pluginSaw = (sessionID, after = 0) => records.filter((record) => record.kind === "plugin.event" && record.sessionID === sessionID && record.receipt > after)
  .map((record) => ({ type: record.type, reason: record.reason ?? null, reply: record.reply ?? null, pid: record.pid }));
const requestsOf = (sessionID, after = 0) => records.filter((record) => record.kind === "model.request" && record.sessionID === sessionID && record.receipt > after && !record.titled)
  .map((record) => ({ label: record.label, step: record.step, tools: record.tools, appended: record.appended, results: record.results }));
const claimOf = (label) => command(label, "start")?.env?.OPENCODE_SESSION_ID ?? null;
const childrenOf = (parentID) => records.filter((record) => record.kind === "server.event" && record.type === "session.created" && record.parentID === parentID)
  .map((record) => record.sessionID);

const pluginFile = path.join(configHome, "plugins", "dashpot.js");
const probeFile = path.join(configHome, "plugins", "fixture-probe.js");
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), fixtureBinarySHA256: sha256(opencode), servicePort, fixture, trees: tree, wheel,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))), proxy: { HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY },
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    installedMatchesSource: exercised.every((file) => sha256(path.join(installed, file)) === sha256(path.join(checkout, "src", "dashpot", file)))
      && sha256Tree(path.join(installed, bundledSkill)) === sha256Tree(path.join(checkout, "src", "dashpot", bundledSkill)),
    sourceSHA256: Object.fromEntries([
      ...experimentFiles.map((file) => [file, sha256(path.join(here, file))]),
      ...exercised.map((file) => [`src/dashpot/${file}`, sha256(path.join(checkout, "src", "dashpot", file))]),
      [`src/dashpot/${bundledSkill}/`, sha256Tree(path.join(checkout, "src", "dashpot", bundledSkill))],
    ]) });
  operator("start");

  // Scenario installer: the integration, as a person installs it, and the
  // fixture's probe plugin beside it.
  trace("scenario", { name: "installer" });
  writeFileSync(path.join(configHome, "opencode.json"), opencodeConfig);
  integrate("install", ["opencode"]);
  assert(readFileSync(pluginFile, "utf8").includes(JSON.stringify(helper)), "the plugin names the installed helper");
  writeFileSync(probeFile, readFileSync(path.join(here, "probe-plugin.js"), "utf8").replace("__SPIKE_SINK__", sink.url));
  trace("files", { label: "installed", plugin: sha256(pluginFile), probe: sha256(probeFile),
    workerAgent: sha256(path.join(configHome, "agent", "dashpot-worker.md")), skill: existsSync(path.join(configHome, "skills", "dashpot-issue-work", "SKILL.md")) });
  trace("service.start", { label: "start", ...cli(["service", "start"]) });
  await awaitService("start");
  integrate("status", ["opencode", "--status"]);

  // Scenario placement: where a root lands with no location; a child given a
  // location; and whether the `read` rule asks.
  trace("scenario", { name: "placement" });
  known.lead = await session("Lead", fixture);
  known.bare = await session("Bare", null);
  await sessionInfo("bare", known.bare);
  known.child = await session("Child", tree.g, { parentID: known.lead });
  await sessionInfo("child-with-location", known.child);
  trace("delete", { label: "bare", ...(await request("DELETE", `/api/session/${known.bare}`)) });
  trace("delete", { label: "child", ...(await request("DELETE", `/api/session/${known.child}`)) });
  known.askProbe = await session("AskProbe", fixture);
  const askMark = records.length;
  await send(known.askProbe, "ask-probe");
  const askWorks = await soft(() => asked(known.askProbe, askMark), "ask-probe asked", 15000);
  trace("ask.rule", { asks: askWorks });
  await request("POST", `/api/session/${known.askProbe}/interrupt`);
  await settle(500);
  trace("delete", { label: "ask-probe", ...(await request("DELETE", `/api/session/${known.askProbe}`)) });

  // Scenario dispatch: the Lead, bound at the main Worktree, makes Worker A
  // at Worktree a from its shell; Worker A binds there and holds.
  trace("scenario", { name: "dispatch" });
  await prompt(known.lead, "lead-bind");
  const dispatchMark = records.length;
  await prompt(known.lead, "lead-dispatch-a");
  known.wa = createdBy("lead-create-a");
  assert(known.wa, "the Lead's shell made Worker A");
  await waitFor(() => command("wa-hold", "start"), "Worker A holding", 60000);
  await settle(1000);
  await active("wa-holding");
  await sessionInfo("wa-holding", known.wa);
  stateFiles("wa-holding");
  observe("wa-holding");
  check("tree-a-wa-holding", tree.a);
  check("tree-b-wa-holding", tree.b);
  trace("plugin.seen", { label: "wa", events: records.filter((record) => record.kind === "plugin.event" && record.sessionID === known.wa && record.receipt > dispatchMark).length });

  // Scenario notice: Worker A's notices to the idle Lead (steer, the same id
  // again, then queue); the runner's to the busy Lead; and one while the
  // Lead's own ask waits.
  trace("scenario", { name: "notice" });
  await waitFor(() => command("wa-after-notice"), "Worker A notices sent", 60000);
  await settle(2000);
  await idle(known.lead, "lead-woken");
  await sessionInfo("lead-after-idle-notices", known.lead);
  await inbox("lead-after-idle-notices", known.lead);
  const steerMark = records.length;
  const steering = send(known.lead, "lead-busy-steer");
  await waitFor(() => command("lead-busy-steer-hold", "start"), "Lead busy (steer)", 30000);
  await steering;
  await settle(500);
  trace("guarded", { label: "busy-steer", ...(await guardedCall("runner-busy-steer", ["api", "POST", `/api/session/${known.lead}/synthetic`, "-d",
    JSON.stringify(synthetic("msg_dashpotrn0001", "busy-steer", "steer"))], { cwd: tree.a })) });
  await inbox("lead-busy-steer-pending", known.lead);
  await idle(known.lead, "lead-busy-steer");
  await settle(1500);
  await idle(known.lead, "lead-busy-steer-settled");
  trace("executions", { label: "busy-steer", lead: executions(known.lead, steerMark) });
  const queueMark = records.length;
  const queueing = send(known.lead, "lead-busy-queue");
  await waitFor(() => command("lead-busy-queue-hold", "start"), "Lead busy (queue)", 30000);
  await queueing;
  await settle(500);
  trace("guarded", { label: "busy-queue", ...(await guardedCall("runner-busy-queue", ["api", "POST", `/api/session/${known.lead}/synthetic`, "-d",
    JSON.stringify(synthetic("msg_dashpotrn0002", "busy-queue", "queue"))], { cwd: tree.a })) });
  await inbox("lead-busy-queue-pending", known.lead);
  await idle(known.lead, "lead-busy-queue");
  await settle(2000);
  await idle(known.lead, "lead-busy-queue-settled");
  trace("executions", { label: "busy-queue", lead: executions(known.lead, queueMark) });
  // The Lead's own ask, pending while a notice arrives.
  const leadAskMark = records.length;
  await send(known.lead, "lead-ask");
  const leadAsked = await soft(() => asked(known.lead, leadAskMark), "Lead asked", 20000);
  if (leadAsked) {
    await settle(500);
    trace("guarded", { label: "ask-steer", ...(await guardedCall("runner-ask-steer", ["api", "POST", `/api/session/${known.lead}/synthetic`, "-d",
      JSON.stringify(synthetic("msg_dashpotrn0003", "ask-steer", "steer"))], { cwd: tree.a })) });
    await settle(3000);
    await pending("lead-ask-after-notice", known.lead);
    await inbox("lead-ask-after-notice", known.lead);
    trace("replies", { label: "lead-ask-after-notice", replies: replied(known.lead, leadAskMark).map((record) => record.reply ?? null) });
    stateFiles("lead-asking");
    observe("lead-asking");
    const asks = (await pending("lead-ask-answering", known.lead)).asks;
    for (const ask of asks) {
      const answer = await request("POST", `/api/session/${known.lead}/permission/${ask.id}/reply`, { decision: "once" });
      trace("permission.reply", { label: "lead-ask", decision: "once", status: answer.status });
    }
  }
  await idle(known.lead, "lead-ask");
  await settle(2000);
  await idle(known.lead, "lead-ask-settled");
  trace("executions", { label: "lead-ask", lead: executions(known.lead, leadAskMark) });

  // Scenario worker-ask: Worker B, with the `dashpot-worker` agent and a
  // replaced environment; its ask, listed and answered by the Lead's shell.
  trace("scenario", { name: "worker-ask" });
  const madeB = await guardedCall("runner-create-b", ["api", "POST", "/api/session", "-d",
    JSON.stringify(workerBody(tree.b, "Worker B", "issue-3", known.lead, { agent: "dashpot-worker" }))]);
  known.wb = idIn(madeB.stdout, "ses");
  trace("agent.root", { agent: "dashpot-worker", made: Boolean(known.wb), status: madeB.status });
  if (!known.wb) {
    const plain = await guardedCall("runner-create-b-plain", ["api", "POST", "/api/session", "-d", JSON.stringify(workerBody(tree.b, "Worker B", "issue-3", known.lead))]);
    known.wb = idIn(plain.stdout, "ses");
  }
  assert(known.wb, "Worker B made");
  await sessionInfo("wb-made", known.wb);
  const replaced = Object.fromEntries(Object.entries({ ...env, PUT_MARK: "put" }).filter(([key]) => key !== "XDG_CACHE_HOME"));
  trace("guarded", { label: "wb-environment", ...(await guardedCall("runner-environment-b", ["api", "PUT", `/api/session/${known.wb}/environment`, "-d",
    JSON.stringify({ variables: replaced })])) });
  const wbMark = records.length;
  await send(known.wb, "wb");
  const wbAsked = await soft(() => asked(known.wb, wbMark), "Worker B asked", 30000);
  if (wbAsked) {
    await settle(1000);
    await active("wb-asking");
    await pending("wb-asking", known.wb);
    stateFiles("wb-asking");
    observe("wb-asking");
    check("tree-b-wb-asking", tree.b);
    await prompt(known.lead, "lead-answer");
  }
  await soft(() => command("wb-after-move"), "Worker B went on", 60000);
  await idle(known.wb, "wb");
  await sessionInfo("wb-after", known.wb);
  observe("wb-after");

  // Scenario fork: Worker B forked from the runner, as a Lead's shell would.
  trace("scenario", { name: "fork" });
  const forkMark = records.length;
  const forked = await guardedCall("runner-fork-b", ["api", "POST", `/api/session/${known.wb}/fork`, "-d", "{}"]);
  let forkData = null;
  try { forkData = JSON.parse(forked.stdout).data ?? null; } catch {}
  known.fork = forkData?.id ?? idIn(forked.stdout, "ses");
  await settle(1000);
  trace("fork", { status: forked.status, sessionID: known.fork, keys: forkData ? Object.keys(forkData).toSorted() : null, parentID: forkData?.parentID ?? null,
    forkFields: forkData ? Object.fromEntries(Object.entries(forkData).filter(([key]) => /fork|source|origin|parent|revert/i.test(key))) : null,
    metadata: forkData?.metadata ?? null, location: forkData?.location?.directory ?? null, agent: forkData?.agent ?? null, title: forkData?.title ?? null,
    plugin: records.filter((record) => record.kind === "plugin.event" && record.sessionID === known.fork && record.receipt > forkMark)
      .map((record) => ({ type: record.type, parentID: record.parentID, dataKeys: record.dataKeys, metadata: record.metadata })),
    server: records.filter((record) => record.kind === "server.event" && record.sessionID === known.fork && record.receipt > forkMark)
      .map((record) => ({ type: record.type, parentID: record.parentID, keys: record.keys, metadata: record.metadata ?? null })) });
  if (known.fork) {
    await sessionInfo("fork", known.fork);
    trace("delete", { label: "fork", ...(await request("DELETE", `/api/session/${known.fork}`)) });
  }

  // Scenario replies: Worker J's two asks at once, one rejected; an ask
  // rejected with a message. `always` is the last scenario.
  trace("scenario", { name: "replies" });
  known.wj = idIn((await guardedCall("runner-create-j", ["api", "POST", "/api/session", "-d",
    JSON.stringify(workerBody(tree.j, "Worker J", "issue-13", known.lead))])).stdout, "ses");
  assert(known.wj, "Worker J made");
  const askedAll = (id, after) => records.filter((record) => record.kind === "server.event" && record.type === "permission.asked" && record.sessionID === id && record.receipt > after);
  const answerAll = async (label, id, decision = "once") => {
    for (const ask of (await pending(`${label}-answering`, id)).asks) {
      const answer = await request("POST", `/api/session/${id}/permission/${ask.id}/reply`, { decision });
      trace("permission.reply", { label, decision, status: answer.status });
    }
  };
  const twoMark = records.length;
  await send(known.wj, "wj-two");
  await soft(() => askedAll(known.wj, twoMark).length >= 2, "Worker J asked twice", 20000);
  await settle(500);
  const twoAsks = (await pending("wj-two-asking", known.wj)).asks;
  if (twoAsks.length) {
    const answer = await request("POST", `/api/session/${known.wj}/permission/${twoAsks[0].id}/reply`, { decision: "reject" });
    trace("permission.reply", { label: "wj-two-first", decision: "reject", requestID: twoAsks[0].id, status: answer.status });
  }
  await settle(2000);
  const twoLeft = await pending("wj-two-after-reject", known.wj);
  trace("replies", { label: "wj-two", replies: replied(known.wj, twoMark).map((record) => ({ requestID: record.requestID ?? null, reply: record.reply ?? null })),
    stillPending: twoLeft.asks.length });
  if (twoLeft.asks.length) await answerAll("wj-two-rest", known.wj);
  await idle(known.wj, "wj-two");
  await sessionInfo("wj-two-done", known.wj);
  trace("turn.requests", { label: "wj-two", continued: Boolean(command("wj-two-after")), requests: requestsOf(known.wj, twoMark) });
  const messageMark = records.length;
  await send(known.wj, "wj-message");
  if (await soft(() => asked(known.wj, messageMark), "Worker J asked (message)", 20000)) {
    await settle(500);
    const [ask] = (await pending("wj-message-asking", known.wj)).asks;
    const answer = await request("POST", `/api/session/${known.wj}/permission/${ask.id}/reply`, { decision: "reject", message: "MSG-479 read the fixture notes instead" });
    trace("permission.reply", { label: "wj-message", decision: "reject", message: true, status: answer.status });
  }
  await idle(known.wj, "wj-message");
  await sessionInfo("wj-message-done", known.wj);
  trace("turn.requests", { label: "wj-message", continued: Boolean(command("wj-message-after")), requests: requestsOf(known.wj, messageMark) });

  // Scenario reviewer: Worker A's own Sub-agent at the default depth.
  trace("scenario", { name: "reviewer" });
  await idle(known.wa, "wa-before-review");
  await send(known.wa, "wa-review");
  const reviewing = await soft(() => command("reviewer-hold", "start"), "reviewer holding", 30000);
  if (reviewing) {
    await settle(500);
    known.reviewer = claimOf("reviewer-start");
    await sessionInfo("reviewer", known.reviewer);
    stateFiles("reviewer-running");
    observe("reviewer-running");
    check("tree-a-reviewer-running", tree.a);
    check("tree-c-reviewer-running", tree.c);
  }
  await idle(known.wa, "wa-review");
  await settle(1000);
  check("tree-c-reviewer-ended", tree.c);

  // Scenario finish: Worker A stops its run and moves back to the main
  // Worktree; Worktree a becomes removable.
  trace("scenario", { name: "finish" });
  await prompt(known.wa, "wa-finish");
  await settle(1500);
  await sessionInfo("wa-finished", known.wa);
  stateFiles("wa-finished");
  observe("wa-finished");
  check("tree-a-wa-finished", tree.a);

  // Scenario interrupt: Worker C interrupted mid-turn, then deleted.
  trace("scenario", { name: "interrupt" });
  const madeC = await guardedCall("runner-create-c", ["api", "POST", "/api/session", "-d", JSON.stringify(workerBody(tree.c, "Worker C", "issue-4", known.lead))]);
  known.wc = idIn(madeC.stdout, "ses");
  await send(known.wc, "wc");
  await waitFor(() => command("wc-hold", "start"), "Worker C holding", 30000);
  await settle(500);
  await sessionInfo("wc-holding", known.wc);
  trace("guarded", { label: "wc-interrupt", ...(await guardedCall("runner-interrupt-c", ["api", "POST", `/api/session/${known.wc}/interrupt`])) });
  await settle(1500);
  await active("wc-interrupted");
  await sessionInfo("wc-interrupted", known.wc);
  stateFiles("wc-interrupted");
  observe("wc-interrupted");
  check("tree-c-wc-interrupted", tree.c);
  trace("session.delete", { label: "wc", ...cli(["session", "delete", known.wc]) });
  await settle(2000);
  await sessionInfo("wc-deleted", known.wc);
  stateFiles("wc-deleted");
  observe("wc-deleted");
  check("tree-c-wc-deleted", tree.c);

  // Scenario delete-lead: Lead 2 deleted while its Worker D runs.
  trace("scenario", { name: "delete-lead" });
  known.lead2 = await session("Lead2", fixture);
  await prompt(known.lead2, "lead2-bind");
  await prompt(known.lead2, "lead2-dispatch");
  known.wd = createdBy("lead2-create-d");
  await waitFor(() => command("wd-hold", "start"), "Worker D holding", 30000);
  await settle(500);
  trace("delete", { label: "lead2", ...(await request("DELETE", `/api/session/${known.lead2}`)) });
  await settle(2000);
  await sessionInfo("lead2-deleted", known.lead2);
  await sessionInfo("wd-after-lead-deleted", known.wd);
  observe("lead2-deleted");
  check("tree-d-lead2-deleted", tree.d);
  await soft(() => command("wd-after"), "Worker D went on", 30000);
  await idle(known.wd, "wd");
  stateFiles("wd-ended");
  observe("wd-ended");

  // Scenario move-lead: the Lead moved to Worktree f while Worker E runs.
  trace("scenario", { name: "move-lead" });
  const moveMark = records.length;
  await prompt(known.lead, "lead-dispatch-e");
  known.we = createdBy("lead-create-e");
  await waitFor(() => command("we-hold", "start"), "Worker E holding", 30000);
  await move(known.lead, tree.f, "lead-moved");
  stateFiles("lead-moved");
  observe("lead-moved");
  check("tree-e-lead-moved", tree.e);
  check("tree-f-lead-moved", tree.f);
  await soft(() => command("we-after"), "Worker E went on", 30000);
  await soft(() => noticedBy(known.lead, "synthetic", "we-done", moveMark).length, "Lead noticed Worker E", 20000);
  await idle(known.lead, "lead-we-notice");
  await sessionInfo("lead-after-we-notice", known.lead);
  await move(known.lead, fixture, "lead-back");
  await prompt(known.lead, "lead-back");
  stateFiles("lead-back");
  observe("lead-back");
  check("tree-f-lead-back", tree.f);

  // Scenario option-b: a Worker dispatched with a background `opencode run`
  // from the Lead's shell; the shell's end is the Lead's notice.
  trace("scenario", { name: "option-b" });
  const runMark = records.length;
  await prompt(known.lead, "lead-run-b");
  await soft(() => noticedBy(known.lead, "shell", null, runMark).length, "Lead noticed the run's end", 60000);
  await idle(known.lead, "lead-run-b-notice");
  known.wf = claimOf("wf-start");
  await sessionInfo("wf", known.wf);
  observe("wf-ended");
  check("tree-f-wf-ended", tree.f);

  // Scenario service-restart: the service stopped while Worker B and the Lead
  // each hold a shell, Worker H waits on its ask, Worker I's turn was
  // interrupted and Worker E is idle; `opencode api` starts it again. Which
  // turns resume, what Dashpot is told, and a `work start` from a resumed turn.
  trace("scenario", { name: "service-restart" });
  known.wh = idIn((await guardedCall("runner-create-h", ["api", "POST", "/api/session", "-d",
    JSON.stringify(workerBody(tree.h, "Worker H", "issue-11", known.lead))])).stdout, "ses");
  known.wi = idIn((await guardedCall("runner-create-i", ["api", "POST", "/api/session", "-d",
    JSON.stringify(workerBody(tree.i, "Worker I", "issue-12", known.lead))])).stdout, "ses");
  assert(known.wh && known.wi, "Workers H and I made");
  await send(known.wi, "wi");
  await waitFor(() => command("wi-hold", "start"), "Worker I holding", 30000);
  await settle(500);
  trace("interrupt", { label: "wi", ...(await request("POST", `/api/session/${known.wi}/interrupt`)) });
  await settle(1500);
  const whMark = records.length;
  await send(known.wh, "wh");
  await soft(() => asked(known.wh, whMark), "Worker H asked", 30000);
  await send(known.wb, "wb-long");
  await send(known.lead, "lead-long");
  await waitFor(() => command("wb-long-hold", "start") && command("lead-long-hold", "start"), "Worker B and the Lead holding", 30000);
  await settle(500);
  const restartSet = { wb: known.wb, lead: known.lead, wh: known.wh, wi: known.wi, we: known.we };
  for (const [name, id] of Object.entries(restartSet)) await sessionInfo(`${name}-before-stop`, id);
  await pending("wh-before-stop", known.wh);
  observe("before-stop");
  const stopping = service.pid;
  service.events?.abort();
  const stopTime = Date.now();
  trace("service.stop", { label: "mid-turn", ...cli(["service", "stop"]) });
  await waitFor(() => !alive(stopping), "service stopped", 15000);
  await settle(1500);
  trace("service.stopped", { pid: stopping, registered: Boolean(registration()), shellsEnded: { wb: Boolean(command("wb-long-hold")), lead: Boolean(command("lead-long-hold")) } });
  stateFiles("stopped");
  observe("stopped");
  check("tree-b-stopped", tree.b);
  check("tree-h-stopped", tree.h);
  const restartMark = records.length;
  const restartTime = Date.now();
  // A client that subscribes as soon as the private port answers, so the
  // restarted service's first events reach the trace.
  let early = null;
  const earlyWatch = (async () => {
    for (let attempt = 0; attempt < 3000 && !early; attempt++) {
      const up = await fetch(service.url + "/api/info", { headers: { authorization }, signal: AbortSignal.timeout(500) }).then((response) => response.ok).catch(() => false);
      if (up) {
        early = subscribe("restarted");
        service.events = early;
        trace("subscribed", { label: "restarted", ms: Date.now() - restartTime });
        return;
      }
      await delay(20);
    }
  })();
  // `opencode api` with no registered service, in the fixture's environment.
  const apiStart = await new Promise((resolve) => {
    assert(env.XDG_STATE_HOME.startsWith(root) && env.HOME.startsWith(root), "the fixture's environment");
    const child = spawn(opencode, ["api", "GET", "/api/info"], { cwd: fixture, env: { ...env, PWD: fixture }, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const timer = setTimeout(() => child.kill("SIGKILL"), 60000);
    child.on("exit", (status, signal) => { clearTimeout(timer); resolve({ status, signal, ms: Date.now() - restartTime, stdout: retained(stdout).slice(0, 600), stderr: retained(stderr).slice(-600) }); });
  });
  trace("api.unregistered", { ...apiStart, registered: registration() ? Object.keys(registration()).toSorted() : null });
  if (!registration() || !alive(registration().pid)) trace("service.start", { label: "after-api", ...cli(["service", "start"]) });
  await earlyWatch;
  await awaitService("restarted", { subscribeAgain: !early });
  // A resumed Worker B holds before its `work start`, so its run can be seen
  // between the resumption and the binding.
  if (await soft(() => command("wb-resumed-hold", "start"), "Worker B resumed", 30000)) {
    await settle(500);
    stateFiles("resumed-holding");
    observe("resumed-holding");
    check("tree-b-resumed-holding", tree.b);
  }
  await soft(() => command("wb-resumed-show") && command("lead-resumed-show"), "resumed turns bound", 40000);
  await settle(8000);
  const restartIds = Object.values(restartSet);
  trace("resumed", { holdsRerun: { wb: commandsOf("wb-long-hold").length, lead: commandsOf("lead-long-hold").length, wi: commandsOf("wi-hold").length },
    sessions: Object.fromEntries(Object.entries(restartSet).map(([name, id]) => [name, { requests: requestsOf(id, restartMark), executions: executions(id, restartMark),
      plugin: pluginSaw(id, restartMark), asked: records.filter((record) => record.kind === "server.event" && record.type === "permission.asked" && record.sessionID === id
        && record.receipt > restartMark).length }])),
    pluginSetups: records.filter((record) => record.kind === "plugin.event" && record.type === "plugin.setup" && record.receipt > restartMark)
      .map((record) => ({ pid: record.pid, ms: record.at - restartTime })),
    hooks: hookOutcomes(restartIds, stopTime).map((entry) => ({ ...entry, ms: entry.time - restartTime, time: undefined })) });
  for (const [name, id] of Object.entries(restartSet)) await sessionInfo(`${name}-after-restart`, id);
  await pending("wh-after-restart", known.wh);
  await inbox("wh-after-restart", known.wh);
  stateFiles("restarted");
  observe("restarted");
  for (const name of ["b", "h", "i", "e"]) check(`tree-${name}-restarted`, tree[name]);
  // Worker H's ask, if it outlived the restart, answered.
  for (const ask of (await pending("wh-answering", known.wh)).asks) {
    const answer = await request("POST", `/api/session/${known.wh}/permission/${ask.id}/reply`, { decision: "once" });
    trace("permission.reply", { label: "wh-after-restart", decision: "once", status: answer.status });
  }
  for (const id of [known.wh, known.wb, known.lead]) await idle(id, "after-restart");
  await settle(1000);
  trace("resumed.after", { wh: requestsOf(known.wh, restartMark), whAfterAsk: Boolean(command("wh-after-ask")),
    hooks: hookOutcomes(restartIds, stopTime).map((entry) => ({ ...entry, ms: entry.time - restartTime, time: undefined })) });
  // A fresh prompt to Worker B after the resumed turn: its `work start`.
  await prompt(known.wb, "wb-recover");
  await settle(1000);
  stateFiles("recovered");
  observe("recovered");
  check("tree-b-recovered", tree.b);
  check("tree-h-recovered", tree.h);

  // Scenario standalone: a `--standalone` Lead dispatches Worker SA through
  // `opencode api`, and Worker SA's notice comes back while the Lead holds.
  trace("scenario", { name: "standalone" });
  const standalone = client("sa", ["run", "--standalone", "-m", "loop/fixture", "--title", "SALead", "PROBE:sa-lead"]);
  await soft(() => command("sa-lead-hold", "start"), "standalone Lead holding", 60000);
  known.sa = claimOf("sa-lead-hold");
  known.wsa = createdBy("sa-create");
  await soft(() => command("wsa-after"), "Worker SA went on", 30000);
  await soft(() => standalone.exited, "standalone Lead exited", 60000);
  await settle(4000);
  trace("standalone", { serverPid: command("sa-lead-hold", "start")?.env?.DASHPOT_OPENCODE_PID ?? null, servicePid: service.pid,
    woken: commandsOf("sa-woken").map((record) => ({ serverPid: record.env?.DASHPOT_OPENCODE_PID ?? null, session: record.env?.OPENCODE_SESSION_ID ?? null })) });
  if (known.sa) await sessionInfo("sa-lead-after", known.sa);
  if (known.wsa) await sessionInfo("wsa-after", known.wsa);
  observe("standalone-ended");

  // Scenario long-wait: Worker K's ask holds its turn open past five minutes
  // while `opencode api` waits on the session and streams events; the ask is
  // answered at five and a half minutes, so a call a deadline cuts ends first.
  trace("scenario", { name: "long-wait" });
  known.wk = idIn((await guardedCall("runner-create-k", ["api", "POST", "/api/session", "-d",
    JSON.stringify(workerBody(tree.k, "Worker K", "issue-14", known.lead))])).stdout, "ses");
  const waitMark = records.length;
  await send(known.wk, "wk");
  if (await soft(() => asked(known.wk, waitMark), "Worker K asked", 30000)) {
    const longStart = Date.now();
    const timed = (promise) => promise.then((result) => ({ status: result.status, ms: Date.now() - longStart, bytes: result.stdout.length,
      head: retained(result.stdout).slice(0, 200) }));
    const waiting = timed(guardedCall("runner-wait-k", ["api", "POST", `/api/experimental/session/${known.wk}/wait`], { extra: { SPIKE_GUARD_TIMEOUT: "420000" } }));
    const streaming = timed(guardedCall("runner-event-stream", ["api", "GET", "/api/event"], { extra: { SPIKE_GUARD_TIMEOUT: "390000" } }));
    const endedBeforeAnswer = await Promise.race([waiting.then(() => true), delay(330000).then(() => false)]);
    const answeredAt = Date.now() - longStart;
    await answerAll("wk", known.wk);
    const [waited, streamed] = await Promise.all([waiting, streaming]);
    trace("long.wait", { answeredAt, endedBeforeAnswer, wait: waited, stream: streamed });
    await idle(known.wk, "wk");
  }

  // Scenario always, last, since the rule it saves would answer every later
  // ask: an ask allowed `always`, where that rule lands, whether Worker J or
  // the Lead is asked again, and the rule's removal.
  trace("scenario", { name: "always" });
  const configFile = path.join(configHome, "opencode.json");
  // Saved rules are listed per Project: with no `projectID`, the listing is
  // empty even when a rule applies.
  const projectID = (await request("GET", `/api/session/${known.wj}`)).body?.projectID ?? null;
  const savedList = async (label) => {
    const items = {};
    for (const [scope, route] of [["unscoped", "/api/permission/saved"], ["project", `/api/permission/saved?projectID=${encodeURIComponent(projectID)}`]]) {
      const answer = await request("GET", route);
      items[scope] = Array.isArray(answer.body) ? answer.body.map((item) => JSON.parse(retained(JSON.stringify(item))))
        : { status: answer.status, raw: retained(JSON.stringify(answer.body)).slice(0, 800) };
    }
    return trace("permissions.saved", { label, projectID, items, config: sha256(configFile) });
  };
  const savedBefore = await savedList("before-always");
  const alwaysMark = records.length;
  await send(known.wj, "wj-always");
  if (await soft(() => asked(known.wj, alwaysMark), "Worker J asked (always)", 20000)) {
    await settle(500);
    const [ask] = (await pending("wj-always-asking", known.wj)).asks;
    const answer = await request("POST", `/api/session/${known.wj}/permission/${ask.id}/reply`, { decision: "always" });
    trace("permission.reply", { label: "wj-always", decision: "always", status: answer.status });
  }
  await idle(known.wj, "wj-always");
  const savedAfter = await savedList("after-always");
  if (savedAfter.config !== savedBefore.config) trace("config.changed", { content: retained(readFileSync(configFile, "utf8")).slice(0, 1500) });
  // Asked again: Worker J at Worktree j, and the Lead at the main Worktree.
  for (const [label, id] of [["wj-again", known.wj], ["lead-read", known.lead]]) {
    const mark = records.length;
    await send(id, label);
    const again = await soft(() => asked(id, mark) || command(`${label}-after`), `${label} asked or went on`, 20000) && Boolean(asked(id, mark));
    trace("asked.again", { label, asked: again });
    if (again) { await settle(500); await answerAll(label, id); }
    await idle(id, label);
  }
  // The rule across a service restart: stopped and started again, then
  // Worker J reads once more.
  {
    const before = service.pid;
    service.events?.abort();
    trace("service.stop", { label: "always", ...cli(["service", "stop"]) });
    await waitFor(() => !alive(before), "service stopped (always)", 15000);
    trace("service.start", { label: "always", ...cli(["service", "start"]) });
    await awaitService("always-restarted");
    await savedList("after-restart");
    const mark = records.length;
    await send(known.wj, "wj-restarted");
    const again = await soft(() => asked(known.wj, mark) || command("wj-restarted-after"), "wj-restarted asked or went on", 20000) && Boolean(asked(known.wj, mark));
    trace("asked.again", { label: "wj-restarted", asked: again });
    if (again) { await settle(500); await answerAll("wj-restarted", known.wj); }
    await idle(known.wj, "wj-restarted");
  }
  // The `always` rule removed, and the configuration restored if it changed.
  const listed = (saved) => Object.values(saved.items).flatMap((items) => Array.isArray(items) ? items : []);
  const beforeIds = new Set(listed(savedBefore).map((item) => item.id));
  for (const id of new Set(listed(savedAfter).map((item) => item.id))) {
    if (beforeIds.has(id)) continue;
    trace("permission.saved.remove", { id, status: (await request("DELETE", `/api/permission/saved/${id}`)).status });
  }
  if (sha256(configFile) !== savedBefore.config) { writeFileSync(configFile, opencodeConfig); trace("config.restored", { config: sha256(configFile) }); }
  await savedList("after-removal");
  // Removed: Worker J is asked again.
  const removedMark = records.length;
  await send(known.wj, "wj-removed");
  const askedAfterRemoval = await soft(() => asked(known.wj, removedMark) || command("wj-removed-after"), "wj-removed asked or went on", 20000) && Boolean(asked(known.wj, removedMark));
  trace("asked.again", { label: "wj-removed", asked: askedAfterRemoval });
  if (askedAfterRemoval) { await settle(500); await answerAll("wj-removed", known.wj); }
  await idle(known.wj, "wj-removed");

  operator("end");
  trace("event.types", { types: [...eventTypes].toSorted() });
  trace("models", { requests: Object.fromEntries(modelRequests) });
  trace("known", { sessions: known });
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)) });
  console.error(error);
} finally {
  // The helper's own record of each run: outcomes by kind, and every outcome
  // that did not succeed.
  const outcomes = eventLog().filter((event) => String(event["dashpot.process.kind"] ?? "").startsWith("hook:opencode"));
  const summary = {};
  for (const event of outcomes) {
    const entry = summary[event["dashpot.process.kind"]] ??= { runs: 0, results: {} };
    if (event["event.name"] === "process.end") entry.runs += 1;
    if (event["event.name"] === "hook.outcome") entry.results[event["dashpot.outcome.result"]] = (entry.results[event["dashpot.outcome.result"]] ?? 0) + 1;
  }
  trace("events", { summary, unsuccessful: outcomes.filter((event) => event["event.name"] === "hook.outcome" && event["dashpot.outcome.result"] !== "succeeded")
    .map((event) => ({ kind: event["dashpot.process.kind"], result: event["dashpot.outcome.result"], reason: event["dashpot.hook.reason"] ?? null })) });
  for (const state of clients) if (!state.exited) state.child.kill("SIGKILL");
  if (service.pid && alive(service.pid)) {
    trace("service.stop", { label: "final", ...cli(["service", "stop"]) });
    try { await waitFor(() => !alive(service.pid), "final service exit", 10000); } catch {}
  }
  service.events?.abort();
  await delay(1000);
  for (const entry of fixtureProcesses()) {
    if (entry.pid === process.pid) continue;
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm, cmdline: retained(entry.cmdline) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid).filter((pid) => pid !== process.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
  process.exit(0);
}
