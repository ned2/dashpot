---
status: research
date: 2026-09-16
---

<!-- The instructions common to the four blind clustering agents, as used on 2026-09-16; the frontmatter above and this comment are the only additions. -->

# Clustering: common instructions

You are clustering a set of 3,464 idea cards extracted from a body of research notes. Each card is one line in the export:

```
<id> [<kind>/<evidence>] <claim> (<figures>)
```

`id` is `N<nn>:<n>` — an opaque note code and a running number; the code tells you two cards came from the same source document, nothing more. `kind` is finding / mechanism / definition / practice / tool / policy / argument / measurement / dead-end. `evidence` is C causal, M measured, Q qualitative, T testimonial, A argument, - none.

The export is in three files, in the directory `/tmp/claude-1000/-home-ned-projects-dashpot/61fd747f-14f2-45ae-9eb4-112b66fdd61f/scratchpad/themes/`: `export-part-00.txt`, `export-part-01.txt`, `export-part-02.txt` (about 1,200 lines each). Read all three in full before grouping. Read nothing else on disk except the files this prompt names. Do not use the web. Do not read any git repository.

## Output

Write a JSON file at the path you are given, of the form:

```json
{
  "groups": [
    {"name": "...", "statement": "one sentence: what the members share", "members": ["N03:12", "N17:4", ...]},
    ...
  ],
  "unassigned": ["N05:9", ...]
}
```

Constraints:

- Roughly 15 to 40 groups. Each group at least 5 members and at most about 120. A group's members should come from **several different note codes** wherever the material allows — a group drawn from one code is usually the note's own structure, not a cross-cutting idea; prefer to merge such a group into a cross-cutting one or leave its cards unassigned.
- A card may belong to at most two groups. Most cards belong to one.
- Every card id in the export appears either in some group or in `unassigned`. Cards that are pure bookkeeping (a bibliographic aside, a date, a tool's star count) may go unassigned; aim for at least 70% of cards assigned.
- Use the ids exactly as they appear; do not invent ids.

Build the file incrementally if you need to (write the group list in several passes and merge), but the final file must be a single valid JSON document. After writing, run:

```
python3 /tmp/claude-1000/-home-ned-projects-dashpot/61fd747f-14f2-45ae-9eb4-112b66fdd61f/scratchpad/themes/check_clustering.py <your output path>
```

and fix whatever it reports (unknown ids, cards in more than two groups, coverage below 98% — coverage counts unassigned cards as covered, so the check is that every id is accounted for) until it exits 0. Then reply with only: the number of groups, the coverage, and the list of group names with member counts.
