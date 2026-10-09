// Independent verifier for the OpenCode acceptance trace, re-pinned to 2.0.22
// by Issue #407: checks each claim docs/agent-sessions.md,
// docs/installation.md, the harness reference and ADR 0090 make about OpenCode
// v2 sessions through Dashpot's managed plugin against the recorded installer
// output, shell commands, hook and publisher records, observations and
// Cleanup reports.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the acceptance trace");
const text = readFileSync(tracePath, "utf8");
const records = text.trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };
const main = "$ROOT/repository";
const treeA = "$ROOT/repository.worktrees/a";
const treeB = "$ROOT/repository.worktrees/b";
const treeC = "$ROOT/repository.worktrees/c";
const other = "$ROOT/other";

const kind = (name) => records.filter((record) => record.kind === name);
const one = (name, predicate = () => true) => {
  const found = records.find((record) => record.kind === name && predicate(record));
  assert(found, `no ${name} record`);
  return found;
};
const labelled = (name, label) => one(name, (record) => record.label === label);
const shell = (label, phase = "end") => one("command", (record) => record.label === label && record.phase === phase);
const dashpot = (label) => shell(label).dashpot;
const claimed = (label) => shell(label, "start").env;
const observation = (label) => {
  const found = labelled("observation", label);
  assert.equal(found.error, null, `${label}: ${found.error}`);
  return found;
};
// Each bound Agent Run, by Issue: its state, whether it is orphaned, the Host
// Process it names, and the Worktree it is observed at.
const runs = (label) => Object.fromEntries(observation(label).runs.filter((run) => run.issueId)
  .map((run) => [run.issueId.replace("I_fixture_", "issue-"), [run.state, run.orphaned, Number(run.processOrSession.match(/pid (\d+)/)?.[1]), run.workingDirectory]]));
const diagnostics = (label) => observation(label).diagnostics.map((diagnostic) => diagnostic.code).filter((code) => code !== "pull-requests-not-configured");
const cleanup = (label) => labelled("cleanup", label).report;
const blockers = (label) => cleanup(label).obstacles.map((obstacle) => obstacle.kind);
const sessionOf = (title) => one("session", (record) => record.title === title).sessionID;
const turn = (label) => one("turn", (record) => record.label === label);
const hookFile = (label, worktree, id) => labelled("state", label).files[`${worktree}/.dashpot/state/sessions/${id}.json`];
const integration = (label) => {
  const found = labelled("integrate", label);
  return { ...found, text: found.stdout + found.stderr };
};
const serviceOf = (label) => labelled("service", label);
const helperSummary = one("events").summary;
// The instance counts, by the label of the step that took them.
const counts = Object.fromEntries(kind("instances").map((record) => [record.label, record]));

const environment = one("environment");
// The runner's helper scripts change only with a new trace, so they must
// match. The runner and this verifier may be edited after the trace, and
// Dashpot's sources keep changing after it is retained, so a difference in
// either is reported, and fails only under --strict.
const editable = ["run.mjs", "verify.mjs"];
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
const scripts = ["run.mjs", "verify.mjs", "command.mjs", "replay.mjs", "ancestry.mjs"];
for (const file of scripts) if (!editable.includes(file)) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot sources differ from the run's: ${drifted.join(", ")}`);
const runnerChanged = editable.filter((file) => digestOf(path.join(here, file)) !== environment.sourceSHA256[file]);
assert(!(strict && runnerChanged.length), `the runner or verifier differs from the run's: ${runnerChanged.join(", ")}`);

check("the trace names no path outside the fixture's placeholders", () => {
  assert.deepEqual(text.match(/(?<![\w$])\/(?:tmp|home)\/[^"\s]*/g) ?? [], []);
});

const shared = serviceOf("shared").pid;
const older = serviceOf("older").pid;
const newer = serviceOf("newer").pid;
const restarted = serviceOf("restarted").pid;
const a1 = sessionOf("A1");
const a2 = sessionOf("A2");
const b1 = sessionOf("B1");
const p = sessionOf("P");
const q = sessionOf("Q");
const m = sessionOf("M");
const tui = claimed("tui-start").OPENCODE_SESSION_ID;
const cliRun = claimed("run-start").OPENCODE_SESSION_ID;
const fork = one("fork");
const leaked = "ses_leakedfromanothersession00";
const hex = /^[0-9a-f]{64}$/;

check("the accepted OpenCode release, driving the installed copy of this checkout's plugin and helper", () => {
  // As each binary's --version prints it: v2 names itself, v1 does not.
  assert.deepEqual([environment.version, environment.olderVersion, environment.v1Version], ["opencode v2.0.22", "opencode v2.0.21", "1.18.30"]);
  for (const name of ["binarySHA256", "olderBinarySHA256", "v1BinarySHA256"]) assert.match(environment[name], hex, name);
  assert.equal(environment.installedMatchesSource, true);
});
check("every scenario completed and no fixture process outlived the run", () => {
  assert.deepEqual(kind("failure"), []);
  assert.deepEqual(kind("scenario").map((record) => record.name), ["installer", "shared", "subagents", "fork", "moves", "churn",
    "unavailable-helper", "deletion", "replacement", "standalone", "npm"]);
  assert.equal(kind("done").length, 1);
  assert.deepEqual(one("cleanup.remaining").pids, []);
});
check("every turn reached the fixture provider", () => {
  const { requests } = one("models");
  const prompted = [...kind("turn").map((record) => record.label),
    ...kind("client.spawn").flatMap((record) => record.args.filter((arg) => arg.startsWith("PROBE:")).map((arg) => arg.slice(6)))];
  assert(prompted.length > 30, `${prompted.length} turns`);
  for (const label of prompted) assert(requests[label] > 0, `${label} reached the provider`);
});
check("the service listens only on its private port, on the loopback address", () => {
  for (const label of ["shared", "older", "newer", "restarted", "npm"]) {
    assert.deepEqual(serviceOf(label).listening, [{ table: "tcp", address: "0100007F", port: environment.servicePort }], label);
  }
});
check("every helper run the Event Log recorded succeeded, the slowest within a second", () => {
  assert.deepEqual(one("events").unsuccessful, []);
  for (const kindName of ["hook:opencode:register", "hook:opencode:event", "hook:opencode:gone", "hook:opencode:unobserved"]) {
    assert(helperSummary[kindName]?.runs > 0, kindName);
    assert.deepEqual(Object.keys(helperSummary[kindName].results), ["succeeded"], kindName);
    assert(helperSummary[kindName].slowestSeconds < 1, `${kindName}: ${helperSummary[kindName].slowestSeconds}`);
  }
});
check("the helper runs as a child of the Host Process that loaded the plugin", () => {
  const helpers = one("helpers").processes.filter((entry) => !entry.parentCmdline?.includes("replay.mjs"));
  assert(helpers.length > 50, `${helpers.length} helpers sampled`);
  for (const entry of helpers) assert(["opencode", "opencode.exe"].includes(entry.parentComm), JSON.stringify(entry));
});

// The installer, beside unrelated configuration and plugins.
check("integrate refuses OpenCode v1 on PATH and writes nothing", () => {
  assert.equal(integration("v1-on-path").status, 2);
  assert.match(integration("v1-on-path").text, /the opencode on PATH is OpenCode 1\.18\.30, and Dashpot observes OpenCode v2 only; install OpenCode 2\.0\.22 and retry/);
  const contents = ({ plugin, skill, unrelated }) => ({ plugin, skill, unrelated });
  assert.deepEqual(contents(labelled("files", "after-v1")), contents(labelled("files", "before")));
});
check("install, reinstall, remove and install again leave unrelated configuration and plugins untouched", () => {
  const files = (label) => labelled("files", label);
  for (const label of ["installed", "reinstalled", "removed", "final"]) assert.deepEqual(files(label).unrelated, files("before").unrelated, label);
  assert.equal(files("before").plugin, null);
  assert(files("installed").plugin && files("installed").skill);
  assert.equal(files("reinstalled").plugin, files("installed").plugin);
  assert.deepEqual([files("removed").plugin, files("removed").skill], [null, false]);
  assert.equal(files("final").plugin, files("installed").plugin);
  assert.match(integration("install").text, /^OpenCode release on PATH: 2\.0\.22, the accepted release$/m);
  assert.match(integration("reinstall").text, /OpenCode plugin already installed/);
  assert.match(integration("remove").text, /removed the OpenCode plugin/);
});
check("a plugin file the user owns is refused and kept", () => {
  assert.equal(integration("foreign-plugin").status, 2);
  assert.match(integration("foreign-plugin").text, /is not a plugin Dashpot manages/);
  assert.equal(one("foreign").kept, true);
});
check("status names the accepted release, on PATH and as the running service, with nothing to warn of", () => {
  assert.match(integration("status").text, /^OpenCode release on PATH: 2\.0\.22, the accepted release$/m);
  assert.match(integration("status").text, /^OpenCode service: none registered in \$ROOT\/state\/opencode\/service\.json$/m);
  const service = integration("status-service").text;
  assert.match(service, new RegExp(`^OpenCode service: pid ${shared}, registered in `, "m"));
  assert.match(service, /^OpenCode service release: 2\.0\.22, the accepted release$/m);
  for (const label of ["status", "status-service"]) assert.doesNotMatch(integration(label).text, /warning:/, label);
});
check("status warns of another 2.x release, on PATH or as the service, and refuses v1", () => {
  assert.match(integration("status-older-on-path").text, /warning: OpenCode 2\.0\.21 is not the accepted release 2\.0\.22; the plugin observes it/);
  const service = integration("status-older-service").text;
  assert.match(service, new RegExp(`^OpenCode service: pid ${older}, registered`, "m"));
  assert.match(service, /^OpenCode service release: 2\.0\.21\nwarning: OpenCode 2\.0\.21 is not the accepted release 2\.0\.22/m);
  const v1 = integration("status-v1-on-path").text;
  assert.match(v1, /^OpenCode release on PATH: 1\.18\.30, refused$/m);
  assert.match(v1, /warning: Dashpot observes OpenCode v2 only: under 1\.18\.30 the plugin publishes nothing and no command can opt in/);
});
check("status reports an edited plugin and a missing helper, and integrate repairs the plugin", () => {
  assert.match(integration("status-edited").text, /plugin update available at \$ROOT\/config\/opencode\/plugins\/dashpot\.js; run 'dashpot integrate opencode' to repair/);
  assert.match(integration("repair").text, /updated the OpenCode plugin/);
  assert.match(integration("status-missing-helper").text, /hook publisher missing at \$ROOT\/venv\/bin\/dashpot-opencode-hook; run 'dashpot integrate opencode' to repair/);
});

// The shared service: a TUI dispatched as the skill does, sessions in three
// Worktrees, and a CLI run.
check("the TUI the skill dispatches starts the service, and its session is created in the named Worktree", () => {
  const spawned = one("client.spawn", (record) => record.name === "tui");
  assert.equal(spawned.cwd, "$ROOT");
  assert.deepEqual(spawned.args.slice(0, 1), [treeC]);
  assert.equal(shell("tui-start").cwd, treeC);
  const { processes } = labelled("processes", "tui-running");
  const service = processes.find((entry) => entry.pid === shared);
  assert.equal(service.cmdline, "$ROOT/home/.opencode/bin/opencode serve --service");
  assert.equal(processes.find((entry) => entry.pid === service.ppid).cmdline.split(" ")[0], "opencode");
});
check("a model's shell carries OpenCode's own claim for its session, with inherited claims cleared then overridden", () => {
  assert.deepEqual(one("client.spawn", (record) => record.name === "tui").inherited,
    ["OPENCODE_SESSION_ID", "OPENCODE", "DASHPOT_AGENT_SESSION", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"]);
  assert.notEqual(tui, leaked);
  for (const [label, id] of [["tui-start", tui], ["a1-start", a1], ["a2-start", a2], ["b1-start", b1], ["run-start", cliRun]]) {
    const env = claimed(label);
    assert.deepEqual([env.OPENCODE_SESSION_ID, env.OPENCODE, env.DASHPOT_OPENCODE_PID, env.DASHPOT_OPENCODE_REFUSAL], [id, "1", String(shared), null], label);
    assert.deepEqual([env.DASHPOT_AGENT_SESSION, env.CODEX_THREAD_ID, env.CLAUDE_CODE_SESSION_ID, env.CLAUDE_PID], ["", "", "", ""], label);
    assert.equal(dashpot(label).status, 0, label);
    assert.match(dashpot(label).stdout, /^started work on issue-\d+ \(I_fixture_\d+\)$/m, label);
  }
});
check("sessions of one service hold their own runs, in the same Worktree and in different ones", () => {
  assert.deepEqual(runs("three-bound"), {
    "issue-1": ["waiting", false, shared, treeC], "issue-2": ["waiting", false, shared, main],
    "issue-3": ["waiting", false, shared, main], "issue-4": ["waiting", false, shared, treeA],
  });
  assert.deepEqual(blockers("tree-a-bound"), ["agent-session", "agent-run"]);
  const [session] = cleanup("tree-a-bound").obstacles;
  assert.match(session.detail, new RegExp(`OpenCode session ${b1} is live here .* To free this Worktree, move that session to another location in OpenCode, or delete that session with opencode session delete ${b1}, or stop the OpenCode server it runs in, with opencode service stop or by quitting its --standalone client, which leaves every Agent Run on that server orphaned\\.`));
});
check("one session's activity is not another's", () => {
  assert.deepEqual(Object.fromEntries(Object.entries(runs("a1-holding")).map(([issue, [state]]) => [issue, state])),
    { "issue-1": "waiting", "issue-2": "running", "issue-3": "waiting", "issue-4": "waiting" });
});
check("one session switches and another stops, leaving the rest alone", () => {
  assert.match(dashpot("a1-switch").stdout, /^switched from issue-2 to issue-7 \(I_fixture_7\)$/m);
  assert.match(dashpot("a2-stop").stdout, /^stopped work on issue-3$/m);
  assert.deepEqual(Object.keys(runs("switched-and-stopped")).sort(), ["issue-1", "issue-4", "issue-6", "issue-7"]);
});
check("a CLI run's session runs in the service, and outlives the run's exit", () => {
  assert.equal(one("client.exit", (record) => record.name === "run").code, 0);
  assert.equal(shell("run-start").cwd, treeB);
  assert.deepEqual(runs("switched-and-stopped")["issue-6"], ["waiting", false, shared, treeB]);
  assert.deepEqual(blockers("tree-b-run-exited"), ["agent-session", "agent-run"]);
});

// Shells that cannot opt in.
check("a claim from another Worktree, by cd, is refused", () => {
  assert.equal(shell("a2-cd-tree-a").cwd, treeA);
  assert.equal(dashpot("a2-cd-tree-a").status, 2);
  assert.match(dashpot("a2-cd-tree-a").stderr, /Issue work is declared where the session itself runs/);
});
check("an explicit DASHPOT_AGENT_SESSION naming an OpenCode session without OpenCode's claim is refused", () => {
  assert.equal(dashpot("a2-explicit").status, 2);
  assert.match(dashpot("a2-explicit").stderr, new RegExp(`OpenCode session ${a2} \\(from DASHPOT_AGENT_SESSION\\) is not OpenCode's own claim`));
});
check("a user's shell keeps the plugin's pid but not OpenCode's variables, and is refused as one", () => {
  const env = claimed("user-shell");
  assert.deepEqual([env.OPENCODE_SESSION_ID, env.OPENCODE, env.DASHPOT_OPENCODE_PID], [null, null, String(shared)]);
  assert.equal(dashpot("user-shell").status, 2);
  assert.match(dashpot("user-shell").stderr, /this command runs in a shell the user started in OpenCode, not one its agent ran/);
});
check("a terminal runs no plugin hook, and is refused as no agent's command", () => {
  const env = claimed("pty");
  assert.equal(one("pty").status, 200);
  // The terminal inherits the service's environment, which the TUI that
  // started the service leaked into.
  assert.equal(env.DASHPOT_OPENCODE_PID, null);
  assert.equal(env.OPENCODE_SESSION_ID, leaked);
  assert.equal(dashpot("pty").status, 2);
  assert.match(dashpot("pty").stderr, /or it runs in an OpenCode terminal, which is no agent's command/);
  assert.equal(runs("switched-and-stopped")["issue-5"], undefined);
});

// The TUI's session after the TUI quits, and resumed from elsewhere.
check("quitting the TUI leaves its session in the service, still blocking Cleanup", () => {
  assert(one("tui.quit", (record) => record.label === "ctrl-c").ms < 3000);
  assert.equal(one("service.after-tui").alive, true);
  assert.deepEqual(runs("tui-quit")["issue-1"], ["waiting", false, shared, treeC]);
  assert.deepEqual(blockers("tree-c-tui-quit"), ["agent-session", "agent-run"]);
});
check("a session resumed from another directory still runs where it was, and keeps its run", () => {
  assert.equal(one("client.spawn", (record) => record.name === "tui-resumed-elsewhere").args[0], main);
  assert.equal(labelled("session.info", "tui-resumed-elsewhere").location, treeC);
  assert.equal(shell("tui-resumed-elsewhere-show").cwd, treeC);
  assert.equal(claimed("tui-resumed-elsewhere-show").OPENCODE_SESSION_ID, tui);
  assert.match(dashpot("tui-resumed-elsewhere-show").stdout, new RegExp(`^opencode pid ${shared}: issue-1 `, "m"));
  assert.deepEqual(runs("tui-resumed-elsewhere")["issue-1"], ["waiting", false, shared, treeC]);
});

// Sub-agents and forks.
check("a child's command carries the child's claim and is refused as delegated, while its root reads running", () => {
  const child = claimed("child-hold").OPENCODE_SESSION_ID;
  assert.equal(one("server.event", (record) => record.type === "session.created" && record.sessionID === child).parentID, p);
  assert.equal(dashpot("child-start").status, 2);
  assert.match(dashpot("child-start").stderr, new RegExp(`OpenCode session ${child} \\(from OpenCode environment\\) is refused \\(delegated-session\\): it is a child session of ${p}`));
  assert.deepEqual(hookFile("child-working", main, p).liveSubagents, [child]);
  assert.equal(runs("child-working")["issue-8"][0], "running");
  assert.equal(runs("child-finished")["issue-8"][0], "waiting");
});
check("a background child holds its root running after the root's turn ends, and blocks Cleanup in every Worktree", () => {
  const parent = one("parent.settled");
  assert.deepEqual([parent.sessionID, parent.childStarted], [q, false]);
  const child = claimed("bg-child").OPENCODE_SESSION_ID;
  assert.deepEqual(hookFile("background-working", treeA, q).liveSubagents, [child]);
  assert.equal(one("active").sessions[child]?.type, "running");
  assert.equal(runs("background-working")["issue-10"][0], "running");
  assert(blockers("tree-b-background-working").includes("sub-agent"));
  assert.equal(dashpot("bg-child-start").status, 2);
  assert.match(dashpot("bg-child-start").stderr, /refused \(delegated-session\)/);
  assert.equal(runs("background-finished")["issue-10"][0], "waiting");
  assert(!blockers("tree-b-background-finished").includes("sub-agent"));
});
check("a fork is a root session with its own run", () => {
  assert.equal(fork.parentID, null);
  assert.equal(one("server.event", (record) => record.type === "session.forked" && record.sessionID === fork.sessionID).parentID, a1);
  assert.equal(claimed("fork-start").OPENCODE_SESSION_ID, fork.sessionID);
  assert.doesNotMatch(dashpot("fork-unbound-show").stdout, /issue-11/);
  assert.match(dashpot("fork-start").stdout, /started work on issue-11/);
  assert.deepEqual(runs("forked")["issue-11"], ["waiting", false, shared, main]);
  assert.deepEqual(runs("forked")["issue-7"], ["waiting", false, shared, main]);
});

// Moves.
check("a session moved within the Repository, by its own tool or the API, takes its run along", () => {
  assert.equal(labelled("session.info", "m-moved-by-tool").location, treeA);
  assert.deepEqual(runs("m-moved-by-tool")["issue-12"], ["waiting", false, shared, treeA]);
  assert.equal(labelled("move", "m-moved-by-api").status, 204);
  assert.equal(shell("m-moved-by-api-show").cwd, treeB);
  assert.match(dashpot("m-moved-by-api-show").stdout, /issue-12/);
  assert.deepEqual(runs("m-moved-by-api")["issue-12"], ["waiting", false, shared, treeB]);
});
check("a move while the session works takes effect when its execution ends", () => {
  const moved = labelled("move", "m-moved-while-busy");
  assert.deepEqual([moved.status, moved.after.location], [204, treeB]);
  assert.equal(labelled("session.info", "m-moved-while-busy").location, main);
  assert.deepEqual(runs("m-moved-while-busy")["issue-12"], ["waiting", false, shared, main]);
});
check("a session moved out of the Repository keeps its run, reported as working elsewhere, and back again", () => {
  assert.equal(runs("m-in-other")["issue-12"][3], main);
  assert.deepEqual(diagnostics("m-in-other"), ["work-session-elsewhere"]);
  assert(observation("m-in-other-project").runs.some((run) => run.processOrSession.includes(m) && !run.issueId));
  assert.equal(runs("m-in-plain")["issue-12"][3], main);
  assert.deepEqual(diagnostics("m-in-plain"), ["work-session-elsewhere"]);
  assert.deepEqual(runs("m-back")["issue-12"], ["waiting", false, shared, main]);
  assert.deepEqual(diagnostics("m-back"), []);
});
check("the records a moved session leaves behind never hold a Worktree", () => {
  assert.equal(hookFile("run-deleted-by-cli", treeB, m).state, "running");
  assert.equal(cleanup("tree-b-run-deleted").removable, true);
});

// Plugin instances set up again.
check("a plugin edit, its repair and opencode reload set every instance up again, leaving bound sessions as they were", () => {
  assert(counts.edited.registered > counts["before-edit"].registered);
  assert(counts.repaired.registered > counts["before-repair"].registered);
  assert(counts.reloaded.registered > counts["before-reload"].registered);
  assert.equal(counts.reloaded.unobserved, counts["before-reload"].unobserved);
  assert.equal(one("reload").status, 0);
  assert.equal(runs("reload-holding")["issue-10"][0], "running");
  assert.equal(hookFile("reload-holding", treeA, q).sessionProcessUnobservable, null);
  assert.equal(runs("reload-hold-ended")["issue-10"][0], "waiting");
});
check("a missing helper never delays a turn, a stalled one by no more than the plugin's wait, and a restored one publishes again", () => {
  assert(turn("a1-missing-helper").ms < 2000, `${turn("a1-missing-helper").ms}`);
  assert(turn("a1-stalled-helper").ms > 2500 && turn("a1-stalled-helper").ms < 7000, `${turn("a1-stalled-helper").ms}`);
  for (const label of ["a1-missing-helper-show", "a1-stalled-helper-show", "a1-helper-back-show"]) {
    assert.equal(claimed(label).OPENCODE_SESSION_ID, a1, label);
    assert.equal(dashpot(label).status, 0, label);
  }
  const record = hookFile("helper-back", main, a1);
  assert.deepEqual([record.state, record.event], ["waiting", "Stop"]);
  assert(Date.parse(record.lastActivityAt) > turn("a1-stalled-helper").receiptTime, record.lastActivityAt);
});

// Deletion.
check("deleting a session through the API ends its run, and every other session survives", () => {
  assert.equal(hookFile("b1-deleted", treeA, b1), undefined);
  assert.equal(runs("b1-deleted")["issue-4"], undefined);
  assert.deepEqual(Object.keys(runs("b1-deleted")).sort(), Object.keys(runs("reload-hold-ended")).filter((issue) => issue !== "issue-4").sort());
});
check("opencode session delete, run from another Worktree, ends the session's run and frees its Worktree", () => {
  assert.equal(one("client.exit", (record) => record.name === "cli-delete").code, 0);
  assert.equal(hookFile("run-deleted-by-cli", treeB, cliRun), undefined);
  assert.equal(runs("run-deleted-by-cli")["issue-6"], undefined);
  assert.equal(cleanup("tree-b-run-deleted").removable, true);
});
check("with the plugin unloaded, a model's shell carries OpenCode's variables but no mark, and is refused", () => {
  assert.equal(counts.removed.unobserved, counts["before-remove"].unobserved + 1);
  const env = claimed("a1-unplugged-start");
  assert.deepEqual([env.OPENCODE_SESSION_ID, env.OPENCODE, env.DASHPOT_OPENCODE_PID], [a1, "1", null]);
  assert.equal(env.DASHPOT_AGENT_SESSION, "codex:inherited");
  assert.equal(dashpot("a1-unplugged-start").status, 2);
  assert.match(dashpot("a1-unplugged-start").stderr, /the OpenCode server running it has not loaded the plugin/);
  assert.equal(runs("fork-deleted-unplugged")["issue-13"], undefined);
});
check("the last instance's cleanup marks running records as observed by nothing, and only those", () => {
  const { files } = labelled("state", "fork-deleted-unplugged");
  const records = Object.values(files).filter((record) => record.harness === "opencode");
  assert(records.some((record) => record.state === "running"));
  for (const record of records) assert.equal(record.sessionProcessUnobservable, record.state === "running" ? "opencode-no-live-instance" : null, record.sessionId);
});
check("a deletion no instance received is recovered when an instance registers", () => {
  assert.equal(one("delete", (record) => record.unplugged).status, 204);
  assert.equal(hookFile("fork-deleted-unplugged", main, fork.sessionID).state, "waiting");
  assert.deepEqual(runs("fork-deleted-unplugged")["issue-11"].slice(0, 2), ["waiting", false]);
  assert.deepEqual(kind("recovery.missing"), []);
  assert.equal(hookFile("fork-recovered", main, fork.sessionID), undefined);
  assert.equal(runs("fork-recovered")["issue-11"], undefined);
  assert.equal(claimed("a1-replugged-show").DASHPOT_OPENCODE_PID, String(shared));
});
check("late, earlier, deleted, misplaced and forged publications change nothing", () => {
  const replay = one("replay");
  assert.equal(replay.target, a1);
  assert.deepEqual(replay.outcomes.map(({ label, acknowledgment }) => [label, acknowledgment.result, acknowledgment.reason ?? null]), [
    ["register", "accepted", null],
    ["late-end", "stale", null],
    ["earlier-start", "stale", null],
    ["deleted-session", "refused", "session-deleted"],
    ["outside-project", "refused", "outside-project"],
    ["forged-host", "rejected", "host-process-not-corroborated"],
  ]);
  assert.deepEqual(replay.after, replay.before);
});

// The service replaced, stopped and killed.
check("another release's TUI replaces the service, orphaning every run on it", () => {
  assert.equal(serviceOf("older").version, "2.0.21");
  assert.equal(serviceOf("older").process.exe, "$ROOT/older/bin/opencode");
  for (const [issue, [state, orphaned, pid]] of Object.entries(runs("older-service"))) assert.deepEqual([state, orphaned, pid], ["unknown", true, shared], issue);
});
check("a session continues its run on a new service only through work start", () => {
  assert.equal(claimed("a1-on-older-show").DASHPOT_OPENCODE_PID, String(older));
  assert.match(dashpot("a1-on-older-show").stdout, new RegExp(`^opencode pid ${shared}: issue-7 `, "m"));
  assert.match(dashpot("a1-on-older-start").stdout, /^already working on issue-7; run restarted$/m);
  assert.deepEqual(runs("a1-on-older")["issue-7"], ["waiting", false, older, main]);
});
check("a 2.0.22 TUI resuming a session as the skill says replaces the service again, and work start continues the run", () => {
  const spawned = one("client.spawn", (record) => record.name === "q-resumed");
  assert.deepEqual(spawned.args.slice(0, 3), [treeA, "--session", q]);
  assert.equal(serviceOf("newer").version, "2.0.22");
  assert.equal(claimed("q-resumed-start").OPENCODE_SESSION_ID, q);
  assert.match(dashpot("q-resumed-start").stdout, /^already working on issue-10; run restarted$/m);
  assert.deepEqual(runs("q-resumed")["issue-10"], ["waiting", false, newer, treeA]);
  assert.deepEqual(runs("q-resumed")["issue-7"].slice(0, 3), ["unknown", true, older]);
});
check("opencode service stop orphans every run, and Cleanup's named stop frees the Worktree", () => {
  const stopped = one("service.stopped", (record) => record.how === "cli" && record.pid === newer);
  assert.equal(stopped.registration, "removed");
  for (const [issue, [state, orphaned]] of Object.entries(runs("service-stopped"))) assert.deepEqual([state, orphaned], ["unknown", true], issue);
  assert.deepEqual(blockers("tree-a-service-stopped"), ["agent-run"]);
  assert.equal(cleanup("tree-a-service-stopped").obstacles[0].detail, `Orphaned Agent Run on issue-10 for opencode pid ${newer}`);
  assert(kind("work-stop").filter((record) => record.label === "tree-a-orphans").every((record) => record.status === 0));
  assert.equal(cleanup("tree-a-orphans-stopped").removable, true);
});
check("a killed service leaves its registration, which status reports as exited, and its runs orphaned", () => {
  assert.equal(one("service.stopped", (record) => record.how === "SIGKILL").registration, "kept");
  assert.match(integration("status-killed-service").text, new RegExp(`^OpenCode service: none running; \\$ROOT/state/opencode/service\\.json names pid ${restarted}, which has exited$`, "m"));
  assert.deepEqual(runs("service-killed")["issue-14"], ["unknown", true, restarted, treeC]);
  assert.deepEqual(blockers("tree-c-service-killed"), ["agent-run", "agent-run"]);
});

// --standalone.
const standalone = (label, client) => {
  const { processes } = labelled("processes", label);
  const parent = processes.find((entry) => entry.cmdline.startsWith(client));
  const server = processes.find((entry) => entry.ppid === parent.pid);
  assert.equal(server.cmdline, "$ROOT/home/.opencode/bin/opencode serve --stdio --port 0", label);
  return server.pid;
};
check("opencode run --standalone hosts its session in a private server, and its exit orphans the run", () => {
  const server = standalone("standalone-run", "opencode run --standalone");
  assert.equal(claimed("sa-run-start").DASHPOT_OPENCODE_PID, String(server));
  assert.notEqual(server, restarted);
  assert.deepEqual(runs("standalone-run-working")["issue-15"], ["running", false, server, treeB]);
  assert.equal(one("client.exit", (record) => record.name === "standalone-run").code, 0);
  assert.deepEqual(runs("standalone-run-exited")["issue-15"], ["unknown", true, server, treeB]);
});
check("a --standalone TUI hosts its session in a private server, and quitting it orphans the run", () => {
  const server = standalone("standalone-tui", "opencode --standalone");
  assert.equal(claimed("sa-tui-start").DASHPOT_OPENCODE_PID, String(server));
  assert.deepEqual(runs("standalone-tui-bound")["issue-16"], ["waiting", false, server, treeB]);
  assert.deepEqual(blockers("tree-b-standalone-tui"), ["agent-session", "agent-run", "agent-run"]);
  assert.deepEqual(runs("standalone-tui-quit")["issue-16"], ["unknown", true, server, treeB]);
  assert(kind("work-stop").filter((record) => record.label === "tree-b-orphans").every((record) => record.status === 0));
  assert.equal(cleanup("tree-b-orphans-stopped").removable, true);
});

// The npm package's layout.
check("the npm package's service is opencode.exe, a Host Process like any other", () => {
  const service = serviceOf("npm");
  assert.deepEqual([service.version, service.process.comm], ["2.0.22", "opencode.exe"]);
  assert.equal(claimed("npm-start").DASHPOT_OPENCODE_PID, String(service.pid));
  assert.equal(dashpot("npm-start").status, 0);
  assert.deepEqual(runs("npm-bound")["issue-17"], ["waiting", false, service.pid, main]);
  assert(one("helpers").processes.some((entry) => entry.parentComm === "opencode.exe"));
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} claims verified`);
console.log(drifted.length ? `Dashpot sources changed since the run: ${drifted.join(", ")}` : `Dashpot sources match the run's (${environment.dashpotHead})`);
if (runnerChanged.length) console.log(`note - runner or verifier changed since this trace was recorded: ${runnerChanged.join(", ")}`);
