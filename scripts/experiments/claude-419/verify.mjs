// Independent verifier for the Issue #419 worker-mechanics trace: checks each
// claim docs/spikes/claude-code-worker-mechanics-spike.md makes about a Claude
// Code lead and its background sub-agent workers against the recorded hook,
// shell, model-request, stream and observation evidence, and that the trace
// came from the runner retained beside this file.
//
// Usage: node verify.mjs <trace.jsonl> [--strict]
//
// The Dashpot sources the trace hashes keep changing after the run, so a
// difference from this checkout is reported, and fails only under --strict.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [file] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(file, "Pass the trace to verify");
const records = readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => {
  try { test(); } catch (error) { console.error(`not ok - ${claim}`); throw error; }
  checks.push(claim);
};
const main = "$ROOT/repository";
const sibling = "$ROOT/repository.worktrees/sibling";
const pinned = "2.1.287";

const of = (kind) => records.filter((record) => record.kind === kind);
const hooks = of("hook");
const requests = of("model.request");
const command = (label, phase = "end") => {
  const found = records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
  assert(found, `command ${label} ${phase}`);
  return found;
};
const ran = (label) => records.some((record) => record.kind === "command" && record.label === label && record.phase === "end");
const observation = (label) => {
  const found = records.find((record) => record.kind === "observation" && record.label === label);
  assert(found, `observation ${label}`);
  assert.equal(found.error, null, `${label}: ${found.error}`);
  return found;
};
const obstacles = (label) => (observation(label).check.obstacles ?? []).map((obstacle) => obstacle.kind);
const runs = (label) => observation(label).runs.map((run) => [run.issueId, run.state, run.observationTarget]);
const wait = (label) => {
  const found = records.find((record) => record.kind === "wait" && record.label === label);
  assert(found, `wait ${label}`);
  return found.met;
};
const one = (kind, predicate) => {
  const found = records.find((record) => record.kind === kind && predicate(record));
  assert(found, `${kind} record`);
  return found;
};
const request = (label, step) => {
  const found = requests.find((record) => record.label === label && record.step === step);
  assert(found, `model request ${label} step ${step}`);
  return found;
};
const outcome = (label, tool) => {
  const found = requests.filter((record) => record.label === label).flatMap((record) => record.outcomes ?? []).find((item) => item.tool === tool);
  assert(found, `${tool} outcome in ${label}`);
  return found;
};
const deliveries = (label) => requests.filter((record) => record.label === label).flatMap((record) => record.deliveries ?? []);
const notifications = (conversation) => requests.filter((record) => record.conversation === conversation)
  .flatMap((record) => record.deliveries ?? []).filter((item) => item.notification).map((item) => item.notification);
const session = (label) => command(label, "start").env.CLAUDE_CODE_SESSION_ID;
const events = (sessionId, event, agent) => hooks.filter((record) => record.payload.session_id === sessionId && record.event === event
  && (agent === undefined || (record.payload.agent_id ?? null) === agent));
const agentOf = (label) => outcome(label, "Agent").text.match(/agentId: (a[0-9a-f]+)/)?.[1];
const streams = (client) => of("client.stream").filter((record) => record.client === client);

// The run itself.
const environment = records[0];
check("the trace is of the pinned Claude Code release", () => {
  assert.equal(environment.kind, "environment");
  assert.equal(environment.version, `${pinned} (Claude Code)`);
});
check("the trace came from the runner, hook and command retained beside this verifier", () => {
  for (const name of ["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"]) {
    assert.equal(environment.sourceSHA256[name], createHash("sha256").update(readFileSync(path.join(here, name))).digest("hex"), name);
  }
});
check("hooks are subscribed as `dashpot integrate claude-code` subscribes them", () => assert.deepEqual(environment.subscriptions, {
  events: ["SessionStart", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "SessionEnd"],
  matched: [["PostToolUse", "EnterWorktree"], ["PostToolUse", "ExitWorktree"]],
}));
check("skills come from the directory `integrate` installs into, the home's `.claude/skills`", () => {
  assert.equal(environment.skillsDirectory, "$ROOT/home/.claude/skills");
  assert.equal(environment.flags.CLAUDE_CONFIG_DIR, "$ROOT/home/.claude");
});
check("the Agent tool has no name parameter and launches in the background by default", () => {
  const schema = requests.find((record) => record.agentSchema).agentSchema;
  assert.deepEqual(schema.parameters, ["description", "prompt", "subagent_type", "model", "run_in_background", "isolation"]);
  assert.match(schema.runInBackground, /^Agents run in the background by default/);
});
check("every scenario ran to its end", () => {
  const ends = of("scenario.end");
  assert.deepEqual(ends.map((record) => record.name), environment.scenarios);
  for (const end of ends) assert.equal(end.ok, true, `${end.name}: ${end.error}`);
});
check("every hook reached the real publisher, which succeeded", () => {
  assert(hooks.length > 100);
  for (const hook of hooks) assert.equal(hook.publisher.status, 0, `${hook.event}: ${hook.publisher.stderr}`);
});
check("no fixture process outlived the run", () => assert.deepEqual(one("cleanup.remaining", () => true).pids, []));

// The three launch modes of the core arc: headless stream-json, `-p`, and
// an interactive terminal.
for (const p of ["h", "p", "i"]) {
  const lead = session(`${p}-w-start`);
  const worker = agentOf(`${p}-lead`);

  // 1. Launch.
  check(`${p}: Agent returns at once with the worker's agentId, and the lead's turn goes on`, () => {
    assert.match(outcome(`${p}-lead`, "Agent").text, /^Async agent launched successfully\./);
    assert.match(worker, /^a[0-9a-f]{16}$/);
    assert.deepEqual(events(lead, "SubagentStart").map((record) => record.payload.agent_id)[0], worker);
    // The lead's next shell ran and its turn stopped while the worker was held at its gate.
    const held = command(`${p}-w-start`).receipt;
    assert(command(`${p}-lead-after-dispatch`).receipt < held);
    assert(events(lead, "Stop", null)[0].receipt < held);
  });

  // 2. Mid-flight report.
  check(`${p}: a worker's SendMessage to "main" is queued and the worker goes on`, () => {
    assert.match(outcome(`${p}-worker`, "SendMessage").text, /^\{"success":true,"message":"Message queued for the main conversation's next turn\."\}$/);
    const sent = requests.find((record) => record.label === `${p}-worker` && (record.outcomes ?? []).some((item) => item.tool === "SendMessage"));
    assert(sent.receipt < command(`${p}-w-cd`, "start").receipt);
    assert(command(`${p}-w-cd`).receipt < events(lead, "SubagentStop", worker)[0].receipt);
  });
  check(`${p}: an idle lead gets the report as a new turn wrapped as an agent-message`, () => {
    const [report] = deliveries(`${p}-lead-on-report`).filter((item) => item.agentMessage);
    assert.equal(report.agentMessage, worker);
    assert.deepEqual(report.marks, [`${p}-report`]);
    assert.equal(report.withToolResult, false);
    assert.match(report.head, /^Another Claude session sent a message:\n<agent-message from="/);
    const prompt = events(lead, "UserPromptSubmit", null).find((record) => record.prompt.labels.includes(`${p}-lead-on-report`));
    assert.equal(prompt.prompt.agentMessage, true);
    assert(ran(`${p}-lead-got-report`));
  });
  check(`${p}: the lead's message to a running worker lands at the worker's next tool round`, () => {
    assert.match(outcome(`${p}-lead-on-report`, "SendMessage").text, new RegExp(`^\\{"success":true,"message":"Message queued for delivery to ${worker} at its next tool round\\."`));
    // It arrives as a message of its own between two of the worker's tool
    // calls, inside the worker's running turn.
    const carrying = requests.find((record) => record.label === `${p}-worker` && (record.deliveries ?? []).some((item) => item.marks.includes(`${p}-broadcast`)));
    assert(carrying.step > 0);
    const broadcast = carrying.deliveries.find((item) => item.marks.includes(`${p}-broadcast`));
    assert.equal(broadcast.withToolResult, false);
    assert.match(broadcast.head, /^The coordinator sent a message while you were working:/);
  });

  // 3. Completion.
  check(`${p}: a finished worker fires SubagentStop, and the idle lead wakes with a completed task-notification carrying its final message`, () => {
    assert(events(lead, "SubagentStop", worker).length >= 1);
    const [done] = deliveries(`${p}-lead-on-done`).filter((item) => item.notification);
    // The worker's whole final message is the label and mark, well inside
    // what the trace keeps of a result.
    assert.deepEqual(done.notification, {
      taskId: worker, status: "completed", summary: `Agent "Fixture ${p}-worker" finished`,
      result: `SPIKE:${p}-lead-on-done MARK:${p}-final`, outputFile: true,
    });
    assert(ran(`${p}-lead-got-done`));
  });

  // 4. Resume.
  check(`${p}: SendMessage to a finished worker's agentId resumes it with its transcript under the same agent_id`, () => {
    assert.match(outcome(`${p}-lead-on-done`, "SendMessage").text, new RegExp(`^\\{"success":true,"message":"Resuming agent ${worker.slice(0, 7)}","resumedAgentId":"${worker}"`));
    assert.equal(events(lead, "SubagentStart", worker).length, 2);
    const before = Math.max(...requests.filter((record) => record.label === `${p}-worker`).map((record) => record.messages));
    assert(request(`${p}-worker-resume`, 0).messages > before);
    assert.equal(request(`${p}-worker-resume`, 0).conversation, `${p}-worker`);
    const [resumed] = deliveries(`${p}-worker-resume`).filter((item) => item.marks.includes(`${p}-resume`));
    assert.match(resumed.head, new RegExp(`^The coordinator sent a message while you were working:\nSPIKE:${p}-worker-resume MARK:${p}-resume`));
    assert(ran(`${p}-w-resumed`));
    const [again] = deliveries(`${p}-lead-on-resumed`).filter((item) => item.notification);
    assert.equal(again.notification.status, "completed");
    assert.equal(again.notification.taskId, worker);
    assert(ran(`${p}-lead-got-resumed`));
  });

  // 5. One Agent Session.
  check(`${p}: a worker's shell carries the lead's session id and \`work show\` reports the lead's run`, () => {
    for (const label of [`${p}-w-start`, `${p}-w-show`, `${p}-w-cd`, `${p}-w-after-hold`]) assert.equal(command(label).env.CLAUDE_CODE_SESSION_ID, lead, label);
    const pid = command(`${p}-lead-start`).env.CLAUDE_PID;
    assert.equal(command(`${p}-w-start`).env.CLAUDE_PID, pid);
    // The worker's shell is a child of the lead's own process.
    const [shell, parent] = command(`${p}-w-start`).ancestry;
    assert.equal(shell.ppid, Number(pid));
    assert.equal(parent.pid, Number(pid));
    assert.equal(command(`${p}-w-show`).dashpot.status, 0);
    assert.match(command(`${p}-w-show`).dashpot.stdout, new RegExp(`^claude-code pid ${pid}: issue-${{ h: 1, p: 4, i: 6 }[p]} `));
    assert.match(command(`${p}-w-show`).dashpot.stdout, new RegExp(`has 1 sub-agent listed as working \\(${worker}\\)`));
  });
  check(`${p}: a worker's \`work start\` from the sibling Worktree is refused as running where the session is not`, () => {
    const refused = command(`${p}-w-start-sibling`);
    assert.equal(refused.cwd, sibling);
    assert.equal(refused.dashpot.status, 2);
    assert.match(refused.dashpot.stderr, /according to its freshest Claude Code hook record, not at/);
  });
  check(`${p}: the lead reads running while its worker lives, with the sub-agent blocker on the sibling, and both clear after SubagentStop`, () => {
    const issue = `I_fixture_${{ h: 1, p: 4, i: 6 }[p]}`;
    assert.deepEqual(runs(`${p}-lead-idle-worker-live`), [[issue, "running", main]]);
    // Read after the lead's own turn stopped, before the worker's SubagentStop.
    const live = observation(`${p}-lead-idle-worker-live`).receipt;
    assert(events(lead, "Stop", null)[0].receipt < live);
    assert(live < events(lead, "SubagentStop", worker)[0].receipt);
    assert.deepEqual(obstacles(`${p}-lead-idle-worker-live`), ["sub-agent"]);
    assert.deepEqual(obstacles(`${p}-worker-holding`), ["sub-agent"]);
    assert.deepEqual(obstacles(`${p}-arc-done`), []);
    // A `-p` lead has already exited by then, ending its run.
    assert.deepEqual(runs(`${p}-arc-done`), p === "p" ? [] : [[{ h: "I_fixture_3", i: issue }[p], "waiting", main]]);
  });

  // 6. Location.
  check(`${p}: a worker's shell starts in the lead's directory and a \`cd\` holds only for its own command`, () => {
    assert.equal(command(`${p}-w-start`).cwd, main);
    assert.equal(command(`${p}-w-cd`).cwd, sibling);
    assert.equal(command(`${p}-w-after-hold`).cwd, main);
  });
}
check("h: a worker's `work start` where the lead is switches the whole session's Issue work", () => {
  const switched = command("h-w-start-main");
  assert.equal(switched.dashpot.status, 0);
  assert.match(switched.dashpot.stdout, /switched from issue-1 .*to issue-3/s);
});
check("headless and `-p` hosts see the task lifecycle on the SDK stream", () => {
  for (const client of ["h", "p"]) {
    const kinds = new Set(streams(client).map((record) => `${record.type}/${record.subtype}`));
    for (const kind of ["system/task_started", "system/task_progress", "system/task_updated", "system/task_notification"]) assert(kinds.has(kind), `${client} ${kind}`);
  }
});
check("`-p` stays up for its background worker, lets the lead handle the completions, then exits", () => {
  const exit = one("client.exit", (record) => record.name === "p");
  assert.equal(exit.status, 0);
  assert(exit.receipt > command("p-lead-got-resumed").receipt);
  assert.deepEqual(events(session("p-w-start"), "SessionEnd", null).map((record) => record.payload.reason), ["other"]);
  assert.equal(wait("p exit after the arc"), true);
});

// 1. Concurrency.
check("three parallel Agents run at once under the default cap", () => {
  assert.deepEqual(request("cd-lead", 0).tools, ["Agent", "Agent", "Agent"]);
  assert.deepEqual(one("concurrency", (record) => record.client === "cd").holding, ["w1", "w2", "w3"]);
});
check("past CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS the Agent call fails and says not to retry", () => {
  assert.equal(one("concurrency", (record) => record.client === "c2").holding.length, 2);
  const refused = requests.filter((record) => record.label === "c2-lead").flatMap((record) => record.outcomes ?? []).find((item) => item.isError);
  assert.match(refused.text, /^Concurrent subagent limit reached\. You can run 2 subagents at once\. Do not retry\./);
});

// 2. A report and a completion to a lead in a tool call.
for (const p of ["h", "i"]) {
  check(`${p}: a busy lead gets the report and the completion together at its next tool round, not as a new turn`, () => {
    // One message after the held tool's result carries both, and each fires
    // UserPromptSubmit although no turn starts.
    const carrying = requests.filter((record) => record.label === `${p}-busy-lead` && record.deliveries);
    assert.equal(carrying.length, 1);
    assert.equal(carrying[0].step, 2);
    const [both] = carrying[0].deliveries;
    assert.equal(both.withToolResult, false);
    assert.equal(both.role, "system");
    assert.deepEqual(both.marks, [`${p}-busy-report`, `${p}-busy-final`]);
    assert.match(both.head, /^Another Claude session sent a message while you were working:/);
    assert.equal(both.notification.status, "completed");
    const prompts = one("busy.after", (record) => record.client === p).hooks.map((record) => record.event === "UserPromptSubmit"
      ? `${record.prompt.agentMessage ? "agent-message" : ""}${record.prompt.taskNotification ? "task-notification" : ""}` : record.event);
    assert.deepEqual(prompts, ["agent-message", "task-notification", "Stop"]);
    assert(ran(`${p}-busy-lead-after`));
    // The lead's turn stopped once, after its last step.
    const lead = session(`${p}-busy-lead-hold`);
    const stops = events(lead, "Stop", null);
    assert.equal(stops.length, 1);
    assert(stops[0].receipt > command(`${p}-busy-lead-after`).receipt);
  });
}

// 6. EnterWorktree from a worker.
check("a worker's EnterWorktree by path is refused while the session is at the repository root", () => {
  const entered = outcome("en-worker", "EnterWorktree");
  assert.equal(entered.isError, true);
  assert.match(entered.text, /^Cannot enter worktree: the current working directory \$ROOT\/repository is the repository root, not an isolated worktree/);
});
check("a worker's EnterWorktree by name and ExitWorktree are refused as mutating the parent's working directory", () => {
  assert.match(outcome("em-worker", "EnterWorktree").text, /EnterWorktree cannot create a worktree from a subagent with a cwd override .* it would mutate the parent session's process-wide working directory/);
  const exited = outcome("en-worker", "ExitWorktree");
  assert.equal(exited.input.action, "keep");
  assert.equal(exited.isError, true);
  assert.match(exited.text, /ExitWorktree cannot be called from a subagent with a cwd override/);
});
check("the lead's location and run are unchanged by its worker's worktree tools", () => {
  assert.equal(command("en-w-after-enter").cwd, main);
  assert.equal(command("en-lead-cwd").cwd, main);
  assert.match(command("en-lead-show").dashpot.stdout, /issue-8 /);
  assert.deepEqual(runs("en-lead-checked"), [["I_fixture_8", "waiting", main]]);
  assert.deepEqual(runs("em-lead-checked"), [["I_fixture_9", "waiting", main]]);
});

// 7. Interruption.
check("a headless SDK interrupt stops the running worker without a SubagentStop, and the SDK host alone hears of it", () => {
  const lead = session("h-int-lead-hold");
  const worker = agentOf("h-int-lead");
  const after = one("interrupt.after", (record) => record.client === "h");
  assert.equal(after.workerHoldAlive, false);
  assert.equal(after.leadHoldAlive, false);
  assert.deepEqual(after.hooks, []);
  assert(streams("hi").some((record) => record.subtype === "task_notification" && record.status === "stopped" && record.taskId === worker));
  assert(streams("hi").some((record) => record.type === "result" && record.subtype === "error_during_execution"));
  assert.equal(events(lead, "SubagentStop").length, 0);
  assert.equal(wait("h worker continued after the interrupt"), false);
  assert.equal(wait("h lead woke on the worker's completion"), false);
  // The lead's next turn is told only that its own tool call was interrupted.
  assert.deepEqual(notifications("h-int-lead"), []);
  const told = deliveries("h-int-after").filter((item) => item.interrupted);
  assert.equal(told.length, 1);
  assert.equal(told[0].head, "[Request interrupted by user for tool use]\n");
});
check("after a headless interrupt Dashpot keeps the run running and the sub-agent blocker until SessionEnd clears both", () => {
  for (const label of ["h-int-interrupted", "h-int-done", "h-int-after"]) {
    assert.deepEqual(obstacles(label), ["sub-agent"], label);
    assert.equal(runs(label)[0][1], "running", label);
  }
  const detail = observation("h-int-after").check.obstacles[0].detail;
  assert.match(detail, /Dashpot lists a sub-agent until Claude Code reports that it stopped, which an interrupted one may never do, so if none is still working, end that session\.$/);
  assert.equal(one("ended", (record) => record.client === "hi").hooks.map((record) => `${record.event}:${record.reason}`).join(), "SessionEnd:other");
  assert.deepEqual(runs("h-int-ended"), []);
  assert.deepEqual(obstacles("h-int-ended"), []);
});
check("an interactive Esc interrupts the lead's tool only: the worker finishes and the lead wakes on its completion", () => {
  const after = one("interrupt.after", (record) => record.client === "i");
  assert.equal(after.leadHoldAlive, false);
  assert.equal(after.workerHoldAlive, true);
  assert.equal(wait("i worker continued after the interrupt"), true);
  assert.equal(events(session("i-int-lead-hold"), "SubagentStop", agentOf("i-int-lead")).length, 1);
  assert.equal(notifications("i-int-lead")[0].status, "completed");
  assert.deepEqual(obstacles("i-int-done"), []);
});
for (const p of ["h", "i"]) {
  check(`${p}: a lead's TaskStop stops its worker, then a new turn tells the lead it was killed, with no SubagentStop`, () => {
    const lead = session(`${p}-ts-w-hold`);
    const worker = agentOf(`${p}-ts-lead`);
    assert.match(outcome(`${p}-ts-stop`, "TaskStop").text, new RegExp(`Successfully stopped task: ${worker} \\(Fixture ${p}-ts-worker\\)`));
    assert.equal(one("taskstop.after", (record) => record.client === p).workerHoldAlive, false);
    assert.equal(wait(`${p} worker continued after TaskStop`), false);
    const [killed] = notifications(`${p}-ts-lead`);
    assert.deepEqual(killed, { taskId: worker, status: "killed", summary: `Agent "Fixture ${p}-ts-worker" was stopped by Claude`, outputFile: true });
    assert.equal(events(lead, "SubagentStop").length, 0);
  });
  check(`${p}: after TaskStop Dashpot keeps the sub-agent blocker and running until SessionEnd clears both`, () => {
    for (const label of [`${p}-ts-stopped`, `${p}-ts-after`]) {
      assert.deepEqual(obstacles(label), ["sub-agent"], label);
      assert.equal(runs(label)[0][1], "running", label);
    }
    const end = one("ended", (record) => record.client === `${p}ts`).hooks.map((record) => `${record.event}:${record.reason}`);
    assert.deepEqual(end, [p === "h" ? "SessionEnd:other" : "SessionEnd:prompt_input_exit"]);
    assert.deepEqual(runs(`${p}-ts-ended`), []);
    assert.deepEqual(obstacles(`${p}-ts-ended`), []);
  });
}

// 7. Session end.
const ended = (p) => one("end.after", (record) => record.client === p);
const endHooks = (p) => ended(p).hooks.map((record) => `${record.event}:${record.reason}`);
check("headless: closing stdin waits for the running worker, which the lead then hears finish", () => {
  assert.equal(ended("h").workerHoldAlive, true);
  assert.equal(ended("h").clientAlive, true);
  assert.equal(wait("h worker continued after its lead ended"), true);
  const final = one("end.final", (record) => record.client === "h");
  assert.deepEqual(final.hooks.map((record) => record.event === "UserPromptSubmit" && record.prompt.taskNotification ? "task-notification" : `${record.event}${record.reason ? `:${record.reason}` : ""}`),
    ["SubagentStop", "task-notification", "Stop", "SessionEnd:other"]);
  assert.equal(final.clientAlive, false);
  assert.equal(notifications("h-end-lead")[0].status, "completed");
  assert.deepEqual(runs("h-end-final"), []);
  assert.deepEqual(obstacles("h-end-final"), []);
});
check("interactive `/exit` with a running worker opens a dialog and leaves the session up, and the blocker clears on SubagentStop", () => {
  assert.match(one("screen", (record) => record.label === "i-after-end").tail, /Background work is running.*1\. Exit and stop tasks 2\. Move to background and exit 3\. Stay/);
  assert.equal(ended("i").clientAlive, true);
  assert.deepEqual(endHooks("i"), []);
  // The worker finished once released, and the unanswered dialog kept the session up.
  assert.equal(wait("i worker continued after its lead ended"), true);
  const final = one("end.final", (record) => record.client === "i");
  assert.deepEqual(final.hooks.map((record) => record.event), ["SubagentStop"]);
  assert.equal(final.clientAlive, true);
  assert.equal(wait("i exit once the worker was released"), false);
  assert.deepEqual(obstacles("i-end-final"), []);
});
check("\"Exit and stop tasks\" kills the worker and ends the session, and Dashpot clears the run and blocker", () => {
  assert.deepEqual(endHooks("ix"), ["SessionEnd:prompt_input_exit"]);
  assert.equal(ended("ix").workerHoldAlive, false);
  assert.equal(wait("ix worker continued after its lead ended"), false);
  assert.deepEqual(runs("ix-end-ended"), []);
  assert.deepEqual(obstacles("ix-end-ended"), []);
});
check("\"Move to background and exit\" forks a new unbound session, ends the bound one and kills the worker", () => {
  const original = session("iy-end-w-hold");
  assert.equal(command("iy-end-lead-start").dashpot.status, 0);
  assert.deepEqual(runs("iy-end-worker-live"), [["I_fixture_10", "running", main]]);
  assert.deepEqual(endHooks("iy"), ["SessionEnd:prompt_input_exit"]);
  const fork = hooks.find((record) => record.event === "SessionStart" && record.payload.source === "fork");
  assert(fork && fork.payload.session_id !== original);
  assert.equal(ended("iy").workerHoldAlive, false);
  assert(ended("iy").processes.some((entry) => /daemon run --origin transient/.test(entry.cmdline)));
  assert(ended("iy").processes.some((entry) => entry.cmdline.includes(`--session-id ${fork.payload.session_id} --fork-session --resume`)));
  assert.equal(wait("iy worker continued after its lead ended"), false);
  // The fork is observed as its own session, holding no Issue work.
  assert.deepEqual(runs("iy-end-ended"), [[null, "running", main]]);
  assert(observation("iy-end-ended").runs[0].processOrSession.startsWith(fork.payload.session_id));
  assert(!observation("iy-end-ended").stateFiles[main].some((name) => name.startsWith("work/")));
  const shown = command("iy-fork-show");
  assert.equal(shown.env.CLAUDE_CODE_SESSION_ID, fork.payload.session_id);
  assert.match(shown.dashpot.stdout, /^no active Issue work at this worktree/);
  const [failed] = deliveries("iy-fork-show").filter((item) => item.notification);
  assert.equal(failed.notification.status, "failed");
  assert.match(failed.notification.summary, /didn't finish before the previous session ended$/);
});
check("closing the terminal ends the session as `other`, kills the worker, and Dashpot clears the run and blocker", () => {
  assert.deepEqual(endHooks("ic"), ["SessionEnd:other"]);
  assert.equal(ended("ic").workerHoldAlive, false);
  assert.deepEqual(runs("ic-end-ended"), []);
  assert.deepEqual(obstacles("ic-end-ended"), []);
});
for (const [p, verb] of [["bs", "stop"], ["br", "rm"]]) {
  check(`\`claude ${verb}\` on a \`--bg\` lead ends it as \`other\` and kills the worker, and Dashpot clears the run and blocker`, () => {
    assert.deepEqual(obstacles(`${p}-end-worker-live`), ["sub-agent"]);
    assert.deepEqual(endHooks(p), ["SessionEnd:other"]);
    assert.equal(ended(p).workerHoldAlive, false);
    assert.deepEqual(runs(`${p}-end-ended`), []);
    assert.deepEqual(obstacles(`${p}-end-ended`), []);
    const listed = one("agents", (record) => record.label === (p === "bs" ? "bs-stopped" : "br-removed")).agents.filter((agent) => agent.name === `fixture-lead-${verb}`);
    assert.deepEqual(listed.map((agent) => agent.state), p === "bs" ? ["stopped"] : []);
  });
}

// 8. Skills.
check("leads and workers list the skills in the `integrate` directory, except one with disable-model-invocation", () => {
  for (const label of ["h-lead", "h-worker", "hs-model", "hs-worker"]) {
    const skills = request(label, 0).skills;
    assert(skills.includes("issueWork") && skills.includes("modelListed"), label);
    assert(!skills.includes("userListed"), label);
  }
});
check("the model loads a model-invocable skill and dashpot-issue-work through Skill, in a lead and in a worker", () => {
  assert.equal(outcome("hs-model", "Skill").text, "Launching skill: fixture-model-skill");
  const lead = requests.filter((record) => record.label === "hs-model").flatMap((record) => record.outcomes ?? []);
  assert(lead.some((item) => item.input.skill === "dashpot-issue-work" && item.text === "Launching skill: dashpot-issue-work"));
  const worker = requests.filter((record) => record.label === "hs-worker").flatMap((record) => record.outcomes ?? []);
  assert(worker.some((item) => item.input.skill === "fixture-model-skill" && item.text === "Launching skill: fixture-model-skill"));
});
check("the Skill tool refuses a disable-model-invocation skill and tells the model to ask the user", () => {
  for (const label of ["hs-model", "hs-worker"]) {
    const refused = requests.filter((record) => record.label === label).flatMap((record) => record.outcomes ?? []).find((item) => item.input.skill === "fixture-user-skill");
    assert.equal(refused.isError, true, label);
    assert.match(refused.text, /cannot be used with Skill tool due to disable-model-invocation\. Ask the user to run \/fixture-user-skill themselves/);
  }
});
check("a user's slash command loads a disable-model-invocation skill, headless and interactive", () => {
  for (const label of ["hs-user", "is-user"]) assert(request(label, 0).skills.includes("userBody"), label);
  assert(request("is-model", 0).skills.includes("modelBody"));
});

console.log(checks.map((claim) => `ok - ${claim}`).join("\n"));
console.log(`${checks.length} claims verified against ${records.length} records.`);
const checkout = path.resolve(here, "..", "..", "..");
const drifted = Object.keys(environment.sourceSHA256).filter((name) => name.startsWith("src/"))
  .filter((name) => {
    try { return createHash("sha256").update(readFileSync(path.join(checkout, name))).digest("hex") !== environment.sourceSHA256[name]; } catch { return true; }
  });
console.log(drifted.length ? `Dashpot sources changed since the run: ${drifted.join(", ")}` : "Dashpot sources match the run's.");
assert(!(strict && drifted.length), "--strict: Dashpot sources differ from the run's");
