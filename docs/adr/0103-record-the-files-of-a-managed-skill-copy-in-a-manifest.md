---
status: accepted
date: 2026-10-05
---

# Record the files of a managed skill copy in a manifest

[ADR 0079](0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md)
gives each harness its own copy of a bundled skill, and
[#418](https://github.com/ned2/dashpot/issues/418) made `integrate` install,
update, check and remove every skill in its `BUNDLED_SKILLS` registry. A copy
is Dashpot's to manage while its `SKILL.md` carries that skill's marker; a
directory of the skill's name without it is the user's, and is never
overwritten or removed.

Inside a managed copy, `integrate` knew only the files the running Dashpot
ships. [#436](https://github.com/ned2/dashpot/issues/436) found two
consequences in #418's review:

- **A file a release stops shipping survives.** An update writes the files
  this Dashpot ships and nothing removes the rest, so a reference file an
  older Dashpot shipped stays where the harness still reads it. `--remove`
  unlinks only this Dashpot's files, so it stays there too, with the
  directory around it.
- **A directory that cannot be listed raises.** A destination that can be
  entered but not listed, holding no `SKILL.md`, made `--status`, `--remove`
  and the install check end in a `PermissionError` traceback. An install
  over a managed copy of that kind raised too, since its check listed the
  directory before reading the marker.

Telling the first kind of file apart needs a record of what Dashpot wrote: a
file at a path the current release does not ship may be one an older
release shipped, or one the user added, and the copy itself cannot say
which.

## Decision

**A manifest beside the marker.** Every managed copy holds
`.dashpot-manifest.json`, which names each file Dashpot wrote there,
relative to the copy, as `{"files": [...]}`. Inside a managed copy, a file
the manifest names is Dashpot's, and any other file is the user's.

- **Update.** When this Dashpot ships a file the copy's manifest does not
  name, `integrate` first widens the manifest to name both. It then writes
  the shipped files, `SKILL.md` first, removes each file the old manifest
  named that this Dashpot no longer ships, with every directory that
  removal empties, and last writes a manifest naming the shipped files
  alone. An update cut short at any step leaves every file Dashpot wrote
  named, for the next update or `--remove` to finish. A first installation
  writes no manifest until its files are written, so one cut short before
  `SKILL.md` leaves an empty directory, free to install into again. A file
  the user added is never touched, and a directory that still holds one
  stays.
- **Remove.** `--remove` deletes exactly the files the manifest names, then
  the manifest, then `SKILL.md` last, so a removal cut short still leaves a
  copy the next `--remove` recognises by its marker. Each directory the
  removal empties goes, and the copy's own directory goes when nothing the
  user added is left in it.
- **Status.** A managed copy is current only when it holds every shipped
  file unchanged and its manifest names exactly those files. A copy whose
  manifest names a file this Dashpot no longer ships still holds that file,
  and `--status` reports it as an update available.
- **Copies written before the manifest.** A copy without one was written by
  a development revision before this decision. Every file any of those
  revisions shipped is still shipped (no file under `src/dashpot/skills/` was
  ever removed or renamed, checked against `main` at 9f7a1e9), so the files
  this Dashpot ships stand in for its manifest: an update keeps every other
  file as the user's and writes the manifest, and `--remove` deletes the
  shipped files. `--status` reports such a copy as an update available until
  `integrate` writes its manifest. The first release keeps manifests, so no
  published release writes a copy without one.
- **A manifest that cannot be trusted** — unreadable, not the expected
  shape, or naming a path that is absolute or climbs out with `..` — counts
  as absent.
- **Nothing outside the copy is ever removed.** A file is removed, or a
  directory pruned, only when the directory holding it resolves inside the
  copy, so a symbolic link the user put inside a copy is never followed.

**A destination that cannot be inspected is reported, never raised.**
`SKILL.md` is read before the directory is listed, so a managed copy that
can be entered but not listed is still recognised by its marker, and is
updated and removed by its manifest without a listing. A destination
without a readable `SKILL.md` that cannot be listed, or one whose parent
cannot be searched, is refused by `integrate` ("could not inspect it"),
reported as unreadable by `--status`, and left in place by `--remove`
("could not inspect"), like any other unreadable copy. Only a path that is
absent counts as absent: a destination Dashpot may not inspect is never
reported as missing. A managed copy Dashpot can read but not change ends
`integrate` with an error naming the copy ("could not update") and
`--remove` with a message ("could not remove"), and the manifest still
names whatever the attempt left.

## Considered options

- **A list in code of every file an earlier release shipped.** Rejected. It
  grows with every release that drops a file, and says what a release
  shipped, not what was written into a given copy. The copy's own record is
  exact for that copy.
- **Treat every file in a managed copy as Dashpot's.** Rejected. An update
  or `--remove` would then delete files the user added, which the marker
  rule promises never to do.
- **Record digests to spare a shipped file the user edited.** Rejected. An
  update already overwrites an edited shipped file, as it does an edited
  managed agent ([ADR 0093](0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md)),
  so a path Dashpot wrote is Dashpot's whatever it now holds.
- **Keep the record outside the copy**, in Dashpot's own state. Rejected.
  The copies are user-wide, in each harness's skill directory, outside any
  Project; a record inside the copy is found wherever the copy is, and goes
  with it.
- **Carry the list in `SKILL.md`, beside the marker.** Rejected. `SKILL.md`
  is shipped byte for byte, and an installed copy is current by comparing
  it with the shipped one.

## Consequences

- Every copy installed before this decision reports an update available
  once, and the next `integrate` writes its manifest.
- A release may drop a file from a bundled skill: the next `integrate`
  removes it from every managed copy, and `--remove` takes it too.
- The manifest is a hidden JSON file in the skill's directory. Claude
  Code, Codex and OpenCode find a skill by its `SKILL.md`, and no skill
  names the manifest.
- OpenCode's warning about another harness's differing copy uses the same
  test of currency, so it also names a copy that still holds a dropped file
  or has no manifest; that harness's own `integrate` repairs it.
