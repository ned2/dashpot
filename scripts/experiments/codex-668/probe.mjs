// The shell command the fixture model asks Codex to run for Issue #668. It
// runs inside the session's sandbox, which has no network, so it reports by
// printing one `PROBE {...}` line that Codex returns to the fixture model as
// the call's output. It records where the command runs, which thread it
// belongs to, and whether it may write each target: the source checkout and
// the managed checkout a tool created. A target written with an `@cwd/`
// prefix is taken from the command's own directory.
//
//   node probe.mjs <label> <write target>...
import { rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const [label, ...targets] = process.argv.slice(2);
const attempt = (operation) => {
  try { operation(); return { ok: true }; } catch (error) { return { ok: false, code: error.code ?? String(error) }; }
};
// A write that succeeds is removed at once, so no checkout is left changed.
const writes = targets.map((target) => {
  const resolved = target.startsWith("@cwd/") ? path.join(process.cwd(), target.slice("@cwd/".length)) : target;
  const result = attempt(() => writeFileSync(resolved, "probe\n"));
  if (result.ok) rmSync(resolved, { force: true });
  return [resolved, result];
});
console.log("PROBE " + JSON.stringify({ label, cwd: process.cwd(), thread: process.env.CODEX_THREAD_ID ?? null, writes }));
