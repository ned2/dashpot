// A stdio MCP server for the Codex 663 run whose startup the runner holds.
// It reads newline-delimited JSON-RPC from Codex, but answers nothing until
// the gate file exists, so a thread that requires it stays in MCP startup.
// Then it answers `initialize` and lists no tools. Each step is appended to
// the status file as one JSON line with this process's pid and the time, so
// the runner can see when startup began, when it was released and when the
// process ended.
//
//   node mcp-blocked.mjs <status file> <gate file>
import { appendFileSync, existsSync } from "node:fs";

const [statusPath, gatePath] = process.argv.slice(2);
const status = (event, extra = {}) => appendFileSync(statusPath, JSON.stringify({ event, pid: process.pid, at: Date.now(), ...extra }) + "\n");
const reply = (message) => process.stdout.write(JSON.stringify(message) + "\n");
status("start");

const queue = [];
let open = false;
let buffer = "";
const handle = (message) => {
  if (message.method === "initialize") {
    status("initialize-answered");
    reply({ jsonrpc: "2.0", id: message.id, result: { protocolVersion: message.params?.protocolVersion ?? "2025-06-18",
      capabilities: { tools: {} }, serverInfo: { name: "fixture-blocked", version: "0" } } });
  } else if (message.method === "tools/list") {
    reply({ jsonrpc: "2.0", id: message.id, result: { tools: [] } });
  } else if (message.id !== undefined && message.method) {
    reply({ jsonrpc: "2.0", id: message.id, error: { code: -32601, message: "fixture" } });
  }
};
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let newline;
  while ((newline = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, newline).trim();
    buffer = buffer.slice(newline + 1);
    if (!line) continue;
    let message;
    try { message = JSON.parse(line); } catch { continue; }
    if (message.method === "initialize") status("initialize-received");
    if (open) handle(message); else queue.push(message);
  }
});
process.stdin.on("end", () => { status("stdin-end"); process.exit(0); });
for (const signal of ["SIGTERM", "SIGINT", "SIGHUP"]) process.on(signal, () => { status("signal", { signal }); process.exit(0); });
const timer = setInterval(() => {
  if (open || !existsSync(gatePath)) return;
  open = true;
  clearInterval(timer);
  status("gate-open");
  for (const message of queue.splice(0)) handle(message);
}, 100);
