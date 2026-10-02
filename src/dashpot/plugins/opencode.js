// dashpot-managed-plugin: opencode
// The Dashpot observation plugin for OpenCode, written by `dashpot integrate
// opencode` and removed by `dashpot integrate opencode --remove`; an edit here
// is overwritten by the next integration.
//
// It is deliberately thin. It reports OpenCode's own lifecycle metadata --
// session status, deletion, parentage, its own lifetime -- to the installed
// Dashpot helper, one bounded subprocess per publication, and gives a shell
// command a Dashpot identity claim only after the helper acknowledged that
// command's own bootstrap. Every decision about what the metadata means is the
// helper's. A failed publication never fails an OpenCode tool or prompt.
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

const HELPER = "__DASHPOT_OPENCODE_HELPER__";
const PROTOCOL = 1;
// One helper invocation: Python start, Git and process probes, the write.
const PUBLICATION_DEADLINE_MS = 3000;
// A shell command waits at most this long for its own bootstrap, metadata,
// queue and helper together.
const SHELL_BUDGET_MS = 3000;
const METADATA_DEADLINE_MS = 500;
const QUEUE_LIMIT = 16;
const HELPER_LIMIT = 8;
const REGISTRATION_RETRY_MS = 1000;
const CONFLICT_BACKOFF_MS = 50;
const DISPOSAL_DRAIN_MS = 1000;
const CONFLICT_BACKOFF_LIMIT_MS = 400;
const PARENT_DEPTH_LIMIT = 8;
// Every identity claim Dashpot reads from a command's environment: this
// plugin's own, and the claims of a harness that launched OpenCode, which a
// command inside OpenCode must never inherit.
const CLAIM_VARIABLES = [
  "DASHPOT_OPENCODE_SESSION_ID",
  "DASHPOT_OPENCODE_GENERATION",
  "DASHPOT_OPENCODE_PID",
  "DASHPOT_AGENT_SESSION",
  "CODEX_THREAD_ID",
  "CLAUDE_CODE_SESSION_ID",
  "CLAUDE_PID",
];
const STATUSES = new Set(["busy", "retry", "idle"]);

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, Math.max(0, milliseconds)));

export const DashpotOpenCodeObservation = async ({ directory, client }) => {
  // One plugin instance is one publisher generation.
  const generation = randomUUID();
  const sessions = new Map();
  const queues = new Map();
  let helpers = 0;
  let registered = false;
  let registering = null;
  let retryAfter = 0;
  let closed = false;

  // Run the helper once, killing it at the deadline; resolve its
  // acknowledgment, or null for anything else.
  const invoke = (request, deadline) =>
    new Promise((resolve) => {
      const remaining = deadline - Date.now();
      if (remaining <= 0 || helpers >= HELPER_LIMIT) {
        resolve(null);
        return;
      }
      let child;
      try {
        child = spawn(HELPER, [], { stdio: ["pipe", "pipe", "ignore"] });
      } catch {
        resolve(null);
        return;
      }
      // A helper killed at its deadline still counts until it exits, so a
      // stalled helper holds back further admission rather than piling up.
      helpers++;
      let released = false;
      const release = () => {
        if (!released) {
          released = true;
          helpers--;
        }
      };
      let output = "";
      let settled = false;
      const finish = (value) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve(value);
        }
      };
      const timer = setTimeout(() => {
        try {
          child.kill("SIGKILL");
        } catch {}
        finish(null);
      }, remaining);
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
          directory,
          pid: process.pid,
          deadlineMs: remaining,
        }),
      );
    });

  // A generation publishes only once it owns its backend and directory.
  // OpenCode starts a replacement instance before the one it disposed has
  // retired, so a conflict is retried with backoff while the caller's
  // deadline allows; a helper that failed outright is retried, at most once
  // a second, by later publications.
  const attempt = async (deadline, patient) => {
    for (let backoff = CONFLICT_BACKOFF_MS; !closed; backoff *= 2) {
      const result = (await invoke({ kind: "register" }, deadline))?.result;
      if (result === "accepted" || result === "duplicate") return "registered";
      if (result === "retired") {
        closed = true;
        return "retired";
      }
      if (result !== "conflict") return "failed";
      if (!patient || Date.now() + backoff >= deadline) return "conflict";
      await sleep(Math.min(backoff, CONFLICT_BACKOFF_LIMIT_MS));
    }
    return "retired";
  };
  const register = (deadline, patient = true) => {
    if (registered) return Promise.resolve(true);
    if (closed || Date.now() < retryAfter) return Promise.resolve(false);
    if (!registering) {
      registering = attempt(deadline, patient).then((outcome) => {
        registering = null;
        registered = outcome === "registered";
        if (outcome === "failed") retryAfter = Date.now() + REGISTRATION_RETRY_MS;
        return registered;
      });
    }
    return registering;
  };

  const remember = (info) => {
    const known = {
      id: info.id,
      directory: info.directory,
      parentID: info.parentID ?? null,
    };
    sessions.set(info.id, known);
    return known;
  };

  // The native metadata of one session, or null when it cannot be read in
  // time: unknown parentage is never read as a root.
  const describe = async (id, deadline) => {
    const known = sessions.get(id);
    if (known) return known;
    const remaining = Math.min(METADATA_DEADLINE_MS, deadline - Date.now());
    if (remaining <= 0) return null;
    try {
      const response = await Promise.race([
        client.session.get({ path: { id } }),
        sleep(remaining).then(() => null),
      ]);
      const info = response?.data;
      if (info?.id === id && typeof info.directory === "string") return remember(info);
    } catch {}
    return null;
  };

  // The root session whose Agent Run a session's activity belongs to.
  const rootOf = async (info, deadline) => {
    let current = info;
    for (let depth = 0; current?.parentID && depth < PARENT_DEPTH_LIMIT; depth++) {
      current = await describe(current.parentID, deadline);
    }
    return current && !current.parentID ? current.id : null;
  };

  // One ordered queue per native session: its sequence is taken when the
  // callback enters, so publications keep OpenCode's order for the session
  // while separate sessions publish concurrently.
  const enqueue = (id, task) => {
    let queue = queues.get(id);
    if (!queue) {
      queue = { tail: Promise.resolve(), pending: 0, sequence: 0, status: null };
      queues.set(id, queue);
    }
    if (closed || queue.pending >= QUEUE_LIMIT) return Promise.resolve(null);
    const sequence = ++queue.sequence;
    queue.pending++;
    const run = queue.tail.then(async () => {
      try {
        return await task(sequence);
      } catch {
        return null;
      } finally {
        queue.pending--;
      }
    });
    queue.tail = run;
    return run;
  };

  const publish = async (id, fields, sequence, deadline) => {
    // OpenCode repeats a session's status at every step of a turn; an
    // unchanged status the helper already accepted is not published again.
    const queue = queues.get(id);
    if (fields.kind === "status" && queue.status === fields.status) {
      return { result: "duplicate" };
    }
    const info = await describe(id, deadline);
    if (!info) return { result: "unavailable", reason: "session-metadata-unavailable" };
    const root = await rootOf(info, deadline);
    if (!root) return { result: "unavailable", reason: "session-parentage-unavailable" };
    if (!(await register(deadline))) {
      return { result: "unavailable", reason: "publisher-not-registered" };
    }
    const acknowledgment = await invoke({ ...fields, sequence, session: info, root }, deadline);
    if (fields.kind === "status") {
      queue.status = acknowledgment?.result === "accepted" ? fields.status : null;
    } else if (fields.kind === "bootstrap") {
      // A bootstrap is activity the next status must not be mistaken for.
      queue.status = null;
    }
    return acknowledgment;
  };

  // OpenCode awaits a plugin's initialisation before the instance serves, so
  // the first registration is a single attempt; a conflict is left for the
  // first publication to wait out.
  await register(Date.now() + PUBLICATION_DEADLINE_MS, false);

  return {
    event: async ({ event }) => {
      const properties = event?.properties ?? {};
      const type = event?.type;
      if (type === "session.created" || type === "session.updated") {
        if (properties.info?.id) remember(properties.info);
        return;
      }
      if (type === "session.status") {
        const id = properties.sessionID;
        const status = properties.status?.type;
        if (!id || !STATUSES.has(status)) return;
        enqueue(id, (sequence) =>
          publish(id, { kind: "status", status }, sequence, Date.now() + PUBLICATION_DEADLINE_MS),
        );
        return;
      }
      if (type === "session.deleted") {
        const info = properties.info;
        if (!info?.id) return;
        remember(info);
        enqueue(info.id, (sequence) =>
          publish(info.id, { kind: "deleted" }, sequence, Date.now() + PUBLICATION_DEADLINE_MS),
        );
      }
    },
    "shell.env": async (input, output) => {
      const env = output.env;
      for (const name of CLAIM_VARIABLES) env[name] = "";
      const id = input?.sessionID;
      if (!id) {
        env.DASHPOT_OPENCODE_UNCORROBORATED = "no-session-identity";
        return;
      }
      const command = input.callID ?? null;
      const deadline = Date.now() + SHELL_BUDGET_MS;
      const acknowledgment = await Promise.race([
        enqueue(id, (sequence) =>
          publish(id, { kind: "bootstrap", command }, sequence, deadline),
        ),
        sleep(deadline - Date.now()).then(() => null),
      ]);
      const claim = acknowledgment?.claim;
      if (
        acknowledgment?.result === "accepted" &&
        acknowledgment.command === command &&
        claim?.sessionID === id &&
        claim.generation === generation &&
        Number.isInteger(claim.pid)
      ) {
        env.DASHPOT_OPENCODE_SESSION_ID = id;
        env.DASHPOT_OPENCODE_GENERATION = generation;
        env.DASHPOT_OPENCODE_PID = String(claim.pid);
        return;
      }
      env.DASHPOT_OPENCODE_UNCORROBORATED = acknowledgment?.reason ?? "no-acknowledgment";
    },
    dispose: async () => {
      closed = true;
      // Publications already admitted finish first, briefly: the replacement
      // generation is waiting for this retirement.
      await Promise.race([
        Promise.all([...queues.values()].map((queue) => queue.tail)),
        sleep(DISPOSAL_DRAIN_MS),
      ]);
      // Retirement is sent even when registration never succeeded: its
      // tombstone keeps a late registration from taking ownership.
      await invoke({ kind: "retire" }, Date.now() + PUBLICATION_DEADLINE_MS);
    },
  };
};
