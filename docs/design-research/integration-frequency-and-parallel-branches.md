---
status: research
date: 2026-09-15
---

# Integration frequency and parallel branches

Research date: 2026-09-15

This note documents what the software-engineering literature and the tool vendors' own
texts say about three linked questions the corpus has so far treated as background: how
often work on parallel branches conflicts, what long-lived and many branches cost in quality
and delay, and what happens to both when coding agents multiply the number of concurrent
branches on one repository — worktrees per Agent Session, batches of worktree-isolated Agent
Runs, cloud agents pushing branches. It is documentary: it records what each source measured
or asserted, with its numbers, sample and method, and maps each finding to where the
existing notes in this directory touch it. It does not evaluate fit for Dashpot or any tool.
Terminal citations are primary — the paper or the author's copy, the vendor's documentation
page, the practice text — and every figure is reported as the source states it. The read
level is marked per source ("full text", "abstract", "metadata", "secondary",
"unverified"); the evidence type is marked as measured, qualitative, testimonial or
argument. Where an earlier note already covers a source, this note links to it rather than
repeating it: the workspace-awareness tools (Palantír, FASTDash) and the socio-technical
congruence line are in
[workspace-awareness-and-coordination.md](workspace-awareness-and-coordination.md#awareness-tools-for-developers-and-how-they-were-evaluated);
merge queues as review capacity and the AIDev-based counts of agent Pull Requests are in
[review-capacity-and-volume.md](review-capacity-and-volume.md#tooling-positioned-as-capacity);
batch size as a flow device is in
[flow-wip-limits-and-constraints.md](flow-wip-limits-and-constraints.md#reinertsen-and-dora-on-batch-size--argument-and-survey);
the chat-per-worktree pattern in OpenAI's product and GitButler's branch-first response are in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#openaicodex-specific-signs-of-the-same-fault-line);
and ownership footprints (who touched what, and what is lost when they leave) are in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss).

## Finding

Across the pre-agent measurements the textual merge-conflict rate for a merge between
concurrently developed lines sits in a band from roughly one in six to one in three:
17% of merges in nine open-source systems (one in six), with a further 33% of the
version-control-clean merges hiding a build or test conflict, conflicts persisting a mean of
10 days and a median of 1.6 days
([Brun, Holmes, Ernst and Notkin 2011](https://people.cs.umass.edu/~brun/pubs/pubs/Brun11fse.pdf),
full text); 22.75%–46.62% of CVS workspace integrations in GCC, JBoss, jEdit and Python
([Zimmermann 2007](https://thomas-zimmermann.com/publications/files/zimmermann-msr-2007.pdf),
full text); 7.6%–19.3% of merges in Perl, Storm, Jenkins and Voldemort, with resolution
averaging 22.93 days in Perl
([Kasi and Sarma 2013](https://web.engr.oregonstate.edu/~sarmaa/wp-content/uploads/2020/08/2486788.2486884.pdf),
full text); and a "10 to 20%" band restated by the 2,731-project study of 25,328 failed
merges ([Ghiotto, Murta, Barros and van der Hoek 2020](https://www.ic.uff.br/~leomurta/papers/ghiotto2018.pdf),
full text). The one industrial number relating conflict probability to the count of
concurrent changes is Uber's: "chances of a conflict ↑ from 5% to 40% as #. of concurrent &
potentially conflicting changes ↑"
([Ananthanarayanan et al. 2019, author slides](https://sundaram.io/slides/eurosys19.pdf),
slides; paper abstract only). Quality costs of branch structure were measured at Microsoft:
branch activity at its maximum predicts up to 59% (±11%) more post-release failures in
Windows Vista, and adding branch metrics to a defect model raised its fit from 17% to 36% for
Windows 7
([Shihab, Bird and Zimmermann 2012](https://thomas-zimmermann.com/publications/files/shihab-esem-2012.pdf),
full text); at Lucent, 12.5% of deltas were made to the same file by different developers
within 24 hours and parallel change was a significant contributor to defect variance after
size and history were controlled
([Perry, Siy and Votta 2001](https://users.ece.utexas.edu/~perry/work/papers/DP-01-tosem.pdf),
full text); and Microsoft engineers reported 5.45 hours a month on branching and integration,
with the Big Bang Merge and Branchmania among the anti-patterns they named
([Bird and Zimmermann 2012](https://thomas-zimmermann.com/publications/files/bird-fse-2012.pdf),
full text). The frequency prescriptions — merge "at least daily", "no code sits on a branch
longer than a few hours"
([Fowler 2024](https://martinfowler.com/articles/continuousIntegration.html), full page);
branches that "should only last a couple of days"
([Hammant](https://trunkbaseddevelopment.com/short-lived-feature-branches/), full page);
"less than a day" and "less than three active branches in total"
([DORA 2016](https://dora.dev/research/2016/2016-state-of-devops-report.pdf), full text,
n>4,600 self-report) — rest on argument and cross-sectional survey, not on the conflict
measurements. Integration-order devices exist on both sides of the agent line: Cassandra
schedules tasks to avoid predicted conflicts (Kasi and Sarma 2013), bors advances trunk only
when a temporary integration revision passes tests and offers "priority markers to help you
manually tune the integration order"
([Hoare 2014](https://web.archive.org/web/2020id_/https://graydon2.dreamwidth.org/1597.html),
full text), Rust's rollups batch by a per-PR `rollup=` tag
([rust-forge](https://raw.githubusercontent.com/rust-lang/rust-forge/master/src/release/rollups.md),
full text), and GitHub's merge queue builds groups of 1–100 in FIFO order
([GitHub Docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue),
full page). The agent vendors' texts multiply branches without stating an integration order:
Claude Code's `--worktree`, `isolation: worktree` subagents and `/batch` (5 to 30
worktree-isolated subagents each opening a Pull Request) isolate writes and prompt to keep or
remove the worktree at exit, agent teams carry the only count advice ("Start with 3-5
teammates") and the only same-file warning ("Two teammates editing the same file leads to
overwrites")
([Claude Code Docs, worktrees](https://code.claude.com/docs/en/worktrees),
[agent teams](https://code.claude.com/docs/en/agent-teams), full pages); Anthropic's April
2025 practices say "3-4 git checkouts" and that with non-overlapping tasks each Claude works
"without ... dealing with merge conflicts"
([Anthropic 2025, Wayback](https://web.archive.org/web/20250601id_/https://www.anthropic.com/engineering/claude-code-best-practices),
full text); Cursor caps managed worktrees at 25 per machine, `/best-of-n` "does not merge
changes back", and cloud agents may run "as many ... as you want in parallel"
([Cursor Docs](https://cursor.com/docs/configuration/worktrees), full pages); Codex keeps 15
managed worktrees per default and relies on Git's rule that a branch cannot be checked out
twice ([OpenAI](https://learn.chatgpt.com/docs/environments/git-worktrees), full page);
Conductor's only order rule is "Use multiple workspaces when tasks should land independently"
([Conductor Docs](https://docs.conductor.build/concepts/parallel-agents), full page). The
first measurements of agent-authored branches, both on the AIDev dataset, report a 27.67%
textual conflict rate on 107,026 open-or-closed-unmerged agent Pull Requests, rising with
churn from about 9.9% at 2 lines to about 30% at 25 lines and differing by agent (Copilot
15.24% to Codex 31.85%)
([Ogenrwot and Businge 2026](https://arxiv.org/abs/2604.03551), full text), and, on 33,596
Pull Requests in 2,807 repositories, that 79.4% of agent Pull Requests were open concurrently
with another and that replayed merges of co-active pairs conflicted in 19.8% of intra-agent
pairs (119/601) and 41.7% of cross-agent pairs (48/115), a "conservative lower bound" that
counts textual conflicts only
([Xu, Subramanian and Karthik 2026](https://arxiv.org/abs/2607.04697), full text). No source
read for this note measures conflict or quality as a function of the number of concurrent
Agent Runs on one repository, and no vendor text states how many parallel runs is too many
or in what order their branches are to land.

## How often parallel work conflicts: the pre-agent measurements

### Perry, Siy and Votta 2001 — parallel changes at Lucent

One subsystem (of about 50) of Lucent's 5ESS switch, April 1984 to April 1996, studied
through its change-management data. Around 60% of files were touched by more than one
modification request (MR) within release I6; for the maximum number of concurrent MRs per
file per day (PCmax), 55% of files never had more than one, about 30% had up to two, 0.6%
more than six, with an average PCmax of 1.73. Only 10% of initial MRs needed more than one
developer. "Twelve and one half percent of all deltas are made by different developers to
the same files within a day of each other, and some of these may interfere with each
other"; about 3% of those physically overlap. An ANOVA of 1994–96 defects found parallel
change a significant contributor to defect variance after number of deltas, size and past
faults; lifetime was not significant. Evidence type: measured, one subsystem, one
organisation. Read: full text.
Source: <https://users.ece.utexas.edu/~perry/work/papers/DP-01-tosem.pdf>.

### Zimmermann 2007 — workspace updates in CVS

GCC, JBoss, jEdit and Python, mined at the level of CVS `update` operations. Integration
rate (updates that merged remote changes into a workspace) was 0.15%–0.54% of updates; of
those integrations, the fraction that produced a conflict was 22.75% (GCC) to 46.62%
(JBoss), 24.32% and 38.26% for the other two; 1.86%–9.06% of commits led to a conflict; "in
GCC and JEDIT approximately every 11th commit led to an integration, for PYTHON even every
5th commit". Evidence type: measured, four projects, CVS-era workspace model. Read: full
text. Source:
<https://thomas-zimmermann.com/publications/files/zimmermann-msr-2007.pdf>.

### Brun, Holmes, Ernst and Notkin 2011 — "Proactive detection of collaboration conflicts"

Nine open-source systems (Git, Perl5, Voldemort, Gallery3, Insoshi, jQuery, MaNGOS, Rails
among them), selected for at least ten developers and a thousand changesets, 3.4M
non-comment source lines and 550,000 development versions, histories ending 13 February
2010. The answer to their first research question "is that conflicts are the norm": for
each subject there was no time at which every developer pair was consistent. 17% of merges,
"one in six", had textual conflicts; 19% of potential earlier merges would have conflicted,
so 81% would have been clean. For the three systems whose builds and tests they could run
(Git, Perl5, Voldemort; 5,355 merges): 76% clean, 16% textual, 1% build, 6% test failure;
"33% of the 399 merges that the version control system reported as" clean in fact carried a
build or test conflict. Of the conflict relationships observed, 93% developed from a state
in which both sides had been consistent (TEST✓) and 7% from a behind state. Conflicts
persisted a mean of 10 days and a median of 1.6 days; the longest textual conflict persisted
138 days (Voldemort) and the longest by changesets 232 (Gallery3). The paper cites
Zimmermann's 23–47% band. Crystal, the speculative-merging tool the paper proposes, was
evaluated only "preliminary and qualitative[ly]". Evidence type: measured (history
analysis); the tool evaluation is qualitative. Read: full text.
Source: <https://people.cs.umass.edu/~brun/pubs/pubs/Brun11fse.pdf>.

### Kasi and Sarma 2013 — four projects, and Cassandra

Perl (185 merges, 51 developers in the six-month window), Voldemort (380 merges, 33),
Storm (88 merges, whole history), Jenkins (505 merges, 100 developers). "In the projects
analyzed merge conflicts ranged from 7.6% to 19.3%. Of the clean merges 2.1% to 14.7% had
build failures, and 5.6% to 35% of correct builds incurred test failures. Resolving these
conflicts took substantial effort, typically spanning multiple days." Perl had the fewest
direct conflicts (7.6%) but the longest resolution (22.93 days average, median 10); Storm the
most (19.3%) with 6 days average; Jenkins 13.5%. (The subject table also carries a 4.2%
conflict entry, so the abstract's lower bound and the table do not agree; recorded, not
resolved.) Cassandra encodes predicted conflicts between tasks as constraints and solves for
an ordering (Z3); on the four projects it "would have successfully avoided a majority of
conflicts". This is the pre-agent literature's explicit integration-order device: it chooses
which task each developer works on next so that concurrent tasks touch disjoint files.
Evidence type: measured (history analysis); the scheduler evaluation is retrospective
simulation. Read: full text. Source:
<https://web.engr.oregonstate.edu/~sarmaa/wp-content/uploads/2020/08/2486788.2486884.pdf>.

### Estler, Nordio, Furia and Meyer 2014 — conflicts and awareness in distributed teams

The DOSE 2013 distributed course: 171 students, 134 active developers, 12 teams, four
weeks of development, 105 questionnaire responses (78%). "More than 94%" of developers had
merge conflicts over the four weeks (none: 6.7%; one to four: 58.1%; five to nine: 18.1%;
ten or more: 17.1%); about 70% spent no more than 10 minutes per conflict. The paper's
headline is that "lack of awareness occurs more frequently" than merge conflicts and is
more harmful to performance — the awareness line this corpus treats in
[workspace-awareness-and-coordination.md](workspace-awareness-and-coordination.md#awareness-tools-for-developers-and-how-they-were-evaluated).
Evidence type: measured self-report, student teams. Read: full text. Source:
<https://se.inf.ethz.ch/people/estler/publications/Awareness_Conflicts.pdf>.

### Ghiotto, Leßenich and Owhadi-Kareshk — scale, a negative result, and prediction

Ghiotto, Murta, Barros and van der Hoek 2020: 2,731 Java projects, 25,328 failed merges,
175,805 conflicting chunks; restates the prior finding that "10 to 20%" of merges fail, some
projects near 50%; 40% of failed merges have a single chunk and 90% ten or fewer; 94% of
chunks are under 50 lines on each side; 52% involve a single language construct. Evidence
type: measured. Read: full text. Source:
<https://www.ic.uff.br/~leomurta/papers/ghiotto2018.pdf>.

Leßenich, Siegmund, Apel, Kästner and Hunsen 2018: a survey of 41 developers produced seven
candidate indicators of conflict-proneness (commit count, file count, chunk count, lines,
and so on); on 163 projects and 21,488 merge scenarios (49,449,773 LOC) none of the seven
correlated with conflict frequency (Spearman). A negative result: the intuitive size and
activity indicators developers name do not predict which merges conflict. Evidence type:
measured. Read: full text. Source: <https://www.cs.cmu.edu/~ckaestne/pdf/jase17.pdf>.

Owhadi-Kareshk, Nadi and Rubin 2019: 267,657 merge scenarios in 744 repositories across
seven languages; a classifier predicts safe merges at F1 0.95–0.97 and conflicting merges
at 0.57–0.68. Evidence type: measured. Read: abstract only. Source:
<https://arxiv.org/abs/1907.06274>.

### Nelson, Brindescu, McKee, Sarma and Dig 2019 — how developers live with conflicts

Ten interviews across seven organisations and two surveys (162 and 102 responses). The
paper's framing cites "approximately 19% of all merges" conflicting. 29.41% of respondents
do not actively monitor for conflicts; among those with reactive processes 87.72% rely on
the version-control system and 21.05% on CI to learn of one; 56.18% have deferred a
conflict at least once, and the most common effect of deferral, in 46 free-text answers, was
"Stop the Presses" (15 responses) — halting development to resolve. Evidence type:
qualitative and survey. Read: full text. Source:
<https://epiclab.github.io/publications/emse19-nelson.pdf>.

## Branch structure and quality

### Bird and Zimmermann 2012 — isolation versus liveness

A January 2011 survey to 370 Microsoft engineers in the top 10% of branch creators,
integrators and editors; 124 responses (33.6%), median 11 years' experience. Respondents
spent an average of 5.45 hours a month on branching and integration (median 3, 95th
percentile 15.45); integration took minutes to days, mostly on conflicts and verification;
integration errors "happen from time to time" and "tend to be subtle". The anti-patterns
respondents recognised most were Development Freeze, Big Bang Merge, Integration Wall and
Branchmania. The paper's what-if analysis on the Windows 7 branch tree frames the trade as
isolation (conflicts avoided by keeping lines apart) against liveness (transit time of a
change to the trunk): removing high-cost, low-benefit branches "would each have saved 8.9
days of delay and only introduced 0.04 additional conflicts on average". Evidence type:
survey plus measured simulation on one product's history. Read: full text. Source:
<https://thomas-zimmermann.com/publications/files/bird-fse-2012.pdf>.

### Shihab, Bird and Zimmermann 2012 — branch activity and post-release failures

Windows Vista and Windows 7 at binary level, post-release failures as the outcome, linear
regression with churn and complexity as controls. Base model fit 72% (Vista) and 17%
(Windows 7); adding branch activity 75%/18%; adding branch scatter 77%/19%; branch depth
under 0.5%; adding branch families 79%/36%, all at p<0.01. "H1. Branch activity: has a
negative impact on software quality. It can increase post-release failures by up to 59% in
Windows Vista and up to 51% in Windows 7"; at minimum activity, Vista failures fall to 85%
(±2.9%) of the value. Branch scatter can increase failures by up to 40% (Vista); scatter
entropy up to 43% (Windows 7); depth "very little to no impact". A second analysis finds
mismatch between the branch structure and the organisation a better predictor than mismatch
with the architecture, both significant (p<0.05), quality falling as mismatch rises. The
paper cites Perry's 12.5% and "up to 50%" of files changed by multiple developers. Evidence
type: measured, two releases of one product. Read: full text. Source:
<https://thomas-zimmermann.com/publications/files/shihab-esem-2012.pdf>.

### Zou et al. 2019 — branch use on GitHub

"Branch use in practice: a large-scale empirical study of 2,923 projects on GitHub" (QRS
2019): most projects use fewer than five branches; more than 75% of branches are fully
merged into master; branch count has a small positive association with productivity.
Evidence type: measured. Read: abstract only (doi 10.1109/qrs.2019.00047).

## Integration frequency: the practice texts and the survey evidence

### Fowler — Continuous Integration

The 18 January 2024 revision defines the practice as "each member of a team merges their
changes into a codebase together with their colleagues changes at least daily", each
integration verified by an automated build; "Continuous Integration requires full mainline
integration, no code sits on a branch longer than a few hours without being pushed into the
mainline." It distinguishes textual conflicts ("the easiest to find and resolve") from
semantic conflicts detectable only by tests, and argues that with frequent integration "the
very worst case would be ... less than a day's work to lose". It cites the DORA programme
for the deployment-frequency result, not for branch counts. Evidence type: argument and
practice description. Read: full page. Source:
<https://martinfowler.com/articles/continuousIntegration.html>.

### Hammant — trunk-based development

The site defines the practice as committing to a single trunk and gives the branch rule for
larger teams: "the branch should only last a couple of days. Any longer than two days, and
there is a risk of the branch becoming a long-lived feature branch"; one developer per
branch (two if pairing); direct-to-trunk for teams up to 15, "with 16 or more, the team is
more productive with short-lived feature branches" verified by CI before landing; Google
cited at "35000 developers and QA automators" on one trunk. Its evidence claim is that
"many publications promote Trunk-Based Development", naming *Continuous Delivery* and *The
DevOps Handbook*. Evidence type: practice text and argument. Read: full pages. Sources:
<https://trunkbaseddevelopment.com/> and
<https://trunkbaseddevelopment.com/short-lived-feature-branches/>.

### DORA 2016 and 2017

2016 (more than 4,600 respondents): "having branches or forks with very short lifetimes
(less than a day) before being merged into trunk, and less than three active branches in
total, are important aspects of continuous delivery, and all contribute to higher
performance. So does merging code into trunk or master on a daily basis. Teams that don't
have code freeze periods ... also achieve higher performance." 2017 (3,200 respondents):
"High performers have the shortest integration times and branch lifetimes, with branch life
and integration typically lasting hours"; low performers "days"; "These differences are
statistically significant"; guidance "Teams should avoid keeping branches alive more than a
day." Both are cross-sectional self-report surveys; neither reports conflict rates or
defect counts. The batch-size reading of the same reports is in
[flow-wip-limits-and-constraints.md](flow-wip-limits-and-constraints.md#reinertsen-and-dora-on-batch-size--argument-and-survey).
Evidence type: survey. Read: full text. Sources:
<https://dora.dev/research/2016/2016-state-of-devops-report.pdf> and
<https://dora.dev/research/2017/2017-state-of-devops-report.pdf>.

## Early detection and integration order: tools before agents

### Speculative and continuous merging: Crystal and WeCode

Crystal (Brun et al. 2011, above) speculatively merges each developer's workspace against
every other and reports textual, build and test conflicts as they arise. WeCode
([Guimarães and Silva 2012](https://web.archive.org/web/2015id_/http://www.cs.washington.edu/education/courses/cse590n/12sp/mario.pdf),
full text via Wayback) merges continuously inside Eclipse; in a controlled study with 21
graduates (half bachelors, half PhDs) on a 41-class, 1,143-line application, a confederate
introduced four indirect conflicts, and the MERGE condition detected 28 of 28 before
check-in against 7 of 28 for a heuristic and 0 of 28 for repository-only detection (χ² =
62.4, df 2, p<.001). Evidence type: measured, laboratory. Palantír and FASTDash, which show
who is touching what rather than merging, are in
[workspace-awareness-and-coordination.md](workspace-awareness-and-coordination.md#palantír-sarma-noroozi-and-van-der-hoek-2003-sarma-redmiles-and-van-der-hoek-2012).

### Cassandra as an integration-order device

Cassandra (Kasi and Sarma 2013, above) is the one pre-agent tool read for this note that
acts on the order of work rather than on its visibility: it takes the set of open tasks and
their predicted file footprints and schedules them so that concurrently active tasks do not
overlap. Its evaluation is a retrospective simulation, not a deployment. Evidence type:
measured simulation. Read: full text.

## Merge queues as integration devices

[review-capacity-and-volume.md](review-capacity-and-volume.md#tooling-positioned-as-capacity)
records merge queues as tooling "positioned as capacity"; this section records them as
integration-order devices, which is what their own texts describe.

### bors and the Not Rocket Science Rule

Graydon Hoare's 2014 post states the rule — "automatically maintain a repository of code
that always passes all the tests" — and its mechanism: bors tests a temporary integration
revision (trunk plus the candidate) and advances trunk only if the tests pass. "It does
mean that your integration cycle time is bounded by your test cycle time, and it means that
some changes take a number of attempts to integrate (bors supports priority markers to help
you manually tune the integration order)." Evidence type: testimonial and design. Read:
full text via Wayback (the live page requires a login). Source:
<https://web.archive.org/web/2020id_/https://graydon2.dreamwidth.org/1597.html>.

### Rust rollups

The rust-forge page: every Pull Request is tested after merging into master; a full CI run
is about 3.5 hours; because serial testing would cap throughput, reviewers tag Pull
Requests `rollup=always`, `maybe`, `iffy` or `never` and a rollup batches several into one
integration revision, example compositions running from one `iffy` plus four `maybe` plus
five `always` up to one or two `iffy` plus eight `maybe` plus ten `always`; a failed rollup
is bisected. Evidence type: practice text. Read: full text. Source:
<https://raw.githubusercontent.com/rust-lang/rust-forge/master/src/release/rollups.md>.

### GitHub merge queue

The documentation describes temporary `gh-readonly-queue/{base_branch}` branches combining
the base with queued Pull Requests, a `merge_group` webhook that runs checks "against the
combination", FIFO ordering, removal of a Pull Request from the queue when its checks fail
or it conflicts, a build concurrency of 1–100, group sizes of 1–100, and the option to "only
merge non-failing pull requests". Evidence type: product documentation. Read: full page.
Source:
<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue>.

### Uber SubmitQueue

Ananthanarayanan, Ardekani, Haenikel, Varadarajan, Soriano, Patel and Adl-Tabatabai,
"Keeping master green at scale" (EuroSys 2019). The author slides carry the one number
relating conflict probability to concurrency: "Observation: Chances of a conflict ↑ from 5%
to 40% as #. of concurrent & potentially conflicting changes ↑". They set out the design
space — a serial queue "Guarantees an always green master by serializing changes" but "Does
not scale to 1000s of changes/day"; batching "Improves the throughput if batches succeed more
often than not" but "masks intermediate changes that fail" and "will fail often as the size
of the batch increases"; speculating on every outcome needs 2ⁿ builds for n changes — and the
paper's answer, probabilistic speculation guided by a conflict analyzer, evaluated in
production, with the analyzer improving P95 turnaround "by up to 50%" at 500 changes/hour
and P99 "only 4x worse under extreme contention". Evidence type: measured, one company; the
5%–40% figure is a slide without stated n. Read: slides full; paper abstract only (ACM PDF
403). Sources: <https://sundaram.io/slides/eurosys19.pdf>;
<https://doi.org/10.1145/3302424.3303970>.

## Agent tools: worktrees, parallel runs, and what vendors say about count and order

### Claude Code

The worktrees page: `claude --worktree <name>` (`-w`) creates `.claude/worktrees/<name>/`
on branch `worktree-<name>`; `EnterWorktree` and `ExitWorktree` move a session in and out;
four isolation checks confine a session's git commands to its worktree; at exit, a clean
unnamed worktree is removed automatically, a named one prompts, and one with work prompts to
keep or remove — "Removing deletes the worktree directory and its branch, along with all the
work in them"; `-p` runs get no exit prompt and their worktrees are left for a later sweep.
Subagents declared `isolation: worktree` get a temporary worktree branched from the default
branch unless `worktree.baseRef` is `"head"`, removed by a periodic sweep after
`cleanupPeriodDays`. The common-workflows page: "`/batch` is a skill that has Claude split
one large change into 5 to 30 worktree-isolated subagents that each open a pull request",
and "Running several sessions or subagents at once multiplies token usage." The agent-teams
page is the only Anthropic text with a count: "There's no hard limit on the number of
teammates, but practical constraints apply" — token cost "scale[s] linearly", "Coordination
overhead increases", "Diminishing returns" — "Start with 3-5 teammates for most workflows
... If you have 15 independent tasks, 3 teammates is a good starting point", and the only
same-file rule: "Two teammates editing the same file leads to overwrites. Break the work so
each teammate owns a different set of files." Teammates share one checkout; they are not
worktree-isolated. None of the pages says in what order worktree branches or `/batch` Pull
Requests are to land, or what to do when two of them touch one file. Evidence type: product
documentation. Read: full pages. Sources: <https://code.claude.com/docs/en/worktrees>;
<https://code.claude.com/docs/en/sub-agents>; <https://code.claude.com/docs/en/agent-teams>;
<https://code.claude.com/docs/en/common-workflows>; <https://code.claude.com/docs/en/commands>.
Compaction, resume and subagent hand-off on the same product are in
[handover-between-sessions-people-and-agents.md](handover-between-sessions-people-and-agents.md#claude-code-compaction-rewind-resume-subagents).

### Anthropic's best practices, April 2025

The original engineering post (18 April 2025; the live URL now redirects to the docs)
recommends, under "Have multiple checkouts of your repo", "Create 3-4 git checkouts in
separate folders", one terminal tab each, and "Cycle through to check progress and
approve/deny permission requests"; and under "Use git worktrees", that a worktree per
independent task means "one Claude refactoring your authentication system while another
builds a completely unrelated data visualization component. Since the tasks don't overlap,
each Claude can work at full speed without waiting for the other's changes or dealing with
merge conflicts", with cleanup by `git worktree remove`. The non-overlap is assumed, not
checked. Evidence type: vendor practice text. Read: full text via Wayback (1 June 2025
capture). Source:
<https://web.archive.org/web/20250601id_/https://www.anthropic.com/engineering/claude-code-best-practices>.

### Cursor

"Use worktrees when you want to start several agents on the same repo without conflicts."
`/worktree` creates one, `/apply-worktree` brings its changes into the main checkout,
`/delete-worktree` removes it; `/best-of-n` runs the same prompt in several worktrees and
"compares runs only. It does not merge changes back into your main checkout for you";
`cursor.worktreeMaxCount` defaults to 25 per machine and cleanup runs every six hours; the
CLI's `-w` puts worktrees under `~/.cursor/worktrees/<repo>/<name>`. Cloud agents "work on
a separate branch, then push changes to your repo for handoff" as "merge-ready PRs"; "You
can run as many agents as you want in parallel". The cloud-agents page does not address
conflict management, simultaneous modification of the same files, or a limit on the number
of parallel agents. Evidence type: product documentation. Read: full pages. Sources:
<https://cursor.com/docs/configuration/worktrees>; <https://cursor.com/docs/cli/using>;
<https://cursor.com/docs/background-agent> (titled "Cloud Agents").

### OpenAI Codex

A managed worktree per chat under `$CODEX_HOME/worktrees`; "Codex keeps your most recent 15
Codex-managed worktrees" by default, deleting older ones when chats are archived or the
limit is exceeded and saving a snapshot first; hand-off moves work between checkouts; the
only conflict statement is Git's own — the same branch cannot be "checked out in more than
one worktree at a time"; no advisory on how many chats to run.
The product's chat-per-worktree ownership model is analysed in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#openaicodex-specific-signs-of-the-same-fault-line).
Evidence type: product documentation. Read: full page. Source:
<https://learn.chatgpt.com/docs/environments/git-worktrees>.

### Conductor and GitButler

Conductor (Melty Labs) keeps workspaces under `~/conductor/workspaces/<repo>/<workspace>`
and gives one decision rule: "Use multiple workspaces when tasks should land independently.
Use multiple agents in one workspace when the work shares the same branch, code state, and
context"; "The tradeoff is that agents in the same workspace can edit the same files"; its
decision guide maps "Two features can ship separately" to multiple workspaces ("Each gets
its own branch, app state, and PR path") and issue fan-out to one workspace per issue.
Evidence type: product documentation. Read: full pages. Sources:
<https://docs.conductor.build/concepts/git-worktrees>;
<https://docs.conductor.build/concepts/parallel-agents>.

GitButler's post on running several Claude Code sessions in one checkout gives the counter
case against worktrees — "you need to bootstrap each of the worktrees (`npm install`, build
artifacts, etc)" and "now you have created the fun new ability to create merge conflicts
with _yourself_" — and its device: lifecycle hooks assign each session's edits to a virtual
branch, so three sessions yield "three independent branches which can be merged in any
order". What happens when two sessions edit one file is not addressed. Evidence type:
vendor testimonial and design. Read: full page. Source:
<https://blog.gitbutler.com/parallel-claude-code>.

### Practitioner accounts

Nick Khami (26 May 2025) ran "two Claude Code agents and two Codex agents, all with the same
prompt, running in parallel within their own git worktrees" and reasons "if each has a ~25%
chance of producing something useful, then running four gives a 68% chance that at least
one will succeed", at "$0.40" against "$0.10", saving "20 minutes"; he names as frustrations
tracking which branch each worktree targets, no way to broadcast a prompt, and port
management. Evidence type: testimonial, one author, one task. Read: full page. Source:
<https://www.skeptrune.com/posts/git-worktrees-agents-and-tmux/>. The pattern — same prompt,
n worktrees, pick one — is what Cursor later packaged as `/best-of-n`.

## Measured conflicts on agent-authored branches, 2026

Both studies below draw on the AIDev dataset of agent-authored Pull Requests; the dataset's
own descriptive counts and the merge-and-review findings on it are in
[review-capacity-and-volume.md](review-capacity-and-volume.md#agentic-pull-requests-in-open-source)
and
[automation-as-a-team-player.md](automation-as-a-team-player.md#coding-agents-as-teammates-20252026).

### AgenticFlict — Ogenrwot and Businge 2026

From AIDev (932,791 Pull Requests, Hugging Face snapshot of 5 January 2026) only open or
closed-unmerged Pull Requests were retained — 142,652 from 59,412 repositories — and
`git merge --no-commit --no-ff <head>` against the base at closure was replayed for 107,026
(75.03%). 29,609 conflicted, "a conflict rate of 27.67%", with 336,380 conflict regions; a
conflicting Pull Request touches a mean of 4.36 files (median 2), 11.36 regions and 540.42
conflict lines. Table 2 by agent: Copilot 16,954 Pull Requests, 2,583 conflicting, 15.24%
[95% CI 14.69–15.78]; Cursor 7,196 / 1,421, 19.75%; Devin 8,241 / 1,883, 22.85%; Claude Code
779 / 202, 25.93% [22.85–29.01]; OpenAI Codex 73,856 / 23,520, 31.85% [31.51–32.18]. The
running text gives slightly different values (Copilot 15.43%, Cursor 20.06%, Devin 23.04%,
Claude Code 26.86%, Codex 32.31%); the inconsistency is recorded here, not resolved. By
churn decile, "PRs with a median churn of 2 lines have a conflict rate of approximately
9.9%, whereas PRs with a median churn of 25 lines exhibit a conflict rate of nearly 30%",
stabilising in the low thirties above that. Because merged Pull Requests are excluded the
rate is not comparable to the pre-agent all-merges figures; it describes Pull Requests that
were still open or abandoned. Evidence type: measured, textual conflicts only. Read: full
text (arXiv HTML, v2 of 12 May 2026; AIware 2026, doi 10.1145/3805760.3814923). Source:
<https://arxiv.org/abs/2604.03551>.

### Xu, Subramanian and Karthik 2026 — co-activity and merge replay

AIDev-pop, 33,596 Pull Requests in 2,807 repositories, December 2024 to July 2025. Under
exact temporal overlap "40.2% of all repositories" (1,129 of 2,807, CI 95% [38.4%, 42.0%])
have co-active agent Pull Request pairs and "79.4% of all pull requests submitted by
agents (26691 of 33596) are open concurrently" with another; within a ±7-day window 53.4%
and 95.0%. Only 0.5% of co-active pairs are cross-agent, in 122 repositories (4.3%); "the
top ten account for 91.4% of all raw pairs", so the authors normalise to one pair per
repository. Replaying three-way merges with `git merge-tree --write-tree` on 747 pairs
(716 evaluable): "Intra-Agent Pairs (601 evaluatable out of 625): 19.8% textual conflict
rate (119/601, 95% CI [16.8%, 23.2%]). Cross-Agent Pairs (115 evaluatable out of 122):
41.7% textual conflict rate (48/115, 95% CI [33.1%, 50.9%])." Of conflicted files 84.4%
are source code, not manifests; "approximately 42% of conflict signals are structural
(modify/delete or add/add operations)". Co-activity by agent: Devin 82.5%, Codex 80.9%,
Copilot 76.7%, Cursor 69.8%, Claude Code 39.7%, which the authors attribute to how each is
deployed. "No tracking is done for deeper build or semantic conflicts. Our results therefore
provide a conservative lower bound." The costs of the conflicts (rework, delay) are
hypothesised, not measured. Evidence type: measured. Read: full text (arXiv HTML, v2 of
7 July 2026). Source: <https://arxiv.org/abs/2607.04697>.

Read together with the pre-agent band: the intra-agent replay rate (19.8%) sits inside Brun's
17%–19% and Ghiotto's "10 to 20%", the cross-agent rate (41.7%) at the top of Zimmermann's
band and near Uber's 40% end; both agent studies count textual conflicts only, where Brun
found a further third of clean merges failing build or test.

### Practitioner proposals without measurement

"Claim-before-spawn: preventing write collisions in parallel AI coding agents" (Sagar
Thakkar, 9 September 2026) proposes that each agent declare the paths it will write before
it is spawned; it reports two live trials and that a supervisor-loop variant "showed no
improvement". Evidence type: proposal with anecdotal trials. Read: abstract only. Source:
<https://doi.org/10.5281/zenodo.22670722>. "Git Can't Handle AI Agents — Yet" (Zenodo
10.5281/zenodo.19445715, 7 April 2026) is an AI-generated podcast episode (a Gemini script
with synthetic voices), recorded here as discourse, not as a study. Read: metadata.

## What the two bodies of evidence do and do not connect

The pre-agent studies measure conflict per merge and per file, with n in the thousands of
merges, and one of them (Shihab 2012) ties branch structure to post-release failures; none
varies the number of concurrent developers as a treatment, and the only concurrency-to-
conflict curve read is Uber's slide (5% to 40%, no n stated). The agent-era studies measure
textual conflict on agent branches at large n, and one of them (Xu 2026) establishes that
concurrent agent branches are the common case on the repositories where agents are used
(79.4% of Pull Requests co-active); neither measures build or test conflict, rework time or
defects, and neither relates conflict to the number of Agent Runs open at once. The vendor
texts describe how a Worktree is prepared, isolated, applied and removed per Agent Session
or Agent Run, and Conductor and Cursor state the two ends of the choice (separate workspace
per independent landing; same workspace when the work must share a branch), but the only
numbers any vendor gives are caps and starting points — 25 worktrees (Cursor), 15
(Codex), "3-5 teammates" and "3 teammates" for 15 tasks (Anthropic), "5 to 30" `/batch`
subagents — and the only integration-order statements are bors's priority markers and
Rust's `rollup=` tags, which predate agents. Where the two lines meet is the same-file
question: Anthropic's "Since the tasks don't overlap" and "each teammate owns a different
set of files", Conductor's "agents in the same workspace can edit the same files", and
Cassandra's disjoint-footprint scheduling all address it; Leßenich 2018 is the caution that
the indicators developers reach for do not predict which merges will conflict, and Xu 2026
that 42% of the observed agent conflicts are structural (a file deleted on one side and
modified on the other, or added on both) rather than same-line edits.

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where existing notes touch it |
| --- | --- | --- | --- |
| 17% of merges textually conflict; 33% of VCS-clean merges hide build/test conflicts; mean persistence 10 days | Brun, Holmes, Ernst and Notkin 2011 | Measured, 9 systems | No counterpart |
| Conflict rate 22.75%–46.62% of CVS integrations | Zimmermann 2007 | Measured, 4 projects | No counterpart |
| 7.6%–19.3% merge conflicts; resolution days; Cassandra schedules tasks to avoid predicted conflicts | Kasi and Sarma 2013 | Measured; simulation | No counterpart |
| 12.5% of deltas by different developers to the same file within a day; parallel change predicts defects | Perry, Siy and Votta 2001 | Measured, 1 subsystem | Ownership footprints in [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss) |
| Branch activity up to +59% post-release failures (Vista); organisational mismatch beats architectural | Shihab, Bird and Zimmermann 2012 | Measured, 2 releases | Congruence line in [workspace-awareness-and-coordination.md](workspace-awareness-and-coordination.md#cataldo-wagstrom-herbsleb-and-carley-2006-and-cataldo-and-herbsleb-2008-2013--socio-technical-congruence) |
| 5.45 h/month on branching; isolation vs liveness; 8.9 days delay per edit for 0.04 conflicts | Bird and Zimmermann 2012 | Survey; what-if simulation | No counterpart |
| >94% of student developers had conflicts in 4 weeks; lack of awareness more frequent and more harmful | Estler et al. 2014 | Survey | Awareness tools in [workspace-awareness-and-coordination.md](workspace-awareness-and-coordination.md#awareness-tools-for-developers-and-how-they-were-evaluated) |
| None of 7 developer-named indicators predicts conflict frequency | Leßenich et al. 2018 | Measured (negative) | No counterpart |
| 56% have deferred a conflict; deferral halts development | Nelson et al. 2019 | Qualitative and survey | No counterpart |
| Merge at least daily; branches hours to a couple of days; <3 active branches | Fowler 2024; Hammant; DORA 2016, 2017 | Argument; survey | Batch size in [flow-wip-limits-and-constraints.md](flow-wip-limits-and-constraints.md#reinertsen-and-dora-on-batch-size--argument-and-survey) |
| Continuous merging detects 28/28 indirect conflicts before check-in vs 0/28 | Guimarães and Silva 2012 | Measured, lab | Palantír and FASTDash in [workspace-awareness-and-coordination.md](workspace-awareness-and-coordination.md#palantír-sarma-noroozi-and-van-der-hoek-2003-sarma-redmiles-and-van-der-hoek-2012) |
| Trunk advances only when a temporary integration revision passes; priority markers tune order; rollups batch by tag | Hoare 2014; rust-forge | Design; practice text | Merge queue as capacity in [review-capacity-and-volume.md](review-capacity-and-volume.md#tooling-positioned-as-capacity) |
| Merge queue: FIFO groups of 1–100, removal on failure or conflict | GitHub Docs | Product documentation | [review-capacity-and-volume.md](review-capacity-and-volume.md#tooling-positioned-as-capacity) |
| Conflict chance 5% to 40% as concurrent changes rise; serial queue does not scale; probabilistic speculation | Ananthanarayanan et al. 2019 (slides) | Measured, one company | No counterpart |
| Worktree per session/subagent; `/batch` 5–30 PRs; "Start with 3-5 teammates"; same-file edits overwrite | Claude Code Docs | Product documentation | Session mechanics in [handover-between-sessions-people-and-agents.md](handover-between-sessions-people-and-agents.md#claude-code-compaction-rewind-resume-subagents); "Worktree prepared" stage in [flow-wip-limits-and-constraints.md](flow-wip-limits-and-constraints.md#where-each-device-sits-in-the-lifecycle) |
| "3-4 git checkouts"; non-overlap assumed so no merge conflicts | Anthropic 2025 | Vendor practice text | Single-developer orchestration in [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#single-developer-orchestration-is-not-team-level-engineering) |
| 25-worktree cap; `/best-of-n` does not merge back; "as many agents as you want" | Cursor Docs | Product documentation | No counterpart |
| Worktree per chat; keeps 15; Git's one-checkout-per-branch rule | OpenAI Codex Docs | Product documentation | [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#openaicodex-specific-signs-of-the-same-fault-line) |
| "Use multiple workspaces when tasks should land independently"; same workspace can edit same files | Conductor Docs | Product documentation | No counterpart |
| Virtual branches per session "merged in any order"; "merge conflicts with yourself" | GitButler 2025 | Vendor testimonial | GitButler branch-first response in [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#2-attach-sessions-to-the-teams-existing-work-graph) |
| 4 agents, same prompt, 68% chance one succeeds; branch tracking a frustration | Khami 2025 | Testimonial | No counterpart |
| 27.67% textual conflict rate on unmerged agent PRs; rises with churn; Copilot 15.24% to Codex 31.85% | Ogenrwot and Businge 2026 | Measured | AIDev counts in [review-capacity-and-volume.md](review-capacity-and-volume.md#agentic-pull-requests-in-open-source) |
| 79.4% of agent PRs co-active; replay conflicts 19.8% intra-agent, 41.7% cross-agent; 42% structural | Xu, Subramanian and Karthik 2026 | Measured, lower bound | AIDev in [automation-as-a-team-player.md](automation-as-a-team-player.md#coding-agents-as-teammates-20252026) |
| Declare write paths before spawning; supervisor loop no improvement | Thakkar 2026 | Proposal, anecdotal | No counterpart |

"No counterpart" means no note in this directory addresses the point; it is a statement
about the notes, not about the wider literature.

## Dead ends

- <https://dl.acm.org/doi/pdf/10.1145/3302424.3303970> (Uber SubmitQueue paper): HTTP 403
  from both curl and the fetch tool; <https://www.uber.com/blog/> post on the same system:
  HTTP 406. Used the author slides and the OpenAlex abstract instead.
- <https://cacm.acm.org/> Potvin and Levenberg 2016, "Why Google stores billions of lines of
  code in a single repository": HTTP 403; the research.google abstract page was read, but the
  paper is not cited above because nothing in the abstract bears on conflict rate.
- <https://link.springer.com/> pages for Leßenich et al. 2018 and Nelson et al. 2019: bot
  challenge, and the fetch tool was redirected to `idp.springer.com`; author copies at CMU
  and epiclab.github.io were used. <https://www.cs.cmu.edu/~ckaestne/pdf/emse19.pdf> is a
  different paper (Kolesnikov et al.), not Nelson.
- <https://www.microsoft.com/en-us/research/> PDF links for Bird and Zimmermann 2012 and
  Shihab et al. 2012: HTTP 403; author copies at thomas-zimmermann.com used.
- <https://graydon2.dreamwidth.org/1597.html>: live page requires a login; Wayback `id_`
  copy used.
- <https://cursor.com/docs/agent/parallel-agents>: HTTP 404; the worktrees, CLI and
  cloud-agent pages were used instead.
- <https://www.anthropic.com/engineering/claude-code-best-practices>: now redirects to
  <https://code.claude.com/docs/en/best-practices>, which no longer carries the "3-4 git
  checkouts" text; the 1 June 2025 Wayback capture (served gzip; `--compressed` needed) was
  read.
- DBLP API: timed out; arXiv API: "Rate exceeded" twice; Semantic Scholar keyword search
  returned empty results repeatedly while its DOI endpoint worked. Crossref and OpenAlex were
  used for metadata.
- Zou et al. 2019 (QRS) and Owhadi-Kareshk et al. 2019 (ESEM): abstract only; full texts
  not pursued within budget.
- "Claim Plane" (a 2026 practitioner proposal on agent write-set coordination named in the
  Zenodo search results): no OpenAlex record with an abstract; not cited.
- No study was found that varies the number of concurrent Agent Runs on one repository and
  measures conflict, rework or defects; no vendor page read states a maximum number of
  parallel runs or an integration order for their branches.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Ananthanarayanan, S., Ardekani, M. S., Haenikel, D., Varadarajan, B., Soriano, S., Patel,
  D. and Adl-Tabatabai, A.-R. (2019). Keeping master green at scale. *Proceedings of the
  Fourteenth EuroSys Conference*, article 29. doi:10.1145/3302424.3303970. Slides:
  <https://sundaram.io/slides/eurosys19.pdf>.
- Anthropic (2025). Claude Code: Best practices for agentic coding. 18 April 2025.
  <https://web.archive.org/web/20250601id_/https://www.anthropic.com/engineering/claude-code-best-practices>.
- Anthropic (2026). Claude Code documentation: Worktrees; Subagents; Agent teams; Common
  workflows; Commands. <https://code.claude.com/docs/en/worktrees>,
  <https://code.claude.com/docs/en/sub-agents>, <https://code.claude.com/docs/en/agent-teams>,
  <https://code.claude.com/docs/en/common-workflows>,
  <https://code.claude.com/docs/en/commands>.
- Bird, C. and Zimmermann, T. (2012). Assessing the value of branches with what-if analysis.
  *Proceedings of the ACM SIGSOFT 20th International Symposium on the Foundations of Software
  Engineering (FSE '12)*, article 45. doi:10.1145/2393596.2393648.
  <https://thomas-zimmermann.com/publications/files/bird-fse-2012.pdf>.
- Brun, Y., Holmes, R., Ernst, M. D. and Notkin, D. (2011). Proactive detection of
  collaboration conflicts. *Proceedings of the 19th ACM SIGSOFT Symposium and the 13th
  European Conference on Foundations of Software Engineering (ESEC/FSE '11)*:168–178.
  doi:10.1145/2025113.2025139. <https://people.cs.umass.edu/~brun/pubs/pubs/Brun11fse.pdf>.
- Conductor (Melty Labs) (2026). Git worktrees; Parallel agents.
  <https://docs.conductor.build/concepts/git-worktrees>,
  <https://docs.conductor.build/concepts/parallel-agents>.
- Cursor (2026). Worktrees; Using the CLI; Cloud agents.
  <https://cursor.com/docs/configuration/worktrees>, <https://cursor.com/docs/cli/using>,
  <https://cursor.com/docs/background-agent>.
- DORA / Puppet (2016). 2016 State of DevOps Report.
  <https://dora.dev/research/2016/2016-state-of-devops-report.pdf>.
- DORA / Puppet (2017). 2017 State of DevOps Report.
  <https://dora.dev/research/2017/2017-state-of-devops-report.pdf>.
- Estler, H.-C., Nordio, M., Furia, C. A. and Meyer, B. (2014). Awareness and merge
  conflicts in distributed software development. *2014 IEEE 9th International Conference on
  Global Software Engineering (ICGSE)*:26–35. doi:10.1109/icgse.2014.17.
  <https://se.inf.ethz.ch/people/estler/publications/Awareness_Conflicts.pdf>.
- Fowler, M. (2024). Continuous Integration. Revised 18 January 2024.
  <https://martinfowler.com/articles/continuousIntegration.html>.
- Ghiotto, G., Murta, L., Barros, M. and van der Hoek, A. (2020). On the nature of merge
  conflicts: a study of 2,731 open source Java projects hosted by GitHub. *IEEE Transactions
  on Software Engineering* 46(8):892–915. doi:10.1109/TSE.2018.2871083.
  <https://www.ic.uff.br/~leomurta/papers/ghiotto2018.pdf>.
- GitButler (Chacon, S.) (2025). Managing multiple Claude Code sessions without git
  worktrees. <https://blog.gitbutler.com/parallel-claude-code>.
- GitHub (2026). Managing a merge queue. GitHub Docs.
  <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue>.
- Guimarães, M. L. and Silva, A. R. (2012). Improving early detection of software merge
  conflicts. *Proceedings of the 34th International Conference on Software Engineering
  (ICSE '12)*:342–352. doi:10.1109/icse.2012.6227180.
  <https://web.archive.org/web/2015id_/http://www.cs.washington.edu/education/courses/cse590n/12sp/mario.pdf>.
- Hammant, P. (2017–2020). Trunk Based Development; Short-lived feature branches.
  <https://trunkbaseddevelopment.com/>,
  <https://trunkbaseddevelopment.com/short-lived-feature-branches/>.
- Hoare, G. (2014). technicalities: "not rocket science" (the story of monotone and bors).
  <https://web.archive.org/web/2020id_/https://graydon2.dreamwidth.org/1597.html>.
- Kasi, B. K. and Sarma, A. (2013). Cassandra: proactive conflict minimization through
  optimized task scheduling. *Proceedings of the 2013 International Conference on Software
  Engineering (ICSE '13)*:732–741. doi:10.1109/ICSE.2013.6606619.
  <https://web.engr.oregonstate.edu/~sarmaa/wp-content/uploads/2020/08/2486788.2486884.pdf>.
- Khami, N. (2025). LLM codegen go brrr — parallelization with git worktrees and tmux.
  26 May 2025. <https://www.skeptrune.com/posts/git-worktrees-agents-and-tmux/>.
- Leßenich, O., Siegmund, J., Apel, S., Kästner, C. and Hunsen, C. (2018). Indicators for
  merge conflicts in the wild: survey and empirical study. *Automated Software Engineering*
  25(2):279–313. doi:10.1007/s10515-017-0227-0.
  <https://www.cs.cmu.edu/~ckaestne/pdf/jase17.pdf>.
- Nelson, N., Brindescu, C., McKee, S., Sarma, A. and Dig, D. (2019). The life-cycle of
  merge conflicts: processes, barriers, and strategies. *Empirical Software Engineering*
  24(5):2863–2906. doi:10.1007/s10664-018-9674-x.
  <https://epiclab.github.io/publications/emse19-nelson.pdf>.
- Ogenrwot, D. and Businge, J. (2026). AgenticFlict: a large-scale dataset of merge
  conflicts in AI coding agent pull requests on GitHub. *Proceedings of the 3rd ACM
  International Conference on AI-Powered Software (AIware '26)*.
  doi:10.1145/3805760.3814923. arXiv:2604.03551. <https://arxiv.org/abs/2604.03551>.
- OpenAI (2026). Worktrees. Codex documentation.
  <https://learn.chatgpt.com/docs/environments/git-worktrees>.
- Owhadi-Kareshk, M., Nadi, S. and Rubin, J. (2019). Predicting merge conflicts in
  collaborative software development. *2019 ACM/IEEE International Symposium on Empirical
  Software Engineering and Measurement (ESEM)*. arXiv:1907.06274.
  <https://arxiv.org/abs/1907.06274>.
- Perry, D. E., Siy, H. P. and Votta, L. G. (2001). Parallel changes in large-scale
  software development: an observational case study. *ACM Transactions on Software
  Engineering and Methodology* 10(3):308–337. doi:10.1145/383876.383878.
  <https://users.ece.utexas.edu/~perry/work/papers/DP-01-tosem.pdf>.
- Rust project (2026). Rollups. rust-forge.
  <https://raw.githubusercontent.com/rust-lang/rust-forge/master/src/release/rollups.md>.
- Shihab, E., Bird, C. and Zimmermann, T. (2012). The effect of branching strategies on
  software quality. *Proceedings of the ACM-IEEE International Symposium on Empirical
  Software Engineering and Measurement (ESEM '12)*:301–310. doi:10.1145/2372251.2372305.
  <https://thomas-zimmermann.com/publications/files/shihab-esem-2012.pdf>.
- Thakkar, S. (2026). Claim-before-spawn: preventing write collisions in parallel AI coding
  agents. Zenodo, 9 September 2026. doi:10.5281/zenodo.22670722.
- Xu, X., Subramanian, S. and Karthik, R. (2026). AI agent pull requests on GitHub:
  frequency, structure, and merge conflict rates. arXiv:2607.04697 (v2, 7 July 2026).
  <https://arxiv.org/abs/2607.04697>.
- Zimmermann, T. (2007). Mining workspace updates in CVS. *Fourth International Workshop on
  Mining Software Repositories (MSR '07)*. doi:10.1109/MSR.2007.22.
  <https://thomas-zimmermann.com/publications/files/zimmermann-msr-2007.pdf>.
- Zou, W., Zhang, W., Xia, X., Holmes, R. and Chen, Z. (2019). Branch use in practice: a
  large-scale empirical study of 2,923 projects on GitHub. *2019 IEEE 19th International
  Conference on Software Quality, Reliability and Security (QRS)*:306–317.
  doi:10.1109/qrs.2019.00047.
