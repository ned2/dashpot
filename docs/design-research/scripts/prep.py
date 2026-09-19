"""Prepare scratchpad copies of the research notes and the link graph."""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # docs/design-research (was an absolute path as run)
OUT = Path(__file__).parent
EXCLUDED = {"README.md", "synthesis.md", "analysis.md", "thematic-analysis-plan.md"}
REF_HEADINGS = ("## References", "## Related material", "## Sources the talk draws on")

notes = sorted(p for p in ROOT.glob("*.md") if p.name not in EXCLUDED)
assert len(notes) == 27, len(notes)
codes = {p.stem: f"N{i + 1:02d}" for i, p in enumerate(notes)}
(OUT / "note-codes.json").write_text(json.dumps(codes, indent=1))

bodies = OUT / "bodies"
bodies.mkdir(exist_ok=True)


def slug(heading: str) -> str:
    h = heading.strip().strip("#").strip().lower()
    h = re.sub(r"[^\w\s-]", "", h)
    return re.sub(r"\s+", "-", h).strip("-")


LINK = re.compile(r"\]\(([\w./-]+\.md)(#[\w-]+)?\)")

edges = []  # (src_note, src_section, dst_note, dst_anchor, in_mapping)
sections = defaultdict(list)
for p in notes:
    text = p.read_text()
    lines = text.split("\n")
    # strip frontmatter
    if lines[0] == "---":
        end = lines.index("---", 1)
        lines = lines[end + 1 :]
    # strip reference-type sections (only trailing ones)
    body = []
    current = "(top)"
    in_mapping = False
    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            current = line
            in_mapping = line.startswith("## Mapping") or line.startswith("## Sources")
            if line.startswith("## "):
                sections[p.stem].append(slug(line))
        for m in LINK.finditer(line):
            dst = Path(m.group(1)).name
            if dst.endswith(".md"):
                edges.append((p.stem, slug(current), dst[:-3], (m.group(2) or "")[1:], in_mapping))
        body.append(line)
    # cut trailing reference sections
    cut = None
    for i, line in enumerate(body):
        if line.startswith(REF_HEADINGS):
            cut = i
            break
    if cut is not None:
        # keep sections after the references heading only if they are not references either
        rest = body[cut:]
        keep = []
        skipping = True
        for line in rest:
            if line.startswith("## "):
                skipping = line.startswith(REF_HEADINGS)
            if not skipping:
                keep.append(line)
        body = body[:cut] + keep
    (bodies / f"{codes[p.stem]}.md").write_text("\n".join(body))
    print(codes[p.stem], p.stem, len("\n".join(body).split()), "words")

(OUT / "edges.json").write_text(json.dumps(edges, indent=0))
print(len(edges), "edges")
