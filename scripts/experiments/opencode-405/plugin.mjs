// Throwaway OpenCode measurement plugin for Issue #405, in the shape the
// rewritten Dashpot plugin will take: one default export carrying the v2
// `{id, setup}` definition and a v1 `server` entry. The runner copies it into
// each fixture's plugin directory with its paths filled in.
//
// Under v2, each setup is one plugin instance. It records the process-wide
// registry it finds on `globalThis` and the module evaluation it came from,
// every session event's envelope, a bounded `ctx.session.get` of each created
// or forked session, and of each session the runner lists in its probe file,
// and the shells it prepares. Under v1, the `server` entry records that it
// was called and gives every shell a refusal variable. It never writes
// Dashpot state.
import { appendFileSync, readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

const LOG = "__SPIKE_LOG__";
const PROBE = "__SPIKE_PROBE__";
const REGISTRY = Symbol.for("dashpot.spike405.registry");
// A module evaluation: a plugin file edit evaluates the module afresh.
const evaluation = randomUUID();
const write = (record) => {
  try { appendFileSync(LOG, JSON.stringify({ ...record, pid: process.pid, evaluation, at: Date.now() }) + "\n"); } catch {}
};
const sessionOf = (data) => data?.sessionID ?? data?.info?.id ?? data?.session?.id ?? null;
const label = (command) => command.match(/command\.mjs (\S+)/)?.[1] ?? command.slice(0, 80);
const failure = (error) => ({ name: error?.name ?? null, tag: error?._tag ?? null, message: String(error?.message ?? error).slice(0, 300),
  keys: error && typeof error === "object" ? Object.keys(error).slice(0, 12) : null });
const recorded = /^session\.(created|forked|deleted|moved|execution\.)/;

export default {
  id: "spike.measure405",
  // The v1 entry: OpenCode 1.18.30 calls it as a server plugin.
  server: async (input) => {
    write({ kind: "v1.server", directory: input?.directory ?? null, keys: Object.keys(input ?? {}) });
    return {
      "shell.env": async (shellInput, output) => {
        output.env.SPIKE_V1_REFUSED = "opencode-v1";
        write({ kind: "v1.shell", sessionID: shellInput?.sessionID ?? null });
      },
    };
  },
  async setup(ctx) {
    const registry = (globalThis[REGISTRY] ??= { id: randomUUID(), live: new Set(), seen: new Map() });
    const instance = randomUUID();
    registry.live.add(instance);
    const base = { instance, registry: registry.id };
    write({ kind: "plugin.setup", ...base, live: registry.live.size, app: ctx.app, location: ctx.location?.directory ?? null });
    const get = async (sessionID, why) => {
      const started = Date.now();
      try {
        const answer = await Promise.race([
          ctx.session.get({ sessionID }),
          new Promise((resolve) => setTimeout(() => resolve({ timedOut: true }), 500)),
        ]);
        const info = answer?.data ?? answer;
        write({ kind: "plugin.get", ...base, why, sessionID, ms: Date.now() - started, timedOut: Boolean(answer?.timedOut),
          found: info?.id === sessionID, location: info?.location?.directory ?? null, parentID: info?.parentID ?? null,
          fork: info?.fork ?? null, keys: info && typeof info === "object" ? Object.keys(info) : null });
      } catch (error) {
        write({ kind: "plugin.get", ...base, why, sessionID, ms: Date.now() - started, error: failure(error) });
      }
    };
    // Recovery on registration: the sessions the runner lists.
    let listed = [];
    try { listed = JSON.parse(readFileSync(PROBE, "utf8")); } catch {}
    for (const sessionID of listed) await get(sessionID, "recovery");
    const controller = new AbortController();
    (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (!recorded.test(event.type)) continue;
          const data = event.data ?? {};
          const sessionID = sessionOf(data);
          const first = !registry.seen.has(event.id);
          if (first) registry.seen.set(event.id, instance);
          write({ kind: "plugin.event", ...base, type: event.type, id: event.id ?? null, first, durable: event.durable ?? null,
            created: event.created ?? null, envelope: Object.keys(event), location: event.location?.directory ?? null,
            sessionID, parentID: data.parentID ?? data.info?.parentID ?? null, reason: data.reason ?? null,
            to: data.location?.directory ?? null, dataKeys: Object.keys(data) });
          if (first && (event.type === "session.created" || event.type === "session.forked")) {
            await get(event.type === "session.forked" ? (data.sessionID ?? sessionID) : sessionID, event.type);
          }
        }
        write({ kind: "plugin.stream-ended", ...base });
      } catch (error) {
        write({ kind: "plugin.stream-error", ...base, error: failure(error) });
      }
    })();
    await ctx.shell.hook("create.before", async (invocation) => {
      const before = { OPENCODE_SESSION_ID: invocation.env.OPENCODE_SESSION_ID ?? null, OPENCODE: invocation.env.OPENCODE ?? null };
      delete invocation.env.OPENCODE_SESSION_ID;
      delete invocation.env.OPENCODE;
      invocation.env.SPIKE_HOST_PID = String(process.pid);
      invocation.env.SPIKE_PLUGIN_INSTANCE = instance;
      write({ kind: "plugin.shell", ...base, label: label(invocation.command), cwd: invocation.cwd, before,
        invocation: Object.keys(invocation) });
    });
    return async () => {
      registry.live.delete(instance);
      write({ kind: "plugin.cleanup", ...base, live: registry.live.size });
      controller.abort();
    };
  },
};
