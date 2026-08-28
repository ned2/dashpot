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
A stable opaque identity for an Issue, globally unique within Dashpot's Issue
universe and independent of its Project membership, reference, and location.

**Issue Number**:
A positive Project-local integer used as an Issue's compact human label, such
as `#16`. It may change with Project membership and never participates in Issue
identity.

**Issue Reference**:
A mutable, human-readable shorthand for an Issue, such as `ned2/dashpot#9` or a
local slug.

**Issue Location**:
An actionable, mutable locator for an Issue, such as a GitHub URL or a Markdown
file and line number.

### Observation

**Workspace**:
An optional local observation scope composing Projects that Dashpot presents
together. It owns no Project configuration or work state and never participates
in Project or Issue identity.

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

**Agent Session**:
The lifetime of one harness conversation or process, such as a single Codex
run. A session is never permanently bound to an Issue; its lifecycle state
(running, waiting, or unknown) is an observation of the session itself.

**Agent Run**:
A time-bounded period during one Agent Session when it is explicitly working
on exactly one Issue. Starting, switching, or stopping Issue work begins or
ends Agent Runs without ending or restarting the session.
_Avoid_: Agent Run as a synonym for the whole session

**Work Store**:
The versioned, Project-local record of active Agent Runs beneath a Worktree's
`.dashpot/state/`. It is the sole authority for which sessions are working on
which Issues at that Worktree.

**Issue Binding**:
A durable association between an Agent Run and an Issue by Issue Identity,
created by an explicit opt-in from the running session and stored in the Work
Store. It survives changes to Project membership, Issue Reference, and Issue
Location and is observed relationship state rather than part of the Issue
entity.

**Issue Hint**:
A mutable Issue Reference used only to establish an Issue Binding at opt-in
time. A hint never becomes identity and must resolve unambiguously within the
observed Project.
