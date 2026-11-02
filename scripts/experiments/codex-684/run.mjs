// Push and lease-push run for Issue #684: drives a pinned Codex CLI against a
// loopback Responses API fixture, with an isolated CODEX_HOME whose daemon
// updater is off, and has a sandboxed v2 Worker run `git ls-remote`, a first
// push, a lease push and the pre-push hook against a disposable remote, once
// for each F9 transport remedy and once for a baseline without one.
//
// The disposable remote is one bare repository served two ways on loopback,
// both by this process, outside every sandbox: a fixture `sshd` whose only
// key is a fixture key and whose forced command is `git-shell`, and an HTTPS
// smart server, `git http-backend` behind Basic authentication with a fixture
// token and a self-signed certificate. The fixture's `origin` is the scp-like
// SSH URL `fixture-forge:owner/repo.git`, which no remedy rewrites. Each
// scenario is one `codex app-server` over stdio, launched as the
// execute-issues skill's resume command grants: `workspace-write`, the
// Worktree Root and the Git directory as writable roots, and the network on.
// Its remedy, if any, reaches the Worker's shell through
// `shell_environment_policy.set` alone:
//
//   baseline            the system SSH configuration, with the fixture's
//                       identity named on the command line;
//   https               remedy 1: GIT_CONFIG_* sets `url.<https>.insteadOf`
//                       and `!gh auth git-credential` as the credential
//                       helper, with `gh`'s own store in an isolated
//                       GH_CONFIG_DIR;
//   ssh-config          remedy 2: GIT_SSH_COMMAND="ssh -F <user-owned config>",
//                       with a fixture agent's socket in SSH_AUTH_SOCK;
//   escalated-never     remedy 3 under approval policy `never`;
//   escalated-approved  remedy 3 under `on-request`, each escalation
//                       approved by this runner for the operator.
//
// No real model, forge, credential, SSH agent or key of the operator's is
// used: `gh` reads only the fixture's store, and every `ssh` reads a file
// named with `-F`, never the operator's `~/.ssh/config`. The trace records
// names, statuses, scheme classes and digests, never a Git configuration
// value or a credential, with paths replaced by `$ROOT`, `$HOME`,
// `$CHECKOUT`, `$EXPERIMENT` and `~`.
//
//   node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [codex binary]
import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, copyFileSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import https from "node:https";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.166.0";
// A fixture below a harness session would run inside that session's own
// sandbox, if it has one, and its processes would join that session's tree.
const runnerAncestry = ancestry(process.ppid, 64, 1);
const isHarness = (entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline);
const harnessAbove = runnerAncestry.find(isHarness);
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);

// `workspace-write` makes `/tmp` writable by default, so the fixture lives
// under `/var/tmp`, as a person's checkout lives outside it, and only the
// granted roots inside it are writable to a Worker.
const root = mkdtempSync(path.join("/var/tmp", "dashpot-codex-684-"));
console.log(`Isolated fixture: ${root}`);
const main = path.join(root, "repository");
const worktreeRoot = path.join(root, "repository.worktrees");
const gitDir = path.join(main, ".git");
const outside = path.join(root, "outside");
const sshDir = path.join(root, "ssh");
const privateKey = path.join(sshDir, "private", "client_key");
const publicKey = path.join(sshDir, "client_key.pub");
const knownHosts = path.join(sshDir, "known_hosts");
const userSshConfig = path.join(sshDir, "config");
const agentSocket = path.join(sshDir, "agent", "agent.sock");
const server = path.join(root, "server");
const served = path.join(server, "srv");
const bare = path.join(served, "owner", "repo.git");
const receiveLog = path.join(server, "receive.jsonl");
const sshSessionLog = path.join(server, "ssh-sessions.jsonl");
const certificate = path.join(server, "tls", "cert.pem");
const fixtureHome = path.join(root, "home");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
// The fixture token is a random value of this run's own. It never leaves
// this process except to `gh`'s fixture store and the fixture server, and
// the trace replaces it wherever it might appear.
const token = randomBytes(24).toString("hex");
// The operator's home directory, user name, host name and the fixture's root
// never enter the trace.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const userName = new RegExp(`\\b${os.userInfo().username}\\b`, "g");
const clean = (text) => String(text).replaceAll(token, "<fixture-token>").replaceAll(fixtureHome, "$HOME").replaceAll(root, "$ROOT")
  .replaceAll(path.basename(root), "<fixture>").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~")
  .replace(hostName, "<host>").replace(userName, "<user>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, clean(JSON.stringify(record)) + "\n");
  return record;
};
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const readJsonLines = (file) => existsSync(file) ? readFileSync(file, "utf8").trim().split("\n").filter(Boolean).map(parseJson).filter(Boolean) : [];

// The pinned release runs through a fixture-local `codex` on PATH.
const fixtureBin = path.join(root, "bin");
for (const dir of [main, worktreeRoot, outside, path.dirname(privateKey), path.dirname(agentSocket), served, path.dirname(certificate),
  fixtureHome, fixtureBin]) mkdirSync(dir, { recursive: true });
symlinkSync(binary, path.join(fixtureBin, "codex"));
// The Host Process environment every scenario starts from. `gh` keeps its
// fixture store in GH_CONFIG_DIR; GIT_TERMINAL_PROMPT=0 makes a missing
// credential fail rather than wait for a terminal.
const env = {
  PATH: `${fixtureBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: fixtureHome,
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  CODEX_HOME: path.join(root, "codex-home"),
  GH_CONFIG_DIR: path.join(root, "gh"),
  GH_NO_UPDATE_NOTIFIER: "1",
  GIT_TERMINAL_PROMPT: "0",
  TERM: "dumb",
  LANG: "C.UTF-8",
};
for (const dir of [env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.CODEX_HOME, env.GH_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);
const run = (command, args, options = {}) => spawnSync(command, args, { env, encoding: "utf8", timeout: 60000, ...options });
const must = (command, args, options = {}) => {
  const ran = run(command, args, options);
  assert.equal(ran.status, 0, `${command} ${args[0]}: ${clean(ran.stderr ?? "")}`);
  return ran.stdout;
};

// Keys and certificate, all the fixture's own.
must("ssh-keygen", ["-q", "-t", "ed25519", "-N", "", "-C", "fixture-684-host", "-f", path.join(server, "host_key")]);
must("ssh-keygen", ["-q", "-t", "ed25519", "-N", "", "-C", "fixture-684-client", "-f", privateKey]);
copyFileSync(`${privateKey}.pub`, publicKey);
must("openssl", ["req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-days", "1", "-subj", "/CN=127.0.0.1",
  "-addext", "subjectAltName=IP:127.0.0.1", "-keyout", path.join(server, "tls", "key.pem"), "-out", certificate]);

// The disposable remote: one bare repository whose post-receive hook records
// each ref update with the transport that carried it.
must("git", ["init", "--quiet", "--bare", "--initial-branch=main", bare]);
must("git", ["-C", bare, "config", "http.receivepack", "true"]);
writeFileSync(path.join(bare, "hooks", "post-receive"), `#!/bin/sh
via=https
[ -n "$SSH_CONNECTION" ] && via=ssh
while read old new ref; do
  printf '{"via":"%s","old":"%s","new":"%s","ref":"%s","time":%s}\\n' "$via" "$old" "$new" "$ref" "$(date +%s%3N)" >> ${JSON.stringify(receiveLog)}
done
`, { mode: 0o755 });

const listen = async (server, port = 0) => { server.listen(port, "127.0.0.1"); await once(server, "listening"); return server.address().port; };
const freePort = async () => { const probe = net.createServer(); const port = await listen(probe); probe.close(); await once(probe, "close"); return port; };

// The fixture sshd: the runner's own user, a fixture host key, one fixture
// client key whose forced command runs `git-shell` in the served directory,
// and a session HOME of the fixture's, so the login shell reads none of the
// operator's start-up files.
const sshPort = await freePort();
const wrapper = path.join(server, "git-shell-wrapper.sh");
writeFileSync(wrapper, `#!/bin/sh
printf '{"verb":"%s","time":%s}\\n' "\${SSH_ORIGINAL_COMMAND%% *}" "$(date +%s%3N)" >> ${JSON.stringify(sshSessionLog)}
cd ${JSON.stringify(served)} && exec git-shell -c "$SSH_ORIGINAL_COMMAND"
`, { mode: 0o755 });
writeFileSync(path.join(server, "authorized_keys"), `restrict,command="${wrapper}" ${readFileSync(publicKey, "utf8").trim()}\n`, { mode: 0o600 });
const sshdConfig = path.join(server, "sshd_config");
writeFileSync(sshdConfig, `ListenAddress 127.0.0.1
Port ${sshPort}
HostKey ${path.join(server, "host_key")}
AuthorizedKeysFile ${path.join(server, "authorized_keys")}
PidFile none
UsePAM no
StrictModes no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowAgentForwarding no
AllowTcpForwarding no
X11Forwarding no
SetEnv HOME=${path.join(server, "home")}
LogLevel VERBOSE
`);
mkdirSync(path.join(server, "home"));
must("/usr/sbin/sshd", ["-t", "-f", sshdConfig]);
const children = [];
const sshd = spawn("/usr/sbin/sshd", ["-D", "-f", sshdConfig, "-E", path.join(server, "sshd.log")], { env, stdio: "ignore" });
children.push(sshd);
writeFileSync(knownHosts, `fixture-forge ${readFileSync(path.join(server, "host_key.pub"), "utf8").trim().split(" ").slice(0, 2).join(" ")}\n`);

// The fixture SSH agent, holding only the fixture key, on a socket in a
// directory the sandbox does not grant.
const agent = spawn("ssh-agent", ["-D", "-a", agentSocket], { env, stdio: "ignore" });
children.push(agent);
for (let tries = 0; tries < 50 && !existsSync(agentSocket); tries++) await delay(100);
must("ssh-add", ["-q", privateKey], { env: { ...env, SSH_AUTH_SOCK: agentSocket } });

// The HTTPS smart server: Basic authentication with the fixture token, then
// `git http-backend` over the served directory.
let scenario = "setup";
const raw = async (req) => { const chunks = []; for await (const chunk of req) chunks.push(chunk); return Buffer.concat(chunks); };
const httpsServer = https.createServer({ key: readFileSync(path.join(server, "tls", "key.pem")), cert: readFileSync(certificate) }, async (req, res) => {
  try {
    const url = new URL(req.url, "https://fixture");
    const input = await raw(req);
    const [type, credentials] = (req.headers.authorization ?? "").split(" ");
    const password = type === "Basic" && credentials ? Buffer.from(credentials, "base64").toString("utf8").split(":").slice(1).join(":") : null;
    const authorized = password === token;
    const entry = { scenario, method: req.method, path: url.pathname, service: url.searchParams.get("service"), credentialSent: password !== null, authorized };
    if (!authorized) {
      trace("remote.request", { transport: "https", ...entry, status: 401 });
      res.writeHead(401, { "www-authenticate": 'Basic realm="fixture"' });
      res.end();
      return;
    }
    const cgi = spawn("git", ["http-backend"], { env: { PATH: env.PATH, HOME: env.HOME, GIT_PROJECT_ROOT: served, GIT_HTTP_EXPORT_ALL: "1",
      REQUEST_METHOD: req.method, PATH_INFO: url.pathname, QUERY_STRING: url.search.slice(1), CONTENT_TYPE: req.headers["content-type"] ?? "",
      CONTENT_LENGTH: String(input.length), HTTP_CONTENT_ENCODING: req.headers["content-encoding"] ?? "", GIT_PROTOCOL: req.headers["git-protocol"] ?? "",
      REMOTE_ADDR: "127.0.0.1", REMOTE_USER: "fixture" }, stdio: ["pipe", "pipe", "ignore"] });
    cgi.stdin.end(input);
    const out = [];
    cgi.stdout.on("data", (chunk) => out.push(chunk));
    await once(cgi, "close");
    const response = Buffer.concat(out);
    const crlf = response.indexOf("\r\n\r\n");
    const split = crlf >= 0 ? crlf : response.indexOf("\n\n");
    const headers = response.subarray(0, split).toString("utf8").split(/\r?\n/).map((line) => [line.slice(0, line.indexOf(":")), line.slice(line.indexOf(":") + 1).trim()]);
    const status = Number((headers.find(([name]) => name.toLowerCase() === "status")?.[1] ?? "200").split(" ")[0]);
    trace("remote.request", { transport: "https", ...entry, status });
    res.writeHead(status, Object.fromEntries(headers.filter(([name]) => name && name.toLowerCase() !== "status")));
    res.end(response.subarray(split + (crlf >= 0 ? 4 : 2)));
  } catch (error) {
    trace("server.error", { error: String(error?.stack ?? error) });
    if (!res.headersSent) res.writeHead(500);
    res.end();
  }
});
const httpsPort = await listen(httpsServer);
const httpsBase = `https://127.0.0.1:${httpsPort}/`;
// `gh`'s own store for the fixture host, as `gh auth login` would leave it
// with insecure storage: the fixture token, never the operator's.
writeFileSync(path.join(env.GH_CONFIG_DIR, "hosts.yml"), `127.0.0.1:${httpsPort}:
    users:
        fixture:
            oauth_token: ${token}
    git_protocol: https
    oauth_token: ${token}
    user: fixture
`, { mode: 0o600 });
for (let tries = 0; tries < 50; tries++) {
  const ready = await new Promise((resolve) => { const socket = net.connect(sshPort, "127.0.0.1", () => { socket.end(); resolve(true); }); socket.on("error", () => resolve(false)); });
  if (ready) break;
  await delay(100);
}

// Remedy 2's user-owned configuration, mode 600, naming the fixture host, its
// known key and the agent's fixture key by its public half.
writeFileSync(userSshConfig, `Host fixture-forge
  HostName 127.0.0.1
  Port ${sshPort}
  HostKeyAlias fixture-forge
  UserKnownHostsFile ${knownHosts}
  StrictHostKeyChecking yes
  IdentitiesOnly yes
  IdentityFile ${publicKey}
  BatchMode yes
`, { mode: 0o600 });
// The system configuration exactly as plain `ssh` reads it, with the
// fixture's identity named on the command line: `-F` keeps the operator's
// own `~/.ssh/config` out, and the system file's `Include` is read as usual.
const systemSsh = ["ssh", "-F", "/etc/ssh/ssh_config", "-o", "HostName=127.0.0.1", "-o", `Port=${sshPort}`, "-o", "HostKeyAlias=fixture-forge",
  "-o", `UserKnownHostsFile=${knownHosts}`, "-o", "StrictHostKeyChecking=yes", "-o", "IdentityAgent=none", "-o", "IdentitiesOnly=yes",
  "-o", `IdentityFile=${privateKey}`, "-o", "BatchMode=yes"].join(" ");
const remedies = {
  baseline: { GIT_SSH_COMMAND: systemSsh },
  https: { GIT_CONFIG_COUNT: "2", GIT_CONFIG_KEY_0: `url.${httpsBase}.insteadOf`, GIT_CONFIG_VALUE_0: "fixture-forge:",
    GIT_CONFIG_KEY_1: `credential.${httpsBase.slice(0, -1)}.helper`, GIT_CONFIG_VALUE_1: "!gh auth git-credential", GIT_SSL_CAINFO: certificate },
  "ssh-config": { GIT_SSH_COMMAND: `ssh -F ${userSshConfig}`, SSH_AUTH_SOCK: agentSocket },
};

// The disposable repository: a tracked pre-push hook that reports through
// `prepush.mjs`, the operator-style identity in the fixture HOME, and
// `origin` as an scp-like SSH URL.
writeFileSync(path.join(fixtureHome, ".gitconfig"), "[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n[init]\n\tdefaultBranch = main\n");
const git = (...args) => must("git", ["-C", main, ...args]);
git("init", "--quiet");
writeFileSync(path.join(main, "README.md"), "Disposable fixture.\n");
writeFileSync(path.join(main, "fixture.txt"), "Fixture.\n");
mkdirSync(path.join(main, ".githooks"));
writeFileSync(path.join(main, ".githooks", "pre-push"), `#!/bin/sh
exec ${JSON.stringify(process.execPath)} ${JSON.stringify(path.join(here, "prepush.mjs"))} ${JSON.stringify(outside)} "$@"
`, { mode: 0o755 });
git("add", "-A");
git("-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "Disposable fixture");
git("config", "core.hooksPath", ".githooks");
git("remote", "add", "origin", "fixture-forge:owner/repo.git");
// The seeding push skips the hook: only a Worker's pushes report.
git("push", "--quiet", "--no-verify", bare, "main");
const remoteUrlDigest = () => sha(run("git", ["-C", main, "config", "--get", "remote.origin.url"]).stdout.trim());
const scenarioNames = ["baseline", "https", "ssh-config", "escalated-never", "escalated-approved"];
for (const name of scenarioNames) git("worktree", "add", "--quiet", "-b", name, path.join(worktreeRoot, name));

// The fixture model is scripted per directive, as in the codex-639 run. The
// latest input item that is not a tool call and carries `SPIKE:<label>`
// selects the plan `plans[label]`; the number of tool outputs after that item,
// polls aside, selects the step. When the plan runs out, the model answers
// `DONE:<label>`. A command still running when its call yields is polled
// with `write_stdin` until it exits.
const stepScript = path.join(here, "step.mjs");
const quote = (arg) => `'${String(arg).replace(/'/g, "'\\''")}'`;
const exec = (name, steps, escalated = false) => ({ exec: `cd ${quote(path.join(worktreeRoot, name))} && node ${quote(stepScript)} worker-${name} ${name} ${quote(outside)} ${steps}`, escalated });
const plans = {};
const workerPlans = {
  baseline: [exec("baseline", "probe ls-remote commit push")],
  https: [exec("https", "probe ls-remote commit push amend lease stale-lease")],
  "ssh-config": [exec("ssh-config", "probe ls-remote commit push amend lease stale-lease unknown-host")],
  "escalated-never": [exec("escalated-never", "probe ls-remote commit push"), exec("escalated-never", "ls-remote", true), exec("escalated-never", "push", true)],
  "escalated-approved": [exec("escalated-approved", "probe ls-remote commit push"), exec("escalated-approved", "ls-remote", true),
    exec("escalated-approved", "push", true), exec("escalated-approved", "amend"), exec("escalated-approved", "lease stale-lease", true)],
};
for (const name of scenarioNames) {
  plans[`lead-${name}`] = [{ spawn: [`worker_${name.replaceAll("-", "_")}`, `worker-${name}`] }, { wait: `worker-${name}` }];
  plans[`worker-${name}`] = workerPlans[name];
}
const markerPattern = /(SPIKE|DONE):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const outputText = (item) => typeof item.output === "string" ? item.output : JSON.stringify(item.output ?? "");
const reports = [];
const reportKeys = new Set();
const modelRequests = [];
const done = new Set();
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
// The sandbox, approval and permission text Codex puts in a request, by tag.
const contextTags = /<(sandbox_mode|network_access|writable_roots|approval_policy|permissions instructions|cwd)>([\s\S]*?)<\/\1>/g;
const model = http.createServer(async (req, res) => {
  try {
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
      for (const match of outputText(item).matchAll(/STEP (\{.*\})/g)) {
        const report = parseJson(match[1]);
        const key = JSON.stringify(report);
        if (report && !reportKeys.has(key)) { reportKeys.add(key); reports.push({ scenario, thread, report }); trace("step", { scenario, thread, report }); }
      }
    }
    const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name, nested]) : [[null, tool.name ?? tool.type, tool]]);
    const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
    const sideThread = !offered("exec_command");
    const execParams = Object.keys(offered("exec_command")?.[2]?.parameters?.properties ?? {}).sort();
    const callNames = new Map(input.filter((item) => item.type === "function_call").map((item) => [item.call_id, item.name]));
    const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
    const planned = outputs.filter((item) => callNames.get(item.call_id) !== "write_stdin");
    const latestOutput = outputs.at(-1);
    const running = latestOutput && /Process running with session ID (\d+)/.exec(outputText(latestOutput));
    const plan = label && !sideThread ? plans[label] ?? [] : [];
    let step = running ? { poll: Number(running[1]) } : plan[Math.min(planned.length, plan.length)] ?? null;
    // A lead waits again while its Worker has not handed back.
    if (!running && plan.length && planned.length >= plan.length && plan.at(-1).wait && !done.has(plan.at(-1).wait)) step = plan.at(-1);
    if (step?.wait && done.has(step.wait) && !running) step = null;
    const toolCall = (name, args) => {
      const tool = offered(name);
      return tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
    };
    let item = null;
    let action = null;
    if (step?.poll) {
      action = "write_stdin";
      item = toolCall("write_stdin", { session_id: step.poll, chars: "", yield_time_ms: 30000 });
    } else if (step?.exec) {
      action = step.escalated ? "exec_command:escalated" : "exec_command";
      item = toolCall("exec_command", { cmd: step.exec, login: false, yield_time_ms: 30000,
        ...(step.escalated ? { sandbox_permissions: "require_escalated", justification: "Fixture: reach the disposable loopback remote outside the sandbox" } : {}) });
    } else if (step?.spawn) {
      const [taskName, child] = step.spawn;
      action = "spawn_agent";
      item = toolCall("spawn_agent", { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" });
    } else if (step?.wait) {
      action = "wait_agent";
      item = toolCall("wait_agent", { timeout_ms: 30000 });
    }
    if (label && !sideThread && !item && !step) done.add(label);
    const contexts = [...new Map(input.filter((entry) => !isCall(entry)).flatMap((entry) => [...JSON.stringify(entry).matchAll(contextTags)])
      .map((match) => [match[1], match[2].replace(/\\n/g, " ").replace(/\s+/g, " ").trim().slice(0, 300)])).entries()];
    const request = trace("model.request", { scenario, thread, label, step: planned.length, polls: outputs.length - planned.length, inputItems: input.length, directiveAt,
      action, missing: Boolean(step && !item), sideThread, execParams, contexts: Object.fromEntries(contexts),
      lastOutput: latestOutput ? clean(outputText(latestOutput)).replace(/STEP \{.*\}/g, "STEP {…}").replace(/\s+/g, " ").slice(-600) : null });
    modelRequests.push(request);
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    const responseId = `resp_${records.length}`;
    sse(res, { type: "response.created", response: { id: responseId } });
    sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
    sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
    res.end();
  } catch (error) {
    trace("server.error", { error: String(error?.stack ?? error) });
    if (!res.headersSent) res.writeHead(500);
    res.end();
  }
});
const modelPort = await listen(model);

// The model catalog: `fixture-v2` declares multi-agent v2, so the lead and
// its Worker get the collaboration tools.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));
// The configuration sets no sandbox and no approval policy: each scenario
// sets both on its own command line.
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-v2"
model_catalog_json = ${JSON.stringify(catalogPath)}
model_provider = "fixture"
check_for_update_on_startup = false
suppress_unstable_features_warning = true

[features]
multi_agent = true
multi_agent_v2 = true
plugins = false
apps = false

[analytics]
enabled = false

[model_providers.fixture]
name = "Fixture"
base_url = "http://127.0.0.1:${modelPort}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0

[projects.${JSON.stringify(main)}]
trust_level = "trusted"
`);
// The fixture daemon's updater stays off, though no scenario starts the
// daemon: installing a release could replace the pinned binary mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
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
const stopChildren = () => {
  for (const entry of codexProcesses()) { try { process.kill(entry.pid, "SIGKILL"); } catch {} }
  for (const child of children) { try { child.kill("SIGTERM"); } catch {} }
};
for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, () => { stopChildren(); process.exit(1); });
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(200); }
  throw new Error(`Timed out: ${label}`);
};

// One `codex app-server` over stdio per scenario. It answers a command
// approval only in the scenario that approves escalations, and only for the
// fixture's own step script; every other server request is declined.
const appServer = async (name, overrides, approve) => {
  const args = overrides.flatMap((override) => ["-c", override]);
  const child = spawn("codex", [...args, "app-server"], { cwd: main, env, stdio: ["pipe", "pipe", "pipe"] });
  let next = 0;
  const pending = new Map();
  const notifications = [];
  const approvals = [];
  child.stderr.on("data", (chunk) => appendFileSync(path.join(root, `app-server-${name}.stderr`), chunk));
  readline.createInterface({ input: child.stdout }).on("line", (line) => {
    const message = parseJson(line);
    if (!message) return;
    if (message.method && message.id !== undefined) {
      const params = message.params ?? {};
      const command = String(params.command ?? "");
      const accept = approve && message.method === "item/commandExecution/requestApproval" && command.includes(stepScript);
      const decision = accept ? "accept" : "decline";
      const steps = command.includes(outside) ? command.slice(command.indexOf(outside) + outside.length).replace(/^['"\\]+/, "").replace(/['"\\]+$/, "").trim() : null;
      approvals.push(trace("approval", { scenario: name, method: message.method, thread: params.threadId ?? null, steps,
        command: clean(command).slice(-200), reason: params.reason ?? null, decision }));
      child.stdin.write(JSON.stringify({ id: message.id, result: { decision } }) + "\n");
    } else if (message.method) {
      notifications.push(message);
      if (/^(turn|thread)\//.test(message.method)) trace("rpc.event", { scenario: name, method: message.method, thread: message.params?.threadId ?? message.params?.thread?.id ?? null,
        turn: message.params?.turn?.id ?? null, status: message.params?.turn?.status ?? message.params?.status ?? null });
    } else if (pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
  });
  const call = async (method, params) => {
    const id = ++next;
    const response = new Promise((resolve) => pending.set(id, resolve));
    child.stdin.write(JSON.stringify({ id, method, params }) + "\n");
    const result = await Promise.race([response, delay(30000).then(() => ({ error: { message: `${method} timed out` } }))]);
    trace("rpc.result", { scenario: name, method, error: result.error ?? null, thread: result.result?.thread?.id ?? null, turn: result.result?.turn?.id ?? null });
    assert(!result.error, `${method}: ${JSON.stringify(result.error)}`);
    return result.result;
  };
  await call("initialize", { clientInfo: { name: "fixture-684", version: "0" }, capabilities: { experimentalApi: true } });
  child.stdin.write(JSON.stringify({ method: "initialized" }) + "\n");
  return { child, call, notifications, approvals };
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
const compactProfile = (profile) => profile && { type: profile.type, network: profile.network ?? null,
  entries: (profile.file_system?.entries ?? []).map((entry) => [entry.path?.path ?? entry.path?.value?.kind ?? entry.path?.type ?? null, entry.access]) };
const rollouts = () => rolloutFiles(path.join(env.CODEX_HOME, "sessions")).map((file) => {
  const lines = readFileSync(file, "utf8").trim().split("\n").map(parseJson).filter(Boolean);
  const meta = lines.find((line) => line.type === "session_meta")?.payload ?? {};
  return { id: meta.id ?? null, cwd: meta.cwd ?? null, source: meta.source ?? null,
    turns: lines.filter((line) => line.type === "turn_context").map((line) => ({ cwd: line.payload?.cwd ?? null,
      approval_policy: line.payload?.approval_policy ?? null, sandbox_policy: line.payload?.sandbox_policy ?? null,
      permissions: compactProfile(line.payload?.permission_profile) })) };
});

// The remote's state for one branch, read outside every sandbox.
const remoteState = (branch) => ({
  head: run("git", ["-C", bare, "rev-parse", "--verify", "--quiet", `refs/heads/${branch}`]).stdout.trim() || null,
  receives: readJsonLines(receiveLog).filter((entry) => entry.ref === `refs/heads/${branch}`),
});
const sshdLog = () => {
  const text = existsSync(path.join(server, "sshd.log")) ? readFileSync(path.join(server, "sshd.log"), "utf8") : "";
  return { accepted: (text.match(/Accepted publickey/g) ?? []).length, failed: (text.match(/Failed publickey|Connection closed by authenticating/g) ?? []).length };
};

const scripts = ["ancestry.mjs", "prepush.mjs", "run.mjs", "step.mjs", "verify.mjs"];
const sourceDigests = () => Object.fromEntries(scripts.map((file) => [file, sha(readFileSync(path.join(here, file)))]));
try {
  const headRevision = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", path.relative(checkout, here)], { encoding: "utf8" }).trim() !== "";
  const tool = (command, args) => { const ran = run(command, args); return `${ran.stdout ?? ""}${ran.stderr ?? ""}`.trim().split("\n")[0]; };
  trace("environment", { version, expectedVersion, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    git: tool("git", ["--version"]), ssh: tool("ssh", ["-V"]), gh: tool("gh", ["--version"]), bwrap: tool("bwrap", ["--version"]),
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), binarySHA256: sha(readFileSync(binary)),
    checkout: { head: headRevision, experimentDirty: dirty }, sourceSHA256: sourceDigests(),
    config: readFileSync(configPath, "utf8"), updater: JSON.parse(readFileSync(daemonSettingsPath, "utf8")),
    hostEnvironmentNames: Object.keys(env).sort(), runnerParent: process.ppid, ancestry: runnerAncestry.map((entry) => ({ pid: entry.pid, comm: entry.comm, harness: isHarness(entry) })),
    sharedDaemonDirBefore: sharedBefore.length, ports: { ssh: sshPort, https: httpsPort } });

  // The host's own view, outside every sandbox: the fragment's ownership, and
  // each transport's control, which shows the fixture's servers work.
  scenario = "host";
  const lstatOf = (file) => { const link = lstatSync(file); const target = statSync(file);
    return { symlink: link.isSymbolicLink(), target: link.isSymbolicLink() ? readlinkSync(file) : null, uid: target.uid, gid: target.gid, mode: (target.mode & 0o7777).toString(8) }; };
  const fragmentFiles = readdirSync("/etc/ssh/ssh_config.d").sort();
  const includes = readFileSync("/etc/ssh/ssh_config", "utf8").split("\n").filter((line) => /^\s*Include\s/i.test(line)).map((line) => line.trim());
  const hostSsh = run("ssh", ["-F", "/etc/ssh/ssh_config", "-G", "fixture-forge"]);
  // The control commands run asynchronously: this process serves HTTPS.
  const control = (name, extra) => new Promise((resolve) => {
    const child = spawn("git", ["-C", main, "ls-remote", "origin"], { env: { ...env, ...extra }, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = ""; let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("exit", (status) => resolve({ name, status, refs: stdout.trim().split("\n").filter(Boolean).length,
      lines: clean(stderr).split("\n").filter((line) => /fatal|error|denied|Bad owner/.test(line)).slice(0, 4) }));
  });
  trace("host", { systemConfig: lstatOf("/etc/ssh/ssh_config"), includes, fragments: fragmentFiles.map((name) => ({ name, ...lstatOf(path.join("/etc/ssh/ssh_config.d", name)) })),
    sshThroughSystem: { status: hostSsh.status, lines: clean(hostSsh.stderr).split("\n").filter(Boolean).slice(0, 4) },
    controls: [await control("baseline", remedies.baseline), await control("ssh-config", remedies["ssh-config"]), await control("https", remedies.https)],
    agentKeys: run("ssh-add", ["-l"], { env: { ...env, SSH_AUTH_SOCK: agentSocket } }).stdout.trim().split("\n").filter(Boolean).length });

  for (const name of scenarioNames) {
    scenario = name;
    trace("scenario", { name });
    const approvalPolicy = name === "escalated-approved" ? "on-request" : "never";
    const remedy = name.startsWith("escalated") ? remedies.baseline : remedies[name];
    const overrides = ['sandbox_mode="workspace-write"', `sandbox_workspace_write.writable_roots=${JSON.stringify([worktreeRoot, gitDir])}`,
      "sandbox_workspace_write.network_access=true", `approval_policy="${approvalPolicy}"`, 'approvals_reviewer="user"',
      ...Object.entries(remedy).map(([key, value]) => `shell_environment_policy.set.${key}=${JSON.stringify(value)}`)];
    trace("scenario.launch", { name, approvalPolicy, overrides: overrides.map((override) => override.replace(/=.*$/s, "")), remedyNames: Object.keys(remedy) });
    const urlBefore = remoteUrlDigest();
    const sshdBefore = sshdLog();
    const sshSessionsBefore = readJsonLines(sshSessionLog).length;
    const app = await appServer(name, overrides, name === "escalated-approved");
    const started = await app.call("thread/start", { cwd: main, model: "fixture-v2" });
    const lead = `lead-${name}`;
    const worker = `worker-${name}`;
    const turn = await app.call("turn/start", { threadId: started.thread.id, input: [{ type: "text", text: `SPIKE:${lead}` }] });
    let completed = true;
    try {
      await waitFor(() => done.has(worker) && done.has(lead), `${name}: worker and lead hand back`, 240000);
      await waitFor(() => app.notifications.some((entry) => entry.method === "turn/completed" && entry.params?.turn?.id === turn.turn.id), `${name}: lead turn completes`, 30000);
    } catch (error) { completed = false; trace("scenario.timeout", { name, error: String(error.message) }); }
    app.child.stdin.end();
    app.child.kill("SIGTERM");
    await Promise.race([once(app.child, "exit"), delay(5000)]);
    trace("scenario.outcome", { name, completed, approvalPolicy, lead: started.thread.id,
      remoteUrlUnchanged: remoteUrlDigest() === urlBefore, remoteUrlDigest: urlBefore,
      remote: remoteState(name), sshSessions: readJsonLines(sshSessionLog).slice(sshSessionsBefore).map((entry) => entry.verb),
      sshd: { before: sshdBefore, after: sshdLog() },
      approvals: app.approvals.map((entry) => ({ method: entry.method, decision: entry.decision, steps: entry.steps })),
      workerOutputs: modelRequests.filter((record) => record.label === worker && record.lastOutput).map((record) => record.lastOutput) });
  }

  trace("rollouts", { threads: rollouts() });
  trace("outside", { entries: readdirSync(outside).sort() });
  trace("remote.refs", { refs: run("git", ["-C", bare, "for-each-ref", "--format=%(refname) %(objectname)"]).stdout.trim().split("\n") });
  const finalSources = sourceDigests();
  assert.deepEqual(finalSources, records[0].sourceSHA256, "fixture sources stayed fixed during measurement");
  trace("completed", { scenarios: scenarioNames });
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: String(error?.stack ?? error) });
  process.exitCode = 1;
} finally {
  await delay(500);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  for (const child of children) { try { child.kill("SIGTERM"); } catch {} }
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length });
  model.closeAllConnections(); model.close();
  httpsServer.closeAllConnections(); httpsServer.close();
  // The trace must never carry the fixture token, whatever `clean` missed.
  const leaked = readFileSync(tracePath, "utf8").includes(token);
  appendFileSync(tracePath, JSON.stringify({ kind: "artifact", tokenAbsent: !leaked, receipt: records.length + 1, receiptTime: Date.now() }) + "\n");
  console.log(`Metadata trace: ${tracePath}`);
  if (leaked) { console.error("The fixture token reached the trace"); process.exitCode = 1; }
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
