---
name: triage-assess
description: >-
  Assess filed security reports against the project's threat model and source,
  then draft the right response.
  For each filed report in report-cache, look up the PMC from the `pmc` front matter key:
  - If the PMC has a specialized `security_contact` (as determined by `whimsy-tool`) and the contact is in the `To` or `Cc` fields,
    the Security team only TRACKS it (no drafts),
  - Otherwise assess whether the report is a real in-scope issue.
  If it is a high-confidence false positive or hardening suggestion,
  draft a non-assertive note to the reporter (they may take it to the public tracker).
  If it is plausible,
  draft a forward to the PMC (templates/forward.md) plus a receipt to the reporter (templates/receipt.md or template/receipt-specialized.md).
  Before drafting, look up prior reports for the same PMC in the local `email-classification/` archive
  (a worktree of the `email-classification` branch, created automatically by `archive_lookup.py` on first use)
  so duplicates and repeat reporters are surfaced and Ponymail context can be passed to the PMC.
  The final non-issue / hardening / CVE call always belongs to the PMC,
  so drafts never use assertive language and the skill never sends.
  A deterministic helper (draft.py) fills the templates and stamps the bundle's report.md front-matter;
  the model supplies the judgement, summary, and reply text.
  Use whenever the team says "assess the cached reports", "triage report X against its threat model", "draft the forwards/replies",
  or after filing to work through report-cache.
  Project source is read from a --workspace dir (default workspace/<pmc>).
---

# triage-assess SKILL

The **assessment + drafting** phase of the report-triage pipeline.
After `triage-populate-cache` sweeps, filters, and files reports under `report-cache/<date>/<pmc>/<keywords>/`,
this SKILL works through them:
- decides whether they are addressed to the Security Team or just copies from specialized Security teams/project private mailing lists,
- assess plausibility against the project's threat model,
- and draft the response for a human to review and send.

See `triage-populate-cache/SKILL.md` for the cache layout + the `report.md` front-matter schema.
This SKILL writes drafts into the bundle and advances the front-matter `status`;
it leaves the provenance block alone and **never sends**.

## Running this SKILL

For one or a few reports, the main agent runs the Workflow below directly.

For a batch, fan out **one sub-agent per PMC** (not per report).

Each assessor:
- loads its PMC's threat model (`pmc-security-info` + WebFetch),
- locates the source checkout in `--workflow` once
- reuses that context across all of that PMC's filed reports,
- runs `draft.py` to write the drafts,
- and returns a compact per-bundle disposition;

The main agent collects those and presents them.
Per-report fan-out re-fetches the same threat model N times, and a large batch inline in the main agent bloats its context - so per-PMC is the sweet spot.

Spawn each assessor on **Opus** (the orchestrator's model), giving it this SKILL as context and the bundle leaf-ids for its PMC.
The judgement here (in-scope vs reject, reading real code) needs Opus-level reasoning - do **not** downgrade the assessors to Sonnet/Haiku.

Sub-agents will concur for the user's attention to approve tools, so **every tool this SKILL uses should be preapproved** (see Tools below);
otherwise assessors ask for tool approval at the same time.

Before spawning accessors:

- check for the presence of the source code under the `--workspace` dir (default `workspace`),
  so the sub-agents don't need to stop waiting for code.
- check if the source code is up-to-date fetching from the origin (`origin` or `apache`).
- check the authentication status with Ponymail (`mcp__ponymail__auth_status`),
  so the sub-agents can query the archives.

## Hard rules

1. **The PMC owns the verdict.** Whether something is a non-issue, hardening, or a CVE is the PMC's decision,
   never ours.
   Drafts to the reporter use tentative, non-assertive language ("this appears to be...", "the PMC may consider..."),
   never "this is not a vulnerability".
2. **Track only when the PMC's own list was the addressee.**
   A report is the PMC's to handle (no triage) **only if it was sent (To or Cc) to the `security_contact` returned by `pmc-security-info` or the `private@<pmc>` list.
   A report that reached only the central `security@apache.org` list needs triage and a forward **even if the PMC runs its own security team** -
   the central list is where we add value.
   This is a recipient test (the bundle's `to` and `cc` header).
   `draft.py track` enforces it and refuses a central-addressed report.
3. **Bias to forwarding.** Only draft a push-back reply when the report is a false positive or pure hardening **with high confidence**.
   Anything plausible, or where confidence is not high, gets forwarded to the PMC (they decide).
   When in doubt, forward.
4. **Drafts only.** Output is Markdown in the bundle for a human to review and send;
   the SKILL never emails anyone.

## Inputs

- **PMC security coordinates** via the `whimsy-lookup pmc-security-info <slug>` tool:
  the `security_contact` (the PMC's own `security@<pmc>` when registered, else the foundation-wide `security@apache.org` fallback)
  and the `threat_model` link.
  A PMC counts as *specialized* (runs its own security team) when its `security_contact` is its own address rather than the fallback.
- **Project source** under `--workspace` (default `workspace`):
  the SKILL reads `<workspace>/<pmc>` to check the report against real code.
  If that checkout is absent,
  stop and ask the user to check out the code.
- **Templates** `templates/forward.md`, `templates/receipt.md`, and `templates/receipt-specialized.md` (repo root).
- **`email-classification/` archive** (a worktree of the `email-classification` branch, created automatically by `archive_lookup.py` if missing):
  per-PMC archive of every previously triaged report's tag, one `.json` per report under `<pmc>/`, `zzz-non-issue/<pmc>/`, `zzz-resolved/<pmc>/`, or `archive/.../<pmc>/`.
  The filename is the tag (space-separated keywords, often prefixed by a CVE id or date);
  each file lists the thread's messages (`mailtime`, `subj`, `from`, `to`, `message_id`).
  Used by `archive_lookup.py` to find prior reports with the same shape.
  **Privacy:** the archive holds third-party reporter PII (subject, from, to, message_id).
  Surface it only to the PMC (forward summaries, Ponymail lookups for context) and never to the reporter,
  unless the matched archive is from the *same* reporter (i.e. an explicit "you reported this before" follow-up).

## Workflow

For each filed bundle (`status: filed`) under `report-cache/`:

### Step 1: determine extent of work

Determine the kind of work required based on the recipients of the report (the bundle's `to` and `cc` headers) and the `security_contact` of the PMC:

```bash
uv run --project tools/whimsy_lookup whimsy-lookup pmc-security-info <pmc>
```

If the `security_contact` or `private@<pmc>` is among the recipients,
the message is not addressed to the security team.
Return a disposition `tracked` and stop.

Otherwise, continue with step 2.

### Step 2: find prior similar reports

Run `archive_lookup.py --pmc <pmc> --keywords "<tag-keywords>"` to surface archived reports for this PMC whose tag keywords overlap with the current one.

For each similar report, retrieve it using Ponymail and **compare it with the current report**.
Do not judge similarity based **only** on tags.
The content of the reports (vulnerable component, class, method), should also be similar.

If you spot a duplicate, the behavior depends on the previous disposition:

- Reports in `zzz-non-issue` were rejected.
  Draft a reply using `templates/reject.md` and use the previous reason given by the PMC as `--reason` parameter to `draft.py`.
  The status of the report is `drafted-reply`, its tag is prepended with `zzz-non-issue` and stop.

- Reports in current collection are still being evaluated by the PMC.
  The link of the duplicate report will be useful in the drafting phase.

## Step 3: assess the report

The assessment of the report needs to:

1. Determine if the report is not a hallucination.
   Code references in the report need to be checked against the project source code.
   If the reporter provided a Git commit, the same commit should be used for evaluation.
2. Evaluate the report against the project threat model to determine:
   - Which adversary capability is required (unauthenticated user, authenticated user, administrator),
   - Which trust boundary is crossed (untrusted input),
   - Which security property is broken.
3. Check if the adversary is in scope, a trust boundary is crossed and a security property is broken.
   Otherwise, the report is rejected and it might be a candidate for a public hardening.
4. Reporters use various arguments to put in scope inputs that are considered **trusted**.
   For example:
   - They argue that another vulnerability (SQL injection, attacker access to environment properties) can be chained to exploit the reported issue.
     The argument is not valid: ask the reporter, whether they are aware of such a vulnerability.
   - They report problems of the "Secure-by-default" kind.
     Insecure defaults are not necessarily vulnerabilities.
     Check the PMCs threat model to see if the project can be deployed as-is or additional steps are required.
     For example a project might require operators to keep it in a secure network or configure authentication otherwise.

## Step 4: draft

**High-confidence false positive or hardening** -> write your non-assertive note to a temp file and run `draft.py reply <id> --body-file <file> [--kind false-positive|hardening]`.
Write only the message body:
- tentatively, why it looks out of scope or like hardening (cite the specific code path / call when you can),
  the app-side mitigation if relevant,
- if a duplicate non-issue was found, reuse the PMC argumentation, but don't **quote** the PMC.
  The answer to the original report is not necessarily public.
- quote the public threat model whenever possible.
- and an explicit invitation for the reporter's reasoning if they see it differently ("we are open to your arguments...") rather than asserting a final verdict;
  note they are welcome to raise hardening ideas on the project's public issue tracker.

**Plausible (or not high-confidence)** -> write a concise PMC summary to a temp file (what was reported, affected component, why it is plausible, any caveats) and run `draft.py forward <id> --summary-file <file>`.

The summary for the PMC should be **concise**:
duplicating the security report serves no purpose.
A long summary is worse than no summary.

The summary should contain:

- **Problem**.
  A sentence or short paragraph explaining the vulnerability,
- **Source verification**.
  Whether or not the vulnerability was confirmed in code.
  Provide the branch and commit used for the verification.
- **In scope verification**.
  Give the link to the threat model used for verification.
  If the report is a false positive, but without high-confidence,
  cite the gap in the threat model that the PMC should clarify.
  If the project does not have a threat model ask if we missed one,
  provide https://cwiki.apache.org/confluence/display/SECURITY/Documenting+your+security+model as documentation on what a model is.
  If the report is plausible, provide the adversary profile requires and the security properties broken.

## Tools (preapproved)

The whole workflow runs on these tools, allowlisted in `.claude/settings.json` so it needs no approval requests
(required for the sub-agent assessors, which cannot prompt):

- `Bash(.agents/skills/triage-assess/draft.py *)` - write the drafts / set the bundle status.
- `Bash(.agents/skills/triage-assess/archive_lookup.py *)` - prior-report lookup (also creates the `email-classification` worktree on first use, via git, under the allowlisted script).
- `Bash(uv run --project tools/whimsy_lookup whimsy-lookup *)` - PMC security coordinates.
- `WebFetch(domain:*.apache.org)`, `WebFetch(domain:github.com)`, `WebFetch(domain:raw.githubusercontent.com)` - the project's threat-model page.
- `mcp__ponymail__*` - read a prior message in the Ponymail archive.
- `Read` / `Grep` / `Glob` over `report-cache/` and `workspace/<pmc>` - inspect the bundle and the real code.
  Inspect source with these tools, never by shelling out to `bash grep` / `cat` (that path is not allowlisted and would prompt).

Nothing else: this SKILL drafts only - it never sends mail, writes git, or calls other hosts.

## Helper commands

```bash
A=.github/skills/triage-assess
# PMC security coordinates (security_contact to Cc / threat model):
uv run --project tools/whimsy_lookup whimsy-lookup pmc-security-info <pmc> [--json]
$A/archive_lookup.py --pmc <pmc> --keywords "<words>"   # prior reports for this PMC
$A/draft.py track   <id>
$A/draft.py forward <id> --summary-file SUM.md  [--reporter-note NOTE.md] [--wf MARKER] [--triager "Name"] [--model "..."]
$A/draft.py reply   <id> --body-file REPLY.md   [--kind hardening] [--triager "Name"]
```

`archive_lookup.py` creates the `email-classification/` worktree on first run if missing,
then ranks archived `.json` files (one per past report) under `<pmc>/`, `zzz-non-issue/<pmc>/`, `zzz-resolved/<pmc>/`, and `archive/.../<pmc>/` by keyword overlap with the query.
The output is for the triager and the PMC;
the archive's `from`/`to`/`message_id` fields must not leak into reporter-facing drafts (see Inputs for the privacy rule).

`reply` always classifies the report `zzz-non-issue/` (no `wf` marker).
`forward`'s `--wf` is one of `reporter`, `cve-allocation`, `non-issue-docs` (`non-issue-feedback` is the `zzz-non-issue/` case, handled by `reply`);
it appends `wf <marker>` to the tag and records `wf` in the front-matter.

`<id>` is the bundle's Ponymail id or any unique prefix.
`--triager` defaults to `git config user.name`;
`--model` defaults to the running model and fills the forward template's "generated by AI using ..." disclaimer.

## Status values this SKILL sets

- `tracked` - specialized PMC; the Security team only tracks it.
- `drafted-forward` - `draft-forward.md` + `draft-receipt.md` written.
- `drafted-reply` - `draft-reply.md` written (false-positive / hardening).

`handled` stays `false` until a human actually sends the drafted mail.

## Scope

- Reads `report-cache/`, templates, project source,
  the PMC security coordinates (via `whimsy-lookup pmc-security-info`, from security-site),
  and the `email-classification/` archive (which it may create as a worktree).
- May WebFetch threat-model links on `*.apache.org` / `github.com`.
- Writes only draft Markdown + `report.md` front-matter status inside the bundle.
- Never sends, never edits the provenance block, never touches Ponymail.
