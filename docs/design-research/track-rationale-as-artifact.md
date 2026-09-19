---
status: research
date: 2026-09-13
---

# Rationale as artifact

A Phase B deep pass on one feature idea from the design research: capturing and
maintaining the *why* of a codebase — Naur's "theory", the world-to-code mapping and the
design rationale — as a durable artifact that survives the agent finishing and the author
forgetting. The note is documentary. It records what exists, what each source claims, and
what has been measured, for the three sub-families Phase A surfaced (agent-maintained living
documentation; provenance and intent capture; the curated dialog as artifact) plus Litt's
"shared spaces". It does not evaluate fit for Dashpot, for terminal tools, or for any
workflow, does not rank, and does not design. Every claim carries a URL; where a primary page
could not be reached the claim is marked as such. Status is as observed on 2026-09-13.

## The idea

Phase A established the loss and the three shapes of remedy. Naur's argument that the theory
of a program lives in its programmers and "reestablishing the theory of a program merely from
the documentation, is strictly impossible" is summarised in the
[evidence note](evidence-and-mechanisms.md#naur-the-theory-is-not-in-the-text), whose
[finding](evidence-and-mechanisms.md#finding) is that the least-documented layer of an expert's
model is the mapping between world and code and the rationale for each part. The
[landscape sweep](landscape-sweep.md#cluster-5--agent-maintained-living-artifacts) catalogued
tools that regenerate docs, wikis and steering files, noting that "understanding is a side
effect of the artifact existing, not something the tool checks", and a
[provenance cluster](landscape-sweep.md#cluster-6--provenance-and-intent-capture-seeds-missed)
that keeps the raw agent transcript as the record of why; its
[observations for the deep pass](landscape-sweep.md#observations-for-the-deep-pass) asked
what stops regeneration silently rewriting a human's intent, whether any artifact records that
a human read it, what Agent Trace's adoption actually is, how transcript deletion interacts
with commit-linking, and whether any trace is rendered for a reader. The
[Answer.AI sweep](answer-ai-sweep.md#core-claims) supplied the literate-programming and
dialog-engineering lineage, and the [Solveit sweep](solve-it-sweep.md#product-mechanics)
the curated, editable dialog as the durable understanding artifact, contrasted with the
append-only trace. Litt's
[shared spaces](understanding-bottleneck-talk.md#proposal-4-shared-spaces) added the team as
the holder of a shared vocabulary. This note takes each of those threads to its primary
sources.

## Agent-maintained living documentation

### Pre-AI lineage: design rationale research

The idea of recording *why* as a first-class artifact predates ADRs by four decades. Kunz and
Rittel's Issue-Based Information Systems (IBIS, 1970) is the root: IBIS "guides the
identification, structuring, and settling of issues raised by problem-solving groups" and "is
also a documentation and reporting system which permits fast and reliable information on the
state of discourse at any time"
(<https://web.archive.org/web/2020id_/http://magrawal.myweb.usf.edu/phd/articles/ibis_wp_70.pdf>).
Conklin and Begeman's gIBIS (ACM TOIS 1988) implemented it as hypertext, defined design
rationale as "the design problems, alternative resolutions (including those which are later
rejected), trade-off analysis among these alternatives, and a record of the tentative and firm
commitments", and recorded the capture cost first-hand: "in the moment of struggling to solve
the problem, the cognitive overhead required to segment the 'muck' into discrete thoughts,
identify their types, label them, and link them is prohibitive"; writers "in a hurry to
capture a design issue … sometimes write[] only the bare minimum"
(<https://doi.org/10.1145/58566.59297>; author copy at
<http://csis.pace.edu/~marchese/CS835/Readings/p303-conklin_gibis.pdf>). Conklin and Burgess
Yakemovic's process-oriented follow-up reports "a field trial in an industrial setting in
which the low-tech indented text IBIS was used to capture more than 2,300 requirements and
design decisions" (<https://doi.org/10.1207/s15327051hci0603&4_6>). MacLean, Young, Bellotti
and Moran's QOC (Questions, Options, Criteria; 1991) "does not produce a record of the design
process but is instead a coproduct of design and has to be constructed alongside the artifact
itself"; its claimed payoff "serve[s] as goals rather than objectives we have achieved"
(<https://doi.org/10.1207/s15327051hci0603&4_2>). Lee and Lai's "What's in Design Rationale?"
(same issue) built "a framework for evaluating the expressive adequacy of design rationale
representations" and presented DRL (<https://doi.org/10.1207/s15327051hci0603&4_3>); Lee's
1997 IEEE Expert survey holds that "most current design rationale systems fail to consider
practical concerns, such as cost-effective use and smooth integration"
(<https://doi.org/10.1109/64.592267>; the seven issues it lists could not be retrieved).
Grudin's chapter in Moran and Carroll's *Design Rationale* (1996) supplies the incentive
argument (<https://doi.org/10.1201/9781003064053-21>), restated fifteen years after gIBIS by
Buckingham Shum, Selvin, Sierhuis, Conklin, Haley and Nuseibeh: "The capture problem is the
spectre haunting all design rationale efforts"; "No designer can be expected to altruistically
enter quality design rationale solely for the possible benefit of a possibly unknown person at
an unknown point in the future for an unknown task. There must be immediate value"
(<https://doi.org/10.1007/978-3-540-30998-7_5>; preprint at
<https://web.archive.org/web/2016id_/http://libeprints.open.ac.uk/3032/1/HypermediaSupport.pdf>).
Burge and Brown's SEURAT (Software Engineering Using RATionale) brought the argumentation
model to code: "the uses proposed for rationale are not compelling enough to justify the
effort involved in its capture", so SEURAT "integrates with a software development environment
and goes beyond mere presentation of rationale by inferencing over it to check for
completeness and consistency" (Burge's dissertation,
<https://digitalcommons.wpi.edu/etd-dissertations/244>; ICSE 2008 demo
<https://doi.org/10.1145/1368088.1368215>; chapter "Rationale-Based Support for Software
Maintenance" in Dutoit, McCall, Mistrík and Paech (eds.), *Rationale Management in Software
Engineering*, Springer 2006, <https://doi.org/10.1007/978-3-540-30998-7_13>). Horner and
Atwood's chapter in the same volume, "Effective Design Rationale: Understanding the Barriers",
is the standard statement of why capture fails (<https://doi.org/10.1007/978-3-540-30998-7_3>;
not retrieved). What this literature measured about capture cost and use is in the
[Evidence](#evidence) section.

### Pre-AI lineage: ADRs, docs-as-code, arc42 and C4

- **Nygard's ADRs (2011).** The motivating problem is that "one of the hardest things to
  track during the life of a project is the motivation behind certain decisions"; a newcomer
  either accepts a decision blindly or changes it blindly. The template is Title, Context
  ("value-neutral"), Decision ("We will…"), Status (proposed, accepted, deprecated,
  superseded), Consequences. Files live in version control at `doc/arch/adr-NNN.md`; numbers
  are never reused; "if a decision is reversed, we will keep the old one around, but mark it
  as superseded"; and the length rule is explicitly a currency rule: one or two pages, because
  "large documents are never kept up to date"
  (<https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>).
- **adr-tools** (Nat Pryce) scripts the convention: `adr init`, `adr new`, and `adr new -s N`,
  which creates a superseding record and "changes the status of ADR N to indicate that it is
  superceded by the new ADR" (<https://github.com/npryce/adr-tools>).
- **MADR 4.0.0** (2024-09-17) adds Decision Drivers, Considered Options, Decision Outcome,
  Pros and Cons of the Options, and a **Confirmation** section: "Describe how the
  implementation of/compliance with the ADR can/will be confirmed … a design/code review or a
  test with a library such as ArchUnit can help validate this." Frontmatter carries `status`,
  `date`, `decision-makers`, `consulted`, `informed`; the docs describe how a decision is
  confirmed, not who confirms it (<https://adr.github.io/madr/>).
- **Thoughtworks Technology Radar** carried "Lightweight Architecture Decision Records" at
  Trial (Nov 2016, Mar 2017) and Adopt (Nov 2017, May 2018), preferring version-controlled
  storage over wikis so records stay with the code
  (<https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records>).
- **AWS Prescriptive Guidance** adds an explicit reading ritual: an ADR review "should start
  with a dedicated time slot to read the ADR. On average, 10 to 15 minutes should be enough";
  on approval "the owner adds a timestamp, version, and list of stakeholders" and sets
  Accepted; accepted ADRs "become immutable"; a code reviewer who finds a change violating an
  ADR "shares a link to the ADR"
  (<https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html>).
  This is the only pre-AI ADR process found that records who was present when a decision was
  read.
- **Microsoft's Azure Well-Architected Framework** (page dated 2026-04-10): "The ADR serves
  as an append-only log. Don't go back and edit accepted records. If a decision changes, write
  a new record that supersedes the original and link the two together"; records should carry
  "the confidence level of the decision"; "Avoid making decision records design guides"
  (<https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record>).
- **Kopp, Armbruster and Zimmermann (ZEUS 2018)**, the MADR paper, frame the problem as "How
  to seamlessly integrate architectural decision making into developer tool landscapes — so
  that decision rationale can be collected under high coding velocity?", note that decision
  tools are "perceived as chronophages (time wasters)", and report action research on Eclipse
  Winery in which 16 MADRs were written, half without the Pros and Cons section, because
  students "were afraid to be criticized for options not considered"
  (<https://ceur-ws.org/Vol-2072/paper9.pdf>). Keeling's "The Psychology of Architecture
  Decision Records" (IEEE Software 2022) argues ADRs "help developers evolve into
  architectural thinkers" (<https://doi.org/10.1109/ms.2022.3198195>).
- **Joel Parker Henderson's ADR collection** contrasts "immutability (theory)" — amend or
  supersede, never alter — with "mutability (practice)", timestamped insertions as new facts
  arrive, and recommends an after-action review "approximately one month after implementation"
  to "compare the ADR information with what's happened in actual practice"
  (<https://github.com/joelparkerhenderson/architecture-decision-record>).
- **Docs as code** (Write the Docs) prescribes issue trackers, Git, plain-text markup, code
  review and automated tests for documentation, and claims currency comes from workflow:
  teams "can block merging of new features if they don't include documentation, which
  incentivizes developers to write about features while they are fresh"
  (<https://www.writethedocs.org/guide/docs-as-code/>).
- **arc42** reserves section 9 for "Architectural Decisions — important decisions, unless
  described elsewhere", section 8 for crosscutting concepts, and section 12 for a Glossary of
  "important and specific terms ('ubiquitous language')" (<https://arc42.org/overview>).
- **C4 / Structurizr** treat diagrams as code and attach rationale to the model: the DSL's
  `!docs` "can be used to attach Markdown/AsciiDoc documentation" and `!adrs` "can be used to
  attach Markdown/AsciiDoc ADRs to the parent context (either the workspace, a software
  system, or a container)", with importers for adr-tools, MADR and log4brains
  (<https://docs.structurizr.com/dsl/language>, <https://docs.structurizr.com/dsl/adrs>);
  the server renders decisions coloured by status and as "a force-directed graph that shows
  the connections between decisions" (<https://docs.structurizr.com/server/decisions>). The
  C4 FAQ observes that "each diagram will change at a different rate" and suggests generating
  the lower levels from service catalogues, OpenTelemetry or static analysis
  (<https://c4model.com/diagrams/faq>). docToolchain implements arc42 as docs-as-code with
  export tasks for Jira, Enterprise Architect, OpenAPI, Structurizr and change logs
  (<https://doctoolchain.org/docToolchain/v2.0.x/015_tasks/03_tasks.html>). None of these
  pages states how generated and hand-written content are kept apart.
- **Google's g3doc and freshness dates.** *Software Engineering at Google* (ch. 10) states
  that documentation "should, as much as possible, be treated *as code*": under source
  control, owned, reviewed, and changed "*with* the code it documents". Its staleness
  mechanism is a human attestation: "we often attach 'freshness dates' to documentation. Such
  documents note the last time a document was reviewed, and metadata in the documentation set
  will send email reminders when the document hasn't been touched in, for example, three
  months" (`freshness: { owner: 'username' reviewed: '2019-02-27' }`). The chapter also
  concedes that measurement of "accuracy, freshness, etc." is desirable but "tools have still
  not caught up here" (<https://abseil.io/resources/swe-book/html/ch10.html>). Cyrille
  Martraire's *Living Documentation* (2019) generalises the generated side — a "living
  glossary" and "knowledge augmentation" extracted from annotated code so that documentation
  "changes at the same pace as software design and development"
  (<https://www.informit.com/store/living-documentation-continuous-knowledge-sharing-by-design-9780134689326>).

### Agent-era tools

The table answers, per tool, the six questions Phase A left open: what is generated, from
what, when it regenerates, what happens to a human's edits, whether a human's reading or
approval is recorded, and status. Vendor pages are the source unless marked.

| Tool | Generates | From | Regenerates | Human edits to generated text | Records read/approval | Status |
|---|---|---|---|---|---|---|
| Swimm | Code-coupled Markdown docs (`.swm/*.sw.md`) with snippets, Smart Tokens, Smart Paths; Swimm AI drafts docs from PRs and selected snippets | Repo code and git history (Auto-sync needs a full clone); PR diffs | Auto-sync runs in CI and via the GitHub App "whenever a PR is opened or an open PR is updated"; only references re-sync, prose never regenerates | Prose freely editable outside "Swimm specific sections"; trivial code moves/renames auto-synced; deletions or path changes flagged "outdated" and block the PR check until a human reselects the snippet; synced changes land only after "Approve Auto-sync" (or auto-approval if enabled) | Only the per-PR Approve Auto-sync action and the Verify check; no "last reviewed by" metadata found | Product exists; 2026 homepage repositions Swimm as "agentic modernization" for COBOL/JCL |
| Kiro | Steering files `product.md`, `tech.md`, `structure.md` ("architectural decisions"); hooks can regenerate README, OpenAPI, CHANGELOG | Agent exploration of key files; file events plus a natural-language hook prompt | Hook triggers `PostFileSave`/`Create`/`Delete`, `AgentStop`, `SessionStart`, etc.; "File triggers respond only to changes made by the agent" | Hook output is a proposed change set to "accept or modify"; a Refine button for steering; no protected regions; guidance is "treat steering changes like code changes — require reviews"; issue #1818 (closed, not planned) complains Refine "doesn't check if anything has actually changed" | None | Active (Kiro Web GA 2026-09-01); Amazon Q Developer IDE plugins end of support 2027-04-30 |
| Amazon Q Developer `/doc` | README plus data-flow and infrastructure diagrams | Source folder scan | On demand; an "update with recent code changes" mode | Presents a diff; "choose Accept in the chat to update your README in place" | The Accept click only | Sunsetting with Q Developer; Kiro migration table lists no equivalent |
| DeepWiki | Wiki with architecture diagrams, docs, source links, Ask Devin | Repository | On request ("Refresh this wiki"; observed "Last indexed" date); `.devin/wiki.json` fixes `pages` and `repo_notes` — "only the pages you define … will be generated" | An "Edit Wiki" link exists; whether edits survive regeneration is undocumented | None | Active; "over 50,000" public repos indexed at launch |
| Google Code Wiki | "Comprehensive and interactive documentation", architecture/class/sequence diagrams, Gemini chat | Full codebase | "scans the full codebase and regenerates the documentation after each change" | Not addressed | None | Public preview for public repos; private via a "coming soon" Gemini CLI extension |
| AGENTS.md | Nothing — human-written "README for agents" | — | — | It *is* the human text | None | "Used by over 60k open-source projects"; stewarded by the Agentic AI Foundation |
| Cursor rules | `.cursor/rules/*.mdc`; `/create-rule` has the agent write a rule; 0.49 added "generate rules directly from a conversation" (reported gone in 2.0); Memories (beta, 1.0) "remember facts from conversations" | Chat history | On command | Plain files, edited by hand | None | Active; Memories page no longer in docs |
| Continue rules | `.continue/rules/*.md`; agent can create one via `create_rule_block` | Chat | On command | Plain files | None | Active |
| RepoAgent (OpenBMB, 2024) | Per-file Markdown docs and a global structure JSON; "seamlessly replaces Markdown content based on changes" | AST of the repo; `repoagent diff` previews what a code change will regenerate | A `pre-commit` hook runs `repoagent run` on every commit | Generated content is replaced wholesale on change | None | Research framework (arXiv 2402.16667) |
| Mintlify agent / Automations | Doc edits as pull requests | Content-update, code-change, schedule and integration triggers | On trigger | "Direct merge" or "Pull request review … for tasks that change content meaning, like syncing with code changes" | PR review | Active |
| Komment | Overviews, architecture diagrams, API docs, in-code comments | Codebase deltas | "automatically re-documents your software when it detects divergence between code and docs" | Not stated | None | Active |
| Claude Code `/init` and auto memory | `CLAUDE.md` (build, test, conventions); auto memory notes under `~/.claude/projects/<project>/memory/` | Codebase; conversations | `/init` on demand ("suggests improvements rather than overwriting"); memory as Claude works | Memory files are "plain markdown you can edit or delete at any time"; each carries a `modified` timestamp so "the timestamp shows how current the fact is"; `/doctor` proposes trims | None | Active |
| GitHub Copilot | Draft PR for `.github/copilot-instructions.md`; "Update documentation" as a coding-agent task | Repository | On request | Reviewed as a PR | PR review | Active |

Sources: Swimm (<https://docs.swimm.io/features/keep-docs-updated-with-auto-sync/>,
<https://docs.swimm.io/continuous-integration/github-app/>,
<https://swimm.io/blog/docs-as-code-understanding-swimm-sw-md-markdown-format>,
<https://swimm.io/>); Kiro (<https://kiro.dev/docs/steering/>, <https://kiro.dev/docs/hooks/>,
<https://kiro.dev/blog/how-i-stopped-worrying-about-readme-files/>,
<https://github.com/kirodotdev/Kiro/issues/1818>,
<https://aws.amazon.com/blogs/devops/amazon-q-developer-end-of-support-announcement/>);
Amazon Q (<https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/generate-docs.html>,
JS-rendered — quotes from the AWS What's New post
<https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-q-developer-generate-documentation-source-code/>);
DeepWiki (<https://cognition.com/blog/deepwiki>, <https://docs.devin.ai/work-with-devin/deepwiki>);
Code Wiki (<https://developers.googleblog.com/introducing-code-wiki-accelerating-your-code-understanding/>);
AGENTS.md (<https://agents.md/>); Cursor (<https://cursor.com/docs/context/rules>,
<https://cursor.com/changelog/0-49>, <https://cursor.com/changelog/1-0>); Continue
(<https://docs.continue.dev/customize/rules>); RepoAgent
(<https://github.com/OpenBMB/RepoAgent>, <https://arxiv.org/abs/2402.16667>); Mintlify
(<https://www.mintlify.com/docs/ai/agent>); Komment (<https://www.komment.ai/>); Claude Code
(<https://code.claude.com/docs/en/memory>); Copilot
(<https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions>).

Two patterns cut across the table. First, no agent-era tool records that a human *read* a
generated artifact; the nearest are approval events on a diff (Swimm's Approve Auto-sync,
Q's Accept, a PR review) and Google's pre-AI `reviewed:` date. Second, the tools that
regenerate on file events (Kiro hooks, RepoAgent, Code Wiki, Komment) document no
protected-region or merge behaviour; the ones that preserve human prose do so by never
regenerating prose at all (Swimm re-syncs references only; Claude Code memory is plain
editable Markdown). Staleness detection exists in three forms: reference-level (Swimm's
Verify), delta-level (Komment, RepoAgent's `diff`), and attestation-level (Google's
freshness reminders, Claude Code's `modified` timestamp). Kiro issue #1818 explicitly asks for
a change check that steering lacks.

### ADR-writing skills for agents

Several agent skills instruct the harness to write ADRs at the moment a decision is made:

- Eric Clemmons' gist writes to `docs/adr/YYYY-MM-DD-short-title.md` when work "chose among
  meaningful alternatives", "accepted a trade-off", or changes a documented decision; there is
  no status field ("A merged ADR is accepted"), and "Do not rewrite a landed ADR" — add one
  with `Supersedes` (<https://gist.github.com/ericclemmons/96cc6c774e2062e6660f1acb97506940>).
- Vercel's `adr-skill` in the `ai` repo: scan codebase, capture intent, draft, review
  checklist; "if a future agent working in this codebase would benefit from knowing why this
  choice was made, write the ADR"; "Do not rewrite history"
  (<https://github.com/vercel/ai/blob/main/skills/adr-skill/SKILL.md>).
- Anthropic's `knowledge-work-plugins` engineering plugin has an `architecture` skill that
  drafts an ADR (Status Proposed/Accepted/Deprecated/Superseded, options table) and presents
  it for review rather than writing files
  (<https://github.com/anthropics/knowledge-work-plugins/blob/main/engineering/skills/architecture/SKILL.md>).
  No ADR skill exists in `anthropics/skills`.
- `affaan-m/ECC` detects decision moments ("Let's go with X") but "do not auto-create without
  user confirmation" (<https://github.com/affaan-m/ECC/blob/main/skills/architecture-decision-records/SKILL.md>);
  `skillrecordings/adr-skill` uses MADR 4.0 and confirms an intent summary "before anything
  gets written" (<https://github.com/skillrecordings/adr-skill>).
- `rvdbreemen/adr-kit` is the only one with staleness machinery: a `PreToolUse` hook injects
  governing ADR text, a pre-commit check "runs those rules against the staged diff", and a
  "staleness guardian" performs a daily drift check and a bi-weekly LLM audit that "asks
  first" (<https://github.com/rvdbreemen/adr-kit>).
- Claude Code's own best-practices page lists "Architectural decisions specific to your
  project" among what belongs in `CLAUDE.md` and "File-by-file descriptions of the codebase"
  among what does not, and models rationale *recovery* rather than capture: "look through
  ExecutionFactory's git history and summarize how its api came to be"
  (<https://code.claude.com/docs/en/best-practices>).

Every skill found frames the ADR's reader as a future *agent* as much as a person (Vercel:
"a future agent working in this codebase"; adr-kit injects ADRs into the agent's context). All
of them require a human confirmation step before writing, except Clemmons', which relies on
PR merge as acceptance.

### Böckeler's guides and sensors

Birgitta Böckeler's essay (martinfowler.com, 2026-05-27) separates **guides** — Markdown
instructions and skills for the agent — from **sensors** — automated feedback (type checker,
ESLint, Semgrep, dependency-cruiser, tests, incremental mutation testing, GitLeaks, and
"inferential" LLM reviews for coupling and modularity) run in-session, in the pipeline, and on
a slower cadence. She deliberately wrote no guides "for the sake of seeing the effect of the
sensors more purely", asks "Once we feel confident in a set of sensors, what guides can we
delete?", and keeps sensors current by logging their history to find "sensors [that] are never
failing → a signal that they are not necessary". The human-facing artifact — a web UI of
coupling metrics and DSMs — is described as "quite detailed data that needs a lot of context
and experience to interpret", versus a token-frugal summary for the agent; she also reports
having "to ask the agents many, many times why it had not run the sensors check a single time"
(<https://martinfowler.com/articles/sensors-for-coding-agents.html>). Nothing in the essay
concerns document staleness; its living artifact is the sensor history, not prose.

## Provenance and intent capture

### The Agent Trace specification

- **Authorship and status.** The spec is published by Cursor at <https://agent-trace.dev/>
  ("Version: 0.1.0 / Status: RFC / Date: January 2026"), licence CC BY 4.0. Cognition's
  2026-01-29 post, which Phase A treated as the spec's origin, is an endorsement: "We're
  excited to join Cursor, Cloudflare, Vercel, git-ai, Google Jules, Amp, OpenCode and others
  in support of Agent Trace" (<https://cognition.com/blog/agent-trace>). The site's
  "Contributing" section thanks ten partners "for helping shape Agent Trace": Amp, Amplitude,
  Cline, Cloudflare, Cognition, git-ai, Jules, OpenCode, Tapes, Vercel.
- **What it records.** A Trace Record has `version`, `id` (UUID), `timestamp` (RFC 3339),
  `vcs` `{type: git|jj|hg|svn, revision}`, `tool` `{name, version}`, `files[]` and vendor
  `metadata` (reverse-domain keys). Each file lists `conversations[]`, each with a `url` to
  the conversation resource, a `contributor` `{type: human|ai|mixed|unknown, model_id}` (in
  models.dev `provider/model` form), `ranges[]` of `start_line`/`end_line` with optional
  `content_hash` for "position-independent tracking" and per-range contributor override "for
  agent handoffs", and optional `related[]` of session or prompt URLs. **Prompt text is not
  in the record**; the design is URL-by-reference. Cognition's post gives the reason: every
  vendor "has independently developed a url identifier for the 'chat' … a repo with
  associated Agent Traces will always be able to link back to the context that created it. As
  a nice bonus, it helps keep PII and other sensitive information out of the agent trace
  store". Stated non-goals: code ownership or copyright, training-data provenance, quality
  assessment; "UI Agnostic: Agent Trace does not require any specific interface."
- **Where it is stored.** "This spec intentionally does not define how traces are stored.
  This could be local files, git notes, a database, or anything else." Linking to commits is
  via `vcs.revision`; the ownership query is "use VCS blame to find the revision that last
  touched line N" then look up that revision's trace. The FAQ leaves rebases and merges to
  "different implementations in open source" and scripted code generation to the
  implementation. The reference implementation appends NDJSON to `.agent-trace/traces.jsonl`
  at the repo root and wires hooks for Cursor (`.cursor/hooks.json`: `sessionStart`,
  `afterFileEdit`, `afterShellExecution`, …) and Claude Code (`.claude/settings.json`:
  `SessionStart`, `PostToolUse` on `Write|Edit` and `Bash`).
- **Repository state.** The site links <https://github.com/cursor/agent-trace>; on
  2026-09-13 that URL returns 404 from both the authenticated GitHub API and the web. Forks now
  report `superhq-dev/agent-trace` as their parent (created and last pushed 2026-01-29,
  commits "v0.1.0" and "Add OpenCode for their feedback" by Lee Robinson), which is GitHub's
  re-parenting behaviour when an upstream disappears
  (<https://github.com/superhq-dev/agent-trace>); DeepWiki's index of `cursor/agent-trace`
  shows a last-indexed date of 2026-06-23 (<https://deepwiki.com/cursor/agent-trace>). Whether
  the repository was deleted or privatised is unsourced, but it was not renamed or
  transferred: a rename would redirect, and both the web URL and the API return a plain 404
  (re-checked 2026-09-13). The fork network narrows the window: `superhq-dev/agent-trace` is
  now the network root (`fork: false`, 56 forks, no licence) and holds only the first two
  commits, but forks created as late as 2026-06-30 (`zshanhui/agent-trace`) carry the
  upstream's later history — "Add Amplitude" (2026-01-30), "Add Cline" (2026-02-01), "Schema
  version semver (#12)" and "Update TraceRecordSchema version regex (#14)" (2026-02-04/05),
  and a final "Update abstract" (2754f07, 2026-02-06) — whereas a fork created 2026-08-15
  (`Kasifrasi/agent-trace`) descends from the re-parented root, so the canonical repository
  went away between 2026-06-30 and 2026-08-15 and had been dormant since 2026-02-06. The spec
  site still links the dead URL. A GitHub code search for `agent-trace.dev` (2026-09-13) hits
  179 files, all in third-party repositories (VTCode's trace crate, SpecStory's provenance
  docs, `ujjalsharma100/agent-trace-cli`, Trellis research notes, Git Rev News) and none in
  the backers' organisations (cloudflare, vercel, cline, git-ai-project, sourcegraph, sst,
  anomalyco: zero hits each). Git Rev News #135
  (2026-05-31) noted the reference implementation carried "no license provided"
  (<https://github.com/git/git.github.io/blob/master/_posts/2026-05-31-edition-135.markdown>);
  InfoQ's report dates publication to 2026-02-04 and says the RFC "intentionally leaves
  unresolved questions about merges, rebases, and large-scale agent-driven changes"
  (<https://www.infoq.com/news/2026/02/agent-trace-cursor/>).
- **Adoption, checked against each backer's own surfaces.** Cursor's shipped attribution
  product, Cursor Blame (Enterprise only), shows Tab/Agent/Human line attribution, a hover
  "conversation summary (for AI-attributed lines)", and per-commit "percentage attribution for
  Composer, each Agent model, and human edits", with data "cached locally" and summaries
  "retrieved on-demand" from Cursor's servers — and does not mention Agent Trace, git notes
  or a trace file (<https://cursor.com/docs/integrations/cursor-blame>). git-ai's README,
  standard and site contain no Agent Trace reference (<https://github.com/git-ai-project/git-ai>).
  Cloudflare's only "agent tracing" is OpenTelemetry spans for Workers
  (<https://developers.cloudflare.com/agents/runtime/operations/observability/tracing/>).
  Vercel's org code search hits only unrelated OTel files. Jules' changelog has no Agent Trace
  entry; its nearest feature is "Commit Authoring" (2026-02-19) with modes "Jules",
  "Co-authored (Jules + You or You + Jules)" and "User only"
  (<https://jules.google/docs/changelog/>). Amp, OpenCode and Cline: no matches in docs or
  code. Verdict per backer: Cursor — stated authorship, shipped product does not document the
  spec; git-ai — listed, not referenced; all others — not found.
- **Rendering for a reader.** The spec requires none. Cognition's post shows internal tools
  "(all data is mock data unfortunately)": a file viewer attributing AI vs humans, a PR-level
  breakdown, "new interfaces for PR review". No shipped Agent-Trace-consuming UI was found in
  any backer's docs (qualified 2026-09-13: a third-party consumer with a file viewer exists,
  agent-trace-cli, <https://github.com/ujjalsharma100/agent-trace-cli>; see the
  [discourse and tooling addendum](discourse-and-tooling-addendum.md#corrections-proposed)).

### git-ai and the tools that keep the trace in git

- **git-ai** (Apache-2.0, 2,672 stars, v1.7.5 on 2026-09-09) is "an open source git extension
  that tracks the AI-generated code in your repositories". Agents "call `git-ai checkpoint`
  whenever they write code" through managed hooks for Claude Code, Codex, Cursor, Copilot,
  OpenCode, Windsurf, Amp, Gemini and others; "Git AI does not use Git hooks and it does not
  wrap Git". The standard (v3.0.0) requires authorship logs "under the `refs/notes/ai`
  namespace", each note an attestation of session→line-range mappings plus JSON metadata
  (`sessions{agent_id{tool,id,model}}`); the `messages` field "was removed as of v1.3.4 and
  MUST NOT appear in new notes" — sessions "are scanned and redacted, and saved outside of
  Git". `git ai blame` is a drop-in that puts the agent in the author column; `git ai stats`
  reports AI share, accepted rate and human overrides; notes sync on push and fetch, with
  squash/rebase merges on forges needing the Teams product or CI actions. An IDE extension
  shows "the raw prompt or summary" on hover "if session saving is enabled"
  (<https://github.com/git-ai-project/git-ai>,
  <https://github.com/git-ai-project/git-ai/blob/main/specs/git_ai_standard_v3.0.0.md>,
  <https://usegitai.com/docs/get-started/ai-blame>).
- **Entire CLI** (MIT, 5,089 stars, v0.10.6, pushed 2026-09-13; not in Phase A) captures
  "AI agent sessions as you work. Sessions are indexed alongside commits, creating a
  searchable record of how code was written in your repo", to know "why code changed, not
  just what". Checkpoints are their own refs at `refs/entire/checkpoints/<shard>/<id>`
  (metadata, transcripts, subagent records — "never in your branch's history"), each commit
  carries an `Entire-Checkpoint: <id>` trailer, `push_sessions` defaults on, and hooks exist
  for Claude Code, Codex, Copilot CLI, Cursor, Factory Droid, Gemini CLI, OpenCode and Pi. The
  reader-facing surface is `entire checkpoint explain` (with `--generate` for an LLM summary)
  and `entire search` (<https://github.com/entireio/cli>).
- **Commit Context** (AgentsRoom) "captures the conversation of the agent or agents behind
  the commit, uploads it as an unlisted gist, and adds an Agent-Conversation trailer to the
  commit message with the link"; the gist holds "a clean Markdown view of the conversation
  for humans, plus the raw transcript"; secrets are redacted "on a best-effort basis … Treat
  it as a safety net, not a guarantee"; the upload runs before the commit and "if anything
  fails, the commit still goes through without the trailer"; on by default, per-project
  opt-out, 14 agent CLIs (<https://agentsroom.dev/features/commit-context>).
- **Memento** (F#, 450 stars, last push 2026-03-12): summary Markdown in `refs/notes/commits`
  and the full transcript in `refs/notes/memento-full-audit`, for Codex and Claude Code
  (<https://github.com/mandel-macaque/memento>).
- **Agent Blame** (Mesa, 101 stars) is the one tool found that renders provenance *inside the
  forge* for a reader: a browser extension paints "orange gutter markers on GitHub PRs, hover
  shows tool, model, prompt" from git notes written by Cursor/Claude Code/OpenCode hooks
  (<https://github.com/mesa-dot-dev/agentblame>).
- **gitwhy** (6 stars, one weekend in July 2026) reconstructs links after the fact from
  `~/.claude/projects/**/*.jsonl` and `~/.codex/sessions/**/rollout-*.jsonl` by file overlap,
  time windows and `git commit` commands seen in the transcript, emits an interactive
  `gitwhy-report.html` of per-file "origin stories" and a `GITWHY.md` for agents, and has an
  `archive` command because "Claude Code deletes them" (<https://github.com/mehrtam/gitwhy>).
- **blameprompt** (Rust, 3 stars) writes per-prompt "receipts" (model, cost, tokens, files
  and ranges, prompt and response summaries) to `refs/notes/blameprompt` via a post-commit
  hook, with `blame`, `audit` and a dashboard (<https://github.com/Ekaanth/blameprompt>);
  **ai-blame** (6 stars) parses Claude Code and Codex traces into DuckDB and can `annotate`
  YAML/JSON files with provenance sidecars (<https://github.com/ai4curation/ai-blame>);
  **code-provenance** is a one-day design sketch of a capture→pre-commit→CI-gate→compliance
  PDF pipeline (<https://github.com/QAInsights/code-provenance>); **cnotes** (24 stars, 2025)
  writes "Recent user prompts" to git notes from Claude Code hooks
  (<https://github.com/imjasonh/cnotes>); **AIttributor** (Block) adds a `Co-authored-by:`
  trailer for the detected agent (<https://github.com/block/aittributor>); **tempo-cli**
  records adoption metadata with "no source code, diffs, prompts, or conversation transcripts"
  (<https://github.com/usetempo/tempo-cli>). SpecStory's repo carries an internal survey
  (`specstory-cli/docs/git-provenance/`) comparing Agent Trace with W3C PROV, OTel GenAI,
  in-toto, SLSA and C2PA and listing agentblame, aider, aittributor, cnotes, entire, git-ai,
  git-with-intent, tempo-cli and whogitit (<https://github.com/specstoryai/getspecstory>).
- **Amp** writes an `Amp-Thread-ID` trailer into commits so a change links back to its
  thread (<https://ampcode.com/docs/threads>); Copilot's cloud agent puts "a link to the
  session logs" in each commit message (below).

Three storage designs are in use: git notes (`refs/notes/ai`, `refs/notes/blameprompt`,
`refs/notes/commits`), separate refs (`refs/entire/checkpoints/…`), and a commit-message
trailer pointing at an external store (Commit Context's gist, Amp's thread URL, Copilot's
session log, Agent Trace's conversation `url`). Prompt text is kept in-repo only by
Memento, cnotes and blameprompt; git-ai and Agent Trace moved it out deliberately.

### Who renders a trace for a human reader

Reader-facing surfaces found: git-ai's `git ai blame` column and IDE hover; Cursor Blame's
hover summaries and per-commit percentages (Enterprise); Agent Blame's PR gutter markers;
Entire's `checkpoint explain`; gitwhy's HTML report; Commit Context's "clean Markdown view";
Simon Willison's `claude-code-transcripts`, which renders local sessions as paginated HTML
with "a timeline of prompts and commits" and can publish to a Gist
(<https://github.com/simonw/claude-code-transcripts>); and `claude-replay`, which converts
Claude Code, Cursor, Codex, Gemini and OpenCode sessions to self-contained HTML
(<https://github.com/es617/claude-replay>). Willison's own stated practice is to link
transcripts from commit messages: "The actual work that I do is now increasingly represented
by these Claude conversations" and readers can use "the commit log to find links to the
transcripts for each commit" (<https://simonwillison.net/2025/Dec/25/claude-code-transcripts/>).
No forge (GitHub, GitLab) renders any of these formats natively.

### Harness transcript retention versus commit-linked provenance

- **Claude Code** stores "session transcripts locally in plaintext under `~/.claude/projects/`
  for 30 days by default to enable session resumption. Adjust the period with
  `cleanupPeriodDays`" (<https://code.claude.com/docs/en/data-usage>). The layout is
  `projects/<project>/<session>.jsonl` — "Full conversation transcript: every message, tool
  call, and tool result" — plus `subagents/` and `tool-results/`; "the default is 30 days and
  the minimum is 1; setting `0` fails with a validation error"; transcripts touched from
  Claude Desktop or Cowork are exempt unless `desktopSessionCleanupPeriodDays` is set
  (<https://code.claude.com/docs/en/claude-directory>). `/export [filename]` writes "the
  current conversation as plain text"; `/share` is an alias of `/bug` — it submits the
  transcript to Anthropic (5-year retention) rather than producing a link
  (<https://code.claude.com/docs/en/commands>, data-usage page). Claude Code on the web
  sessions have Private/Team (or Public on Pro/Max) visibility and a shareable link whose
  "recipients see the latest state when they open the link" (<https://code.claude.com/docs/en/claude-code-on-the-web>).
  Server-side retention is 30 days for commercial and non-training consumer accounts.
- **Codex CLI** writes rollouts to
  `~/.codex/sessions/rollout-<timestamp>-<conversation_id>.jsonl` and an
  `archived_sessions/` directory (source, `codex-rs/rollout/src/recorder.rs`), with prompt
  history in `~/.codex/history.jsonl` under `history.persistence = save-all|none`
  (<https://github.com/openai/codex>, <https://learn.chatgpt.com/docs/config-file/config-reference>);
  `codex resume` continues "by ID or … the most recent chat"
  (<https://learn.chatgpt.com/docs/developer-commands?surface=cli>). No retention window or
  share URL is documented.
- **OpenCode** keeps session and message data under `~/.local/share/opencode/project/` with
  no stated retention (<https://opencode.ai/docs/troubleshooting/>); `/share` yields
  `opncd.ai/s/<share-id>` showing "full conversation history", modes manual (default), auto
  and disabled, and "shared conversations remain accessible until you explicitly unshare
  them" (<https://opencode.ai/docs/share/>).
- **Cursor** shares transcripts to Team or Public links ("The full conversation history is
  shared, including code snippets, tool calls, and their results"; "best-effort redaction";
  Teams/Enterprise only; 50 shares per day) (<https://cursor.com/help/ai-features/shared-transcripts>).
- **Amp** gives every thread a URL, visibility Private/Workspace/Group/Unlisted, workspace
  threads shared with the workspace by default, and ended public discoverable threads on
  2026-06-02 because "It's getting too hard to review a thread to ensure it doesn't contain
  any snippets of sensitive files" (<https://ampcode.com/docs/threads>,
  <https://ampcode.com/news/end-of-public-threads>).
- **GitHub Copilot cloud agent**: "Session logs show Copilot's internal reasoning and the
  tools it used"; "Each commit message includes a link to the session logs, so you can trace
  why a change was made during code review or an audit"; cloud sessions "are shared by
  default" with anyone who can access the repository; retention not stated
  (<https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/track-copilot-sessions>).
- **Warp** shared agent sessions "expire automatically about one week after you create the
  share" (<https://docs.warp.dev/agents/local-agents/session-sharing/>).

The interaction Phase A asked about is therefore concrete: a commit-linked pointer into
`~/.claude/projects/` (gitwhy, ai-blame, Willison's tool) dereferences to nothing after 30
days unless `cleanupPeriodDays` is raised or the transcript is copied out (gitwhy's `archive`,
Entire's refs, Memento's notes, Commit Context's gist). Agent Trace's `url` field inherits
whatever retention the vendor's conversation store has; none of the vendor pages above states
a retention period for those URLs except Warp (one week) and OpenCode (until unshared).

### Forge-level attribution

GitHub's `Co-authored-by: name <email>` trailer counts as a contribution only "if you use an
email address associated with their account"; the page says nothing about AI
(<https://docs.github.com/en/pull-requests/committing-changes-to-your-project/creating-and-editing-commits/creating-a-commit-with-multiple-authors>).
Copilot cloud-agent commits "are authored by Copilot, with the person who started the task
listed as co-author" and are signed (track-copilot-sessions page above). GitLab's Duo
composite identity attributes the merge request "to the human user who triggered the flow"
while commits "show they were created by the service account on your behalf", on the stated
principle that "prompting an AI system to write code is equivalent to writing the code
yourself"; no "AI-generated" badge is documented
(<https://docs.gitlab.com/user/duo_agent_platform/composite_identity/>). Ghostty's AI policy
requires that "All AI usage in any form must be disclosed" with the tool named, but specifies
no trailer (<https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md>). Empirically,
Robbes et al. found "coding agents tend to leave more explicit traces … such as co-authoring
commits or pull requests" across 128,018 projects (<https://arxiv.org/abs/2601.18341>), and
Yu et al. found PRs with a human `Co-Authored-By` trailer merge less often than purely
autonomous ones (53.8% vs 79.8%) until repository selection and PR structure are controlled
(<https://arxiv.org/abs/2606.22711>).

### The essay position

Blake Crosley's "Agent sessions are the real commit messages we discard" (2026-03-02) argues
git records *what* while the session holds *why*, proposes four metadata layers (intent,
process, reasoning, verification), and names mechanisms: git notes (Memento), transcripts
exported to `.sessions/<date>-<slug>.md`, trailers such as `Agent: Claude Code` and
`Session-Duration`, and "evidence gates"; he prices a session at 500 KB–2 MB raw and warns
that transcripts leak keys and stack traces (<https://blakecrosley.com/blog/session-is-the-commit-message>).

## The dialog as artifact

### Literate programming

Knuth's 1984 paper states the addressee inversion that every later item repeats: "Instead of
imagining that our main task is to instruct a computer what to do, let us concentrate rather
on explaining to human beings what we want a computer to do." The literate programmer is "an
essayist, whose main concern is with exposition and excellence of style … a program that is
comprehensible because its concepts have been introduced in an order that is best for human
understanding"; WEB "allows a person to express programs in a 'stream of consciousness'
order. TANGLE is able to scramble everything up into the arrangement that a PASCAL compiler
demands. This feature of WEB is perhaps its greatest asset" (*The Computer Journal* 27(2),
<https://doi.org/10.1093/comjnl/27.2.97>; text from the author-distributed PDF at
<https://www.cs.tufts.edu/~nr/cs257/archive/literate-programming/01-knuth-lp.pdf>). Asked in
2008 why it did not spread, Knuth answered: "It has tens of thousands of fans, but not
millions"; software written this way "turned out to be significantly better", but "ordinary
software is usually okay — I'd give it a grade of C (or maybe C++), but not F; hence, the
traditional methods stay with us"; and, quoting Bentley, "a small percentage of the world's
population is good at programming, and a small percentage is good at writing; apparently I am
asking everybody to be in both subsets"
(<http://www.informit.com/articles/printerfriendly.aspx?p=1193856>).

Descendants keep the inversion and add the executable record. Literate CoffeeScript treats
indented blocks as code "and ignore[s] the rest as comments" (<https://coffeescript.org/#literate>);
Org-mode Babel takes Knuth's sentence as its motto and makes "the entire document …
executable" for reproducible research (<https://orgmode.org/worg/org-contrib/babel/intro.html>).
Jupyter's founders name the artifact: the Notebook lets users "author computational
narratives that combine live code, equations, narrative text, interactive user interfaces and
other rich media" (2015 grant announcement, <https://blog.jupyter.org/project-jupyter-computational-narratives-as-the-engine-of-collaborative-data-science-2b5fb94c3c58>,
page blocked to direct fetch; phrasing from its search index), and argue that "Jupyter helps
humans to think and tell stories with code and data" (Granger and Pérez, *CiSE* 2021,
<https://doi.org/10.1109/MCSE.2021.3059263>). nbdev's statement is the one Phase A already
cited — "Traditional programming environments throw away the result of your exploration in
REPLs or notebooks" — with `#| export` / `#| exporti` / `#| hide` directives selecting what
becomes module, docs or neither (<https://nbdev.fast.ai/>,
<https://nbdev.fast.ai/explanations/directives.html>). The 2019 launch post's URL now 404s;
Phase A's citation stands.

No controlled study measuring comprehension gains from literate programming was found. Shum
and Cook (SIGCSE 1994) reported that an LP course "encourages more documentation", a quantity
measure (<https://doi.org/10.1145/191029.191059>); Pieterse, Kourie and Boake (2004) is a
position paper (<https://doi.org/10.5555/1035053.1035054>); Colaroid (CHI 2023) found
advantages for tutorial *readers* over video and web tutorials in two lab studies
(<https://doi.org/10.1145/3544548.3581525>).

### Solveit's curated dialog versus the append-only trace

The Solveit note documents the mechanics: a dialog is a linear `.ipynb` of note, code and
prompt messages; `H` hides a message from the AI while a person still sees it, `P` pins,
messages can be edited and deleted, sections collapse with token counts, `E` exports cells to
a module, and dialogs publish as gist, `.ipynb`, `.md`, `.py`, read-only page or fork link
([product mechanics](solve-it-sweep.md#product-mechanics)). Its
[mapping](solve-it-sweep.md#mapping-to-the-phase-a-landscape) states the contrast this note
inherits: the provenance cluster "keeps the agent's raw trace"; Solveit's record "is curated
by editing and deletion; what survives is what the person decided was worth keeping"; and
"whether anyone other than the author reads a dialog is … not checked by the tool."

Other tools that let a person edit the AI dialog and keep the edited version as the record:
Zed's text threads let you "go back and edit earlier messages — including previous LLM
responses — to change direction, refine context, or correct mistakes", saved under
`~/.config/zed/conversations`; they were removed on 2026-03-31 ("All AI conversations now
happen through the Agent Panel") (<https://raw.githubusercontent.com/zed-industries/zed/main/docs/src/ai/text-threads.md>,
PR #52757). gptel: "You can go back and edit previous prompts and responses if you want …
Saving the file will save the state of the conversation as well", and in Org "each
hierarchical outline path through the document is a separate conversation branch"
(<https://github.com/karthink/gptel>). org-ai keeps `#+begin_ai` blocks inside the Org file
(<https://github.com/rksm/org-ai>). Jupyter AI stores "the entire history of the chat" in a
`.chat` file that can be reopened and resumed
(<https://jupyter-ai.readthedocs.io/en/latest/users/index.html>). Cursor's plan mode saves
plans as Markdown that can be edited and "Save[d] to workspace … for future reference, team
sharing, and documentation" (<https://cursor.com/docs/agent/plan-mode>). Claude Code's
`/rewind` offers "Summarize from here" / "Summarize up to here", a curation of context rather
than of the stored transcript (<https://code.claude.com/docs/en/best-practices>). Every
vendor share feature listed in the provenance section (OpenCode, Cursor, Amp, Copilot, Warp,
Claude Code on the web) shares the *append-only* thread; Warp's and Claude Code's "fork"
creates a copy "without modifying the original".

### Litt's explainer as artifact

Litt's written version of the talk (2026-07-02) states the principle — "Whenever an agent
finishes some work, it's an opportunity for an explanation — an artifact" — and his reading
habit: "The end result of all of this is a nice explainer packet. I still read the code diff
but I always read this first"; "Sometimes I'll print these out and take them to the café."
Notion "is a good place for collaborating on and discussing these explainers as a team", and
interactive figures use "a new feature Notion just shipped: you can now embed interactive HTML
inside pages" (<https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck>).
The essay does not say whether explainers are retained, versioned, or re-read after review;
the skill is the gist Phase A analysed
([Proposal 1](understanding-bottleneck-talk.md#proposal-1-code-explainer-docs-explain-diff)).
The essay does not mention Naur.

### Research on transcripts and prompts as documentation

- **DevGPT** (Xiao et al., MSR 2024 Mining Challenge): 29,778 prompt/response pairs from
  shared ChatGPT links "linked to corresponding software development artifacts such as source
  code, commits, issues, pull requests, discussions" (<https://arxiv.org/abs/2309.03914>).
- **Hao et al. (2024)** on 210 PR and 370 issue conversations: sharing is "to facilitate
  their role-specific contributions"; multi-turn conversations are 33.2% in PRs and 36.9% in
  issues (<https://arxiv.org/abs/2403.10468>).
- **Li et al. (TOSEM 2026)** on 2,547 shared links: interactions are "short and task-focused
  (most are 1-3 turns)"; developers share "to delegate tasks, resolve problems, and acquire
  knowledge" (<https://arxiv.org/abs/2505.03901>).
- **AfterVibe** (Paltenghi and Chandra, 2026-07) recovers a natural-language specification
  from "a code artifact and the conversation trajectory that produced it", validated by blind
  regeneration (mean 5.06/6 on 72 internal projects), and proposes that "specifications — not
  code — could become the primary artifact for human review and the source of record"
  (<https://arxiv.org/abs/2607.09900>).
- **Yuan et al. (2026-07)** propose "verifiable literate programming": "unambiguous NL-based
  documentation as a readable intermediate layer between prompts and code", with "trace links
  between prompts and documentation"; pass@1 rises "from 28.7%–73.2% to 65.4%–93.5%"
  (<https://arxiv.org/abs/2607.02333>).
- **Robbes et al. (TOSEM)** and **Watanabe et al. (TOSEM)** measure agent PR adoption and
  merge outcomes (567 Claude Code PRs, 83.8% merged, 54.9% unmodified), not comprehension
  (<https://arxiv.org/abs/2601.18341>, <https://arxiv.org/abs/2509.14745>).

Nothing found measures whether shared transcripts are later read, whether the links remain
accessible over time, or whether reading a transcript improves a maintainer's comprehension.

## Shared spaces and shared vocabulary

### Litt's proposal

The essay's shared-spaces passage is short: "When you and someone else hold the same mental
model, you can communicate efficiently. You have a shared vocabulary that evokes the same
images, so you can jam and riff"; "I'm really excited about creating shared environments where
teams build that understanding together"; and the one concrete mechanism, "when those agents
make a technical plan in Notion, it's in a collaborative page by default, so I can comment on
it with my team and discuss immediately" (<https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck>).
The talk's spoken version added multiplayer threads — "going from one-on-one conversations to
Slack channels" — and the claim that his team "builds a lot of our code in Notion itself"
([Phase A](understanding-bottleneck-talk.md#proposal-4-shared-spaces)); neither appears in
the written essay.

### Notion's External Agents

Notion 3.6 (2026-07-01): "Claude and Cursor are the first two External Agents in Notion";
teams "assign tasks to external agents from shared boards and @-mention them like teammates";
"Notion Agents can create interactive HTML blocks within docs" that teammates "can use or
iterate on … without leaving Notion" (<https://www.notion.com/releases/2026-07-01>). The
Claude-agents help page: sessions "appear in Agent Activity and on the page or task where the
agent runs"; agents "chat with you and your teammates in Notion to answer questions and
coordinate work"; "Claude agents can only see what you share with them. Permissions are set
per agent and aren't inherited from whoever starts a run"; hosting is "by Notion via
Anthropic's infrastructure" (<https://www.notion.com/help/use-claude-agents-in-notion>). The
task-board guide is the closest vendor text to a multiplayer thread: "While Claude works, it
posts updates to the task card so anyone with access can follow along"; "Leave a comment on
the task to redirect the agent, ask a clarifying question, or add context. Anyone with access
can do this, so a teammate watching the run can step in without taking over"
(<https://www.notion.com/help/guides/how-to-set-up-claude-agents-on-your-teams-notion-task-board>).
Cursor-in-Notion runs "entirely on Cursor's infrastructure" with results appearing "on the
page or task where the agent ran" (<https://www.notion.com/help/connect-cursor-to-notion>).
No help article documents interactive HTML blocks or shared agent chats beyond these.

### Multiplayer human-plus-agent threads elsewhere

- **Amp Multiplayer** (2026-07-22): "Anyone in your workspace can then join the thread, send
  messages to the agent, and access the orb's portal, file changes, and shared terminal"
  (<https://ampcode.com/news/multiplayer>); workspace-project threads are workspace-visible by
  default (<https://ampcode.com/docs/enterprise/workspace-thread-visibility-controls>).
- **Linear agents** "function similar to other users in a workspace. They can be @mentioned,
  delegated issues through assignment, create and reply to comments"; agent sessions are
  "created automatically when an agent is mentioned or delegated an issue" and "session state
  is visible to users, and updated automatically based on the agent's emitted activities"
  (<https://linear.app/developers/agents>).
- **GitHub Copilot cloud agent**: sessions "are shared by default" in the repository's Agents
  tab; the PR thread is where humans comment and the agent responds
  (<https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/track-copilot-sessions>).
- **Devin in Slack**: "Messages you send in the webapp appear in the thread, and replies in
  the thread reach Devin" (<https://docs.devin.ai/integrations/slack.md>); Session Insights
  advise "Add key learnings as Knowledge so your teammates can benefit"
  (<https://docs.devin.ai/product-guides/session-insights.md>).
- **Claude Code on the web**: Team visibility for sessions; "Claude in Slack sessions are
  automatically shared with Team visibility"; inline diff comments can be sent "to Claude
  with your next message" (<https://code.claude.com/docs/en/claude-code-on-the-web>).
- **Warp**: cloud-synced conversation links default to "Anyone on your team"; continuing
  someone else's "creates a fork" (<https://docs.warp.dev/agents/local-agents/cloud-conversations/>).

In every product above the shared object is the thread or task; none describes a shared
vocabulary or model artifact that the thread feeds.

### Shared vocabulary as the theory's carrier

- **Naur** locates the theory in the team: a program dies "when the programmer team
  possessing its theory is dissolved", and newcomers acquire it by working "in close contact
  with the programmers who already possess the theory"
  ([Phase A](evidence-and-mechanisms.md#naur-the-theory-is-not-in-the-text), citing the
  reprint at <https://pages.cs.wisc.edu/~remzi/Naur.pdf>, pp. 253–261; the PDF is a scan
  without a text layer, so the page numbers are Phase A's).
- **Domain-Driven Design.** Evans' ubiquitous language is the team's model made spoken and
  written; arc42's glossary section names it explicitly (above). BDD's Cucumber docs make the
  same claim for executable examples: teams "use problem-domain terminology all the way down
  into the code", and "the code reflects the documentation, and the documentation reflects the
  team's shared understanding of the problem domain" (<https://cucumber.io/docs/bdd/>).
- **Contextive** is the glossary tool found closest to code: "a suite of tools to immerse
  developers in the language of their users' domains", with definitions in
  `.contextive/definitions.yml` in the repository, surfaced "through hover panels and
  auto-complete suggestions … in code, comments, configuration files, and documentation",
  supporting monorepos with several bounded contexts and one context spread over several
  repositories (<https://github.com/dev-cycles/contextive>, <https://docs.contextive.tech/>).
- **Shared mental models in software teams.** Levesque, Wilson and Wholey (2001) followed
  software project teams over time and found that "contrary to predictions, team members'
  mental models about the group's work and each other's expertise did not become more similar
  over time"; "as role differentiation increased in these teams, it led to a decrease in
  interaction and a corresponding decline in shared mental models"
  (<https://doi.org/10.1002/job.87>).

## Evidence

### Design rationale: capture cost versus use

- **Karsenty (CHI 1996)** gave six experienced designers a past design's solution documents
  plus QOC rationale documents and recorded their questions. Rationale questions were "by far
  the most frequent" (63% for engineers, 49% for technicians). Of 76 rationale questions, "41%
  … (31 out of 76) were answered by the DR", not varying with competence (43% technicians,
  38% engineers). The 45 unanswered questions were attributed to analysts not recording known
  justifications (14), the QOC method itself (1), readers' misconceptions and inappropriate
  questions (19), and the project team never having considered the issue, option or criterion
  (11). Conclusion: DR "should be useful, at least for some designers who use it as a support
  to their reasoning, but not sufficient"
  (<https://doi.org/10.1145/238386.238462>; full text at
  <https://chi1996.acm.org/proceedings/papers/Karsenty/lk_txt.html>).
- **Tang, Babar, Gorton and Han (JSS 2006)** surveyed 81 practitioners: "practitioners
  recognize the importance of documenting design rationale and frequently use them"; rated
  importance of benefits, constraints and certainty of design 90.1%, 87.6% and 85.2%, but the
  frequency of *documenting* them fell to 69.1%, 82.7% and 46.9%; "the reasons about why a
  design is chosen and why it is better than alternative designs are usually not documented";
  the top barrier is "lack of time/budget (60.5%)", with lack of standards and tools next, and
  only 4.9% unaware of the need; 62.9% say they "completely document" rationale, 44%
  document discarded options "very often" and 36% do not; the tools in use are Word, UML
  tools and in-house templates — "DR tools like gIBIS are not used"
  (<https://doi.org/10.1016/j.jss.2006.04.029>; technical-report text at
  <https://core.ac.uk/download/301360472.pdf>).
- **Bratthall, Johansson and Regnell (PROFES 2000)**: 17 subjects from industry and academia
  did change-impact tasks on two embedded systems with and without a retrospective design
  rationale; "for one of the systems, there is a significant improvement in correctness and
  speed when subjects have access to a design rationale document"; for the other "the results
  were inconclusive" (<https://doi.org/10.1007/978-3-540-45051-1_14>).
- **Falessi, Briand, Cantone, Capilla and Kruchten (TOSEM 2013)**: full rationale
  documentation "is typically too onerous for systematic industrial use as it is not cost
  effective to write, maintain, or read"; two controlled experiments with 75 master students
  showed "the value of a DRD information item significantly depends on its category and …
  on the activity it supports", and documenting only items required at least half the time
  yields "about half the information items of a full documentation"
  (<https://doi.org/10.1145/2491509.2491515>; the WICSA 2008 feasibility study is
  <https://doi.org/10.1109/wicsa.2008.8>).
- **Shum and Hammond (IJHCS 1994)**, "Argumentation-based design rationale: what use at what
  cost?" (<https://doi.org/10.1006/ijhc.1994.1029>), and **Horner and Atwood (2006)** on the
  barriers (above) are the standard cost-side references; their abstracts could not be
  retrieved (ACM and Springer returned 403), so no numbers are quoted here.

### ADR adoption

Buchgeher, Schöberl, Geist and Dorninger's MSR study of GitHub (IEEE Access 2023): "the
adoption of ADRs is still low, although the number of repositories using ADRs is increasing
every year. About 50% of all repositories with ADRs contain just one to five ADRs suggesting
that the concept has been tried but not yet definitively adopted"; where used systematically,
"recording decisions is a team activity conducted by two or more users over a longer period
of time"; "in most repositories the template proposed by Michael Nygard is used"
(<https://doi.org/10.1109/access.2023.3287654>; the open-access PDF was blocked, so
repository counts are not quoted). Capilla, Jansen, Tang and Avgeriou's ten-year review of
architecture knowledge management (JSS 2016) concludes that "the cost to capture this
relevant knowledge hampers a widespread use by software companies" and that "improvements
made over the last decade didn't boost a wider adoption of AKM approaches"
(<https://doi.org/10.1016/j.jss.2015.08.054>; abstract only).

### Documentation use and staleness

- **Forward and Lethbridge (DocEng 2002)** surveyed 48 software professionals: 68% agreed
  that "documentation is always outdated relative to the current state of a software system"
  (43% somewhat, 25% strongly; thesis mean 3.60, 30 of 44 agreeing), while "useful even if not
  up to date" scored 3.96 (37 of 46 agreeing); the modal update frequency for requirements,
  specification, design and architecture documents was "Rarely"; 82% agreed that tools to
  track code changes for documentation maintenance would be useful and 72% that automated
  tests serve as documentation (<https://doi.org/10.1145/585058.585065>; author PDF
  <https://www.site.uottawa.ca/~tcl/gradtheses/aforward/papers/aforwarddoceng2002sub.pdf>;
  thesis <http://www.site.uottawa.ca/~tcl/gradtheses/aforward/aforward_thesis.doc>). The
  companion "Qualities of Relevant Software Documentation" reports that "not-so-up-to-date
  documents could still be an effective resource" even though up-to-dateness was among the
  most important attributes for 46%
  (<https://www.site.uottawa.ca/~tcl/gradtheses/aforward/papers/aforward_icse2003_sub.pdf>).
  Lethbridge, Singer and Forward's IEEE Software 2003 synthesis: engineers "typically do not
  update documentation as timely or completely as software process personnel and managers
  advocate. However … out-of-date software documentation remains useful in many
  circumstances" (<https://doi.org/10.1109/ms.2003.1241364>; abstract only).
- **Aghajani et al. (ICSE 2019)** mined 878 documentation-related artifacts from mailing
  lists, Stack Overflow, issues and PRs into a taxonomy of documentation issues
  (<https://doi.org/10.1109/icse.2019.00122>); **Aghajani et al. (ICSE 2020)** surveyed 146
  practitioners on which issues matter and which document types matter per task
  (<https://doi.org/10.1145/3377811.3380405>).
- **Wen, Nagy, Bavota and Lanza (ICPC 2019)** mined 1.3 billion AST-level changes across
  1,500 systems to characterise which code changes trigger comment updates and which
  inconsistencies developers later fix (<https://doi.org/10.1109/icpc.2019.00019>).
- **Stack Overflow 2024**: 56% "can quickly find answers to my questions with existing tools
  and resources"; 61% spend over 30 minutes a day searching for answers; 30% hit knowledge
  silos "10+ times a week" (<https://survey.stackoverflow.co/2024/professional-developers>).
- **Google** (above) attaches human `reviewed:` dates and email reminders at three months, and
  states that tooling for measuring accuracy and freshness "has still not caught up".

### Accuracy of generated documentation and rationale

- **Dhar, Vaidhyanathan and Varma (ICSA 2024)**: GPT-4 "generate[s] relevant and accurate
  Design Decisions, although they fall short of human-level performance"; GPT-3.5 few-shot and
  fine-tuned Flan-T5 reach "similar outcomes"; "further research is required to attain
  human-level generation" (<https://arxiv.org/abs/2403.01709>). The follow-up **DRAFT**
  (2025) combines retrieval, few-shot and fine-tuning on 4,911 ADRs and "outperforms all other
  approaches in effectiveness" by automated metrics and human judgement
  (<https://arxiv.org/abs/2504.08207>).
- **RepoAgent (2024)** reports "both qualitative and quantitative evaluations" concluding it
  "excels in generating high-quality repository-level documentation"; the abstract gives no
  accuracy figure (<https://arxiv.org/abs/2402.16667>).
- **Sun et al. (2023)** found ChatGPT's code summaries "significantly worse than all three
  SOTA models" by BLEU and ROUGE-L on CSN-Python — a distribution-match measure, not a
  correctness one (<https://arxiv.org/abs/2305.12865>).
- **DeepWiki and Code Wiki**: neither vendor publishes an accuracy evaluation; DeepWiki's
  only claim is "detailed and accurate answers grounded in your code" for Ask Devin
  (<https://docs.devin.ai/work-with-devin/deepwiki>); the Code Wiki launch post makes no
  accuracy claim (<https://developers.googleblog.com/introducing-code-wiki-accelerating-your-code-understanding/>).
  No independent evaluation was located (search unavailable; see Dead ends).

### What is not measured

No study found measures whether an agent-maintained document, an ADR written by an agent, a
provenance trace, or a curated dialog is later read, kept current, or improves a maintainer's
comprehension of the code it describes. The rationale literature's positive results
(Karsenty's 41%, Bratthall's one-of-two systems, Falessi's category-dependence) all concern
human-written rationale read by humans; the AI-era papers evaluate generation quality against
human-written references, not downstream use.

## Open questions in the sources

- Agent Trace's FAQ: "How should I handle rebases or merge commits? We expect to see
  different implementations in open source. This may influence the spec in the future."
  Storage is left open by design (<https://agent-trace.dev/>).
- Cognition on Agent Trace: the tools shown use "mock data unfortunately"
  (<https://cognition.com/blog/agent-trace>).
- Kiro issue #1818 asks whether steering refinement can detect that anything changed; the
  issue was closed "not planned" (<https://github.com/kirodotdev/Kiro/issues/1818>).
- Google: whether documentation can "be measured for aspects such as accuracy, freshness,
  etc. (tools have still not caught up here)" (<https://abseil.io/resources/swe-book/html/ch10.html>).
- Karsenty: whether recording spontaneous explanations, rather than argument structures, would
  close the 59% gap; he notes that in design dialogues "83% of the explanations were
  volunteered" rather than answered (<https://chi1996.acm.org/proceedings/papers/Karsenty/lk_txt.html>).
- Tang et al.: "We do not have any theoretical grounds for explaining" why designers document
  benefits and constraints but not why the chosen design beat the alternatives
  (<https://core.ac.uk/download/301360472.pdf>).
- Bratthall et al.: why rationale helped on one system and not the other; "further studies
  are recommended" (<https://doi.org/10.1007/978-3-540-45051-1_14>).
- Dhar et al.: how to "attain human-level generation and establish standardized widespread
  adoption" of LLM-written decisions (<https://arxiv.org/abs/2403.01709>).
- Buchgeher et al.: how to "further increase the adoption of ADRs" given the one-to-five-ADR
  pattern (<https://doi.org/10.1109/access.2023.3287654>).
- Amp: how to share threads at all when "it's getting too hard to review a thread to ensure
  it doesn't contain any snippets of sensitive files" (<https://ampcode.com/news/end-of-public-threads>).
- Knuth: "If nobody likes it but me, let it die" — whether literate programming needs both
  the programmer and the writer in one person (<http://www.informit.com/articles/printerfriendly.aspx?p=1193856>).
- Litt: nothing in the essay says whether an explainer is re-read after the review it was
  written for.

## Dead ends

- **Agent Trace's canonical repository** (`github.com/cursor/agent-trace`) returns 404 as of
  2026-09-13; content was recovered from a re-parented fork. Whether it was deleted or made
  private is unsourced; that it was not renamed, its last commit date, and the window in which
  it disappeared are established from fork metadata (see Repository state above). Wayback's
  CDX and availability APIs rate-limited every query for this URL on 2026-09-13.
- **No backer other than Cursor** documents emitting or consuming Agent Trace; Cursor's own
  Cursor Blame docs do not mention it.
- **No tool records that a human read a generated document**; the only attestation found is
  Google's pre-AI `reviewed:` freshness date and the AWS ADR review slot.
- **No accuracy evaluation of DeepWiki or Code Wiki**, vendor or independent, was located.
- **No study of transcript link rot, transcript readership, or comprehension gains from
  reading transcripts** was found; the DevGPT-lineage papers characterise sharing, not use.
- **No controlled comprehension study of literate programming** was found.
- **Devin's session-sharing** page is absent from `docs.devin.ai`'s index; only Slack sync
  and Session Insights are documented.
- **Cursor Memories** no longer has a docs page; its approval flow is unsourced.
- **Mutable Auto Wiki** domains do not resolve; **Trelent** has pivoted; **Sweep** docs
  returned HTTP 402; **whogitit** (cited by SpecStory's survey) is 404.
- **Paywalled classics**: Shum and Hammond 1994, Horner and Atwood 2006, Dutoit et al.
  2006 ch. 1, Lee 1997's seven issues, Grudin 1996's four environments, Garousi et al. 2015,
  Bhat et al. 2017, Keeling and Runde's Agile 2017 report, Woodfield et al. 1981 and Tenny
  1988 could not be read; Lethbridge et al. 2003, Capilla et al. 2016 and Buchgeher et al.
  2023 are cited from their abstracts only. No Google-hosted ADR guidance page was found.
- **Tooling limits this session**: the shared WebSearch budget was exhausted early, and
  DuckDuckGo, Bing, arXiv's API and Semantic Scholar rate-limited or blocked scripted queries,
  so coverage of 2025–2026 preprints on generated-documentation hallucination and on
  "prompts as documentation" is incomplete. Crossref, CORE and direct vendor pages were used
  instead.
- **Naur's reprint PDF** is a scan without a text layer; page references are Phase A's.
- **The "team as theory holder" passage** and Evans' *Domain-Driven Design* chapter 2 were
  not re-read from the primary text this session; Evans is cited via arc42's and Cucumber's
  use of "ubiquitous language" and via Contextive's stated lineage.

## References

Pre-AI rationale and documentation

- Nygard, "Documenting Architecture Decisions" (2011): <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>
- adr-tools: <https://github.com/npryce/adr-tools>; MADR: <https://adr.github.io/madr/>;
  Henderson's collection: <https://github.com/joelparkerhenderson/architecture-decision-record>
- Thoughtworks Radar, Lightweight ADRs: <https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records>
- AWS Prescriptive Guidance, ADR process: <https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html>
- Microsoft Azure Well-Architected, ADR: <https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record>
- Kopp, Armbruster and Zimmermann, MADR (2018): <https://ceur-ws.org/Vol-2072/paper9.pdf>;
  Keeling (2022): <https://doi.org/10.1109/ms.2022.3198195>
- Write the Docs, Docs as Code: <https://www.writethedocs.org/guide/docs-as-code/>
- arc42: <https://arc42.org/overview>, <https://docs.arc42.org/section-9/>; Structurizr:
  <https://docs.structurizr.com/dsl/language>, <https://docs.structurizr.com/dsl/adrs>,
  <https://docs.structurizr.com/server/decisions>; C4 FAQ: <https://c4model.com/diagrams/faq>;
  docToolchain: <https://doctoolchain.org/docToolchain/v2.0.x/015_tasks/03_tasks.html>
- *Software Engineering at Google*, ch. 10: <https://abseil.io/resources/swe-book/html/ch10.html>
- Martraire, *Living Documentation*: <https://www.informit.com/store/living-documentation-continuous-knowledge-sharing-by-design-9780134689326>
- Kunz and Rittel, IBIS (1970): <https://web.archive.org/web/2020id_/http://magrawal.myweb.usf.edu/phd/articles/ibis_wp_70.pdf>
- Conklin and Begeman, gIBIS (1988): <https://doi.org/10.1145/58566.59297>,
  <http://csis.pace.edu/~marchese/CS835/Readings/p303-conklin_gibis.pdf>;
  Conklin and Burgess Yakemovic (1991): <https://doi.org/10.1207/s15327051hci0603&4_6>
- Grudin (1996): <https://doi.org/10.1201/9781003064053-21>;
  Buckingham Shum et al. (2006): <https://doi.org/10.1007/978-3-540-30998-7_5>,
  <https://web.archive.org/web/2016id_/http://libeprints.open.ac.uk/3032/1/HypermediaSupport.pdf>
- MacLean et al., QOC (1991): <https://doi.org/10.1207/s15327051hci0603&4_2>;
  Lee and Lai (1991): <https://doi.org/10.1207/s15327051hci0603&4_3>;
  Lee (1997): <https://doi.org/10.1109/64.592267>
- Burge dissertation (2005): <https://digitalcommons.wpi.edu/etd-dissertations/244>;
  Burge and Brown, SEURAT (2008): <https://doi.org/10.1145/1368088.1368215>;
  Burge and Brown (2006): <https://doi.org/10.1007/978-3-540-30998-7_13>;
  Horner and Atwood (2006): <https://doi.org/10.1007/978-3-540-30998-7_3>
- Karsenty (1996): <https://doi.org/10.1145/238386.238462>,
  <https://chi1996.acm.org/proceedings/papers/Karsenty/lk_txt.html>
- Shum and Hammond (1994): <https://doi.org/10.1006/ijhc.1994.1029>
- Tang et al. (2006): <https://doi.org/10.1016/j.jss.2006.04.029>, <https://core.ac.uk/download/301360472.pdf>
- Bratthall et al. (2000): <https://doi.org/10.1007/978-3-540-45051-1_14>
- Falessi et al. (2008, 2013): <https://doi.org/10.1109/wicsa.2008.8>, <https://doi.org/10.1145/2491509.2491515>
- Buchgeher et al. (2023): <https://doi.org/10.1109/access.2023.3287654>;
  Capilla et al. (2016): <https://doi.org/10.1016/j.jss.2015.08.054>
- Forward and Lethbridge (2002): <https://doi.org/10.1145/585058.585065>,
  <https://www.site.uottawa.ca/~tcl/gradtheses/aforward/papers/aforwarddoceng2002sub.pdf>,
  <https://www.site.uottawa.ca/~tcl/gradtheses/aforward/papers/aforward_icse2003_sub.pdf>,
  <http://www.site.uottawa.ca/~tcl/gradtheses/aforward/aforward_thesis.doc>;
  Lethbridge et al. (2003): <https://doi.org/10.1109/ms.2003.1241364>
- Aghajani et al. (2019, 2020): <https://doi.org/10.1109/icse.2019.00122>, <https://doi.org/10.1145/3377811.3380405>
- Wen et al. (2019): <https://doi.org/10.1109/icpc.2019.00019>
- Stack Overflow Developer Survey 2024: <https://survey.stackoverflow.co/2024/professional-developers>
- Levesque, Wilson and Wholey (2001): <https://doi.org/10.1002/job.87>

Agent-era living documentation

- Swimm: <https://docs.swimm.io/>, <https://docs.swimm.io/features/keep-docs-updated-with-auto-sync/>,
  <https://docs.swimm.io/continuous-integration/github-app/>,
  <https://swimm.io/blog/docs-as-code-understanding-swimm-sw-md-markdown-format>
- Kiro: <https://kiro.dev/docs/steering/>, <https://kiro.dev/docs/hooks/>,
  <https://kiro.dev/blog/how-i-stopped-worrying-about-readme-files/>,
  <https://github.com/kirodotdev/Kiro/issues/1818>
- Amazon Q Developer: <https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/generate-docs.html>,
  <https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-q-developer-generate-documentation-source-code/>,
  <https://aws.amazon.com/blogs/devops/amazon-q-developer-end-of-support-announcement/>
- DeepWiki: <https://cognition.com/blog/deepwiki>, <https://docs.devin.ai/work-with-devin/deepwiki>;
  Code Wiki: <https://developers.googleblog.com/introducing-code-wiki-accelerating-your-code-understanding/>
- AGENTS.md: <https://agents.md/>; Cursor rules: <https://cursor.com/docs/context/rules>;
  Continue rules: <https://docs.continue.dev/customize/rules>
- RepoAgent: <https://github.com/OpenBMB/RepoAgent>, <https://arxiv.org/abs/2402.16667>
- Mintlify agent: <https://www.mintlify.com/docs/ai/agent>; Komment: <https://www.komment.ai/>
- Claude Code memory and best practices: <https://code.claude.com/docs/en/memory>,
  <https://code.claude.com/docs/en/best-practices>
- ADR skills: <https://gist.github.com/ericclemmons/96cc6c774e2062e6660f1acb97506940>,
  <https://github.com/vercel/ai/blob/main/skills/adr-skill/SKILL.md>,
  <https://github.com/anthropics/knowledge-work-plugins/blob/main/engineering/skills/architecture/SKILL.md>,
  <https://github.com/affaan-m/ECC/blob/main/skills/architecture-decision-records/SKILL.md>,
  <https://github.com/skillrecordings/adr-skill>, <https://github.com/rvdbreemen/adr-kit>
- Böckeler, "Maintainability sensors for coding agents": <https://martinfowler.com/articles/sensors-for-coding-agents.html>

Provenance

- Agent Trace: <https://agent-trace.dev/>, <https://cognition.com/blog/agent-trace>,
  <https://github.com/superhq-dev/agent-trace>, <https://www.infoq.com/news/2026/02/agent-trace-cursor/>
- Cursor Blame: <https://cursor.com/docs/integrations/cursor-blame>
- git-ai: <https://github.com/git-ai-project/git-ai>,
  <https://github.com/git-ai-project/git-ai/blob/main/specs/git_ai_standard_v3.0.0.md>,
  <https://usegitai.com/docs/get-started/ai-blame>
- Entire CLI: <https://github.com/entireio/cli>
- Commit Context: <https://agentsroom.dev/features/commit-context>
- Memento: <https://github.com/mandel-macaque/memento>; Agent Blame: <https://github.com/mesa-dot-dev/agentblame>;
  gitwhy: <https://github.com/mehrtam/gitwhy>; blameprompt: <https://github.com/Ekaanth/blameprompt>;
  ai-blame: <https://github.com/ai4curation/ai-blame>; code-provenance: <https://github.com/QAInsights/code-provenance>;
  cnotes: <https://github.com/imjasonh/cnotes>; AIttributor: <https://github.com/block/aittributor>;
  tempo-cli: <https://github.com/usetempo/tempo-cli>; SpecStory: <https://github.com/specstoryai/getspecstory>
- Transcript renderers: <https://github.com/simonw/claude-code-transcripts>, <https://github.com/es617/claude-replay>,
  <https://simonwillison.net/2025/Dec/25/claude-code-transcripts/>
- Crosley, "Agent sessions are the real commit messages": <https://blakecrosley.com/blog/session-is-the-commit-message>
- Harness retention: <https://code.claude.com/docs/en/data-usage>, <https://code.claude.com/docs/en/claude-directory>,
  <https://code.claude.com/docs/en/commands>, <https://code.claude.com/docs/en/claude-code-on-the-web>,
  <https://github.com/openai/codex>, <https://learn.chatgpt.com/docs/config-file/config-reference>,
  <https://opencode.ai/docs/share/>, <https://opencode.ai/docs/troubleshooting/>,
  <https://cursor.com/help/ai-features/shared-transcripts>, <https://ampcode.com/docs/threads>,
  <https://ampcode.com/news/end-of-public-threads>, <https://docs.warp.dev/agents/local-agents/session-sharing/>
- Forge attribution: <https://docs.github.com/en/pull-requests/committing-changes-to-your-project/creating-and-editing-commits/creating-a-commit-with-multiple-authors>,
  <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/track-copilot-sessions>,
  <https://docs.gitlab.com/user/duo_agent_platform/composite_identity/>,
  <https://jules.google/docs/changelog/>, <https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md>
- Papers: <https://arxiv.org/abs/2601.18341>, <https://arxiv.org/abs/2509.14745>, <https://arxiv.org/abs/2606.22711>

Dialog as artifact

- Knuth (1984): <https://doi.org/10.1093/comjnl/27.2.97>,
  <https://www.cs.tufts.edu/~nr/cs257/archive/literate-programming/01-knuth-lp.pdf>;
  Knuth interview (2008): <http://www.informit.com/articles/printerfriendly.aspx?p=1193856>
- Jupyter: <https://blog.jupyter.org/project-jupyter-computational-narratives-as-the-engine-of-collaborative-data-science-2b5fb94c3c58>,
  <https://doi.org/10.1109/MCSE.2021.3059263>
- nbdev: <https://nbdev.fast.ai/>, <https://nbdev.fast.ai/explanations/directives.html>
- Literate CoffeeScript: <https://coffeescript.org/#literate>; Org Babel: <https://orgmode.org/worg/org-contrib/babel/intro.html>
- LP evaluations: <https://doi.org/10.1145/191029.191059>, <https://doi.org/10.5555/1035053.1035054>,
  <https://doi.org/10.1145/3544548.3581525>
- Litt (2026): <https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck>
- Editable dialogs: <https://raw.githubusercontent.com/zed-industries/zed/main/docs/src/ai/text-threads.md>,
  <https://github.com/karthink/gptel>, <https://github.com/rksm/org-ai>,
  <https://jupyter-ai.readthedocs.io/en/latest/users/index.html>, <https://cursor.com/docs/agent/plan-mode>
- Transcript research: <https://arxiv.org/abs/2309.03914>, <https://arxiv.org/abs/2403.10468>,
  <https://arxiv.org/abs/2505.03901>, <https://arxiv.org/abs/2607.09900>, <https://arxiv.org/abs/2607.02333>

Shared spaces and vocabulary

- Notion: <https://www.notion.com/releases/2026-07-01>, <https://www.notion.com/help/use-claude-agents-in-notion>,
  <https://www.notion.com/help/connect-cursor-to-notion>,
  <https://www.notion.com/help/guides/how-to-set-up-claude-agents-on-your-teams-notion-task-board>
- Amp Multiplayer: <https://ampcode.com/news/multiplayer>,
  <https://ampcode.com/docs/enterprise/workspace-thread-visibility-controls>
- Linear agents: <https://linear.app/developers/agents>
- Devin: <https://docs.devin.ai/integrations/slack.md>, <https://docs.devin.ai/product-guides/session-insights.md>
- Warp cloud conversations: <https://docs.warp.dev/agents/local-agents/cloud-conversations/>
- Cucumber BDD: <https://cucumber.io/docs/bdd/>; Contextive: <https://github.com/dev-cycles/contextive>,
  <https://docs.contextive.tech/>
- Naur reprint: <https://pages.cs.wisc.edu/~remzi/Naur.pdf>
