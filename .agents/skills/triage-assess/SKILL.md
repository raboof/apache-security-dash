---
name: triage-assess
description: >-
  Assess classified security reports against the project's threat model and source,
  then draft the right response through the `report-cache` CLI.
  Works the reports `triage-populate-cache` left at `status: classified` (reports the PMC
  already received are `assessed` + `disposition: track` upstream, and are skipped here).
  For each classified report: assess whether it is a valid, in-scope vulnerability against
  the PMC's threat model and real source.
  If it is a high-confidence false positive or hardening suggestion,
  draft a non-assertive note to the reporter (they may take it to the public tracker) and
  record `disposition: decline`.
  If it is plausible,
  write a concise PMC summary (`templates/forward.md`) plus an optional reporter note
  (`templates/receipt.md`) and record `disposition: forward`.
  Before drafting, look up prior reports for the same PMC in the local `email-classification/` archive
  (a worktree of the `email-classification` branch, created automatically by `archive_lookup.py` on first use)
  so duplicates and repeat reporters are surfaced and Ponymail context can be passed to the PMC.
  The final non-issue / hardening / CVE call always belongs to the PMC,
  so drafts never use assertive language and the skill never sends.
  The model supplies the judgement, summary, and reply text as bundle artifacts
  (`report-cache put-artifact`) and sets the disposition (`report-cache set`);
  `inbox_manager` applies the templates at send time.
  Use whenever the team says "assess the cached reports", "triage report X against its threat model", "draft the forwards/replies",
  or after a populate pass to work through report-cache.
  Project source is read from a --workspace dir (default workspace/<pmc>).
---

# triage-assess SKILL

The **assessment + drafting** phase of the report-triage pipeline.
After `triage-populate-cache` sweeps and classifies reports,
this SKILL works through the ones it left at a `classified` status:

- summarizes the report,
- assesses it against the PMC's threat model,
- deduplicates similar reports,
- writes the report's disposition (decline or forward) to the triage index,
- and drafts the response for a human to review and send.

This skill doesn't access reports directly,
it uses the `report-cache` tool to read and write the report's state.
Triaging artifacts are stored using `report-cache put-artifact` and `report-cache get-artifact`.

## Running this SKILL

For one or a few reports, the main agent runs the workflow below directly.

For a batch, fan out **one sub-agent per PMC** (not per report).

Each assessor:

- loads its PMC's threat model (the `model:` URL that `report-cache show <id>` prints, WebFetched),
- locates the source checkout under `--workspace` once,
- reuses that context across all of that PMC's classified reports,
- writes the response fragments and sets the disposition through `report-cache`,
- and returns a compact per-bundle disposition.

The main agent collects those and presents them.
Per-report fan-out re-fetches the same threat model N times, and a large batch inline in the main agent bloats its context - so per-PMC is the sweet spot.

Spawn each assessor on **Opus** (the orchestrator's model), giving it this SKILL as context and the bundle leaf-ids for its PMC.
The judgement here (in-scope vs reject, reading real code) needs Opus-level reasoning - do **not** downgrade the assessors to Sonnet/Haiku.

Sub-agents do prompt the user for tool approval, but the per-PMC assessors run concurrently,
so their prompts collide - while you are answering one, another can pop up and override it, and approvals get lost.
So **every tool this SKILL uses must be preapproved** (see Tools below) to avoid that crossfire.

Before spawning assessors:

- list the work with `report-cache list --status classified` and group it by `pmc`,
- determine the threat model for each PMC
  (`whimsy-lookup pmc-security-info` returns its `security_model_source` and `security_model_link`),
  and record it on each of that PMC's reports with
  `report-cache set <id> --security-model-source <url> --security-model-link <url>`,
  so it shows on the report's `model:` line and `inbox_manager` can cite it at send time.
- check for the presence of the source code under the `--workspace` dir (default `workspace`),
  if the code is absent, stop and ask the user to check it out.
- check the source is up-to-date, fetching from its remote (`origin` or `apache`),
- check the authentication status with Ponymail (`mcp__ponymail__auth_status`),
  if it is not, ask the user to log in.

## Hard rules

1. **The PMC owns the verdict.**
   Whether something is a non-issue, hardening, or a CVE is the PMC's decision, never ours.
   The PMC intent is expressed through:
   - the published threat model,
   - the public documentation,
   - previous verdicts in the case of duplicate reports.
   Prefer public sources over private ones.
   Drafts to the reporter without hard public arguments, use tentative, non-assertive language ("this appears to be...", "the PMC may consider..."),
   never "this is not a vulnerability".
2. **Bias to forwarding.** Only draft a decline reply when the report is a false positive or pure hardening **with high confidence**.
   Anything plausible, or where confidence is not high, gets forwarded to the PMC (they decide).
   When in doubt, forward.
3. **Drafts only.** Output is Markdown in the bundle for a human to review and send;
   the SKILL never emails anyone.

## Inputs

- **PMC security coordinates** via the `whimsy-lookup pmc-security-info <slug>` tool:
  the project's security model as two URLs: `security_model_source` (the raw `SECURITY.md`) to read/WebFetch when verifying, and `security_model_link` (the human security page) to cite in a draft to the PMC or reporter.
- **Project source** under `--workspace` (default `workspace`):
  the SKILL reads `<workspace>/<pmc>` to check the report against real code.
  If that checkout is absent,
  stop and ask the user to check out the code.
- **Templates** (repo root): `templates/forward.md`, `forward-duplicate.md`, `receipt.md`, `receipt-specialized.md`, `reject.md`.
  This SKILL never touches them: `inbox_manager` is the sole renderer and applies them at send time.
  See `templates/README.md` for the marker contract:
  this SKILL supplies the content values
  (the `summary.md` / `reason.md` / `note.md` artifacts plus the `assessment_model` and `duplicate_ponymail_link` index fields);
  `inbox_manager` fills those plus the identity / PMC / infra markers and drops any line whose marker stays empty.
- **`email-classification/` archive** (a worktree of the `email-classification` branch, created automatically by `archive_lookup.py` if missing):
  per-PMC archive of every previously triaged report's tag, one `.json` per report under `<pmc>/`, `zzz-non-issue/<pmc>/`, `zzz-resolved/<pmc>/`, or `archive/.../<pmc>/`.
  The filename is the tag (space-separated keywords, often prefixed by a CVE id or date);
  each file lists the thread's messages (`mailtime`, `subj`, `from`, `to`, `message_id`).
  Used by `archive_lookup.py` to find prior reports with the same shape.
  **Privacy:** the archive holds third-party reporter PII (subject, from, to, message_id).
  Surface it only to the PMC (forward summaries, Ponymail lookups for context) and never to the reporter,
  unless the matched archive is from the *same* reporter (i.e. an explicit "you reported this before" follow-up).

## Workflow

Work one classified bundle at a time.
`<id>` is the report's Message-ID;
`report-cache list --status classified` prints ids you can pass straight back.

### Step 1: read the report

```bash
uv run --project tools/report_cache report-cache show <id>
```

`show` prints the merged view:
the Gmail provenance (From / To / Cc / Subject),
the triage state (`pmc`, `delivered`, `status`, `labels`),
the body,
and the attachment / artifact listing.
Read any attachment worth reading with `report-cache get-attachment <id> <name>`.
Confirm the `pmc` (settled during classification) before assessing;
the threat model you assess against is that PMC's.

### Step 2: find prior similar reports

Run `archive_lookup.py --pmc <pmc> --keywords "<tag-keywords>"` to surface archived reports for this PMC
whose tag keywords overlap with the current one.

For each similar report, retrieve it using Ponymail and **compare it with the current report**.
Do not judge similarity based **only** on tags.
The content of the reports (affected component, class, and method, plus the vulnerability class (CWE))
should also be similar.

If you spot a duplicate, file the report under the original's label and record the original's
Ponymail link in the triaging metadata, using:

  ```bash
  report-cache set <id> --add-label "<the original's label>" \
      --remove-label "<this report's active label>" \
      --duplicate-ponymail-link "<original's ponymail thread url>"
  ```

Duplicates also influence the disposition:

- Reports in `zzz-non-issue` were rejected by the PMC.
  Draft a decline reusing the PMC's prior reason (see Step 4, decline).

- Reports in the current (open) collection are still being evaluated by the PMC.
  Forward as a duplicate: write the summary (Step 4, forward).

### Step 3: assess the report

The assessment of the report needs to:

1. Establish that the finding is genuine and reproducible, not a spurious or unsubstantiated claim.
   Code references in the report need to be checked against the project source code.
   If the reporter provided a Git commit, the same commit should be used for evaluation.
2. Evaluate the report against the project threat model to determine:
   - Which adversary capability it requires, mapped to an actor in the project's adversary model.
     The in-scope roles are whatever that model lists; do not assume a fixed
     unauthenticated / authenticated / administrator ladder.
   - Whether the input it relies on is attacker-controllable or trusted, per the model's input assumptions.
   - Which security property the project provides it would violate.
3. The report is in scope only if all three hold: the adversary is an actor the model includes,
   the input it relies on is attacker-controllable across a trust boundary, and it violates a
   security property the project actually provides.
   Otherwise it is out of model, and it might be a candidate for a public hardening.
4. Reporters often try to bring **trusted** inputs into scope by positing an attack chain.
   For example:
   - They argue that another vulnerability (SQL injection, attacker access to environment properties)
     can be chained to exploit the reported issue.
     The chained precondition is hypothetical: ask the reporter whether they are aware of such a
     vulnerability.
   - They report problems of the "Secure-by-default" kind.
     Insecure defaults are not necessarily vulnerabilities.
     Check the PMC's threat model to see if the project can be deployed as-is or additional steps are
     required. For example a project might require operators to keep it in a secure network or configure
     authentication otherwise.

### Step 4: draft

All fragments are written as bundle artifacts with `report-cache put-artifact <id> <name>` (reading the
content from a temp file with `--from <file>`, or from stdin). Every path ends by advancing the report to
`status: assessed` with its `--disposition`; leaving a report at `classified` sends it back through the
queue on the next run.

**High-confidence false positive or hardening** -> write your non-assertive note to a temp file, then:

```bash
report-cache put-artifact <id> reason.md --from reason.md
report-cache set <id> --status assessed --disposition decline \
    --collection zzz-non-issue --pmc <pmc> --keywords "<same keywords>" \
    --remove-label "<pmc>/<the active label from classify>"
```

`inbox_manager` renders `reason.md` through `templates/reject.md` at send time. The `zzz-non-issue/`
collection label is the classification that sorts the report out of the active queue (it carries no
`wf` marker); `--remove-label` drops the plain classify label so the declined report no longer shows as
active. Write only the message body:

- tentatively, why it looks out of scope or like hardening (cite the specific code path / call when you
  can), the app-side mitigation if relevant,
- if a duplicate non-issue was found, reuse the PMC argumentation, but don't **quote** the PMC.
  The answer to the original report is not necessarily public.
- quote the public threat model whenever possible,
- and an explicit invitation for the reporter's reasoning if they see it differently
  ("we are open to your arguments...") rather than asserting a final verdict.

Do not restate that the issue is off-topic for this channel or invite the reporter to the public
contribution channels: the `reject.md` template's closing paragraph already says this.

**Plausible (or not high-confidence)** -> write a concise PMC summary to a temp file, then:

```bash
report-cache put-artifact <id> summary.md --from <file>
report-cache set <id> --status assessed --disposition forward \
    --assessment-model "<the assessor's model id>"
```

`assessment_model` holds the id of the model that wrote the summary; `inbox_manager` renders it into
the AI disclaimer line (`<model>` marker). Add an optional extra paragraph for the reporter's receipt with
`report-cache put-artifact <id> note.md --from note.md`.

The summary for the PMC should be **concise**: duplicating the security report serves no purpose.
A long summary is worse than no summary. It should contain:

- **Finding**. A sentence or short paragraph explaining the alleged vulnerability.
- **Code verification**. Whether or not the vulnerability was confirmed in code. Provide the branch and
  commit used for the verification.
- **Scope assessment**. Give the link to the threat model used for verification.
  If the report is a false positive, but without high-confidence, cite the gap in the threat model that
  the PMC should clarify.
  If the project does not have a threat model ask if we missed one, provide
  https://cwiki.apache.org/confluence/display/SECURITY/Documenting+your+security+model as documentation
  on what a model is.
  If the report is plausible, name the adversary actor required (from the model's adversary model) and
  the security property it violates.

## Tools (preapproved)

The whole workflow runs on these tools, allowlisted in `.claude/settings.json` so it needs no approval
requests (the per-PMC assessors run concurrently, so an un-preapproved tool would fire overlapping
prompts that clobber each other):

- `Bash(uv run --project tools/report_cache report-cache *)` - read the bundle (`show` / `get-attachment`
  / `get-artifact`), write the drafts (`put-artifact`), and set the disposition (`set`).
- `Bash(.agents/skills/triage-assess/archive_lookup.py *)` - prior-report lookup (also creates the
  `email-classification` worktree on first use, via git, under the allowlisted script).
- `Bash(uv run --project tools/whimsy_lookup whimsy-lookup *)` - PMC security coordinates.
- `WebFetch(domain:*.apache.org)`, `WebFetch(domain:github.com)`, `WebFetch(domain:raw.githubusercontent.com)` -
  the project's threat-model page.
- `mcp__ponymail__*` - read a prior message in the Ponymail archive.
- `Read` / `Grep` / `Glob` over `workspace/<pmc>` - inspect the real code.
  Read the bundle through `report-cache show` / `get-attachment`, never by opening the cache files.

Nothing else: this SKILL drafts only - it never sends mail, writes git, or calls other hosts.

## Helper commands

```bash
A=.github/skills/triage-assess
RC="uv run --project tools/report_cache report-cache"
# PMC security coordinates (security_contact to Cc / threat model):
uv run --project tools/whimsy_lookup whimsy-lookup pmc-security-info <pmc> [--json]
$A/archive_lookup.py --pmc <pmc> --keywords "<words>"        # prior reports for this PMC

$RC list --status classified                                 # the work queue
$RC show <id>                                                # read one report
$RC put-artifact <id> summary.md --from summary.md          # forward: the PMC summary
$RC put-artifact <id> note.md --from note.md                # optional reporter receipt note
$RC set <id> --status assessed --disposition forward \
    --assessment-model "<model id>"                          # forward (the model the disclaimer credits)
$RC put-artifact <id> reason.md --from reason.md            # decline: the reject reason
$RC set <id> --status assessed --disposition decline \
    --collection zzz-non-issue --pmc <pmc> --keywords "<kw>" \
    --remove-label "<pmc>/<active label>"                    # decline (non-issue)
$RC set <id> --add-label "<the original's label>" --remove-label "<active label>" \
    --duplicate-ponymail-link "<url>"                        # a duplicate
```

`archive_lookup.py` creates the `email-classification/` worktree on first run if missing,
then ranks archived `.json` files (one per past report) under `<pmc>/`, `zzz-non-issue/<pmc>/`,
`zzz-resolved/<pmc>/`, and `archive/.../<pmc>/` by keyword overlap with the query.
The output is for the triager and the PMC;
the archive's `from`/`to`/`message_id` fields must not leak into reporter-facing drafts
(see Inputs for the privacy rule).

## Status this SKILL sets

Every report this SKILL touches ends at `status: assessed` with one of:

- `disposition: forward` - `summary.md` written (plus `note.md` when there is a reporter note) and
  `assessment_model` set; `duplicate_ponymail_link` recorded, and the original's label filed, when it
  is a duplicate.
- `disposition: decline` - `reason.md` written (false-positive / hardening), `zzz-non-issue/` collection
  label added.

`inbox_manager` sends the drafted mail and files the report; a report leaves the cache (reaches
`status: filed` and is deleted) only once its message is archived out of the Gmail inbox.

## Scope

- Reads report state and bundle content through the `report-cache` CLI, the PMC security coordinates
  (via `whimsy-lookup pmc-security-info`, from security-site), project source under `workspace/<pmc>`,
  and the `email-classification/` archive (which it may create as a worktree).
- May WebFetch threat-model links on `*.apache.org` / `github.com`.
- Writes only draft artifacts + the triage index disposition, through the `report-cache` CLI.
- Never sends, never edits the provenance block, never touches Ponymail beyond reading.
