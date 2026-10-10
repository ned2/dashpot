// Retain an Issue #648 run's trace for the repository: keep what each
// classifier check did, drop the classifier's prompt and reasoning, replace
// two forms of the fixture root the runner's `$ROOT` replacement does not
// reach, and write the trace gzipped. The runner is left as it ran, so the
// hashes the trace records still name it.
//
// A classifier record keeps, for each check, its stage, the action it
// judged, its severity, whether it blocked, its category, its status, model
// and usage, and the SHA-256 and length of the classifier's system prompt.
// It drops the system prompt's opening, the check's user-message tail once
// the action is read from it, and the verdict's text. Each flagged
// hand-back adds the warning the Lead received with the report, read from
// the run's classifier inputs, which are not retained.
//
// The two forms of the root: one is the slugged root Claude Code builds
// from a trial's working directory for its task output files. The other is
// the end of a root path a record's text was cut through: the runner cuts a
// long text to its tail before replacing paths in it, so a tail may open
// partway through the root, which becomes `…$ROOT`.
//
//   node retain.mjs <run root> <out.jsonl.gz>
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { gzipSync } from "node:zlib";

const [root, out] = process.argv.slice(2);
assert(root && out && out.endsWith(".jsonl.gz"), "Pass the run root and an output .jsonl.gz path");
const raw = readFileSync(path.join(root, "trace.jsonl"), "utf8");
// Claude Code names a project's directory by its path with every
// character outside [A-Za-z0-9] turned into `-`.
const slug = (where) => path.resolve(where).replace(/[^A-Za-z0-9]/g, "-");
const forms = [[path.resolve(root), "$ROOT"], [slug(root), "$ROOT_SLUG"]];
let cut = 0;
// A text that opens with the last 8 or more characters of a root form, and
// not with the whole form, was cut through it.
const mend = (value) => {
  if (typeof value === "string") {
    for (const [form, placeholder] of forms) {
      for (let length = form.length - 1; length >= 8; length--) {
        if (value.startsWith(form.slice(-length))) { cut += 1; return `…${placeholder}${value.slice(length)}`; }
      }
    }
    return value;
  }
  if (Array.isArray(value)) return value.map(mend);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, inner]) => [key, mend(inner)]));
  return value;
};
const records = raw.trim().split("\n").map((line) => mend(JSON.parse(line.split(slug(root)).join("$ROOT_SLUG"))));

// The runner kept the first 3000 characters of a verdict.
const VERDICT_KEPT = 3000;
const denied = new Set(records.filter((record) => record.kind === "lead.stream" && record.subtype === "permission_denied").map((record) => record.trial));
const check = (record) => {
  // The check's user message is a transcript whose last line is the action
  // under review, as `{"<tool>": <input>}`.
  const tail = record.lastUserTail;
  const body = tail.slice(0, tail.lastIndexOf("</transcript>")).trimEnd();
  const [[tool, input]] = Object.entries(JSON.parse(body.slice(body.lastIndexOf("\n") + 1)));
  const verdict = record.verdict;
  const stage = record.maxTokens === 64 ? 1 : 2;
  const severity = verdict.match(/<severity>(\d+)/)?.[1];
  const verdictCut = verdict.length >= VERDICT_KEPT;
  // Stage 2 names a category only when it blocks. A verdict cut before its
  // severity is judged by whether the Lead was denied in that trial.
  const blocked = stage === 1 ? null : verdict.includes("<category>") || (verdictCut && severity === undefined && denied.has(record.trial));
  return { kind: record.kind, receipt: record.receipt, receiptTime: record.receiptTime, trial: record.trial, case: record.case, stage, tool, input,
    severity: severity === undefined ? null : Number(severity), blocked, category: verdict.match(/<category>(.*?)<\/category>/s)?.[1] ?? null, verdictCut,
    status: record.status, model: record.model, responseModel: record.responseModel, usage: record.usage, stopReason: record.stopReason,
    authorization: record.authorization, tools: record.tools, stream: record.stream, error: record.error,
    systemSHA256: record.systemSHA256, systemLength: record.systemLength, markers: record.markers,
    forwarded: record.forwarded, totalForwarded: record.totalForwarded };
};

// The warning a flagged hand-back reached the Lead under, as the Lead's next
// check rendered the Lead's transcript: one JSON entry per line.
const entries = (input) => input.messages.flatMap((message) => typeof message.content === "string" ? [message.content] : message.content.map((part) => part.text ?? ""))
  .flatMap((text) => text.split("\n")).flatMap((line) => { try { return Object.values(JSON.parse(line)); } catch { return []; } })
  .filter((value) => typeof value === "string");
const warnings = new Map();
for (const line of readFileSync(path.join(root, "classifier-inputs.jsonl"), "utf8").trim().split("\n")) {
  const input = JSON.parse(line);
  if (warnings.has(input.trial)) continue;
  const found = entries(input).map((entry) => entry.match(/<agent-message from="(a[0-9a-f]{16})">\s*(SECURITY WARNING: [^\n]*)/)).find(Boolean);
  if (found) warnings.set(input.trial, { kind: "handback.warning", trial: input.trial, from: found[1], text: found[2] });
}

const kept = [];
for (const record of records) {
  if (record.kind === "trial.end" && warnings.has(record.trial)) kept.push(warnings.get(record.trial));
  kept.push(record.kind === "classifier.forwarded" ? check(record) : record);
}
const text = kept.map((record) => JSON.stringify(record)).join("\n") + "\n";
for (const leak of [path.resolve(root), path.basename(root), os.homedir(), slug(os.homedir())]) {
  assert(!text.includes(leak), `the retained trace still holds ${leak === path.basename(root) ? "the fixture root's name" : "a local path"}`);
}
for (const internal of ["</transcript>", "<severity>", "<thinking>", "security monitor"]) {
  assert(!text.includes(internal), `the retained trace still holds the classifier's ${internal}`);
}
writeFileSync(out, gzipSync(text, { level: 9 }));
console.log(JSON.stringify({ retained: out, records: kept.length, warnings: warnings.size, replaced: raw.split(slug(root)).length - 1, cut,
  sha256: createHash("sha256").update(text).digest("hex") }));
