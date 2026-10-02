// Throwaway OpenCode v2 measurement plugin for Issue #393. The runner copies
// it into the fixture's plugin directory with the log path filled in. Each
// setup is one plugin instance; it records what that instance is given and
// sees: its location and server process, every event its subscription
// delivers, each shell it is asked to prepare, each tool call, and its
// cleanup. A shell whose command names `SPIKE_CLEAR` has its inherited
// OPENCODE_SESSION_ID removed before the tool sets its own. It never writes
// Dashpot state.
import { appendFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

const LOG = "__SPIKE_LOG__";
const write = (record) => {
  try { appendFileSync(LOG, JSON.stringify({ ...record, at: Date.now() }) + "\n"); } catch {}
};
// The session an event names, wherever its schema keeps it.
const sessionOf = (data) => data?.sessionID ?? data?.info?.id ?? data?.session?.id ?? null;
const parentOf = (data) => data?.parentID ?? data?.info?.parentID ?? data?.session?.parentID ?? null;
const label = (command) => command.match(/command\.mjs (\S+)/)?.[1] ?? command.slice(0, 80);
// Streamed output, a turn's steps, text and tool-input phases, usage, and
// configuration refreshes are not recorded, which keeps the trace small; a
// shell's streamed progress and every lifecycle event are.
const unrecorded = /delta|streamed|^session\.(step|text|tool\.input|inbox|instructions)\.|^session\.tool\.(called|success)$|\.updated$/;

export default {
  id: "spike.measure",
  async setup(ctx) {
    const instance = randomUUID();
    const base = { instance, pid: process.pid };
    write({ kind: "plugin.setup", ...base, ppid: process.ppid, app: ctx.app, location: ctx.location,
      argv: process.argv.slice(0, 6), execPath: process.execPath, cwd: process.cwd(),
      serverEnv: { OPENCODE_SESSION_ID: process.env.OPENCODE_SESSION_ID ?? null, SPIKE_CLIENT: process.env.SPIKE_CLIENT ?? null } });
    const controller = new AbortController();
    (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (unrecorded.test(event.type)) continue;
          const data = event.data ?? {};
          write({ kind: "plugin.event", ...base, type: event.type, location: event.location?.directory ?? null,
            sessionID: sessionOf(data), parentID: parentOf(data), reason: data.reason ?? null,
            moved: event.type === "session.moved" ? data : undefined });
        }
        write({ kind: "plugin.stream-ended", ...base });
      } catch (error) {
        write({ kind: "plugin.stream-error", ...base, error: String(error).slice(0, 300) });
      }
    })();
    await ctx.shell.hook("create.before", async (invocation) => {
      const inherited = invocation.env.OPENCODE_SESSION_ID ?? null;
      const clear = invocation.command.includes("SPIKE_CLEAR");
      if (clear) delete invocation.env.OPENCODE_SESSION_ID;
      invocation.env.SPIKE_PLUGIN_INSTANCE = instance;
      write({ kind: "plugin.shell", ...base, label: label(invocation.command), cwd: invocation.cwd, shell: invocation.shell,
        inherited, cleared: clear, client: invocation.env.SPIKE_CLIENT ?? null, keys: Object.keys(invocation.env).length });
    });
    for (const name of ["execute.before", "execute.after"]) {
      await ctx.tool.hook(name, async (call) => {
        write({ kind: "plugin.tool", ...base, hook: name, tool: call.tool, sessionID: call.sessionID ?? null,
          agent: call.agent ?? null, status: call.status ?? null,
          label: typeof call.input?.command === "string" ? label(call.input.command) : null });
      });
    }
    return async () => {
      write({ kind: "plugin.cleanup", ...base });
      controller.abort();
    };
  },
};
