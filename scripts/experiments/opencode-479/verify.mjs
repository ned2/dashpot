// Verifier for the Issue #479 OpenCode trace: checks each measured claim the
// run makes about root-session Workers on OpenCode 2.0.22's shared service
// against the recorded model requests, shell commands, guarded `opencode api`
// calls, API answers, plugin and server events, hook records, observations
// and Cleanup reports.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
//
// verify.mjs was written after the retained run, so the trace records no hash
// for it; every other experiment file must match the hash the run recorded.
// The Dashpot sources the trace hashes may change after the run, so a
// difference from this checkout is reported, and fails only under --strict.
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
const check = (claim, test) => {
  try { test(); } catch (error) { console.error(`not ok - ${claim}`); throw error; }
  checks.push(claim);
};
const main = "$ROOT/repository";
const tree = (name) => `$ROOT/repository.worktrees/${name}`;

const kind = (name) => records.filter((record) => record.kind === name);
const one = (name, predicate = () => true) => {
  const found = records.filter((record) => record.kind === name && predicate(record));
  assert.equal(found.length, 1, `exactly one ${name}`);
  return found[0];
};
const labelled = (name, label) => one(name, (record) => record.label === label);
const shell = (label, phase = "end") => one("command", (record) => record.label === label && record.phase === phase);
const ran = (label, phase = "end") => records.some((record) => record.kind === "command" && record.label === label && record.phase === phase);
const dashpot = (label) => shell(label).dashpot;
const guarded = (label) => shell(label).exec;
const info = (label) => labelled("session.info", label);
const observation = (label) => {
  const found = labelled("observation", label);
  assert.equal(found.error, null, `${label}: ${found.error}`);
  return found;
};
// Each bound Agent Run, by Issue: its state, its Worktree and whether it is orphaned.
const runs = (label) => Object.fromEntries(observation(label).runs.filter((run) => run.issueId)
  .map((run) => [run.issueId.replace("I_fixture_", "issue-"), [run.state, run.workingDirectory, run.orphaned]]));
const blockers = (label) => labelled("cleanup", label).obstacles.map((obstacle) => obstacle.kind);
const requests = (predicate) => kind("model.request").filter((record) => !record.titled && predicate(record));
const freshNotices = (sessionID, of) => requests((record) => record.sessionID === sessionID)
  .flatMap((record) => (record.notices ?? []).filter((notice) => notice.fresh && notice.of === of).map((notice) => ({ ...notice, label: record.label, step: record.step })));
const serverEvents = (type, sessionID) => kind("server.event").filter((record) => record.type === type && (!sessionID || record.sessionID === sessionID));
const pluginEvents = (type, sessionID) => kind("plugin.event").filter((record) => record.type === type && (!sessionID || record.sessionID === sessionID));

const environment = one("environment");
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
const treeDigestOf = (directory) => {
  if (!existsSync(directory)) return null;
  const hash = createHash("sha256");
  for (const name of readdirSync(directory, { recursive: true }).map(String).toSorted()) {
    try { hash.update(name + "\0" + readFileSync(path.join(directory, name))); } catch {}
  }
  return hash.digest("hex");
};
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((file) => file.startsWith("src/"))
  .filter((file) => (file.endsWith("/") ? treeDigestOf : digestOf)(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot sources differ from the run's: ${drifted.join(", ")}`);

const known = one("known").sessions;
const lead = known.lead;

check("the trace came from these experiment files, the pinned OpenCode release and the installed copy of this checkout's plugin and agent", () => {
  for (const file of ["run.mjs", "command.mjs", "guard.mjs", "ancestry.mjs", "probe-plugin.js"]) {
    assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
  }
  assert.equal(environment.sourceSHA256["verify.mjs"], null, "verify.mjs postdates the run");
  assert.equal(environment.version, "opencode v2.0.22");
  assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
  assert.equal(environment.fixtureBinarySHA256, environment.binarySHA256);
  assert.equal(environment.installedMatchesSource, true);
  assert.equal(environment.flags.OPENCODE_DISABLE_AUTOUPDATE, "1");
  assert.equal(labelled("integrate", "install").status, 0);
});
check("the trace names no path outside the fixture's placeholders", () => {
  assert.deepEqual(text.match(/(?<![\w$])\/(?:tmp|home)\/[^"\s]*/g) ?? [], []);
});
check("every scenario completed, every wait landed, every helper run succeeded, and no fixture process outlived the run", () => {
  assert.deepEqual(kind("failure"), []);
  assert.deepEqual(kind("missing"), []);
  assert.deepEqual(kind("scenario").map((record) => record.name), ["installer", "placement", "dispatch", "notice", "worker-ask", "fork", "replies",
    "reviewer", "finish", "interrupt", "delete-lead", "move-lead", "option-b", "service-restart", "standalone", "long-wait", "always"]);
  assert.equal(kind("done").length, 1);
  assert.deepEqual(one("events").unsuccessful, []);
  assert.deepEqual(one("cleanup.remaining").pids, []);
});
check("every `opencode api` call passed the guard and reached the fixture's service; the operator's service and registration were untouched", () => {
  const calls = kind("command").filter((record) => record.guarded);
  assert(calls.length >= 30, `${calls.length} guarded calls`);
  for (const call of calls) {
    assert.equal(call.ok, true, call.label);
    assert(Object.entries(call.checks).every(([name, value]) => name === "registrationFields" || value === true), call.label);
  }
  const services = new Set(kind("service").map((record) => record.pid));
  assert(calls.every((call) => services.has(call.servicePid)), "every call names a fixture service");
  const [start, end] = [labelled("operator", "start"), labelled("operator", "end")];
  assert.deepEqual([end.registrationMtime, end.services], [start.registrationMtime, start.services]);
});

// Placement.
check("a root made with no location lands at the service's working directory; a child given a location stays at its parent's", () => {
  assert.equal(info("bare").location, "$ROOT/home");
  assert.equal(info("bare").parentID, null);
  assert.deepEqual([info("child-with-location").location, info("child-with-location").parentID], [main, lead]);
  assert.equal(one("ask.rule").asks, true);
});

// Scenario 1: dispatch.
check("1: the Lead's shell makes Worker A, a root with no parentID at Worktree a, carrying the Lead in its metadata", () => {
  const made = JSON.parse(guarded("lead-create-a").stdout).data;
  assert.equal(made.id, known.wa);
  assert.equal(shell("lead-create-a").sessionClaim, lead);
  const wa = info("wa-holding");
  assert.deepEqual([wa.location, wa.parentID, wa.metadata], [tree("a"), null, { "dashpot.lead": lead, "dashpot.issue": "issue-2" }]);
  assert.match(guarded("lead-prompt-a").stdout, /"type":"user"/);
});
check("1: a plugin receives the metadata in session.created; Dashpot's plugin treats Worker A as a root", () => {
  const created = pluginEvents("session.created", known.wa);
  assert.equal(created.length, 1);
  assert.deepEqual(created[0].metadata, { "dashpot.lead": lead, "dashpot.issue": "issue-2" });
  assert.equal(created[0].parentID, null);
  assert(created[0].dataKeys.includes("metadata"));
});
check("1: Worker A's `work start` binds at Worktree a; Worktree b is free; a's blockers are all Worker A's", () => {
  assert.equal(shell("wa-start-work", "start").env.OPENCODE_SESSION_ID, known.wa);
  assert.match(dashpot("wa-start-work").stdout, /started work on issue-2/);
  assert.deepEqual(runs("wa-holding")["issue-2"], ["running", tree("a"), false]);
  assert.deepEqual(runs("wa-holding")["issue-1"], ["waiting", main, false]);
  assert.deepEqual(blockers("tree-b-wa-holding"), []);
  const obstacles = labelled("cleanup", "tree-a-wa-holding").obstacles;
  assert(obstacles.every((obstacle) => ["agent-session", "agent-run", "process"].includes(obstacle.kind)));
  assert.match(obstacles.find((obstacle) => obstacle.kind === "agent-session").detail, new RegExp(known.wa));
  assert.match(obstacles.find((obstacle) => obstacle.kind === "agent-run").detail, /issue-2/);
});
check("1, 10: a root made through the API gets the service's environment, not the Lead's shell exports", () => {
  const start = shell("wa-start", "start");
  assert.deepEqual([start.env.LEAD_MARK, start.present.GH_TOKEN, start.env.OPENCODE_SESSION_ID], [null, false, known.wa]);
  assert.equal(start.env.DASHPOT_OPENCODE_PID, shell("lead-start", "start").env.DASHPOT_OPENCODE_PID);
});

// Scenario 2: notices.
check("2: a synthetic notice wakes an idle Lead; a repeated id is admitted once, returning the first message", () => {
  assert.equal(JSON.parse(guarded("wa-notice-1").stdout).data.id, "msg_dashpotwa0001");
  const again = JSON.parse(guarded("wa-notice-1-again").stdout).data;
  assert.equal(again.id, "msg_dashpotwa0001");
  assert.match(again.payload.text, /NOTICE:wa-idle-1 /);
  const seen = freshNotices(lead, "synthetic").map((notice) => notice.id);
  assert(seen.includes("wa-idle-1") && seen.includes("wa-idle-queue"));
  assert(!seen.includes("wa-idle-1-again"));
  assert(requests((record) => record.sessionID === lead).every((record) => !(record.notices ?? []).some((notice) => notice.id === "wa-idle-1-again")));
  assert.deepEqual(labelled("inbox", "lead-after-idle-notices").items, []);
});
check("2: to a busy Lead, a steer waits in the inbox and is delivered at the next step of the same execution; a queue after the turn's last step", () => {
  assert.deepEqual(labelled("inbox", "lead-busy-steer-pending").items, [{ id: "msg_dashpotrn0001", type: "synthetic", delivery: "steer" }]);
  assert.equal(labelled("executions", "busy-steer").lead, 1);
  const steer = freshNotices(lead, "synthetic").find((notice) => notice.id === "busy-steer");
  assert.deepEqual([steer.label, steer.step], ["lead-busy-steer", 1]);
  assert.deepEqual(labelled("inbox", "lead-busy-queue-pending").items, [{ id: "msg_dashpotrn0002", type: "synthetic", delivery: "queue" }]);
  assert.equal(labelled("executions", "busy-queue").lead, 1);
  const queued = freshNotices(lead, "synthetic").find((notice) => notice.id === "busy-queue");
  assert.deepEqual([queued.label, queued.step], ["lead-busy-queue", 3]);
});
check("2: a notice leaves the Lead's own ask pending and unanswered, and waits in the inbox until the ask is answered", () => {
  assert.equal(labelled("permissions.pending", "lead-ask-after-notice").asks.length, 1);
  assert.deepEqual(labelled("replies", "lead-ask-after-notice").replies, []);
  assert.equal(labelled("inbox", "lead-ask-after-notice").items[0].id, "msg_dashpotrn0003");
  assert.equal(labelled("permission.reply", "lead-ask").status, 204);
  const steer = freshNotices(lead, "synthetic").find((notice) => notice.id === "ask-steer");
  assert.equal(steer.label, "lead-ask");
  assert.equal(labelled("executions", "lead-ask").lead, 1);
});

// Scenario 3: a Worker's ask.
check("3, 10: the `dashpot-worker` agent, a subagent-mode agent, is accepted for a root session", () => {
  assert.deepEqual([one("agent.root").made, info("wb-made").agent, info("wb-made").parentID], [true, "dashpot-worker", null]);
});
check("3: Dashpot shows the asking Worker running; the Lead's shell lists the ask by session or by location, not by its own directory, and answers it", () => {
  assert.deepEqual(runs("wb-asking")["issue-3"], ["running", tree("b"), false]);
  assert.equal(labelled("permissions.pending", "wb-asking").asks.length, 1);
  const ask = labelled("permissions.pending", "wb-asking").asks[0].id;
  assert.match(guarded("lead-list-session").stdout, new RegExp(ask));
  assert.match(guarded("lead-list-default").stdout, /"directory":"\$ROOT\/home"\},"data":\[\]/);
  assert.match(guarded("lead-list-cwd").stdout, /"directory":"\$ROOT\/home"\},"data":\[\]/);
  assert.match(guarded("lead-list-location").stdout, new RegExp(ask));
  assert.equal(guarded("lead-reply").status, 0);
  assert(serverEvents("permission.replied", known.wb).some((record) => record.reply === "once"));
  assert(ran("wb-after-ask"));
});
check("3, 10: PUT environment replaces a Worker's environment wholesale; the agent's move denial holds for a root Worker", () => {
  const start = shell("wb-start", "start");
  assert.deepEqual([start.env.PUT_MARK, start.present.XDG_CACHE_HOME, start.env.OPENCODE_SESSION_ID], ["put", false, known.wb]);
  const moved = requests((record) => record.label === "wb" && record.sessionID === known.wb && /session_move/.test(record.lastTool ?? ""));
  assert.match(moved[0].lastTool, /Unknown tool 'opencode\.session_move'/);
  assert.equal(info("wb-after").location, tree("b"));
});

// Forks.
check("a fork is a root at its source's location, carrying a copy of its metadata and agent and a `fork` field naming its source", () => {
  const fork = one("fork");
  assert.deepEqual([fork.parentID, fork.location, fork.agent, fork.forkFields.fork.sessionID], [null, tree("b"), "dashpot-worker", known.wb]);
  assert.deepEqual(fork.metadata, { "dashpot.lead": lead, "dashpot.issue": "issue-3" });
  assert.deepEqual(fork.plugin.map((event) => [event.type, event.parentID]), [["session.forked", known.wb]]);
  assert.equal(labelled("delete", "fork").status, 204);
});

// Permission reply semantics.
check("rejecting one of two pending asks rejects both and ends the turn", () => {
  assert.equal(labelled("permissions.pending", "wj-two-asking").asks.length, 2);
  const replies = labelled("replies", "wj-two");
  assert.deepEqual(replies.replies.map((reply) => reply.reply), ["reject", "reject"]);
  assert.equal(replies.stillPending, 0);
  assert.equal(labelled("turn.requests", "wj-two").continued, false);
  assert.equal(labelled("turn.requests", "wj-two").requests.length, 1);
});
check("a reject with a message reaches the model as the tool's error, and the turn goes on", () => {
  const turn = labelled("turn.requests", "wj-message");
  assert.equal(turn.continued, true);
  assert(turn.requests.some((request) => (request.results ?? []).some((result) => /permission\.rejected.*MSG-479 read the fixture notes instead/.test(result))));
  const plain = turn.requests[0].results ?? [];
  assert(plain.every((result) => /The user declined this tool call/.test(result)));
});

// Scenario 5: reviewer.
check("5: a root Worker launches a reviewer at the default depth; it is a child at the Worker's Worktree with the Worker's metadata, refused `work start`", () => {
  const reviewer = info("reviewer");
  assert.deepEqual([reviewer.parentID, reviewer.location, reviewer.agent], [known.wa, tree("a"), "general"]);
  assert.deepEqual(reviewer.metadata, { "dashpot.lead": lead, "dashpot.issue": "issue-2" });
  assert.equal(dashpot("reviewer-work-start").status, 2);
  assert.match(dashpot("reviewer-work-start").stderr, /delegated-session/);
});
check("5: while the reviewer runs, the Repository-wide sub-agent blocker returns on another Worktree, and clears when it ends", () => {
  assert(blockers("tree-c-reviewer-running").includes("sub-agent"));
  assert.deepEqual(blockers("tree-c-reviewer-ended"), []);
});

// Scenario 6: finish.
check("6: Worker A's `work stop` and move back to the main Worktree make Worktree a removable", () => {
  assert.match(dashpot("wa-stop").stdout, /stopped work on issue-2/);
  assert.equal(info("wa-finished").location, main);
  assert.equal(runs("wa-finished")["issue-2"], undefined);
  assert.deepEqual(blockers("tree-a-wa-finished"), []);
});
check("6: after the move, Worker A's `work show` reports the Lead's run at the main Worktree", () => {
  assert.equal(shell("wa-after-move-show", "start").env.OPENCODE_SESSION_ID, known.wa);
  assert.match(dashpot("wa-after-move-show").stdout, /: issue-1 \(I_fixture_1\)/);
});

// Scenario 4: interrupt, delete, move.
check("4: an interrupted Worker records `interrupted`, leaves the active list, and keeps its run and blockers until deleted", () => {
  assert.match(guarded("runner-interrupt-c").stdout, /"interrupted":true/);
  assert.deepEqual([info("wc-interrupted").outcome, labelled("active", "wc-interrupted").sessions], ["interrupted", []]);
  assert(info("wc-interrupted").idleAt > info("wc-holding").updatedAt);
  assert.deepEqual(runs("wc-interrupted")["issue-4"], ["waiting", tree("c"), false]);
  assert.deepEqual(blockers("tree-c-wc-interrupted").toSorted(), ["agent-run", "agent-session"]);
  assert.equal(info("wc-deleted").missing, 404);
  assert.equal(runs("wc-deleted")["issue-4"], undefined);
  assert.deepEqual(blockers("tree-c-wc-deleted"), []);
});
check("4: deleting a Lead leaves its root Worker running and bound; the Worker's notice to the deleted Lead fails with 404", () => {
  assert.equal(labelled("delete", "lead2").status, 204);
  assert.equal(info("lead2-deleted").missing, 404);
  assert.deepEqual([info("wd-after-lead-deleted").parentID, info("wd-after-lead-deleted").metadata["dashpot.lead"]], [null, known.lead2]);
  assert.deepEqual(runs("lead2-deleted")["issue-6"], ["running", tree("d"), false]);
  assert.equal(runs("lead2-deleted")["issue-5"], undefined);
  assert.equal(guarded("wd-notice").status, 1);
  assert.match(guarded("wd-notice").stdout + guarded("wd-notice").stderr, /SessionNotFoundError|404/);
  assert(ran("wd-after"));
});
check("4: moving the Lead while a Worker runs carries its run; the Worker's notice reaches it at its new location; nothing is stranded", () => {
  assert.equal(labelled("move", "lead-moved").status, 204);
  assert.deepEqual(runs("lead-moved")["issue-1"], ["waiting", tree("f"), false]);
  assert.deepEqual(runs("lead-moved")["issue-7"], ["running", tree("e"), false]);
  assert(freshNotices(lead, "synthetic").some((notice) => notice.id === "we-done"));
  assert.equal(info("lead-after-we-notice").location, tree("f"));
  assert.deepEqual(runs("lead-back")["issue-1"], ["waiting", main, false]);
  assert.deepEqual(blockers("tree-f-lead-back"), []);
});

// Scenario 7: option B.
check("7: a background `opencode run` from the Lead's shell makes a root Worker that carries the Lead's exports, with no metadata; the shell's end wakes the Lead", () => {
  assert.deepEqual([info("wf").location, info("wf").parentID, info("wf").metadata], [tree("f"), null, null]);
  const start = shell("wf-start", "start");
  assert.deepEqual([start.env.LEAD_MARK, start.present.GH_TOKEN], ["lead-shell", true]);
  assert.match(dashpot("wf-start-work").stdout, /started work on issue-8/);
  assert(freshNotices(lead, "shell").some((notice) => notice.state === "completed"));
  assert.match(guarded("lead-run-f").stdout, /Fixture complete: wf\./);
});

// Scenario 8: service restart.
check("8: `opencode api` with no registered service starts the fixture's service again", () => {
  const started = one("api.unregistered");
  assert.equal(started.status, 0);
  assert.deepEqual(started.registered, ["id", "password", "pid", "url", "version"]);
  assert.equal(kind("service.start").filter((record) => record.label === "after-api").length, 0);
});
check("8: a stop orphans every bound run; the restarted service resumes only the turns it cut off, with an appended message, at the next step", () => {
  assert(Object.values(runs("stopped")).every(([state, , orphaned]) => state === "unknown" && orphaned));
  const resumed = one("resumed");
  const message = "The server restarted while you were working. Continue from where you left off without repeating completed work.";
  for (const name of ["wb", "lead"]) {
    const first = resumed.sessions[name].requests[0];
    assert.deepEqual(first.appended, [message], name);
    assert.match(first.results[0], /Command cancelled/, name);
  }
  assert.deepEqual(resumed.holdsRerun, { wb: 1, lead: 1, wi: 1 });
  assert.deepEqual(resumed.sessions.wi.requests, []);
  assert.deepEqual(resumed.sessions.we.requests, []);
  assert.equal(info("wi-after-restart").outcome, "interrupted");
});
check("8: a stop cancels a pending ask; the resumed turn goes on past it without asking again", () => {
  assert.equal(labelled("permissions.pending", "wh-before-stop").asks.length, 1);
  assert.deepEqual(labelled("permissions.pending", "wh-after-restart").asks, []);
  const after = one("resumed.after");
  assert.match(after.wh[0].results[0], /Interaction cancelled because the location shut down/);
  assert.deepEqual(after.wh[0].appended, ["The server restarted while you were working. Continue from where you left off without repeating completed work."]);
  assert.equal(after.whAfterAsk, true);
  assert.equal(one("resumed").sessions.wh.asked, 0);
});
check("8: Dashpot is told nothing of a resumed turn's start, so its run stays orphaned and its `work start` is refused as a stale hook record", () => {
  const resumed = one("resumed");
  assert(resumed.hooks.filter((hook) => hook.ms > 0).every((hook) => hook.hook === "Stop"));
  assert.deepEqual(resumed.sessions.wb.executions, 0);
  assert(!resumed.sessions.wb.plugin.some((event) => event.type === "session.execution.started"));
  assert.deepEqual(runs("resumed-holding")["issue-3"], ["unknown", tree("b"), true]);
  for (const label of ["wb-resumed-start", "lead-resumed-start"]) {
    assert.equal(dashpot(label).status, 2, label);
    assert.match(dashpot(label).stderr, /is stale \(whose process is gone\)/, label);
  }
  assert.deepEqual(runs("restarted")["issue-3"], ["unknown", tree("b"), true]);
});
check("8: the replaced environment is lost at the restart; a fresh prompt's `work start` binds a new run", () => {
  assert.equal(shell("wb-long-hold", "start").env.PUT_MARK, "put");
  assert.deepEqual([shell("wb-resumed-hold", "start").env.PUT_MARK, shell("wb-resumed-hold", "start").present.XDG_CACHE_HOME], [null, true]);
  assert.match(dashpot("wb-recover-start").stdout, /run restarted/);
  assert.deepEqual(runs("recovered")["issue-3"], ["waiting", tree("b"), false]);
  assert.deepEqual(runs("recovered")["issue-7"], ["unknown", tree("e"), true]);
});

// Scenario 9: a standalone Lead.
check("9: a standalone Lead's `opencode api` reaches the shared service, and a Worker's notice runs the Lead's session there while its own client still holds it", () => {
  const standalone = one("standalone");
  assert.notEqual(Number(standalone.serverPid), standalone.servicePid);
  assert.equal(JSON.parse(guarded("sa-info").stdout).pid, standalone.servicePid);
  assert.equal(shell("sa-info").serverPid, standalone.serverPid);
  assert.deepEqual(standalone.woken.map((woken) => Number(woken.serverPid)), [standalone.servicePid]);
  assert(shell("sa-woken", "start").receiptTime < shell("sa-lead-hold").receiptTime, "woken on the service before the client's own turn ended");
});

// Extras.
check("a v2 plugin's context offers session create, prompt, synthetic, wait, interrupt, move and remove", () => {
  const setup = kind("plugin.event").find((record) => record.type === "plugin.setup");
  for (const name of ["create", "prompt", "synthetic", "wait", "interrupt", "move", "remove"]) assert(setup.sessionKeys.includes(name), name);
});
check("a five-and-a-half-minute wait through `opencode api` is not cut at five minutes; its event stream prints nothing before the call ends", () => {
  const long = one("long.wait");
  assert.equal(long.endedBeforeAnswer, false);
  assert.equal(long.wait.status, 0);
  assert(long.wait.ms > long.answeredAt && long.answeredAt > 300000);
  assert(long.stream.ms >= 390000, "the stream ran to the guard's limit");
  assert.notEqual(long.stream.status, 0);
  assert.equal(long.stream.bytes, 0);
});
check("`always` saves a Project rule that answers the Lead's asks too, survives a service restart, and is removed through the API", () => {
  const before = labelled("permissions.saved", "before-always");
  const after = labelled("permissions.saved", "after-always");
  assert.deepEqual(before.items.project, []);
  assert.deepEqual(after.items.unscoped, []);
  assert.equal(after.items.project.length, 1);
  assert.equal(after.config, before.config);
  assert.deepEqual(kind("asked.again").map((record) => [record.label, record.asked]),
    [["wj-again", false], ["lead-read", false], ["wj-restarted", false], ["wj-removed", true]]);
  assert.equal(labelled("permissions.saved", "after-restart").items.project.length, 1);
  assert(kind("permission.saved.remove").every((record) => record.status >= 200 && record.status < 300));
  assert.deepEqual(labelled("permissions.saved", "after-removal").items.project, []);
});

for (const item of checks) console.log(`ok - ${item}`);
console.log(`${checks.length} claims verified`);
console.log(drifted.length ? `Dashpot sources changed since the run: ${drifted.join(", ")}` : `Dashpot sources match the run's (${environment.dashpotHead})`);
