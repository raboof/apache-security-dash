---
name: frontier-model-preparation-model-verify
description: >-
  Pre-flight verification step in the Frontier Model Preparation scan pipeline.
  Given a PMC's nominated security model (file path or URL in their repo),
  check two things — (1) discoverability via AGENTS.md -> SECURITY.md
  so the scan agent can mechanically find it,
  and (2) completeness against the threat-model-producer rubric (the SKILL bound in this same repo).
  Produce a concrete remediation:
  either draft an email reply to the original PMC thread describing where verification stands and proposing improvements,
  or — when the gap is mechanical (e.g. AGENTS.md missing the link line, or a small set of missing sections) —
  generate the additions via threat-model-producer and open a PR with the diff.
  After verification passes,
  hand off to frontier-model-preparation-update to flip the `Security model verified` cell for that PMC.
  Use whenever a PMC nominates a security model (in their [GLASSWING] request, in a reply, or in their repo)
  and the Security team needs to confirm it before queuing the scan.
  Read-only assessment by default;
  external writes (PR / email / spreadsheet) are gated on explicit user approval.
---

# Frontier Model Preparation model-verify SKILL

Bridges `frontier-model-preparation-response` (where a PMC nominates a model) and `frontier-model-preparation-update` (where the verified-date gets recorded).
The SKILL's job is the mechanical pre-flight check the scan-response SKILL's hard rule alludes to —
and to produce the concrete remediation when the check fails.

## When to invoke

- A PMC has nominated a security model in their `[GLASSWING]` request, in a follow-up reply, or by pointing at a path in their repo (`docs/threat-model.md`, `SECURITY.md`, a wiki page, etc.).
- Before queuing a scan run,
  the Security team needs to confirm the model is (a) mechanically discoverable via `AGENTS.md → SECURITY.md`
  and (b) materially complete enough that the scan output won't drown the PMC in noise.
- A PMC asks "is our existing threat model good enough for Frontier Model Preparation?" and wants a concrete read.

Skip when there's no nominated model yet —
that's a prerequisite handled by `frontier-model-preparation-response` (the discoverability rule: no model, no scan).

## Inputs

- **PMC slug** (e.g. `logging`, `apisix`) — used to locate the PMC's row in the tracker afterwards.
- **Repo list** — read from the PMC's `Repositories requested` cell in the tracker (newline-separated URLs).
  If that cell is empty, the SKILL refuses:
  scope must be confirmed by `frontier-model-preparation-response` (gate 4) *before* verification runs.
  Every repo in the list gets the same two checks (A and B) independently —
  they can have different `AGENTS.md` / `SECURITY.md` shapes and different completeness profiles,
  and the scan agent will run against each one separately.
- **Commit / branch** (per-repo, default `HEAD` of each repo's default branch) —
  the scan binds to a specific commit,
  and the model is read at that commit;
  pin if the PMC named one.
- **Nominated model path or URL** (optional, per-repo) —
  if the PMC said "our model is at `docs/security/threat-model.md`" or pointed at a project-site page,
  start there;
  otherwise the SKILL derives the path from each repo's `AGENTS.md` (or its absence).

## Hard rules (do not skip)

1. **No external write without explicit user approval.** This is the same draft-and-confirm rule as the other Frontier Model Preparation SKILLs:
   show the issue body or PR diff, wait for "yes / open / go", then invoke `gh issue create` / `gh pr create`.
   Never invoke the GitHub write tools before showing the artefact.

2. **One remediation per failing check, not a grab bag.** If discoverability fails *and* completeness fails,
   produce two separate artefacts (e.g. one PR adding the `AGENTS.md` link, one email listing the missing model sections)
   rather than one omnibus thing the PMC has to negotiate as a unit.
   Small, targeted asks land faster.

   **One PR per repo, never one PR spanning multiple repos.** A PR can only touch one repo (GitHub mechanics),
   and a PMC that owns N repos in scope therefore gets up to N PRs.
   Each PR's URL is **appended** to the PMC's `PR/Issues` cell on a new line —
   never overwrite an existing URL.
   The Status tab (`build-status-tab`) reads every PR URL out of the cell and tallies open / merged counts;
   an overwrite loses one PR from the tally and from the team's audit trail.

   **Why email instead of a GitHub issue.** Three reasons, any one of which would be enough:

   - **Many Apache projects have issues disabled** on their GitHub repository (`apache/tomcat` is the textbook example) —
     the PMC tracks work elsewhere (JIRA, mailing list, project Bugzilla).
     A GitHub issue against such a repo cannot be filed at all.

   - **GitHub issues are public**; the scan-readiness conversation often isn't.
     A list of gaps in a project's threat model is exactly the kind of inventory a hostile researcher would mine for "the maintainers admit they don't check X".
     The PMC's `private@<pmc>` list (which the email replies thread through) keeps the same content contained to people the PMC has already vetted.
     Public issue trackers are wrong by default for this conversation.

   - **Even where issues exist, PMC members rarely watch them.** The original `[GLASSWING]` request came in as email;
     the PMC is already monitoring that thread.
     Continuing in the same thread reaches every PMC member, including ones who never see GitHub notifications.

   So: PRs for mechanical fixes (they need a repo write anyway,
   the diff is what the PMC is asked to ratify,
   and public attention is fine on "add one link line"),
   email replies for everything else.

3. **Use the project's own voice for proposed model content.** When generating threat-model section drafts via `threat-model-producer`,
   every claim must carry a `*(documented)*` / `*(maintainer)*` / `*(inferred)*` tag,
   and every `*(inferred)*` claim must route to a matching open question in §14.
   Do not silently fabricate maintainer positions.
   The PR is a *starting point* for the PMC to react to, not a finished model.

4. **Default to *email reply* for substantive gaps; default to *PR* for mechanical fixes.**
   A missing `AGENTS.md` link is mechanical (one-line repo add).
   A missing §8 "Properties provided" section is substantive (needs maintainer input).
   Borderline cases (e.g. missing §11a known-non-findings list) lean toward email with an offer to draft a PR on request.
   The email always replies to the original `[GLASSWING]` thread so the PMC sees it in the same conversation they started.

5. **Pre-flight is a check, not a re-write.**
   Never propose changes to *existing* model content unless the PMC asked.
   The SKILL identifies gaps and proposes *additions* (and the one structural fix of the `AGENTS.md → SECURITY.md` link).
   Edits to existing claims are the PMC's call.

6. **After verification passes, hand off — don't write the spreadsheet directly.**
   "Verification passes" means both: (a) the threat model itself passes the minimum-bar completeness rubric,
   AND (b) **every** repo in `Repositories requested` independently passes Check A (discoverability).
   One or two repos passing while others lack `AGENTS.md` is *not* PMC-level verified —
   that's a partial state where the next step is to either (i) get the missing repos fixed (PMC sweep or our PRs)
   and then re-run verification across the full set,
   or (ii) the PMC chooses to phase the scan
   and narrows `Repositories requested` down to the subset that does pass.

   Only when (a) AND (b) hold across the full `Repositories requested` set should the SKILL produce the handoff line ("Verified for `<pmc-slug>` at `<sha>` — ready to flip `Security model verified` to `<today>`");
   the user then invokes `frontier-model-preparation-update` to apply that change.
   Setting the flag too early causes the PMC to appear `Ready` in status views while the team is in fact still waiting on PMC follow-up.

7. **Verification is not all-or-nothing,
   and the artefacts are proposals — not requirements.**
   The only hard gate is **discoverability** (without it the scan literally cannot find the model and cannot run).
   Everything else is advisory.
   When the existing model is substantive on the core rubric (scope, out-of-scope, inputs, adversary, properties),
   the scan can proceed against it
   and the remaining gaps become *improvement proposals* rather than blockers.
   Partial coverage of the minimum bar is fine —
   we surface the gaps so the maintainer can decide, not so we can refuse.

   Every PR or issue this SKILL produces is a **proposal**.
   The maintainer is the decision-maker, not the Security team.
   The body must phrase this unambiguously:
   lead with "**this is a proposal for the PMC to review —
   please correct, reject, or discuss as needed**" (or similar).
   Do not phrase suggestions as obligations ("you need to do X" / "the scan requires Y").
   The scan does not require any of the §7 / §8 / §11a / §13 gaps to be filled before it runs;
   it just runs better when they are.
   Say so plainly.

8. **Do not mention "Frontier Model Preparation" (or the OpenAI program name) in any public artefact.**
   Public artefacts are: PR titles, PR bodies, commit messages on PMC repos, branch names,
   and anything else that lands on `github.com/apache/<repo>` or any other public-visible surface.
   The PMC-facing rationale for the change in a public PR is "improving the project's security model discoverability for automated scanners" —
   the specific scan program / model identity stays off-record there.
   The name *is* fine in email replies to the `[GLASSWING]` thread,
   because those go to `private@<pmc>.apache.org` and `security@apache.org` — both private lists.
   It's also fine inside this repo (`apache/security`) and in user-scope memory,
   because those surfaces are already inside the Security team's trust boundary.

   Why:
   the program identity is information the Security team controls disclosure of.
   Putting it on public issue trackers or in commit messages forecloses choices later (rebranding, running multiple scans in parallel) and gives hostile researchers a single string to grep for.
   Neutral phrasing — "an automated agentic security scan being piloted by the ASF Security team" — is precise enough for the maintainer to act on the PR without naming the program.

9. **Always use `gh pr create --web` for the final PR submit step.**
   The `--web` flag opens a browser to a pre-filled GitHub form rather than silently submitting from the CLI.
   The user reviews the rendered title + body + diff in the browser and clicks Submit themselves.
   This gives a final read-through pass on top of the in-conversation draft-and-confirm —
   the conversation guards against the wrong *intent*;
   `--web` guards against rendering surprises (escaping, markdown, autolink expansion, the wrong base branch) that the conversation can't see.

   The branch push still happens via `git push` before `gh pr create --web` —
   that part is local-to-remote and not user-facing.
   Only the final PR submission is gated through the browser.

   The SKILL does **not** use `gh issue create` at all —
   every PMC-side ask that isn't a repo write goes via email reply to the original `[GLASSWING]` thread (see hard rule 2).

## The rubric — what "verified" means

Two checks.
Both must pass for verification to succeed.

### Check A — Discoverability

The scan agent finds the model by mechanically following `AGENTS.md → SECURITY.md → model`.
The chain must terminate at a real artefact at the designated commit.

Acceptable terminations:

- The threat model is in `SECURITY.md` itself.
- `SECURITY.md` links to an in-repo file (e.g. `docs/threat-model.md`) and that file exists at the commit.
- `SECURITY.md` links to a project-site URL (e.g. `https://<pmc>.apache.org/security/threat-model/`) and the URL resolves to a model document.
  The website is acceptable per the threat-model-producer §3.1 rule.

Check failures:

| Failure | Mechanical fix? |
| --- | --- |
| `AGENTS.md` does not exist in the repo. | Yes — create with the minimum scaffold (one Security line linking to `SECURITY.md`). |
| `AGENTS.md` exists but has no link to `SECURITY.md` (or to a model file). | Yes — add the one-line link. |
| `AGENTS.md` links to `SECURITY.md` but `SECURITY.md` does not exist. | Sometimes — if a model lives at a known path, propose adding `SECURITY.md` as a stub pointing at it. Otherwise this is a PMC issue. |
| `SECURITY.md` exists but contains no link to a model and no embedded model content. | Issue, not PR — the PMC needs to decide what to point at. |
| The link target is a project-site URL that 404s, redirects to login, or is empty. | Issue — the PMC needs to fix the destination. |

### Check B — Completeness

Read the model.
Cross-check against the threat-model-producer rubric (the SKILL at `.github/skills/threat-model-producer/`).
The *minimum bar* for a Frontier Model Preparation-ready model is the sections below;
each must either contain substantive content or be marked `Not applicable — <reason>`.

| Section | Why the scan needs it |
| --- | --- |
| §2 Scope and intended use (with the component-family table) | Tells the scan which directories are in-model. Without it, every finding in `examples/` or `contrib/` lands on the PMC's plate. |
| §3 Out of scope (explicit non-goals) | The complement of §2 — same reasoning. |
| §6 Inputs and the per-parameter trust table | Triagers route findings against specific sinks; prose alone isn't enough. |
| §7 Adversary model | Lets the agent classify "in-model attacker" vs "out-of-model attacker" without re-deriving. |
| §8 Security properties provided (with violation symptom + severity) | The "what's a real bug" list. The single most-cited section in triage. |
| §9 Security properties *not* provided (with false-friends + well-known attack classes) | Pre-empts the most common false-positive category. |
| §10 Downstream responsibilities | What the integrator must do — clarifies which finding categories aren't the project's bug. |
| §11a Known non-findings | The recurring-false-positive list that feeds the scan agent's suppression. **Highest leverage section for noise reduction.** |
| §13 Triage dispositions | The closed set of routing outcomes. Without it, every finding is implicitly `MODEL-GAP`. |

Sections explicitly **not** part of the minimum bar (nice to have, but verification passes without them):

- §5a Build-time and configuration variants — only required if the project has security-relevant build flags.
- §15 Machine-readable companion (`threat-model.yaml`) — optional; useful but not blocking.

If a section is `Not applicable — <reason>`,
verification passes for that section (the maintainer has thought about it and ruled it out).
Empty headings with no commentary count as missing.

**Important — completeness is graded, not pass/fail.**
A model with substantive coverage of the core rubric (scope, out-of-scope, inputs, adversary, properties) but gaps in §11a or §13 is still good enough for the scan to run.
The gaps are recorded as *improvement proposals* (per hard rule 7), not as blockers.
The only hard-fail under this SKILL is **discoverability** —
without it the scan agent literally cannot reach the model and cannot start.
Every other failure mode produces a proposal that the PMC decides what to do with.

## Procedure

1. **Resolve the inputs.**
   Read the PMC's `Repositories requested` cell from the tracker.
   If the cell is empty,
   refuse and point the user at `frontier-model-preparation-response` to confirm scope first.
   Parse the cell into a list of repo URLs (newline-separated).
   For each repo:
   default the commit to the repo's default-branch HEAD unless the PMC named one explicitly.

2. **Run Checks A and B for *every* repo in the list, independently.**
   Each repo gets its own discoverability chain (an `AGENTS.md` in one repo says nothing about whether another repo has one) and its own completeness assessment (the model might be different per repo, or the same model linked from different `AGENTS.md` files).

   For Check A on each repo, use `gh api`:

   ```
   gh api repos/<owner>/<repo>/contents/AGENTS.md?ref=<sha>
   ```

   For each link traversal, fetch the next file.
   For external URLs, use `curl --head` (or the `WebFetch` tool) to confirm the URL resolves to a 200 with a document body.

   For Check B, read the model and walk the rubric.
   If multiple repos share the same model URL, you only need to read the model once —
   the assessment is per-model, not per-repo.
   The discoverability check is still per-repo even when the model is shared (each repo must independently get the agent to that model).

3. **Mark per-repo status** in a small grid:

   ```
   Repo                             Discoverability   Completeness
   ----                             ---------------   ------------
   apache/logging-log4j2            PASS              PASS (1 soft gap)
   apache/logging-log4net           FAIL              <not run yet — fix discoverability first>
   apache/logging-log4cxx           FAIL              <not run yet>
   ...
   ```

   For each minimum-bar section in the completeness check, mark **present** / **partial** / **missing** / **explicit N/A**.
   "Partial" means the section heading exists but the content is one-line / placeholder / clearly under-specified relative to the rubric.

4. **Summarize the assessment**, per-repo.
   Be explicit in the summary about *which repos were checked* —
   the user (and later, ASF Tooling) needs to know that "the Logging Services model is good" actually means "we verified all 4 listed repos: logging-log4j2 (PASS/PASS), logging-log4net (FAIL/N/A), …".
   Don't elide which repos in the cell got which verdict;
   the cell is the authoritative scope.

   Format:

   ```
   Repos verified (from PMCs!D<row> Repositories cell):
     - apache/logging-log4j2
     - apache/logging-log4net
     - apache/logging-log4cxx
     - apache/logging-flume

   Per-repo discoverability:
     apache/logging-log4j2     PASS    <chain summary>
     apache/logging-log4net    FAIL    <reason>
     ...

   Per-repo / per-model completeness (group by model URL when
   multiple repos share one):
     Model: <URL>
       Repos sharing this model: <list>
       §2 Scope                  present / partial / missing
       §3 Out of scope           ...
       §6 Inputs                 ...
       §7 Adversary              ...
       §8 Properties provided    ...
       §9 Properties not         ...
       §10 Downstream resp.      ...
       §11a Known non-findings   ...
       §13 Triage dispositions   ...
   ```

   When the verification message goes to the PMC (or into the per-PMC enrollment notes ASF Tooling reads off the tracker),
   the same per-repo breakdown should appear —
   implicit summary ("the model is good") hides which repos were actually checked.

5. **Decide remediation per failing check** using the decision table below.
   Show the user the assessment plus the proposed remediation,
   wait for approval before writing.

6. **For PR-path remediations**, draft the diff:

   - **AGENTS.md missing**:
     create with the minimum scaffold (see template below).
   - **AGENTS.md present, no link**: insert a single Security section.
   - **Model sections missing**:
     invoke `threat-model-producer` against the repo's public artefacts to generate drafts for each missing section,
     with every claim carrying a provenance tag (predominantly `*(inferred)*` on first draft) and corresponding §14 open questions.
     The PR scope is *adding* those sections — do not edit existing content.

7. **For issue-path remediations**,
   draft the issue body (template below) listing the gaps with section citations and the rationale ("the Frontier Model Preparation scan needs §11a to suppress recurring false positives; without it the noise rate is X-fold higher").

8. **Show the artefact and wait.**
   Render full PR diff (or issue body), the target repo, and the proposed title.
   Wait for explicit "open" / "go" / "send".

9. **Execute via `gh`** —
   see the **GitHub mechanics** section below for the exact commands.

10. **Record outcome.**
    After opening an issue or PR,
    surface the URL and propose recording it in the PMC's `Notes` cell in the tracker via `frontier-model-preparation-update`.
    After verification passes,
    propose flipping `Security model verified` to today via the same SKILL.
    In both cases the user runs the actual write —
    this SKILL drafts; the update SKILL applies.

## Remediation decision table

| Failure | Default path | Why |
| --- | --- | --- |
| `AGENTS.md` missing entirely | PR creating the file with a single Security line | Mechanical, one-file add. PMC reviews + merges in a minute. |
| `AGENTS.md` present, no link to `SECURITY.md` / model | PR adding one line | Mechanical, no maintainer input needed. |
| `SECURITY.md` missing but model file exists | PR creating `SECURITY.md` stub linking to it | Mechanical, PMC just needs to ratify the canonical pointer. |
| `SECURITY.md` exists but doesn't link to a model and has no embedded model content | Email reply | PMC needs to decide where the model lives. |
| Project-site URL 404 / redirects | Email reply | PMC owns the destination, not us. |
| 1–2 model sections missing, project public artefacts are rich enough to draft from | PR with draft additions via `threat-model-producer` | Maintainer reacts to a concrete starting point. |
| ≥ 3 model sections missing, OR §7 adversary / §8 properties absent | Email reply listing all gaps with rubric citations | Substantive work that the PMC has to drive. Drafting it all unsolicited is too much. |
| Sections present but tagged with hedge-words (`(implicit)`, `(generally known)`) | Email reply with a one-line note about provenance tagging discipline | Not blocking the scan per se, but worth flagging. |
| §11a (known non-findings) missing on a project that's been scanned before | Email reply with offer to draft from prior scan findings on request | Highest-leverage section but only the maintainer knows which findings were false positives. |

When in doubt,
lean toward **email reply** with the explicit offer to draft a PR if the PMC prefers.
PRs that the PMC has to triage unsolicited can land worse than emails that ask them to choose.
**Never** open a GitHub issue against the PMC's repo —
many Apache projects do not have issues enabled (Tomcat is the textbook example),
and even where issues exist they are not the channel PMC members watch.

## Templates

### Template 1 — PR: add Security line to existing `AGENTS.md`

**Title**: `AGENTS.md: link the project's security model for agent discoverability`

**Branch**: `asf-security/agents-md-security-link-<YYYY-MM-DD>`

**Diff** (the existing `AGENTS.md` plus one inserted section, inserted at a sensible spot — usually right after the introduction, or at the end if the file is short):

```markdown
## Security

Security model: [SECURITY.md](./SECURITY.md)

Agents that scan this repository should consult `SECURITY.md`
for the project's threat model, in-scope / out-of-scope
declarations, and known non-findings before reporting issues.
```

**PR body**:

```markdown
**This is a proposal for the PMC to review — please correct,
reject, or discuss as needed.** Nothing here is a requirement;
the maintainer is the decision-maker.

This adds a Security section to `AGENTS.md` so an automated
scan agent can mechanically discover the project's security
model via the conventional `AGENTS.md → SECURITY.md` chain.

Context: the ASF Security team is preparing the project for an
automated agentic security scan we're piloting. Such scans
refuse to run if the model isn't discoverable by that path
(refusing upfront beats wasting PMC reviewer cycles on a
noise-heavy run against an unknown model). Discoverability is
the one hard gate; everything else is suggestion. The Security
team has reached out separately on the PMC's private list with
the program details; this PR is the public-facing repo piece.

The Security team uses
[`threat-model-producer`](https://gist.github.com/potiuk/da14a826283038ddfe38cc9fe6310573)
as the rubric for what a complete model looks like — but this
PR is just the *link*; nothing about the model content itself
changes.

Questions / pushback welcome. Happy to adjust the wording or
move the section if the project has a house style.
```

### Template 2 — PR: create `AGENTS.md` from scratch

**Title**: `Add AGENTS.md with security-model link for agent discoverability`

**Branch**: `asf-security/agents-md-init-<YYYY-MM-DD>`

**New file** `AGENTS.md`:

```markdown
# Agent guidance

This file is read by automated agents (security scanners, code
analyzers, AI assistants) operating on this repository. It
points them at the human-authored references they should
consult before producing output.

## Security

Security model: [SECURITY.md](./SECURITY.md)

Agents that scan this repository should consult `SECURITY.md`
for the project's threat model, in-scope / out-of-scope
declarations, and known non-findings before reporting issues.
```

**PR body**: same shape as Template 1 (no "Frontier Model Preparation" mention; generic "an automated agentic security scan we're piloting" phrasing), framed as the file-creation case.

### Template 3 — PR: add draft sections via `threat-model-producer`

**Title**: `SECURITY.md: draft additions for <list of section numbers>`

**Branch**: `asf-security/security-model-additions-<YYYY-MM-DD>`

**Diff**: append the generated sections to the existing model,
each carrying provenance tags per §3.3 of the producer SKILL.
Group all the `*(inferred)*` claims into a fresh §14 Open questions block at the end (or merge into the existing one).

**PR body skeleton**:

```markdown
**This is a proposal for the PMC to review — please correct,
reject, or discuss as needed.** Every claim in the diff is
tagged with provenance (*(documented)* / *(inferred)*); the
*(inferred)* tags are the agent's guesses for you to confirm
or strike. The scan does not require these sections to be
filled in before it runs — it just runs better when they are.

Context: the ASF Security team is preparing this project for
an automated agentic security scan we're piloting. Per the
[`threat-model-producer`](https://gist.github.com/potiuk/da14a826283038ddfe38cc9fe6310573)
rubric — this PR proposes **draft** content for the following
currently-empty sections, written from the project's own
public artefacts (README, docs, header comments, FAQ):

- §<NN> <Section name>
- §<NN> <Section name>
- §<NN> <Section name>

Every claim in the draft carries a provenance tag:

- *(documented)* — lifted from a project doc; cited.
- *(inferred)* — agent guess from code structure or domain
  norms. **Every *(inferred)* tag has a matching question in
  §14 "Open questions"** for the PMC to confirm, correct,
  or strike.

What's needed from the PMC:

1. Walk the §14 questions and answer in-thread (a one-line
   confirm / correct / strike per question is enough — see the
   producer SKILL §3.2 for the "react, don't compose" pattern).
2. We'll fold the answers in and the *(inferred)* tags will
   become *(maintainer)*.

This PR does not edit any existing model content — only adds
the missing sections. If the PMC would rather draft these
sections themselves, close the PR and open a tracking issue —
we'll wait.
```

### Template 4 — Email reply: gaps in model, PMC drives

The email replies to the original `[GLASSWING] <PMC>: request to scan repositories` thread.
To/CC follow the `frontier-model-preparation-response` rules (reply to the requester; CC `security@apache.org`; CC `private@<pmc>.apache.org`; **always CC the Tooling PMC private list `private@tooling.apache.org`** — the Tooling team's channel for the scanning effort; keep anyone already on the thread).
**Always go through the `frontier-model-preparation-response` flow for the final draft + Gmail draft creation** —
this SKILL drafts the body and hands it off;
it does not call the Gmail tools directly.

**Subject** (verbatim with `Re:` if replying): `Re: [GLASSWING] <PMC>: request to scan repositories`

**Body skeleton**:

```text
Hi <primary contact first name>,

Status update on the pre-flight for the Frontier Model Preparation scan against
<PMC name>:

[If a PR was opened:]
- **Discoverability**: addressed in <PR URL> — adds AGENTS.md
  + SECURITY.md so the scan agent can mechanically follow the
  conventional chain to your existing model at
  <model URL or path>. Feel free to adjust wording / file
  placement before merging; close it and we'll regroup if you
  prefer a different shape.

[If discoverability passed already:]
- **Discoverability**: passes. <one-line note on how — e.g.
  "your AGENTS.md already points the scan agent at the model
  + VDR + FAQ; no repo changes needed".>

- **Completeness against the minimum bar**: your current
  model is substantive on <list the sections that landed
  well — e.g. "scope, out-of-scope, inputs, downstream
  responsibilities">. We ran it against the rubric in
  https://gist.github.com/potiuk/da14a826283038ddfe38cc9fe6310573
  and flagged a few gaps as suggestions (nothing here blocks
  the scan; closing them reduces noise in the output):

    * §<NN> <Section name> — <one-line description of what's
      missing and why the scan benefits from it. Be specific;
      cite the rubric subsection.>
    * §<NN> <Section name> — ...
    * §<NN> <Section name> — ...

Two paths forward, either works for us:

1. You drive — walk the gaps section by section, ping us when
   you'd like a re-check.
2. We draft. We can run the threat-model-producer recipe
   (https://gist.github.com/potiuk/da14a826283038ddfe38cc9fe6310573)
   against your repo's public artefacts, open a PR with
   *(inferred)*-tagged drafts for each gap, and collect the
   open questions at the end so you react to a concrete
   starting point rather than compose from scratch. Usually
   faster.

No timeline pressure — the scan is queued behind verification,
not a date. Reply when convenient.

[Sign off in the human's voice — the SKILL doesn't sign for
them.]
```

The email is from the ASF Security team's voice,
signed by the human who reviews and sends it (Jarek or another team member).
Plain text; no marketing flourish; lengths proportional to the size of the assessment.

### Template 5 — Email reply: model not discoverable, PMC chooses path

Reply to the original `[GLASSWING]` thread;
same recipient conventions as Template 4.

**Subject**: `Re: [GLASSWING] <PMC>: request to scan repositories`

**Body skeleton**:

```text
Hi <primary contact first name>,

Status update on the pre-flight for <PMC name>:

- **Discoverability**: fails right now. The scan agent needs
  to mechanically locate the project's threat model via the
  chain AGENTS.md -> SECURITY.md -> <model>. Currently
  <one-line description of the broken link — e.g. "SECURITY.md
  exists but has no link to a model, and we couldn't find an
  embedded model in it" / "the link in SECURITY.md to
  https://... returns 404" / "no AGENTS.md / SECURITY.md in
  the repo, and we couldn't find a security model anywhere
  obvious on your project website">.

  Discoverability is the one hard gate for the scan — without
  the chain resolving, the scan agent refuses to run. (Refusing
  upfront beats wasting your reviewers on a noise-heavy run
  against a model the agent never found.) But the PMC decides
  where the model lives:

    (a) put the model in SECURITY.md (or link from there to an
        in-repo path);
    (b) host the model on the project website and link from
        SECURITY.md;
    (c) something else — this is your project.

  Once we know where you'd like the model to live, we can open
  a small PR wiring the AGENTS.md -> SECURITY.md -> model
  chain. We'll wait on direction before doing anything in your
  repo.

[If completeness was *also* assessable: add the same gap-list
block from Template 4 here, framed as "for after the discovery
chain is wired".]

No timeline pressure — the scan is queued behind verification,
not a date.

[Sign off in the human's voice.]
```

## GitHub mechanics

The Security-team member running this SKILL is acting via their `gh` CLI auth (their Apache GitHub identity).
The `apache/security` repo's PR-creation workflow applies to PRs opened on third-party `apache/<repo>` repos too.

### Opening an issue

Use `--web` so the user reviews the rendered form in the browser before clicking Submit.
The `--title` and `--body-file` flags pre-fill the issue form;
nothing is created until the user submits in-browser.

```
gh issue create \
  --repo apache/<repo> \
  --title "<title>" \
  --body-file "$TMPDIR/frontier-model-preparation-issue-<timestamp>.md" \
  --web
```

### Opening a PR (small structural fix)

**Preferred: the `model-pr` helper** (`tools/model_pr/`) collapses the whole fork → clone → write the `AGENTS.md → SECURITY.md → model` scaffold (create-or-append, idempotent — it handles the fiddly "create when absent / append one section when present" branch on `SECURITY.md` and `AGENTS.md`) → commit → push → `gh pr create --web` flow into one command:

```bash
# in-repo model (lands THREAT_MODEL.md, wires AGENTS.md -> SECURITY.md -> it):
uv run --project tools/model_pr model-pr open \
  --repo apache/<repo> --model <THREAT_MODEL.md> --date <YYYY-MM-DD> \
  --title "<title>" --body-file "$TMPDIR/frontier-model-preparation-pr-<ts>.md"

# pointer to an umbrella model hosted in another repo:
uv run --project tools/model_pr model-pr open \
  --repo apache/<repo> --pointer <umbrella-model-URL> --date <YYYY-MM-DD> \
  --agents-note "<one-line role note>"
```

It opens the PR with `gh pr create --web` by default (you submit in-browser — the same second gate as the manual flow);
pass `--dry-run` to build the files and show the staged diff without committing, or `--submit` to create the PR non-interactively.
The file-merge core is unit-tested.
The manual steps below are the equivalent it runs under the hood, kept for cases it doesn't cover (issues, non-scaffold edits).

Use a worktree to keep the local state clean.
The branch push happens via `git push` (local-to-remote, no user review surface);
the PR creation goes through `--web` so the user reviews the rendered diff + title + body in the browser before clicking Submit.

```
git -C /tmp/clones clone --depth 1 \
  https://github.com/apache/<repo>.git <repo>
cd /tmp/clones/<repo>
git checkout -b asf-security/<purpose>-<YYYY-MM-DD>
# make the edit
git add <files>
git commit -m "$(cat <<'EOF'
<commit subject>

<commit body — same content as the PR body's first paragraph>

Generated-by: Claude Code (Claude Opus 4.7)
EOF
)"
git push -u origin asf-security/<purpose>-<YYYY-MM-DD>
gh pr create \
  --repo apache/<repo> \
  --title "<title>" \
  --body-file "$TMPDIR/frontier-model-preparation-pr-<timestamp>.md" \
  --web
```

If the Security-team account doesn't have push access to `apache/<repo>` (most apache repos require committer status to push branches directly),
fall back to a fork:

```
gh repo fork apache/<repo> --remote=false --clone=false
# push to the fork instead, then:
gh pr create \
  --repo apache/<repo> \
  --head <your-handle>:asf-security/<purpose>-<YYYY-MM-DD> \
  --title "<title>" \
  --body-file "$TMPDIR/frontier-model-preparation-pr-<timestamp>.md" \
  --web
```

### Always dry-run the PR diff first

Run `git diff main` (or against the appropriate base branch) and show the user before pushing.
The push + `gh pr create --web` combo is what surfaces the artefact to GitHub —
every step before it is local and revertible.
The `--web` step is the *second* gate (the first being the in-conversation draft-and-confirm);
nothing is submitted to GitHub until the user clicks Submit in the browser.

## Hand-off after verification

Verification has three possible exit shapes;
each hands off to a different downstream SKILL.

### A. Verification passes (or passes with soft gaps)

Surface the model-verified handoff offer:

> Ready to mark `<pmc-slug>` as model-verified at
> `<YYYY-MM-DD>`. Want me to invoke `frontier-model-preparation-update`
> to set `Security model verified` on that row?

**Do not** offer to invoke `frontier-model-preparation-submit` here.
Pre-flight pass is not a trigger for submission anymore —
the next step is `frontier-model-preparation-response`'s pre-flight-pass template (OSS-expedite pitch + ready-to-scan notification), sent to the PMC.
Submission to ASF Tooling (via the form flow) only fires after the PMC has replied with their expedite-account list (or `none`) **and** the operator has explicitly said "submit X".
See `frontier-model-preparation-run`'s `pre-flight-passed-pitch-not-sent` and `pmc-pitch-replied-awaiting-operator-decision` pipeline states for the gating logic.

### B. PR opened (discoverability fix) but pre-flight not yet complete

Surface:

> Opened PR #<n> at `<url>`. Want me to log this in the
> tracker's `PR/Issues` column for `<pmc-slug>` via
> `frontier-model-preparation-update`? Verification will be re-run once
> the PR is merged; the pre-flight-pass pitch (and any
> eventual scan submission) waits on that.

### C. Email reply drafted (substantive gaps)

After the user sends the email, surface:

> Email reply drafted to <recipient>. After you send, want me
> to log "Email reply sent <YYYY-MM-DD>" in the tracker's
> `PR/Issues` column for `<pmc-slug>` via
> `frontier-model-preparation-update`? The pre-flight-pass pitch (and any
> eventual scan submission) waits on the PMC's response.

In all three shapes,
the user issues the next instruction and the downstream SKILL takes over with its own draft-and-confirm flow.
This SKILL does not write to the spreadsheet or call Gmail tools directly.

## Style notes

- **Concrete over abstract.**
  "Your model doesn't have a §11a section" beats "your model has gaps".
  Cite the rubric.
- **Single ask per artefact.**
  Per hard rule 2, one remediation per failing check.
- **Don't lecture.**
  Link to `threat-model-producer` rather than re-explaining what a threat model is.
  The PMC's threat model is *their* document;
  the rubric exists to help, not to impose.
- **Don't restate what the recipient already knows.**
  A quick acknowledgment of where things stand is fine;
  full re-explanation of the pre-flight pipeline / sanity-check mechanics / why discoverability matters belongs in the initial scan-response thread, not in every follow-up.
  Keep status updates short: what passed, what didn't, what's the ask.
  Trust prior thread context.
- **Maintainer voice in the *output*, not Security-team voice.**
  When generating model section drafts via the producer SKILL,
  the prose should read as if the project wrote it about itself — first person plural, project-specific examples.
  The Security-team voice is only the PR body / issue body / this SKILL's own prose.
- **Provenance discipline is the producer SKILL's job;
  don't shortcut it.**
  Every drafted claim must carry exactly one of `*(documented)*` / `*(maintainer)*` / `*(inferred)*`.
  Hedge variants ("*(implicit)*", "*(generally known)*") are not allowed —
  the producer SKILL §3.3 is explicit about that.

## Examples of bad outputs (avoid)

- A PR that "fixes" the model by editing existing claims the maintainer wrote.
  Violates hard rule 5.
  The SKILL identifies gaps; it does not rewrite.
- A PR opened against `apache/<repo>` without prior dry-run approval.
  Violates hard rule 1.
- An issue body that lists every section of the producer rubric as a checkbox.
  The PMC doesn't need the entire rubric pasted —
  they need the *gaps* highlighted with citations.
- A PR diff with `Generated-by: Claude Code` as the only context.
  The reader needs the Security-team rationale for the change in the PR body;
  the trailer is a footnote.
- A grab-bag remediation that combines the `AGENTS.md` link fix with model-section additions in one PR.
  Violates hard rule 2 — split.
- Calling the spreadsheet write directly from this SKILL.
  Always hand off to `frontier-model-preparation-update` so the diff-and-confirm gate fires.

## Provenance

This SKILL formalizes the pre-flight discoverability + model-completeness check that `frontier-model-preparation-response`'s "Hard pre-flight" rule alludes to.
The completeness rubric is the minimum-bar subset of [`threat-model-producer`](../threat-model-producer/SKILL.md); the full producer rubric is the standard a model aspires to, this SKILL enforces only the slice the scan agent depends on mechanically.

The remediation patterns (small structural fix → PR; substantive gap → issue) match what Jarek has been doing manually for the first wave of opted-in PMCs.
