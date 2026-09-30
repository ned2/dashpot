// Stand-in for xdg-open and the browser launchers on the fixture PATH: it
// reports what Claude Code asked to open and opens nothing. The runner's shim
// passes the launcher's name first.
const record = { name: process.argv[2], args: process.argv.slice(3).map((arg) => arg.slice(0, 300)) };
try {
  await fetch(process.env.SPIKE_SINK + "/opener", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(3000) });
} catch (error) {
  process.stderr.write(`opener publish failed: ${error}\n`);
}
