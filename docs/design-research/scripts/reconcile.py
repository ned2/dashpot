"""Step 3: match groups across runs, score replicate agreement, test dispersion on the frame."""

import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

HERE = Path(__file__).parent
CL = HERE / "clusters"
codes = json.loads((HERE / "note-codes.json").read_text())
by_code = {v: k for k, v in codes.items()}
export = json.loads((HERE / "export.json").read_text())
ids = [e["id"] for e in export]
note_of = lambda cid: cid.split(":")[0]
PHASE = {  # which pass a note came from
    "N25": "A", "N08": "A", "N13": "A", "N02": "A", "N17": "A",
    "N22": "B", "N21": "B", "N19": "B", "N20": "B", "N24": "B", "N23": "B",
    "N01": "gap", "N26": "gap", "N06": "gap", "N14": "gap", "N07": "gap",
    "N05": "team",
    "N27": "C", "N10": "C", "N11": "C", "N04": "C", "N16": "C", "N15": "C", "N09": "C", "N03": "C", "N12": "C", "N18": "C",
}


def load(name):
    d = json.loads((CL / f"{name}.json").read_text())
    groups = []
    for g in d["groups"]:
        m = set(g["members"])
        groups.append({"run": name, "name": g["name"], "statement": g.get("statement", ""), "members": m,
                       "notes": Counter(note_of(x) for x in m)})
    return groups


def primary_labels(groups):
    """First-group-wins label per card, for partition metrics."""
    lab = {}
    for i, g in enumerate(groups):
        for m in g["members"]:
            lab.setdefault(m, i)
    return [lab.get(c, -1) for c in ids]


def overlap(a, b):
    return len(a & b) / min(len(a), len(b))


runs = {n: load(n) for n in ("mechanism-A", "mechanism-B", "tension-A", "tension-B") if (CL / f"{n}.json").exists()}
placement = json.loads((CL / "placement.json").read_text()) if (CL / "placement.json").exists() else {}

out = []
out.append("# Reconciliation\n")
for n, gs in runs.items():
    sizes = sorted(len(g["members"]) for g in gs)
    covered = set().union(*(g["members"] for g in gs))
    out.append(f"- {n}: {len(gs)} groups, {len(covered)} cards assigned ({len(covered)/len(ids):.0%}), sizes {sizes[0]}–{sizes[-1]}, median {sizes[len(sizes)//2]}")

# replicate agreement
out.append("\n## Replicate agreement\n")
for lens in ("mechanism", "tension"):
    a, b = f"{lens}-A", f"{lens}-B"
    if a in runs and b in runs:
        la, lb = primary_labels(runs[a]), primary_labels(runs[b])
        both = [i for i in range(len(ids)) if la[i] >= 0 and lb[i] >= 0]
        ari = adjusted_rand_score([la[i] for i in both], [lb[i] for i in both])
        nmi = normalized_mutual_info_score([la[i] for i in both], [lb[i] for i in both])
        out.append(f"- {lens}: ARI {ari:.3f}, NMI {nmi:.3f} over {len(both)} cards assigned in both runs")

# pairwise matching
MIN_CARDS, MIN_NOTES, MIN_OVERLAP = 5, 3, 0.6


def eligible(g):
    return len(g["members"]) >= MIN_CARDS and len(g["notes"]) >= MIN_NOTES


matches = defaultdict(list)  # (run, idx) -> [(other run, idx, overlap)]
run_names = list(runs)
for ra, rb in combinations(run_names, 2):
    for i, ga in enumerate(runs[ra]):
        if not eligible(ga):
            continue
        for j, gb in enumerate(runs[rb]):
            if not eligible(gb):
                continue
            o = overlap(ga["members"], gb["members"])
            if o >= MIN_OVERLAP:
                matches[(ra, i)].append((rb, j, o))
                matches[(rb, j)].append((ra, i, o))


def dispersion(members):
    """How the framed placement scatters a group."""
    if not placement:
        return {}
    W = Counter(placement.get(m, {}).get("W", "?") for m in members)
    X = Counter(x for m in members for x in placement.get(m, {}).get("X", []))
    G = Counter(x for m in members for x in placement.get(m, {}).get("G", []))
    T = Counter(x for m in members for x in placement.get(m, {}).get("T", []))
    n = len(members)
    # a value "concentrates" the group if it holds >= 60% of members
    conc = [k for k, v in list(W.items()) + list(X.items()) + list(G.items()) if v >= 0.6 * n and k != "-"]
    w_vals = [k for k in W if k != "-" and W[k] >= max(3, 0.1 * n)]
    x_vals = [k for k in X if X[k] >= max(3, 0.1 * n)]
    g_vals = [k for k in G if G[k] >= max(3, 0.1 * n)]
    return {"W": dict(W.most_common()), "X": dict(X.most_common(6)), "G": dict(G.most_common(6)), "T": dict(T.most_common()),
            "concentrated_by": conc, "w_spread": len(w_vals), "x_spread": len(x_vals), "g_spread": len(g_vals),
            "scattered": (len(w_vals) >= 4 or len(x_vals) >= 3 or len(g_vals) >= 3) and not conc}


# robust = matched between the two runs of its lens
out.append("\n## Robust groups (matched between replicates)\n")
robust = []
seen = set()
for lens in ("mechanism", "tension"):
    a, b = f"{lens}-A", f"{lens}-B"
    if a not in runs or b not in runs:
        continue
    for i, ga in enumerate(runs[a]):
        for rb, j, o in matches.get((a, i), []):
            if rb != b or (b, j) in seen:
                continue
            seen.add((b, j))
            gb = runs[b][j]
            union = ga["members"] | gb["members"]
            core = ga["members"] & gb["members"]
            cross = [(r, k, oo) for (r, k, oo) in matches.get((a, i), []) + matches.get((b, j), []) if not r.startswith(lens)]
            d = dispersion(core)
            phases = Counter(PHASE[note_of(m)] for m in core)
            robust.append({"lens": lens, "a": ga["name"], "b": gb["name"], "overlap": o, "core": sorted(core), "union": len(union),
                           "notes": len({note_of(m) for m in core}), "cross_lens": [(r, runs[r][k]["name"], round(oo, 2)) for r, k, oo in cross],
                           "dispersion": d, "phases": dict(phases), "statement_a": ga["statement"], "statement_b": gb["statement"]})
robust.sort(key=lambda r: (-len(r["core"])))
for r in robust:
    d = r["dispersion"]
    flag = "EMERGENT?" if d.get("scattered") else ("confirms " + ",".join(d.get("concentrated_by", [])) if d.get("concentrated_by") else "mixed")
    single = max(r["phases"].values()) / len(r["core"]) >= 0.8 if r["phases"] else False
    out.append(f"\n### [{r['lens']}] {r['a']}  ⇔  {r['b']}  (overlap {r['overlap']:.2f}, core {len(r['core'])}, notes {r['notes']}) — {flag}{' — single-phase' if single else ''}")
    out.append(f"- A: {r['statement_a']}")
    out.append(f"- B: {r['statement_b']}")
    if r["cross_lens"]:
        out.append(f"- cross-lens matches: {r['cross_lens']}")
    if d:
        out.append(f"- placement W {d['W']} | X {d['X']} | G {d['G']} | T {d['T']}")
    out.append(f"- phases {r['phases']}; core sample: {', '.join(r['core'][:12])}")

# unmatched eligible groups = candidates / connections
out.append("\n## Groups found in one run only (eligible, unmatched within lens)\n")
for n, gs in runs.items():
    lens = n.split("-")[0]
    for i, g in enumerate(gs):
        if not eligible(g):
            continue
        same_lens = [m for m in matches.get((n, i), []) if m[0].startswith(lens)]
        if same_lens:
            continue
        other = [m for m in matches.get((n, i), []) if not m[0].startswith(lens)]
        d = dispersion(g["members"])
        out.append(f"- [{n}] {g['name']} (n={len(g['members'])}, notes={len(g['notes'])}{', scattered' if d.get('scattered') else ''}{', cross-lens ' + str([(r, runs[r][k]['name']) for r, k, _ in other]) if other else ''}) — {g['statement']}")

(HERE / "reconcile-report.md").write_text("\n".join(out) + "\n")
json.dump(robust, (HERE / "robust.json").open("w"), indent=1, default=list)
print("\n".join(out))
