---
status: research
date: 2026-09-15
---

# Review capacity and volume

Research date: 2026-09-15

This note documents what happens to the social stages of the software lifecycle — review,
triage, and maintenance — when coding agents raise the arrival rate of changes, and what
projects, vendors, and studies have measured or decided about it. It is a note about
*capacity*: how many changes a reviewer, a security team, or a maintainer can absorb, how
that was measured before agents, what has been measured since, and which policy texts
projects have adopted in response. It is not about whether the reviewer understands the
change; that is the subject of the rest of this directory. It is documentary: it records
what the sources found, with their evidence and limits, and maps each finding to where the
existing notes touch it. It does not evaluate fit for Dashpot or any tool. Terminal citations
are primary — the paper, the project's own policy file at a named commit, the maintainer's
own post — and every figure is reported as the source states it, with the sample and the
kind of evidence (measured, qualitative, testimonial, argument) marked. Items read only as
abstract or metadata are marked; anything recalled rather than read is marked unverified.
Where an earlier note already covers a source, this note links to it rather than repeating
it: reviewer habituation (Yu et al.) and the "same scrutiny, more time" interviews (Khojah et
al.) are in [track-hand-off-checks.md](track-hand-off-checks.md#evidence); the Hora et al.
policy census is in
[track-hand-off-checks.md](track-hand-off-checks.md#how-hora-et-al-report-enforcement); the
company blogs (PostHog, Duolingo, Ona) are in
[discourse-and-tooling-addendum.md](discourse-and-tooling-addendum.md#target-2-company-engineering-blogs-and-public-rfcs);
METR and DORA 2025 are in
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#ai-specific-evidence-20232026); the
review-time and PR-size proxies are in
[track-measurement.md](track-measurement.md#proxies-and-telemetry); and the relocated-labour
framing this evidence bears on is in
[cowan-more-work-for-mother.md](cowan-more-work-for-mother.md#mapping-to-the-existing-notes)
and the "Saved against relocated" tension of
[synthesis.md](synthesis.md#tensions-the-sources-state).

## Finding

No source measures reviewer-hours per pull request before and after agents on the same
population; what exists is a pre-agent baseline of hours per reviewer per week and a post-agent
set of latencies, counts, and shares. The baseline: Google's five-week 2016 telemetry gives a
mean of 3.2 hours a week reviewing (median 2.6) against a self-reported 6.4 hours a week in
open source, with the median Google developer authoring about 3 changes and reviewing 4 a week
([Sadowski et al. 2018](https://sback.it/publications/icse2018seip.pdf), measured plus 12
interviews; [Bosu and Carver 2013](http://amiangshu.com/papers/Bosu-ESEM-2013.pdf), survey,
n = 287); Microsoft's 911 respondents already named "hard finding time to perform all the
code reviews requested of them" as a top reviewer challenge in 2018
([MacLeod et al.](https://web.archive.org/web/20190501130459id_/https://www.michaelagreiler.com/wp-content/uploads/2019/03/Code-Reviewing-in-the-Trenches-Understanding-Challenges-Best-Practices-and-Tool-Needs.pdf),
survey). Since agents: GitHub reports 43.2 million pull requests merged a month in 2025, up
23% on 2024's 35 million, and over a million Copilot-coding-agent PRs in five months
([Octoverse 2025](https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/),
platform count); in 2,361 open-source repositories the median project received one or two
agentic PRs in three months, 75.22% had agentic-participation ratios below 0.25, only 25
projects (1%) exceeded the 36-PRs-per-participant industry line, and in 78.9% of 25,264 PRs
one person was both reviewer and committer
([Raida and Hou 2026](https://arxiv.org/abs/2607.14037), measured, full text); across
3,000 sampled repositories the share of merged agentic PRs with no human review fell from over
50% in mid-2025 to roughly 12% by February 2026 against a stable human rate of about 14%,
median time-to-merge for agentic PRs rose from about 20 minutes to 2–3 hours, and the authors
say a finding's "direction can reverse under defensible analysis choices" and that their
trend "runs opposite to the within-reviewer habituation reported by Yu et al."
([Agarwal et al. 2026](https://arxiv.org/abs/2607.07980), measured plus 3,100 coded
opinions). Vendor telemetry reports the opposite sign for review time: Faros puts PR review
time up 91% and PR size up 154% on high-adoption teams (10,000+ developers, 1,255 teams) in
2025, and median time in review up 441.5%, median time to first review up 156.6%, and PRs
merged without any review up 31.3% in 2026 (22,000 developers, 4,000+ teams, no control)
([Faros 2025](https://www.faros.ai/blog/ai-software-engineering);
[Faros 2026](https://www.faros.ai/blog/ai-acceleration-whiplash-takeaways)); Uplevel's
~800-developer Copilot comparison found no significant change in PR throughput or cycle time
([Uplevel 2024](https://uplevelteam.com/blog/ai-for-developer-productivity), vendor). DORA's
2024 survey (about 3,000 respondents) estimated that a 25% increase in AI adoption came with
a 1.5% reduction in delivery throughput and a 7.2% reduction in delivery stability, alongside
3.1% faster code reviews, adding that "faster code reviews and approvals do not equate to
better and more thorough code review processes"; the 2025 survey (nearly 5,000) reports
throughput now improving while instability still rises, and warns against "using AI to
simply generate more code that will only exacerbate the bottleneck"
([DORA 2024](https://dora.dev/research/2024/dora-report/2024-dora-accelerate-state-of-devops-report.pdf);
[DORA 2025](https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf),
survey, full text). On the triage side the curl project counted 415 security reports with
64 confirmed by January 2024, then about two submissions a week in 2025 of which about 20%
were AI slop and about 5% genuine (down from over 15% in earlier years), each report engaging
"3-4 persons" for "30 minutes, sometimes up to an hour or three", and ended its bug bounty on
2026-01-31 ([Stenberg, 2024-01-02](https://daniel.haxx.se/blog/2024/01/02/the-i-in-llm-stands-for-intelligence/);
[2025-07-14](https://daniel.haxx.se/blog/2025/07/14/death-by-a-thousand-slops/);
[2026-01-26](https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/),
maintainer counts and testimony); the same project then received over four hundred suspected
issues from two AI-analyzer users in two months and merged about 50 bugfixes from the first
list ([Stenberg, 2025-10-10](https://daniel.haxx.se/blog/2025/10/10/a-new-breed-of-analyzers/)).
Of the policies read in full, none sets a numeric WIP or rate limit at the project level:
Gentoo (2024-04-14), NetBSD, and QEMU (2025-06-16) forbid or decline AI-generated
contributions, Gentoo citing "an unfair human effort from developers and users to review
contributions" ([Gentoo](https://wiki.gentoo.org/wiki/Project:Council/AI_policy)); the Linux
kernel requires an `Assisted-by:` tag and, since 2026-08-02, a bug-finding procedure whose
step 8 says "maintainers currently waste too much time analyzing unverified reports and
untested fixes"
([coding-assistants.rst](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/Documentation/process/coding-assistants.rst)),
with 1,111 of 16,418 commits in 7.2 carrying the tag
([LWN 1088776](https://lwn.net/Articles/1088776/)); the Rust compiler team resolved that
"Reviewer time and effort are very precious and limited resources" and that reviewers may
close burdensome PRs without relitigating
([rust-lang/compiler-team#893](https://github.com/rust-lang/compiler-team/issues/893)); LLVM
requires "a human in the loop", bans agents that act "without human approval", says the tools
shift "effort from the implementor to the reviewer", and dropped a draft 150-line cap
([LLVM AI Tool Use Policy](https://llvm.org/docs/AIToolPolicy.html);
[RFC 88476](https://discourse.llvm.org/t/rfc-llvm-ai-tool-policy-start-small-no-slop/88476));
Debian's 2026 General Resolution chose "Responsible Use of Generative AI", which neither
endorses nor prohibits the tools and routes "mass bug filing or patch submission" through
prior discussion, over a Social-Contract ban that drew 144 votes against 257 for none of the
above ([Debian GR 2026-002](https://www.debian.org/vote/2026/vote_002)). The only numeric
per-contributor limit found is kilocode's "open no more than three PRs at a time, especially
if you are a new contributor", and the only hard stop is pocketbase's "PRs are temporary
disabled and only existing collaborators can open a PR", both among the 3 of 281 policies
(1.6%) (corrected 2026-09-15: Hora et al. Table 4 counts 188 AI-slop countermeasures, not 281 policies; "Limit the number of PRs" is 3 of those 188 (1.6%), i.e. about 1.1% of the 281 policies) that Hora et al. class as "Limit the number of PRs"
([kilocode CONTRIBUTING.md](https://github.com/Kilo-Org/kilocode/blob/abd24c7223df8cd8df203d9b457e5a7bcd9147d2/CONTRIBUTING.md);
[pocketbase CONTRIBUTING.md](https://github.com/pocketbase/pocketbase/blob/089ca8ae412a1dbe29d2ae90d74f3866429d9c52/CONTRIBUTING.md);
[Hora et al.](https://arxiv.org/abs/2609.07542)). The tooling sold as capacity — GitHub's
merge queue, CodeRabbit's "Prioritize your PR flood", Cursor's Bugbot — automates the merge
or the first pass and adds no human reviewer
([merge queue docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue);
[CodeRabbit](https://www.coderabbit.ai/); [Bugbot](https://cursor.com/bugbot), vendor); the
kernel's Sashiko reviewer is the one capacity addition with a reported accuracy (about 85%
true positives on 1,500 threads, per its author) and a recorded dispute over whether it
"would increase the workload on the already overworked memory-management maintainers"
([LWN 1073583](https://lwn.net/Articles/1073583/); [LWN 1064830](https://lwn.net/Articles/1064830/)).
Tidelift's 2024 survey of over 400 maintainers, 60% unpaid, found 45% expecting AI coding
tools to make their work harder
([Tidelift 2024](https://web.archive.org/web/20241031114640id_/https://blog.tidelift.com/ai-based-coding-tools-maintainers-have-some-valid-concerns),
survey). The framing practitioners reach for is Jevons's — "Reviewer throughput grows
linearly with headcount. AI generation throughput grows multiplicatively per developer"
(Agarwal et al., G2802, testimonial) — which Alcott's 2005 review states as efficiency gains
that "rebound or even backfire"
([Alcott 2005](https://doi.org/10.1016/j.ecolecon.2005.03.020), abstract only).

## Baseline: review capacity before agents

The three seed sources for "reviewer load before agents" measure different things — hours
per reviewer per week, changes per reviewer per week, self-reported difficulty — and none
measures hours per change.

### Sadowski, Söderberg, Church, Sipko, and Bacchelli 2018 — Google

"Modern Code Review: A Case Study at Google" (ICSE-SEIP 2018; full text read from the
author's copy at [sback.it](https://sback.it/publications/icse2018seip.pdf)) combines
telemetry with 12 interviews. In frequency terms "the median developer authors about 3
changes a week, and 80 percent of authors make fewer than 7 changes a week. Similarly, the
median for changes reviewed by developers per week is 4, and 80 percent of reviewers review
fewer than 10 changes a week." Changes are small: 35% touch a single file, about 90% fewer
than 10 files, and the median change is 24 lines. Most changes have one reviewer (fewer than
25% have more than one). Latency: median initial feedback under an hour for small changes and
about five hours for very large ones; overall median latency under four hours, which the
paper contrasts with Rigby and Bird's 14.7–19.8 hours in other projects. Time spent: summing
review sessions (interactions no more than 10 minutes apart) over "the five weeks that started
in October 2016", "developers spend an average of 3.2 (median 2.6 hours a week) reviewing
changes. This is low compared to the 6.4 hours/week of self-reported time for OSS projects
[10]." The paper's Finding 5 is that "code review at Google still faces breakdowns", linked to
"the complexity of the interactions" rather than to volume. Evidence type: measured (telemetry)
and qualitative (interviews). The 3.2-hour figure is per reviewer per week, not per change.

### Bosu and Carver 2013 — open source self-report

"Impact of Peer Code Review on Peer Impression Formation: A Survey" (ESEM 2013, pp. 133–142,
[doi 10.1109/esem.2013.23](https://doi.org/10.1109/esem.2013.23); full text read from the
author's copy at [amiangshu.com](http://amiangshu.com/papers/Bosu-ESEM-2013.pdf), via the
Wayback Machine) is the source of Sadowski's 6.4-hour comparison. The survey ran in
February–March 2013; 287 complete responses, a response rate of about 15.8% (287/1815). On
"how many hours per week, on average, do you spend" reviewing, the mean is 6.4 hours (σ =
7.1), and respondents reviewed code from a mean of 2.1 peers a week. Evidence type: survey
self-report; the standard deviation exceeds the mean, so the distribution is wide. The paper's
subject is impression formation, not load; the hours figure is descriptive.

### MacLeod, Greiler, Storey, Bird, and Czerwonka 2018 — Microsoft

"Code Reviewing in the Trenches: Challenges and Best Practices" (IEEE Software 35(4):34–42,
[doi 10.1109/ms.2017.265100500](https://doi.org/10.1109/ms.2017.265100500); full text read
from the [Wayback copy of the author's PDF](https://web.archive.org/web/20190501130459id_/https://www.michaelagreiler.com/wp-content/uploads/2019/03/Code-Reviewing-in-the-Trenches-Understanding-Challenges-Best-Practices-and-Tool-Needs.pdf)).
"The survey was distributed to 4,300 developers and received 911 responses." For authors the
top challenge is receiving "feedback in a timely manner"; for reviewers, "Our code reviewers
said they struggle with large reviews. Participants discussed how it's hard finding time to
perform all the code reviews requested of them, as well as understanding the code's purpose,
the motivations for" the change. One participant (P13) describes a large review as a "big
incomprehensible mess". Evidence type: survey and interview, qualitative; no hours.

### What the baseline does not give

None of the three reports reviewer effort per change, and none was designed to detect a
change in arrival rate. Sadowski's per-week hours and per-week counts come from different
populations and the paper does not divide one by the other, so this note reports no
minutes-per-change figure from it. The later notes in this directory take McIntosh et al.'s
"faster than 200 lines per hour" threshold as the nearest pre-agent rate norm
([track-measurement.md](track-measurement.md#proxies-and-telemetry)).

## Arrival rate: what has been measured since agents

### Platform-scale counts

GitHub's Octoverse 2025 report (2025-10-28; full page read at
[github.blog](https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/))
gives 2024 and 2025 monthly averages: issues closed ≈ 3.4M → 4.25M; pull requests merged
35M → 43.2M (+23% year on year); code pushes 65M → 82.19M; a record 518.7M pull requests
merged in the year (+29%) and "nearly 1 billion commits in 2025 (+25.1% YoY)". It attributes
the acceleration to "the preview of Copilot coding agent in March and the introduction of
Copilot code review in April" and reports "1+ million pull requests that were created between
May 2025 and September 2025" by the coding agent, "skewed toward repositories with more stars,
larger size, and greater age". On the maintenance side: Dependabot "Monthly openings have
since settled near the 3-4M range, but merges hover around 1M. Only ~1 in 3 fixes ships
within the same month it's proposed", and "Automation raises fixes quickly, but merges still
stall when approval depends on humans or policy." Evidence type: platform counts; no review
effort, no per-repository denominator for the coding-agent figure.

Li, Zhang, and Hassan's AIDev dataset (arXiv:2507.15003; abstract read at
[arXiv](https://arxiv.org/abs/2507.15003)) is the corpus most of the agentic-PR studies below
draw on: 456,000 PRs from 61,000 repositories and 47,000 developers, with the abstract's
single-developer example that "one developer submitted as many PRs in three days as they had
in three years", and the finding that agent PRs are accepted less frequently. Evidence type:
measured; abstract only.

### Agentic pull requests in open source

**Raida and Hou 2026**, "How Do Open-Source Projects Adopt Agentic Coding Tools? A Study of
Participation, Productivity, and Human Oversight" (arXiv:2607.14037, v2 revised 2026-07-16;
full text read from the PDF at [arXiv](https://arxiv.org/abs/2607.14037)). Sample: 25,264
agentic PRs (Copilot, Codex, Claude Code) in 2,361 repositories with at least 100 stars
("AIDev-pop"), merged or closed, May–July 2025. Participation: the median repository received
one or two agentic PRs; 42.27% of projects have an agentic participation ratio below 0.05,
70.18% below 0.20, and 75.22% below 0.25; participation differs by project size
(Kruskal-Wallis H = 1211.79, η² ≈ 61.6%). Productivity: against "36 PRs per participant
during the three-month" period, an "industry-reported estimate" (reference [1], Worklytics
2025), "most projects fall below the benchmark line. Only 25 of" 2,361 (about 1%) exceed it.
Oversight: in 19,488 PRs (78.9%) one person was sole reviewer and committer; 2,476 (9.8%)
had one reviewer and no committer; single-human patterns total 88.7%, multi-human 11.3% —
the figures the chat-centric note records
([chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#bottom-line)).
The abstract says the results "highlight the importance of human review capacity and project
governance". The stated limitation that matters here: the productivity proxy "does not
account for differences in PR size, complexity, quality, or review effort". Evidence type:
measured; no reviewer time.

**Watanabe et al.** (arXiv:2509.14745 v3; abstract read at
[arXiv](https://arxiv.org/abs/2509.14745)): 567 Claude Code PRs across 157 projects, 83.8%
merged, 54.9% merged without modification. **Ehsani et al.** (arXiv:2601.15195; abstract at
[arXiv](https://arxiv.org/abs/2601.15195)): 33,000 agent PRs from five agents; not-merged
PRs are larger, touch more files, and fail CI more; a 600-PR qualitative sample names "lack
of meaningful reviewer engagement" and "duplicate PRs" among rejection reasons. **Yoshioka
et al.** (arXiv:2601.18749; abstract at [arXiv](https://arxiv.org/abs/2601.18749)): 40,214
PRs, 64 features; submitter attributes dominate merge outcomes. All measured; abstract only.

**Peralta et al.** (arXiv:2605.22534, 2026-05-21; abstract at
[arXiv](https://arxiv.org/abs/2605.22534)): from 11,048 closed agentic PRs, 9,799
human-reviewed and 717 manually inspected; only 35.7% of rejections are a clear agent
failure, 31.2% workflow constraints, 33.1% no rationale; 15.4% of merged PRs needed explicit
reviewer involvement and 5.5% show no interaction trace; Copilot and Devin PRs are
"reviewer-mediated", Codex and Cursor PRs show minimal interaction. Measured plus manual
coding; abstract.

**Asdaque et al.**, MSR 2026 Mining Challenge (arXiv:2602.23905, 2026-02-27; abstract at
[arXiv](https://arxiv.org/abs/2602.23905)): 22,953 PRs from 1,719 "vibe coders";
low-experience contributors' PRs have 2.15× the commits, 1.47× the files, 4.52× the review
comments, 31% lower acceptance, and stay open 5.16× longer — "shifting verification burden
onto reviewers" "without increasing review capacity". Measured; abstract. This is the closest
any study comes to a per-PR reviewer-effort measure, and its unit is comments, not hours.

### Vendor telemetry

**Faros AI 2025**, "The AI Productivity Paradox" (2025-07-23; report page read at
[faros.ai](https://www.faros.ai/blog/ai-software-engineering)): telemetry from "over 10,000
developers across 1,255 teams". "Developers on teams with high AI adoption complete 21% more
tasks and merge 98% more pull requests, but PR review time increases 91%, revealing a
critical bottleneck: human approval." "AI adoption is consistently associated with a 9%
increase in bugs per developer and a 154% increase in average PR size." "Any correlation
between AI adoption and key performance metrics evaporates at the company level" — "Across
overall throughput, DORA metrics, and quality KPIs, the gains observed in team behavior do
not scale when aggregated", which the page attributes to "downstream bottlenecks". Evidence
type: vendor telemetry, high- versus low-adoption teams, no randomisation.

**Faros AI 2026**, "The AI Engineering Report 2026: The Acceleration Whiplash", ten-takeaways
page (2026-04-12; read at
[faros.ai](https://www.faros.ai/blog/ai-acceleration-whiplash-takeaways); the full report is
behind a form): "Two years of telemetry. 22,000 developers. More than 4,000 teams",
comparing lowest- and highest-adoption periods. Takeaway 7, "the senior engineer tax":
"Median time to first PR review is up 156.6%. Average time spent in code review is up 199.6%.
Median time in review is up 441.5%. The engineers with the deepest knowledge of the system
are spending their most valuable hours unraveling plausible-looking code". Takeaway 8:
"Pull requests merged without any review, human or agentic, are up 31.3%. We do not believe
this reflects a deliberate decision to bypass oversight. The more likely explanation is that
reviewers cannot keep pace with the volume". Other figures on the page: tasks per developer
+33.7%, PR merge rate +16.2%, code churn +861%, incidents per PR +242.7%, bugs per developer
+54%, stalled tasks +26%. Takeaway 9 disputes DORA 2025's survey-based conclusion that strong
foundations amplify AI's benefits: "Strong engineering foundations do not protect you. Two
years of telemetry says so." Evidence type: vendor telemetry, before/after within customers,
no control; the percentages are the vendor's own aggregates and the underlying counts are not
on the page. Note that "time in review" here is elapsed time, not reviewer effort.

**Uplevel 2024**, "AI for Developer Productivity: What Now?" (blog, 2024-10-18; read at
[uplevelteam.com](https://uplevelteam.com/blog/ai-for-developer-productivity); report
gated): from "a sample of nearly 800 developers and objective metrics, such as cycle time,
PR throughput, bug rate, and extended working hours", "Copilot access provided no
significant change in efficiency metrics"; "The group using Copilot introduced 41% more
bugs"; burnout risk fell 28% without Copilot against 17% with. Evidence type: vendor
telemetry of pre-agent Copilot completion, so it measures no rise in arrival rate at all.

### Survey-based estimates

**DORA 2024**, *Accelerate State of DevOps* (full PDF read at
[dora.dev](https://dora.dev/research/2024/dora-report/2024-dora-accelerate-state-of-devops-report.pdf);
about 3,000 respondents that year, 39,000 cumulative). The seed's numbers are verified
against the text: "our findings indicate that AI adoption is negatively impacting software
delivery performance. We see that the effect on delivery throughput is small, but likely
negative (an estimated 1.5% reduction for every 25% increase in AI adoption). The negative
impact on delivery stability is larger (an estimated 7.2% reduction for every 25% increase in
AI adoption)" (Figure 10, with 89% uncertainty intervals). The same model gives, for a 25%
increase in adoption, code review speed +3.1%, approval speed +1.3%, documentation quality
+7.5%, code quality +3.4%, code complexity −1.8%, burnout −0.6%, and toil +0.4%. The report's
own gloss: "faster code reviews and approvals do not equate to better and more thorough code
review processes and approval processes. It is possible that we're gaining speed through an
over-reliance on AI"; and its hypothesis for the stability result: "since AI allows
respondents to produce a much greater amount of code in the same amount of time, it is
possible, even likely, that changelists are growing in size. DORA has consistently shown that
larger changes are slower and more prone to creating instability." Evidence type: survey with
structural-equation modelling; the review-speed figures are self-reports.

**DORA 2025**, *State of AI-assisted Software Development* (full PDF read at
[services.google.com](https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf);
"survey responses from nearly 5,000 technology professionals" plus "more than 100 hours of
qualitative data"; survey fielded June 13 – July 21, 2025). "AI adoption now improves
software delivery throughput, a key shift from last year. However, it still increases delivery
instability. This suggests that while teams are adapting for speed, their underlying systems
have not yet evolved to safely manage AI-accelerated development." Adoption: "The majority of
survey respondents (90%) use AI as part of their work and believe (more than 80%) it has
increased their productivity. Yet a notable portion (30%) currently report little to no trust
in the code generated by AI". The 2025 report gives standardized coefficients (Figure 28)
rather than percentages, and restates 2024's stability figure as a "7.2% increase in software
delivery instability". Its value-stream passage is the report's one direct statement on
review capacity: "a team may discover, through mapping, that code reviews are a significant
bottleneck. With this insight, they can decide to apply AI to improve the code review
process, rather than using AI to simply generate more code that will only exacerbate the
bottleneck." Evidence type: survey; the report's framing of AI as "an amplifier" is
argument. The phrase "verification tax", which
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#surveys-trust-and-verification-not-comprehension)
attributes to DORA, does not occur in this PDF (see Corrections proposed).

### The one controlled experiment

METR's randomized trial (arXiv:2507.09089; full text read from the PDF at
[arXiv](https://arxiv.org/abs/2507.09089)) is summarised, with its 2026-02-24 update, in
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#ai-specific-evidence-20232026). What
bears on review load, as far as the paper itself goes: developers "self-report how long they
spend working on each issue before and after PR review"; "We observe a statistically
insignificant difference in the mean post-review implementation time" (9 minutes
AI-disallowed versus 15 AI-allowed); from 143 hours of labelled screen recordings,
"developers spend approximately 9% of their time reviewing and cleaning AI generated"
output; 75% report "that they read every line of AI generated code". The time the
maintainers who reviewed the 246 PRs spent was not measured. Evidence type: RCT, n = 16
developers; the review-side figures are self-report and screen-labelling.

### Agarwal, Miller, Kästner, and Vasilescu: opinion and observation together

"3100 Opinions on Code Review in an AI World" (arXiv:2607.07980 v1, 2026-07-08; full text
read from the PDF at [arXiv](https://arxiv.org/abs/2607.07980)). The
[discourse addendum](discourse-and-tooling-addendum.md#target-2-company-engineering-blogs-and-public-rfcs)
records its abstract; the body is the most direct treatment of capacity found in this pass.
Method: 38,709 collected documents, 3,100 coded, yielding 26 constructs and 67 relationships;
plus an observational study of 16,317 eligible repositories with 3,000 sampled by strata.

Practitioner claims (testimonial, quoted by the paper's document identifiers): coding agents
"increase code generation speed by 10 to 25 times without proportionally increasing review
capacity" (G2394); "The number of reviewers hasn't changed, and neither has the human
attention available" (G2991); "Reviewer throughput grows linearly with headcount. AI
generation throughput grows multiplicatively per developer" (G2802); "if your team generates
more PRs than your reviewers can thoughtfully evaluate, you either add an automated
first-pass layer or you accept that human review becomes performative" (G3088); "The thing
nobody warned me about is the review fatigue. After a few hours reading through AI-generated
code, I'm more drained than I'd be after twice as long actually writing code" (G439). The
paper's proposition P3: "Higher review load increases relative time spent reviewing, which
decreases review motivation." Its summary of the premise: agents "decouple the rate at which
code is produced from the rate at which it can be reviewed", so that "without an increase in
the review budget, this puts pressure on review efficiency to review more code in the same
time."

Observational results (measured): agentic PRs are merged faster and discussed less; review
"by the PR author, alone or alongside a bot, accounts for 40.1% of agentic PRs versus 21.5%
of human PRs", single-other-person review 4.6% versus 18.7%, multi-person review 20.8% versus
29.3%. Over time "the overall agentic no-review rate falls from over 50% early in the window
to roughly 12% by February 2026, approaching the stable human rate of about 14%", while "the
median per-project no-review rate is near 0% for both author groups in every month"; per-PR
type, agentic no-review rates are "test 69%, refactor 41%, bug fix 25%". "In every month of
the observation period, the median time to merge is lower for agentic PRs than for human
PRs"; "the agentic median climbs from minutes early in the window (roughly 20 minutes in May
2025) to 2–3 hours by early 2026". The authors' own qualification: "a finding's direction can
reverse under defensible analysis choices", the example being whether the invoking developer
counts as an independent reviewer; and, on the trend, "This runs opposite to the
within-reviewer habituation reported by Yu et al. [26], where oversight weakens over time as
approval rises and commenting falls. On the basic question of whether human oversight is
consolidating or eroding, studies disagree." Limitations stated: observational, no
non-adopting control.

### Reviewer-hours per pull request: what was looked for

Searched for a measured reviewer-hours-per-PR trend: the three baselines; DORA, Faros, and
Uplevel; METR; the seven agentic-PR studies; Agarwal et al.'s observational data. Found:
hours per reviewer per week (Sadowski 3.2 mean; Bosu 6.4 mean) with no post-agent
counterpart on the same population; elapsed review time (Faros +91%, +156.6% to +441.5%;
Agarwal 20 minutes → 2–3 hours; DORA +3.1% self-reported speed), which conflates waiting with
working; review comments per PR (Asdaque 4.52×); and reviewer self-reports of fatigue
(Agarwal G439; Khojah et al. in [track-hand-off-checks.md](track-hand-off-checks.md#evidence)).
No source read in this pass measures reviewer effort per change, before and after, on one
population.

## Security triage: the curl record

curl is the one seed case with a multi-year count of arrivals, outcomes, and a stated
per-report cost, all from the maintainer; the evidence type throughout is maintainer counts
and testimony.

### The reports as counted

"The I in LLM stands for intelligence" (2024-01-02; full text read at
[daniel.haxx.se](https://daniel.haxx.se/blog/2024/01/02/the-i-in-llm-stands-for-intelligence/)):
"Our bug bounty has resulted in over 70,000 USD paid in rewards so far. We have received 415
vulnerability reports. Out of those, 64 were ultimately confirmed security problems. 77 of
the report were informative, meaning they typically were bugs or similar. Making 66% of the
reports neither a security issue nor a normal bug."

"Death by a thousand slops" (2025-07-14; full text read at
[daniel.haxx.se](https://daniel.haxx.se/blog/2025/07/14/death-by-a-thousand-slops/)): "The
general trend so far in 2025 has been way more AI slop than ever before (about 20% of all
submissions) as we have averaged in about two security report submissions per week. In early
July, about 5% of the submissions in 2025 had turned out to be genuine vulnerabilities."
Programme to date: "81 of them to be exact, with over 90,000 USD paid in awards." Cost per
report: "The curl security team consists of seven team members. I encourage the others to
also chime in to back me up (so that we act right in each case). Every report thus engages
3-4 persons. Perhaps for 30 minutes, sometimes up to an hour or three. Each." "My fellows
however are not full time on curl. They might only have three hours per week for curl. Not
to mention the emotional toll it takes to deal with these mind-numbing stupidities. Times
eight the last week alone." On the platform's rate control: lowering a reporter's HackerOne
reputation "is only really a mild 'threat' to experienced HackerOne participants. For new
users on the platform that is mostly a pointless exercise as they can just create a new
account next week. Banning those users is similarly a rather toothless threat." A submission
fee is listed and rejected as "a rather hostile way for an Open Source project".

"The end of the curl bug-bounty" (2026-01-26; full text read at
[daniel.haxx.se](https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/)):
"There is no longer a curl bug-bounty program. It officially stops on January 31, 2026."
Totals: "87 confirmed vulnerabilities and over 100,000 USD paid as rewards". "Previous years
we have had a rate of somewhere north of 15% of the submissions ending up confirmed
vulnerabilities. Starting 2025, the confirmed-rate plummeted to below 5%. Not even one in
twenty was real." Decisions: no rewards; leave HackerOne; "We refer everyone to submit
suspected curl security problems on GitHub using their Private vulnerability reporting
feature. We continue to immediately ban and publicly ridicule everyone who submits AI slop
to the project." On pull requests the post is explicit that the flood had not arrived: "We
hear about projects having problems with low-quality AI slop submissions on GitHub as well,
in the form of issues and pull-requests, but for curl we have not (yet) seen this". The
FOSDEM 2026 closing keynote, "Open Source security in spite of AI" (2026-02-03; post read at
[daniel.haxx.se](https://daniel.haxx.se/blog/2026/02/03/open-source-security-in-spite-of-ai/)),
carries the same account; the 59 slides were not read.

### The policy texts as enforced

The repository's own files, read at `master` on 2026-09-15 with commit history from the
GitHub API:

- `docs/CONTRIBUTE.md`, section "On AI use in curl" (added 2025-05-12, commit a9aafbea;
  [raw](https://raw.githubusercontent.com/curl/curl/master/docs/CONTRIBUTE.md)). For
  security reports: "Fake and otherwise made up security problems effectively prevent us from
  doing real project work and make us waste time and resources." "We ban users immediately
  who submit made up fake reports to the project." For pull requests: "A basic rule of thumb
  is that if someone can spot that the contribution was made with the help of AI, you have
  more work to do." "We can accept code written with the help of AI into the project, but the
  code must still follow coding standards, be written clearly, be documented, feature test
  cases". A translation clause asks contributors to mention machine translation so that
  "maintainers [do not] wrongly dismiss translated texts as AI slop".
- `docs/BUG-BOUNTY.md` (commit ca7ef4b8, 2026-01-22, "we stop the bug-bounty end of Jan
  2026"; ed7bf43a, 2026-03-10, "minor rephrase to say there is no bug bounty";
  [raw](https://raw.githubusercontent.com/curl/curl/master/docs/BUG-BOUNTY.md)) now reads:
  "The curl project does not offer any rewards for reported bugs or vulnerabilities. We do
  not aid security researchers to get such rewards for curl problems from other sources. A
  bug bounty gives people too strong incentives to find and make up 'problems' in bad faith
  that cause overload and abuse. We still appreciate and value valid vulnerability reports."

What the policy enforces, then, is a ban on the person (for fake reports), removal of the
reward, and a change of intake channel; it sets no rate limit and no reviewer quota. The
only rate mechanism named in the record is HackerOne's reputation score, which the maintainer
calls "toothless".

### The second wave: AI analyzers as bug sources

"A new breed of analyzers" (2025-10-10; full text read at
[daniel.haxx.se](https://daniel.haxx.se/blog/2025/10/10/a-new-breed-of-analyzers/)) records
the opposite arrival: valid reports at volume. Google's Big Sleep reported the vulnerability
published as CVE-2025-9086 on 2025-08-11; Joshua Rogers, "mostly done with the help of
ZeroPath", sent "over two hundred new potential problems", then "a second list with 47
additional issues", then "a third list with yet another 158 additional potential problems";
Stanislav Fort of Aisle sent "two lists with a total of around twenty possible issues". "Out
of that initial list, we merged about 50 separately identifiable bugfixes." "The total amount
of suspected issues submitted by these two gentlemen are now at over four hundred. A fair
pile of work for us curl maintainers!" The ordinary rate for comparison: "we tend to get 2-3
every week". Two maintainers ("primarily Stefan Eissing and myself") worked through the first
list "within only a couple of days". The post judges the false-positive rate "low and quite
manageable" and the issues "of high quality". Evidence type: maintainer counts; the lists
themselves are private.

## Project policies and what they enforce

The texts below were read in full from the project's own source unless marked. Hora et
al.'s census, tabulated in
[track-hand-off-checks.md](track-hand-off-checks.md#how-hora-et-al-report-enforcement), is
the frame: of 281 policies, "Limit the number of PRs" appears in 3 (1.6%) (corrected 2026-09-15: Hora et al. Table 4 counts 188 AI-slop countermeasures, not 281 policies; "Limit the number of PRs" is 3 of those 188 (1.6%), i.e. about 1.1% of the 281 policies), and the paper
finds no policy enforced by tooling.

### Bans: Gentoo, NetBSD, QEMU

**Gentoo** ([Project:Council/AI_policy](https://wiki.gentoo.org/wiki/Project:Council/AI_policy),
full text): "The Gentoo Council has voted on 2024-04-14 on the following policy: It is
expressly forbidden to contribute to Gentoo any content that has been created with the
assistance of Natural Language Processing artificial intelligence tools. This motion can be
revisited, should a case be made for such a revision." The rationale's quality item is the
one about capacity: the tools "pose both the risk of lowering the quality of Gentoo projects,
and of requiring an unfair human effort from developers and users to review contributions and
detect the mistakes resulting from the use of AI." No detection method is stated.

**NetBSD** ([commit guidelines](https://www.netbsd.org/developers/commit-guidelines.html),
full text): code generated by a large language model "is presumed to be tainted code, and
must not be committed without prior written approval by core", under the existing "Do not
commit tainted code to the repository" rule. Adoption date not on the page (May 2024 from
memory; unverified). Enforcement: written approval by core for each exception.

**QEMU** (`docs/devel/code-provenance.rst`, read from
[gitlab.com](https://gitlab.com/qemu-project/qemu/-/raw/master/docs/devel/code-provenance.rst);
commit 3d40db0e, 2025-06-16, "define policy forbidding use of AI code generators", refined
2025-09-22): "Current QEMU project policy is to DECLINE any contributions which are believed
to include or derive from AI generated content. This includes ChatGPT, Claude, Copilot, Llama
and similar tools." The rationale is the Developer Certificate of Origin, not review
capacity; an exceptions process exists with no exceptions yet listed.

### Attribution and procedure: the Linux kernel

`Documentation/process/coding-assistants.rst` (full text read from
[git.kernel.org](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/Documentation/process/coding-assistants.rst),
history from the same tree): added by Sasha Levin in commit 78d979db (2025-12-23) "per the
consensus reached at the 2025 Maintainers Summit"; Christian Brauner's 816d9992 (2026-07-01)
reduced the tag to `Assisted-by: LLM` because naming the model "provides free advertising to
proprietary software companies while adding little or no useful information"; Willy Tarreau's
3d7c44f7 (2026-08-02) added "Procedure for finding and fixing bugs", merged for 7.3. The
procedure's capacity clauses: step 3, a non-trivial bug needs a reproducer, "Lacking it may
cause the report to be ignored, as many unverified bug reports sent to maintainers happen to
be invalid"; step 4, "an AI assistant able to find a bug is able to fix it" and must; step 8,
"Indicate what could not be done. If the fix could not be built or tested, or if no
reproducer could be produced, say so explicitly: maintainers currently waste too much time
analyzing unverified reports and untested fixes"; step 9, "the assistant must never send
anything itself". What is enforced is a tag and a format, and the tag is not enforced by
tooling — Levin said at the Summit he "would not make an effort to enforce the rule"
([LWN 1049830](https://lwn.net/Articles/1049830/), Corbet, 2025-12-11, full text). The same
report carries Torvalds's expectation, not a measurement: "developers have long been
complaining about a lack of code review; LLMs may just solve that problem", and "Once these
systems start submitting kernel code, we will truly need automated systems to review all
that code"; Alexei Starovoitov's account of Meta's tools (about 60% good reviews, 20% with
some good points, under 20% false positives) is testimonial. Counts: "As of 7.2-rc4, over
1,200 commits carry Assisted-by tags" alongside "a significant stream of machine-generated
patches that do not carry that tag" ([LWN 1083275](https://lwn.net/Articles/1083275/),
2026-07-21); for 7.2, 16,418 non-merge commits from 2,652 developers, 1,111 with Assisted-by
(under 7%, against 301 in 7.1), 252 with Reported-by crediting Sashiko, and 4,830 with Fixes
tags, "a dramatic rise" ([LWN 1088776](https://lwn.net/Articles/1088776/), 2026-08-17);
first-time contributors for 7.0 up "roughly 50%" ([LWN 1073583](https://lwn.net/Articles/1073583/)).
Evidence type: tag counts from git history as LWN reports them.

### Reviewer empowerment: the Rust compiler team and LLVM

**Rust**, [compiler-team#893](https://github.com/rust-lang/compiler-team/issues/893)
("Policy: Empower reviewers to reject burdensome PRs", opened 2025-06-27 by jieyouxu; the
major change proposal was accepted 2025-07-07 and the issue closed 2025-08-22; full text via
the GitHub API): "Reviewer time and effort are very precious and limited resources. However,
there are Pull Requests (PRs) with certain qualities that place undue work on reviewers. We
are proposing a policy that reviewers can use as justification for rejecting a PR without
them having to excessively defend their position or relitigate the reasons for closing." The
motivation: generative AI has "significantly lowered the effort to produce
'plausibly-looking' contributions that are entirely inadmissible". Reviewers may ask for
rework, edit out verbose descriptions, or close. What is enforced is a reviewer's discretion
to stop; no limit on arrivals.

**LLVM**, [AI Tool Use Policy](https://llvm.org/docs/AIToolPolicy.html) (full text; adopted
from [RFC 88476](https://discourse.llvm.org/t/rfc-llvm-ai-tool-policy-start-small-no-slop/88476),
opened 2025-10-01 by rnk, 44 posts, read as JSON): "contributors can use whatever tools they
would like to craft their contributions, but there must be a human in the loop."
"Contributors should be sufficiently confident that the contribution is high enough quality
that asking for a review is a good use of scarce maintainer time". "An important implication
of this policy is that it bans agents that take action in our digital spaces without human
approval, such as the GitHub @claude agent. Similarly, automated review tools that publish
comments without human review are not allowed. However, an opt-in review tool that keeps a
human in the loop is acceptable". "AI tools must not be used to fix GitHub issues labelled
good first issue." The rationale states the relocation directly: "Prior to the advent of
LLMs, open source project maintainers would often review any and all changes sent to the
project simply because posting a change for review was a sign of interest from a potential
long-term contributor. While new tools enable more development, it shifts effort from the
implementor to the reviewer, and our policy exists to ensure that we value and do not
squander maintainer time." The RFC draft had a numeric threshold — contributions "below 150
additional lines of non-test code" — which its author called arbitrary and the adopted text
drops; the draft's term for the harm is Nadia Eghbal's "extractive" contribution and its
rule that a change be "worth more to the project than the time it takes to review it". What
is enforced: a ban on unattended agents and auto-publishing review bots; discretion
otherwise. The earlier thread the Hora census cites
([88300](https://discourse.llvm.org/t/our-ai-policy-vs-code-of-conduct-and-vs-reality/88300))
was not read.

### Rate limits and hard stops in the Hora et al. corpus

The three "Limit the number of PRs" policies in Hora, Robbes, and Zacchiroli's census
(arXiv:2609.07542; full text read from the PDF at [arXiv](https://arxiv.org/abs/2609.07542))
are quoted by the paper and two were verified at a pinned commit:

- **kilocode** (`CONTRIBUTING.md` at
  [abd24c72](https://github.com/Kilo-Org/kilocode/blob/abd24c7223df8cd8df203d9b457e5a7bcd9147d2/CONTRIBUTING.md)):
  keep "PRs focused and limited. As a rule, open no more than three PRs at a time, especially
  if you are a new contributor"; "Do not submit batches of agent-generated, untested, or
  weakly reviewed PRs"; maintainers may close a batch and ask the contributor to reopen one.
  This is the only per-contributor numeric WIP limit found in this pass.
- **pocketbase** (`CONTRIBUTING.md` at
  [089ca8ae](https://github.com/pocketbase/pocketbase/blob/089ca8ae412a1dbe29d2ae90d74f3866429d9c52/CONTRIBUTING.md)):
  "Due to recent LLM spam, PRs are temporary disabled and only existing collaborators can
  open a PR" — a stop on arrivals rather than a limit.
- **docusaurus** (per Hora et al.; not verified at source): PRs of about 1k lines "require
  prior communication".
- **vitest** (per Hora et al.; not verified at source): PRs judged "maybe automated" are
  auto-closed after three days — the one mechanism in the census that is tooling rather than
  text, and it acts on suspicion of automation, not on count.

The paper's own framing: "reviewer attention is a scarce, often volunteer-funded resource"
and agent-generated contributions arrive "at a volume that current review processes were not
designed to absorb". Evidence type: policy-text census; the effect of any policy on arrival
rate is not measured.

### Debian's General Resolution

[GR 2026-002, "LLM usage in Debian"](https://www.debian.org/vote/2026/vote_002) (page read
in full; discussion 2026-07-23 to 2026-08-13, extended; voting 2026-08-15 to 2026-08-28;
eight proposals; "Current Developer Count = 1045"). The capacity argument is in Proposal A
(Matthias Geiger), the Social-Contract ban: "New contributors submitting LLM output for
review places an unnecessary strain on the reviewer, which can lead to burnout" and "Debian
is not here to generate as much code as possible requiring manual review by a shrinking
number of human volunteers." Proposal A needed a 3:1 majority and was dropped at 0.560 (144
votes over "None of the above", 257 the other way). The Condorcet winner was Option 5, Marc
Haber's "Responsible Use of Generative AI" (majority 2.230, 281/126; 55 votes over Option 2,
"Allow AI-Assisted Contributions with conditions"). Its text: "Debian neither endorses nor
prohibits the use of generative AI tools"; "Contributors are expected to understand, review,
test, and, where appropriate, modify AI-assisted output before incorporating it into
Debian. Blindly accepting or uploading AI-generated material without appropriate human
review is inconsistent with Debian's established development practices"; disclosure is
encouraged but not required; and the one clause on volume: "The use of generative AI does
not alter Debian's established expectations regarding large-scale or automated project
actions. Contributors intending to perform actions with broad project impact, such as mass
bug filing or patch submission, large-scale code modifications, or other automated changes
or requests affecting many packages or contributors, should seek prior discussion and
consensus through the appropriate project channels before proceeding. Any such automated
process should be overseen by a human who remains accountable for its behavior and output."
What is enforced: the existing mass-action norm; no limit and no disclosure requirement.
Evidence type: the project's vote page; the tally is measured, the arguments are argument.

### Sashiko: adding review capacity, and the dispute over it

The kernel is the one project in the seed list that responded to volume by adding an
automated reviewer and then argued, on the record, about whether it added or consumed
capacity. At the 2026 LSFMM+BPF plenary ([LWN 1073583](https://lwn.net/Articles/1073583/),
Jake Edge, 2026-05-25, full text) Roman Gushchin said he started Sashiko partly because of
the "roughly 50%" rise in first-time contributors for 7.0; his analysis of "1500 email
threads" gave a false-positive rate "around 10%", "roughly 85%" true positives, and "almost
97%" accuracy on critical and high-severity findings; "140 mentions of Sashiko in the commit
messages" had accrued in seven weeks; the tool runs on linux-kernel and 47 or 48 opted-in
lists. Chuck Lever "has sent an 18-patch series to the mailing list seven or eight times
because Sashiko keeps finding different problems each time"; Christoph Hellwig called the
output "overly human-looking language that takes a huge amount of time to parse"; Ted Ts'o
"keeps getting reports of the same things over and over". In the memory-management dispute
([LWN 1064830](https://lwn.net/Articles/1064830/), Daroc Alden, 2026-03-31, full text)
Andrew Morton proposed requiring authors to answer Sashiko and lengthening the lag before
merging; Lorenzo Stoakes objected that the tool's "inexhaustible ability to produce new
reviews that require human attention" meant that "Incorporating the tool in its present
state, as anything other than a simple advisory, would increase the workload on the already
overworked memory-management maintainers"; Morton's count was that "Out of about 35 emails,
22 received replies indicating that alterations were definitely needed" and "If checking
these reports slows us down and we end up merging less code and less buggy code then that's
a good tradeoff"; Stoakes replied that 22 threads with one correct observation each says
nothing about the per-comment false-positive rate. Later
([LWN 1083275](https://lwn.net/Articles/1083275/)): Ts'o, "one of the things that really
excites me about Sashiko is that it reduces my workload"; Laurent Pinchart, that mandatory
responses would "force contributors to constantly justify their value against a machine that
is known to produce a non-negligible quantity of nonsense"; James Bottomley, "the contributor
doesn't get to approve the tools the maintainer uses to assess and apply patches". Evidence
type: the accuracy figures are the author's own analysis as LWN reports it; the workload
claims are testimonial on both sides.

## Tooling positioned as capacity

**Merge queues.** GitHub's documentation
([Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue),
full page): "A merge queue helps increase velocity by automating pull request merges into a
busy branch and ensuring the branch is never broken by incompatible changes." It requires
passing checks, schedules merges after approval, and has no setting that concerns reviewer
load. Evidence type: product documentation.

**CodeRabbit** ([coderabbit.ai](https://www.coderabbit.ai/), homepage read 2026-09-15):
"Fast code. Faster chaos. Coding agents are flooding pipelines with massive PRs faster than
teams can validate, prioritize, understand, or secure them." Its Triage product: "Prioritize
your PR flood. With more PRs than ever ballooning your queue, CodeRabbit Triage scores,
ranks, and routes them". **Cursor Bugbot** ([cursor.com/bugbot](https://cursor.com/bugbot),
read 2026-09-15): "70%+ of flags get resolved before merge"; customer quotes include "Bugbot
helps give back 40% of time spent on code reviews" (Rippling). Evidence type: vendor
marketing and customer testimonial; no method stated.

Agarwal et al.'s G3088 names the two responses these products embody — "add an automated
first-pass layer or you accept that human review becomes performative" — and LLVM's policy
draws the line between them: an auto-publishing review bot is banned, an opt-in one with a
human in the loop is allowed ([LLVM](https://llvm.org/docs/AIToolPolicy.html)). None of the
three products, nor the merge queue, adds a human reviewer; each changes what reaches one.

## Maintainer labour: the Tidelift survey

Tidelift's 2024 State of the Open Source Maintainer survey (over 400 maintainers; the blog
has moved and its original URLs return 404, so two posts were read from the Wayback Machine:
[60% of maintainers are still not paid for their work](https://web.archive.org/web/20241021160054id_/https://blog.tidelift.com/60-of-maintainers-are-still-not-paid-for-their-work)
and [AI-based coding tools: maintainers have some valid concerns](https://web.archive.org/web/20241031114640id_/https://blog.tidelift.com/ai-based-coding-tools-maintainers-have-some-valid-concerns)).
60% describe themselves as unpaid hobbyists (16% of whom do not want payment, 44% would
accept it); 61% of the unpaid are the sole maintainer. 45% expect AI coding tools to have a
negative impact on their work (22% somewhat, 23% extremely) against 9% extremely positive;
the named concerns are the quality of generated contributions and then "increased
maintenance burden". Evidence type: survey of a self-selected sample recruited through
Tidelift, fielded before the agentic-PR volume above, so it records expectation, not
experience.

## Framing: Jevons and rebound

The corpus records that no note in this directory uses the Jevons or rebound framing
([synthesis.md](synthesis.md#gaps-every-pass-left), gap 10;
[cowan-more-work-for-mother.md](cowan-more-work-for-mother.md#travel-into-technology-criticism-and-software-discourse)).
The sources in this pass supply the practitioner version without the name — G2802's
linear-versus-multiplicative throughput, G2394's "10 to 25 times without proportionally
increasing review capacity", DORA 2025's "simply generate more code that will only exacerbate
the bottleneck", Faros 2026's "reviewers cannot keep pace with the volume" — and Alcott
supplies the named claim: Blake Alcott, "Jevons' paradox", *Ecological Economics* 54(1):9–21,
2005 ([doi 10.1016/j.ecolecon.2005.03.020](https://doi.org/10.1016/j.ecolecon.2005.03.020);
abstract via Semantic Scholar, the publisher returning 403), in which efficiency gains in the
use of a resource "rebound or even backfire" rather than reduce its consumption. The mapping
is structural, not sourced: none of the software sources cites Jevons or Alcott, and no
measurement in this pass tests whether review capacity freed by a tool is consumed by more
submissions. What the pass does show is the relocation the Cowan note describes, stated as
policy rationale by LLVM ("it shifts effort from the implementor to the reviewer") and as a
finding by Asdaque et al. ("shifting verification burden onto reviewers").

## Mapping to the existing notes

Documentary only: where a note in this directory touches the same point, the link; otherwise
"No counterpart".

| Finding | Primary source | Evidence type | Where the existing notes touch it |
| --- | --- | --- | --- |
| Pre-agent reviewer load: 3.2 h/week mean at Google (median 2.6), 6.4 h/week self-reported in OSS; median 4 changes reviewed a week | Sadowski et al. 2018; Bosu and Carver 2013 | Measured (telemetry); survey n = 287 | No counterpart; the nearest rate norm in the notes is McIntosh's 200 lines/hour ([measurement, proxies](track-measurement.md#proxies-and-telemetry)) |
| "Hard finding time to perform all the code reviews requested" was a top reviewer challenge before agents | MacLeod et al. 2018 | Survey, n = 911 | No counterpart |
| Platform arrivals: 43.2M PRs merged/month (+23%), 1M+ coding-agent PRs in five months; Dependabot merges ~1M of 3–4M openings/month | Octoverse 2025 | Platform count | No counterpart |
| Agentic PRs are concentrated: median repo 1–2 in three months; 75.22% of projects below 0.25 participation; 25 of 2,361 projects above 36 PRs/participant | Raida and Hou 2026 | Measured, n = 25,264 PRs | The 78.9% / 11.3% oversight figures only ([chat-centric, bottom line](chat-centric-agents-vs-team-sdlc.md#bottom-line); [synthesis, tensions](synthesis.md#tensions-the-sources-state)) |
| Low-experience agent-assisted PRs draw 4.52× the review comments and stay open 5.16× longer | Asdaque et al. 2026 | Measured, n = 22,953; abstract | No counterpart |
| Share of merged agentic PRs with no human review fell >50% → ~12%; agentic time-to-merge rose 20 min → 2–3 h; direction "can reverse under defensible analysis choices" | Agarwal et al. 2026 | Measured, 3,000 repos; observational | Abstract only, as "reviewed less often and merged faster" ([discourse addendum, Target 2](discourse-and-tooling-addendum.md#target-2-company-engineering-blogs-and-public-rfcs)); the opposite-direction habituation result ([hand-off checks, evidence](track-hand-off-checks.md#evidence)); the "Saved against relocated" tension cites only the habituation direction ([synthesis, tensions](synthesis.md#tensions-the-sources-state)) |
| Practitioners state the capacity mismatch as linear reviewers versus multiplicative generation; review fatigue; "human review becomes performative" | Agarwal et al. 2026, G2802, G439, G3088 | Testimonial, coded from 3,100 documents | The "verification tax" and Vella and Blincoe's "supervisory engineering work" ([Cowan, mapping](cowan-more-work-for-mother.md#mapping-to-the-existing-notes); [literature addendum, Target 1](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026)) |
| Elapsed review time up 91% (2025) and 156.6–441.5% (2026); unreviewed merges up 31.3%; no company-level correlation | Faros 2025, 2026 | Vendor telemetry, no control | The 91% and 154% figures ([measurement, proxies](track-measurement.md#proxies-and-telemetry)); PostHog's and Ona's throughput ([discourse addendum, Target 2](discourse-and-tooling-addendum.md#target-2-company-engineering-blogs-and-public-rfcs)) |
| Copilot: no significant change in PR throughput or cycle time; 41% more bugs | Uplevel 2024 | Vendor telemetry, ~800 developers | No counterpart |
| 25% more AI adoption ↔ −1.5% throughput, −7.2% stability, +3.1% review speed (2024); throughput now positive, instability still rising (2025); "simply generate more code that will only exacerbate the bottleneck" | DORA 2024, 2025 | Survey, ~3,000 / ~5,000 | DORA's question batteries ([measurement, self-report](track-measurement.md#self-report-and-survey-instruments)); the 2025 trust figures ([evidence, surveys](evidence-and-mechanisms.md#surveys-trust-and-verification-not-comprehension)) |
| Post-review implementation time 9 vs 15 min, not significant; reviewer time not measured | METR 2025 | RCT, n = 16 | METR's slowdown and 9% reviewing time ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| curl: ~2 security reports/week, ~20% AI slop, confirmed rate >15% → <5%, 3–4 people × 30 min–3 h per report; bounty ended 2026-01-31 | Stenberg 2024–2026 | Maintainer counts and testimony | No counterpart |
| curl policy enforces a ban on fake reporters, removal of reward, and a channel change; no rate limit | curl CONTRIBUTE.md, BUG-BOUNTY.md | Policy text | No counterpart; Hora's "Ban" and "Stop accepting PRs" classes ([hand-off checks, Hora](track-hand-off-checks.md#how-hora-et-al-report-enforcement)) |
| AI analyzers delivered >400 suspected issues in two months; ~50 fixes merged from the first list | Stenberg 2025-10-10 | Maintainer counts | No counterpart |
| Gentoo, NetBSD, QEMU forbid or decline AI content; Gentoo names "an unfair human effort … to review" | Project policy pages | Policy text | Ghostty, CloudNativePG, Mastodon texts and the Hora census ([hand-off checks, policy texts](track-hand-off-checks.md#policy-texts)) |
| Kernel: Assisted-by tag, no tooling enforcement; bug-fix procedure names "unverified reports and untested fixes"; 1,111 of 16,418 commits tagged in 7.2 | coding-assistants.rst; LWN 1049830, 1083275, 1088776 | Policy text; tag counts | No counterpart |
| Rust: reviewers may close burdensome PRs without relitigating, "Reviewer time and effort are very precious and limited resources" | compiler-team#893 | Policy text | No counterpart |
| LLVM: human in the loop; unattended agents and auto-publishing review bots banned; "shifts effort from the implementor to the reviewer"; 150-line draft cap dropped | AIToolPolicy; RFC 88476 | Policy text | "LLVM cites Fedora's proposal" only ([hand-off checks, policy texts](track-hand-off-checks.md#policy-texts)) |
| Only numeric per-contributor limit: kilocode's three open PRs; only hard stop: pocketbase; 3 of 281 policies limit PR count (corrected 2026-09-15: Hora et al. Table 4 counts 188 AI-slop countermeasures, not 281 policies; "Limit the number of PRs" is 3 of those 188 (1.6%), i.e. about 1.1% of the 281 policies) | kilocode, pocketbase CONTRIBUTING.md; Hora et al. | Policy text; census | The census row "Limit the number of PRs 3 (1.6%)" without the texts ([hand-off checks, Hora](track-hand-off-checks.md#how-hora-et-al-report-enforcement)) |
| Debian: "Responsible Use" won; ban lost 144 vs 257; mass patch submission routed through prior discussion | Debian GR 2026-002 | Vote tally; policy text | No counterpart |
| Sashiko: ~85% true positives on 1,500 threads per its author; dispute over whether mandatory response adds or consumes maintainer capacity | LWN 1073583, 1064830, 1083275 | Author's analysis as reported; testimonial | No counterpart |
| Merge queues, CodeRabbit Triage, Bugbot automate the merge or the first pass; none adds a reviewer | GitHub docs; vendor pages | Documentation; marketing | The step-gate vendors' habituation remark ([synthesis, what the grid shows](synthesis.md#what-the-grid-shows)) |
| 60% of maintainers unpaid; 45% expect AI tools to make their work harder; "increased maintenance burden" | Tidelift 2024 | Survey, n > 400 | No counterpart |
| The rebound framing exists in the discourse without the name | Alcott 2005; Agarwal G2802; DORA 2025 | Argument; testimonial | Gap 10 and the Cowan note's grep ([synthesis, gaps](synthesis.md#gaps-every-pass-left); [Cowan, software discourse](cowan-more-work-for-mother.md#travel-into-technology-criticism-and-software-discourse)); Bainbridge's residual-task irony ([adjacent literatures, Bainbridge](adjacent-literatures.md#bainbridges-ironies)) |

"No counterpart" means no note in this directory addresses the point; it is a statement about
the notes, not about the wider literature.

## Corrections proposed

Documentary; no existing note was edited.

1. **evidence-and-mechanisms.md, Surveys: trust and verification, not comprehension**: "DORA
   frames a 'verification tax' and AI as an amplifier of existing organisational strengths
   and weaknesses." — "verification tax" does not occur in the 2025 report PDF (a text search
   for "tax" matches only "syntax") or on the report's landing page; "amplifier" does ("AI is
   an amplifier", executive summary). The nearest report language is "a need for critical
   validation skills". The phrase may come from coverage not located; until a DORA source is
   found the attribution is unverified
   ([DORA 2025 PDF](https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf);
   [landing page](https://dora.dev/research/2025/dora-report/)). The
   [Cowan note's mapping](cowan-more-work-for-mother.md#mapping-to-the-existing-notes)
   ("DORA's 'verification tax'") and the
   [synthesis](synthesis.md#tensions-the-sources-state) inherit the attribution.
2. **track-measurement.md, Dead ends**: "Not located or not published: … the Faros 2026
   report cited by Wheeler" — A Faros AI 2026 report exists and its ten-takeaways page is
   public: "The AI Engineering Report 2026: The Acceleration Whiplash" (2026-04-12; 22,000
   developers, 4,000+ teams)
   ([Faros 2026](https://www.faros.ai/blog/ai-acceleration-whiplash-takeaways)). Whether it
   is the report Wheeler cites was not verified; the full report is behind a form.
3. **synthesis.md, Tensions the sources state, "Saved against relocated"**: "while its review
   telemetry runs *opposite* to the second: approvals rise and scrutiny falls rather than the
   standard rising." — The sentence rests on one direction of evidence (Yu et al.'s
   within-reviewer habituation). Two later sources report the other direction on different
   measures: Agarwal et al.'s observational data has the no-review share of merged agentic PRs
   falling from over 50% to about 12% and agentic time-to-merge lengthening from about 20
   minutes to 2–3 hours, and the authors state that this "runs opposite to the within-reviewer
   habituation reported by Yu et al." and that "studies disagree"
   ([Agarwal et al.](https://arxiv.org/abs/2607.07980)); Faros 2026 has median time in review
   up 441.5% while unreviewed merges are up 31.3% in the same population
   ([Faros 2026](https://www.faros.ai/blog/ai-acceleration-whiplash-takeaways)). "Its review
   telemetry runs opposite" is no longer a single-direction statement; the same sentence
   appears in the Cowan note's mapping row ("The notes' review telemetry runs the other way
   from Cowan"; [cowan-more-work-for-mother.md](cowan-more-work-for-mother.md#mapping-to-the-existing-notes)).

## Dead ends

- **Reviewer-hours per PR, before and after agents, on one population**: searched the
  baselines (Sadowski, Bosu, MacLeod), the vendor reports (Faros 2025 and 2026, Uplevel), the
  surveys (DORA 2024 and 2025), METR, and the seven agentic-PR studies; not found. Elapsed
  time, comment counts, and hours per reviewer per week exist; effort per change does not.
- **Sasha Levin's July 2025 LKML RFC** for the Assisted-by tag: lore.kernel.org served an
  Anubis bot-challenge page to every fetch (three URL forms tried); the merged document and
  LWN's Summit report were used instead. **Torvalds's July 2026 remarks** on LLM patches: no
  primary link located; not searched with the web tool.
- **Unverified dates and claims**: NetBSD's adoption date for the LLM clause (not on the
  page; May 2024 from memory); a withdrawn 2025 Debian GR attempt (search-result only);
  Hora et al.'s docusaurus and vitest examples (quoted from the paper, not read at a pinned
  commit); Worklytics 2025, the source of Raida and Hou's 36-PRs-per-participant line (the
  resources page was fetched, the report not located).
- **Gated or unreachable**: Uplevel's full report (email form; blog summary used); Faros's
  full 2026 report (form; takeaways page used); the DORA 2025 PDF on dora.dev (links to a
  gated cloud.google.com form; found at services.google.com by the first web search);
  Alcott 2005 full text (ScienceDirect 403; Semantic Scholar abstract after one 429);
  Tidelift's blog (now a 404 at sonarsource.com; two Wayback captures read, the CDX index
  intermittently "Temporarily Offline"); MacLeod et al.'s Microsoft Research PDF (403) and
  current author copy (404; a 2019 Wayback capture read); GitHub code search (401 without
  authentication; the kernel documentation index and the Hora census used to locate files).
- **Not read**: LLVM's "Our AI policy vs code of conduct" thread (88300); the FOSDEM 2026
  slides; Khojah et al. and Yu et al., cited through the existing note.
- **Maintainer burnout measured against arrival rate**: the Tidelift survey records
  expectation in 2024; no post-2025 measurement of burnout against agentic-PR volume was
  found in the sources read. Not searched with the web tool.
- Web searches used: 2 of the permitted 15 — (1) locating the DORA 2025 PDF; (2) locating the
  Debian General Resolution.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Agarwal, Miller, Kästner, and Vasilescu, "3100 Opinions on Code Review in an AI World" (arXiv:2607.07980 v1, 2026-07-08). Full text. https://arxiv.org/abs/2607.07980
- Alcott, "Jevons' paradox", *Ecological Economics* 54(1):9–21 (2005). Abstract only. https://doi.org/10.1016/j.ecolecon.2005.03.020
- Asdaque et al., MSR 2026 Mining Challenge paper on vibe-coder PRs (arXiv:2602.23905, 2026-02-27). Abstract. https://arxiv.org/abs/2602.23905
- Bosu and Carver, "Impact of Peer Code Review on Peer Impression Formation: A Survey" (ESEM 2013). Full text, author's copy via Wayback. http://amiangshu.com/papers/Bosu-ESEM-2013.pdf
- CodeRabbit, homepage (read 2026-09-15). Vendor. https://www.coderabbit.ai/
- curl, `docs/CONTRIBUTE.md` and `docs/BUG-BOUNTY.md` at `master` (read 2026-09-15). Full text. https://raw.githubusercontent.com/curl/curl/master/docs/CONTRIBUTE.md ; https://raw.githubusercontent.com/curl/curl/master/docs/BUG-BOUNTY.md
- Cursor, Bugbot product page (read 2026-09-15). Vendor. https://cursor.com/bugbot
- Debian Project, General Resolution 2026-002, "LLM usage in Debian". Full page. https://www.debian.org/vote/2026/vote_002
- DORA, *Accelerate State of DevOps Report 2024*. Full text. https://dora.dev/research/2024/dora-report/2024-dora-accelerate-state-of-devops-report.pdf
- DORA, *State of AI-assisted Software Development 2025*. Full text. https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf
- Ehsani et al., study of 33,000 agent PRs (arXiv:2601.15195). Abstract. https://arxiv.org/abs/2601.15195
- Faros AI, "The AI Productivity Paradox" (2025-07-23). Report page. https://www.faros.ai/blog/ai-software-engineering
- Faros AI, "Ten takeaways from the AI Engineering Report 2026: The Acceleration Whiplash" (2026-04-12). Takeaways page. https://www.faros.ai/blog/ai-acceleration-whiplash-takeaways
- Gentoo Council, AI policy (voted 2024-04-14). Full text. https://wiki.gentoo.org/wiki/Project:Council/AI_policy
- GitHub Docs, "Managing a merge queue". Full page. https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- GitHub, Octoverse 2025 (2025-10-28). Full page. https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/
- Hora, Robbes, and Zacchiroli, "'We Permit the Use of AI, but […]': The Landscape of AI Policies in Open Source" (arXiv:2609.07542). Full text. https://arxiv.org/abs/2609.07542
- Kilo-Org/kilocode, `CONTRIBUTING.md` at commit abd24c72. Full text. https://github.com/Kilo-Org/kilocode/blob/abd24c7223df8cd8df203d9b457e5a7bcd9147d2/CONTRIBUTING.md
- Li, Zhang, and Hassan, AIDev dataset (arXiv:2507.15003). Abstract. https://arxiv.org/abs/2507.15003
- Linux kernel, `Documentation/process/coding-assistants.rst` (commits 78d979db, 816d9992, 3d7c44f7). Full text. https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/Documentation/process/coding-assistants.rst
- LLVM, "LLVM AI Tool Use Policy". Full text. https://llvm.org/docs/AIToolPolicy.html
- LLVM Discourse, "RFC: LLVM AI tool policy: start small, no slop" (88476, 2025-10-01). Full thread as JSON. https://discourse.llvm.org/t/rfc-llvm-ai-tool-policy-start-small-no-slop/88476
- LWN.net, Corbet, "Toward a policy for machine-learning tools in kernel development" (1049830, 2025-12-11). Full text. https://lwn.net/Articles/1049830/
- LWN.net, Alden, "The role of LLMs in patch review" (1064830, 2026-03-31). Full text. https://lwn.net/Articles/1064830/
- LWN.net, Edge, "Reviewing kernel patches with LLMs" (1073583, 2026-05-25). Full text. https://lwn.net/Articles/1073583/
- LWN.net, "Debating the role of large language models in the kernel community" (1083275, 2026-07-21). Full text. https://lwn.net/Articles/1083275/
- LWN.net, "Development statistics for the 7.2 kernel" (1088776, 2026-08-17). Full text. https://lwn.net/Articles/1088776/
- MacLeod, Greiler, Storey, Bird, and Czerwonka, "Code Reviewing in the Trenches" (IEEE Software 35(4), 2018). Full text via Wayback. https://web.archive.org/web/20190501130459id_/https://www.michaelagreiler.com/wp-content/uploads/2019/03/Code-Reviewing-in-the-Trenches-Understanding-Challenges-Best-Practices-and-Tool-Needs.pdf
- METR, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity" (arXiv:2507.09089). Full text. https://arxiv.org/abs/2507.09089
- NetBSD, "Commit guidelines". Full text. https://www.netbsd.org/developers/commit-guidelines.html
- Peralta et al., rejection of agentic PRs (arXiv:2605.22534, 2026-05-21). Abstract. https://arxiv.org/abs/2605.22534
- pocketbase/pocketbase, `CONTRIBUTING.md` at commit 089ca8ae. Full text. https://github.com/pocketbase/pocketbase/blob/089ca8ae412a1dbe29d2ae90d74f3866429d9c52/CONTRIBUTING.md
- QEMU, `docs/devel/code-provenance.rst`. Full text. https://gitlab.com/qemu-project/qemu/-/raw/master/docs/devel/code-provenance.rst
- Raida and Hou, "How Do Open-Source Projects Adopt Agentic Coding Tools?" (arXiv:2607.14037 v2, 2026-07-16). Full text. https://arxiv.org/abs/2607.14037
- rust-lang/compiler-team, issue 893, "Policy: Empower reviewers to reject burdensome PRs" (2025-06-27). Full text via API. https://github.com/rust-lang/compiler-team/issues/893
- Sadowski, Söderberg, Church, Sipko, and Bacchelli, "Modern Code Review: A Case Study at Google" (ICSE-SEIP 2018). Full text. https://sback.it/publications/icse2018seip.pdf
- Stenberg, "The I in LLM stands for intelligence" (2024-01-02). Full text. https://daniel.haxx.se/blog/2024/01/02/the-i-in-llm-stands-for-intelligence/
- Stenberg, "Death by a thousand slops" (2025-07-14). Full text. https://daniel.haxx.se/blog/2025/07/14/death-by-a-thousand-slops/
- Stenberg, "A new breed of analyzers" (2025-10-10). Full text. https://daniel.haxx.se/blog/2025/10/10/a-new-breed-of-analyzers/
- Stenberg, "The end of the curl bug-bounty" (2026-01-26). Full text. https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/
- Stenberg, "Open Source security in spite of AI" (2026-02-03). Post only; slides not read. https://daniel.haxx.se/blog/2026/02/03/open-source-security-in-spite-of-ai/
- Tidelift, "60% of maintainers are still not paid for their work" (2024). Full text via Wayback. https://web.archive.org/web/20241021160054id_/https://blog.tidelift.com/60-of-maintainers-are-still-not-paid-for-their-work
- Tidelift, "AI-based coding tools: maintainers have some valid concerns" (2024). Full text via Wayback. https://web.archive.org/web/20241031114640id_/https://blog.tidelift.com/ai-based-coding-tools-maintainers-have-some-valid-concerns
- Uplevel, "AI for Developer Productivity: What Now?" (2024-10-18). Blog summary; report gated. https://uplevelteam.com/blog/ai-for-developer-productivity
- Watanabe et al., "Is It Merged? Characterizing Claude Code PRs" (arXiv:2509.14745 v3). Abstract. https://arxiv.org/abs/2509.14745
- Yoshioka et al., merge-outcome features of agentic PRs (arXiv:2601.18749). Abstract. https://arxiv.org/abs/2601.18749
