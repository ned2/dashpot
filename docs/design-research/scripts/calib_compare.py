"""Compare the six calibration extractions of N05."""

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent / "calib"
runs = {p.stem: json.loads(p.read_text()) for p in sorted(HERE.glob("*.json"))}
for k, cards in runs.items():
    kinds = Counter(c["kind"] for c in cards)
    ev = Counter(c["evidence"] for c in cards)
    anchors = Counter(c["anchor"] for c in cards)
    words = [len(c["claim"].split()) for c in cards]
    over = sum(1 for c in cards if len(c["claim"].split()) > (60 if c["kind"] == "measurement" else 40))
    figs = sum(1 for c in cards if c["figures"])
    rest = sum(1 for c in cards if c["restates"])
    print(f"{k}: {len(cards)} cards, mean {sum(words)/len(words):.1f} words, {over} over cap, {figs} with figures, {rest} restates")
    print("   evidence", dict(ev))
    print("   per section:", {a[:30]: n for a, n in anchors.items()})

# Do the runs agree on the measured figures? List every distinct figure string.
print("\nFigures by run:")
for k, cards in runs.items():
    print(k, [c["figures"][:60] for c in cards if c["figures"]])

print("\nSample claims from A, section by section:")
for c in runs["A"][:12]:
    print(f"  {c['id']} [{c['kind']}/{c['evidence']}] {c['claim']}")
