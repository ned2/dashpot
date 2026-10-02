// Independent verifier for the Issue #393 OpenCode v2 spike trace: checks
// each claim docs/spikes/opencode-v2-spike.md makes about the shared service,
// plugin instances and their events, shell identity, sub-agents, moves,
// generation churn, --standalone, install layouts and idle eviction against
// the recorded plugin, server, shell, process and model records.
//
// Usage: node verify.mjs <trace.jsonl> [<idle trace.jsonl>]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const [tracePath, idlePath] = process.argv.slice(2);
assert(tracePath, "Pass the spike trace, and optionally the idle-eviction trace");
// The trace under check; the helpers below read whichever is loaded.
let records;
let setups;
const load = (file) => {
  records = readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line));
  setups = kind("plugin.setup");
};
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };
const main = "$ROOT/repository";
const treeA = "$ROOT/repository.worktrees/a";
const treeB = "$ROOT/repository.worktrees/b";
const home = "$ROOT/home";
const leaked = "ses_leakedfromanothersession00";

const kind = (name) => records.filter((record) => record.kind === name);
const one = (name, predicate = () => true) => {
  const found = records.find((record) => record.kind === name && predicate(record));
  assert(found, `no ${name} record`);
  return found;
};
const labelled = (name, label) => one(name, (record) => record.label === label);
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const ended = (label) => kind("command").some((record) => record.label === label && record.phase === "end");
const sessionOf = (title) => one("session", (record) => record.title === title).sessionID;
const turn = (label) => one("turn", (record) => record.label === label);
const mark = (label) => labelled("mark", label).receipt;
const spawned = (name) => one("client.spawn", (record) => record.name === name);
const service = (label) => labelled("service", label);
const instance = (id) => setups.find((record) => record.instance === id);
const cleanedUp = (id) => kind("plugin.cleanup").find((record) => record.instance === id);
const located = (id) => instance(id).location.directory;
const events = (type, predicate = () => true) => kind("plugin.event").filter((record) => record.type === type && predicate(record));
const serverEvents = (type, sessionID) => kind("server.event").filter((record) => record.type === type && record.sessionID === sessionID);
const processes = (label) => labelled("processes", label).processes;

// The runner's scripts change only with a new trace, so they must match.
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
const verifyEnvironment = (name, scenarios) => {
  const environment = one("environment");
  for (const file of ["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs", "plugin.mjs"]) {
    assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${name}: ${file} matches the hash the run recorded`);
  }
  check(`${name}: pinned OpenCode releases, every scenario completed, and no fixture process outlived the run`, () => {
    assert.equal(environment.version, "opencode v2.0.22");
    assert.equal(environment.olderVersion, "opencode v2.0.21");
    assert.deepEqual(environment.scenarios, scenarios);
    assert.deepEqual(kind("failure"), []);
    assert.equal(kind("done").length, 1);
    assert.deepEqual(one("cleanup.remaining").pids, []);
  });
  check(`${name}: every session the run created used the local fixture model, never a hosted one`, () => {
    const { sessions } = one("models");
    assert(sessions.length > 0);
    for (const session of sessions) assert.deepEqual([session.model.providerID, session.model.id], ["loop", "fixture"], session.id);
    assert(kind("model.request").length > 0);
  });
  return environment;
};

load(tracePath);
verifyEnvironment("trace", ["shared", "subagents", "moves", "churn", "standalone", "layouts"]);
const shared = service("shared").process;

// The shared service.
check("a TUI spawns the shared service as `serve --service`, a session leader in $HOME, under the TUI", () => {
  const tui = processes("tui-running").find((entry) => entry.cmdline.startsWith("opencode --prompt"));
  assert.equal(shared.ppid, tui.pid);
  assert.deepEqual([shared.pgrp, shared.sid], [shared.pid, shared.pid]);
  assert.equal(shared.cmdline, "$ROOT/home/.opencode/bin/opencode serve --service");
  assert.equal(shared.comm, "opencode");
  assert.equal(shared.cwd, home);
  assert.deepEqual([service("shared").registration.version, service("shared").registration.pid], ["2.0.22", shared.pid]);
});
check("quitting the TUI leaves the service running, reparented, with no plugin cleaned up", () => {
  const after = one("service.after-tui");
  assert.deepEqual([after.alive, after.process.ppid], [true, 1]);
  const quit = labelled("tui.quit", "ctrl-c").receipt;
  assert(!kind("plugin.cleanup").some((record) => record.pid === shared.pid && record.receipt < mark("hot-reload")), `cleanup before ${quit}`);
});
check("inside the plugin, argv names Bun's virtual entry point while execPath and /proc name the real binary", () => {
  const first = instance(setups[0].instance);
  assert.deepEqual(first.argv, ["bun", "/$bunfs/root/opencode", "serve", "--service"]);
  assert.equal(first.execPath, "$ROOT/home/.opencode/bin/opencode");
  assert.equal(first.cwd, home);
});
check("the service loads one plugin instance per location it serves, $HOME included", () => {
  const live = setups.filter((record) => record.pid === shared.pid && record.receipt < mark("hot-reload"));
  assert.deepEqual(live.map((record) => record.location.directory).sort(), [home, main, treeA, treeB].sort());
});
check("every plugin instance receives every location's events from its setup on, not only its own", () => {
  let crossings = 0;
  for (const created of events("session.created")) {
    const at = created.at;
    const receivers = new Set(events("session.created", (record) => record.sessionID === created.sessionID).map((record) => record.instance));
    const live = setups.filter((record) => record.pid === created.pid && record.at < at
      && !(cleanedUp(record.instance) && cleanedUp(record.instance).at <= at));
    for (const record of live) assert(receivers.has(record.instance), `${record.instance} missed ${created.sessionID}`);
    crossings += live.filter((record) => record.location.directory !== created.location).length;
  }
  assert(crossings > 50, `${crossings} cross-location deliveries`);
});
check("session.created, a shell's progress and shell events name a location; execution, deletion and worktree events name none", () => {
  for (const type of ["session.created", "session.tool.progress", "session.shell.started", "shell.created", "shell.exited"]) {
    const found = events(type);
    assert(found.length > 0 && found.every((record) => record.location), type);
  }
  for (const type of ["session.execution.started", "session.execution.succeeded", "session.execution.interrupted", "session.deleted", "worktree.resolved"]) {
    const found = events(type);
    assert(found.length > 0, type);
    assert(found.every((record) => record.location === null), type);
  }
});

// Shell identity.
check("a model-driven shell is the service's child in its own session, naming its own session ID", () => {
  // The run client creates its own session, which the service lists.
  const run = labelled("sessions", "shared").list.find((entry) => entry.title === "R").id;
  for (const [label, id] of [["api-main", sessionOf("A1")], ["api-main-2", sessionOf("A2")], ["api-tree-a", sessionOf("B1")], ["cli-run", run]]) {
    const start = shell(label);
    assert.equal(start.ppid, shared.pid, label);
    assert.deepEqual([start.pgrp, start.sid], [start.pid, start.pid], label);
    assert.deepEqual([start.env.OPENCODE_SESSION_ID, start.env.OPENCODE, start.env.AGENT, start.env.AI_AGENT, start.env.OPENCODE_PID],
      [id, "1", "1", "opencode", null], label);
  }
  assert.equal(shell("api-tree-a").cwd, treeA);
  assert.equal(shell("cli-run").cwd, treeB);
});
check("a leaked OPENCODE_SESSION_ID reaches the service's environment, and a model-driven shell overrides it", () => {
  assert.equal(spawned("tui").leaked, leaked);
  assert.equal(instance(setups[0].instance).serverEnv.OPENCODE_SESSION_ID, leaked);
  assert.equal(labelled("plugin.shell", "tui-1").inherited, leaked);
  assert.notEqual(shell("tui-1").env.OPENCODE_SESSION_ID, leaked);
  assert.match(shell("tui-1").env.OPENCODE_SESSION_ID, /^ses_/);
});
check("a run client's environment replaces the service's base for its shells; API and child sessions get the service's own", () => {
  assert.deepEqual([labelled("plugin.shell", "cli-run").inherited, shell("cli-run").env.SPIKE_CLIENT], [null, "run"]);
  for (const label of ["api-main", "api-tree-a", "child-sync", "child-bg"]) {
    assert.deepEqual([labelled("plugin.shell", label).inherited, shell(label).env.SPIKE_CLIENT], [leaked, "tui"], label);
  }
});
check("a user shell keeps an inherited session ID and lacks the agent markers, but the plugin's shell hook can clear it", () => {
  const user = shell("user-shell").env;
  assert.deepEqual([user.OPENCODE_SESSION_ID, user.OPENCODE, user.AGENT, user.AI_AGENT], [leaked, null, null, null]);
  assert.equal(labelled("plugin.shell", "user-shell").inherited, leaked);
  assert.equal(labelled("plugin.shell", "user-shell-clear").cleared, true);
  assert.equal(shell("user-shell-clear").env.OPENCODE_SESSION_ID, null);
});
check("a terminal opened through the API passes no plugin shell hook and keeps an inherited session ID", () => {
  assert.equal(one("pty").status, 200);
  assert(!kind("plugin.shell").some((record) => record.label === "pty"));
  assert.deepEqual([shell("pty").env.OPENCODE_SESSION_ID, shell("pty").env.SPIKE_PLUGIN_INSTANCE], [leaked, null]);
  assert.equal(shell("pty").ppid, shared.pid);
});
check("a shell runs under the plugin instance of its session's location", () => {
  for (const label of ["api-main", "api-tree-a", "cli-run", "child-bg"]) {
    assert.equal(located(shell(label).env.SPIKE_PLUGIN_INSTANCE), shell(label).cwd, label);
  }
});

// Sub-agents.
const parentP = sessionOf("P");
const parentQ = sessionOf("Q");
const parentR = sessionOf("R2");
const childOf = (label) => shell(label).env.OPENCODE_SESSION_ID;
check("a sub-agent's shell names the child session, whose creation names its parent, as do its model requests", () => {
  for (const [label, parent] of [["child-sync", parentP], ["child-bg", parentQ], ["child-bg-deleted", parentR]]) {
    const child = childOf(label);
    assert.notEqual(child, parent, label);
    assert.equal(events("session.created", (record) => record.sessionID === child)[0].parentID, parent, label);
    const requests = kind("model.request").filter((record) => record.sessionID === child);
    assert(requests.length > 0 && requests.every((record) => record.parentSessionID === parent && record.subagent), label);
  }
  assert(kind("model.request").filter((record) => [parentP, parentQ, parentR].includes(record.sessionID)).every((record) => !record.parentSessionID));
});
check("a background sub-agent ends its parent's turn at once, and its completion starts a new parent execution", () => {
  const settled = one("parent.settled");
  assert.deepEqual([settled.sessionID, settled.childStarted, settled.childEnded], [parentQ, false, false]);
  assert(turn("delegate-bg").ms < 1000);
  assert(turn("delegate-bg").receipt < shell("child-bg").receipt);
  const childEnd = shell("child-bg", "end").receipt;
  const parentRuns = serverEvents("session.execution.started", parentQ);
  assert.equal(parentRuns.length, 2);
  assert(parentRuns[1].receipt > childEnd);
  assert.equal(serverEvents("session.execution.succeeded", parentQ).length, 2);
});
check("deleting a parent interrupts its running background child, kills the child's shell, and deletes both", () => {
  const child = childOf("child-bg-deleted");
  assert.equal(one("delete").sessionID, parentR);
  assert.deepEqual(serverEvents("session.execution.interrupted", child).map((record) => record.reason), ["user"]);
  assert.equal(ended("child-bg-deleted"), false);
  assert.equal(one("after-delete").shellAlive, false);
  assert.equal(serverEvents("session.deleted", child).length, 1);
  assert.equal(serverEvents("session.deleted", parentR).length, 1);
});
check("a deleted parent may then report an execution start with no end, while the active list is empty", () => {
  const deleted = serverEvents("session.deleted", parentR)[0].receipt;
  const late = serverEvents("session.execution.started", parentR).filter((record) => record.receipt > deleted);
  assert.equal(late.length, 1);
  const terminal = kind("server.event").filter((record) => record.sessionID === parentR && record.receipt > late[0].receipt
    && /^session\.execution\.(succeeded|failed|interrupted)$/.test(record.type));
  assert.deepEqual(terminal, []);
  assert.deepEqual(one("after-delete-settled").active, {});
});

// Moves.
const moved = sessionOf("M");
const movedEvents = () => kind("server.event").filter((record) => record.type === "session.moved" && record.sessionID === moved);
check("the model's move tool reaches plugins as opencode_session_move, and later shells run in the new location", () => {
  const hooks = kind("plugin.tool").filter((record) => record.sessionID === moved && record.tool === "opencode_session_move");
  assert.deepEqual(hooks.map((record) => record.hook), ["execute.before", "execute.after"]);
  assert.equal(labelled("session.info", "after-move-tool").info.location.directory, treeA);
  assert.equal(shell("after-tool-move").cwd, treeA);
  assert.equal(located(shell("after-tool-move").env.SPIKE_PLUGIN_INSTANCE), treeA);
});
check("session.moved is delivered in the old location and carries the new one", () => {
  assert.deepEqual(movedEvents().map((record) => [record.location, record.moved.location.directory]),
    [[main, treeA], [treeA, treeB], [treeB, main]]);
});
check("moving an idle session through the API is itself an execution", () => {
  const sequence = kind("server.event").filter((record) => record.sessionID === moved && /^session\.(moved|execution\.)/.test(record.type));
  const at = sequence.indexOf(movedEvents()[1]);
  assert.deepEqual(sequence.slice(at - 1, at + 2).map((record) => record.type),
    ["session.execution.started", "session.moved", "session.execution.succeeded"]);
  assert(sequence[at - 1].receipt > turn("after-tool-move").receipt);
  assert.equal(shell("after-api-move").cwd, treeB);
});
check("a move during a running shell waits for the step boundary, and the shell finishes in the old location", () => {
  const request = one("move", (record) => record.during === "move-hold");
  assert(request.receipt < shell("move-hold", "end").receipt);
  assert.equal(shell("move-hold", "end").cwd, treeB);
  assert(movedEvents()[2].receipt > shell("move-hold", "end").receipt);
  assert.equal(labelled("session.info", "after-busy-move").info.location.directory, main);
});

// Generations.
const between = (records, from, to) => records.filter((record) => record.receipt > from && record.receipt < to);
check("editing the plugin file cleans up every instance and sets each location up again", () => {
  const from = mark("hot-reload");
  const to = turn("after-hot-reload").receipt;
  const cleaned = between(kind("plugin.cleanup"), from, to).map((record) => located(record.instance)).sort();
  const fresh = between(setups, from, to).map((record) => record.location.directory).sort();
  assert.deepEqual(cleaned, [home, main, treeA, treeB].sort());
  assert.deepEqual(fresh, cleaned);
});
check("`opencode reload` shuts every location down and sets each up again", () => {
  assert.deepEqual([one("reload").status, one("reload").stdout], [0, "Configuration reloaded\n"]);
  const from = mark("cli-reload");
  const to = turn("after-cli-reload").receipt;
  assert.deepEqual(new Set(between(events("location.shutdown"), from, to).map((record) => record.location)), new Set([home, main, treeA, treeB]));
  assert.equal(between(kind("plugin.cleanup"), from, to).length, 4);
  assert.equal(between(setups, from, to).length, 4);
});
check("evicting an idle location cleans its instance up and sets a new one up", () => {
  const from = mark("evict-idle");
  const to = turn("after-evict").receipt;
  assert.deepEqual(between(kind("plugin.cleanup"), from, to).map((record) => located(record.instance)), [treeA]);
  assert.deepEqual(between(setups, from, to).map((record) => record.location.directory), [treeA]);
});
check("evicting a busy location shuts it down at once; its instance is never cleaned up and still hears events after a successor is set up", () => {
  const from = mark("evict-busy");
  const old = shell("evict-hold").env.SPIKE_PLUGIN_INSTANCE;
  const request = one("evict", (record) => record.during === "evict-hold");
  assert(request.receipt < shell("evict-hold", "end").receipt);
  assert(events("location.shutdown", (record) => record.instance === old && record.location === treeA
    && record.receipt > request.receipt && record.receipt < shell("evict-hold", "end").receipt).length === 1);
  // The successor is set up when the session next needs the location, after the shell.
  const successor = between(setups, from, turn("evict-hold").receipt);
  assert.deepEqual(successor.map((record) => record.location.directory), [treeA]);
  assert(successor[0].receipt > shell("evict-hold", "end").receipt);
  assert.equal(shell("after-busy-evict").env.SPIKE_PLUGIN_INSTANCE, successor[0].instance);
  assert.equal(cleanedUp(old), undefined);
  const heard = kind("plugin.event").filter((record) => record.instance === old && record.receipt > successor[0].receipt);
  for (const type of ["session.created", "session.deleted", "location.shutdown"]) assert(heard.some((record) => record.type === type), type);
});
check("`opencode session delete` goes through the service: no plugin loads in the CLI, and the deletion is published", () => {
  const client = spawned("cli-delete");
  assert.equal(one("client.exit", (record) => record.name === "cli-delete").code, 0);
  const deleted = sessionOf("E");
  assert.equal(serverEvents("session.deleted", deleted).length, 1);
  assert(!setups.some((record) => record.pid === client.pid || record.ppid === client.pid));
  assert.deepEqual(labelled("session.info", "after-cli-delete").info, { missing: 404 });
});
check("`opencode service stop` cleans every instance up and removes the registration", () => {
  for (const stopped of kind("service.stopped").filter((record) => record.how === "cli")) {
    assert.equal(stopped.registration, "removed", stopped.label);
    const pid = stopped.pid;
    const leftover = setups.filter((record) => record.pid === pid && !cleanedUp(record.instance));
    assert.deepEqual(leftover.map((record) => record.instance), [], stopped.label);
  }
});
check("a killed service runs no cleanup and leaves its registration, which `service start` replaces", () => {
  const killed = labelled("service.stopped", "service-kill");
  assert.equal(killed.registration, "kept");
  const orphans = setups.filter((record) => record.pid === killed.pid);
  assert(orphans.length > 0 && orphans.every((record) => !cleanedUp(record.instance)));
  assert.equal(kind("service.start").every((record) => record.status === 0), true);
  assert.notEqual(service("after-kill").registration.pid, killed.pid);
  assert.equal(turn("after-kill").sessionID, turn("before-kill").sessionID);
});

// Version mismatch.
check("an older run client reuses a newer service", () => {
  const after = one("service.after-older-run");
  assert.deepEqual([after.registered, after.version], [after.before, "2.0.22"]);
  assert.equal(instance(shell("older-run").env.SPIKE_PLUGIN_INSTANCE).app.version, "2.0.22");
});
check("an older TUI replaces a newer service, interrupting its running shell, and resumes the session", () => {
  const older = service("older");
  assert.equal(older.registration.version, "2.0.21");
  const after = one("after-older-tui");
  assert.deepEqual([after.holdEnded, after.holdShellAlive, after.oldServiceAlive], [false, false, false]);
  const held = shell("mismatch-hold").env.OPENCODE_SESSION_ID;
  assert(events("session.execution.interrupted", (record) => record.sessionID === held).every((record) => record.reason === "shutdown"));
  assert(events("session.execution.interrupted", (record) => record.sessionID === held).length > 0);
  assert(setups.some((record) => record.pid === older.registration.pid && record.app.version === "2.0.21"));
  assert.equal(serverEvents("session.execution.succeeded", held).some((record) => record.receipt > older.receipt), true);
  assert.equal(shell("on-older-service").env.OPENCODE_SESSION_ID, held);
  assert.equal(shell("on-older-service").ppid, older.registration.pid);
});
check("a newer TUI replaces the older service in turn", () => {
  assert.equal(service("newer").registration.version, "2.0.22");
  assert(kind("plugin.cleanup").some((record) => record.pid === service("older").registration.pid));
});

// --standalone.
check("--standalone runs a private `serve --stdio` under the client, whose plugin is cleaned up when the client exits", () => {
  for (const [client, label] of [["standalone-run", "standalone-hold"], ["standalone-tui", "standalone-tui"]]) {
    const start = shell(label);
    const server = start.ancestry[0];
    assert.equal(server.cmdline, "$ROOT/home/.opencode/bin/opencode serve --stdio --port 0", label);
    assert.notEqual(server.pid, service("after-kill").registration.pid);
    const plugin = instance(start.env.SPIKE_PLUGIN_INSTANCE);
    assert.equal(plugin.pid, server.pid);
    assert.deepEqual(plugin.argv, ["bun", "/$bunfs/root/opencode", "serve", "--stdio", "--port", "0"]);
    assert(cleanedUp(plugin.instance), label);
    assert(cleanedUp(plugin.instance).receipt < one("client.exit", (record) => record.name === client).receipt + 5, label);
    const clientPid = spawned(client).terminal ? start.ancestry[1].pid : spawned(client).pid;
    assert.equal(server.ppid, clientPid, label);
  }
});
check("a standalone server shares the session store with the shared service", () => {
  const ids = labelled("sessions", "standalone").list.map((entry) => entry.id);
  assert(ids.includes(shell("standalone-hold").env.OPENCODE_SESSION_ID));
  assert(ids.includes(shell("standalone-tui").env.OPENCODE_SESSION_ID));
});

// Install layouts.
check("an npm install's service runs as opencode.exe, whichever command name launched it", () => {
  for (const label of ["npm-opencode", "npm-opencode2"]) {
    // Sampled while the client still ran, so the service is still its child.
    const server = processes(label).find((entry) => entry.pid === service(label).registration.pid);
    assert.equal(server.comm, "opencode.exe", label);
    assert.equal(server.exe, "$ROOT/npm/lib/node_modules/@opencode/cli/bin/opencode.exe", label);
    const client = processes(label).find((entry) => entry.pid === server.ppid);
    assert.equal(client.comm, label === "npm-opencode" ? "opencode" : "opencode2");
    assert.equal(instance(shell(`${label}-hold`).env.SPIKE_PLUGIN_INSTANCE).execPath, server.exe);
  }
});
check("the curl install's opencode2 shim execs opencode, so client and service are both named opencode", () => {
  const server = processes("curl-opencode2").find((entry) => entry.pid === service("curl-opencode2").registration.pid);
  assert.equal(server.comm, "opencode");
  assert.equal(spawned("curl-opencode2").executable, "opencode2");
  assert.equal(processes("curl-opencode2").find((entry) => entry.pid === server.ppid).comm, "opencode");
});

// Idle eviction: three sessions in three locations past the hour.
if (idlePath) {
  load(idlePath);
  const environment = verifyEnvironment("idle", ["idle"]);
  const minutes = (ms) => ms / 60000;
  const quiet = sessionOf("Quiet");
  const busy = sessionOf("Busy");
  const chatty = sessionOf("Chatty");
  const instanceAt = (directory) => setups.filter((record) => record.location.directory === directory);
  check("idle: the run waited past the hour with a silent and a printing shell running", () => {
    assert(environment.idleMinutes >= 62, `${environment.idleMinutes} minutes`);
    assert(minutes(one("idle.done").ms) >= environment.idleMinutes);
    assert.equal(shell("idle-hold").cwd, treeB);
    assert.equal(shell("idle-chatty").cwd, main);
  });
  check("idle: a location whose sessions are quiet is evicted about an hour after its last session event, its instance cleaned up", () => {
    const [first] = instanceAt(treeA);
    const cleanup = cleanedUp(first.instance);
    assert(cleanup, "the quiet location's instance was never cleaned up");
    const after = minutes(cleanup.at - turn("idle-quiet").receiptTime);
    assert(after >= 60 && after < 62.5, `${after} minutes`);
    assert(events("location.shutdown", (record) => record.location === treeA).length > 0);
  });
  // Each long shell's session, its location, and the minute its shell started.
  for (const [what, session, label, directory] of [["with no output", busy, "idle-hold", treeB], ["printing every minute", chatty, "idle-chatty", main]]) {
    check(`idle: a running shell ${what} is interrupted for inactivity about an hour after it started, its shell killed and its instance cleaned up`, () => {
      const interrupted = events("session.execution.interrupted", (record) => record.sessionID === session);
      assert(interrupted.length > 0 && interrupted.every((record) => record.reason === "inactivity"), label);
      assert.equal(ended(label), false, label);
      // The interruption, the location's shutdown and its instance's cleanup
      // land within milliseconds of each other, in no fixed order.
      const [first] = instanceAt(directory);
      assert(cleanedUp(first.instance), label);
      for (const at of [interrupted[0].at, cleanedUp(first.instance).at]) {
        const after = minutes(at - shell(label).startedAt);
        assert(after >= 60 && after < 62.5, `${label}: ${after} minutes`);
      }
      assert(!one("idle.settled").active[session], label);
    });
  }
  check("idle: a shell's output publishes no event, so it renews nothing", () => {
    const progress = events("session.tool.progress", (record) => record.sessionID === chatty);
    assert(progress.length > 0 && progress.every((record) => record.location === main));
    const firstTick = one("idle.tick").receipt;
    assert(progress.every((record) => record.receipt < firstTick), "progress during the wait");
  });
  check("idle: an evicted location is set up afresh by its session's next turn", () => {
    const [first, second] = instanceAt(treeA);
    assert(second && second.receipt > cleanedUp(first.instance).receipt);
    assert.equal(shell("after-idle").env.SPIKE_PLUGIN_INSTANCE, second.instance);
    assert.equal(shell("after-idle").env.OPENCODE_SESSION_ID, quiet);
  });
}

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} claims verified`);
