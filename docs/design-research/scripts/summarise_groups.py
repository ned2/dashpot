"""Write groups-summary.md: every run's groups with statement, note span, and members."""

import json
from pathlib import Path

HERE = Path(__file__).parent
CL = HERE / "clusters"
out = []
for n in ("mechanism-A", "mechanism-B", "tension-A", "tension-B"):
    d = json.loads((CL / f"{n}.json").read_text())
    out.append(f"# {n}\n")
    for g in d["groups"]:
        notes = sorted({m.split(":")[0] for m in g["members"]})
        out.append(
            f"## [{n}] {g['name']}\n{g['statement']}\nn={len(g['members'])}, notes={len(notes)} ({' '.join(notes)})\n"
            f"members: {' '.join(sorted(g['members']))}\n"
        )
(HERE / "groups-summary.md").write_text("\n".join(out))
print(len("\n".join(out).split()), "words")
