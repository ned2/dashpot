"""Validate a clusterer's JSON: coverage, duplicates, group sizes. Usage: check_clustering.py <file>."""

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
export = json.loads((HERE / "export.json").read_text())
valid = {e["id"] for e in export}
path = Path(sys.argv[1])
d = json.loads(path.read_text())
groups = d["groups"]
unassigned = set(d.get("unassigned", []))
count = Counter()
problems = []
for g in groups:
    for k in ("name", "statement", "members"):
        if k not in g:
            problems.append(f"group missing {k}: {g.get('name')}")
    for m in g.get("members", []):
        if m not in valid:
            problems.append(f"{g.get('name')}: unknown id {m}")
        count[m] += 1
for m, c in count.items():
    if c > 2:
        problems.append(f"{m} in {c} groups")
covered = set(count) | unassigned
missing = valid - covered
cov = 1 - len(missing) / len(valid)
sizes = sorted((len(g.get("members", [])) for g in groups), reverse=True)
print(f"{path.name}: {len(groups)} groups, coverage {cov:.1%} ({len(missing)} missing, {len(unassigned)} unassigned), sizes {sizes[:5]}…{sizes[-5:]}")
print(f"{len(problems)} problems")
for p in problems[:30]:
    print(" ", p)
if missing:
    print("missing sample:", sorted(missing)[:40])
sys.exit(0 if cov >= 0.98 and not problems else 1)
