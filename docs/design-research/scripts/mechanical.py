"""Step 2.4: TF-IDF + agglomerative clustering, twice; undrawn connections."""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

HERE = Path(__file__).parent
codes = json.loads((HERE / "note-codes.json").read_text())
by_code = {v: k for k, v in codes.items()}
export = json.loads((HERE / "export.json").read_text())
ids = [e["id"] for e in export]
note_of = {e["id"]: e["id"].split(":")[0] for e in export}
texts = [e["claim"] + " " + e["figures"] for e in export]

FRAME_WORDS = set(
    """hand-off handoff hand off review reviewer reviewing gate gates gated friction session sessions
    task start loop step steps merge commit continuous onboarding team teams generate predict write explain
    teach-back teach back recall retrieval verify approve approval read navigate ask artifact artifacts
    default defaults opt-in mode practice policy tool tooling enforced enforcement understanding comprehension
    model models code codebase developer developers agent agents ai llm""".split()
)


def run(tag, stop):
    vec = TfidfVectorizer(stop_words=list(stop), ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    X = vec.fit_transform(texts)
    best = None
    for k in (20, 30, 40, 50, 60, 80):
        model = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
        labels = model.fit_predict(X.toarray())
        s = silhouette_score(X, labels, metric="cosine")
        print(f"[{tag}] k={k} silhouette={s:.3f}")
        if best is None or s > best[0]:
            best = (s, k, labels)
    s, k, labels = best
    groups = defaultdict(list)
    for cid, lab in zip(ids, labels):
        groups[int(lab)].append(cid)
    out = {"tag": tag, "k": k, "silhouette": s, "groups": []}
    terms = np.array(vec.get_feature_names_out())
    Xa = X.toarray()
    for lab, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        idx = [ids.index(m) for m in members]
        centroid = Xa[idx].mean(axis=0)
        top = terms[np.argsort(-centroid)[:6]]
        notes = Counter(note_of[m] for m in members)
        out["groups"].append({"label": f"{tag}-{lab}", "top_terms": list(top), "n": len(members), "notes": len(notes), "members": members})
    (HERE / f"mech-{tag}.json").write_text(json.dumps(out, indent=1))
    print(f"[{tag}] chosen k={k}; groups spanning >=3 notes with >=5 cards: {sum(1 for g in out['groups'] if g['notes'] >= 3 and g['n'] >= 5)}")
    for g in out["groups"][:15]:
        print(f"  {g['label']:8s} n={g['n']:3d} notes={g['notes']:2d} {', '.join(g['top_terms'])}")
    return X


X = run("plain", ENGLISH_STOP_WORDS)
run("noframe", set(ENGLISH_STOP_WORDS) | FRAME_WORDS)

# undrawn connections: high lexical similarity, notes with no body link between them
G = nx.read_edgelist(HERE / "note-graph-body.edgelist", data=[("weight", float)])
sim = cosine_similarity(X)
pairs = []
n = len(ids)
for i in range(n):
    for j in range(i + 1, n):
        a, b = note_of[ids[i]], note_of[ids[j]]
        if a == b:
            continue
        if sim[i, j] < 0.45:
            continue
        sa, sb = by_code[a], by_code[b]
        if G.has_edge(sa, sb):
            continue
        pairs.append((float(sim[i, j]), ids[i], ids[j]))
pairs.sort(reverse=True)
(HERE / "undrawn.json").write_text(json.dumps(pairs[:300], indent=0))
print(f"\nundrawn connections (sim>=0.45, no body link between notes): {len(pairs)}")
note_pairs = Counter(tuple(sorted((note_of[a], note_of[b]))) for _, a, b in pairs)
for (a, b), c in note_pairs.most_common(20):
    print(f"  {c:3d}  {by_code[a]} <-> {by_code[b]}")
