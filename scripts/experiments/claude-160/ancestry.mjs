// Walk /proc upwards from a PID, recording each ancestor's identity.
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

export const ancestry = (pid, limit = 12) => {
  const chain = [];
  let current = pid;
  while (current > 1 && chain.length < limit) {
    let entry;
    try { entry = describe(current); } catch { break; }
    chain.push(entry);
    current = entry.ppid;
  }
  return chain;
};
