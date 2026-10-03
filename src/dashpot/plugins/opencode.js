// dashpot-managed-plugin: opencode
// The Dashpot observation plugin for OpenCode v2, written by `dashpot integrate
// opencode` and removed by `dashpot integrate opencode --remove`; an edit here
// is overwritten by the next integration.
//
// It is deliberately thin. It reports OpenCode's own session events, in
// OpenCode's own order, to the installed Dashpot helper, one bounded
// subprocess per event, and prepares every shell so that only OpenCode's own
// step for a model's shell can give it a session identity. Every decision
// about what the events mean is the helper's. A failed publication never
// fails an OpenCode tool or prompt.
//
// One server sets up one instance of this plugin per OpenCode location, and
// every instance receives every event of the whole server. The instances of
// one server share a registry on `globalThis`, which admits each event once,
// keeps each session's location and parent, and sends each session's
// publications to the helper one at a time (ADR 0090).
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

const HELPER = "__DASHPOT_OPENCODE_HELPER__";
const PROTOCOL = 2;
// One helper invocation: Python start, Git and process probes, the write.
const PUBLICATION_DEADLINE_MS = 3000;
// A shell waits at most this long for the publications already admitted.
const SHELL_WAIT_MS = 3000;
const METADATA_DEADLINE_MS = 500;
// The admitted publications the last instance's cleanup lets finish first.
const CLEANUP_DRAIN_MS = 1000;
const QUEUE_LIMIT = 16;
const HELPER_LIMIT = 8;
const PARENT_DEPTH_LIMIT = 8;
// Bounds on what the registry remembers: event ids are admitted within
// moments of each other by every instance, and sessions are re-read on demand.
const SEEN_LIMIT = 4096;
const SESSION_LIMIT = 4096;
const ROUTED_LIMIT = 256;
const REGISTRY = Symbol.for("dashpot.opencode.registry.v2");
// The claims of a harness that launched OpenCode, which a command inside
// OpenCode must never inherit.
const CLAIM_VARIABLES = ["DASHPOT_AGENT_SESSION", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"];
const PUBLISHED = new Set([
  "session.created",
  "session.forked",
  "session.execution.started",
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
  "session.moved",
  "session.deleted",
]);
const REASON = /^[a-z][a-z0-9_-]{0,63}$/;
const SESSION = /^[A-Za-z0-9._:-]+$/;
const NOT_FOUND = "Session.NotFoundError";

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, Math.max(0, milliseconds)));
const bounded = (map, limit) => {
  while (map.size > limit) map.delete(map.keys().next().value);
};
const directoryOf = (location) => (typeof location?.directory === "string" ? location.directory : null);

// The server-wide state every instance of this plugin shares. Each instance
// is its own module evaluation, so module state is never shared.
const registry = () =>
  (globalThis[REGISTRY] ??= {
    live: new Map(),
    seen: new Map(),
    sessions: new Map(),
    queues: new Map(),
    pending: new Set(),
    routed: new Set(),
    helpers: 0,
    waiters: [],
    barrier: Promise.resolve(),
  });

// Run the helper once, killing it at its deadline; resolve its
// acknowledgment, or null for anything else.
const invoke = async (shared, generation, request) => {
  const deadline = Date.now() + PUBLICATION_DEADLINE_MS;
  while (shared.helpers >= HELPER_LIMIT) {
    if (Date.now() >= deadline) return null;
    await new Promise((resolve) => {
      // A waiter that times out leaves the queue, so a released slot always
      // wakes one that still waits.
      const timer = setTimeout(() => {
        const index = shared.waiters.indexOf(wake);
        if (index >= 0) shared.waiters.splice(index, 1);
        resolve();
      }, deadline - Date.now());
      const wake = () => {
        clearTimeout(timer);
        resolve();
      };
      shared.waiters.push(wake);
    });
  }
  shared.helpers++;
  // A helper killed at its deadline holds its slot until it exits, so a
  // stalled helper holds back further helpers rather than piling them up.
  let released = false;
  const release = () => {
    if (released) return;
    released = true;
    shared.helpers--;
    shared.waiters.shift()?.();
  };
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(HELPER, [], { stdio: ["pipe", "pipe", "ignore"] });
    } catch {
      release();
      resolve(null);
      return;
    }
    let output = "";
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {}
      finish(null);
    }, Math.max(1, deadline - Date.now()));
    child.on("error", () => {
      release();
      finish(null);
    });
    child.on("close", () => {
      release();
      let acknowledgment = null;
      try {
        acknowledgment = JSON.parse(output.trim().split("\n").pop());
      } catch {}
      finish(acknowledgment);
    });
    child.stdout.on("data", (chunk) => {
      output += chunk;
    });
    child.stdin.on("error", () => {});
    child.stdin.end(
      JSON.stringify({
        ...request,
        protocol: PROTOCOL,
        generation,
        pid: process.pid,
        deadlineMs: Math.max(1, deadline - Date.now()),
      }),
    );
  });
};

// Read one session from OpenCode through any live instance, bounded: its
// location and parent, `{missing: true}` only when OpenCode answers that it
// has no such session, and null for anything else.
const read = async (shared, sessionID, milliseconds) => {
  const ctx = [...shared.live.values()].pop();
  if (!ctx || milliseconds <= 0) return null;
  try {
    const answer = await Promise.race([ctx.session.get({ sessionID }), sleep(milliseconds).then(() => null)]);
    // The session itself, or wrapped as `data` like a v1 SDK answer.
    const info = answer?.data ?? answer ?? null;
    if (info?.id !== sessionID) return null;
    const location = directoryOf(info.location);
    return location ? { location, parentID: info.parentID ?? null } : null;
  } catch (error) {
    return error?._tag === NOT_FOUND || error?.name === NOT_FOUND ? { missing: true } : null;
  }
};

const remember = (shared, sessionID, location, parentID) => {
  const known = { location, parentID: parentID ?? null };
  shared.sessions.delete(sessionID);
  shared.sessions.set(sessionID, known);
  bounded(shared.sessions, SESSION_LIMIT);
  return known;
};

// The root a session's activity belongs to and the root's location, from
// what the registry knows now; null when any link is unknown.
const routeKnown = (shared, sessionID) => {
  let current = sessionID;
  let known = shared.sessions.get(current);
  for (let depth = 0; known?.parentID && depth < PARENT_DEPTH_LIMIT; depth++) {
    current = known.parentID;
    known = shared.sessions.get(current);
  }
  return known && !known.parentID ? { root: current, location: known.location } : null;
};

// The same, reading unknown sessions from OpenCode: unknown parentage is
// never read as a root.
const route = async (shared, sessionID) => {
  let current = sessionID;
  for (let depth = 0; depth <= PARENT_DEPTH_LIMIT; depth++) {
    let known = shared.sessions.get(current);
    if (!known) {
      const answer = await read(shared, current, METADATA_DEADLINE_MS);
      if (!answer?.location) return null;
      known = remember(shared, current, answer.location, answer.parentID);
    }
    if (!known.parentID) return { root: current, location: known.location };
    current = known.parentID;
  }
  return null;
};

// One ordered queue per root: a root's publications and its children's reach
// the helper one at a time, in the order they were admitted, so a child's
// event never overtakes its root's move; separate roots publish
// concurrently. Every publication first waits for a last instance's
// cleanup to finish marking its sessions.
const enqueue = (shared, key, task) => {
  let queue = shared.queues.get(key);
  if (!queue) {
    queue = { tail: Promise.resolve(), pending: 0 };
    shared.queues.set(key, queue);
  }
  // A full queue loses the event; the session's next accepted publication
  // corrects its state.
  if (queue.pending >= QUEUE_LIMIT) return;
  queue.pending++;
  const run = queue.tail
    .then(() => shared.barrier)
    .then(task)
    .catch(() => null)
    .finally(() => {
      queue.pending--;
      shared.pending.delete(run);
      if (queue.pending === 0 && shared.queues.get(key) === queue) shared.queues.delete(key);
    });
  queue.tail = run;
  shared.pending.add(run);
};

const routed = (shared, location) => {
  shared.routed.delete(location);
  shared.routed.add(location);
  while (shared.routed.size > ROUTED_LIMIT) shared.routed.delete(shared.routed.values().next().value);
};

// Admit one event: place its session from what the event says, and queue its
// publication with the route the registry knows at admission, so a later
// move never redirects an earlier event. A session the registry cannot yet
// route is read from OpenCode when its turn comes, and routed to where its
// root is then.
const admit = (shared, generation, event) => {
  const data = event.data ?? {};
  const sessionID = data.sessionID;
  const sequence = event.durable?.seq;
  if (typeof sessionID !== "string" || !SESSION.test(sessionID) || !Number.isInteger(sequence)) return;
  let from = null;
  let to = null;
  if (event.type === "session.created") {
    const location = directoryOf(event.location) ?? directoryOf(data.location);
    if (location) remember(shared, sessionID, location, data.parentID);
  } else if (event.type === "session.forked") {
    // A fork's `parentID` is its source, never its parent: a fork is a root.
    const location = directoryOf(event.location);
    if (location) remember(shared, sessionID, location, null);
  } else if (event.type === "session.moved") {
    to = directoryOf(data.location);
    if (!to) return;
    const known = shared.sessions.get(sessionID);
    from = directoryOf(event.location) ?? known?.location ?? null;
    if (known) remember(shared, sessionID, to, known.parentID);
  }
  const admitted = routeKnown(shared, sessionID);
  const reason = typeof data.reason === "string" && REASON.test(data.reason) ? data.reason : undefined;
  enqueue(shared, admitted?.root ?? sessionID, async () => {
    const found = admitted ?? (await route(shared, sessionID));
    if (!found) return null;
    const moved = event.type === "session.moved";
    if (moved && !from) return null;
    // A move routes by where its session was; a child's events by its root.
    const location = moved && found.root === sessionID ? from : found.location;
    routed(shared, location);
    if (moved) routed(shared, to);
    const acknowledgment = await invoke(shared, generation, {
      kind: "event",
      session: { id: sessionID, root: found.root, location },
      event: { id: event.id, type: event.type, sequence, reason, to: moved ? to : undefined },
    });
    if (event.type === "session.deleted") shared.sessions.delete(sessionID);
    return acknowledgment;
  });
};

// Publish a deletion no live instance received: the helper returned the
// roots its store records on this server, and OpenCode answers that it has
// no such session. A timeout or an error is never read as a deletion.
const recover = async (shared, generation, location, sessions) => {
  for (const recovered of sessions ?? []) {
    if (typeof recovered?.id !== "string") continue;
    const ids = [recovered.id, ...(Array.isArray(recovered.subagents) ? recovered.subagents : [])];
    for (const id of ids) {
      if (typeof id !== "string") continue;
      const answer = await read(shared, id, METADATA_DEADLINE_MS);
      if (!answer?.missing) continue;
      enqueue(shared, recovered.id, () =>
        invoke(shared, generation, { kind: "gone", session: { id, root: recovered.id, location } }),
      );
    }
  }
};

const majorVersion = (version) => Number.parseInt(String(version ?? "").split(".")[0], 10);

// Why a shell OpenCode v1 prepared cannot opt in: Dashpot observes v2 only.
const V1_REFUSAL = "opencode-v1";

export default {
  id: "dashpot.observation",
  // OpenCode 1.x loads this entry: it publishes nothing, and tells every
  // shell that Dashpot refuses OpenCode v1, so `work start` says so (ADR 0090).
  server: async () => ({
    "shell.env": async (_input, output) => {
      const env = output?.env;
      if (!env) return;
      for (const name of CLAIM_VARIABLES) env[name] = "";
      env.DASHPOT_OPENCODE_REFUSAL = V1_REFUSAL;
    },
  }),
  async setup(ctx) {
    // OpenCode 1.x calls `setup` too, with no `ctx.app`: this entry observes
    // OpenCode v2 only, and on any other release does nothing at all.
    if (majorVersion(ctx?.app?.version) !== 2) return async () => {};
    const shared = registry();
    // One instance is one Publisher Generation.
    const generation = randomUUID();
    shared.live.set(generation, ctx);
    const location = directoryOf(ctx.location);

    if (location) {
      invoke(shared, generation, { kind: "register", location })
        .then((acknowledgment) =>
          acknowledgment?.result === "accepted" ? recover(shared, generation, location, acknowledgment.sessions) : null,
        )
        .catch(() => {});
    }

    const controller = new AbortController();
    (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (!PUBLISHED.has(event?.type) || typeof event.id !== "string") continue;
          // Every instance receives every event; whichever does first admits it.
          if (shared.seen.has(event.id)) continue;
          shared.seen.set(event.id, generation);
          bounded(shared.seen, SEEN_LIMIT);
          admit(shared, generation, event);
        }
      } catch {}
    })();

    await ctx.shell.hook("create.before", async (invocation) => {
      const env = invocation?.env;
      if (!env) return;
      // OpenCode sets both again after every plugin hook, for a model's shell
      // only, so with the pid below they are a claim no other shell can carry.
      delete env.OPENCODE_SESSION_ID;
      delete env.OPENCODE;
      for (const name of CLAIM_VARIABLES) env[name] = "";
      env.DASHPOT_OPENCODE_PID = String(process.pid);
      // A session's first command finds the session's record.
      await Promise.race([Promise.allSettled([...shared.pending]), sleep(SHELL_WAIT_MS)]);
    });

    return async () => {
      controller.abort();
      shared.live.delete(generation);
      if (shared.live.size > 0) return;
      // The server's last live instance: let what it admitted finish briefly,
      // then mark the running sessions it published as observed by nothing,
      // unless an instance was set up meanwhile.
      await Promise.race([Promise.allSettled([...shared.pending]), sleep(CLEANUP_DRAIN_MS)]);
      if (shared.live.size > 0 || shared.routed.size === 0) return;
      const marking = invoke(shared, generation, { kind: "unobserved", locations: [...shared.routed] }).catch(() => null);
      shared.barrier = marking.then(() => {});
      await shared.barrier;
    };
  },
};
