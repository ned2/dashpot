"""Validate the extracted cards: schema, id order, restates, anchors, caps."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
codes = json.loads((HERE / "note-codes.json").read_text())
by_code = {v: k for k, v in codes.items()}
KINDS = {"finding", "mechanism", "definition", "practice", "tool", "policy", "argument", "measurement", "dead-end"}
EV = {"C", "M", "Q", "T", "A", "-"}
KEYS = ["id", "claim", "figures", "kind", "evidence", "unit", "where", "actor", "source", "anchor", "counterpart", "restates"]


def headings(code):
    hs = []
    for line in (HERE / "bodies" / f"{code}.md").read_text().split("\n"):
        if line.startswith("## ") or line.startswith("### "):
            hs.append(line.lstrip("#").strip())
    return hs


def norm(s):
    s = s.strip().lstrip("#").strip()
    s = re.sub(r"[*_`]", "", s)
    return re.sub(r"\s+", " ", s).lower()


problems = []
total = 0
per_note = {}
for p in sorted(q for q in (HERE / "cards").glob("N*.json") if re.fullmatch(r"N\d\d", q.stem)):
    code = p.stem
    try:
        cards = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        problems.append(f"{code}: bad JSON: {e}")
        continue
    hs = {norm(h): h for h in headings(code)}
    ids = []
    for i, c in enumerate(cards, 1):
        missing = [k for k in KEYS if k not in c]
        extra = [k for k in c if k not in KEYS]
        if missing or extra:
            problems.append(f"{code}:{i} keys missing={missing} extra={extra}")
        cid = c.get("id", "")
        if cid != f"{code}:{i}":
            problems.append(f"{code}:{i} id is {cid!r}")
        ids.append(cid)
        if c.get("kind") not in KINDS:
            problems.append(f"{cid} kind {c.get('kind')!r}")
        if c.get("evidence") not in EV:
            problems.append(f"{cid} evidence {c.get('evidence')!r}")
        cap = 60 if c.get("kind") == "measurement" else 40
        n = len(str(c.get("claim", "")).split())
        if n > cap + 5:
            problems.append(f"{cid} claim {n} words (cap {cap})")
        r = c.get("restates", "")
        if r and (r not in ids[:-1]):
            problems.append(f"{cid} restates {r!r} not an earlier id")
        a = norm(str(c.get("anchor", "")))
        if a not in hs:
            # tolerate a trailing-colon or partial match
            cands = [h for h in hs if a and (a in h or h in a)]
            if len(cands) == 1:
                c["anchor"] = hs[cands[0]]
            else:
                problems.append(f"{cid} anchor {c.get('anchor')!r} not a heading")
        if c.get("counterpart") not in ("", "none"):
            problems.append(f"{cid} counterpart {c.get('counterpart')!r}")
    p.write_text(json.dumps(cards, indent=1, ensure_ascii=False))
    per_note[code] = (len(cards), Counter(c["kind"] for c in cards), sum(1 for c in cards if c.get("restates")), sum(1 for c in cards if c.get("counterpart") == "none"))
    total += len(cards)

for code, (n, kinds, rest, cp) in sorted(per_note.items()):
    words = len((HERE / "bodies" / f"{code}.md").read_text().split())
    print(f"{code} {by_code[code][:40]:40s} {n:4d} cards  {1000*n/words:5.1f}/kw  restates {rest:3d}  counterpart-none {cp:2d}")
print(f"\n{len(per_note)} notes, {total} cards")
print(f"\n{len(problems)} problems")
for pr in problems[:80]:
    print(" ", pr)
sys.exit(1 if problems else 0)
