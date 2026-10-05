// Independent verifier for the Issue #479 Claude Code trace: checks each
// claim the root-session Workers experiment
// (docs/spikes/root-session-workers-spike.md) makes about root `claude --bg`
// Workers dispatched from a Lead's shell (identity, environment, occupancy, messaging,
// permission classes, the commit instruction, stop and respawn) against the
// recorded hook, shell, listing, Worktree check and observation evidence.
//
// The retained traces are gzipped to stay under the repository's large-file
// check; their recorded SHA-256 is of the uncompressed JSONL.
//
// Usage: node verify.mjs <trace.jsonl[.gz]> [<trace.jsonl[.gz]> ...]
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";

const read = (file) => (file.endsWith(".gz") ? gunzipSync(readFileSync(file)) : readFileSync(file)).toString("utf8");
const load = (file) => read(file).trim().split("\n").map((line) => JSON.parse(line));
const passed = [];
const check = (claim, test) => { test(); passed.push(claim); };
const main = "$ROOT/repository";
const tree = (name) => `$ROOT/repository.worktrees/${name}`;

const verify = (records, file) => {
  const environment = records.find((record) => record.kind === "environment");
  const version = environment.version.split(" ")[0];
  const label = (claim) => `${version}: ${claim}`;
  const hooks = records.filter((record) => record.kind === "hook");
  const command = (name, phase = "end") => records.find((record) => record.kind === "command" && record.label === name && record.phase === phase);
  const shells = (session) => records.filter((record) => record.kind === "command" && record.env.CLAUDE_CODE_SESSION_ID === session);
  const worker = (name) => records.filter((record) => record.kind === "worker" && record.name === name && record.sessionId).at(-1);
  const sessionHooks = (session, event) => hooks.filter((record) => record.payload.session_id === session && (!event || record.event === event) && !record.payload.agent_id);
  const checks = (name) => { const found = records.find((record) => record.kind === "checks" && record.label === name); assert(found, `checks ${name}`); return found; };
  const kinds = (result) => result.blockers.map((blocker) => blocker.kind).sort();
  const observation = (name) => { const found = records.find((record) => record.kind === "observation" && record.label === name); assert(found, `observation ${name}`); assert.equal(found.error, null); return found; };
  const listing = (name) => records.find((record) => record.kind === "action.claude" && record.label === name);
  const requests = (name) => records.filter((record) => record.kind === "model.request" && record.label === name && record.stream);
  const lead = records.find((record) => record.kind === "turn" && record.lead === "lead").session;
  const lead2 = records.find((record) => record.kind === "turn" && record.lead === "lead2")?.session;
  const ids = Object.fromEntries(["a", "b", "p", "q"].map((name) => [name, worker(`worker-${name}`).sessionId]));
  ids.z = command("wz-shell", "start").env.CLAUDE_CODE_SESSION_ID;
  for (const name of ["r", "s"]) ids[name] = worker(`worker-${name}`)?.sessionId;

  check(label("pinned release, through a fixture-local launcher"), () => assert.match(environment.binary, new RegExp(`/claude/versions/${version.replaceAll(".", "\\.")}$`)));
  check(label("every published hook reached Dashpot's publisher, which succeeded"), () => {
    const published = hooks.filter((record) => !record.traceOnly);
    assert(published.length > 50);
    for (const hook of published) assert.equal(hook.publisher.status, 0, `${hook.event}: ${hook.publisher.stderr}`);
  });
  check(label("messaging was isolated from the operator's sessions before any message"), () => {
    const isolation = records.find((record) => record.kind === "isolation");
    for (const key of ["leadSocketPrivate", "noFixtureSocketInShared", "fixtureSessionFilesOnly", "daemonEntryDistinct", "listingFixtureOnly"]) assert.equal(isolation[key], true, key);
    for (const shared of records.filter((record) => record.kind === "shared.directories")) {
      assert.equal(shared.daemon.preexistingKept, true);
      assert.deepEqual(shared.socks.addedByFixture, []);
    }
  });
  check(label("no fixture process outlived the run"), () => assert.deepEqual(records.find((record) => record.kind === "cleanup.remaining").pids, []));

  // Scenario 1: identity.
  check(label("`--bg` prints its short id and name; `agents --json` lists that id with the full session id"), () => {
    const dispatched = requests("lead-dispatch").flatMap((record) => record.results).filter((result) => result.tool === "Bash").map((result) => result.text);
    assert.match(dispatched[0], new RegExp(`^backgrounded · ${ids.a.slice(0, 8)} · worker-a\\n`));
    assert.match(dispatched[1], new RegExp(`backgrounded · ${ids.b.slice(0, 8)} · worker-b\\n`));
    assert.equal(worker("worker-a").id, ids.a.slice(0, 8));
    assert.equal(worker("worker-a").agentKind, "background");
    assert.match(ids.a, /^[0-9a-f-]{36}$/);
  });
  check(label("`--bg` ignores `--session-id`"), () => {
    const text = requests("lead-dispatch").flatMap((record) => record.results).filter((result) => result.tool === "Bash")[1].text;
    assert.match(text, /warning: --bg manages the session id; ignoring --session-id/);
    const requested = environment.sessionIdB;
    if (requested) assert.notEqual(ids.b, requested);
  });
  check(label("`agents --json --cwd <worktree>` lists only that Worktree's Worker, with its full session id"), () => {
    const found = listing("dispatched-cwd-a");
    assert.deepEqual(found.agents.map((entry) => [entry.name, entry.sessionId, entry.cwd]), [["worker-a", ids.a, tree("a")]]);
  });
  check(label("the Lead is listed as an interactive session under its `--name`"), () => {
    assert(listing("worker-a-listed").agents.some((entry) => entry.name === "lead" && entry.kind === "interactive" && entry.sessionId === lead));
  });
  for (const [name, dir, start] of [["a", "a", "wa-start"], ["b", "b", "wb-start"], ["p", "p", "wp-start"], ["q", "q", "wq-start"]]) {
    check(label(`Worker ${name}'s shells and hooks carry its own identity, at its Worktree, never the Lead's`), () => {
      const own = shells(ids[name]);
      assert(own.length > 0);
      const pid = sessionHooks(ids[name], "SessionStart")[0].env.CLAUDE_PID;
      for (const shell of own.filter((record) => record.receipt < (records.find((r) => r.kind === "action.kill")?.receipt ?? Infinity))) {
        assert.equal(shell.env.CLAUDE_PID, pid);
        assert.equal(shell.cwd, tree(dir));
      }
      for (const hook of sessionHooks(ids[name])) assert.equal(hook.payload.cwd, tree(dir));
      assert.notEqual(ids[name], lead);
      assert.equal(command(start).dashpot.status, 0);
      assert.match(command(start).dashpot.stdout, /^started work on issue-\d/);
    });
  }
  check(label("the Lead's own run stays bound at the main checkout after dispatch"), () => {
    assert.match(command("lead-show").dashpot.stdout, /issue-5 \(I_fixture_5\)/);
    assert.equal(command("lead-after-dispatch").cwd, main);
    const run = observation("dispatched").runs.find((entry) => entry.issueId === "I_fixture_5");
    assert.equal(run.workingDirectory, main);
  });

  // Environment and the Lead-link stamp.
  const stamped = (session) => shells(session).find((record) => record.phase === "start").env;
  check(label("every Worker carries the environment of the dispatch that started the supervisor, never its own dispatch's"), () => {
    assert.equal(stamped(ids.z).DASHPOT_479_MARKER, "shell-z");
    for (const name of ["a", "b", "p", "q"]) {
      const env = stamped(ids[name]);
      assert.equal(env.DASHPOT_479_MARKER, "shell-z", name);
      assert.equal(env.DASHPOT_479_TOKEN, "synthetic-shell-z", name);
      assert.equal(env.SPIKE_STAMP, "z", name);
      assert.match(env.DASHPOT_LEAD, /^shell-z:/, name);
    }
  });
  check(label("the Lead process's own environment reaches every Worker through the supervisor; a later Lead's does not"), () => {
    for (const name of ["a", "b", "p", "q"]) assert.equal(stamped(ids[name]).DASHPOT_479_LEAD_ENV_TOKEN, "synthetic-lead-process", name);
    if (ids.s && shells(ids.s).length) {
      assert.equal(stamped(ids.s).DASHPOT_479_LEAD_ENV_TOKEN, "synthetic-lead-process");
      assert.equal(stamped(ids.s).DASHPOT_479_LEAD2_ENV_TOKEN, undefined);
    }
  });
  check(label("a name containing TOKEN is passed on like a neutral one"), () => {
    for (const name of ["a", "b"]) {
      const env = stamped(ids[name]);
      assert.equal(Boolean(env.DASHPOT_479_TOKEN), Boolean(env.DASHPOT_479_MARKER));
    }
  });
  check(label("a `--settings` `env` reaches that Worker's shells and hooks, and only that Worker's"), () => {
    assert.equal(stamped(ids.a).DASHPOT_LEAD_SETTINGS, "settings-a");
    assert.equal(stamped(ids.a).DASHPOT_479_SETTINGS_TOKEN, "synthetic-settings-a");
    assert.equal(stamped(ids.b).DASHPOT_LEAD_SETTINGS, "settings-b");
    assert.equal(stamped(ids.b).DASHPOT_479_SETTINGS_TOKEN, undefined);
    assert.equal(stamped(ids.p).DASHPOT_LEAD_SETTINGS, undefined);
    assert(sessionHooks(ids.a).every((hook) => hook.env.DASHPOT_LEAD_SETTINGS === "settings-a"));
  });
  check(label("the Worker's own identity variables replace the Lead's"), () => {
    for (const name of ["a", "b"]) {
      const env = stamped(ids[name]);
      assert.equal(env.CLAUDE_CODE_SESSION_ID, ids[name]);
      assert.equal(env.CLAUDECODE, "1");
      assert(env.CLAUDE_JOB_DIR.endsWith(`/jobs/${ids[name].slice(0, 8)}`));
      assert.equal(env.CLAUDE_CODE_MESSAGING_SOCKET, `$RUNTIME/cc-socks/${env.CLAUDE_PID}.sock`);
    }
  });

  // Scenario 2: occupancy.
  check(label("bound: each Worker blocks only its own Worktree"), () => {
    const bound = checks("bound");
    assert.deepEqual([...new Set(kinds(bound.a))].filter((kind) => kind !== "dirty"), ["agent-run", "agent-session", "process"]);
    assert(bound.a.blockers.filter((blocker) => blocker.session).every((blocker) => blocker.session === ids.a));
    assert.deepEqual(kinds(bound.b), ["agent-run", "agent-session", "process"]);
    assert(bound.b.blockers.filter((blocker) => blocker.session).every((blocker) => blocker.session === ids.b));
    assert.equal(bound.c.removable, true);
  });
  check(label("a Worker's running reviewer Sub-agent blocks every Worktree, then only while it runs"), () => {
    const running = checks("reviewer-running");
    for (const name of ["b", "c"]) assert(running[name].blockers.some((blocker) => blocker.kind === "sub-agent" && blocker.detail.includes(ids.a)), name);
    const finished = checks("reviewer-finished");
    assert.equal(finished.c.removable, true);
    assert(!finished.b.blockers.some((blocker) => blocker.kind === "sub-agent"));
  });
  check(label("after `work stop`, a live finished Worker still blocks its Worktree by Agent Session and process, not by run"), () => {
    const stopped = checks("a-work-stopped");
    assert.equal(command("wa-stop").dashpot.status, 0);
    assert(kinds(stopped.a).includes("agent-session"));
    assert(kinds(stopped.a).includes("process"));
    assert(!kinds(stopped.a).includes("agent-run"));
  });
  check(label("after `claude stop`, no session or process blocks the Worktree"), () => {
    const stopped = checks("a-stopped");
    assert(!kinds(stopped.a).some((kind) => ["agent-session", "agent-run", "process", "sub-agent"].includes(kind)), JSON.stringify(kinds(stopped.a)));
  });

  // Scenario 3: Worker to Lead.
  const arrival = (name) => requests(name).find((record) => record.step === 0)?.arrivals.find((entry) => entry.labels.includes(name));
  check(label("a message by name wakes an idle -p Lead with a new turn, framed with the sender's name and mode"), () => {
    const framed = arrival("lead-hears-a-name");
    assert(framed.tags.includes("cross-session-message"));
    assert.equal(framed.attributes[0]["from-name"], "worker-a");
    assert.equal(framed.attributes[0]["from-mode"], "bypass");
    assert(command("lead-on-a-name"));
  });
  // A message that reaches a session mid-turn waits for the running tool
  // call, is submitted (UserPromptSubmit) without a Stop, and arrives in the
  // same turn's next request as a `system`-role message after the tool result.
  const midTurn = (session, holdLabel, messageLabel) => {
    const hold = command(holdLabel);
    const prompt = hooks.find((record) => record.event === "UserPromptSubmit" && record.payload.session_id === session && record.prompt?.labels.includes(messageLabel));
    assert(prompt, "the queued message is submitted");
    assert(prompt.receipt > hold.receipt, "after the tool call ends");
    const request = requests(messageLabel).find((record) => record.step === 0);
    assert(request, "a request carries it");
    const position = request.labelPositions.find((entry) => entry.label === messageLabel);
    assert.equal(position.role, "system");
    assert.equal(position.index, request.messageCount - 1);
    assert.deepEqual(request.freshParts[0], ["tool_result"]);
    assert(!sessionHooks(session, "Stop").some((stop) => stop.receipt > hold.receipt && stop.receipt < request.receipt), "no Stop in between");
  };
  check(label("a message by `uds:` address to a busy Lead lands inside its running turn, after the tool call"), () => {
    midTurn(lead, "lead-busy", "lead-hears-b-uds");
    assert(command("lead-on-b-uds"));
  });
  check(label("`notify_when_idle` subscribes, and the notice starts a Lead turn after the Worker's Stop"), () => {
    const response = hooks.find((record) => record.event === "PostToolUse" && record.toolTarget?.notifyWhenIdle === true);
    assert.match(response.toolResponse, /Subscribed/);
    const probe = records.find((record) => record.kind === "probe" && record.label === "notify");
    const bStop = probe.bStops.at(-1);
    assert(probe.leadPrompts.some((time) => time > bStop));
  });
  check(label("a mid-turn message to a Worker lands inside its running turn"), () => {
    midTurn(ids.b, "wb-steer-hold", "wb-mid");
    assert(command("wb-mid-seen"));
  });

  // Scenario 6: permission classes.
  check(label("a prompting Worker holds a bypassing Lead's message, waiting for approval, and lists as blocked"), () => {
    assert(hooks.some((record) => record.event === "Notification" && record.payload.session_id === ids.p && /message from another session needs your approval/.test(record.notification)));
    assert(!command("wp-on-msg"));
    const entry = listing("lead-to-asking").agents.find((agent) => agent.name === "worker-p");
    assert.deepEqual([entry.status, entry.state, entry.waitingFor], ["waiting", "blocked", "permission prompt"]);
  });
  check(label("a bypassing -p Lead holds a prompting Worker's message and drops it when the deadline passes"), () => {
    const holds = records.filter((record) => record.kind === "lead.stream" && record.lead === "lead" && record.subtype === "peer_message_hold" && record.fields.from_name === "worker-p");
    assert.deepEqual(holds[0].fields, { state: "held", lane: "socket", from_name: "worker-p", cause: "mode-mismatch" });
    assert(!command("lead-on-p"));
    const dropped = holds.find((record) => record.fields.state === "dropped");
    assert(dropped);
    assert(dropped.receiptTime - holds[0].receiptTime >= 295000, `dropped after ${dropped.receiptTime - holds[0].receiptTime} ms`);
  });
  check(label("a sender is told its message is held"), () => {
    assert(records.some((record) => record.kind === "lead.stream" && record.subtype === "informational" && /^Cross-session message held (for approval|by the receiving session)/.test(record.notice)));
  });
  check(label("a sender's model gets an unlabelled notice turn when its message is held, and the Worker another when it expires"), () => {
    const notices = (session) => sessionHooks(session, "UserPromptSubmit").filter((record) => record.prompt && record.prompt.labels.length === 0);
    const holds = records.filter((record) => record.kind === "lead.stream" && record.lead === "lead" && record.subtype === "peer_message_hold" && record.fields.from_name === "worker-p");
    const dropped = holds.find((record) => record.fields.state === "dropped");
    const pNotices = notices(ids.p);
    assert(pNotices.some((record) => record.receipt > holds[0].receipt && record.receipt < dropped.receipt));
    assert(pNotices.some((record) => record.receipt > dropped.receipt));
    for (const informational of records.filter((record) => record.kind === "lead.stream" && record.lead === "lead" && record.subtype === "informational")) {
      assert(notices(lead).some((record) => record.receipt > informational.receipt && record.receipt <= informational.receipt + 3));
    }
  });
  check(label("a Worker blocked on an ask lists as waiting for a permission prompt, while Dashpot reports its run running"), () => {
    assert(hooks.some((record) => record.event === "PermissionRequest" && record.payload.session_id === ids.q));
    const entry = listing("asking-workers").agents.find((agent) => agent.name === "worker-q");
    assert.deepEqual([entry.status, entry.state, entry.waitingFor], ["waiting", "blocked", "permission prompt"]);
    const run = observation("asking-workers").runs.find((entry) => entry.issueId === "I_fixture_4");
    assert.equal(run.state, "running");
  });
  check(label("within the prompting class (dontAsk Lead, dontAsk Worker) messages deliver both ways without a hold"), () => {
    const framed = arrival("lead2-hears-s");
    assert.equal(framed.attributes[0]["from-mode"], "prompting");
    assert(command("lead2-on-s"));
    assert.equal(arrival("ws-msg").attributes[0]["from-mode"], "prompting");
    assert(command("ws-on-msg"));
  });
  check(label("a dontAsk Worker holds a bypassing Lead's message"), () => {
    assert(hooks.some((record) => record.event === "Notification" && record.payload.session_id === ids.s && /needs your approval/.test(record.notification)));
    assert(!command("ws-on-lead"));
  });
  check(label("an auto-mode Worker whose classifier cannot answer blocks its tools and then asks"), () => {
    const results = requests("wr-start").flatMap((record) => record.results);
    assert(results.some((result) => result.tool === "SendMessage" && /Auto mode could not evaluate this action/.test(result.text)));
    assert(hooks.some((record) => record.event === "PermissionRequest" && record.payload.session_id === ids.r));
  });
  check(label("a Lead whose added directories hold the Worktree moves into it with `cd <worktree> && claude --bg`"), () => {
    const stops = sessionHooks(lead2, "Stop");
    assert.equal(stops[0].payload.cwd, main);
    assert.equal(stops.at(-1).payload.cwd, tree("s"));
    assert.equal(command("lead2-on-s", "start").cwd, tree("s"));
  });
  check(label("a Lead without them stays put"), () => {
    assert(sessionHooks(lead, "Stop").every((hook) => hook.payload.cwd === main));
  });

  // Scenario 7: the commit instruction.
  check(label("a Worker's system prompt has the Background Session section with EnterWorktree, and the ask-before-committing line unless bgIsolation is none"), () => {
    const first = (name) => requests(name).find((record) => record.system).system;
    assert.equal(first("wa-start").backgroundSession, true);
    assert.equal(first("wa-start").sectionMentionsEnterWorktree, true);
    assert.equal(first("wa-start").askBeforeCommitting, true);
    assert.equal(first("wb-start").backgroundSession, true);
    assert.equal(first("wb-start").askBeforeCommitting, false);
    assert.equal(first("lead-identify").backgroundSession, false);
  });
  check(label("a bypassing Worker commits in its Worktree with no permission ask"), () => {
    const commits = records.find((record) => record.kind === "commits");
    assert.equal(commits.a[0], "Fixture commit");
    assert(!commits.asks.some(([, own]) => own));
  });
  check(label("a Worker's Stop carries last_assistant_message"), () => {
    const stops = sessionHooks(ids.a, "Stop");
    assert(stops.length > 0);
    for (const stop of stops) assert.equal(stop.lastAssistantMessage?.type, "string");
  });

  // Scenario 5: stop and respawn.
  check(label("`claude stop` publishes SessionEnd with reason other"), () => {
    assert.deepEqual(records.find((record) => record.kind === "worker.stop").hooks, [["SessionEnd", "other"]]);
  });
  check(label("SIGTERM ends the Worker's process, and the supervisor resumes the same session in a new process"), () => {
    const term = records.find((record) => record.kind === "worker.term");
    assert.equal(term.hooks[0][0], "SessionEnd");
    assert.equal(term.hooks[0][1], "other");
    const resumed = term.hooks.find(([event, source]) => event === "SessionStart" && source === "resume");
    assert(resumed);
    assert.notEqual(resumed[2], String(term.pid));
  });
  check(label("the respawned Worker's shells carry the same session id and supervisor environment"), () => {
    const env = command("wb-resumed-shell", "start").env;
    assert.equal(env.CLAUDE_CODE_SESSION_ID, ids.b);
    assert.equal(env.DASHPOT_479_MARKER, "shell-z");
    assert.equal(env.DASHPOT_LEAD_SETTINGS, "settings-b");
  });
  check(label("the killed process's SessionEnd ends the Worker's run, so the respawned Worker has no Issue Binding to continue"), () => {
    assert.match(command("wb-resumed-show").dashpot.stdout, /^no active Issue work at this worktree/);
    for (const name of ["b-terminated", "b-resumed-turn"]) {
      const runs = observation(name).runs;
      assert(!runs.some((run) => run.issueId === "I_fixture_2"), name);
      assert(runs.some((run) => run.processOrSession.startsWith(ids.b) && run.issueId === null && run.workingDirectory === tree("b")), name);
    }
    assert.deepEqual(kinds(checks("b-resumed-turn").b), ["agent-session", "process"]);
  });
  check(label("Dashpot warns that the moved Lead's work is recorded elsewhere"), () => {
    const warning = observation("prompting").diagnostics.find((item) => item.code === "work-session-elsewhere");
    assert.match(warning.message, /executing at \$ROOT\/repository\.worktrees\/s .* issue-8 .* recorded at \$ROOT\/repository;/);
  });
  check(label("a background Worker still holds the Lead's message past the five-minute deadline"), () => {
    const probe = records.find((record) => record.kind === "probe" && record.label === "worker-hold-deadline");
    assert(probe.heldForMs >= 330000);
    assert.equal(probe.delivered, false);
    const entry = listing("after-hold-deadline").agents.find((agent) => agent.name === "worker-p");
    assert.deepEqual([entry.status, entry.state, entry.waitingFor], ["waiting", "blocked", "permission prompt"]);
  });
  return passed.length;
};

for (const file of process.argv.slice(2)) verify(load(file), file);
for (const claim of passed) console.log(`ok - ${claim}`);
console.log(`${passed.length} claims verified`);
