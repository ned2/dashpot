// A fixture OpenCode v2 plugin installed beside Dashpot's: it records every
// event a plugin instance receives, as metadata only (type, ids, durable
// sequence, parent, reason word and location), plus each instance's setup
// and disposal. Like Dashpot's plugin, one server sets up one instance per
// location and every instance receives every event, so the instances share a
// registry on `globalThis` and the first to see an event records it. The
// records are appended to the file the runner names, which it tails.
//
// Streaming deltas are counted, not recorded.
import { appendFileSync } from "node:fs";

const REGISTRY = Symbol.for("fixture.probe.registry.448");
const STREAMED = /\.delta$|\.streamed$|\.progress$/;

const write = (record) => {
  try {
    appendFileSync(process.env.SPIKE_PLUGIN_EVENTS, JSON.stringify({ ...record, at: Date.now(), pid: process.pid }) + "\n");
  } catch {}
};

export default {
  id: "fixture.probe",
  async setup(ctx) {
    const shared = (globalThis[REGISTRY] ??= { seen: new Set(), instances: 0, order: 0, streamed: {} });
    const instance = ++shared.instances;
    const location = typeof ctx?.location?.directory === "string" ? ctx.location.directory : null;
    write({ phase: "setup", instance, location, version: ctx?.app?.version ?? null });
    const controller = new AbortController();
    (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (typeof event?.id !== "string" || shared.seen.has(event.id)) continue;
          shared.seen.add(event.id);
          const type = String(event.type);
          if (STREAMED.test(type)) {
            shared.streamed[type] = (shared.streamed[type] ?? 0) + 1;
            continue;
          }
          const data = event.data ?? {};
          write({
            phase: "event", instance, order: ++shared.order, type, id: event.id,
            seq: Number.isInteger(event.durable?.seq) ? event.durable.seq : null,
            sessionID: typeof data.sessionID === "string" ? data.sessionID : null,
            parentID: type === "session.created" ? (data.parentID ?? null) : undefined,
            source: type === "session.forked" ? (data.parentID ?? null) : undefined,
            reason: typeof data.reason === "string" && /^[a-z][a-z0-9_-]{0,63}$/.test(data.reason) ? data.reason : undefined,
            location: typeof event.location?.directory === "string" ? event.location.directory : null,
            to: type === "session.moved" && typeof data.location?.directory === "string" ? data.location.directory : undefined,
          });
        }
      } catch {}
    })();
    return async () => {
      controller.abort();
      write({ phase: "dispose", instance, location, streamed: shared.streamed });
    };
  },
};
