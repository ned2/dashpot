// Process identity and traced variables read from /proc. Only the variables
// in TRACED are ever recorded from a process's environment, and only from
// processes whose environment names the fixture's configuration directory;
// another process's environment is matched against that directory and never
// recorded, so the operator's own processes and variables never enter the
// trace.
import { readFileSync, readlinkSync } from "node:fs";

// The synthetic markers the run sets, and direnv's record of what it loaded.
// The markers' values are fixture labels, never credentials.
export const TRACED = ["DASHPOT_274_MARKER", "DASHPOT_274_TOKEN", "DIRENV_DIR"];

const environ = (pid) => readFileSync(`/proc/${pid}/environ`, "utf8").split("\0");

export const describe = (pid) => {
  const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
  const close = stat.lastIndexOf(")");
  const comm = stat.slice(stat.indexOf("(") + 1, close);
  const fields = stat.slice(close + 2).split(" ");
  let cmdline = "";
  try { cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8").split("\0").filter(Boolean).join(" "); } catch {}
  let cwd;
  try { cwd = readlinkSync(`/proc/${pid}/cwd`); } catch {}
  return { pid, ppid: Number(fields[1]), comm, startTime: Number(fields[19]), cmdline, cwd };
};

// Whether a process belongs to the fixture: its environment names the
// fixture's configuration directory.
export const inFixture = (pid, configHome) => {
  try { return environ(pid).includes(`XDG_CONFIG_HOME=${configHome}`); } catch { return false; }
};

// The traced variables in a fixture process's environment, null for an absent one.
export const markers = (pid) => {
  const found = Object.fromEntries(TRACED.map((name) => [name, null]));
  for (const entry of environ(pid)) {
    const at = entry.indexOf("=");
    const name = entry.slice(0, at);
    if (TRACED.includes(name)) found[name] = entry.slice(at + 1);
  }
  return found;
};

// The chain from a pid upwards, each fixture process with its markers. The
// walk ends at the runner, or at the first process outside the fixture,
// which is recorded by name only.
export const ancestry = (pid, configHome, stop, limit = 16) => {
  const chain = [];
  let current = pid;
  while (current > 1 && chain.length < limit) {
    let entry;
    try { entry = describe(current); } catch { break; }
    if (current === stop || !inFixture(current, configHome)) {
      chain.push({ pid: entry.pid, comm: entry.comm, outside: current !== stop, runner: current === stop });
      break;
    }
    let found = null;
    try { found = markers(current); } catch {}
    // The whole command line: the runner shortens it once its paths are
    // placeholders, so no fixture path is cut short of being replaced.
    chain.push({ ...entry, markers: found });
    current = entry.ppid;
  }
  return chain;
};
