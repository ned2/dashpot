"""The managed OpenCode plugin, driven in Node.js against a fake server and a stub helper.

The helper's decisions are tested in ``test_opencode``; these tests hold the
plugin to what ADR 0090 makes its own: it observes OpenCode v2 only, admits
each event once across every instance of one server, routes a child's
activity to its root and a move by where its session was, prepares every
shell, marks the server unobserved when its last instance goes, recovers a
deletion no instance received, and bounds its queues and helpers. The fake
server's events, sessions and errors take the shapes the #405 trace
recorded at OpenCode 2.0.22.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dashpot.sessions.integrate import render_plugin

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")

# Answers like the helper: a registration with the roots in STUB_SESSIONS,
# anything else accepted, after STUB_DELAY_MS (only for an event of
# STUB_SLOW_TYPE, when that is set). Each invocation is logged with
# when it started, so a test can read what the plugin sent and when.
STUB = """#!/usr/bin/env node
import { appendFileSync } from "node:fs";
const started = Date.now();
let input = "";
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const request = JSON.parse(input);
  appendFileSync(process.env.STUB_LOG, JSON.stringify({ ...request, started }) + "\\n");
  const answer =
    request.kind === "register"
      ? { result: "accepted", sessions: JSON.parse(process.env.STUB_SESSIONS ?? "[]") }
      : { result: "accepted" };
  const slow = process.env.STUB_SLOW_TYPE;
  const delay = slow && request.event?.type !== slow ? 0 : Number(process.env.STUB_DELAY_MS ?? 0);
  setTimeout(() => console.log(JSON.stringify(answer)), delay);
});
"""

DRIVER = """
import { existsSync, readFileSync } from "node:fs";
const { default: plugin } = await import(process.argv[2]);
const scenario = process.argv[3];
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const at = (directory) => ({ directory });

// The server: its sessions, the sessions whose read fails, and every
// instance's event subscription, each of which receives every event.
const sessions = new Map([["ses_root", { location: "/repo" }]]);
const broken = new Set();
const slow = new Set();
const subscribers = new Set();
const shellHooks = [];
const stream = (signal) => {
  const buffer = [];
  let wake = null;
  const subscriber = (event) => {
    buffer.push(event);
    wake?.();
  };
  subscribers.add(subscriber);
  return (async function* () {
    try {
      while (!signal.aborted) {
        if (buffer.length) {
          yield buffer.shift();
          continue;
        }
        await new Promise((resolve) => {
          wake = resolve;
          signal.addEventListener("abort", resolve, { once: true });
        });
        wake = null;
      }
    } finally {
      subscribers.delete(subscriber);
    }
  })();
};
const context = (directory, version = "2.0.22") => ({
  app: version === null ? undefined : { name: "cli", version, channel: "latest" },
  location: at(directory),
  session: {
    get: async ({ sessionID }) => {
      if (broken.has(sessionID)) throw new Error("connection reset");
      if (slow.has(sessionID)) await sleep(2000);
      const known = sessions.get(sessionID);
      if (!known) throw Object.assign(new Error(""), { _tag: "Session.NotFoundError", sessionID });
      return { id: sessionID, location: at(known.location), ...(known.parentID ? { parentID: known.parentID } : {}) };
    },
  },
  event: { subscribe: ({ signal }) => stream(signal) },
  shell: { hook: async (name, run) => shellHooks.push({ name, run }) },
});
let events = 0;
const sequences = new Map();
const emit = (type, sessionID, { location, data = {} } = {}) => {
  const seq = (sequences.get(sessionID) ?? -1) + 1;
  sequences.set(sessionID, seq);
  const event = {
    id: `evt_${++events}`,
    created: Date.now(),
    type,
    durable: { aggregateID: sessionID, seq, version: 1 },
    ...(location ? { location: at(location) } : {}),
    data: { sessionID, ...data },
  };
  for (const subscriber of subscribers) subscriber(event);
};
const logged = () =>
  existsSync(process.env.STUB_LOG)
    ? readFileSync(process.env.STUB_LOG, "utf8").trim().split("\\n").filter(Boolean).map(JSON.parse)
    : [];
const until = async (done, milliseconds = 8000) => {
  const deadline = Date.now() + milliseconds;
  while (!done(logged()) && Date.now() < deadline) await sleep(20);
};
const count = (kind) => (requests) => requests.filter((request) => request.kind === kind).length;
const shell = async (env) => {
  const started = Date.now();
  for (const hook of shellHooks) if (hook.name === "create.before") await hook.run({ command: "true", cwd: "/repo", env });
  return { env, elapsed: Date.now() - started };
};

const result = {};
if (scenario === "guard") {
  const cleanups = [await plugin.setup(context("/repo", "1.18.30")), await plugin.setup(context("/repo", null))];
  emit("session.execution.started", "ses_root");
  await sleep(300);
  for (const cleanup of cleanups) await cleanup();
  result.id = plugin.id;
  result.cleanups = cleanups.map((cleanup) => typeof cleanup);
  result.hooks = shellHooks.length;
  result.subscribers = subscribers.size;
} else if (scenario === "shell") {
  const cleanup = await plugin.setup(context("/repo"));
  result.model = await shell({
    PATH: "/bin",
    OPENCODE_SESSION_ID: "ses_root",
    OPENCODE: "1",
    DASHPOT_AGENT_SESSION: "codex:outer",
    CODEX_THREAD_ID: "t",
    CLAUDE_CODE_SESSION_ID: "c",
    CLAUDE_PID: "7",
  });
  result.user = await shell({ PATH: "/bin" });
  result.pid = process.pid;
  result.hooks = shellHooks.map((hook) => hook.name);
  await cleanup();
} else if (scenario === "shell-wait") {
  const cleanup = await plugin.setup(context("/repo"));
  await until(count("register"));
  emit("session.execution.started", "ses_root");
  await sleep(50);
  result.model = await shell({ OPENCODE_SESSION_ID: "ses_root", OPENCODE: "1" });
  await cleanup();
} else if (scenario === "route") {
  // Two instances, at two locations of one server.
  const cleanups = [await plugin.setup(context("/repo")), await plugin.setup(context("/repo/wt"))];
  sessions.set("ses_child", { location: "/repo", parentID: "ses_root" });
  sessions.set("ses_late", { location: "/repo", parentID: "ses_child" });
  sessions.set("ses_fork", { location: "/repo" });
  emit("session.created", "ses_root", { location: "/repo", data: { location: at("/repo") } });
  emit("session.execution.started", "ses_root");
  emit("session.created", "ses_child", { location: "/repo", data: { location: at("/repo"), parentID: "ses_root" } });
  emit("session.execution.started", "ses_child");
  // A fork names its source as `parentID`, and is a root.
  emit("session.forked", "ses_fork", { location: "/repo", data: { parentID: "ses_root" } });
  emit("session.execution.interrupted", "ses_root", { data: { reason: "user" } });
  emit("session.moved", "ses_root", { location: "/repo", data: { location: at("/other") } });
  emit("session.execution.started", "ses_root");
  // A grandchild whose creation no instance received is read from OpenCode,
  // and routed to where its root is.
  emit("session.execution.started", "ses_late");
  emit("session.deleted", "ses_child");
  // Neither a session OpenCode does not have nor an event Dashpot does not
  // publish is sent.
  emit("session.execution.started", "ses_unknown");
  emit("session.status", "ses_root", { data: { status: { type: "busy" } } });
  await until((requests) => count("event")(requests) >= 10);
  await sleep(200);
  for (const cleanup of cleanups) await cleanup();
} else if (scenario === "child-after-move") {
  const cleanup = await plugin.setup(context("/repo"));
  await until(count("register"));
  emit("session.created", "ses_root", { location: "/repo", data: { location: at("/repo") } });
  emit("session.created", "ses_child", { location: "/repo", data: { location: at("/repo"), parentID: "ses_root" } });
  emit("session.moved", "ses_root", { location: "/repo", data: { location: at("/repo/wt") } });
  emit("session.execution.started", "ses_child");
  await until((requests) => count("event")(requests) >= 4);
  await cleanup();
} else if (scenario === "cleanup") {
  const cleanups = [await plugin.setup(context("/repo")), await plugin.setup(context("/repo/wt"))];
  emit("session.execution.started", "ses_root");
  await until(count("event"));
  await cleanups[0]();
  result.afterFirst = logged().map((request) => request.kind);
  await cleanups[1]();
  result.afterLast = logged().map((request) => request.kind);
  // A server's next instance publishes only after the marking.
  const next = await plugin.setup(context("/repo"));
  emit("session.execution.succeeded", "ses_root");
  await until(count("event"));
  await until((requests) => count("event")(requests) >= 2);
  await next();
} else if (scenario === "recover") {
  sessions.set("ses_alive", { location: "/repo" });
  broken.add("ses_broken");
  // OpenCode no longer has it, but does not answer in time.
  slow.add("ses_slow");
  const cleanup = await plugin.setup(context("/repo"));
  await until((requests) => count("gone")(requests) >= 2);
  // Past the slow session's 500 ms read.
  await sleep(1000);
  await cleanup();
} else if (scenario === "queue") {
  const cleanup = await plugin.setup(context("/repo"));
  for (let step = 0; step < 20; step++) {
    emit(step % 2 ? "session.execution.succeeded" : "session.execution.started", "ses_root");
  }
  await until((requests) => count("event")(requests) >= 16);
  await sleep(300);
  await cleanup();
} else if (scenario === "helpers") {
  const cleanup = await plugin.setup(context("/repo"));
  await until(count("register"));
  for (let session = 0; session < 10; session++) {
    sessions.set(`ses_${session}`, { location: "/repo" });
    emit("session.execution.started", `ses_${session}`);
  }
  await until((requests) => count("event")(requests) >= 10);
  await cleanup();
}
console.log(JSON.stringify(result));
process.exit(0);
"""


def drive(
    tmp_path: Path, scenario: str, **stub: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run one scenario; answer its result and the helper requests in order."""
    helper = tmp_path / "helper.mjs"
    helper.write_text(STUB)
    helper.chmod(0o755)
    plugin = tmp_path / "dashpot.mjs"
    plugin.write_text(render_plugin(helper))
    driver = tmp_path / "driver.mjs"
    driver.write_text(DRIVER)
    log = tmp_path / "requests.jsonl"
    completed = subprocess.run(
        ["node", str(driver), plugin.as_uri(), scenario],
        cwd=tmp_path,
        env={
            "PATH": str(Path(shutil.which("node") or "node").parent),
            "STUB_LOG": str(log),
            **stub,
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    requests = (
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.exists()
        else []
    )
    return json.loads(completed.stdout.strip().splitlines()[-1]), requests


def kinds(requests: list[dict[str, Any]]) -> list[str]:
    return [request["kind"] for request in requests]


def published(requests: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """Each event request as its session, root, location, type and destination."""
    return [
        (
            request["session"]["id"],
            request["session"]["root"],
            request["session"]["location"],
            request["event"]["type"],
            request["event"].get("to"),
        )
        for request in requests
        if request["kind"] == "event"
    ]


def test_the_plugin_observes_opencode_v2_only(tmp_path: Path) -> None:
    result, requests = drive(tmp_path, "guard")

    # OpenCode 1.x calls `setup` with no `app`; neither it nor another major
    # release registers, subscribes, or prepares a shell.
    assert result == {
        "id": "dashpot.observation",
        "cleanups": ["function", "function"],
        "hooks": 0,
        "subscribers": 0,
    }
    assert requests == []


def test_every_request_names_the_protocol_server_and_instance(tmp_path: Path) -> None:
    _result, requests = drive(tmp_path, "cleanup")

    for request in requests:
        assert request["protocol"] == 2
        assert 0 < request["deadlineMs"] <= 3000
    # One server: every request names the same pid; one generation per instance.
    assert len({request["pid"] for request in requests}) == 1
    registrations = [request for request in requests if request["kind"] == "register"]
    assert len({request["generation"] for request in registrations}) == 3


def test_a_shell_carries_only_the_claim_opencode_gives_a_models_shell(
    tmp_path: Path,
) -> None:
    result, _requests = drive(tmp_path, "shell")

    assert result["hooks"] == ["create.before"]
    # The plugin removes OpenCode's variables, which OpenCode sets again for
    # a model's shell only, and blanks every inherited claim.
    assert result["model"]["env"] == {
        "PATH": "/bin",
        "DASHPOT_AGENT_SESSION": "",
        "CODEX_THREAD_ID": "",
        "CLAUDE_CODE_SESSION_ID": "",
        "CLAUDE_PID": "",
        "DASHPOT_OPENCODE_PID": str(result["pid"]),
    }
    assert result["user"]["env"]["DASHPOT_OPENCODE_PID"] == str(result["pid"])
    assert result["user"]["elapsed"] < 500


def test_a_shell_waits_for_the_publications_already_admitted(tmp_path: Path) -> None:
    result, requests = drive(tmp_path, "shell-wait", STUB_DELAY_MS="800")

    assert 600 <= result["model"]["elapsed"] < 2500
    assert kinds(requests)[:2] == ["register", "event"]


def test_a_shell_waits_no_longer_than_three_seconds(tmp_path: Path) -> None:
    result, _requests = drive(tmp_path, "shell-wait", STUB_DELAY_MS="10000")

    assert 2500 <= result["model"]["elapsed"] < 3600


def test_a_childs_event_never_overtakes_its_roots_move(tmp_path: Path) -> None:
    _result, requests = drive(
        tmp_path,
        "child-after-move",
        STUB_DELAY_MS="600",
        STUB_SLOW_TYPE="session.moved",
    )

    events = [request for request in requests if request["kind"] == "event"]
    assert [
        (request["session"]["id"], request["event"]["type"]) for request in events
    ] == [
        ("ses_root", "session.created"),
        ("ses_child", "session.created"),
        ("ses_root", "session.moved"),
        ("ses_child", "session.execution.started"),
    ]
    moved, started = events[2], events[3]
    # Admitted after the move, the child's event waits for it to be written,
    # and is written where its root now is.
    assert started["started"] - moved["started"] >= 500
    assert started["session"] == {
        "id": "ses_child",
        "root": "ses_root",
        "location": "/repo/wt",
    }


def test_each_event_is_published_once_and_routed_to_its_root(tmp_path: Path) -> None:
    _result, requests = drive(tmp_path, "route")

    assert kinds(requests).count("register") == 2
    assert sorted(published(requests)) == sorted(
        [
            ("ses_root", "ses_root", "/repo", "session.created", None),
            ("ses_root", "ses_root", "/repo", "session.execution.started", None),
            ("ses_child", "ses_root", "/repo", "session.created", None),
            ("ses_child", "ses_root", "/repo", "session.execution.started", None),
            ("ses_late", "ses_root", "/other", "session.execution.started", None),
            ("ses_fork", "ses_fork", "/repo", "session.forked", None),
            ("ses_root", "ses_root", "/repo", "session.execution.interrupted", None),
            # A move is written by where its session was, naming where it went.
            ("ses_root", "ses_root", "/repo", "session.moved", "/other"),
            ("ses_root", "ses_root", "/other", "session.execution.started", None),
            ("ses_child", "ses_root", "/other", "session.deleted", None),
        ]
    )
    # One session's publications reach the helper in the order it emitted them.
    root = [
        request["event"]["sequence"]
        for request in requests
        if request["kind"] == "event" and request["session"]["id"] == "ses_root"
    ]
    assert root == sorted(root)
    (interrupted,) = [
        request
        for request in requests
        if request["kind"] == "event"
        and request["event"]["type"] == "session.execution.interrupted"
    ]
    assert interrupted["event"]["reason"] == "user"


def test_the_last_instance_marks_what_it_routed_unobserved(tmp_path: Path) -> None:
    result, requests = drive(tmp_path, "cleanup")

    assert "unobserved" not in result["afterFirst"]
    assert result["afterLast"][-1] == "unobserved"
    (marking, *_later) = [
        request for request in requests if request["kind"] == "unobserved"
    ]
    assert marking["locations"] == ["/repo"]
    # The next instance's publication follows the marking.
    marked_at = requests.index(marking)
    assert "event" in kinds(requests[marked_at + 1 :])


def test_registration_recovers_only_what_opencode_says_it_deleted(
    tmp_path: Path,
) -> None:
    roots = [
        {"id": "ses_gone", "subagents": ["ses_gone_child"]},
        {"id": "ses_alive", "subagents": ["ses_broken"]},
        {"id": "ses_slow", "subagents": []},
    ]

    _result, requests = drive(tmp_path, "recover", STUB_SESSIONS=json.dumps(roots))

    gone = sorted(
        (request["session"]["id"], request["session"]["root"])
        for request in requests
        if request["kind"] == "gone"
    )
    # A failed read, or one that does not answer in time, is never read as a
    # deletion.
    assert gone == [("ses_gone", "ses_gone"), ("ses_gone_child", "ses_gone")]
    assert {
        request["session"]["location"]
        for request in requests
        if request["kind"] == "gone"
    } == {"/repo"}


def test_a_sessions_queue_admits_at_most_sixteen_publications(tmp_path: Path) -> None:
    _result, requests = drive(tmp_path, "queue", STUB_DELAY_MS="20")

    events = [request for request in requests if request["kind"] == "event"]
    assert [request["event"]["sequence"] for request in events] == list(range(16))
    assert [request["event"]["type"] for request in events] == [
        "session.execution.started",
        "session.execution.succeeded",
    ] * 8


def test_at_most_eight_helpers_run_at_once(tmp_path: Path) -> None:
    _result, requests = drive(tmp_path, "helpers", STUB_DELAY_MS="600")

    started = sorted(
        request["started"] for request in requests if request["kind"] == "event"
    )
    assert len(started) == 10
    # The ninth waits for a slot an earlier helper releases.
    assert started[8] - started[0] >= 400
