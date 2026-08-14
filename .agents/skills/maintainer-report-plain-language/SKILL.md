---
name: maintainer-report-plain-language
description: >-
  Rewrite a MAINTAINER-REPORT.md and CRITICAL-CANDIDATES.md into the canonical maintainer-facing
  format — the one established on the Superset report — so every report in the archive reads the
  same way. Written for a maintainer who is NOT a security specialist: a "How to read this report"
  glossary up front, every finding split into what goes wrong / what an attacker gets / suggested
  fix, plain-language cluster headings, and severity explained in the project's own terms.
  Changes no facts. Runs on one scan directory or in bulk across the whole archive with parallel
  agents, one per scan directory. Every rewrite is checked by an independent verification agent that
  confirms every finding id, file:line, severity, score, panel vote, confidence, precondition,
  caveat, coverage claim, threat-model delta and patch-table row survived unchanged, and that no new
  fact was invented. A rewrite that fails verification is rejected, not shipped.
  Use when Jarek says "rewrite the <project> report in plain language", "do the language pass on
  <project>", "bulk plain-language pass over the archive", "make the reports readable for
  maintainers", or when the parent report pipeline reaches its report stage.
---

# maintainer-report-plain-language SKILL

The **language pass** over the two maintainer-facing files the scan pipeline produces:
`MAINTAINER-REPORT.md` and `CRITICAL-CANDIDATES.md`.

It exists because the pipeline writes both in security-research shorthand, and the people who read
them are developers. On the worked example the reports were correct and largely unusable: attacker
labels, the fail-open/fail-closed distinction, the panel notation and the product's own role names
were assumed rather than explained — so the two most serious findings did not read as serious,
because nothing said that the role they needed was an ordinary analyst role rather than an admin one.

This SKILL turns that one hand-written rewrite into a **canonical format every report is held to**.
The output shape below is normative, not advisory: two reports for two different projects should
differ in their findings and in nothing else.

**It is a language pass and nothing else.** It changes how a report reads, never what it says. That
invariant is what makes it safe to run unattended across the archive, and it is enforced by a
verification agent rather than by care.

## Two modes

| | Single | Bulk |
| --- | --- | --- |
| Target | one scan directory | a set of scan directories (default: every one holding a report) |
| Dispatch | inline, in the current session | one agent per scan directory, in parallel |
| Verification | one verifier per file | one verifier per file, same contract |
| Approval | show the diff, confirm, commit | pilot batch first, then confirm the full run |
| Typical cost | $2–3 per scan directory | see "Cost and scale" |

Bulk is single, fanned out. There is no cheaper bulk variant: what makes the pass safe is per-file
verification, and that does not amortise.

## Parameters

| Parameter | Values | Default | What it controls |
| --- | --- | --- | --- |
| `targets` | a project name, a list, or `all` | the project named at invocation | Which scan directories to process. `all` = every directory under the archive's scan tree holding at least one of the two report files. |
| `files` | `maintainer-report` \| `critical-candidates` \| `both` | `both` | Which files to rewrite. A directory missing one is processed for the other, not skipped. |
| `verify` | `true` \| `false` | `true` | The fact-preservation check. `false` needs an explicit operator instruction in the same breath and is recorded in the commit message. There is no silent way to turn it off. |
| `concurrency` | integer | 8 | Parallel rewrite agents in bulk mode. |
| `pilot` | integer | 5 | Directories to process and stop for review before the rest of a bulk run. `0` needs the operator to say so. |

## Hard rules

1. **No fact may change.** The rewrite may re-word, re-head, re-order within a section, split prose
   into labelled parts, merge duplicated passages, and add explanation. It may not change, drop or
   add a finding, severity, score, citation, vote, count, precondition, caveat or patch row. If the
   rewrite believes a fact is wrong, it says so **to the operator** and changes nothing — a language
   pass is not the place to correct analysis.

2. **Verification is a gate, not a report.** Anything other than a clean verdict is rejected and
   re-run once with the verifier's findings as input. A second failure stops that file and surfaces
   it; it does not ship with a note.

3. **Keep the `§` numbering and the finding ids exactly as they are.** Section *titles* are rewritten;
   section *numbers* are anchors other documents and the forward cite. Renumbering because the new
   headings read better in a different order breaks every inbound reference.

4. **Touch only the two report files.** Never `VULN-FINDINGS.*`, `TRIAGE.*`, `PATCHES.*`,
   `THREAT_MODEL.md`, `METHODOLOGY.md`, `PROVENANCE.md`, or anything under `PATCHES/`. Those are the
   evidence the rewrite is checked against; rewriting them destroys the check.

5. **Build agent prompts from sanitized values only.** In bulk mode the dispatcher hands each agent a
   path. Archive paths carry programme code names, and a hard-coded path in an agent prompt bypasses
   the `Read` sanitizing hook entirely — the one leak vector that has actually occurred. Pass a
   sanitized path or an opaque target id and let the agent resolve it through a hooked `Read`. Grep
   every generated prompt for code names before dispatch and fail loudly on a hit.

6. **One commit per batch, language-only.** Prefix `[report-lang]`, list the scan directories, state
   the invariant in the message. Never mix a language pass with a content change in one commit — the
   whole value of the commit is that it reviews as "nothing changed but the words".

7. **Show the diff and confirm before committing.** For bulk, the pilot batch is that confirmation
   point: the operator reads those diffs in full before the rest runs.

8. **Never let a CVSS number stand as the recommendation.** Wherever a score or vector appears, the
   ASF framing appears with it: the number came from the pipeline, CVSS fits this software badly,
   and the criticality call should be made on the ASF four-level scale. A report that prints a
   CVSS 9.1 with no framing has told a maintainer to act on a number the Foundation does not rate
   with — and it is precisely the reports with the highest scores that get read fastest.

---

# The canonical format

Normative. Every rewritten report has these sections, in this order, with these titles.

## MAINTAINER-REPORT.md

**Filenames are fixed: `MAINTAINER-REPORT.md` and `CRITICAL-CANDIDATES.md`.** They are the pipeline's
own names and they are what the forward attaches. Do not rename per project, per PMC or per commit: a
stable name is what keeps links to a report from rotting when it is revised in place, and a name that
varies by project cannot be scripted over the archive. One report per project per bundle, overwritten
in place as it is revised.

The title carries the project; the **subtitle carries the repository and commit**, so a reader can
tell which tree a finding refers to without opening another file, and so a report that outlives its
commit cannot be mistaken for current. Where a bundle spans more than one repository or commit, the
subtitle lists each pair, and any other commit the bundle touches gets its own line beneath.

| # | Canonical title | Source |
| --- | --- | --- |
| — | `# <Project display name> — Security Findings Report for Maintainers` | keep |
| — | `### Based on <repo> at <commit>[ and <repo> at <commit>]` | **new — always added** |
| — | `## How to read this report` | **new — always added** |
| §1 | `## §1 Summary` | rewrite of the executive summary |
| §1 | `### The critical overlay (a derived view)` | only when critical candidates exist |
| §2 | `## §2 Findings grouped by root cause, in fix-first order` | the cluster section |
| §3 | `## §3 How the panel resolved disagreements` | panel disputes |
| §4 | `## §4 Worth confirming by hand` | needs manual/dynamic confirmation |
| §5 | `## §5 What we checked and found sound, and what we did not reach` | verified clean + coverage |
| §6 | `## §6 Changes to your threat model` | threat-model deltas |
| §7 | `## §7 The one caveat that applies to everything here` | static-analysis caveat |
| §8 | `## §8 Candidate patches` | patches |
| §9 | `## §9 Disclosure` | keep |
| — | `## Appendix A — All <N> findings` | the full findings table |
| — | `## Appendix B — Who can reach each finding, and what they get` | reachability/impact table |
| — | `*Generated by …*` provenance line | **relocated to the very end** — see below |

### Protected regions — never authored by the rewrite

Two regions carry the programme name and are read through the sanitizing hook, so an agent that
retypes them writes a placeholder over the real text. They are **spliced from the original file's
raw bytes** by the dispatcher, never regenerated:

- **the metadata block** — everything before the first `## ` heading: title, To / From / Date /
  Target / Run / Method / Counts / scoping contract, and the `---` separator;
- **the provenance line** — the single italic line beginning `*Generated by `.

**The splice and the assertion are the dispatcher's job, never the agent's — and an agent's claim
that the regions are intact is not evidence.** An agent reads everything through the sanitizing hook,
so when it compares its output against a copy it read itself, it is comparing placeholder to
placeholder: they match, and it reports byte-identity in good faith while the real name has been
overwritten. This is not hypothetical — a bounded pilot run reported "confirmed byte-identical by
mechanical diff (not eyeballing)" for two regions it had in fact corrupted, and no check available
to it could have caught that. Splice from the original bytes outside the agent, and assert there.

Assert afterwards that the sanitizer's placeholder string appears **zero** times in the output. That
check needs no knowledge of the real token: the real one lives only in the spliced regions, so any
surviving placeholder means the rewrite authored one where it should not have.

**The provenance line moves to the very end of the document.** The pipeline emits it between §9 and
the appendices, which leaves both appendices stranded after what reads as the document's footer — a
reader who stops at the footer never sees the findings table. Relocation is not a content change: the
line's bytes are carried through identically, only its position is normalised. Do it deterministically
in the dispatcher, not by asking the agent, for the same reason the splice exists.

Sections the source does not have are not invented. A report with no panel disputes keeps §3 with one
line saying there were none — the numbering is fixed, so a section is never dropped to close a gap.

### `## How to read this report`

Sits immediately after the title, before §1. It defines every term the report otherwise assumes, once,
so the jargon is explained in one place instead of being relied on silently dozens of times. Four
labelled blocks, in this order:

**Who the attacker is.** A bullet per principal the report actually names, **using the project's own
role names**, saying what that account can already do before the attack starts. Where a role sounds
privileged but is not — an "elevated" role that is not admin — say so here **and** at the findings
that turn on it, citing the project's own permission matrix. This is the single highest-value line in
the section: without it a reader silently discounts the findings that need that role.

**"Default config".** One short paragraph: reachable without turning on a non-default feature flag or
optional service, and what still counts as default.

**Recurring concepts.** A bullet per term, defined in the sentence a maintainer needs rather than the
textbook one. Draw from this bank, and **include only what the report uses**:

> fail open / fail closed · per-object authorization · existence check vs. access check · RLS
> (row-level security) · DML / DDL · an "oracle" · SSRF · TOCTOU / DNS rebinding · stored XSS ·
> formula injection · path traversal · deserialization · SSTI / template injection · XXE ·
> open redirect · privilege escalation · secret exposure

Name the dominant pattern explicitly where there is one — "most of the findings below are a missing
per-object check" tells a maintainer how to read the whole report.

**How severity works here.** Severity is the panel's judgement of exploitability *under the project's
threat model* — how much privilege it needs, whether it works in a default configuration, how far the
damage spreads. **State plainly that it is not CVSS.** Where the report carries CVSS at all it is only
in the critical overlay, and that is a separate derived view; say which numbers are which. Then
explain the panel notation in the report's own terms, e.g. *"Panel: 5/5 TP, mean confidence 0.62"* —
what the vote is, what the confidence scale is, and how to read a unanimous vote with low confidence.

**On CVSS, and how we would like you to rate these.** Mandatory wherever the report carries a CVSS
score or vector — in this section, and again in `CRITICAL-CANDIDATES.md`. Say, in the report's own
words:

- any CVSS number here is present because the scanning pipeline produced one, **not** because it is
  the number we think the PMC should act on;
- **CVSS is a poor fit for this kind of software.** The ASF Security Team's own published position is
  that scoring systems like CVSS "don't work well for libraries, and they don't work particularly
  well for OSS projects in general"
  (<https://security.apache.org/blog/severityrating/>). A vector string cannot know which of your
  deployments enables the feature, who holds the role in practice, or what your users actually run;
- so **please assign criticality using the ASF default severity rating system** — Critical /
  Important / Moderate / Low, as defined in that post. Reproduce the four levels inline so the
  maintainer does not have to leave the document to use them:

| Level | Given to flaws that… |
| --- | --- |
| **Critical** | could be easily exploited by a remote unauthenticated attacker and lead to system compromise (arbitrary code execution) without user interaction. Flaws needing authentication, local or physical access, or an unlikely configuration are not Critical. |
| **Important** | can easily compromise confidentiality, integrity or availability: local or authenticated users gaining privileges, unauthenticated remote users viewing resources that should be protected, authenticated remote users executing arbitrary code, or remote users causing a denial of service. |
| **Moderate** | may be harder to exploit but could still compromise confidentiality, integrity or availability in some circumstances — could have been Critical or Important but are less easily exploited, affect unlikely configurations, or have limited scope. |
| **Low** | have some security impact but need unlikely circumstances to exploit, or where a successful exploit has minimal consequences. |

Two things this must not do. It must not tell the PMC that CVSS is forbidden — ASF projects are free
to use their own scale, and some deliberately publish CVSS. And it must not present our severities as
the answer: ours are a starting order under our reading of their model, and the rating that matters is
theirs, against their deployments.

### §1 — the summary, and the asks

§1 opens with a **TL;DR a maintainer can read in under a minute and know whether they need to act**.
It sits above everything else in the document and carries, in this order:

- **what was scanned and what came out** — the raw finding count, then the number actually in front
  of them, with severities;
- **the single most important finding**, in one sentence;
- **what they have already fixed**, if anything — leading with that is both accurate and a courtesy;
- **an explicit, numbered "what we are asking of you"** naming every ruling and decision required;
- one line stating the document is advisory and nothing is published.

It is a summary, not an abstract of every section: a finding that needs a paragraph belongs below.

**Ask for what you need, plainly.** If two threat-model rulings and three design decisions are
required, the TL;DR says so and says which findings each decides. A report that buries its asks in §6
gets the findings triaged and the questions ignored.

**Ask 1 is always to review and fix, in priority order — never left implied.** It is easy to omit
precisely because it feels obvious, and a report full of rulings and caveats otherwise reads as an
academic exercise rather than a request to act:

- **review the findings and confirm which hold** in their deployment and their reading of their own
  model — they may reasonably reach a different answer on any of them;
- **fix the ones that hold, highest severity first**, with our severities offered as a starting order
  and explicitly theirs to override;
- **assign each an ASF severity level** (see the CVSS block above) for their own deployments;
- **treat anything they judge a genuine vulnerability through their normal security process**, not as
  a public issue.

Two things this ask must not do. It must not set or imply a deadline, a turnaround or a queue
position — the programme makes no such promise and neither does this report. And it must not
instruct: the PMC owns the authoritative call on every finding, so this is a request for their
attention in an order we suggest. Phrase it as *"we are asking you to"*, not *"you must"*.

Where the PMC already has fixes in flight — merged or open PRs against the findings — say so **in the
same breath**, so the ask lands as "please finish and confirm" rather than "please start".

The rest of §1 is the funnel table (what each stage kept) and the headline risks, each in one
sentence, ordered as §2 orders them.

### §2 — the finding format

A one-line preamble states what each finding gives the reader. Then, per cluster:

```markdown
### Cluster <n> — <plain-language root cause> (<n> findings: <severity breakdown>)

**Root cause.** <what the shared mistake is, in the project's vocabulary>

**Why one fix closes <both/all>.** <only when a single change covers the cluster>

- **<id> — <SEVERITY> — `<file:line>`** — <one sentence: what it is>
  Panel: <n>/<n> real, mean confidence <0.00><, note on any split>.
  **What goes wrong:** <the defect, mechanically, in one or two sentences>
  **What an attacker gets:** <who they are, what they must already hold, what they end up with>
  **Panel correction:** <only when the panel refuted part of the original write-up>
  **Suggested fix:** <what to change, offered as a starting point>
```

Rules for this block:

- **The three labelled parts are mandatory** on every finding. `Panel correction:` appears only where
  there is one.
- **Cluster headings say the mistake, not the category.** "The semantic-layer API checks existence
  where it should check access" — not "Broken access control".
- **Fix-first order**, and the parenthesised counts in each heading must match the findings under it.
- **Merge duplicated scoring-and-verification prose.** Where the source restates the same score and
  panel outcome twice, it becomes one statement.
- **Cross-reference relatives inline** — `(see also f034 in Cluster 8)` — where one defect spans
  clusters, so a maintainer fixing one is told about the others.
- Findings that belong to no cluster go under `### One-offs (<n> findings: <breakdown>)`.

## CRITICAL-CANDIDATES.md

```markdown
# Critical findings — <project> (<date>)

## What this file is
<what "critical" means here and how it was derived; that any CVSS score and vector
string come from the pipeline and are background, not our recommendation; the ASF
CVSS caveat and the four-level ASF scale, reproduced inline; that the criticality
call is theirs>

## The <n> critical findings

### <id> — <plain-language title: what an attacker can do>
<the same three labelled parts as §2, plus the CVSS score and, in the body rather
than a summary table, the vector string>

## What we would like you to do
<the ask, in order — item 1 is always review-and-fix; one item is always
"assign each of these an ASF severity level (Critical / Important / Moderate /
Low) for your own deployments, and tell us if you land somewhere different from
our reading">
```

Same invariants: the finding set, ids, scores and vectors are carried through unchanged; only the
prose and the arrangement change. The vector string moves out of any summary table into the finding
body — readers who want it can find it, readers who do not are not made to scroll past it.

---

## Cost bounds — how the rewrite is allowed to run

Measured on the first pilot: an unbounded agent spent **$36 per report**, because it iterated
freely — 460 tool calls on the largest report, 339 on another — and every turn re-reads the whole
accumulated context. Cache reads were 250M tokens and 68% of the bill; generated output was under
3% of it. **Cost here is turn count, not report size.** The cheapest run in that pilot made 48 calls
and cost $6.21; the dearest made 460 and cost $61.56 on a report only two-thirds larger.

So the rewrite runs to a fixed shape, not to the agent's satisfaction:

1. **Read the source once.** Read each report file exactly once, in full. Do not re-read it to check
   your own work — that is the verifier's job, and it has fresh context precisely so it can do it
   without paying for yours.
2. **Draft in one pass, write once.** Compose the whole rewritten file, then write it in a single
   operation. No section-by-section write-then-reread loop.
3. **One correction round, maximum.** The verifier is the only correction loop. On a failed verdict,
   apply its findings and write once more. A second failure stops the file and surfaces it; it does
   not earn a third attempt.
4. **Do not re-verify your own corrections — re-dispatch the verifier, or stop.** An agent checking
   its own fix is the loop that produced the 460-call run.

   **Re-dispatching is mandatory when the correction PUT TEXT BACK — restoring a missing fact or
   re-specifying an altered one — and optional when it only deleted invented text.** Deletion is the
   safe direction: removing an unsupported clause cannot introduce a new error. Everything else can.
   Restoration covers re-attaching a dropped section, a panel vote, a classification, and equally the
   re-specifying of detail a rewrite had blurred — putting "B3 filed a FALSE_POSITIVE vote" back where
   the draft had written "one voter" is the same risk as restoring a dropped paragraph, because the
   letter can land on the wrong finding. Deleting invented text is self-contained and hard to get wrong;
   putting dropped content back can land it in the wrong section, with altered values, or attached to
   the wrong finding — and the first verifier is gone by then. One pilot report had a 17-row table
   dropped and re-inserted, plus a classification restored to two findings; the re-check cost $0.20
   against a $7 run and confirmed all five corrections landed without overshoot. At that ratio,
   guessing is not worth it. In that pilot, three of eleven reports needed a restoration and **one of
   those three had a defect introduced by the correction round itself** — a summary line rewritten
   into a claim the original never made, caught only because the re-check was run. A third of
   corrections going wrong is far too high a rate to leave to an agent's judgement.

**Model tiers.** The rewrite is a constrained transformation against a written spec, not open
research: run it on Sonnet 5. Run the verifier on Sonnet 5 too — it already does in practice, and
its verdicts have caught every real defect this pass has found, at $0.41–$6.33 per file. Reserve
Opus for a report the verifier has failed twice, where something genuinely needs judgement.

**Budget the run, and stop when it is spent.** A bulk run states its expected cost before it starts
and reports actual against expected when it finishes. If a single report exceeds 3× the per-report
budget, abandon it and surface it rather than letting it run — one pathological report must not
consume the batch. Never report a bulk run as complete without stating what it cost.

## The preservation checklist

The contract between the rewrite agent and the verifier. Keep the two in sync.

| Class | What must survive |
| --- | --- |
| Findings | every finding id; the set of findings; cluster membership; the counts in cluster headings |
| Citations | every `file:line`, path and symbol name |
| Scoring | every severity label; every CVSS score; every vector string |
| Panel | every vote, tally, mean confidence, dissent, and who moved |
| Qualifiers | every precondition, binding constraint, feature flag and caveat |
| Coverage | §5 verified-clean and not-reached claims, verbatim in substance |
| Model | §6 threat-model deltas |
| Patches | every §8 patch-table row and its finding mapping |
| Appendices | every row of Appendix A and Appendix B |
| Provenance | every commit sha, repository and date |

## Verification

A separate agent, fresh context, receives the original and the rewrite and answers one question:
**did any fact change?** It is dispatched to **refute** — to find a changed fact — not to confirm the
rewrite looks fine. A verifier told to check will find a way to agree.

```json
{
  "preserved": true,
  "missing":  [],   // facts in the original, absent from the rewrite
  "altered":  [],   // facts present but changed
  "invented": []    // facts in the rewrite with no basis in the original
}
```

**`preserved` is not a judgement the verifier gets to make — it is arithmetic.** It is `true` if and
only if `missing`, `altered` and `invented` are all empty. A verdict of `preserved: true` alongside a
non-empty array is incoherent, and the dispatcher must compute the boolean from the arrays rather
than trusting it. This is not hypothetical: one pilot report shipped five pieces of added
interpretation — glosses like "a TOCTOU gap" and "(no CSRF protection)" inside root-cause sentences,
an appended clause on a finding's exploit description — because its verifier listed them under
`altered` and still returned `preserved: true`, and the rewrite agent read "clean pass" and stopped.
A gate that can be talked past by its own summary field is not a gate.

`invented` matters as much as `missing`: a rewrite that explains a mechanism the original never
claimed has added analysis, which is what this pass must not do.

**One carve-out, covering every section this SKILL mandates.** These are new text by design and are
**not** `invented` facts, because they restate or explain rather than claim: `How to read this
report` (all four blocks, including the ASF severity table and CVSS caveat); §1's TL;DR and its
"what we are asking of you" list; `Appendix B`; and, in `CRITICAL-CANDIDATES.md`, `What this file
is` and `What we would like you to do`.

**Give the verifier this list explicitly, every time.** Where it is incomplete the gate fights the
format: in the pilot, one report's verifier flagged the mandated "advisory, nothing is published"
line as invented, another approved a report for *omitting* the mandated Appendix B, and a third
passed one that included it. Same spec, three readings, and the inconsistency lands in documents
PMCs are meant to compare.

Carve-out sections may restate facts already in the report and define terms. They may **not** assert
anything new about the code, an attacker, a configuration, a fix, or the process. Appendix B in
particular is a restatement: every cell must be traceable to that finding's own text above. Give the verifier
that exemption explicitly, scoped to those sections by heading. Anything outside them that asserts
something about the code, an attacker, a configuration or a fix, and that has no basis in the
original, is `invented` and fails the gate. Do not widen the carve-out to "explanatory sentences" in
general — a plausible-sounding mechanism added inside a finding is exactly the failure this check
exists to catch.

Run it on a cheap model with the preservation checklist as its rubric — this is mechanical
comparison, not judgement. It costs roughly a fifth of the rewrite and it is why the pass can run
unattended. Store the verdict with the run record, never in the report: the report is a PMC
deliverable and carries no process metadata.

## The mechanical screen — run it before you trust the verifier

The verifier reads. It does not count, and it is not exhaustive. Before accepting any rewrite, the
dispatcher runs a token-parity check over the original and the rewrite — seconds of shell, no model
involved — and investigates every mismatch:

| Token class | How to extract |
| --- | --- |
| Finding ids | `grep -o '\bf[0-9]\{3\}\b' \| sort -u` |
| Citations | file-with-extension plus `:line`, **keyed on basename + line** |
| Voter labels | `grep -o '\b[A-D][1-5]\b'` — counted, not deduped |
| Severities, CVSS scores and vectors, confidence figures, patch-row ids | one pattern each |

In the pilot this caught what careful reading had missed. One report's rewrite had systematically
replaced specific voter attributions — "B3 filed a FALSE_POSITIVE vote" — with "one voter" and
"panel note". Its verifier, dispatched to refute and given the whole file, found four instances. The
count found **twenty**. A verifier that reads well still reads sequentially and tires; counting does
neither.

**Treat a mismatch as a signal to investigate, never as a verdict.** The same screen produced a
false positive on another report: 27 citations looked lost, and the rewrite had in fact normalised
the source's inconsistent short and long forms (`admin/resource.lua:179` and
`apisix/admin/resource.lua:179` for the same line) onto the full path — an improvement, and
fact-preserving. Keying on basename plus line rather than the literal string turned 27 losses into
zero. Choose keys that are invariant under the reformatting the rewrite is *supposed* to do, and read
the diff before concluding anything.

Finding ids and citations should come out exactly equal on every report. Voter labels and confidence
figures may legitimately shift by one or two where the rewrite merges two adjacent mentions of the
same voter into one sentence — so inspect those, rather than demanding equality.

## Bulk mode

1. **Enumerate.** Every scan directory holding either report file. Report the count, the total size,
   and every directory holding neither — those are earlier or partial pipeline runs, skipped by
   design. Say so explicitly; a silent skip reads as coverage.

2. **Pilot.** Process `pilot` directories first, deliberately spanning a small, a median and a large
   report, and stop. The operator reads those diffs in full. This is what turns the estimate into a
   measurement: whether the format lands, what a report really costs on this corpus, and whether the
   verifier catches anything.

3. **Fan out.** One agent per scan directory, `concurrency` at a time, each rewriting both files in
   its own directory and returning per-file summaries plus verifier verdicts. No worktree isolation —
   each agent owns a distinct directory and they cannot collide.

4. **Report honestly.** Per directory: rewritten / skipped / failed verification. State any bound the
   run applied — a cap, a sampled subset, a retry not made. A run that silently did less than it
   enumerated is worse than one that did nothing.

5. **Commit in batches** once the diffs are confirmed.

## Cost and scale

Measured on the worked example: a 111 KB pair took ~132k output tokens and ~20 minutes in an
interactive session. Most of that session's spend was the same file re-read on every turn; a one-shot
agent does not pay that.

Planning figures for ~180 scan directories (~12 MB of report text):

| | Estimate |
| --- | --- |
| Per scan directory | $2–3 |
| Full archive, rewrite + verify | $400–500 |
| Worst case (interactive-style, many turns per file) | ~$900 |
| Wall clock at 8–16 parallel agents | 1.5–2 hours |

Re-derive from the pilot rather than trusting these. They are an anchor, not a budget.

## Relationship to the parent skill

The parent report-preparation SKILL owns *producing* the reports; this one owns *how they read*. When
the parent reaches its report stage it invokes this SKILL, so a report produced today and a report
rewritten from the archive come out in the same format, checked the same way.

Run it standalone whenever reports already exist — the common case for the archive, where every
report predates this format.

## Examples of bad runs (avoid)

- Correcting an analysis error found while rewriting. Surface it; change nothing. The moment a
  language pass edits a fact, no reviewer can trust the diff.
- Shipping a rewrite whose verifier flagged a missing citation, with a note that it was probably a
  duplicate.
- Inventing a section the source has no material for, to fill the canonical list.
- Renumbering the `§` sections because the new headings read better in another order.
- Rewriting `VULN-FINDINGS.md` or `TRIAGE.md` "for consistency" — they are the evidence.
- Interpolating a raw archive path into a fan-out prompt.
- Dropping the glossary because this project's report "does not really use jargon". Include the terms
  it uses; the section is not optional.
- Reporting a bulk run as complete when directories were skipped, without listing them.
- Running the full archive without a pilot because the format was already validated on one report.
