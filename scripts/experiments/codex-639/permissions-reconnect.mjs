// Measure the real local TUI's permission parameters through a transport loss.
// The server is a protocol fixture, like Codex's pinned reconnect integration
// test. It deliberately returns different recovered defaults; it executes no
// commands. Filesystem enforcement is measured separately by the real server.
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import net from "node:net";
import path from "node:path";

export async function runReconnect({ root, main, env, trace, terminal, waitFor, delay, mode }) {
  const codexHome = path.join(root, `reconnect-${mode}`);
  const socketPath = path.join(codexHome, "app-server-control/app-server-control.sock");
  mkdirSync(path.dirname(socketPath), { recursive: true });
  // Preserve the isolated provider, catalog and updater settings. Remove the
  // constrained profile: this case specifically tests explicit legacy launch
  // overrides, which are represented in each turn/start request.
  const original = readFileSync(path.join(env.CODEX_HOME, "config.toml"), "utf8");
  const config = original.replace(/^default_permissions = .*\n/m, "")
    .replace("guardian_approval = true", "guardian_approval = true\ndaemon_auto_start = false")
    .split("[permissions.fixture.filesystem]")[0];
  writeFileSync(path.join(codexHome, "config.toml"), config + '\n[tui]\nstatus_line = ["thread-id"]\n');
  mkdirSync(path.join(codexHome, "app-server-daemon"));
  writeFileSync(path.join(codexHome, "app-server-daemon/settings.json"), '{"updater":{"autoUpdateEnabled":false}}');
  const id = "00000000-0000-0000-0000-000000000665";
  const thread = { id, sessionId: id, preview: "", ephemeral: false, modelProvider: "fixture", createdAt: 1, updatedAt: 2,
    status: { type: "idle" }, cwd: main, cliVersion: "0.162.0", source: "cli", turns: [] };
  const connections = new Set();
  let resumed = false, started = false, submitted = null, active = null;
  const frame = (text) => {
    const payload = Buffer.from(JSON.stringify(text));
    if (payload.length < 126) return Buffer.concat([Buffer.from([0x81, payload.length]), payload]);
    const head = Buffer.alloc(4); head[0] = 0x81; head[1] = 126; head.writeUInt16BE(payload.length, 2);
    return Buffer.concat([head, payload]);
  };
  const server = net.createServer((socket) => {
    connections.add(socket); socket.on("close", () => connections.delete(socket));
    let buffer = Buffer.alloc(0), upgraded = false;
    const respond = (request) => {
      // The TUI's local MCP bearer token is disposable but unnecessary evidence.
      const params = request.params && { ...request.params }; if (params) delete params.config;
      trace("reconnect.rpc", { mode, recovered: resumed, message: { ...request, params } });
      if (request.id === undefined) return;
      let result;
      switch (request.method) {
        case "initialize": result = { userAgent: "fixture-reconnect" }; break;
        case "experimentalFeature/list": result = { data: ["api_key_model_discovery", "code_mode_host", "auth_elicitation"].map((name) => ({ name,
          stage: "stable", displayName: null, description: null, announcement: null, enabled: true, defaultEnabled: true })), nextCursor: null }; break;
        case "account/read": result = { account: { type: "apiKey" }, requiresOpenaiAuth: false }; break;
        case "model/list": result = { data: [], nextCursor: null }; break;
        case "config/read": result = { config: { model: "fixture-v2", model_provider: "fixture", tui: { status_line: ["thread-id"] },
          projects: { [main]: { trust_level: "trusted" } } }, origins: {}, layers: [] }; break;
        case "configRequirements/read": result = { requirements: null }; break;
        case "thread/start":
        case "thread/resume": {
          const starting = request.method === "thread/start";
          result = { thread, model: "fixture-v2", modelProvider: "fixture", cwd: main, runtimeWorkspaceRoots: [main],
            approvalPolicy: starting ? "never" : "on-request", approvalsReviewer: "user",
            sandbox: starting ? (mode === "full" ? { type: "dangerFullAccess" }
              : { type: "workspaceWrite", writableRoots: [], networkAccess: false, excludeTmpdirEnvVar: false, excludeSlashTmp: false })
              : { type: "readOnly" }, reasoningEffort: null };
          if (starting) { started = true; active = socket; }
          else { resumed = true; active = socket; }
          trace("reconnect.server-defaults", { mode, method: request.method, approvalPolicy: result.approvalPolicy, sandbox: result.sandbox });
          break;
        }
        case "turn/start":
          submitted = request.params;
          result = { turn: { id: "after-reconnect", items: [], status: "inProgress", error: null } }; break;
        case "thread/read": result = { thread }; break;
        case "thread/goal/get": result = { goal: null }; break;
        case "skills/list": result = { data: [] }; break;
        default:
          socket.write(frame({ id: request.id, error: { code: -32601, message: "fixture method not implemented" } })); return;
      }
      socket.write(frame({ id: request.id, result }));
      if (request.method === "turn/start") socket.write(frame({ method: "turn/completed", params: { threadId: id,
        turn: { id: "after-reconnect", items: [], status: "completed", error: null } } }));
    };
    socket.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      if (!upgraded) {
        const end = buffer.indexOf("\r\n\r\n"); if (end < 0) return;
        const headers = buffer.subarray(0, end).toString();
        const key = /Sec-WebSocket-Key: (.*)/i.exec(headers)?.[1].trim();
        if (!key) { socket.end(); return; }
        const accept = createHash("sha1").update(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
        socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
        buffer = buffer.subarray(end + 4); upgraded = true;
      }
      while (buffer.length >= 2) {
        const opcode = buffer[0] & 15, masked = Boolean(buffer[1] & 128);
        let length = buffer[1] & 127, offset = 2;
        if (length === 126) { if (buffer.length < 4) return; length = buffer.readUInt16BE(2); offset = 4; }
        if (length === 127) { if (buffer.length < 10) return; length = Number(buffer.readBigUInt64BE(2)); offset = 10; }
        if (buffer.length < offset + (masked ? 4 : 0) + length) return;
        const mask = buffer.subarray(offset, offset + 4); if (masked) offset += 4;
        const payload = Buffer.from(buffer.subarray(offset, offset + length));
        if (masked) payload.forEach((byte, index) => { payload[index] = byte ^ mask[index % 4]; });
        buffer = buffer.subarray(offset + length);
        if (opcode === 8) { socket.end(); return; }
        if (opcode === 1) respond(JSON.parse(payload.toString()));
      }
    });
    socket.on("error", (error) => trace("reconnect.socket-error", { code: error.code }));
  });
  server.listen(socketPath); await new Promise((resolve) => server.once("listening", resolve));
  const originalHome = env.CODEX_HOME;
  let t;
  try {
    env.CODEX_HOME = codexHome;
    t = terminal(`reconnect-${mode}`, ["-C", main, "-a", "never", "--sandbox", mode === "full" ? "danger-full-access" : "workspace-write", "--no-alt-screen"]);
    await waitFor(() => started && t.text().includes(id), "local TUI attached to fixture", 30000);
    t.key("SPIKE:reconnect-after", "draft-before-disconnect"); await delay(500);
    t.screen("before-disconnect");
    trace("reconnect.disconnect", { mode, thread: id }); active.destroy();
    await waitFor(() => resumed, "local TUI automatically reconnected", 30000);
    await delay(500); t.screen("recovered-draft"); t.key("\r", "submit-preserved-draft");
    await waitFor(() => submitted, "preserved launch permissions submitted", 30000);
    trace("reconnect.outcome", { mode, thread: id, submitted });
    await t.type("/exit"); await waitFor(() => t.exited, "reconnect TUI exit", 10000);
  } finally {
    t?.screen("reconnect-final");
    env.CODEX_HOME = originalHome;
    for (const socket of connections) socket.destroy(); server.close();
  }
}
