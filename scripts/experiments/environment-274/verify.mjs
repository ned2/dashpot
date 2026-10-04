// Independent verifier for the #274 environment trace. Checks every finding
// the spike reports against the recorded probes, clients, Host Processes and
// sessions, without importing the runner.
//
//   node verify.mjs <trace.jsonl>
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const [tracePath] = process.argv.slice(2);
assert(tracePath, "Pass the trace.jsonl path");
const text = readFileSync(tracePath, "utf8");
const records = text.trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const findings = [];
const finding = (line) => findings.push(line);

// The trace names the runner's exact sources and the pinned releases.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.versions.codex, "codex-cli 0.160.0");
assert.equal(environment.versions.opencode, "opencode v2.0.22");
assert.match(environment.codexSHA256, /^[0-9a-f]{64}$/);
assert.match(environment.opencodeSHA256, /^[0-9a-f]{64}$/);
const scripts = ["ancestry.mjs", "command.mjs", "run.mjs"];
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), scripts);
for (const file of scripts) {
  const digest = createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex");
  assert.equal(digest, environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
}
assert.deepEqual(of("scenario").map((record) => record.name), ["shell", "codex", "opencode"]);
assert(!of("runner.error").length, "the runner completed");
// Metadata only: every fixture path is a placeholder, and the markers are
// the synthetic values the run set.
assert(!/"\/(tmp|home)\//.test(text) && !/[ =:]\/(tmp|home)\//.test(text), "no absolute fixture or home path in the trace");
const shared = one("shared-daemon-dir");
assert.deepEqual(shared.removed, [], "nothing was removed from the shared daemon directory");
assert(shared.added.length === 1 && shared.added[0].endsWith(".lock"), "the run added one lock file to the shared daemon directory");
const { main, trees } = environment;

const probe = (label) => one("probe", (record) => record.label === label);
const marker = (label) => probe(label).env.DASHPOT_274_MARKER;
const client = (name) => one("client", (record) => record.name === name).process;
// A synthetic token-named variable is treated exactly like the plain marker,
// so no harness filtered a variable by its name.
for (const record of of("probe")) assert.equal(record.env.DASHPOT_274_TOKEN, record.env.DASHPOT_274_MARKER, `${record.label}: the token-named marker matches`);
for (const record of [...of("client").map((entry) => entry.process), ...of("codex.daemons").flatMap((entry) => entry.daemons), ...of("opencode.service").map((entry) => entry.process).filter(Boolean)]) {
  assert.equal(record.markers.DASHPOT_274_TOKEN, record.markers.DASHPOT_274_MARKER, `${record.pid}: the token-named marker matches`);
}
const expect = (label, value, cwd) => {
  assert.equal(marker(label), value, `${label}: marker ${value}`);
  if (cwd) assert.equal(probe(label).cwd, cwd, `${label}: runs in ${cwd}`);
};

// Part 1. The shell and direnv.
const loaded = "checkout-envrc";
expect("shell-exec-main", loaded, main);
expect("shell-exec-worktree", null, trees.a);
finding("direnv exec in a linked Worktree does not load the main checkout's .envrc; in the main checkout it does");
expect("shell-main-into-worktree-hook", null, trees.a);
expect("shell-main-into-worktree-nohook", loaded, trees.a);
finding("an interactive shell with direnv's hook, started with the main checkout's environment in a linked Worktree, unloads it at its first prompt; without the hook it keeps it");
expect("shell-cd-at-main", loaded, main);
expect("shell-cd-same-line", loaded, trees.a);
expect("shell-cd-next-prompt", null, trees.a);
assert(probe("shell-cd-at-main").pid !== probe("shell-cd-next-prompt").pid);
finding("a hooked shell that cds from the main checkout keeps the environment for the rest of that command line and loses it at the next prompt");
expect("shell-worktree-hook", null, trees.a);
const pool = one("pool-envrc");
assert.equal(pool.path, `${environment.pool}/.envrc`);
assert.equal(pool.content, `source_env ${main}/.envrc\n`);
const poolExec = one("direnv.exec", (record) => record.label === "shell-pool-exec-worktree");
assert(poolExec.stderr.indexOf(`loading ${environment.pool}/.envrc`) >= 0 && poolExec.stderr.indexOf(`loading ${main}/.envrc`) > poolExec.stderr.indexOf(`loading ${environment.pool}/.envrc`), "the pool .envrc loads the main checkout's through source_env");
for (const label of ["shell-pool-exec-worktree", "shell-pool-worktree-hook", "shell-pool-wrapper-hook"]) {
  expect(label, loaded, trees.a);
  assert.equal(probe(label).env.DIRENV_DIR, `-${environment.pool}`, `${label}: direnv names the Worktree Root's .envrc`);
}
finding("with a Worktree Root .envrc that source_env's the main checkout's, direnv exec, a hooked shell and a direnv-exec wrapper in a linked Worktree all load it");
assert(pool.receipt < one("scenario", (record) => record.name === "codex").receipt, "the pool .envrc exists for both harness parts");

// Part 2. Codex: the tool's environment is its Host Process's.
const daemonsAt = (label) => one("codex.daemons", (record) => record.label === label).daemons;
const daemonAt = (label) => {
  const found = daemonsAt(label);
  assert.equal(found.length, 1, `${label}: one managed daemon`);
  assert.match(found[0].cmdline, /app-server .*--managed-daemon/);
  // The daemon runs Codex's own copy of the release, byte for byte the
  // pinned binary.
  assert.equal(found[0].exeSHA256, environment.codexSHA256, `${label}: the daemon runs the pinned release`);
  return found[0];
};
const hostedBy = (label, host) => assert(probe(label).ancestry.some((entry) => entry.pid === host.pid), `${label}: the tool is a descendant of ${host.pid}`);
const codexLabels = of("probe").map((record) => record.label).filter((label) => label.startsWith("codex-"));
assert.deepEqual(codexLabels, ["codex-standalone", "codex-first", "codex-later-direnv", "codex-later-set", "codex-resume", "codex-autostart-direnv", "codex-inherited", "codex-resume-inherited", "codex-after-daemon-start", "codex-standalone-resume"]);
for (const label of codexLabels) {
  const daemons = daemonsAt(label);
  const host = daemons.length ? daemons[0] : client(label);
  hostedBy(label, host);
  assert.equal(marker(label), host.markers.DASHPOT_274_MARKER, `${label}: the tool has its Host Process's markers`);
}
// Standalone: no daemon, the client's own environment.
assert.deepEqual(daemonsAt("codex-standalone"), []);
expect("codex-standalone", "codex-standalone-client", trees.a);
// An autostarted daemon is the starting terminal's child and keeps its
// environment; a later client's never reaches the tool.
const first = daemonAt("codex-first");
assert.equal(first.ppid, client("codex-first").pid, "the first terminal autostarts the daemon as its child");
expect("codex-first", null, main);
for (const [label, clientMarker, cwd] of [["codex-later-direnv", loaded, trees.b], ["codex-later-set", "codex-later-client", trees.c], ["codex-resume", loaded, trees.d]]) {
  assert.equal(daemonAt(label).pid, first.pid, `${label}: the same daemon`);
  assert.equal(client(label).markers.DASHPOT_274_MARKER, clientMarker, `${label}: the client has ${clientMarker}`);
  expect(label, null, cwd);
}
assert.equal(probe("codex-resume").env.CODEX_THREAD_ID, probe("codex-first").env.CODEX_THREAD_ID, "codex resume -C continues the first thread");
finding("Codex 0.160.0: a daemon autostarted by a terminal without the markers never gives them to a tool, whether a later client has them from direnv, from its own environment, or resumes with -C into a linked Worktree");
const direnvDaemon = daemonAt("codex-autostart-direnv");
assert.equal(direnvDaemon.ppid, client("codex-autostart-direnv").pid);
assert.equal(direnvDaemon.markers.DASHPOT_274_MARKER, loaded);
expect("codex-autostart-direnv", loaded, trees.e);
for (const [label, cwd] of [["codex-inherited", main], ["codex-resume-inherited", trees.f]]) {
  assert.equal(daemonAt(label).pid, direnvDaemon.pid, `${label}: the same daemon`);
  assert.equal(client(label).markers.DASHPOT_274_MARKER, null, `${label}: the client has no markers`);
  expect(label, loaded, cwd);
}
assert.equal(probe("codex-resume-inherited").env.CODEX_THREAD_ID, probe("codex-first").env.CODEX_THREAD_ID);
finding("Codex 0.160.0: a daemon autostarted by a terminal launched through direnv gives that environment to every later client's tools, a resumed thread's included");
const explicit = daemonAt("codex-after-daemon-start");
assert.equal(explicit.markers.DASHPOT_274_MARKER, "codex-daemon-start");
assert.equal(client("codex-after-daemon-start").markers.DASHPOT_274_MARKER, null);
expect("codex-after-daemon-start", "codex-daemon-start", trees.g);
finding("Codex 0.160.0: `codex app-server daemon start` gives its own environment to later clients' tools");
assert.deepEqual(daemonsAt("codex-standalone-resume"), []);
expect("codex-standalone-resume", "codex-standalone-resume-client", trees.h);
assert.equal(probe("codex-standalone-resume").env.CODEX_THREAD_ID, probe("codex-first").env.CODEX_THREAD_ID);
finding("Codex 0.160.0: a standalone client (--disable daemon_auto_start), fresh or resumed with -C, gives its tools its own environment");

// Part 3. OpenCode.
const service = (label) => one("opencode.service", (record) => record.label === label);
const sessionOf = (label) => probe(label).env.OPENCODE_SESSION_ID;
assert.equal(service("opencode-standalone").registered, false);
expect("opencode-standalone", "opencode-standalone-client", trees.a);
// The standalone client's private server is its child.
hostedBy("opencode-standalone", client("opencode-standalone"));
finding("OpenCode 2.0.22: a --standalone client gives its tools its own environment");
const firstService = service("opencode-first").process;
assert.equal(firstService.ppid, client("opencode-first").pid, "the first TUI starts the shared service as its child");
assert.equal(firstService.markers.DASHPOT_274_MARKER, null);
expect("opencode-first", null, main);
const firstSession = sessionOf("opencode-first");
// A client of the shared service gives the session its own environment,
// whatever the service started with.
for (const [label, cwd] of [["opencode-later-direnv", trees.b], ["opencode-later-tui", trees.c], ["opencode-continue", main], ["opencode-move", trees.e]]) {
  const host = service(label).process;
  assert.equal(host.pid, firstService.pid, `${label}: the same service`);
  assert.equal(host.markers.DASHPOT_274_MARKER, null, `${label}: the service has no markers`);
  hostedBy(label, host);
  assert.equal(client(label).markers.DASHPOT_274_MARKER, loaded, `${label}: the client was launched through direnv`);
  expect(label, loaded, cwd);
}
assert.equal(sessionOf("opencode-continue"), firstSession);
assert.equal(sessionOf("opencode-move"), firstSession);
assert.equal(one("opencode.session", (record) => record.label === "opencode-continue").location, main, "--session from a linked Worktree does not move the session");
assert.equal(one("opencode.session", (record) => record.label === "opencode-move").location, trees.e, "session_move moves it");
finding("OpenCode 2.0.22: a CLI client of the shared service (`opencode run`, the TUI, `run --session`, a session_move) gives the session's tools the client's environment, not the service's");
// A prompt through the API, which sends no environment, keeps the
// variables the session's last client sent.
const apiPrompt = one("opencode.api.prompt", (record) => record.label === "opencode-api-prompt");
assert.equal(apiPrompt.sessionID, sessionOf("opencode-later-direnv"));
assert.equal(sessionOf("opencode-api-prompt"), apiPrompt.sessionID);
assert.equal(service("opencode-api-prompt").process.markers.DASHPOT_274_MARKER, null);
hostedBy("opencode-api-prompt", service("opencode-api-prompt").process);
expect("opencode-api-prompt", loaded, trees.b);
finding("OpenCode 2.0.22: a later prompt through the HTTP API runs with the variables a client gave the session");
const direnvService = service("opencode-service-direnv").process;
assert.equal(direnvService.ppid, client("opencode-service-direnv").pid);
assert.equal(direnvService.markers.DASHPOT_274_MARKER, loaded);
expect("opencode-service-direnv", loaded, trees.f);
for (const [label, cwd] of [["opencode-inherited", main], ["opencode-moved-inherited", trees.e]]) {
  assert.equal(service(label).process.pid, direnvService.pid);
  assert.equal(client(label).markers.DASHPOT_274_MARKER, null);
  hostedBy(label, direnvService);
  expect(label, null, cwd);
}
assert.equal(sessionOf("opencode-moved-inherited"), firstSession);
finding("OpenCode 2.0.22: a client without the markers removes them from its session's tools even when the service has them");
const apiSession = one("opencode.api.session", (record) => record.label === "opencode-api-session");
assert.equal(apiSession.directory, trees.h);
assert.equal(sessionOf("opencode-api-session"), apiSession.sessionID);
assert.equal(service("opencode-api-session").process.pid, direnvService.pid);
hostedBy("opencode-api-session", direnvService);
expect("opencode-api-session", loaded, trees.h);
finding("OpenCode 2.0.22: a session created and prompted only through the HTTP API runs in the service's own environment");
const explicitService = service("opencode-service-started").process;
assert.equal(explicitService.markers.DASHPOT_274_MARKER, "opencode-service-start");
assert.equal(client("opencode-after-service-start").markers.DASHPOT_274_MARKER, null);
expect("opencode-after-service-start", null, trees.g);
const restarted = one("opencode.api.prompt", (record) => record.label === "opencode-api-after-restart");
assert.equal(restarted.sessionID, sessionOf("opencode-later-direnv"));
assert.equal(service("opencode-api-after-restart").process.pid, explicitService.pid);
hostedBy("opencode-api-after-restart", explicitService);
expect("opencode-api-after-restart", "opencode-service-start", trees.b);
finding("OpenCode 2.0.22: a session's variables do not outlive the service; after a restart an API prompt runs in the new service's environment");

// The Worktree Root .envrc existed for both harness parts, yet no agent's
// command in a linked Worktree loaded it itself: every one that ran without
// the markers there has no DIRENV_DIR either, in both harnesses.
const harnessProbes = of("probe").filter((record) => /^(codex|opencode)-/.test(record.label));
const unloaded = harnessProbes.filter((record) => record.cwd.startsWith(`${environment.pool}/`) && record.env.DASHPOT_274_MARKER === null);
for (const record of unloaded) assert.equal(record.env.DIRENV_DIR, null, `${record.label}: did not load the Worktree Root .envrc`);
assert(unloaded.some((record) => record.label.startsWith("codex-")) && unloaded.some((record) => record.label.startsWith("opencode-")), "both harnesses ran a command without the markers in a linked Worktree");
finding(`no agent's command loaded the Worktree Root .envrc itself: ${unloaded.length} commands in linked Worktrees ran without it`);

for (const line of findings) console.log(`ok - ${line}`);
console.log(`${findings.length} findings verified against ${records.length} records`);
