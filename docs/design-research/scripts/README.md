---
status: research
date: 2026-09-20
---

# Thematic analysis scripts

The scripts and agent instructions that ran the
[thematic analysis plan](../thematic-analysis-plan.md) on 2026-09-16 and
produced the [claim inventory](../claim-inventory.md) and the
[themes note](../themes.md). They are kept as they ran, from the analysing
session's scratchpad, so that the figures the themes note reports — the
link-graph communities, the calibration counts, the NMI and ARI between
clustering runs, the silhouette scores of the mechanical clustering — can
be traced to the code that computed them. They are a record, not
maintained code: Ruff is told to leave them alone, ty does not check them,
and nothing in the package imports them. Three edits were made when they
were copied in on 2026-09-20, each replacing an absolute path with one
relative to the file (one in `prep.py`, two in `build_inventory.py`); the
three instruction files gained a frontmatter block and a one-line comment
saying so, nothing else.

## What is here and what is not

The scripts read and write a working directory beside themselves — note
bodies, the card JSON per note, the clustering outputs, the shuffled
export — that is not tracked: the cards are the inventory, published as
Markdown, and the clustering outputs are agent output the reconciliation
report summarises. So the scripts document the method and cannot be run
from this directory as-is; rerunning the analysis means re-extracting the
cards and re-running the four clustering agents, which is the plan's
procedure, not this directory's. The runs needed `networkx`,
`scikit-learn`, `numpy`, and `scipy` in a separate virtual environment;
none is a Dashpot dependency.

## The pipeline, in run order

| Step in the plan | File | Reads | Writes |
| --- | --- | --- | --- |
| Preparation | `prep.py` | the 27 research notes (index, synthesis, analysis, and plan excluded) | `bodies/N01–N27.md`, `note-codes.json`, `edges.json` |
| Step 0, link graph | `linkgraph.py` | `note-codes.json`, `edges.json`, `bodies/` | `step0-linkgraph.md`, `note-graph-body.edgelist` |
| Extraction rules | `extractor-instructions.md` | — | given verbatim to every card-extraction agent |
| Calibration | `calib_compare.py` | `calib/A–F.json`, six extractions of N05 | counts and granularity to stdout |
| Card validation | `validate_cards.py` | `cards/N*.json` | findings to stdout; rewrites `cards/N*.json` with repaired anchors |
| Inventory build | `build_inventory.py` | `cards/`, `note-codes.json`, `placements.json`; the repository's `scripts/check_docs.py` for heading anchors | `../claim-inventory.md`, `../claim-inventory/N*.md`, `all_cards.json`, the shuffled `export.json` and `export.txt` |
| Clustering rules | `clusterer-common.md` | — | given to the four blind clustering agents |
| Clustering check | `check_clustering.py` | a clusterer's JSON | coverage, duplicates, group sizes to stdout |
| Step 2.4, mechanical | `mechanical.py` | `export.json`, `note-codes.json`, `note-graph-body.edgelist` | `mech-plain.json`, `mech-noframe.json`, `undrawn.json`; silhouette per k to stdout |
| Framed placement | `frame.md` | — | the frame given to the placement agent after the blind runs |
| Step 3, reconciliation | `reconcile.py` | `clusters/mechanism-A,B.json`, `clusters/tension-A,B.json`, `clusters/placement.json`, `export.json` | `reconcile-report.md`, `robust.json`; NMI and ARI per run pair |
| Group summary | `summarise_groups.py` | `clusters/` | `groups-summary.md` |
| Emergent themes | `emergent_stats.py` | `clusters/`, `export.json` | per-candidate overlap, note span, and evidence to stdout |

Ad-hoc diagnostic and one-off repair scripts from the same session are
not kept; the [themes note's method notes](../themes.md#method-notes)
record the one case where a script's first result was corrected by hand
rather than rerun.
