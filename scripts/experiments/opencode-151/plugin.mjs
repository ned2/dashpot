import { appendFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

// Experimental metadata publisher; it never writes Dashpot state.
export const IdentityProbe = async ({ directory, worktree, client }) => {
  const instance = randomUUID();
  const queues = new Map();
  let sequence = 0;
  const base = { instance, directory, worktree, pid: process.pid, ppid: process.ppid };
  const diagnostic = (record) => {
    try {
      appendFileSync(process.env.SPIKE_DIAGNOSTICS, JSON.stringify(record) + "\n");
    } catch {
      process.stderr.write("OpenCode identity probe: diagnostic write failed\n");
    }
  };
  const publish = (kind, fields = {}) => {
    const record = { ...base, ...fields, kind, sequence: ++sequence, sourceTime: Date.now() };
    const key = fields.sessionID ?? "instance";
    const previous = queues.get(key) ?? { tail: Promise.resolve(), count: 0 };
    if (previous.count >= 16) {
      diagnostic({ ...record, outcome: "queue-full" });
      return Promise.resolve(false);
    }
    const state = { count: previous.count + 1 };
    state.tail = previous.tail.then(async () => {
      try {
        const response = await fetch(process.env.SPIKE_SINK + "/publish", {
          method: "POST", body: JSON.stringify(record),
          signal: AbortSignal.timeout(250),
        });
        if (!response.ok || !(await response.json()).accepted) throw new Error("receiver-status");
        return true;
      } catch {
        diagnostic({ ...record, outcome: "publication-failed" });
        return false;
      } finally {
        const current = queues.get(key);
        current.count--;
        if (!current.count) queues.delete(key);
      }
    });
    queues.set(key, state);
    return state.tail;
  };
  await publish("plugin.init");
  return {
    event: async ({ event }) => {
      if (!event.type.startsWith("session.") && event.type !== "server.instance.disposed") return;
      const p = event.properties ?? {};
      const info = p.info ?? {};
      await publish(event.type, {
        sessionID: p.sessionID ?? info.id,
        parentID: info.parentID,
        sessionDirectory: info.directory,
        activity: p.status?.type,
        attempt: p.status?.attempt,
        nativeEventID: event.id,
      });
    },
    "tool.execute.before": async (input) => {
      await publish("tool.before", { sessionID: input.sessionID, tool: input.tool, callID: input.callID });
    },
    "tool.execute.after": async (input) => {
      await publish("tool.after", { sessionID: input.sessionID, tool: input.tool, callID: input.callID });
    },
    "shell.env": async (input, output) => {
      if (!input.sessionID) {
        await publish("shell.identity-missing", { shellCwd: input.cwd });
        return;
      }
      let info;
      try {
        const response = await Promise.race([
          client.session.get({ path: { id: input.sessionID } }),
          new Promise((_, reject) => setTimeout(() => reject(new Error("metadata-timeout")), 250)),
        ]);
        info = response.data;
      } catch {
        // Missing location is explicit evidence loss, never a shell-cwd fallback.
      }
      const metadataKnown = info?.id === input.sessionID;
      const published = await publish(metadataKnown ? "shell.bootstrap" : "shell.metadata-missing", {
        sessionID: input.sessionID, parentID: info?.parentID,
        sessionDirectory: info?.directory, shellCwd: input.cwd, callID: input.callID,
      });
      output.env.DASHPOT_AGENT_SESSION = `opencode:${input.sessionID}`;
      output.env.SPIKE_BOOTSTRAP_ACK = String(metadataKnown && published);
      output.env.SPIKE_INSTANCE = instance;
    },
    dispose: async () => {
      await Promise.all([...queues.values()].map((value) => value.tail));
      await publish("plugin.dispose");
    },
  };
};
