"""Build claim-inventory.md and the shuffled clustering export from the cards."""

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).parent
DOCS = Path(__file__).resolve().parents[1]  # docs/design-research (was an absolute path as run)
codes = json.loads((HERE / "note-codes.json").read_text())
by_code = {v: k for k, v in codes.items()}


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))  # repo scripts/ (was an absolute path as run)
import check_docs


def heading_slugs(slugname: str) -> dict[str, str]:
    """Map each heading's text to the anchor the docs gate assigns it (duplicates numbered)."""
    text = (DOCS / f"{slugname}.md").read_text()
    masked = check_docs.mask_code(text, spans=False)
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    for heading in check_docs.iter_headings(masked):
        s = check_docs.slugify_heading(heading)
        if not s:
            continue
        n = seen.get(s, 0)
        seen[s] = n + 1
        anchor = s if n == 0 else f"{s}-{n}"
        key = heading.strip()
        # first occurrence wins for the plain-text key; a later duplicate is keyed by index too
        out.setdefault(key, anchor)
        out[f"{key}#{n}"] = anchor
    return out


placements = {}
if (HERE / "placements.json").exists():
    placements = json.loads((HERE / "placements.json").read_text())

all_cards = []
sections = []
for code in sorted(by_code):
    slugname = by_code[code]
    cards = json.loads((HERE / "cards" / f"{code}.json").read_text())
    hslugs = heading_slugs(slugname)
    lines = [f"---\nstatus: research\ndate: 2026-09-16\n---\n\n# {code}: {slugname}", "",
             f"Cards read from [{slugname}.md](../{slugname}.md) — {len(cards)} in all. Part of the [claim inventory](../claim-inventory.md).", ""]
    for c in cards:
        anchor = hslugs.get(c["anchor"])
        if anchor is None:
            # try a loose match
            cands = [h for h in hslugs if c["anchor"].lower() in h.lower() or h.lower() in c["anchor"].lower()]
            anchor = hslugs[cands[0]] if len(cands) == 1 else None
        link = f"[{c['anchor']}](../{slugname}.md#{anchor})" if anchor else c["anchor"]
        tags = [c["kind"], c["evidence"]]
        if c["unit"] not in ("", "-"):
            tags.append(c["unit"])
        if c["actor"] not in ("", "-"):
            tags.append(c["actor"])
        bits = [f"**{c['id']}** ({', '.join(tags)}) {c['claim']}"]
        if c["figures"]:
            bits.append(f"Figures: {c['figures']}.")
        if c["where"]:
            bits.append(f"Where: {c['where']}.")
        if c["source"]:
            bits.append(f"Source: {c['source']}.")
        bits.append(f"From: {link}.")
        if c["counterpart"] == "none":
            bits.append("No counterpart in another note.")
        if c["restates"]:
            bits.append(f"Restates {c['restates']}.")
        if c["id"] in placements:
            bits.append(f"Placement: {placements[c['id']]}.")
        lines.append("- " + " ".join(bits))
        all_cards.append({**c, "note": slugname})
    (DOCS / "claim-inventory").mkdir(exist_ok=True)
    (DOCS / "claim-inventory" / f"{code}-{slugname}.md").write_text("\n".join(lines) + "\n")

key = "\n".join(f"| {code} | [{by_code[code]}]({by_code[code]}.md) | [{len(json.loads((HERE / 'cards' / f'{code}.json').read_text()))} cards](claim-inventory/{code}-{by_code[code]}.md) |" for code in sorted(by_code))
head = f"""---
status: research
date: 2026-09-16
---

# Claim inventory

Every research note in this folder decomposed into atomic idea cards, as
the [thematic analysis plan](thematic-analysis-plan.md#step-1-the-claim-inventory)
specifies: one card per claim, mechanism, definition, practice, tool,
policy, argument, measurement, or substantive dead end, in the note's own
terms, with its figures verbatim and a link to the section it was read
from. One file per note, linked from the key below. The cards were extracted by agents given the note bodies alone, in
a scratchpad, with no access to this folder's index, synthesis, analysis,
or plan; a stratified sample was verified against the sections. Kind and
evidence code follow the plan's schema (C causal, M measured, Q
qualitative, T testimonial, A argument, — none). A card marked *restates*
repeats an earlier card in the same note and was dropped from the
clustering export; *no counterpart in another note* carries a mapping
table's claim that the idea is new to the corpus. The clustering export
used the opaque note codes below, shuffled, so that no clusterer saw a
note's name. Each exported card also carries its *placement* on the
frame the [synthesis](synthesis.md) and [analysis](analysis.md) fixed,
in the codes listed after the key; the placement was made by an agent
that saw the frame and the export and nothing else, and the
[themes](themes.md) note reads the results.

{len(all_cards)} cards across {len(by_code)} notes.

## Key

| Code | Note | Cards |
| --- | --- | --- |
{key}

## Placement codes

`Placement: W/D/E X.. G.. T..` — one value or `-` on each of the three
axes, then any tensions, gaps, and index themes the card bears on.

**W, where the friction lives:** W1 task start; W2 inside the loop,
each step; W3 hand-off, agent done and before commit or review; W4
review and merge; W5 continuous, scheduled and independent of any
task; W6 onboarding and team.

**D, what it demands of the person:** D1 generate or predict before
seeing; D2 write; D3 explain, teach back; D4 recall; D5 verify or
approve; D6 read; D7 navigate or ask; D8 nothing, the artifact exists.

**E, how it is enforced:** E1 a tool default; E2 an opt-in mode; E3 a
personal practice; E4 a policy enforced socially; E5 a gate enforced
by tooling.

**X, tensions:** X1 speed against understanding; X2 text against model;
X3 expert against novice; X4 default against practice; X5 artifact
against act; X6 measure against Goodhart; X7 interrupt against flow; X8
saved against relocated; X9 individual against team; X10 session
against work graph; X11 rate against capacity; X12 a named person
against many hands.

**G, gaps:** G1 no retention study of a codebase model over weeks under
agentic work; G2 no comprehension effect measured for any approval or
plan gate; G3 no human evaluation of a generated wiki, map, or
walkthrough; G4 no code change connected to review scheduling; G5 no
record that a person read a generated artifact; G6 no validated
instrument for ownership, motivation, or flow under delegation; G7 no
company describes an enforced comprehension ritual; G8 no editor or
agent CLI ships a manual-trigger or generate-first default; G9 no
source addresses code whose only author was never a person; G10 no
AI-coding source cites the human-factors literature it restates; G11 no
source treats an automated actor as an awareness subject; G12 no
measure of what a human recovers from a compaction summary or handoff
artifact; G13 no measure of the coordination cost an agent imposes on a
team; G14 no before-and-after measure of reviewer hours per change; G15
no instrument for a team's shared model of its codebase; G16 no measure
of conflict or quality against concurrent agent runs; G17 no measure of
whether a WIP limit or batch rule changes what a team member
understands.

**T, index themes:** T1 cognitive debt; T2 the friction that keeps
understanding; T3 work above the session.

"""
(DOCS / "claim-inventory.md").write_text(head.rstrip("\n") + "\n")

# clustering export: no slug, shuffled, restatements dropped
export = [
    {"id": c["id"], "claim": c["claim"], "figures": c["figures"], "kind": c["kind"], "evidence": c["evidence"]}
    for c in all_cards
    if not c["restates"]
]
random.Random(20260916).shuffle(export)
(HERE / "export.json").write_text(json.dumps(export, ensure_ascii=False))
(HERE / "all_cards.json").write_text(json.dumps(all_cards, ensure_ascii=False))
text = "\n".join(f"{e['id']} [{e['kind']}/{e['evidence']}] {e['claim']}" + (f" ({e['figures']})" if e["figures"] else "") for e in export)
(HERE / "export.txt").write_text(text)
print(len(all_cards), "cards;", len(export), "in export;", len(text.split()), "words in export")
