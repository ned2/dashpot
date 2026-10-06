// Independent verifier for the Issue #421 trace: checks each measured claim
// docs/spikes/opencode-v2-worker-mechanics-spike.md makes about OpenCode 2.0.22's
// worker mechanics against the recorded model requests, shell commands,
// API answers, hook records, observations and Cleanup reports.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace");
const text = readFileSync(tracePath, "utf8");
const records = text.trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };
const main = "$ROOT/repository";
const treeA = "$ROOT/repository.worktrees/a";
const treeB = "$ROOT/repository.worktrees/b";
const treeC = "$ROOT/repository.worktrees/c";

const kind = (name) => records.filter((record) => record.kind === name);
const one = (name, predicate = () => true) => {
  const found = records.find((record) => record.kind === name && predicate(record));
  assert(found, `no ${name} record`);
  return found;
};
const labelled = (name, label) => one(name, (record) => record.label === label);
const shell = (label, phase = "end") => one("command", (record) => record.label === label && record.phase === phase);
const ran = (label, phase = "end") => records.some((record) => record.kind === "command" && record.label === label && record.phase === phase);
const dashpot = (label) => shell(label).dashpot;
const output = (label) => dashpot(label).stdout + dashpot(label).stderr;
// The session a shell ran for, by the identity OpenCode gave it.
const claim = (label) => shell(label, "start").env.OPENCODE_SESSION_ID;
const sessionOf = (title) => one("session", (record) => record.title === title).sessionID;
const observation = (label) => {
  const found = labelled("observation", label);
  assert.equal(found.error, null, `${label}: ${found.error}`);
  return found;
};
// Each bound Agent Run, by Issue: its state and the Worktree it is observed at.
const runs = (label) => Object.fromEntries(observation(label).runs.filter((run) => run.issueId)
  .map((run) => [run.issueId.replace("I_fixture_", "issue-"), [run.state, run.workingDirectory]]));
const blockers = (label) => labelled("cleanup", label).obstacles.map((obstacle) => obstacle.kind);
const blocker = (label, kindName) => labelled("cleanup", label).obstacles.find((obstacle) => obstacle.kind === kindName)?.detail ?? "";
// A session's hook record in one Worktree's store.
const hook = (label, worktree, id) => labelled("state", label).sessions[`${worktree}/${id}.json`];
const requests = (predicate) => kind("model.request").filter((record) => !record.titled && predicate(record));
// The tool result a session's model saw at one step of a label's sequence.
const toolResult = (label, step, sessionID) => {
  const found = requests((record) => record.label === label && record.step === step && (!sessionID || record.sessionID === sessionID));
  assert(found.length, `no request for ${label} step ${step}`);
  return found.at(-1).lastTool ?? "";
};
const freshNotice = (sessionID, child) => requests((record) => record.sessionID === sessionID)
  .find((record) => record.notices?.some((notice) => notice.fresh && notice.sessionID === child));
const info = (label) => labelled("session.info", label);
const UNKNOWN_MOVE = "Unknown tool 'opencode.session_move'";

const environment = one("environment");
// The runner's helper scripts change only with a new trace, so they must
// match. The runner and this verifier may be edited after the trace, and
// Dashpot's sources keep changing after it is retained, so a difference in
// either is reported, and fails only under --strict.
const editable = ["run.mjs", "verify.mjs"];
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// A directory's digest, as the runner takes it: each file's relative name and
// content, in sorted order.
const treeDigestOf = (directory) => {
  if (!existsSync(directory)) return null;
  const hash = createHash("sha256");
  for (const name of readdirSync(directory, { recursive: true }).map(String).toSorted()) {
    try { hash.update(name + "\0" + readFileSync(path.join(directory, name))); } catch {}
  }
  return hash.digest("hex");
};
for (const file of ["run.mjs", "verify.mjs", "command.mjs", "api.mjs", "ancestry.mjs"]) {
  if (!editable.includes(file)) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
}
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => (file.endsWith("/") ? treeDigestOf : digestOf)(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot sources differ from the run's: ${drifted.join(", ")}`);
const runnerChanged = editable.filter((file) => digestOf(path.join(here, file)) !== environment.sourceSHA256[file]);
assert(!(strict && runnerChanged.length), `the runner or verifier differs from the run's: ${runnerChanged.join(", ")}`);

const known = one("known").sessions;
const lead = sessionOf("Lead");
const rep = sessionOf("Reporter");
const loc = sessionOf("Locator");
const mv = sessionOf("Mover");
const guard = sessionOf("Guard");

check("the trace names no path outside the fixture's placeholders", () => {
  assert.deepEqual(text.match(/(?<![\w$])\/(?:tmp|home)\/[^"\s]*/g) ?? [], []);
});
check("the pinned OpenCode release, driving the installed copy of this checkout's plugin, helper and skill", () => {
  assert.equal(environment.version, "opencode v2.0.22");
  assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
  assert.equal(environment.installedMatchesSource, true);
  assert.equal(labelled("integrate", "install").status, 0);
  assert.match(labelled("integrate", "install").stdout, /skill in \$ROOT\/config\/opencode\/skills\/dashpot-issue-work/);
});
check("every scenario completed, every helper run succeeded, and no fixture process outlived the run", () => {
  assert.deepEqual(kind("failure"), []);
  assert.deepEqual(kind("scenario").map((record) => record.name), ["installer", "launch", "idle-wake", "report", "resume", "location",
    "move-while-working", "guard", "depth", "interrupt", "tui", "delete", "skills", "project-agent"]);
  assert.equal(kind("done").length, 1);
  assert.deepEqual(one("events").unsuccessful, []);
  assert.deepEqual(one("cleanup.remaining").pids, []);
});

// Question 1: launch and concurrency.
check("Q1: the subagent tool takes agent, description, prompt, model, sessionID and background; the shell tool a workdir, timeout and background", () => {
  const tools = Object.fromEntries(one("tools").tools.map((tool) => [tool.name, tool.parameters]));
  assert.deepEqual(tools.subagent, ["agent", "description", "prompt", "model", "sessionID", "background"]);
  assert.deepEqual(tools.shell, ["command", "workdir", "timeout", "background"]);
});
check("Q1: three background launches in one step run at once while the lead's own shell runs", () => {
  assert.deepEqual(requests((record) => record.label === "lead-launch" && record.step === 0)[0].tools, ["subagent", "subagent", "subagent"]);
  assert.match(toolResult("lead-launch", 1, lead), /working in the background \(sessionID: ses_/);
  const leadShell = shell("lead-after-launch");
  for (const worker of ["w1-hold", "w2-hold", "w3-hold"]) {
    assert(shell(worker, "start").startedAt < leadShell.endedAt, `${worker} started while the lead held`);
    assert(shell(worker).endedAt > leadShell.startedAt, `${worker} still ran when the lead's shell began`);
  }
  assert.equal(labelled("active", "workers-running").sessions.length, 4);
  assert(labelled("prompt.admitted", "lead-launch").ms < 1000);
});
check("Q1: a turn that only launches a worker ends at once, before the worker starts", () => {
  assert(labelled("turn", "idle-launch").ms < 2000);
  assert.equal(one("parent.settled").childEnded, false);
});
check("Q1: a worker cannot launch its own sub-agent at the default depth, and can once the configuration raises it", () => {
  assert.match(toolResult("w11", 1), /Subagent depth limit reached \(1\)\. Increase \\"experimental\.subagent_depth\\"/);
  assert.equal(labelled("reload", "depth-two").status, 0);
  const grandchild = claim("reviewer-deeper");
  assert.equal(one("server.event", (record) => record.type === "session.created" && record.sessionID === grandchild).parentID, claim("w12-after-reviewer"));
  assert.match(toolResult("w12", 1), /<subagent sessionID="ses_\w+" state="completed">/);
});

// Question 2: a mid-flight report.
check("Q2: `opencode run --session <lead>` from a worker starts the idle lead and returns its reply", () => {
  const { exec } = shell("w5-report-idle");
  assert.deepEqual([exec.status, exec.args.slice(0, 3)], [0, ["opencode", "run", "--session"]]);
  assert.equal(exec.args[3], rep);
  assert(exec.ms < 5000);
  assert.match(exec.stdout, /Fixture complete: report-idle\./);
  assert(requests((record) => record.sessionID === rep && record.label === "report-idle").length);
});
check("Q2: into a busy lead the message is steered in at the next step, and the worker's call blocks until the lead's turn ends", () => {
  const { exec } = shell("w6-report-busy");
  assert.equal(exec.status, 0);
  assert(exec.ms > 5000, `blocked ${exec.ms} ms`);
  const first = requests((record) => record.sessionID === rep && record.label === "report-busy")[0];
  assert(first.receiptTime >= shell("rep-busy-hold").endedAt);
  assert.match(exec.stdout, /Fixture complete: report-busy\./);
});
check("Q2: a background shell lets the worker go on while its report waits", () => {
  const went = labelled("worker.went-on", "w16-after");
  assert.deepEqual([went.reportEnded, went.leadHeld], [false, false]);
  assert.equal(shell("w16-report-background").exec.status, 0);
  assert(freshNotice(rep, known.w16));
});
check("Q2: a report from a shell in another Worktree neither moves the lead nor relocates its run", () => {
  assert.equal(shell("w18-report-cd", "start").cwd, treeB);
  assert.equal(shell("w18-report-cd").exec.status, 0);
  assert.equal(info("rep-after-cd-report").location, main);
  assert.deepEqual(runs("rep-after-cd-report")["issue-4"], ["waiting", main]);
  assert.deepEqual(Object.keys(labelled("state", "rep-after-cd-report").sessions).filter((key) => key.includes(rep)), [`${main}/${rep}.json`]);
});
check("Q2: a shell timeout ends the worker's blocking report, and the lead still gets the message", () => {
  const timeout = labelled("worker.timeout", "w19-after");
  assert.deepEqual([timeout.reportStarted, timeout.reportEnded, timeout.leadHeld], [true, false, false]);
  assert.match(toolResult("w19", 2), /Command exceeded timeout of 3000 ms/);
  assert.equal(labelled("delivered", "report-timeout").seen, true);
});
check("Q2: the HTTP API, with the registration's password, admits the report and returns at once", () => {
  const { api } = shell("w25-report-api");
  assert.equal(api.status, 200);
  assert(api.ms < 2000);
  assert(api.registration.includes("password") && api.registration.includes("url"));
  assert.match(api.body, /"delivery":"steer"/);
  assert.equal(labelled("delivered", "report-api").seen, true);
});
check("Q2: Dashpot sees no new session, Host Process or location for a worker's report", () => {
  const before = observation("rep-before-report");
  for (const label of ["rep-after-idle-report", "rep-during-busy-report", "rep-after-cd-report"]) {
    const after = observation(label);
    assert.equal(after.runs.length, before.runs.length, label);
    assert.deepEqual([...new Set(after.runs.map((run) => run.processOrSession))], [...new Set(before.runs.map((run) => run.processOrSession))], label);
  }
  assert.deepEqual(runs("rep-during-busy-report")["issue-4"], ["running", main]);
});

// Question 3: completion.
check("Q3: a finished worker's final text reaches its lead as a synthetic user notice", () => {
  for (const worker of ["w1-hold", "w2-hold", "w3-hold"]) {
    const request = freshNotice(lead, claim(worker));
    const notice = request.notices.find((item) => item.sessionID === claim(worker));
    assert.deepEqual([notice.role, notice.state], ["user", "completed"]);
    assert.match(notice.head, /^Fixture complete: w\d\.$/);
  }
});
check("Q3: a busy lead gets the notices at its next step, in the execution it was running", () => {
  const notified = freshNotice(lead, claim("w1-hold"));
  assert.equal(notified.label, "lead-launch");
  const launched = requests((record) => record.sessionID === lead && record.label === "lead-launch" && record.step === 0)[0];
  // The launch's own execution, and no other before the notices arrive.
  assert.equal(kind("server.event").filter((record) => record.type === "session.execution.started" && record.sessionID === lead
    && record.receipt > launched.receipt && record.receipt < notified.receipt).length, 1);
  assert(notified.receipt < labelled("turn", "lead-launch").receipt);
});
check("Q3: a lead whose turn had ended is woken with a new execution by the notice", () => {
  const ended = one("turn", (record) => record.label === "idle-launch");
  const request = freshNotice(sessionOf("Idle"), known.w4);
  assert(request.receiptTime > ended.receiptTime);
  assert(kind("server.event").some((record) => record.type === "session.execution.started" && record.sessionID === sessionOf("Idle")
    && record.receiptTime > ended.receiptTime));
});

// Question 4: resume.
check("Q4: the lead resumes a finished worker by its session ID, in the same child session", () => {
  assert.equal(claim("w5-resumed"), known.w5);
  assert.equal(claim("w5-start"), known.w5);
  // One child session per worker launched, none for the resumption.
  assert.deepEqual(kind("server.event").filter((record) => record.type === "session.created" && record.parentID === rep).map((record) => record.sessionID).toSorted(),
    [known.w5, known.w6, known.w16, known.w18, known.w19, known.w25, known.w7].toSorted());
});
check("Q4: a prompt to a running worker steers it: its next step follows the new prompt", () => {
  assert.equal(claim("w7-steered"), claim("w7-hold"));
  assert(shell("w7-steered", "start").startedAt >= shell("w7-hold").endedAt);
  assert.equal(ran("w7-unsteered", "start"), false);
});

// Question 5: the shared Agent Session.
check("Q5: a worker's `work start` is refused as a delegated session naming its lead, at any depth", () => {
  assert.equal(dashpot("w1-cd").status, 2);
  assert.match(output("w1-cd"), new RegExp(`refused \\(delegated-session\\): it is a child session of ${lead}`));
  assert.equal(dashpot("reviewer-deeper-start").status, 2);
  assert.match(output("reviewer-deeper-start"), new RegExp(`refused \\(delegated-session\\): it is a child session of ${sessionOf("Depth")}`));
});
check("Q5: the lead's run reads running while its workers run, even after its own turn ended", () => {
  assert.deepEqual(runs("workers-running")["issue-1"], ["running", main]);
  assert.deepEqual(runs("workers-finished")["issue-1"], ["waiting", main]);
  assert.deepEqual(runs("idle-lead-worker-running")["issue-3"], ["running", main]);
  assert.deepEqual(runs("idle-lead-woken")["issue-3"], ["waiting", main]);
});
check("Q5: the Cleanup sub-agent blocker holds every other Worktree while workers run and clears when they end", () => {
  assert.deepEqual(blockers("tree-a-workers-running"), ["sub-agent"]);
  assert.match(blocker("tree-a-workers-running", "sub-agent"), /has 3 sub-agents listed as working/);
  assert.deepEqual(blockers("tree-a-workers-finished"), []);
  assert.deepEqual(blockers("tree-a-idle-lead-worker-running"), ["sub-agent"]);
  assert.deepEqual(blockers("tree-a-idle-lead-woken"), []);
});
check("Q5: `work show` from a worker reports its lead's run where the lead is, and nothing elsewhere", () => {
  assert.match(output("w1-show"), /issue-1 \(I_fixture_1\)[\s\S]*has 3 sub-agents listed as working/);
  assert.equal(shell("w8-cd").cwd, treeB);
  assert.equal(output("w8-cd"), "no active Issue work at this worktree\n");
});

// Question 6: location.
check("Q6: a worker's shell starts in its lead's directory; `cd` and `workdir` run a command elsewhere", () => {
  assert.equal(shell("w1-start", "start").cwd, main);
  assert.equal(shell("w8-start", "start").cwd, main);
  assert.equal(shell("w8-cd", "start").cwd, treeB);
  assert.equal(shell("w8-workdir", "start").cwd, treeC);
});
check("Q6: a worker's session_move on itself moves only the worker", () => {
  assert.deepEqual([info("w8-after-self-move").location, info("w8-after-self-move").parentID], [treeA, loc]);
  assert.equal(shell("w8-after-self-move", "start").cwd, treeA);
  assert.equal(info("loc-after-child-self-move").location, main);
  assert.deepEqual(runs("child-moved-itself")["issue-5"], ["waiting", main]);
});
check("Q6: a worker's session_move naming its lead moves the lead, and Dashpot relocates the lead's run", () => {
  assert.match(toolResult("w9", 1), new RegExp(`"directory": "\\$ROOT/repository\\.worktrees/c"`));
  assert.equal(info("loc-after-child-moved-it").location, treeC);
  assert.deepEqual(runs("child-moved-lead")["issue-5"], ["waiting", treeC]);
  assert.equal(shell("loc-after-move-show", "start").cwd, treeC);
});
check("Q6: a deny of *session_move removes the tool from a worker whose agent is in the configuration, a global agent file, or a project agent file", () => {
  assert.match(toolResult("w10", 1), new RegExp(UNKNOWN_MOVE));
  assert.equal(info("loc-after-guarded-child").location, main);
  assert.match(toolResult("w20", 1), new RegExp(UNKNOWN_MOVE));
  assert.equal(info("guard-md-lead").location, main);
  assert.match(toolResult("w21", 1), new RegExp(UNKNOWN_MOVE));
  assert.equal(info("guard-project-lead").location, main);
  const ids = (label) => labelled("agents.listed", label).agents.map((agent) => agent.id);
  assert(ids("guard").includes("dashpot-worker-md") && !ids("guard").includes("dashpot-worker-project"));
  assert(ids("project-config").includes("dashpot-worker-project"));
  assert.deepEqual(one("project.ancestors").found, []);
});
check("Q6: a lead session's own permissions bind its workers; the lead's agent does not", () => {
  assert.deepEqual(one("session", (record) => record.title === "GuardSession").permissions, [{ action: "*session_move", resource: "*", effect: "deny" }]);
  assert.match(toolResult("w22", 1), new RegExp(UNKNOWN_MOVE));
  assert.equal(info("guard-session-lead").location, main);
  assert.equal(one("session", (record) => record.title === "GuardAgent").agent, "dashpot-lead");
  assert.doesNotMatch(toolResult("w23", 1), /Unknown tool/);
  assert.equal(info("guard-agent-lead").location, treeC);
});
check("Q6: a denied worker still moves its lead through the HTTP API with the registration's password", () => {
  assert.match(toolResult("w24", 1), new RegExp(UNKNOWN_MOVE));
  assert.equal(shell("w24-bypass-api").api.status, 204);
  assert.equal(info("guard-bypass-lead").location, treeC);
  assert.equal(guard, known.guard);
});
check("Dashpot: a lead moved while its worker runs keeps that worker listed in the record it left, after the worker ended", () => {
  const worker = known.w17;
  assert.deepEqual(hook("mv-before-move", main, mv).subagents, [worker]);
  assert.deepEqual(hook("mv-moved-worker-running", treeB, mv).subagents, [worker]);
  assert(freshNotice(mv, worker));
  for (const label of ["mv-worker-ended", "mv-later"]) {
    assert.deepEqual([hook(label, main, mv).state, hook(label, main, mv).subagents], ["running", [worker]], label);
    assert.deepEqual(hook(label, treeB, mv).subagents, [], label);
  }
  assert.deepEqual(runs("mv-worker-ended")["issue-11"], ["waiting", treeB]);
  assert.deepEqual(blockers("tree-a-mv-worker-ended"), ["sub-agent"]);
  assert.match(blocker("tree-a-mv-later", "sub-agent"), new RegExp(`at \\$ROOT/repository\\.worktrees/b has 1 sub-agent listed as working \\(${worker}`));
  assert.match(output("mv-later-show"), new RegExp(`has 1 sub-agent listed as working \\(${worker}\\)`));
  assert.deepEqual(hook("mv-back", main, mv).subagents, []);
  assert.deepEqual(blockers("tree-a-mv-back"), []);
});
check("Dashpot: the same holds when the worker itself moved the lead", () => {
  assert.deepEqual(hook("child-moved-lead", main, loc).subagents, [known.w9]);
  assert.match(blocker("tree-b-child-moved-lead", "sub-agent"), new RegExp(`has 1 sub-agent listed as working \\(${known.w9}`));
  assert.match(output("loc-after-move-show"), new RegExp(`has 1 sub-agent listed as working \\(${known.w9}\\)`));
});

// Question 7: interruption.
check("Q7: interrupting the lead's turn ends its own shell but not its background worker, whose notice wakes the lead", () => {
  const interrupt = one("interrupt");
  assert.deepEqual([interrupt.status, interrupt.body], [200, { interrupted: true }]);
  assert.deepEqual(labelled("active", "lead-interrupted").sessions, [known.w13]);
  assert.equal(ran("int-busy"), false);
  assert(ran("w13-hold"));
  assert(freshNotice(sessionOf("Interrupted"), known.w13));
  assert.deepEqual(runs("lead-interrupted-worker-running")["issue-8"], ["running", main]);
  assert.deepEqual(runs("lead-interrupted-worker-ended")["issue-8"], ["waiting", main]);
});
check("Q7: quitting the lead's TUI leaves the worker running and the run live, and the notice wakes the client-less lead", () => {
  const exit = one("client.exit", (record) => record.name === "tui");
  assert(exit.receiptTime < shell("w14-hold").receiptTime);
  assert.deepEqual(labelled("active", "tui-quit-worker-running").sessions, [known.w14]);
  assert.deepEqual(runs("tui-quit-worker-running")["issue-9"], ["running", treeC]);
  assert(freshNotice(known.tui ?? claim("tui-start"), known.w14).receiptTime > exit.receiptTime);
  assert.deepEqual(runs("tui-quit-worker-ended")["issue-9"], ["waiting", treeC]);
});
check("Q7: deleting the lead deletes its running worker, ends the run and clears the blocker", () => {
  assert.equal(one("delete").status, 204);
  const after = one("worker.after-delete");
  assert.deepEqual([after.held, after.after, after.info], [false, false, { missing: 404 }]);
  assert.deepEqual(labelled("active", "lead-deleted").sessions, []);
  assert.equal(runs("delete-worker-running")["issue-10"][0], "running");
  assert.equal(runs("lead-deleted")["issue-10"], undefined);
  assert(blockers("tree-b-delete-worker-running").includes("sub-agent"));
  assert(!blockers("tree-b-lead-deleted").includes("sub-agent"));
});

// Question 8: skills.
check("Q8: OpenCode lists the skill integrate installs, beside skills in Claude Code's and the shared agents directories", () => {
  const listed = Object.fromEntries(one("skills.listed").skills.map((skill) => [skill.id, skill.path]));
  assert.equal(listed["dashpot-issue-work"], "$ROOT/config/opencode/skills/dashpot-issue-work/SKILL.md");
  assert.equal(listed["fixture-external-claude"], "$ROOT/home/.claude/skills/fixture-external-claude/SKILL.md");
  assert.equal(listed["fixture-external-agents"], "$ROOT/home/.agents/skills/fixture-external-agents/SKILL.md");
});
check("Q8: autoinvoke false hides a skill from the model's list but not from the skill tool; Claude Code's flag is ignored", () => {
  const offered = requests((record) => record.label === "skills-probe")[0].skills;
  assert(offered.includes("dashpot-issue-work") && offered.includes("fixture-claude-flag"));
  assert(!offered.includes("fixture-user-only"));
  const loaded = requests((record) => record.label === "skills-probe" && record.step === 3)[0].skillContent;
  assert.deepEqual(loaded, ["dashpot-issue-work", "fixture-user-only", "fixture-claude-flag"]);
});
check("Q8: a user invokes the hidden skill by naming it in the prompt", () => {
  assert.deepEqual(requests((record) => record.label === "skills-user" && record.step === 0)[0].skillContent, ["fixture-user-only"]);
});

for (const item of checks) console.log(`ok - ${item}`);
console.log(`${checks.length} claims verified`);
console.log(drifted.length ? `Dashpot sources changed since the run: ${drifted.join(", ")}` : `Dashpot sources match the run's (${environment.dashpotHead})`);
if (runnerChanged.length) console.log(`note - runner or verifier changed since this trace was recorded: ${runnerChanged.join(", ")}`);
