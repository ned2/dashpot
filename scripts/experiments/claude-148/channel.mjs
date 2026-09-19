// A development channel for the Claude Code 148 experiment: a stdio MCP
// server that declares the `claude/channel` capability, accepts relocation
// requests over a loopback HTTP control endpoint, and pushes each one into
// the hosting session as a `notifications/claude/channel` event. It reports
// only metadata (its identity environment, ancestry, and message shapes) to
// the runner's sink; a request's text is retained only as its SPIKE label.
import { createInterface } from "node:readline";
import http from "node:http";
import { ancestry } from "./ancestry.mjs";

const sink = process.env.SPIKE_SINK;
const post = (record) => fetch(sink + "/channel", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(3000) }).catch(() => {});
const send = (message) => process.stdout.write(JSON.stringify(message) + "\n");
const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CLAUDE") && key !== "CLAUDE_CODE_MESSAGING_TOKEN"));

const control = http.createServer(async (req, res) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  const body = raw ? JSON.parse(raw) : {};
  if (req.url === "/push") {
    // The relocation request Dashpot would deliver; the label is the only content kept.
    send({ jsonrpc: "2.0", method: "notifications/claude/channel", params: { content: body.content, meta: body.meta ?? {} } });
    await post({ phase: "pushed", label: body.content.match(/SPIKE:[a-z0-9-]+/)?.[0] ?? null, meta: body.meta ?? {} });
    res.end("ok");
    return;
  }
  res.writeHead(404);
  res.end();
});
control.listen(0, "127.0.0.1", () => {
  post({ phase: "listening", control: `http://127.0.0.1:${control.address().port}`, pid: process.pid, ppid: process.ppid, cwd: process.cwd(), env, ancestry: ancestry(process.ppid) });
});

createInterface({ input: process.stdin }).on("line", async (line) => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  if (message.method === "initialize") {
    send({ jsonrpc: "2.0", id: message.id, result: {
      protocolVersion: "2025-06-18",
      capabilities: { experimental: { "claude/channel": {} }, tools: {} },
      serverInfo: { name: "dashpot-fixture-channel", version: "0" },
      instructions: "Events from this channel are relocation requests from Dashpot. Follow the SPIKE label each carries, then call ack.",
    } });
    await post({ phase: "initialize", protocolVersion: message.params?.protocolVersion, clientInfo: message.params?.clientInfo, clientCapabilities: Object.keys(message.params?.capabilities ?? {}) });
  } else if (message.method === "tools/list") {
    send({ jsonrpc: "2.0", id: message.id, result: { tools: [{ name: "ack", description: "Acknowledge a Dashpot relocation request with the session's current working directory.", inputSchema: { type: "object", properties: { cwd: { type: "string" }, outcome: { type: "string" } }, required: ["cwd", "outcome"] } }] } });
  } else if (message.method === "tools/call") {
    await post({ phase: "ack", tool: message.params?.name, arguments: message.params?.arguments });
    send({ jsonrpc: "2.0", id: message.id, result: { content: [{ type: "text", text: "acknowledged" }] } });
  } else if (message.method === "ping") {
    send({ jsonrpc: "2.0", id: message.id, result: {} });
  } else if (message.id !== undefined && message.method) {
    send({ jsonrpc: "2.0", id: message.id, error: { code: -32601, message: `unsupported: ${message.method}` } });
  } else if (message.method) {
    await post({ phase: "notification", method: message.method, paramKeys: Object.keys(message.params ?? {}) });
  }
});
process.stdin.on("end", () => { post({ phase: "stdin-closed" }).finally(() => process.exit(0)); });
