// A fixture-only OpenCode v2 plugin, installed beside Dashpot's for the
// Issue #479 run: it reports what a plugin receives for each session
// lifecycle, execution and permission event, its type, session, parent,
// location, the field names of its data, and any `metadata` it carries, so the
// run can tell what Dashpot's plugin could read without changing it. It lives
// inside the service, so it sees a restarted service's first events, which a
// client subscribing from outside can miss. At setup it reports the names its
// context offers, so the run can tell whether a plugin could make or prompt
// sessions itself. The runner writes the sink URL in place of the placeholder
// below.
const SINK = "__SPIKE_SINK__";
const SEEN = Symbol.for("fixture.probe.seen");
const names = (value) => value && (typeof value === "object" || typeof value === "function") ? Object.keys(value).toSorted() : null;

export default {
  id: "fixture.probe",
  async setup(ctx) {
    if (String(ctx?.app?.version ?? "").split(".")[0] !== "2") return async () => {};
    const seen = (globalThis[SEEN] ??= new Set());
    const controller = new AbortController();
    fetch(SINK + "/plugin", { method: "POST", signal: AbortSignal.timeout(3000), body: JSON.stringify({
      type: "plugin.setup", ctxKeys: names(ctx), sessionKeys: names(ctx?.session), clientKeys: names(ctx?.client), pid: process.pid, at: Date.now(),
    }) }).catch(() => {});
    (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          const type = event?.type ?? "";
          if (!/^(session\.(created|forked|metadata|updated|deleted|moved|execution\.)|permission\.)/.test(type) || typeof event.id !== "string" || seen.has(event.id)) continue;
          seen.add(event.id);
          const data = event.data ?? {};
          const info = data.info ?? data.session ?? null;
          fetch(SINK + "/plugin", { method: "POST", signal: AbortSignal.timeout(3000), body: JSON.stringify({
            type, sessionID: data.sessionID ?? info?.id ?? null, parentID: data.parentID ?? info?.parentID ?? null,
            location: event.location?.directory ?? null, dataKeys: Object.keys(data).toSorted(),
            metadata: data.metadata ?? info?.metadata ?? null, reason: data.reason ?? null, reply: data.reply ?? data.decision ?? null,
            pid: process.pid, at: Date.now(),
          }) }).catch(() => {});
        }
      } catch {}
    })();
    return async () => controller.abort();
  },
};
