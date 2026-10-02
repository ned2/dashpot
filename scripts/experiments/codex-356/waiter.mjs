// Detached host watcher for the Codex 356 acceptance run: started by a
// SessionEnd hook in a session of its own, as Dashpot's settler is, it
// watches the hook's Codex host for 15 s and reports when, if ever, the host
// exited, measured from the moment the hook began.
import { existsSync } from "node:fs";

const [host, hookBegan, session] = [Number(process.argv[2]), Number(process.argv[3]), process.argv[4]];
const watchMs = 15000;
const began = Date.now();
let exitedSinceHookBegan = null;
while (Date.now() - began < watchMs) {
  if (!existsSync(`/proc/${host}`)) { exitedSinceHookBegan = Date.now() - hookBegan; break; }
  await new Promise((resolve) => setTimeout(resolve, 25));
}
await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", signal: AbortSignal.timeout(2500),
  body: JSON.stringify({ kind: "waiter", session, pid: process.pid, host, startedSinceHookBegan: began - hookBegan, exitedSinceHookBegan, hostAliveAtEnd: existsSync(`/proc/${host}`) }) }).catch(() => {});
