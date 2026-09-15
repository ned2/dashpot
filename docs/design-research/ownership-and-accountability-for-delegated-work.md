---
status: research
date: 2026-09-15
---

# Ownership and accountability for delegated work

Research date: 2026-09-15

This note documents what the literature and the published rules say about three questions
the agent-delegation material leaves implicit: who is accountable for a change an agent
wrote, what code-ownership models exist and what evidence connects ownership to quality, and
what contribution policies, forges, and licence instruments say about delegated authorship.
It is documentary: it records what each source states, with its evidence type and limits, and
maps each finding to where the existing notes in this directory touch it. It does not
evaluate fit for Dashpot or any tool. Terminal citations are primary — the paper, the
author's copy, the policy file in the project's own tree, the vendor's own terms page — and
every figure is reported as the source states it. Items read only as abstract or metadata are
marked; anything recalled rather than read is marked unverified. Where an earlier note
already covers a source, this note links to it rather than repeating it: the knowledge side of
ownership (Bird 2011 and Greiler 2015 as footprint metrics, truck factor, Mockus succession)
is in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss),
the same metrics as telemetry proxies in
[track-measurement.md](track-measurement.md#proxies-and-telemetry), the `Co-authored-by`
mechanics and GitLab composite identity in
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#forge-level-attribution),
the Ghostty, CloudNativePG, Mastodon and BeeWare comprehension clauses in
[track-hand-off-checks.md](track-hand-off-checks.md#policy-texts), the capacity side of the
kernel's `Assisted-by:` history and the Gentoo, NetBSD and QEMU bans in
[review-capacity-and-volume.md](review-capacity-and-volume.md#attribution-and-procedure-the-linux-kernel)
and [review-capacity-and-volume.md](review-capacity-and-volume.md#bans-gentoo-netbsd-qemu),
and the Linear "assignee remains responsible" clause in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#2-attach-sessions-to-the-teams-existing-work-graph).
This note takes the accountability side: who signs, what the signature certifies, and what
the measurements of ownership say.

## Finding

Every policy, forge rule, and vendor term read for this note places accountability for an
agent-written change on a named person, and none names the agent or the vendor: the Linux
kernel's `coding-assistants.rst` states "AI agents MUST NOT add Signed-off-by tags. Only humans
can legally certify the Developer Certificate of Origin (DCO)" and lists the human submitter as
responsible for "Reviewing all AI-generated code", licensing compliance, "Adding their own
Signed-off-by tag", and "Taking full responsibility for the contribution"
([coding-assistants.rst](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-assistants.rst),
full text, policy text); Hora, Robbes and Zacchiroli's census of 281 AI contribution policies
finds 122 (43.4%) assign accountability to the human contributor, 159 (56.6%) say nothing, and
"none of the analyzed AI policies explicitly state that accountability is not required"
([arXiv:2609.07542](https://arxiv.org/html/2609.07542), full text, measured); GitHub's own
agent is the one case where the agent is the commit author, and the forge compensates by
marking the initiating human as co-author and by ruling that "your approval of a Copilot pull
request won't count toward the required number. Another reviewer must approve"
([Copilot review docs](https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/review-copilot-output),
full text, policy text); vendor terms assign Output to the customer and make review the
customer's duty in near-identical words — Anthropic's "It is Customer's responsibility to
evaluate whether Outputs are appropriate for Customer's use case, including where human review
is appropriate" ([Commercial Terms D.3](https://www.anthropic.com/legal/commercial-terms), full
text), OpenAI's "Customer is solely responsible for all use of the Outputs and for evaluating
the accuracy and appropriateness"
([Services Agreement 4.3](https://openai.com/policies/services-agreement/), full text via
Wayback), GitHub's "You are responsible for reviewing, testing, and validating any Output
before use"
([Terms of Service J.4](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service),
full text) — while the licence-side instruments diverge on whether a person *can* certify
agent output at all: the ASF says AI output "can be contributed" under three conditions and a
`Generated-by:` token ([ASF guidance](https://www.apache.org/legal/generative-tooling.html),
full text), the Linux Foundation says to treat it "no differently"
([LF guidance](https://www.linuxfoundation.org/legal/generative-ai), full text), QEMU declines
it because "How contributors could comply with DCO terms (b) or (c) for the output of AI
content generators commonly available today is unclear"
([code-provenance.rst](https://gitlab.com/qemu-project/qemu/-/raw/master/docs/devel/code-provenance.rst),
full text), and OpenTTD holds that "you cannot truly release code for use if you didn't author
it yourself"
([CONTRIBUTING.md](https://github.com/OpenTTD/OpenTTD/blob/master/CONTRIBUTING.md#use-of-ai),
full text). The pre-AI ownership–quality evidence is a strong industrial result with weak open
source replication: Bird et al. found the proportion of minor contributors correlated with
pre- and post-release defects in Windows Vista and 7 more than "any other metric that
Microsoft collects", with models explaining "up to 72% of variance in failures"
([TSE/FSE 2011 PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf),
full text, measured); Greiler et al. found weakly owned files in Office "on average 6 times
more bugs" with file-level correlations averaging 0.39 and directory-level 0.57
([MSR 2015 PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2015/05/MSR-2015-Source-Code-Ownership-IEEE_camera-ready.pdf),
full text, measured); Foucault et al. found in seven Java FLOSS projects that "the relationship
between ownership metrics and module faults is weak"
([EASE 2014 PDF](https://scholar.archive.org/work/veyzrlolbvggdolb2rcu5umc2u/access/wayback/https://hal.archives-ouvertes.fr/hal-00976024/document),
full text, measured) and in the IST 2015 follow-up that the metrics' "relative importance ...
in multiple linear regression models is low"
([IST 2015](https://ink.library.smu.edu.sg/sis_research/2848), abstract); Thongtanunam et al.
showed that 67%–86% of developers who never authored a module reviewed 21%–39% of its changes
and that modules with minor authors who are also minor reviewers are the defect-prone ones
(AUC 0.81–0.87)
([ICSE 2016 PDF](https://rebels.cs.uwaterloo.ca/papers/icse2016_thongtanunam.pdf), full text,
measured). Under AI authorship, two measurements exist: Seo, Deldari and Mentis's
within-subjects study across three autonomy levels found possession "decreased continuously",
identity fell only under high autonomy, and responsibility decreased from low to medium or
high autonomy "though developers maintained some sense of responsibility", while "willingness
to ... accept accountability for production systems remained consistent"
([IUI 2026, doi:10.1145/3742413.3789121](https://dl.acm.org/doi/10.1145/3742413.3789121),
abstract via OpenAlex; 30 participants per Camargo's secondary report, measured); Rahman and
Shihab's survival analysis of 5,171 Pull Requests in 201 repositories found agent-written code
units 15.8 percentage points less likely to be modified and a hazard ratio of 0.842 for later
modification, which they attribute to an "ownership hypothesis" that "agent-generated code
lacks a clear human owner" and state "remains untested"
([arXiv:2601.16809](https://arxiv.org/html/2601.16809), full text, measured with argued
interpretation). Nissenbaum's four barriers to accountability — "the problem of many hands",
"the problem of bugs", "blaming the computer", and "software ownership without liability" —
were stated in 1996 for conventional software and are the vocabulary the 2026 policies restate
without citing ([Nissenbaum 1996](https://nissenbaum.tech.cornell.edu/papers/accountability.pdf),
full text, argument).

## Ownership models before AI

### Strong, weak, collective: the named models

Fowler's bliki entry (2006-05-12) sets out the three-term vocabulary most later sources use:
"strong code ownership", which "assigns each module to one developer" and where "Developers
are only allowed to make changes to modules they own"; "weak code ownership", where
"developers are allowed to change modules owned by other people" while "Module owners are
expected to take responsibility for the modules they own and keep an eye on changes made by
other people"; and "collective code ownership", from Extreme Programming, where anyone may
change anything. He writes that "Of the three the one I really don't like is strong code
ownership" and that "in the second edition the practice is called Shared Code"
([martinfowler.com/bliki/CodeOwnership.html](https://martinfowler.com/bliki/CodeOwnership.html),
full text, argument).

Nordberg, "Managing Code Ownership", *IEEE Software* 20(2):26–33, March 2003, describes four
models along a scale from one individual owning the whole system to collective ownership, and
argues that "No single code ownership model is best" and that the model should be adjusted
over the phases of a unified-process project
([doi:10.1109/MS.2003.1184163](https://doi.org/10.1109/MS.2003.1184163), abstract via OpenAlex;
45 citations recorded there; argument). Greiler et al. (below) summarise Nordberg's
distinction between "collaborative ownership" and "non-ownership" (secondary).

Beck's first edition (2000) states the collective model as an obligation, not a permission:
"Anybody who sees an opportunity to add value to any portion of the code is required to do so
at any time." He contrasts it with no ownership and with individual ownership, where the module
"doesn't evolve as quickly as it should. Then the owner leaves ....", and adds "In XP, everybody
takes responsibility for the whole of the system. Not everyone knows every part equally well,
although everyone knows something about every part." The rationale in the practices chapter is
knowledge spread: "It is unlikely that there will ever be a part of the system that only two
people know (it has to be at least a pair, which is already better)"
([archive.org item kentBeck2000](https://archive.org/details/kentBeck2000), OCR full text,
argument). Wells's rules page restates the practice as "Collective Ownership encourages everyone
to contribute new ideas to all segments of the project"
([extremeprogramming.org](http://www.extremeprogramming.org/rules/collective.html), full text,
argument). Neither source measures anything.

### Ownership as a review right: Google's OWNERS and GitHub's CODEOWNERS

*Software Engineering at Google*, chapter 9 (Sadowski, Winter, Wright), separates three
approvals a change needs — a correctness LGTM, an approval from someone with ownership of the
code, and a readability approval — and notes that most reviews at Google are done by one
reviewer holding all three. The ownership sidebar (Hyrum Wright) defines ownership as "a set of
knowledge and responsibilities" tied to a directory: OWNERS files are hierarchical, kept as "a
relatively small and focused list to ensure responsibility is clear", and ownership "conveys
approval rights" along with "responsibilities, such as understanding the code that is owned or
knowing how to find somebody who does"; members who leave a team yield ownership. Wright writes
that "'stewards' would almost certainly be a better term". The chapter's "Psychological and
Cultural Benefits" section states that review reinforces that code is "not 'theirs' but in
fact part of a collective enterprise"
([abseil.io ch. 9](https://abseil.io/resources/swe-book/html/ch09.html), full text,
testimonial).

GitHub's CODEOWNERS "define individuals or teams that are responsible for code in a
repository"; owners are "automatically requested for review when someone opens a pull request
that modifies code that they own"; repository administrators may require code-owner approval
before merge; owners must have write permission
([about-code-owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners),
full text, policy text). The mechanism is a glob-to-handle map with no notion of authorship: a
code owner need never have written the file. [track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure)
records the same page as an estimator with "no estimation, no decay".

### Ownership as a tracker field: Linear

Linear's documentation states "Issues in Linear are assigned to a single person at a time,
giving teams clear ownership and responsibility", and, for delegation: "Delegate an issue to an
agent while keeping a human teammate as the assignee. The assignee remains responsible for the
work, while the agent contributes on their behalf"
([linear.app/docs/assigning-issues](https://linear.app/docs/assigning-issues), full text,
policy text). This is the only tracker documentation found that names *who* remains
responsible when an Issue is delegated to an agent; the corpus discusses it in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#2-attach-sessions-to-the-teams-existing-work-graph).

## Ownership and quality: what was measured

The knowledge framing of these studies (footprint, succession, loss) is in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss);
this section records the accountability framing and the replication results, which that note
does not cover.

### Bird, Nagappan, Murphy, Gall, Devanbu 2011

"Don't Touch My Code!" defines Minor (contributors below 5% of a binary's commits), Major,
Total, and Ownership (the top contributor's proportion) and relates them to pre- and
post-release failures of Windows Vista and Windows 7 binaries. Minor "had a higher correlation
with both pre- and post-release defects in Vista and pre-release defects in Windows 7 than any
other metric that Microsoft collects!"; models including ownership metrics "account for up to
72% of variance in failures". The authors test one explanation for minor contributors: in the
observed Vista contribution graph, "52% of the binaries had minor contributors who were major
contributors to other binaries that the original had a dependency with", against an average of
24% in random graphs with the same degree distributions (maximum 32% over 10,000 graphs). The
paper states its scope condition — "Microsoft employs strong ownership practices and our
results are much more likely to hold in other industrial settings where the same is true" — and
closes with three recommendations: changes by minor contributors should be reviewed with extra
scrutiny by major contributors; developers needing a change in a component they rarely touch
should communicate it to an experienced developer; and QA should give priority to low-ownership
components. "These recommendations are currently being evaluated at Microsoft"
([bird2011dtm.pdf](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf),
full text read via Wayback `2025id_`; measured, with the recommendations as argument).
Rahman and Shihab (below) cite this paper for developers being "reluctant to modify code they
did not author"; the paper measures defect correlation, not reluctance to modify.

### Greiler, Herzig, Czerwonka 2015

The Microsoft replication covers Office, Office365, Exchange, and Windows, moves the ownership
threshold to 50%, adds the directory level, and interviews six Office engineers and three from
other groups. "Weakly owed [sic] files have on average 6 times more bugs assigned as files that
have a strong owner"; 90% of directories contain no weakly owned files; correlation values "on
file level are on average 0.39 and 0.57 on directory level" (p < 0.01). The interviews distinguish
intentional from unintentional weak ownership and yield three organisational groups —
individual ownership, collective ownership, and non-ownership, the last marked by "lack of
accountability and responsibility". The paper reports that "In Office, strong ownership of code
is discouraged" and lists the recommendations: do not enforce strong ownership without
understanding its impact, because "strong ownership prohibits knowledge transfer" and
"accountability can be unclear"; review weakly owned files; assign an owner who is "aware of
changes ... via code reviewing". It cites LaToza et al. 2006 for the finding that 72% of
Microsoft developers reported personal code ownership and 92% team ownership (secondary; the
LaToza PDF was unreachable)
([MSR 2015 PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2015/05/MSR-2015-Source-Code-Ownership-IEEE_camera-ready.pdf),
full text via Wayback; measured and qualitative).

### Rahman and Devanbu 2011: line-level authorship

"Ownership, Experience and Defects" uses `git blame` on lines implicated in fixes in Apache
Httpd, Evolution, Gimp, and Nautilus (C, 200k–1M LOC) and finds "implicated code is more
strongly associated with a single developer's contribution" and that specialised experience in
a file matters more than general experience. The introduction states the accountability
motive directly: "code ownership makes it easier for managers to hold the right people
accountable"
([archived PDF](https://web.archive.org/web/20160208035713id_/http://www.inf.usi.ch:80/faculty/lanza/Education/SDE-2011/papers/Rahm2011a.pdf),
full text, measured). [track-measurement.md](track-measurement.md#proxies-and-telemetry)
already quotes its main result.

### Foucault et al. 2014 and 2015: the open-source replications

Foucault, Falleri, and Blanc replicate Bird's metrics on seven Java FLOSS projects from the
PROMISE and D'Ambros corpora, post-release faults only, and report that "the relationship
between ownership metrics and module faults is weak. At best, less than half of projects exhibit
a significant correlation, and at worst, no projects at all"; module size matters more, and
the projects show "heroes" who author most code
([EASE 2014 PDF](https://scholar.archive.org/work/veyzrlolbvggdolb2rcu5umc2u/access/wayback/https://hal.archives-ouvertes.fr/hal-00976024/document),
full text, measured). The journal extension, Foucault, Teyton, Lo, Blanc, Falleri, "Impact of
developer turnover and code ownership on software quality", *Information and Software
Technology* 64:102–112 (2015), "confirm[s] the existence of a relationship between ownership
metrics and module faults, but the relative importance of ownership metrics in multiple linear
regression models is low" against lines of code, number of modifications, and number of
developers ([IST 2015, doi:10.1016/j.infsof.2015.01.013](https://ink.library.smu.edu.sg/sis_research/2848),
abstract from the SMU repository landing page; the PDF route returned HTML; measured).
[track-measurement.md](track-measurement.md#proxies-and-telemetry) quotes the 2014 sentence;
the 2015 restatement is not in the corpus.

### Thongtanunam, McIntosh, Hassan, Iida 2016: review-aware ownership

"Revisiting Code Ownership and its Relationship with Software Quality in the Scope of Modern
Code Review" opens with the accountability claim — "Code ownership establishes a chain of
responsibility for modules in large software systems" — and shows that authorship-only
heuristics miss most of the people in that chain. Across six releases of Qt and OpenStack,
"67%-86% of developers did not author any code changes for a module, but still actively
contributed by reviewing 21%-39% of the code changes"; "13%-58% of developers who are flagged
as minor contributors of a module by traditional code ownership heuristics are actually major
contributors" once review is counted; and the proportion of developers who are minor as both
author and reviewer "shares a strong, increasing relationship with the likelihood of having
post-release defects" (models with AUC 0.81–0.87). The paper's suggestions: include review
activity when estimating ownership, and apply extra scrutiny to contributions from people with
neither authorship nor review history in a module
([ICSE 2016 PDF](https://rebels.cs.uwaterloo.ca/papers/icse2016_thongtanunam.pdf), full text,
measured). This is the closest pre-AI analogue to the agent case, where the reviewer, not the
author, is the accountable party.

### What the pre-AI evidence does and does not say

Read together: ownership metrics predicted defects strongly in one company with strong
ownership practices (Bird; Greiler), weakly or not at all in FLOSS (Foucault 2014, 2015), and
partly because authorship undercounts review (Thongtanunam). No study in this set measured a
developer's *feeling* of ownership; Greiler's interviews and the LaToza survey it cites are
the only self-report elements, and the "accountability" language in Bird, Rahman, Greiler, and
Thongtanunam is motivation or interpretation, not a measured variable.

## Who signs: the DCO and the kernel's rule

### What a sign-off certifies

The Developer Certificate of Origin 1.1 is a first-person certification with three alternative
grounds and one condition: "(a) The contribution was created in whole or in part by me and I
have the right to submit it under the open source license indicated in the file; or (b) The
contribution is based upon previous work that, to the best of my knowledge, is covered under an
appropriate open source license and I have the right under that license to submit that work
with modifications ...; or (c) The contribution was provided directly to me by some other
person who certified (a), (b) or (c) and I have not modified it", plus "(d) I understand and
agree that this project and the contribution are public and that a record of the contribution
(including all personal information I submit with it, including my sign-off) is maintained
indefinitely" ([developercertificate.org](https://developercertificate.org/), full text, policy
text). Clause (c) names "some other person"; the text has no clause for a tool.

The kernel's `submitting-patches.rst` explains the trailer: the sign-off "certifies that you
wrote it or otherwise have the right to pass it on as an open-source patch"; "no anonymous
contributions"; sign-off chains "should reflect the **real** route a patch took"; and
"Co-developed-by: denotes authorship ... every Co-developed-by: must be immediately followed by
a Signed-off-by: of the associated co-author", with the submitter's sign-off last. `Acked-by:`
is for "those responsible for or involved with the affected code"
([submitting-patches.rst](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/submitting-patches.rst),
full text, policy text). Under this text an agent cannot be a `Co-developed-by:` because it
cannot supply the sign-off that trailer requires.

### The kernel's assistant rule

`Documentation/process/coding-assistants.rst` states the rule quoted in the Finding and the
four duties of the human submitter. Its attribution trailer is `Assisted-by: LLM [TOOL1]
[TOOL2]` (example: `Assisted-by: LLM coccinelle sparse`). Its bug-finding procedure includes
step 6, "Do not add a Signed-off-by tag", and step 9, "the assistant must never send anything
itself"
([coding-assistants.rst](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-assistants.rst),
full text, policy text). History from the GitHub commits API on the file's path: added by Sasha
Levin in 78d979db6cef (2025-12-23) "per the consensus reached at the 2025 Maintainers Summit",
with a `Link:` to LWN 1049830; reduced by Christian Brauner in 816d9992d9ed (2026-07-01);
cross-linked by Lorenzo Stoakes in d699a5da1039 (2026-07-02); the bug procedure added by Willy
Tarreau in 3d7c44f73765 (2026-08-02) and merged in 72fdff1416e2 (2026-08-20)
([api.github.com commits](https://api.github.com/repos/torvalds/linux/commits?path=Documentation/process/coding-assistants.rst),
metadata). The capacity side of the same history is in
[review-capacity-and-volume.md](review-capacity-and-volume.md#attribution-and-procedure-the-linux-kernel).

The companion `generated-content.rst` (Dave Hansen, a66437c27979, 2026-01-19) states it sets
"no new or unique rules" and applies when "a meaningful amount of content ... was not written
by a person in the Signed-off-by chain, but was instead created by a tool". Its contributor
clause: "Ensure that you understand your entire submission and are prepared to respond to
review comments"; "You are expected to understand and to be able to defend everything you
submit. If you are unable to do so, then do not submit"; and "expect additional scrutiny in
proportion to how much of it was generated". Its maintainer clause lists discretionary
responses — reject outright, apply extra scrutiny, lower priority, ask the submitter to explain
so the maintainer is assured they "fully understand how the code works", or suggest a better
prompt
([generated-content.rst](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/generated-content.rst),
full text, policy text).

Corbet's Maintainers Summit report records the reasoning behind the sign-off rule: Greg
Kroah-Hartman said the DCO "should cover the legal side"; Steven Rostedt that "the submitter is
ultimately on the hook for the code they contribute"; Ted Ts'o that the same problems exist
without tools ([LWN 1049830](https://lwn.net/Articles/1049830/), 2025-12-11, full text,
testimonial).

### Derivative policies that copy the sign-off logic

Several project policies restate the kernel's allocation. GraalVM's `CODING_ASSISTANTS.md`
states "The human contributor submitting a change remains responsible for the entire
contribution, including any AI-assisted portion", lists four expectations (review and
understand; verify; "address reviewer questions and follow-up changes without deferring
responsibility to a tool"; "stand behind the contribution during review and maintenance"),
makes attribution to a model or tool "optional", and states the Oracle Contributor Agreement
applies "whether AI-assisted or not"
([oracle/graal](https://raw.githubusercontent.com/oracle/graal/master/CODING_ASSISTANTS.md),
full text, policy text). Cilium's `AI-POLICY.md` states "you are fully accountable for the
correctness, security, and clarity" of a contribution, asks contributors to "Take personal
responsibility ... in the same way as if you authored the content without using Generative
AI", grounds this in the DCO — signing off is "personally certifying" — links the Linux
Foundation guidance, and adds an "AI Influence Level" disclosure
([cilium/community](https://raw.githubusercontent.com/cilium/community/main/AI-POLICY.md),
full text, policy text). Mesa's submission guide adds `Assisted-by: TOOL (OPTIONAL: MODEL)` and
`Generated-by:` trailers and states "Do not use the Co-authored-by tag as this one is reserved
for human co-authors" ([docs.mesa3d.org](https://docs.mesa3d.org/submittingpatches.html), full
text, policy text).

## Who signs: forge mechanics and the `Co-authored-by` dispute

### GitHub's agent as commit author

GitHub's responsible-use page for Copilot agents states "You are responsible for reviewing and
validating responses generated by Copilot cloud agent" and, for the CLI, "You are ultimately
responsible for the commands executed". Under "Ensuring traceability": "The cloud agent's
commits are authored by Copilot, with the human who started the task marked as the co-author.
This makes it easier to identify code generated by the agent and who initiated the task. The
cloud agent's commits are signed"; each commit message links to the agent session logs.
Structural limits: the agent "only responds to interactions from users with repository write
access"; Actions workflows on its Pull Requests "require approval from a user with write access
before they will run"; it pushes only to the existing PR branch or a new `copilot/` branch
([responsible-use/agents](https://docs.github.com/en/copilot/responsible-use/agents), full
text, policy text). The concept page adds that repository rulesets restricting commit authors
block Copilot unless it is added as a bypass actor, that a session is limited to 59 minutes,
and that each task yields one Pull Request
([about-cloud-agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent),
full text, policy text). The review page states the approval rule quoted in the Finding and
"Copilot pull requests deserve the same thorough review as any contribution"
([review-copilot-output](https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/review-copilot-output),
full text, policy text).

The allocation here is the inverse of the kernel's: the agent is the author of record and the
person is the co-author, and accountability is reconstructed by (i) recording who initiated
the Agent Session, (ii) discounting that person's approval, and (iii) requiring a second
write-access human. No GitHub page read states who is accountable for a merged Copilot PR
beyond the Terms of Service clause in the next section.

### Claude Code's default trailer

Claude Code's settings reference documents `attribution.commit`, whose default is
`Co-Authored-By: <name> <noreply@anthropic.com>` where the name is the active model (for
example "Claude Sonnet 5"), falling back to "Claude" or "Claude Code"; `attribution.pr`
defaults to "🤖 Generated with [Claude Code](https://claude.com/claude-code)";
`attribution.sessionUrl` can add a session link; the older `includeCoAuthoredBy` is deprecated
since v2.0.62
([settings-reference](https://code.claude.com/docs/en/settings-reference.md), full text,
policy text). The commit author remains the person's git identity; the model appears as a
`Co-Authored-By:` trailer. This is the default that several policies below reject.

### Projects that forbid the trailer

attrs and pip publish the same `AI_POLICY.md` text: "Every contribution has to be backed by a
human who unequivocally owns the copyright"; the contributor certifies authorship, copyright,
understanding, and "full technical and legal responsibility"; "No LLM bots in
`Co-authored-by:`s"; Pull Requests with an LLM co-author are closed
([python-attrs/attrs](https://raw.githubusercontent.com/python-attrs/attrs/main/.github/AI_POLICY.md),
[pypa/pip](https://raw.githubusercontent.com/pypa/pip/main/AI_POLICY.md), full text, policy
text). LinkML's `AI_COVENANT.md` states "You Own Your Contributions ... you are the author" and
that "AI co-authorship in commit messages ... [is] actively discouraged"
([linkml/linkml](https://raw.githubusercontent.com/linkml/linkml/main/AI_COVENANT.md), full
text, policy text). Mesa reserves the trailer for humans (above). Hora et al. record the same
split from the other side: "some requiring a Git commit message trailer such as Assisted-by
while others explicitly forbid the Co-authored-by trailer that some coding agents emit by
default" ([arXiv:2609.07542](https://arxiv.org/html/2609.07542), full text).

pytest's `CONTRIBUTING.rst` takes the opposite position on the trailer while keeping the same
allocation of responsibility: "You are responsible for your contribution"; "If you submit it,
you own it"; "Purely agentic contributions are not accepted"; and contributors may "consider
adding `Co-authored-by` trailers to your commit messages to credit them. This is not required"
([pytest-dev/pytest](https://raw.githubusercontent.com/pytest-dev/pytest/main/CONTRIBUTING.rst),
full text, policy text). The melissawm index of policies lists IREE as accepting either
`Assisted-by:` or `Co-authored-by:`
([open-source-ai-contribution-policies](https://github.com/melissawm/open-source-ai-contribution-policies),
secondary index).

Mastodon's `AI_POLICY.md`, beyond the comprehension clause quoted in
[track-hand-off-checks.md](track-hand-off-checks.md#policy-texts), states "The human
contributor is the sole party responsible for the contribution", forbids autonomous agents from
submitting Pull Requests, specifies `Assisted-by: Name of AI`, and includes copyright warranties
([mastodon/.github](https://raw.githubusercontent.com/mastodon/.github/main/AI_POLICY.md), full
text, policy text). Ghostty's policy states "the human-in-the-loop must fully understand all
code" and exempts maintainers
([ghostty-org/ghostty](https://raw.githubusercontent.com/ghostty-org/ghostty/main/AI_POLICY.md),
full text, policy text). Hora et al. quote Mastodon's and GraalVM's clauses as their
accountability examples and, among 31 explained policy commits, code five under "Enforcing
Human Accountability", with messages including "discourage adding AI agents as commit
authors", "add policy for sign-offs", "make human communication mandatory", and "agent policy:
mention human-reply-to-human rule" ([arXiv:2609.07542](https://arxiv.org/html/2609.07542), full
text, measured). Their enforcement coding is in
[track-hand-off-checks.md](track-hand-off-checks.md#how-hora-et-al-report-enforcement).

### What "co-author" means to the forge

GitHub counts a `Co-authored-by:` trailer as a contribution for the named account, GitLab's
composite identity attributes an agent's merge request to the human who triggered it, and
git-ai keeps a separate trace; these are recorded in
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#forge-level-attribution) and
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#git-ai-and-the-tools-that-keep-the-trace-in-git)
and are not repeated here.

## Licences, CLAs, and whether a person can certify agent output

### Instruments that say yes, with conditions

The ASF's Generative Tooling Guidance reads the ICLA clause by clause. Section 5's
representation that each contribution is "your original creation" still applies; section 7
(submitting work that is not your own) "asks for the complete details of the work's source",
which "are generally not knowable" for AI output, so "Section 7 is not a practical route";
section 4's "legally entitled to grant the above license" "depends on what the tool's terms
grant as well as what they restrict"; section 8 obliges the contributor to notify the
Foundation if a representation later proves inaccurate. AI output "can be contributed if the
contributor ensures that" the tool's terms are compatible with the Open Source Definition and
at least one of three conditions holds: 2.1 the output is not copyrightable subject matter,
2.2 no third-party material is included, or 2.3 any included third-party material is used with
permission. The page cites the U.S. Copyright Office's January 2025 Part 2 report — "purely
AI-generated output is not copyrightable, but works where a human has creatively selected,
arranged or modified AI-generated material may be" — recommends a `Generated-by:` token in the
commit message, and dates itself "August 2026"
([apache.org/legal/generative-tooling](https://www.apache.org/legal/generative-tooling.html),
full text, policy text). Its EU AI Act paragraph is discussed under regulation below.

The Linux Foundation's guidance states AI-generated output "can be contributed", that projects
should treat such contributions "no differently" from others, that the contributor confirms the
tool's terms permit the contribution and that any third-party material is identified, and that
projects may add their own guidance
([linuxfoundation.org/legal/generative-ai](https://www.linuxfoundation.org/legal/generative-ai),
full text, policy text).

### Instruments that say no, and why

QEMU's `code-provenance.rst` declines contributions "believed to include or derive from AI
generated content", on DCO grounds: "To satisfy the DCO, the patch contributor has to fully
understand the copyright and license status of content they are contributing"; the output's
status "is ill-defined with no generally accepted, settled legal foundation"; and "How
contributors could comply with DCO terms (b) or (c) for the output of AI content generators
commonly available today is unclear". An exceptions process exists; none is listed
([code-provenance.rst](https://gitlab.com/qemu-project/qemu/-/raw/master/docs/devel/code-provenance.rst),
full text, policy text). NetBSD's commit guidelines open with "Commit only code you are
familiar with" and state that LLM-generated code "is presumed to be tainted code, and must not
be committed without prior written approval by core"
([netbsd.org commit-guidelines](https://www.netbsd.org/developers/commit-guidelines.html), full
text, policy text). Gentoo's council policy (voted 2024-04-14) forbids NLP-AI-assisted content;
its first rationale is copyright — the tools "weaken Gentoo claims to copyright and void the
guarantees given by copyleft" — alongside the quality and ethical rationales
([wiki.gentoo.org](https://wiki.gentoo.org/wiki/Project:Council/AI_policy), full text, policy
text; the capacity rationale is quoted in
[review-capacity-and-volume.md](review-capacity-and-volume.md#bans-gentoo-netbsd-qemu)).
OpenTTD's `CONTRIBUTING.md` gives a licence rationale — "AI-generated code conflicts with this
project's license (GPL v2), since you cannot truly release code for use if you didn't author it
yourself" — and a learning one: "Nobody learns anything when a maintainer reviews code written
by an LLM"
([OpenTTD CONTRIBUTING.md](https://github.com/OpenTTD/OpenTTD/blob/master/CONTRIBUTING.md#use-of-ai),
full text, policy text).

The disagreement between these two groups is not about who is accountable — every text places
it on the submitter — but about whether the submitter's certification can be true. The ASF and
LF texts treat the DCO/CLA representations as satisfiable with diligence; QEMU, NetBSD, Gentoo
and OpenTTD treat them as unsatisfiable or presumptively false for tool output.

### Vendor terms: Output belongs to the customer, and so does review

Anthropic's Consumer Terms (effective 2025-10-08) state "You are responsible for all Inputs you
submit to our Services and all Actions", assign Outputs to the user, and add "You should not
rely on any Outputs or Actions without independently confirming their accuracy"
([consumer-terms](https://www.anthropic.com/legal/consumer-terms), full text, policy text).
The Commercial Terms (effective 2025-06-17) assign Outputs to the Customer; D.3 states "It is
Customer's responsibility to evaluate whether Outputs are appropriate for Customer's use case,
including where human review is appropriate, before using or sharing Outputs"; K.1 has
Anthropic defend intellectual-property claims arising from paid use of Outputs, with K.3
exclusions for modifications and combinations
([commercial-terms](https://www.anthropic.com/legal/commercial-terms), full text, policy text).

OpenAI's Terms of Use (effective 2026-01-01) state "You are responsible for Content", assign
Output to the user, and require that "You must evaluate Output for accuracy and appropriateness
for your use case, including using human review as appropriate, before using or sharing
Output" ([row-terms-of-use](https://openai.com/policies/row-terms-of-use/), full text via
Wayback; openai.com returned 403 directly). The Services Agreement (updated 2025-12-01,
effective 2026-01-01) states in 4.1 that Customer owns Output and in 4.3 that "Customer is
solely responsible for all use of the Outputs and for evaluating the accuracy and
appropriateness" ([services-agreement](https://openai.com/policies/services-agreement/), full
text via Wayback, policy text).

GitHub's Copilot Product Specific Terms (version October 2024, read via Wayback) state in §2
"GitHub does not own Suggestions. You retain ownership of Your Code" and in §3 "You retain all
responsibility for Your Code, including Suggestions you include"; the page is marked
"deprecated effective 5 March 2026" and superseded by the GitHub Generative AI Services Terms
([github-copilot-product-specific-terms](https://github.com/customer-terms/github-copilot-product-specific-terms),
full text via Wayback; the successor page at gh.io/terms returned HTTP 500). The GitHub Terms of
Service (effective 2026-04-27) §J covers AI Features: J.2 "GitHub does not claim ownership of
your Input or Output" and "You are responsible for determining whether your use of Output
requires a third-party license"; J.4 "You are responsible for reviewing, testing, and
validating any Output before use"; J.5 "You are responsible for your use of Output" and the
§Q indemnity applies to "claims arising from Output you incorporate into your products or
services" ([github-terms-of-service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service),
full text, policy text).

Across four vendors the clause structure is the same: the customer owns Output, the customer
reviews Output, and the customer bears the consequences of using it. Anthropic's K.1 is the only
clause read that has the vendor take on a liability, and it is limited to intellectual-property
claims.

## Accountability under AI authorship: measurements and studies, 2025–2026

### Hora, Robbes, Zacchiroli 2026: the policy census

Across 281 policies from the 2,000 most popular GitHub repositories plus 36 well-known
projects: 214 (76.2%) permit generative AI for code contributions and 83.3% permit or encourage
it; 189 (67.3%) require a high level of human involvement; 48.8% require disclosure; 122
(43.4%) assign accountability to the human contributor; 159 (56.6%) give no information on
accountability; none states it is not required. Accountability is coded as required or not
required only "when the AI policy explicitly" says so. Among 92 dedicated policy files (8 created
in 2025, 84 in 2026), 196 commits were analysed and 31 carried rationales, five of them under
"Enforcing Human Accountability"
([arXiv:2609.07542](https://arxiv.org/html/2609.07542), full text, measured; manual
classification). The paper's implication section states "there is no disclosure convention to
target". [landscape-sweep.md](landscape-sweep.md) and
[track-hand-off-checks.md](track-hand-off-checks.md#how-hora-et-al-report-enforcement) record
the paper's other dimensions.

### Seo, Deldari, Mentis 2026: ownership feeling under three autonomy levels

"Whose Code Is It? How AI Autonomy Reshapes Ownership, Responsibility, and Disclosure in
AI-Assisted Programming", *IUI 2026*, pp. 393–425. The OpenAlex abstract describes a
within-subjects design across High, Medium and Low autonomy conditions with measures of
possession, identity and responsibility (the three dimensions of psychological ownership),
attribution, and disclosure. Reported: possession "decreased continuously" as autonomy
increased; identity declined only under High autonomy; responsibility decreased from Low to
Medium or High "though developers maintained some sense of responsibility"; attribution shifted
from human to AI; disclosure practices were stable; and "willingness to ... accept
accountability for production systems remained consistent"
([doi:10.1145/3742413.3789121](https://dl.acm.org/doi/10.1145/3742413.3789121), abstract via
the OpenAlex API; the ACM page returned 403 and its Wayback copy 404; measured). Camargo's
research note reports the sample as "a study with 30 participants" and summarises the result
as "increasing AI contribution reduced perceived possession and shifted attribution toward AI.
Willingness to accept accountability for production systems remained comparatively stable"
([arXiv:2609.09022](https://arxiv.org/html/2609.09022), full text, secondary for Seo et al.).
Whether the participants were professionals, and which scale was used, could not be read.

This is the only measurement found of "ownership feeling" for AI-generated code as a function
of agent autonomy. Its pre-AI frame is psychological ownership theory: Pierce, Kostova and
Dirks define the construct as a state in which individuals feel a target is "theirs" (*AMR*
26(2):298–310, 2001, [doi:10.5465/amr.2001.4378028](https://doi.org/10.5465/amr.2001.4378028),
abstract); Van Dyne and Pierce relate it to attitudes and behaviour across three field samples
of more than 800 employees (*JOB* 25(4):439–459, 2004,
[doi:10.1002/job.249](https://doi.org/10.1002/job.249), abstract); Pierce, Jussila and
Cummings relate it to job design (*JOB* 30(4):477–496, 2008,
[doi:10.1002/job.550](https://doi.org/10.1002/job.550), abstract). Camargo also cites Draxler
et al.'s "AI Ghostwriter Effect" (*ACM TOCHI* 31(2), 2024,
[doi:10.1145/3637875](https://doi.org/10.1145/3637875), secondary), where users "can feel
little ownership of generated text while publicly declaring themselves its authors".

### Rahman and Shihab 2026: the "ownership hypothesis"

"Untouched Code? Agent-Generated Code Survival" (submitted 2026-01-23) follows more than 200,000
code units across 5,171 Pull Requests (3,003 agent-authored, 2,168 human-authored) in 201
repositories. Agent-written units show a 15.8 percentage-point lower modification rate; the
Cox hazard ratio for later modification is 0.842 (p < 0.001); corrective changes are 26.3%
versus 23.0% (Cramér's V 0.116). By tool, Copilot-style assistants (Cursor, Claude Code,
Copilot, Codex) show 20–30 percentage-point lower "death rates", while Devin's code is modified
at 71.7% versus 69.3% for humans. The authors read the gap as an ownership effect —
"agent-generated code lacks a clear human owner" — write that if the hypothesis holds
"organizations should explicitly designate human owners for agent-generated code and document
AI provenance", and state "our ownership hypothesis remains untested"
([arXiv:2601.16809](https://arxiv.org/html/2601.16809), full text, measured; the ownership
reading is argument). The paper cites Bird et al. 2011 for developers being "reluctant to
modify code they did not author, a phenomenon known as 'Don't touch my code!'", which Bird did
not measure (above).

### Interview and survey evidence

Alami, Paja and Tiwari's 21 interviews at one company name "accountability anxiety" as a
response to agentic tools ([arXiv:2609.03456](https://arxiv.org/abs/2609.03456), abstract here;
full text in [adjacent-literatures.md](adjacent-literatures.md#finding), qualitative).
Choudhuri et al.'s 448-developer survey finds accountability lowers the autonomy developers
accept (odds ratio 0.82), and Shukla and Sharma's eleven-interview thesis is the nearest
interview evidence on ownership of agent-written code; both are in
[literature-addendum.md](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026).
A self-declaration study (613 snippets, 111 survey responses) reports 76.6% of respondents
always or sometimes declare AI-generated code
([arXiv:2504.16485](https://arxiv.org/abs/2504.16485), abstract, measured); a registered
report on disclosure practices exists ([arXiv:2607.09434](https://arxiv.org/abs/2607.09434),
abstract). GitLab's "2026 AI Accountability Report" surveyed 1,528 DevSecOps professionals in
six countries; the report itself is gated and only the landing page was read
([about.gitlab.com](https://about.gitlab.com/resources/ai-accountability-survey-2026/),
metadata). No figure from it is cited here.

### Accountability theory the policies restate

Nissenbaum's "Accountability in a Computerized Society" (*Science and Engineering Ethics*
2(1):25–42, 1996) identifies "four barriers" to accountability: "(1) the problem of many hands,
(2) the problem of bugs, (3) blaming the computer, and (4) software ownership without
liability", and proposes an "explicit standard of care" for the computing profession and
strict liability for some harms
([author PDF](https://nissenbaum.tech.cornell.edu/papers/accountability.pdf), full text,
argument). The 2026 policy texts above address barrier (3) by name — the kernel's "Only humans
can legally certify", Mastodon's "'The AI generated it and it works for me' is never an
acceptable answer" — and barrier (4) by the vendor terms' allocation of Output to the customer;
none cites Nissenbaum. Matthias's "responsibility gap" (*Ethics and Information Technology*
6(3):175–183, 2004, [doi:10.1007/s10676-004-3422-1](https://doi.org/10.1007/s10676-004-3422-1),
abstract via Wayback) argues that learning machines create cases where "nobody has enough
control over the machine's actions to be able to assume the responsibility"; Elish's "moral
crumple zone" (*Engaging STS* 5:40–60, 2019,
[doi:10.17351/ests2019.260](https://doi.org/10.17351/ests2019.260), abstract) names the
pattern where responsibility is "misattributed to a human actor who had limited control".
Camargo's note applies Elish's term to agent-written code and states that "Shared ownership
alone does not resolve these gaps"
([arXiv:2609.09022](https://arxiv.org/html/2609.09022), full text, argument).

### Regulation: the EU AI Act's editorial-responsibility exemption

Article 50(4) of Regulation (EU) 2024/1689 applies to AI-generated text "published with the
purpose of informing the public on matters of public interest" and exempts it from labelling
"where the AI-generated content has undergone a process of human review or editorial control
and where a natural or legal person holds editorial responsibility for the publication"
([artificialintelligenceact.eu/article/50](https://artificialintelligenceact.eu/article/50/),
secondary reproduction of the Official Journal text; EUR-Lex returned HTTP 202 with an empty
body). The ASF guidance paraphrases this as "such text must be labeled as AI-generated unless a
person reviewed it before publication and takes responsibility for it ... review it before you
publish it, or label it", applied to project announcements and replies
([ASF guidance](https://www.apache.org/legal/generative-tooling.html), full text). The ASF
paraphrase omits the Article's public-interest scope; whether project communications fall
within it is not addressed by either text. No regulation read applies an editorial-
responsibility rule to code.

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where existing notes touch it |
|---|---|---|---|
| Strong / weak / collective ownership vocabulary | Fowler 2006 bliki | argument | No counterpart |
| Four ownership models; "No single code ownership model is best" | Nordberg 2003 | argument | No counterpart |
| Collective ownership as an obligation; "everybody takes responsibility for the whole" | Beck 2000 | argument | [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss) (pair and mob as transfer) |
| Ownership as approval right and "stewardship"; three approval bits | SWE at Google ch. 9 | testimonial | No counterpart |
| CODEOWNERS as responsibility without authorship | GitHub docs | policy text | [track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure) |
| "The assignee remains responsible" under delegation | Linear docs | policy text | [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#2-attach-sessions-to-the-teams-existing-work-graph) |
| Minor contributors predict defects; 72% variance; strong-ownership scope condition; three recommendations | Bird et al. 2011 | measured | [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss); [track-measurement.md](track-measurement.md#proxies-and-telemetry) (knowledge framing only) |
| Weakly owned files 6× bugs; intentional vs unintentional weak ownership; "accountability can be unclear" | Greiler et al. 2015 | measured, qualitative | [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss); [track-measurement.md](track-measurement.md#proxies-and-telemetry) |
| "hold the right people accountable"; line-level authorship and defects | Rahman and Devanbu 2011 | measured | [track-measurement.md](track-measurement.md#proxies-and-telemetry) |
| FLOSS replication: relationship weak; 2015: relative importance low | Foucault et al. 2014, 2015 | measured | [track-measurement.md](track-measurement.md#proxies-and-telemetry) (2014 only) |
| Review-aware ownership; 67–86% never authored but reviewed; minor author and reviewer predicts defects | Thongtanunam et al. 2016 | measured | No counterpart |
| DCO clauses (a)–(d) name a person; no clause for a tool | DCO 1.1 | policy text | No counterpart |
| "AI agents MUST NOT add Signed-off-by"; four submitter duties | kernel coding-assistants.rst | policy text | [review-capacity-and-volume.md](review-capacity-and-volume.md#attribution-and-procedure-the-linux-kernel) (capacity clauses only) |
| Co-developed-by requires the co-author's sign-off | kernel submitting-patches.rst | policy text | No counterpart |
| "understand and be able to defend everything you submit"; maintainer discretion list | kernel generated-content.rst | policy text | No counterpart |
| "the submitter is ultimately on the hook" | LWN 1049830 | testimonial | [review-capacity-and-volume.md](review-capacity-and-volume.md#attribution-and-procedure-the-linux-kernel) |
| Copilot commits authored by the agent, human as co-author; initiator's approval does not count | GitHub Copilot docs | policy text | [track-rationale-as-artifact.md](track-rationale-as-artifact.md#forge-level-attribution) (co-author only) |
| Claude Code default `Co-Authored-By` model trailer | Claude Code settings reference | policy text | No counterpart |
| Projects forbidding the LLM `Co-authored-by` trailer; pytest suggesting it | attrs, pip, LinkML, Mesa, pytest | policy text | [track-hand-off-checks.md](track-hand-off-checks.md#policy-texts) (comprehension clauses only) |
| 43.4% of policies assign accountability; none waives it; five commits "Enforcing Human Accountability" | Hora et al. 2026 | measured | [track-hand-off-checks.md](track-hand-off-checks.md#how-hora-et-al-report-enforcement); [landscape-sweep.md](landscape-sweep.md) (other dimensions) |
| ICLA sections 4, 5, 7, 8 and three conditions; `Generated-by:` | ASF guidance | policy text | No counterpart |
| Treat AI output "no differently" | LF guidance | policy text | No counterpart |
| DCO (b)/(c) compliance "unclear"; GPL "cannot truly release"; "tainted code"; copyleft "void" | QEMU, OpenTTD, NetBSD, Gentoo | policy text | [review-capacity-and-volume.md](review-capacity-and-volume.md#bans-gentoo-netbsd-qemu) (capacity rationale only) |
| Customer owns Output and must review it; vendor liability limited to IP defence | Anthropic, OpenAI, GitHub terms | policy text | No counterpart |
| Possession decreases with autonomy; accountability willingness stable | Seo et al. 2026 | measured | [literature-addendum.md](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026) (title only) |
| Agent code modified less; "ownership hypothesis remains untested" | Rahman and Shihab 2026 | measured; argument | No counterpart |
| "accountability anxiety" | Alami et al. 2026 | qualitative | [adjacent-literatures.md](adjacent-literatures.md#finding) |
| Four barriers to accountability | Nissenbaum 1996 | argument | No counterpart |
| Responsibility gap; moral crumple zone | Matthias 2004; Elish 2019 | argument | No counterpart |
| Editorial-responsibility exemption scoped to public-interest text | EU AI Act Art. 50(4) | policy text | No counterpart |

"No counterpart" means no note in this directory addresses the point; it is a statement about the notes, not about the wider literature.

## Corrections proposed

1. **literature-addendum.md, Target 1 (Seo et al. entry)**: "Seo et al.'s design and sample
   are therefore unknown here." — The design is now readable: the OpenAlex record of
   [doi:10.1145/3742413.3789121](https://api.openalex.org/works/https://doi.org/10.1145/3742413.3789121)
   carries the abstract (within-subjects; High, Medium, Low autonomy; possession, identity,
   responsibility, attribution, disclosure), and Camargo's
   [arXiv:2609.09022](https://arxiv.org/html/2609.09022) reports "a study with 30 participants".
   A supplement, not a retraction: the sentence was true of the ACM page.
2. **literature-addendum.md, Corrections proposed, item 7** and **evidence-and-mechanisms.md,
   Dead ends and gaps**: "still no quantitative ownership instrument" — Seo et al. (IUI 2026)
   is a quantitative within-subjects measurement of possession, identity and responsibility
   under three autonomy levels
   ([doi:10.1145/3742413.3789121](https://dl.acm.org/doi/10.1145/3742413.3789121), abstract), and
   Rahman and Shihab ([arXiv:2601.16809](https://arxiv.org/html/2601.16809)) is a behavioural
   proxy (modification survival) with an explicit, untested ownership hypothesis. Whether Seo
   et al.'s participants were professionals is not readable, so the addendum's stricter
   "on professionals" phrasing in Target 1 may stand; the unqualified dead-end sentence does
   not.
3. **track-measurement.md, Proxies and telemetry**: "Foucault, Falleri, and Blanc find in open
   source that 'the relationship between ownership metrics and module faults is weak ...'" —
   not wrong, but the journal extension (Foucault, Teyton, Lo, Blanc, Falleri, *IST* 64, 2015,
   [doi:10.1016/j.infsof.2015.01.013](https://ink.library.smu.edu.sg/sis_research/2848))
   "confirm[s] the existence of a relationship" while finding its "relative importance ... is
   low"; a reader of the 2014 sentence alone would take the FLOSS result as null rather than
   weak.

## Dead ends

- LaToza, Venolia, DeLine 2006 ("Maintaining mental models: a study of developer work habits",
  ICSE 2006): every PDF route returned 403 or 404; the 72% / 92% ownership figures are cited
  only through Greiler et al. 2015.
- Seo et al. 2026 full text: ACM returned 403 and the Wayback copy 404; the sample
  description, scale, and participant population are not read.
- GitHub Generative AI Services Terms (gh.io/terms), the successor to the Copilot Product
  Specific Terms: HTTP 500 on every attempt; the deprecated terms and the Terms of Service §J
  are cited instead.
- EUR-Lex (Regulation 2024/1689) returned HTTP 202 with an empty body; Article 50(4) is quoted
  from a secondary reproduction.
- git.kernel.org served an anti-bot challenge page; the kernel documents were read from the
  raw GitHub mirror and history from the GitHub commits API.
- Microsoft Research PDF hosts returned 403; Bird 2011 and Greiler 2015 were read from
  Wayback `id_` raw captures of the same URLs.
- HAL's document URL for Foucault 2014 returned HTML; the scholar.archive.org route worked.
  The SMU `viewcontent.cgi` route for Foucault 2015 returned HTML; only the landing-page
  abstract is read.
- Semantic Scholar and the arXiv export API returned 429; OpenAlex, Crossref, and direct arXiv
  pages were used instead.
- Springer pages for Matthias 2004 and Nissenbaum 1996 were bot-walled; Nissenbaum was read from
  the author's PDF, Matthias only as a Wayback abstract.
- "dco.org DCO Policy Tracker" is the Digital Cooperation Organization, unrelated to the
  Developer Certificate of Origin.
- GitLab's 2026 AI Accountability Report is gated behind a form; no figure from it is cited.
- No source was found that measures whether a reviewer who approves an agent's Pull Request
  feels or is held to ownership of it afterwards; Seo et al. measure the author's feeling under
  varying autonomy, Rahman and Shihab measure later modification, and no study measures the
  accountable reviewer.
- No policy read defines what "taking full responsibility" obliges beyond responding to review
  and fixing defects; the kernel's `generated-content.rst` and Mastodon's policy come nearest
  (explain the change; do not answer "the AI generated it").
- No study of accountability allocation for an Agent Session that spans several people (one
  starts it, another approves, a third merges) was found; Thongtanunam et al. 2016 is the
  nearest pre-AI analysis of a multi-role chain.
- No tracker documentation other than Linear's names who remains responsible for an Issue
  delegated to an agent.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Alami, Paja, Tiwari, "accountability anxiety" interview study (2026). https://arxiv.org/abs/2609.03456
- Anthropic, Commercial Terms of Service (effective 2025-06-17). https://www.anthropic.com/legal/commercial-terms
- Anthropic, Consumer Terms of Service (effective 2025-10-08). https://www.anthropic.com/legal/consumer-terms
- Anthropic, Claude Code settings reference (`attribution`). https://code.claude.com/docs/en/settings-reference.md
- Apache Software Foundation, Generative Tooling Guidance ("August 2026"). https://www.apache.org/legal/generative-tooling.html
- artificialintelligenceact.eu, Article 50 of Regulation (EU) 2024/1689 (secondary reproduction). https://artificialintelligenceact.eu/article/50/
- Beck, *Extreme Programming Explained*, 1st ed. (2000), archive.org OCR text. https://archive.org/details/kentBeck2000
- Bird, Nagappan, Murphy, Gall, Devanbu, "Don't Touch My Code! Examining the Effects of Ownership on Software Quality" (2011). https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf
- Camargo, "It Is Not My Code Anymore" (2026-09). https://arxiv.org/html/2609.09022
- Cilium community, AI-POLICY.md. https://raw.githubusercontent.com/cilium/community/main/AI-POLICY.md
- Corbet, "Coding assistants and the kernel" (Maintainers Summit report), LWN 2025-12-11. https://lwn.net/Articles/1049830/
- Developer Certificate of Origin 1.1. https://developercertificate.org/
- Draxler et al., "The AI Ghostwriter Effect", ACM TOCHI 31(2) (2024), cited via Camargo. https://doi.org/10.1145/3637875
- Elish, "Moral Crumple Zones", Engaging STS 5 (2019), abstract. https://doi.org/10.17351/ests2019.260
- Foucault, Falleri, Blanc, "Code Ownership in Open-Source Software", EASE 2014. https://scholar.archive.org/work/veyzrlolbvggdolb2rcu5umc2u/access/wayback/https://hal.archives-ouvertes.fr/hal-00976024/document
- Foucault, Teyton, Lo, Blanc, Falleri, "Impact of developer turnover and code ownership on software quality", IST 64 (2015), abstract. https://ink.library.smu.edu.sg/sis_research/2848
- Fowler, "CodeOwnership" (2006-05-12). https://martinfowler.com/bliki/CodeOwnership.html
- Gentoo Council, AI policy (2024-04-14). https://wiki.gentoo.org/wiki/Project:Council/AI_policy
- Ghostty, AI_POLICY.md. https://raw.githubusercontent.com/ghostty-org/ghostty/main/AI_POLICY.md
- GitHub, About code owners. https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- GitHub, About Copilot cloud agent. https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent
- GitHub, Copilot Product Specific Terms (October 2024; deprecated 2026-03-05), via Wayback. https://github.com/customer-terms/github-copilot-product-specific-terms
- GitHub, Responsible use of Copilot agents. https://docs.github.com/en/copilot/responsible-use/agents
- GitHub, Reviewing Copilot output. https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/review-copilot-output
- GitHub, Terms of Service (effective 2026-04-27), section J. https://docs.github.com/en/site-policy/github-terms/github-terms-of-service
- GitLab, 2026 AI Accountability Report (landing page only). https://about.gitlab.com/resources/ai-accountability-survey-2026/
- GraalVM, CODING_ASSISTANTS.md. https://raw.githubusercontent.com/oracle/graal/master/CODING_ASSISTANTS.md
- Greiler, Herzig, Czerwonka, "Code Ownership and Software Quality: A Replication Study", MSR 2015. https://www.microsoft.com/en-us/research/wp-content/uploads/2015/05/MSR-2015-Source-Code-Ownership-IEEE_camera-ready.pdf
- Hora, Robbes, Zacchiroli, AI contribution policies census (2026). https://arxiv.org/html/2609.07542
- Linear, Assign and delegate issues. https://linear.app/docs/assigning-issues
- LinkML, AI_COVENANT.md. https://raw.githubusercontent.com/linkml/linkml/main/AI_COVENANT.md
- Linux Foundation, Generative AI Guidance. https://www.linuxfoundation.org/legal/generative-ai
- Linux kernel, Documentation/process/coding-assistants.rst. https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-assistants.rst
- Linux kernel, Documentation/process/generated-content.rst. https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/generated-content.rst
- Linux kernel, Documentation/process/submitting-patches.rst. https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/submitting-patches.rst
- Linux kernel, commit history of coding-assistants.rst (GitHub API). https://api.github.com/repos/torvalds/linux/commits?path=Documentation/process/coding-assistants.rst
- Mastodon, AI_POLICY.md. https://raw.githubusercontent.com/mastodon/.github/main/AI_POLICY.md
- Matthias, "The responsibility gap", Ethics and Information Technology 6(3) (2004), abstract. https://doi.org/10.1007/s10676-004-3422-1
- melissawm, open-source-ai-contribution-policies (secondary index). https://github.com/melissawm/open-source-ai-contribution-policies
- Mesa, Submitting Patches. https://docs.mesa3d.org/submittingpatches.html
- NetBSD, Commit Guidelines. https://www.netbsd.org/developers/commit-guidelines.html
- Nissenbaum, "Accountability in a Computerized Society", Science and Engineering Ethics 2(1) (1996). https://nissenbaum.tech.cornell.edu/papers/accountability.pdf
- Nordberg, "Managing Code Ownership", IEEE Software 20(2) (2003), abstract. https://doi.org/10.1109/MS.2003.1184163
- OpenAI, Services Agreement (updated 2025-12-01), via Wayback. https://openai.com/policies/services-agreement/
- OpenAI, Terms of Use (effective 2026-01-01), via Wayback. https://openai.com/policies/row-terms-of-use/
- OpenTTD, CONTRIBUTING.md, "Use of AI". https://github.com/OpenTTD/OpenTTD/blob/master/CONTRIBUTING.md#use-of-ai
- Pierce, Jussila, Cummings, "Psychological ownership within the job design context", JOB 30(4) (2008), abstract. https://doi.org/10.1002/job.550
- Pierce, Kostova, Dirks, "Toward a Theory of Psychological Ownership in Organizations", AMR 26(2) (2001), abstract. https://doi.org/10.5465/amr.2001.4378028
- pip, AI_POLICY.md. https://raw.githubusercontent.com/pypa/pip/main/AI_POLICY.md
- pytest, CONTRIBUTING.rst, AI/LLM-assisted contributions policy. https://raw.githubusercontent.com/pytest-dev/pytest/main/CONTRIBUTING.rst
- python-attrs, AI_POLICY.md. https://raw.githubusercontent.com/python-attrs/attrs/main/.github/AI_POLICY.md
- QEMU, docs/devel/code-provenance.rst. https://gitlab.com/qemu-project/qemu/-/raw/master/docs/devel/code-provenance.rst
- Rahman and Devanbu, "Ownership, Experience and Defects", ICSE 2011, archived PDF. https://web.archive.org/web/20160208035713id_/http://www.inf.usi.ch:80/faculty/lanza/Education/SDE-2011/papers/Rahm2011a.pdf
- Rahman and Shihab, agent-generated code survival analysis (2026-01). https://arxiv.org/html/2601.16809
- Sadowski, Winter, Wright, "Code Review", *Software Engineering at Google* ch. 9. https://abseil.io/resources/swe-book/html/ch09.html
- Self-declaration of AI-generated code study (2025), abstract. https://arxiv.org/abs/2504.16485
- Seo, Deldari, Mentis, "Whose Code Is It?", IUI 2026, abstract via OpenAlex. https://dl.acm.org/doi/10.1145/3742413.3789121
- Thongtanunam, McIntosh, Hassan, Iida, "Revisiting Code Ownership and its Relationship with Software Quality in the Scope of Modern Code Review", ICSE 2016. https://rebels.cs.uwaterloo.ca/papers/icse2016_thongtanunam.pdf
- Van Dyne and Pierce, "Psychological ownership and feelings of possession", JOB 25(4) (2004), abstract. https://doi.org/10.1002/job.249
- Wells, "Collective Ownership", extremeprogramming.org. http://www.extremeprogramming.org/rules/collective.html
- AI disclosure registered report (2026), abstract. https://arxiv.org/abs/2607.09434
