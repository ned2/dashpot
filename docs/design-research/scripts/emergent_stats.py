"""For each emergent candidate, the groups that carry it: pairwise overlap, note span, evidence."""

import json
from collections import Counter
from itertools import combinations
from pathlib import Path

H = Path(__file__).parent
export = {e["id"]: e for e in json.loads((H / "export.json").read_text())}
runs = {}
for n in ("mechanism-A", "mechanism-B", "tension-A", "tension-B"):
    for g in json.loads((H / "clusters" / f"{n}.json").read_text())["groups"]:
        runs[(n, g["name"])] = set(g["members"])

CANDS = {
    "E1 staleness": [("mechanism-A", "Recorded knowledge drifts"), ("mechanism-B", "A stored representation has no change trigger"),
                     ("tension-A", "Fixed review items"), ("tension-B", "Documentation freshness"), ("tension-B", "Item stability"),
                     ("mechanism-A", "Spaced retrieval assumes")],
    "E2 habituation": [("mechanism-A", "Vigilance over reliable"), ("mechanism-B", "Repeated monitoring"), ("tension-B", "Trust in automation"),
                       ("tension-A", "Review thoroughness against")],
    "E3 confidence": [("mechanism-A", "Assistance inflates"), ("mechanism-B", "Fluent, answer-visible"), ("tension-A", "Explanation and transparency"),
                      ("mechanism-A", "People follow the assistant")],
    "E4 self-report": [("mechanism-A", "Self-report instruments score"), ("mechanism-B", "Self-report instruments capture"),
                       ("tension-A", "Self-report against telemetry"), ("tension-B", "Survey instrument convenience")],
    "E5 routing": [("mechanism-A", "Asking a colleague"), ("mechanism-B", "Asking AI first"), ("tension-A", "Asking a person"),
                   ("tension-B", "Knowledge in artifacts"), ("mechanism-A", "Knowing who knows what"), ("mechanism-B", "Transactive memory forms")],
    "E6 regenerability": [("mechanism-A", "Comprehension is layered"), ("mechanism-B", "Comprehension is question-driven"),
                          ("mechanism-B", "Restructuring code for the reader"), ("mechanism-B", "Regenerating documentation"),
                          ("tension-B", "Comprehension depth"), ("tension-A", "Holding the program")],
    "E7 suspension": [("mechanism-A", "Working state held only"), ("mechanism-B", "A finite working store"), ("tension-B", "Context budget"),
                      ("tension-A", "Compressed handover")],
    "E8 authorship": [("mechanism-A", "Knowledge concentrated in few authors"), ("mechanism-B", "AI authorship severs"),
                      ("tension-A", "Authorship as evidence")],
    "E9 invisible": [("mechanism-A", "Understanding effects go unobserved"), ("mechanism-B", "Instruments count output"),
                     ("mechanism-A", "Activity and output metrics"), ("tension-A", "Vendor evidence"), ("tension-B", "Research rigour")],
}


def find(run, prefix):
    for (r, name), m in runs.items():
        if r == run and name.startswith(prefix):
            return name, m
    raise KeyError((run, prefix))


for cand, specs in CANDS.items():
    print("\n==", cand)
    got = [(r, *find(r, p)) for r, p in specs]
    for r, name, m in got:
        print(f"  [{r}] {name[:60]} n={len(m)} notes={len({x.split(':')[0] for x in m})}")
    for (r1, n1, m1), (r2, n2, m2) in combinations(got, 2):
        o = len(m1 & m2) / min(len(m1), len(m2))
        if o >= 0.3:
            print(f"  overlap {o:.2f}: [{r1}] {n1[:40]} ~ [{r2}] {n2[:40]}")
    # cards in >=2 of the groups
    cnt = Counter(x for _, _, m in got for x in m)
    core = [x for x, c in cnt.items() if c >= 2]
    notes = Counter(x.split(":")[0] for x in core)
    ev = Counter(export[x]["evidence"] for x in core)
    print(f"  core (in >=2 groups): {len(core)} cards, notes {dict(notes.most_common())}, evidence {dict(ev.most_common())}")
    top = [x for x in core if export[x]["evidence"] in "CM"]
    print("  C/M cards:", " ".join(sorted(top)[:25]))
