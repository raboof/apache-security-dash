---
name: glasswing-model-verify
description: Pre-flight verification step in the Glasswing scan pipeline. Given a PMC's nominated security model (file path or URL in their repo), check two things — (1) discoverability via AGENTS.md -> SECURITY.md so the scan agent can mechanically find it, and (2) completeness against the threat-model-producer rubric (the SKILL bound in this same repo). Produce a concrete remediation: either open a GitHub issue listing the gaps, or — when the gap is mechanical (e.g. AGENTS.md missing the link line, or a small set of missing sections) — generate the additions via threat-model-producer and open a PR with the diff. After verification passes, hand off to glasswing-scan-update to flip the `Security model verified` cell for that PMC. Use whenever a PMC nominates a security model (in their [GLASSWING] request, in a reply, or in their repo) and the Security team needs to confirm it before queuing the scan. Read-only assessment by default; external writes (issue / PR / spreadsheet) are gated on explicit user approval.
---

# Glasswing model-verify SKILL

Bridges `glasswing-scan-response` (where a PMC nominates a model)
and `glasswing-scan-update` (where the verified-date gets
recorded). The SKILL's job is the mechanical pre-flight check the
scan-response SKILL's hard rule alludes to — and to produce the
concrete remediation when the check fails.

## When to invoke

- A PMC has nominated a security model in their `[GLASSWING]`
  request, in a follow-up reply, or by pointing at a path in
  their repo (`docs/threat-model.md`, `SECURITY.md`, a wiki page,
  etc.).
- Before queuing a scan run, the Security team needs to confirm
  the model is (a) mechanically discoverable via
  `AGENTS.md → SECURITY.md` and (b) materially complete enough
  that the scan output won't drown the PMC in noise.
- A PMC asks "is our existing threat model good enough for
  Glasswing?" and wants a concrete read.

Skip when there's no nominated model yet — that's a prerequisite
handled by `glasswing-scan-response` (the discoverability rule:
no model, no scan).

## Inputs

- **PMC slug** (e.g. `logging`, `apisix`) — used to locate the
  PMC's row in the tracker afterwards.
- **Repo** (e.g. `apache/logging-log4j2`) — the GitHub repo to
  assess.
- **Commit / branch** (default `HEAD` of the default branch) —
  the scan binds to a specific commit, and the model is read at
  that commit; pin if the PMC named one.
- **Nominated model path or URL** (optional) — if the PMC said
  "our model is at `docs/security/threat-model.md`" or pointed
  at a project-site page, start there; otherwise the SKILL
  derives the path from `AGENTS.md` (or its absence).

## Hard rules (do not skip)

1. **No external write without explicit user approval.** This is
   the same draft-and-confirm rule as the other Glasswing SKILLs:
   show the issue body or PR diff, wait for "yes / open / go",
   then invoke `gh issue create` / `gh pr create`. Never invoke
   the GitHub write tools before showing the artefact.

2. **One remediation per failing check, not a grab bag.** If
   discoverability fails *and* completeness fails, produce two
   separate artefacts (e.g. one PR adding the `AGENTS.md` link,
   one issue listing the missing model sections) rather than one
   omnibus PR that the PMC has to negotiate as a unit. Small,
   targeted asks land faster.

3. **Use the project's own voice for proposed model content.**
   When generating threat-model section drafts via
   `threat-model-producer`, every claim must carry a
   `*(documented)*` / `*(maintainer)*` / `*(inferred)*` tag, and
   every `*(inferred)*` claim must route to a matching open
   question in §4.14. Do not silently fabricate maintainer
   positions. The PR is a *starting point* for the PMC to react
   to, not a finished model.

4. **Default to *issue* for substantive gaps; default to *PR*
   for mechanical fixes.** A missing `AGENTS.md` link is
   mechanical (one-line add). A missing §4.8 "Properties
   provided" section is substantive (needs maintainer input).
   Borderline cases (e.g. missing §4.11a known-non-findings
   list) lean toward issue with an offer to draft on request.

5. **Pre-flight is a check, not a re-write.** Never propose
   changes to *existing* model content unless the PMC asked. The
   SKILL identifies gaps and proposes *additions* (and the one
   structural fix of the `AGENTS.md → SECURITY.md` link). Edits
   to existing claims are the PMC's call.

6. **After verification passes, hand off — don't write the
   spreadsheet directly.** The SKILL produces a short
   handoff line ("Verified for `<pmc-slug>` at `<sha>` —
   ready to flip `Security model verified` to `<today>`"); the
   user then invokes `glasswing-scan-update` to apply that
   change.

## The rubric — what "verified" means

Two checks. Both must pass for verification to succeed.

### Check A — Discoverability

The scan agent finds the model by mechanically following
`AGENTS.md → SECURITY.md → model`. The chain must terminate at
a real artefact at the designated commit.

Acceptable terminations:

- The threat model is in `SECURITY.md` itself.
- `SECURITY.md` links to an in-repo file (e.g.
  `docs/threat-model.md`) and that file exists at the commit.
- `SECURITY.md` links to a project-site URL (e.g.
  `https://<pmc>.apache.org/security/threat-model/`) and the URL
  resolves to a model document. The website is acceptable per
  the threat-model-producer §3.1 rule.

Check failures:

| Failure | Mechanical fix? |
| --- | --- |
| `AGENTS.md` does not exist in the repo. | Yes — create with the minimum scaffold (one Security line linking to `SECURITY.md`). |
| `AGENTS.md` exists but has no link to `SECURITY.md` (or to a model file). | Yes — add the one-line link. |
| `AGENTS.md` links to `SECURITY.md` but `SECURITY.md` does not exist. | Sometimes — if a model lives at a known path, propose adding `SECURITY.md` as a stub pointing at it. Otherwise this is a PMC issue. |
| `SECURITY.md` exists but contains no link to a model and no embedded model content. | Issue, not PR — the PMC needs to decide what to point at. |
| The link target is a project-site URL that 404s, redirects to login, or is empty. | Issue — the PMC needs to fix the destination. |

### Check B — Completeness

Read the model. Cross-check against the threat-model-producer
rubric (the SKILL at `.github/skills/threat-model-producer/`).
The *minimum bar* for a Glasswing-ready model is the sections
below; each must either contain substantive content or be marked
`Not applicable — <reason>`.

| Section | Why the scan needs it |
| --- | --- |
| §4.2 Scope and intended use (with the component-family table) | Tells the scan which directories are in-model. Without it, every finding in `examples/` or `contrib/` lands on the PMC's plate. |
| §4.3 Out of scope (explicit non-goals) | The complement of §4.2 — same reasoning. |
| §4.6 Inputs and the per-parameter trust table | Triagers route findings against specific sinks; prose alone isn't enough. |
| §4.7 Adversary model | Lets the agent classify "in-model attacker" vs "out-of-model attacker" without re-deriving. |
| §4.8 Security properties provided (with violation symptom + severity) | The "what's a real bug" list. The single most-cited section in triage. |
| §4.9 Security properties *not* provided (with false-friends + well-known attack classes) | Pre-empts the most common false-positive category. |
| §4.10 Downstream responsibilities | What the integrator must do — clarifies which finding categories aren't the project's bug. |
| §4.11a Known non-findings | The recurring-false-positive list that feeds the scan agent's suppression. **Highest leverage section for noise reduction.** |
| §4.13 Triage dispositions | The closed set of routing outcomes. Without it, every finding is implicitly `MODEL-GAP`. |

Sections explicitly **not** part of the minimum bar (nice to
have, but verification passes without them):

- §4.5a Build-time and configuration variants — only required
  if the project has security-relevant build flags.
- §4.15 Machine-readable companion (`threat-model.yaml`) —
  optional; useful but not blocking.

If a section is `Not applicable — <reason>`, verification passes
for that section (the maintainer has thought about it and ruled
it out). Empty headings with no commentary count as missing.

## Procedure

1. **Resolve the inputs.** Confirm PMC slug, repo, and commit
   (default to the repo's default-branch HEAD if the request
   didn't pin one). If the PMC named a specific model path, use
   it; otherwise start from `AGENTS.md`.

2. **Run discoverability (Check A).** Use `gh api` to fetch the
   relevant files; do not clone unless preparing a PR. Example:

   ```
   gh api repos/<owner>/<repo>/contents/AGENTS.md?ref=<sha>
   ```

   For each link traversal, fetch the next file. For external
   URLs, use `curl --head` (or the `WebFetch` tool) to confirm
   the URL resolves to a 200 with a document body.

3. **Run completeness (Check B).** Read the model. Walk the
   rubric table above; for each minimum-bar section, mark
   **present** / **partial** / **missing** / **explicit N/A**.
   "Partial" means the section heading exists but the content
   is one-line / placeholder / clearly under-specified relative
   to the rubric.

4. **Summarize the assessment.** Format:

   ```
   Discoverability: PASS / FAIL — <one-line reason>
   Completeness:
     §4.2 Scope                  present / partial / missing
     §4.3 Out of scope           ...
     §4.6 Inputs                 ...
     §4.7 Adversary              ...
     §4.8 Properties provided    ...
     §4.9 Properties not         ...
     §4.10 Downstream resp.      ...
     §4.11a Known non-findings   ...
     §4.13 Triage dispositions   ...
   ```

5. **Decide remediation per failing check** using the decision
   table below. Show the user the assessment plus the proposed
   remediation, wait for approval before writing.

6. **For PR-path remediations**, draft the diff:

   - **AGENTS.md missing**: create with the minimum scaffold
     (see template below).
   - **AGENTS.md present, no link**: insert a single Security
     section.
   - **Model sections missing**: invoke `threat-model-producer`
     against the repo's public artefacts to generate drafts for
     each missing section, with every claim carrying a
     provenance tag (predominantly `*(inferred)*` on first
     draft) and corresponding §4.14 open questions. The PR
     scope is *adding* those sections — do not edit existing
     content.

7. **For issue-path remediations**, draft the issue body
   (template below) listing the gaps with section citations and
   the rationale ("the Glasswing scan needs §4.11a to suppress
   recurring false positives; without it the noise rate is
   X-fold higher").

8. **Show the artefact and wait.** Render full PR diff (or
   issue body), the target repo, and the proposed title. Wait
   for explicit "open" / "go" / "send".

9. **Execute via `gh`** — see the **GitHub mechanics** section
   below for the exact commands.

10. **Record outcome.** After opening an issue or PR, surface
    the URL and propose recording it in the PMC's `Notes` cell
    in the tracker via `glasswing-scan-update`. After
    verification passes, propose flipping
    `Security model verified` to today via the same SKILL. In
    both cases the user runs the actual write — this SKILL
    drafts; the update SKILL applies.

## Remediation decision table

| Failure | Default path | Why |
| --- | --- | --- |
| `AGENTS.md` missing entirely | PR creating the file with a single Security line | Mechanical, one-file add. PMC reviews + merges in a minute. |
| `AGENTS.md` present, no link to `SECURITY.md` / model | PR adding one line | Mechanical, no maintainer input needed. |
| `SECURITY.md` missing but model file exists | PR creating `SECURITY.md` stub linking to it | Mechanical, PMC just needs to ratify the canonical pointer. |
| `SECURITY.md` exists but doesn't link to a model and has no embedded model content | Issue | PMC needs to decide where the model lives. |
| Project-site URL 404 / redirects | Issue | PMC owns the destination, not us. |
| 1–2 model sections missing, project public artefacts are rich enough to draft from | PR with draft additions via `threat-model-producer` | Maintainer reacts to a concrete starting point. |
| ≥ 3 model sections missing, OR §4.7 adversary / §4.8 properties absent | Issue listing all gaps with rubric citations | Substantive work that the PMC has to drive. Drafting it all unsolicited is too much. |
| Sections present but tagged with hedge-words (`(implicit)`, `(generally known)`) | Issue with a one-line note about provenance tagging discipline | Not blocking the scan per se, but worth flagging. |
| §4.11a (known non-findings) missing on a project that's been scanned before | Issue with offer to draft from prior scan findings on request | Highest-leverage section but only the maintainer knows which findings were false positives. |

When in doubt, lean toward **issue** with the explicit offer to
draft a PR if the PMC prefers. PRs that the PMC has to triage
unsolicited can land worse than issues that ask them to choose.

## Templates

### Template 1 — PR: add Security line to existing `AGENTS.md`

**Title**: `AGENTS.md: link the project's security model for agent discoverability`

**Branch**: `asf-security/agents-md-security-link-<YYYY-MM-DD>`

**Diff** (the existing `AGENTS.md` plus one inserted section,
inserted at a sensible spot — usually right after the
introduction, or at the end if the file is short):

```markdown
## Security

Security model: [SECURITY.md](./SECURITY.md)

Agents that scan this repository should consult `SECURITY.md`
for the project's threat model, in-scope / out-of-scope
declarations, and known non-findings before reporting issues.
```

**PR body**:

```markdown
This adds a Security section to `AGENTS.md` so an automated
scan agent can mechanically discover the project's security
model via the conventional `AGENTS.md → SECURITY.md` chain.

The ASF Security team is preparing the project for a Glasswing
agentic security scan; the scan refuses to run if the model
isn't discoverable by that path (refusing upfront beats wasting
PMC reviewer cycles on a noise-heavy run against an unknown
model).

The Security team uses
[`threat-model-producer`](https://github.com/apache/security/blob/main/.github/skills/threat-model-producer/SKILL.md)
as the rubric for what counts as a complete model — but this
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

**PR body**: same as Template 1, framed as the file-creation
case.

### Template 3 — PR: add draft sections via `threat-model-producer`

**Title**: `SECURITY.md: draft additions for <list of section numbers>`

**Branch**: `asf-security/security-model-additions-<YYYY-MM-DD>`

**Diff**: append the generated sections to the existing model,
each carrying provenance tags per §3.3 of the producer SKILL.
Group all the `*(inferred)*` claims into a fresh §4.14 Open
questions block at the end (or merge into the existing one).

**PR body skeleton**:

```markdown
The ASF Security team is preparing this project for a
Glasswing agentic security scan. Per the scan's discoverability
gate, the project's security model needs to cover the rubric
in
[`threat-model-producer`](https://github.com/apache/security/blob/main/.github/skills/threat-model-producer/SKILL.md)
— this PR proposes **draft** content for the following
currently-empty sections, written from the project's own
public artefacts (README, docs, header comments, FAQ):

- §<NN> <Section name>
- §<NN> <Section name>
- §<NN> <Section name>

Every claim in the draft carries a provenance tag:

- *(documented)* — lifted from a project doc; cited.
- *(inferred)* — agent guess from code structure or domain
  norms. **Every *(inferred)* tag has a matching question in
  §4.14 "Open questions"** for the PMC to confirm, correct,
  or strike.

What's needed from the PMC:

1. Walk the §4.14 questions and answer in-thread (a one-line
   confirm / correct / strike per question is enough — see the
   producer SKILL §3.2 for the "react, don't compose" pattern).
2. We'll fold the answers in and the *(inferred)* tags will
   become *(maintainer)*.

This PR does not edit any existing model content — only adds
the missing sections. If the PMC would rather draft these
sections themselves, close the PR and open a tracking issue —
we'll wait.
```

### Template 4 — Issue: gaps in model, PMC drives

**Title**: `Threat model gaps to address before Glasswing scan (<PMC name>)`

**Body skeleton**:

```markdown
The ASF Security team is preparing this project for a Glasswing
agentic security scan. The scan reads the project's threat
model to suppress known non-findings and route findings to the
correct triage disposition — without a model that covers the
minimum rubric, the scan output's false-positive rate is high
enough to be unfair to PMC reviewers.

We ran a pre-flight check against the current model at
`<path-to-model>@<sha>` using the rubric from
[`threat-model-producer`](https://github.com/apache/security/blob/main/.github/skills/threat-model-producer/SKILL.md).
Discoverability passes; the minimum-bar completeness check
flags the following gaps:

- [ ] **§<NN> <Section name>** — <one-line description of
  what's missing and why the scan needs it>
- [ ] **§<NN> <Section name>** — ...
- [ ] **§<NN> <Section name>** — ...

Two paths forward — either is fine; let us know which you
prefer:

1. **You draft.** Walk through the producer rubric section by
   section. We'll re-run the pre-flight when you ping us.
2. **We draft via the producer SKILL.** We can open a PR with
   `*(inferred)*`-tagged drafts for each missing section, with
   the open questions collected at the end for you to react to
   rather than compose from scratch. This is usually faster.

No timeline pressure — the scan is queued behind verification,
not behind a date.
```

### Template 5 — Issue: model not discoverable, PMC chooses path

**Title**: `Security model not discoverable via AGENTS.md → SECURITY.md (<PMC name>)`

**Body skeleton**:

```markdown
The Glasswing scan needs to mechanically locate the project's
threat model via the chain `AGENTS.md → SECURITY.md → <model>`.
Right now <description of the broken link — e.g. "SECURITY.md
exists but has no link to a model, and we can't find an
embedded model in it" / "the link in SECURITY.md to
`https://<...>` returns 404">.

If the model is already written somewhere we just haven't
found, point us at it and we'll close this. Otherwise the PMC
needs to decide:

- (a) put the model in `SECURITY.md` (or link it from there to
  an in-repo path);
- (b) host the model on the project website and link from
  `SECURITY.md`; or
- (c) something else — open to suggestions, this is your
  project.

We can help with the mechanics in any of those (PR opening the
links once we know where to point) — happy to drive once
direction's clear.
```

## GitHub mechanics

The Security-team member running this SKILL is acting via their
`gh` CLI auth (their Apache GitHub identity). The
`apache/security` repo's PR-creation workflow applies to PRs
opened on third-party `apache/<repo>` repos too.

### Opening an issue

```
gh issue create \
  --repo apache/<repo> \
  --title "<title>" \
  --body-file "$TMPDIR/glasswing-issue-<timestamp>.md"
```

### Opening a PR (small structural fix)

Use a worktree to keep the local state clean:

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
  --body-file "$TMPDIR/glasswing-pr-<timestamp>.md"
```

If the Security-team account doesn't have push access to
`apache/<repo>` (most apache repos require committer status to
push branches directly), fall back to a fork:

```
gh repo fork apache/<repo> --remote=false --clone=false
# push to the fork instead, then:
gh pr create \
  --repo apache/<repo> \
  --head <your-handle>:asf-security/<purpose>-<YYYY-MM-DD> \
  ...
```

### Always dry-run the PR diff first

Run `git diff main` (or against the appropriate base branch)
and show the user before pushing. The push + `gh pr create`
combo is the actual write — everything before it is local and
revertible.

## Hand-off to `glasswing-scan-update`

After verification passes, surface a single line that the user
pastes into the next turn:

> Ready to mark `<pmc-slug>` as model-verified at `<YYYY-MM-DD>`.
> Want me to invoke `glasswing-scan-update` to set
> `Security model verified` on that row?

After an issue or PR opens, surface:

> Opened <type> #<n> at `<url>`. Want me to log this in the
> tracker's `Notes` column for `<pmc-slug>` via
> `glasswing-scan-update`?

In both cases, the user issues the next instruction and the
update SKILL does the spreadsheet write through its own diff-
and-confirm flow. This SKILL does not write to the spreadsheet
directly.

## Style notes

- **Concrete over abstract.** "Your model doesn't have a §4.11a
  section" beats "your model has gaps". Cite the rubric.
- **Single ask per artefact.** Per hard rule 2, one
  remediation per failing check.
- **Don't lecture.** Link to `threat-model-producer` rather
  than re-explaining what a threat model is. The PMC's threat
  model is *their* document; the rubric exists to help, not to
  impose.
- **Maintainer voice in the *output*, not Security-team voice.**
  When generating model section drafts via the producer SKILL,
  the prose should read as if the project wrote it about
  itself — first person plural, project-specific examples.
  The Security-team voice is only the PR body / issue body /
  this SKILL's own prose.
- **Provenance discipline is the producer SKILL's job; don't
  shortcut it.** Every drafted claim must carry exactly one of
  `*(documented)*` / `*(maintainer)*` / `*(inferred)*`. Hedge
  variants ("*(implicit)*", "*(generally known)*") are not
  allowed — the producer SKILL §3.3 is explicit about that.

## Examples of bad outputs (avoid)

- A PR that "fixes" the model by editing existing claims the
  maintainer wrote. Violates hard rule 5. The SKILL identifies
  gaps; it does not rewrite.
- A PR opened against `apache/<repo>` without prior dry-run
  approval. Violates hard rule 1.
- An issue body that lists every section of the producer
  rubric as a checkbox. The PMC doesn't need the entire rubric
  pasted — they need the *gaps* highlighted with citations.
- A PR diff with `Generated-by: Claude Code` as the only
  context. The reader needs the Security-team rationale for
  the change in the PR body; the trailer is a footnote.
- A grab-bag remediation that combines the `AGENTS.md` link
  fix with model-section additions in one PR. Violates hard
  rule 2 — split.
- Calling the spreadsheet write directly from this SKILL.
  Always hand off to `glasswing-scan-update` so the diff-and-
  confirm gate fires.

## Provenance

This SKILL formalizes the pre-flight discoverability + model-
completeness check that `glasswing-scan-response`'s
"Hard pre-flight" rule alludes to. The completeness rubric is
the minimum-bar subset of
[`threat-model-producer`](../threat-model-producer/SKILL.md);
the full producer rubric is the standard a model aspires to,
this SKILL enforces only the slice the scan agent depends on
mechanically.

The remediation patterns (small structural fix → PR; substantive
gap → issue) match what Jarek has been doing manually for the
first wave of opted-in PMCs.
