# Dashpot

Dashpot observes project Issues, repositories, worktrees, and agent sessions
without controlling them.

## Language

### Declared work

**Project**:
A durable body of work rooted in exactly one Git Repository. It remains the same
Project across checkout moves, clones, branches, and worktrees.

**Git Repository**:
The single logical Git repository that roots a Project. Its hosting location and
local checkouts may change without changing the Project.
_Avoid_: Repository when referring to a checkout path

**Repository Identity**:
A stable opaque identity for a Git Repository, independent of remote URLs and
local checkouts.

**Issue**:
A declared unit of Project work conforming to Dashpot's source-neutral Issue
model. An Issue may be represented on GitHub or in local Markdown.
_Avoid_: Task, work item

**Issue Profile**:
The source-neutral set of facts every Issue Source must provide for an Issue. A
profile is complete; unavailable source facts are observation failures rather
than ambiguous Issue values.

**Issue Provenance**:
Source-specific evidence identifying the representation from which an Issue was
observed. Provenance does not participate in semantic equivalence.

**GitHub Issue**:
The GitHub Issues representation of an Issue.

**Local Issue**:
The local Markdown representation of an Issue.

**Issue Source**:
The authoritative representation through which a Project declares its Issues.
A Project has exactly one active Issue Source.

**Project Identity**:
A stable opaque identity for a Project, independent of repository hosting and
local filesystem location.

**Project Display Label**:
A mutable, human-readable label for a Project. It helps people recognize a
Project but never participates in identity.
_Avoid_: Project name when identity is intended

**Issue Identity**:
A stable opaque identity for an Issue, independent of its reference and
location.

**Issue Reference**:
A mutable, human-readable shorthand for an Issue, such as `ned2/dashpot#9` or a
local slug.

**Issue Location**:
An actionable, mutable locator for an Issue, such as a GitHub URL or a Markdown
file and line number.

### Observation

**Workspace**:
A named observation scope selecting Projects that Dashpot presents together. It
is a local grouping concept and never participates in Project or Issue identity.

**Repository Anchor**:
A configured local checkout through which Dashpot locates a Project and asks Git
for its linked worktrees. It is also the authoritative checkout for Local Issues.

**Worktree**:
A local working tree of a Project's Git Repository, including its main working
tree and any Git-linked working trees.

**Observation Target**:
A Worktree Dashpot discovered and refreshes at runtime. It is observed state,
not persisted Workspace membership or durable identity.

**Observation Location**:
Where an agent session is executing, such as a branch, Worktree, or working
directory. It is evidence about execution, never Project or Issue identity.
