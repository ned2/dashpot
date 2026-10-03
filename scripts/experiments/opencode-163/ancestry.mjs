// Walk /proc upwards from a PID, recording each ancestor's identity. The walk
// ends at the experiment runner (SPIKE_STOP_PID), or at the first ancestor
// outside the fixture, which is recorded by name only, so the operator's own
// processes above a detached server never enter the trace.
import { readFileSync, readlinkSync } from "node:fs";

export const describe = (pid) => {
  const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
  const close = stat.lastIndexOf(")");
  const comm = stat.slice(stat.indexOf("(") + 1, close);
  const fields = stat.slice(close + 2).split(" ");
  let cmdline = "";
  try { cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8").split("\0").filter(Boolean).slice(0, 8).join(" "); } catch {}
  let cwd, exe;
  try { cwd = readlinkSync(`/proc/${pid}/cwd`); } catch {}
  try { exe = readlinkSync(`/proc/${pid}/exe`); } catch {}
  return { pid, ppid: Number(fields[1]), pgrp: Number(fields[2]), sid: Number(fields[3]), comm, startTime: Number(fields[19]), cmdline, exe, cwd };
};

// Whether a process belongs to the fixture: its environment names the
// fixture's configuration directory.
export const inFixture = (pid, marker = process.env.XDG_CONFIG_HOME) => {
  try { return readFileSync(`/proc/${pid}/environ`, "utf8").includes(`XDG_CONFIG_HOME=${marker}\0`); } catch { return false; }
};

export const ancestry = (pid, limit = 12, stop = Number(process.env.SPIKE_STOP_PID ?? 1)) => {
  const chain = [];
  let current = pid;
  while (current > 0 && chain.length < limit) {
    let entry;
    try { entry = describe(current); } catch { break; }
    if (current !== stop && !inFixture(current)) {
      chain.push({ pid: entry.pid, comm: entry.comm, outside: true });
      break;
    }
    chain.push(entry);
    if (current === stop) break;
    current = entry.ppid;
  }
  return chain;
};
