"""Step 0: the link graph between research-note sections."""

import json
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

HERE = Path(__file__).parent
codes = json.loads((HERE / "note-codes.json").read_text())
edges = json.loads((HERE / "edges.json").read_text())
research = set(codes)

out = []


def report(title, all_edges):
    out.append(f"\n## {title}\n")
    # section-level in-degree by distinct citing notes
    citers = defaultdict(set)
    note_edges = Counter()
    for src, _sec, dst, anchor, _m in all_edges:
        if dst not in research or src not in research or src == dst:
            continue
        citers[(dst, anchor)].add(src)
        note_edges[(src, dst)] += 1
    top = sorted(citers.items(), key=lambda kv: -len(kv[1]))[:25]
    out.append("Load-bearing sections (distinct citing notes):\n")
    for (dst, anchor), s in top:
        out.append(f"- {len(s):2d}  {dst}#{anchor}")
    # note-level graph
    G = nx.DiGraph()
    G.add_nodes_from(research)
    for (s, d), w in note_edges.items():
        G.add_edge(s, d, weight=w)
    out.append(f"\nNote graph: {G.number_of_nodes()} notes, {G.number_of_edges()} note-pairs, {sum(note_edges.values())} links\n")
    indeg = sorted(((sum(w for _, _, w in G.in_edges(n, data='weight')), len(list(G.predecessors(n))), n) for n in G), reverse=True)
    out.append("Notes by in-links (links, distinct citers):\n")
    for w, k, n in indeg:
        out.append(f"- {w:3d} {k:2d}  {n}")
    U = G.to_undirected()
    comms = nx.community.greedy_modularity_communities(U, weight="weight")
    out.append(f"\nCommunities (greedy modularity, {len(comms)}):\n")
    for i, c in enumerate(comms):
        out.append(f"- C{i}: " + ", ".join(sorted(c)))
    louv = nx.community.louvain_communities(U, weight="weight", seed=1)
    out.append(f"\nCommunities (Louvain, seed 1, {len(louv)}):\n")
    for i, c in enumerate(louv):
        out.append(f"- L{i}: " + ", ".join(sorted(c)))
    isolated = [n for n in G if G.in_degree(n) == 0]
    out.append(f"\nNotes cited by no other note: {', '.join(sorted(isolated)) or 'none'}")
    unlinked = [n for n in G if G.out_degree(n) == 0]
    out.append(f"Notes citing no other note: {', '.join(sorted(unlinked)) or 'none'}")
    # pairs with no path (undirected)
    nopath = []
    nodes = sorted(research)
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            if not nx.has_path(U, a, b):
                nopath.append((a, b))
    out.append(f"Unconnected note pairs: {len(nopath)}")
    return U


# sections with no inbound links at all
all_sections = defaultdict(list)
import re

for p in sorted((HERE / "bodies").glob("*.md")):
    slug = [k for k, v in codes.items() if v == p.stem][0]
    for line in p.read_text().split("\n"):
        if line.startswith("## "):
            h = line[3:].strip().lower()
            h = re.sub(r"[^\w\s-]", "", h)
            all_sections[slug].append(re.sub(r"\s+", "-", h).strip("-"))

U_all = report("All edges", edges)
U_body = report("Body edges only (mapping-table and sources sections excluded)", [e for e in edges if not e[4]])

cited = {(d, a) for _s, _sec, d, a, _m in edges if d in research}
out.append("\n## Sections with no inbound link (by note)\n")
for slug, secs in sorted(all_sections.items()):
    orphans = [s for s in secs if (slug, s) not in cited and s not in ("finding", "dead-ends", "references", "corrections-proposed", "mapping-to-the-existing-notes")]
    out.append(f"- {codes[slug]} {slug}: {len(orphans)}/{len(secs)} — " + ", ".join(orphans))

# save the undirected body graph for the mechanical step
nx.write_edgelist(U_body, HERE / "note-graph-body.edgelist", data=["weight"])
(HERE / "step0-linkgraph.md").write_text("# Step 0: link graph\n" + "\n".join(out) + "\n")
print("\n".join(out))
