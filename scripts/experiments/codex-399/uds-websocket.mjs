// A minimal WebSocket client over a Unix domain socket, for the app-server
// daemon's control socket. Node's built-in WebSocket only dials TCP, and the
// experiment keeps to the standard library. Text frames only; a ping is
// answered, a close frame ends the connection.
import { createHash, randomBytes } from "node:crypto";
import net from "node:net";
import { once } from "node:events";

const GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

export const connectUnixWebSocket = async (socketPath) => {
  const socket = net.connect(socketPath);
  await once(socket, "connect");
  const key = randomBytes(16).toString("base64");
  socket.write(`GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ${key}\r\n\r\n`);
  const listeners = { message: [], close: [] };
  let buffer = Buffer.alloc(0);
  let upgraded = false;
  let fragments = [];
  const emit = (event, value) => { for (const listener of listeners[event]) listener(value); };
  const frame = (opcode, payload) => {
    const mask = randomBytes(4);
    const masked = Buffer.from(payload.map((byte, index) => byte ^ mask[index % 4]));
    let header;
    if (payload.length < 126) header = Buffer.from([0x80 | opcode, 0x80 | payload.length]);
    else if (payload.length < 65536) { header = Buffer.alloc(4); header[0] = 0x80 | opcode; header[1] = 0x80 | 126; header.writeUInt16BE(payload.length, 2); }
    else { header = Buffer.alloc(10); header[0] = 0x80 | opcode; header[1] = 0x80 | 127; header.writeBigUInt64BE(BigInt(payload.length), 2); }
    return Buffer.concat([header, mask, masked]);
  };
  const parse = () => {
    while (true) {
      if (buffer.length < 2) return;
      const fin = (buffer[0] & 0x80) !== 0;
      const opcode = buffer[0] & 0x0f;
      let length = buffer[1] & 0x7f;
      let offset = 2;
      if (length === 126) { if (buffer.length < 4) return; length = buffer.readUInt16BE(2); offset = 4; }
      else if (length === 127) { if (buffer.length < 10) return; length = Number(buffer.readBigUInt64BE(2)); offset = 10; }
      const maskedByServer = (buffer[1] & 0x80) !== 0;
      if (maskedByServer) offset += 4;
      if (buffer.length < offset + length) return;
      const payload = buffer.subarray(offset, offset + length);
      buffer = buffer.subarray(offset + length);
      if (opcode === 0x9) { socket.write(frame(0xa, payload)); continue; }
      if (opcode === 0x8) { socket.end(); emit("close", { code: payload.length >= 2 ? payload.readUInt16BE(0) : null }); continue; }
      if (opcode === 0x1 || opcode === 0x0) {
        fragments.push(payload);
        if (fin) { const text = Buffer.concat(fragments).toString("utf8"); fragments = []; emit("message", text); }
      }
    }
  };
  const ready = new Promise((resolve, reject) => {
    socket.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      if (!upgraded) {
        const end = buffer.indexOf("\r\n\r\n");
        if (end < 0) return;
        const head = buffer.subarray(0, end).toString();
        buffer = buffer.subarray(end + 4);
        const accept = createHash("sha1").update(key + GUID).digest("base64");
        if (!/ 101 /.test(head) || !head.includes(accept)) { reject(new Error(`upgrade refused: ${head.split("\r\n")[0]}`)); socket.destroy(); return; }
        upgraded = true;
        resolve();
      }
      parse();
    });
    socket.on("error", reject);
  });
  socket.on("close", () => emit("close", { code: null }));
  await ready;
  return {
    send: (text) => socket.write(frame(0x1, Buffer.from(text, "utf8"))),
    on: (event, listener) => listeners[event].push(listener),
    close: () => { try { socket.write(frame(0x8, Buffer.from([0x03, 0xe8]))); } catch {} socket.end(); },
  };
};
