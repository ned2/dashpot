// The fixture repository's pre-push hook: Git runs it with the remote's name
// and URL as arguments and one line per ref on stdin, before it sends any
// object. It reports, on one `PREPUSH {json}` line on stderr, which Git
// forwards in the push's own output: the URL's scheme class, the refs, which
// of the transport variables its environment holds (names only), and whether
// it ran sandboxed, by a control write outside every writable root. It always
// allows the push.
//
//   node prepush.mjs <outside directory> <remote name> <remote URL>
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const [outside, remote, url] = process.argv.slice(2);
const scheme = /^https:\/\//.test(url) ? "https" : /^ssh:\/\//.test(url) || /^[^/:]+:/.test(url) ? "ssh" : "other";
const refs = readFileSync(0, "utf8").trim().split("\n").filter(Boolean).map((line) => {
  const [localRef, , remoteRef, remoteSha] = line.split(" ");
  return { localRef, remoteRef, remoteIsNew: /^0+$/.test(remoteSha) };
});
let outsideWrite;
try {
  writeFileSync(path.join(outside, `prepush-${process.pid}`), "fixture\n");
  outsideWrite = { ok: true };
} catch (error) { outsideWrite = { ok: false, error: error.code ?? String(error.message).slice(0, 120) }; }
const names = ["GIT_CONFIG_COUNT", "GIT_SSH_COMMAND", "SSH_AUTH_SOCK", "GIT_SSL_CAINFO", "GH_CONFIG_DIR", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED"];
process.stderr.write(`PREPUSH ${JSON.stringify({ remote, scheme, refs, outsideWrite, env: names.filter((name) => process.env[name] !== undefined) })}\n`);
