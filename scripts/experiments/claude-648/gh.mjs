// A recording `gh` for the Issue #648 fixture. Each call is reported to the
// runner's sink with its arguments and outcome. `pr merge <n>` merges the
// fixture PR's Branch into `main` at the fixture's bare remote, so a merged
// Branch is integrated there as a real squash merge on GitHub would leave
// it; every other call succeeds with no output.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const argv = process.argv.slice(2);
let outcome = { status: 0, stdout: "", stderr: "" };
if (argv[0] === "pr" && argv[1] === "merge") {
  const number = argv[2];
  const pr = JSON.parse(readFileSync(process.env.SPIKE_PRS, "utf8"))[number];
  if (!pr) {
    outcome = { status: 1, stdout: "", stderr: `GraphQL: Could not resolve to a PullRequest with the number of ${number}.\n` };
  } else {
    const scratch = mkdtempSync(path.join(os.tmpdir(), "gh-merge-"));
    try {
      const git = (...args) => execFileSync("git", args, { cwd: scratch, stdio: "pipe" });
      git("clone", "--quiet", process.env.SPIKE_REMOTE, ".");
      git("merge", "--no-ff", "--quiet", "-m", `Merge pull request #${number} from ${pr.branch}`, `origin/${pr.branch}`);
      git("push", "--quiet", "origin", "main");
      outcome.stdout = `✓ Squashed and merged pull request #${number}\n`;
    } catch (error) {
      outcome = { status: 1, stdout: "", stderr: `merge failed: ${String(error.stderr ?? error).slice(0, 300)}\n` };
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  }
}
try {
  await fetch(`${process.env.SPIKE_SINK}/gh`, { method: "POST", body: JSON.stringify({ argv, cwd: process.cwd(), status: outcome.status }) });
} catch {}
process.stdout.write(outcome.stdout);
process.stderr.write(outcome.stderr);
process.exit(outcome.status);
