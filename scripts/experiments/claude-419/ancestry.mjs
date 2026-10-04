// Walk /proc upwards from a PID, recording each ancestor's identity. The
// walk ends at the experiment runner (SPIKE_STOP_PID) so the operator's own
// session above it never enters the trace.
import { readFileSync, readlinkSync } from "node:fs";

export const describe = (pid) => {
  const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
  const close = stat.lastIndexOf(")");
  const comm = stat.slice(stat.indexOf("(") + 1, close);
  const fields = stat.slice(close + 2).split(" ");
  let cmdline = "";
  try { cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8").split("\0").filter(Boolean).slice(0, 6).join(" ").slice(0, 200); } catch {}
  let cwd;
  try { cwd = readlinkSync(`/proc/${pid}/cwd`); } catch {}
  return { pid, ppid: Number(fields[1]), comm, startTime: Number(fields[19]), cmdline, cwd };
};

export const ancestry = (pid, limit = 12, stop = Number(process.env.SPIKE_STOP_PID ?? 1)) => {
  const chain = [];
  let current = pid;
  while (current > 1 && chain.length < limit) {
    let entry;
    try { entry = describe(current); } catch { break; }
    chain.push(entry);
    if (current === stop) break;
    current = entry.ppid;
  }
  return chain;
};
