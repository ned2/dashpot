// Independent verifier for the Issue #163 acceptance trace: checks each claim
// docs/agent-sessions.md, docs/installation.md and the harness reference make
// about OpenCode sessions through Dashpot's managed plugin against the
// recorded installer output, shell commands, hook and publisher records,
// observations and Cleanup reports.
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
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };
const main = "$ROOT/repository";
const sibling = "$ROOT/repository.worktrees/sibling";
const tuiTree = "$ROOT/repository.worktrees/tui";

const kind = (name) => records.filter((record) => record.kind === name);
const one = (name, predicate = () => true) => {
  const found = records.find((record) => record.kind === name && predicate(record));
  assert(found, `no ${name} record`);
  return found;
};
const labelled = (name, label) => one(name, (record) => record.label === label);
const shell = (label, phase = "end") => one("command", (record) => record.label === label && record.phase === phase);
const dashpot = (label) => shell(label).dashpot;
const observation = (label) => {
  const found = labelled("observation", label);
  assert.equal(found.error, null, `${label}: ${found.error}`);
  return found;
};
// Each bound Agent Run, by Issue: its state, whether it is orphaned, and the
// Host Process it names.
const runs = (label) => Object.fromEntries(observation(label).runs.filter((run) => run.issueId)
  .map((run) => [run.issueId.replace("I_fixture_", "issue-"), [run.state, run.orphaned, Number(run.processOrSession.match(/pid (\d+)/)?.[1])]]));
const cleanup = (label) => labelled("cleanup", label).report;
const blockers = (label) => cleanup(label).obstacles.map((obstacle) => obstacle.kind);
const sessionOf = (title) => one("session", (record) => record.title === title).sessionID;
const backend = (name) => one("backend.start", (record) => record.name === name).pid;
const turn = (label) => one("turn", (record) => record.label === label);
const hookFile = (label, worktree, id) => labelled("state", label).files[`${worktree}/.dashpot/state/sessions/${id}.json`];
const claimed = (label) => shell(label, "start").env;
const integration = (label) => {
  const found = labelled("integrate", label);
  return { ...found, text: found.stdout + found.stderr };
};

const environment = one("environment");
// The runner's scripts change only with a new trace, so they must match;
// Dashpot's sources keep changing after the trace is retained, so a
// difference is reported, and fails only under --strict.
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
const scripts = ["run.mjs", "verify.mjs", "command.mjs", "replay.mjs", "ancestry.mjs"];
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot sources differ from the run's: ${drifted.join(", ")}`);
const b1 = backend("b1");
const b2 = backend("b2");
const s1 = sessionOf("S1");
const s2 = sessionOf("S2");
const s3 = sessionOf("S3");
const fork = one("fork");
const tuiSession = one("tui.session");

check("pinned OpenCode release, driving the installed copy of this checkout's plugin and helper", () => {
  assert.equal(environment.version, "1.18.30");
  assert.equal(environment.installedMatchesSource, true);
});
check("every scenario completed and no fixture process outlived the run", () => {
  assert.deepEqual(kind("failure"), []);
  assert.equal(kind("done").length, 1);
  assert.deepEqual(one("cleanup.remaining").pids, []);
});
check("every helper run the Event Log recorded succeeded, the slowest within a second", () => {
  const { summary, unsuccessful } = one("events");
  assert.deepEqual(unsuccessful, []);
  for (const kindName of ["hook:opencode:register", "hook:opencode:status", "hook:opencode:bootstrap", "hook:opencode:retire", "hook:opencode:deleted"]) {
    assert(summary[kindName]?.runs > 0, kindName);
    assert(summary[kindName].slowestSeconds < 1, `${kindName}: ${summary[kindName].slowestSeconds}`);
  }
});
check("the helper runs as a child of the process that loaded the plugin", () => {
  const helpers = one("helpers").processes.filter((entry) => !entry.parentCmdline?.includes("replay.mjs"));
  assert(helpers.length > 50, `${helpers.length} helpers sampled`);
  for (const entry of helpers) assert.equal(entry.parentComm, "opencode", JSON.stringify(entry));
});

// The installer, beside unrelated configuration, plugins and skills.
check("install, reinstall, remove and reinstall leave unrelated configuration, plugins and skills untouched", () => {
  const files = (label) => labelled("files", label);
  // The Claude Code skill is edited and repaired between "removed" and
  // "final", which must leave it as it was before.
  const unrelated = (label) => Object.entries(files(label).unrelated);
  for (const label of ["installed", "reinstalled", "removed", "final"]) assert.deepEqual(unrelated(label), unrelated("before"), label);
  assert.equal(files("before").plugin, null);
  assert(files("installed").plugin && files("installed").skill);
  assert.equal(files("reinstalled").plugin, files("installed").plugin);
  assert.deepEqual([files("removed").plugin, files("removed").skill], [null, false]);
  assert.equal(integration("install").status, 0);
  assert.match(integration("reinstall").text, /OpenCode plugin already installed/);
  assert.match(integration("remove").text, /removed the OpenCode plugin/);
  assert.match(integration("status-removed").text, /^not installed: no /m);
});
check("a plugin file the user owns is refused and kept", () => {
  assert.equal(integration("foreign-plugin").status, 2);
  assert.match(integration("foreign-plugin").text, /is not a plugin Dashpot manages/);
  assert.equal(one("foreign").kept, true);
});
check("status names the accepted release, and nothing is unsupported on it", () => {
  for (const label of ["status", "status-final"]) {
    assert.match(integration(label).text, /OpenCode release: 1\.18\.30, the accepted release/);
    assert.doesNotMatch(integration(label).text, /unsupported|warning:/);
  }
});
check("status warns that another release is unsupported", () => {
  assert.match(integration("status-other-release").text, /warning: OpenCode 1\.18\.31 is unsupported/);
});
check("status reports a stale or missing helper path, and integrate repairs it", () => {
  assert.match(integration("status-stale-helper").text, /hook publisher missing at \$ROOT\/removed\/bin\/dashpot-opencode-hook; run 'dashpot integrate opencode' to repair/);
  assert.match(integration("repair").text, /updated the OpenCode plugin/);
  assert.match(integration("status-missing-helper").text, /hook publisher missing at \$ROOT\/venv\/bin\/dashpot-opencode-hook/);
});
check("status warns of a second plugin copy, a differing discovered skill, and OPENCODE_PURE", () => {
  const text = integration("status-duplicates-pure").text;
  assert.match(text, /warning: OpenCode also discovers the Issue work skill at \$ROOT\/home\/\.claude\/skills\/dashpot-issue-work, which differs/);
  assert.match(text, /warning: OpenCode also loads a copy of the Dashpot plugin at \$ROOT\/home\/\.opencode\/plugins\/copy\.js/);
  assert.match(text, /warning: OPENCODE_PURE is set here/);
  assert.match(integration("claude-code-repair").text, /updated Dashpot Issue work skill/);
});
check("OpenCode offers the installed Issue-work skill beside the user's own", () => {
  const mentions = one("skills").mentions.join("\n");
  // Two identical skills share the name: OpenCode offers one of them.
  assert.match(mentions, /<location>\$ROOT\/(config\/opencode|home\/\.claude)\/skills\/dashpot-issue-work\/SKILL\.md<\/location>/);
  assert.match(mentions, /Not Dashpot's skill/);
});

// One backend, two sessions in the main Worktree and one in a sibling.
check("a shell command gets its own session's claim, with inherited claims blanked", () => {
  for (const [label, id] of [["s1-start", s1], ["s2-start", s2], ["s3-start", s3]]) {
    const env = claimed(label);
    assert.deepEqual([env.DASHPOT_OPENCODE_SESSION_ID, env.DASHPOT_OPENCODE_PID], [id, String(b1)], label);
    assert.deepEqual([env.DASHPOT_AGENT_SESSION, env.CODEX_THREAD_ID, env.CLAUDE_CODE_SESSION_ID], ["", "", ""], label);
    assert.equal(dashpot(label).status, 0, label);
  }
  assert.equal(shell("s3-start").cwd, sibling);
});
check("sessions of one backend hold their own runs, in the same Worktree and in different ones", () => {
  assert.deepEqual(runs("three-bound"), { "issue-1": ["waiting", false, b1], "issue-2": ["waiting", false, b1], "issue-3": ["waiting", false, b1] });
  const targets = Object.fromEntries(observation("three-bound").runs.filter((run) => run.issueId).map((run) => [run.issueId, run.observationTarget]));
  assert.deepEqual(targets, { I_fixture_1: main, I_fixture_2: main, I_fixture_3: sibling });
  assert.deepEqual(blockers("sibling-live"), ["agent-session", "agent-run"]);
});
check("one session's activity is not another's", () => {
  assert.deepEqual(runs("s1-holding"), { "issue-1": ["running", false, b1], "issue-2": ["waiting", false, b1], "issue-3": ["waiting", false, b1] });
});
check("one session switches and another stops, leaving the third alone", () => {
  assert.match(dashpot("s1-switch").stdout, /issue-4/);
  assert.equal(dashpot("s2-stop").status, 0);
  assert.deepEqual(runs("switched-and-stopped"), { "issue-4": ["waiting", false, b1], "issue-3": ["waiting", false, b1] });
});

// Safe failures.
check("a claim from another Worktree, by cd or a tool workdir, is refused", () => {
  for (const label of ["s2-cd-sibling", "s2-workdir-sibling"]) {
    assert.equal(shell(label).cwd, sibling, label);
    assert.equal(dashpot(label).status, 2, label);
    assert.match(dashpot(label).stderr, /Issue work is declared where the session itself runs/, label);
  }
});
check("an explicit DASHPOT_AGENT_SESSION naming an OpenCode session without its claim is refused", () => {
  assert.equal(dashpot("s2-explicit").status, 2);
  assert.match(dashpot("s2-explicit").stderr, /from DASHPOT_AGENT_SESSION/);
});
check("a terminal OpenCode opens carries no identity and is refused", () => {
  const env = claimed("pty");
  assert.equal(env.DASHPOT_OPENCODE_SESSION_ID, "");
  assert.equal(env.DASHPOT_OPENCODE_UNCORROBORATED, "no-session-identity");
  assert.equal(dashpot("pty").status, 2);
  assert.match(dashpot("pty").stderr, /no corroborated identity: no-session-identity/);
  assert.equal(runs("refusals")["issue-5"], undefined);
});

// Attached clients.
check("an attached client's commands run in the backend under its session's claim", () => {
  for (const label of ["s3-attached-show", "s3-reattached-show", "s3-tui-attached-show"]) {
    const start = shell(label, "start");
    assert.equal(start.env.DASHPOT_OPENCODE_SESSION_ID, s3, label);
    assert(start.ancestry.some((entry) => entry.pid === b1), label);
    assert.equal(dashpot(label).status, 0, label);
  }
});
check("a client detached mid-command leaves the session running in its backend, still blocking Cleanup", () => {
  const exited = one("client.exit", (record) => record.name === "cli-detach");
  assert.equal(exited.signal, "SIGTERM");
  assert.deepEqual(runs("s3-detached-mid-command")["issue-3"], ["running", false, b1]);
  assert.deepEqual(blockers("sibling-detached"), ["agent-session", "agent-run"]);
  assert(shell("s3-detach-hold").receipt > exited.receipt);
  assert.deepEqual(runs("s3-detached-turn-ended")["issue-3"], ["waiting", false, b1]);
});
check("closing an attached TUI leaves the session in its backend", () => {
  assert.deepEqual(runs("attached-tui-closed")["issue-3"], ["waiting", false, b1]);
  assert.deepEqual(blockers("sibling-attached-tui-closed"), ["agent-session", "agent-run"]);
});

// Children and forks.
check("a native child's command is refused as delegated, while its root reads running", () => {
  assert.equal(claimed("child-hold").DASHPOT_OPENCODE_UNCORROBORATED, "delegated-session");
  assert.equal(claimed("child-hold").DASHPOT_OPENCODE_SESSION_ID, "");
  assert.equal(dashpot("child-start").status, 2);
  assert.match(dashpot("child-start").stderr, /no corroborated identity: delegated-session/);
  assert.deepEqual(runs("child-working")["issue-4"], ["running", false, b1]);
  assert.deepEqual(runs("child-finished")["issue-4"], ["waiting", false, b1]);
});
check("a fork is a separate root session with its own run", () => {
  assert.equal(fork.parentID, null);
  assert.notEqual(fork.sessionID, s1);
  assert.equal(claimed("fork-start").DASHPOT_OPENCODE_SESSION_ID, fork.sessionID);
  assert.match(dashpot("fork-start").stdout, /started work on issue-7/);
  assert.deepEqual(runs("forked"), { "issue-7": ["waiting", false, b1], "issue-4": ["waiting", false, b1], "issue-3": ["waiting", false, b1] });
});

// Retry, interrupt, refusal.
check("a retried turn stays running", () => {
  assert(kind("native").some((record) => record.sessionID === s3 && record.type === "session.status" && record.status === "retry"));
  assert.deepEqual(runs("s3-retrying")["issue-3"], ["running", false, b1]);
  assert.equal(turn("retry").error, null);
});
check("an interrupted turn ends at waiting, its command stopped", () => {
  assert.equal(turn("interrupt").error, "MessageAbortedError");
  assert.equal(one("aborted").commandEnded, false);
  assert(one("aborted").ms < 3000);
  assert.deepEqual(runs("s3-aborted")["issue-3"], ["waiting", false, b1]);
});
check("a turn the provider refuses ends at waiting", () => {
  assert.equal(turn("refused").error, "APIError");
  assert.deepEqual(runs("s3-refused")["issue-3"], ["waiting", false, b1]);
});

// Plugin replacement, removal and restoration.
check("a replaced plugin leaves its instance's sessions unknown while the backend runs, and others alone", () => {
  assert.deepEqual(runs("main-disposed"), { "issue-7": ["unknown", false, b1], "issue-4": ["unknown", false, b1], "issue-3": ["waiting", false, b1] });
  assert.equal(hookFile("main-disposed", main, s1).sessionProcessUnobservable, "opencode-publisher-retired");
  assert.equal(hookFile("main-disposed", main, s1).sessionProcess.pid, b1);
});
check("the successor's publication returns the session to its run, unchanged", () => {
  assert.equal(runs("main-replaced")["issue-4"][0], "waiting");
  const since = (label) => dashpot(label).stdout.match(/issue-4 \(I_fixture_4\) since (\S+)/)[1];
  assert.equal(since("s1-after-replace"), since("s1-switched-show"));
  assert.notEqual(claimed("s1-after-replace").DASHPOT_OPENCODE_GENERATION, claimed("s1-switch").DASHPOT_OPENCODE_GENERATION);
});
check("a retired generation's claim is refused while its backend runs", () => {
  assert.equal(dashpot("s1-retired-claim").status, 2);
  assert.match(dashpot("s1-retired-claim").stderr, /is not corroborated/);
});
check("with the plugin removed, inherited claims reach commands and are refused", () => {
  const env = claimed("s1-unplugged-start");
  assert.equal(env.DASHPOT_OPENCODE_SESSION_ID, null);
  assert.equal(env.DASHPOT_AGENT_SESSION, "codex:inherited");
  assert.equal(dashpot("s1-unplugged-start").status, 2);
  assert.equal(runs("main-unplugged")["issue-8"], undefined);
});
check("a restored plugin claims for the session again", () => {
  assert.equal(claimed("s1-restored-show").DASHPOT_OPENCODE_SESSION_ID, s1);
  assert.equal(dashpot("s1-restored-show").status, 0);
});
check("Cleanup names a retired plugin instance as the reason a session is unknown", () => {
  assert.deepEqual(runs("sibling-disposed")["issue-3"], ["unknown", false, b1]);
  const [obstacle] = cleanup("sibling-disposed").obstacles;
  assert.equal(obstacle.kind, "agent-session");
  assert.match(obstacle.detail, /may be live here: its liveness is unknown .* Its OpenCode backend, pid \d+, still runs, but the plugin instance that observed the session has retired/);
  assert.match(obstacle.detail, /To free this Worktree, quit the OpenCode TUI serving that session, or stop the OpenCode backend it runs in/);
});

// An unavailable helper.
check("a missing helper fails a command's claim at once, and a stalled one within the 3 s budget", () => {
  assert.equal(claimed("s2-missing-helper").DASHPOT_OPENCODE_UNCORROBORATED, "no-acknowledgment");
  assert(turn("missing-helper").ms < 2000, `${turn("missing-helper").ms}`);
  assert.equal(claimed("s2-stalled-helper").DASHPOT_OPENCODE_UNCORROBORATED, "no-acknowledgment");
  assert(turn("stalled-helper").ms > 2500 && turn("stalled-helper").ms < 5000, `${turn("stalled-helper").ms}`);
  assert.equal(claimed("s2-helper-back").DASHPOT_OPENCODE_SESSION_ID, s2);
});

// Deletion and replay.
check("deleting a session in its backend ends its run, and every other session survives", () => {
  assert.equal(runs("s1-deleted")["issue-4"], undefined);
  assert.equal(hookFile("s1-deleted", main, s1), undefined);
  assert.deepEqual(Object.keys(runs("s1-deleted")).sort(), ["issue-3", "issue-7"]);
});
check("opencode session delete run in the session's directory ends its observation, not its bound run", () => {
  const s4 = sessionOf("S4");
  assert.equal(one("client.exit", (record) => record.name === "cli-delete-here").code, 0);
  assert.equal(hookFile("s4-deleted-by-cli", sibling, s4), undefined);
  assert.deepEqual(runs("s4-deleted-by-cli")["issue-10"], ["unknown", false, b1]);
  const run = cleanup("sibling-s4-deleted-by-cli").obstacles.find((obstacle) => obstacle.kind === "agent-run" && /issue-10/.test(obstacle.detail));
  assert.match(run.detail, /is working on issue-10, but no hook record of that session is left, as after 'opencode session delete', while the OpenCode backend that served it still runs: quit that OpenCode TUI or stop that backend, then end the run/);
  assert.match(run.command, /&& dashpot work stop --session opencode-session-\S+$/);
  // The named stop is refused while the backend runs, and works once it exits.
  const stop = one("work-stop", (record) => record.label === "s4-deleted-by-cli");
  assert.notEqual(stop.status, 0);
  assert.match(stop.stderr, /is still running/);
  assert.deepEqual(runs("b1-stopped")["issue-10"], ["unknown", true, b1]);
});
check("opencode session delete run in another directory publishes nothing for the session", () => {
  assert.equal(one("client.exit", (record) => record.name === "cli-delete-elsewhere").code, 0);
  assert.equal(hookFile("fork-deleted-by-cli-elsewhere", main, fork.sessionID).state, "waiting");
  // The fork's run stays, held by the live backend, until that backend exits.
  assert.deepEqual(runs("fork-deleted-by-cli-elsewhere")["issue-7"], ["unknown", false, b1]);
  assert.deepEqual(runs("b1-stopped")["issue-7"], ["unknown", true, b1]);
});
check("late, duplicate, retired, deleted and forged publications change nothing", () => {
  const replay = one("replay");
  assert.deepEqual(replay.outcomes.map(({ label, acknowledgment }) => [label, acknowledgment.result, acknowledgment.reason ?? null]), [
    ["register-again", "duplicate", null],
    ["stale-status", "stale", null],
    ["duplicate-status", "duplicate", null],
    ["retired-generation", "retired", null],
    ["deleted-session", "rejected", "session-deleted"],
    ["forged-backend", "rejected", "backend-not-corroborated"],
  ]);
  assert.deepEqual(replay.after, replay.before);
});

// Backend replacement.
check("a backend ended by SIGTERM leaves its sessions gone and their runs orphaned", () => {
  assert.equal(one("backend.exit", (record) => record.name === "b1").signal, "SIGTERM");
  for (const [issue, value] of Object.entries(runs("b1-stopped"))) assert.deepEqual(value, ["unknown", true, b1], issue);
  assert(!blockers("sibling-b1-stopped").includes("agent-session"));
});
check("a resumed session continues its run only through work start", () => {
  // Before work start, the run still names the backend that exited.
  assert.match(dashpot("s3-resumed-show").stdout, new RegExp(`^opencode pid ${b1}: issue-3 `, "m"));
  assert.doesNotMatch(dashpot("s3-resumed-show").stdout, new RegExp(`^opencode pid ${b2}: issue-3 `, "m"));
  assert.match(dashpot("s3-resumed-start").stdout, /already working on issue-3; run restarted/);
  assert.deepEqual(runs("s3-resumed")["issue-3"], ["waiting", false, b2]);
  assert.deepEqual(runs("b2-killed")["issue-3"], ["unknown", true, b2]);
});
check("once the backend exits and its orphaned runs are stopped, Cleanup is free", () => {
  assert(kind("work-stop").filter((record) => record.label === "sibling-orphan").every((record) => record.status === 0));
  assert.equal(cleanup("sibling-orphan-stopped").removable, true);
});

// The ordinary TUI.
const tuiPid = shell("tui-start", "start").env.DASHPOT_OPENCODE_PID;
check("the TUI is one process that hosts its own sessions", () => {
  const { processes } = labelled("processes", "tui");
  const tui = processes.find((entry) => String(entry.pid) === tuiPid);
  assert.equal(tui.comm, "opencode");
  assert(!processes.some((entry) => entry.comm === "opencode" && entry.ppid === tui.pid));
});
check("the TUI's plugin registers within seconds of startup, and its first publication follows the prompt", () => {
  const spawned = one("client.spawn", (record) => record.name === "tui").receiptTime;
  const registered = one("record.seen", (record) => record.file.startsWith(`${tuiTree}/.dashpot/state/sessions/opencode/`) && String(record.pid) === tuiPid).receiptTime;
  assert(registered - spawned < 10000, `${registered - spawned} ms`);
  const typed = one("typed", (record) => record.label === "tui-bind").receiptTime;
  const published = one("record.seen", (record) => record.file === `${tuiTree}/.dashpot/state/sessions/${tuiSession.sessionID}.json`).receiptTime;
  assert(published - typed < 3000, `${published - typed} ms`);
});
check("the TUI's commands, model-driven and typed with !, carry its session's claim", () => {
  assert.equal(dashpot("tui-start").status, 0);
  assert.equal(claimed("tui-bang").DASHPOT_OPENCODE_SESSION_ID, tuiSession.sessionID);
  assert.equal(dashpot("tui-bang").status, 0);
  assert.deepEqual(blockers("tui-live"), ["agent-session", "agent-run"]);
});
check("quitting the TUI with Ctrl+C retires its plugin, and the session reads gone", () => {
  assert(one("tui.quit", (record) => record.label === "ctrl-c").ms < 3000);
  const record = hookFile("tui-quit", tuiTree, tuiSession.sessionID);
  assert.deepEqual([record.sessionProcess.pid, record.sessionProcessUnobservable], [Number(tuiPid), "opencode-publisher-retired"]);
  assert.deepEqual(runs("tui-quit")["issue-9"], ["unknown", true, Number(tuiPid)]);
  assert.deepEqual(blockers("tui-quit"), ["agent-run"]);
});
check("a TUI resumed on the session continues its run through work start", () => {
  const resumedPid = claimed("tui-resumed-start").DASHPOT_OPENCODE_PID;
  assert.notEqual(resumedPid, tuiPid);
  assert.match(dashpot("tui-resumed-show").stdout, new RegExp(`^opencode pid ${tuiPid}: issue-9 `, "m"));
  assert.match(dashpot("tui-resumed-start").stdout, /already working on issue-9; run restarted/);
  assert.equal(runs("tui-resumed")["issue-9"][0], "waiting");
});
check("a session resumed from another Worktree still runs where it was created", () => {
  assert.equal(one("client.spawn", (record) => record.name === "tui-elsewhere").cwd, main);
  assert.equal(shell("tui-elsewhere").cwd, tuiTree);
  assert.equal(hookFile("tui-elsewhere", tuiTree, tuiSession.sessionID).state, "waiting");
  assert.deepEqual(blockers("tui-elsewhere"), ["agent-session", "agent-run"]);
});
check("a TUI whose terminal hangs up retires its plugin too, and the session reads gone", () => {
  const record = hookFile("tui-hangup", tuiTree, tuiSession.sessionID);
  assert.equal(record.sessionProcessUnobservable, "opencode-publisher-retired");
  assert(!blockers("tui-hangup").includes("agent-session"));
  assert.equal(cleanup("tui-orphan-stopped").removable, true);
});

// A background child.
check("a background child holds its root running after the parent's turn, and is refused as delegated", () => {
  assert(turn("bg-delegate").receipt < shell("bg-child", "start").receipt);
  assert.equal(claimed("bg-child").DASHPOT_OPENCODE_UNCORROBORATED, "delegated-session");
  const root = (label) => observation(label).runs.find((run) => !run.issueId);
  assert.equal(root("background-working").state, "running");
  assert.equal(root("background-finished").state, "waiting");
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} claims verified`);
console.log(drifted.length ? `Dashpot sources changed since the run: ${drifted.join(", ")}` : `Dashpot sources match the run's (${environment.dashpotHead})`);
