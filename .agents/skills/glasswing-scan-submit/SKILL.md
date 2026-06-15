---
name: glasswing-scan-submit
description: >-
  Submit a PMC's scan request to the vendor's project-enrollment Google Form (one form submission per repo),
  then draft the PMC notification email.
  The form replaces the old "Email 1 to Mirko" flow as of 2026-05-19.
  Repos are ordered by OSSF Criticality Score (highest first);
  the top-ranked repo carries the maintainer roster + the OSS-expedite explanation + the "I'm interested in Claude Max 20x" checkbox in its Additional Information field.
  Subsequent repos in the same PMC's scope submit slimmer forms that point back to the first submission for context.
  The SKILL only fires on **explicit operator instruction** ("submit X for scan" / "queue X" / "OK send the request").
  Form submission uses a Playwright persistent profile (one-time Google sign-in via `form-submitter setup`);
  the helper then drives the form headlessly per repo.
  After all forms are submitted, the SKILL drafts a PMC-notification email for human review and hands off to `glasswing-scan-update` to set `Date scan requested` + `Repositories submitted`.
---

# glasswing-scan-submit SKILL

The handoff step between the ASF Security team's pre-flight work (verifying the model) and the scan vendor actually running the scan.
This SKILL submits the scan request via the vendor's project-enrollment Google Form (one form submission per repo) and drafts the PMC notification email.

The submission is a **form-then-email flow**:

1. **Form submissions — one per repo, vendor-side.** The helper fills and submits the vendor's project-enrollment Google Form once per repo in the PMC's confirmed scope.
   Repos are ordered by OSSF Criticality Score, highest first;
   the top-ranked submission ("the headline form") carries the maintainer roster + the OSS-expedite addresses (with one-line "for whom" explanation) and has the "I'm interested in Claude Max 20x for my Open Source work" checkbox ticked.
   Subsequent submissions for the same PMC are slimmer —
   they point back to the headline submission for the maintainer roster and OSS expedite context.

2. **PMC notification email.** After all forms have been submitted, the SKILL drafts a single email to the PMC's primary contact, CC'd to the backup contacts + `private@<pmc>.apache.org` + `security@<pmc>.apache.org` (if it exists) + `security@apache.org` + every `@apache.org` scan-result recipient from the original `[GLASSWING]` request.
   Body says the scan has been submitted, lists the repos, summarises what happens next, and acknowledges the expedite ask if one was relayed in the headline form.

The form-based submission replaced the prior "Email 1 to mirko@alpha-omega.dev" flow on 2026-05-19 —
the vendor now collects scan-request intake via the Google Form rather than via free-form email.
The PMC-notification email shape is unchanged from the prior flow except for wording updates that reflect the new submission channel.

## When to invoke

**Hard precondition: explicit operator instruction.** This SKILL fires only when Jarek (or another Security-team member) says something like:

- "submit X for scan"
- "queue X"
- "OK send the scan request for X"
- "request the scan for X"

Pre-flight passing is **not** a trigger by itself.
When `glasswing-model-verify` passes for a PMC, the next step is **not** this SKILL —
it's `glasswing-scan-response`'s "options" template (the OSS-expedite pitch + ready-to-scan notification), which goes to the PMC and asks them what they'd like to do next.
This SKILL fires only after the operator decides to actually queue the scan.

**Skip** when:
- Pre-flight hasn't run or didn't pass —
  point the user at `glasswing-model-verify` first;
  this SKILL is downstream of it.
- The PMC's row is missing primary/backup contacts or scan-result recipients —
  the PMC-notification email needs them, and we don't fabricate.
- The operator hasn't explicitly said "submit".
  Pre-flight pass alone is not enough —
  surface the PMC as `pre-flight-passed-awaiting-operator-decision` and stop.

## Hard rules (do not skip)

1. **Pre-flight must be done.** If `Security model verified` is blank on the PMC's row in the tracker, refuse and point the user at `glasswing-model-verify`.
   This SKILL doesn't bypass the gate; it's the next step *after* the gate.

2. **Explicit operator instruction is required.** Pre-flight passing does not auto-trigger this SKILL.
   The operator must say "submit" / "queue" / "send the request" or similar for a specific named PMC.
   Surface PMCs in `pre-flight-passed-awaiting-operator-decision` state from `glasswing-scan-run`'s sweep;
   never fire on those automatically.

3. **Every named contact on the PMC notification must be `@apache.org`-rooted and on the PMC roster.** Cross-check against the PMC sheet's `Contact Person` + `Backup contact` cells (which already carry `@apache.org` addresses per the scan-request verification gates) and against Apache Whimsy's roster page for the PMC.
   If a row has a placeholder like "JB" or a bare handle without a verifiable `@apache.org` address, surface it as a question —
   don't put unverifiable names into the email.

4. **Draft + confirm before submitting forms or creating Gmail drafts.** Two confirmation gates apply to this SKILL:

   - **Form-submission gate.** Render the per-repo submission plan (ordering by Criticality Score, the exact text that would go into the Additional Information field on each form, which checkboxes are ticked) and run the helper in `--dry-run` first.
     The operator reviews the plan, approves explicitly,
     then the helper runs live.
   - **PMC notification email gate.** After all forms have been submitted, render the PMC notification draft (To / CC / Subject / Body) and wait for explicit approval, then call `mcp__claude_ai_Gmail__create_draft`.
     Never call `send` directly —
     the user reviews in the Gmail UI once more and presses Send themselves.

4a.
**Refresh email threads and the spreadsheet before submitting.** State on PMC threads and on the tracker moves fast —
late OSS-expedite requests, scope amendments, contact changes, additional questions, and chair-level go-aheads commonly land between sweeps.
A submission based on stale state can miss an expedite address the PMC asked for, submit the wrong scope, or skip a branch the PMC explicitly named.
Before running the form-submission gate:

   1. **Re-read the PMC's `[GLASSWING]` Gmail thread** via `mcp__claude_ai_Gmail__get_thread`.
      Look specifically for messages that arrived after the most recent `glasswing-scan-run` sweep:
      explicit submission green-lights, branch-level scope, OSS-expedite asks ("please include X in your expedite ask"), scope amendments.
      Surface any that the spreadsheet doesn't yet reflect.

   2. **Re-read the PMC's row** from the PMCs sheet via the Sheets API.
      Compare `Expedite Claude OSS Requests`, `Repositories requested`, `Contact Person`, `Backup contact`, `Security Model`, and any `Submission notes` against what the thread says.

   3. **If divergence is found**, apply the missing updates via `glasswing-scan-update apply` (Expedite, scope, submission notes) **before** running `--dry-run`.
      Don't try to short-circuit by passing values inline —
      the spreadsheet is the durable record the rest of the pipeline reads from.

   Recipient changes ("send results to Y instead of X") do NOT need to be applied to the spreadsheet before form submission —
   the form deliberately doesn't pin a downstream delivery destination,
   and the Security team handles forwarding manually when results arrive.
   The recipient list only matters when drafting the PMC notification email (step 10) and when the eventual forward goes out via `glasswing-scan-forward`;
   apply recipient updates to `Contact Person` / `Backup contact` when the PMC themselves asks for a roster change,
   but don't gate submission on it.

   The dry-run that the operator approves must reflect a spreadsheet snapshot that's been reconciled against the PMC thread in this session.
   Skipping this refresh is a bug, not an optimisation.

5. **Form-submission cardinality, ordering, and the per-repo discoverability auto-skip.** One form submission per repo in the PMC's confirmed scope (the `Repositories requested` cell), with two filters applied:

   - **Auto-skip on missing discoverability markers.** For each repo, the helper queries `repos/apache/<repo>/contents/AGENTS.md`, `.../SECURITY.md`, `.../security.txt`, and `.../.well-known/security.txt` via the GitHub API before submission.
     A repo with **none** of those markers is **silently dropped from the submission batch** (and logged in the dry-run output as skipped).
     The rationale is twofold:
     the scan agent needs `AGENTS.md` (or one of the SECURITY anchors) to reach the threat model,
     and the form's "valid SECURITY.md" assertion is structurally false for a repo with none of those files.
     The operator lands discoverability via `glasswing-model-verify` for skipped repos and re-runs `submit-pmc` to pick them up.
     The natural "phased submission" pattern (e.g. Logging's wave 1 = log4j2 + log4net + log4cxx, wave 2+ as `AGENTS.md` lands) falls out of this rule without any separate phasing knob.

   - **Ordering by OSSF Criticality Score (descending).** The submittable subset is sorted high-to-low by `Criticality Score (%)` (read from the Repositories sheet).
     Repos with blank Criticality Score sort last in the submittable list (they're typically sandbox / less-active repos that still passed the discoverability check).
     The first submittable repo after this sort is the "headline form" —
     it carries the maintainer roster + OSS expedite explanation + the "I'm interested in Claude Max 20x" checkbox.
     Subsequent submittable forms are slimmer (see rule 6 for the field contents).

   The dry-run output **must** list any skipped repos so the operator can decide whether to land discoverability before going live.
   Silent skipping without surfacing in the plan is a bug.

6. **Field contents per submission.**

   The form has 10 fields.
   Their values per submission:

   | Field | Headline form (first repo) | Subsequent forms |
   | --- | --- | --- |
   | Name of the Open Source Project | `Apache <PMC name>` (e.g. `Apache Tomcat`) | Same |
   | URL of the Repository | The repo's GitHub URL (e.g. `https://github.com/apache/tomcat`) | The repo's GitHub URL for *this* submission |
   | Your Name | Submitter's name (e.g. `Jarek Potiuk`) — read from the `form-submitter` CLI (in `tools/form_submitter/`) config | Same |
   | Your Email Address | Submitter's `@apache.org` address (e.g. `potiuk@apache.org`) — read from config | Same |
   | URL of your Github profile | Submitter's GitHub profile URL — read from config | Same |
   | Your Role within the Project | `ASF Security Committee member, submitting on behalf of <PMC name> PMC at their request` | Same |
   | Additional information and context | **Full block (see template below)**: PMC primary + backup contacts, scan-result recipients, OSS-expedite addresses with one-line "for whom" explanation, and the link to the verified threat model. | **Short pointer**: "Submitted by the ASF Security Committee on behalf of `Apache <PMC name>` PMC. The maintainer roster and any OSS-expedite request are on the headline submission for this PMC (apache/`<headline-repo-name>`)." |
   | I confirm I'm authorized to request this scan, and this is aligned with the project governance | Checked (always — the operator's explicit instruction is the authorization) | Checked |
   | There is a valid security.txt or SECURITY.md in my repository that describes how to deal with findings | Checked per-repo: **when any of `AGENTS.md`, `SECURITY.md`, or `security.txt` exists at the repo's HEAD** (verified by the helper's auto-discoverability check from rule 5). The form's literal phrasing names SECURITY.md / security.txt, but the operational intent ("the repo tells researchers where to take findings") is satisfied equally by AGENTS.md, which is the standard pointer-file in the ASF Glasswing pipeline and carries the same find-the-model role. Tick the box whenever the chain resolves. | Same per-repo rule |
   | I'm interested in Claude Max 20x for my Open Source work | Checked **only if** the PMC's `Expedite Claude OSS Requests` cell is non-empty AND not the literal string `none`. Otherwise leave unchecked. | **Always unchecked** — only the headline form carries the expedite ask |

   The "Additional information" headline-block template:

   ```text
   Submitted by the ASF Security Committee on behalf of
   Apache <PMC name> PMC at their request.

   PMC contacts:
     - Primary: <Primary contact name + @apache.org>
     - Backup:  <Backup contact name(s) + @apache.org>

   Threat model (verified by the ASF Security team against
   the Scovetta rubric):
     - <model URL>

   <IF the Expedite Claude OSS Requests cell is non-empty
   and not "none", include this block; otherwise omit>
   Claude-for-Open-Source subscription expedite — the
   following PMC members have registered for the Claude
   Max 20x program at
   https://claude.com/contact-sales/claude-for-oss and
   would benefit from an expedite of their applications.
   The "I'm interested in Claude Max 20x" checkbox on
   this form refers specifically to:

     - <addr1@apache.org>
     - <addr2@apache.org>
     - ...
   </block>

   Repos in scope for Apache <PMC name> (submitted as
   separate forms, ordered by OSSF Criticality Score):
     1. apache/<repo-1>  ← this submission (headline)
     2. apache/<repo-2>
     3. apache/<repo-3>
     ...

   <IF the PMCs sheet's `Submission notes` column is
   non-empty for this PMC, append here verbatim under a
   `Submission notes (operator-supplied):` header. Each
   line is indented two spaces. The Submission notes
   column is the operator's free-text channel for per-PMC
   quirks that the vendor's scan team should see — e.g.
   "scan main + 2.x branches of log4j2", "PMC asked us
   to leave repo X out of this batch despite it being in
   scope", "model URL points at a draft pending merge in
   PR #N". Vendor-facing only — do NOT put internal-process
   overrides here (e.g. don't write the scan-result
   delivery destination; that's an ASF-internal
   forwarding detail and the Security team handles it
   when results arrive). The helper renders the cell
   contents verbatim without parsing tags.>
   ```

   **Why no "Scan-result recipients" block?** The form is the vendor-facing intake;
   the scan vendor sends results back to the submitter (the ASF Security team),
   and the team forwards manually to the PMC's named contacts via `glasswing-scan-forward`.
   Binding the downstream forwarding destination into the form submission makes it brittle to PMC-contact changes after the scan was queued.
   The form should describe what is to be scanned and against what threat model;
   the team handles delivery internally when results land.

   The "Additional information" subsequent-submission template:

   ```text
   Submitted by the ASF Security Committee on behalf of
   Apache <PMC name> PMC at their request.

   This is the apache/<this-repo-name> submission within a
   per-repo batch for Apache <PMC name>. The maintainer
   roster, scan-result recipients, threat model, and any
   OSS-subscription expedite request are on the headline
   submission for this PMC (the apache/<headline-repo-name>
   submission, submitted via this form immediately before
   this one).
   ```

7. **Submitter identity — `@apache.org`-rooted.** The "Your Email Address" field on the form is the submitter's `@apache.org` address (e.g. `potiuk@apache.org`), not a personal email —
   the submission represents the ASF Security Committee acting on behalf of the PMC.
   The `form-submitter` CLI (in `tools/form_submitter/`) helper reads this from a config file (`~/.config/asf-security/glasswing/submitter.json`) so it doesn't need to be repeated per-submission.
   If the config file is missing, surface as a question before submitting.

   The Google account the submitter signs in with during `form-submitter setup` can be any account they prefer —
   the form will collect that login-anchored email separately from the "Your Email Address" field.
   The two don't need to match;
   the form-collected one is the vendor's audit trail,
   and the "Your Email Address" field is what they'll respond to.

8. **Expedite request handling.** The form has an "I'm interested in Claude Max 20x for my Open Source work" checkbox.
   If the PMC's `Expedite Claude OSS Requests` cell is non-empty and not the literal string `none`, the **headline form** (the highest-Criticality repo) ticks this checkbox AND includes the per-address "for whom" explanation in its Additional Information block.
   Subsequent forms for the same PMC leave the checkbox unchecked.

   If the cell is empty or `none`, the checkbox stays unchecked on every form, and the expedite-ask block in Additional Information is omitted.

   Either way, the PMC notification email (step 11 below) mentions whether an expedite ask was included on the headline submission.

9. **CC discipline on the PMC notification.** The PMC notification email's CC list is:

   - `security@apache.org` (Foundation-level audit trail);
   - `private@<pmc>.apache.org` (PMC collective visibility);
   - the project's `security@<pmc>.apache.org` alias if one exists (look it up via <https://security.apache.org/projects/>);
   - the backup PMC contact (the primary is on the To: line);
   - every `@apache.org` address listed in the original `[GLASSWING]` request as a scan-result recipient.

   These are the people who need to know the scan has been queued and who will receive the eventual forwarded results.
   The notification is sent as a reply on the PMC's original `[GLASSWING]` request thread (step 12),
   so the whole engagement stays on one thread of record.

10. **After form submissions are confirmed AND the user sends the PMC notification email, hand off to `glasswing-scan-update`** to write two cells on the PMC's row to the dates the work actually happened:

    - `Date scan requested` — the date the form submissions were completed (the `form-submitter` CLI (in `tools/form_submitter/`) returns this).
    - `Repositories submitted` — the exact list of repo URLs that were submitted via the form, newline-separated, in the same descending-Criticality order the forms were submitted in.

    The `Mirko thread (ponymail)` column stays blank for form-based submissions —
    there's no email thread on a public list to permalink to.
    This is intentional and matches the post-2026-05-17 convention for that column (kept for back-compat with submissions made before the form transition; not maintained going forward).

    This SKILL does not write to the spreadsheet directly;
    it produces the two values (`Date scan requested`, `Repositories submitted`) and hands off to the update SKILL.

11. **Vendor opacity on PMC-facing email.** The PMC notification email follows `glasswing-scan-response`'s hard rule 5 (Vendor opacity):
    the body must not name the scan vendor in any form (no "Mirko", no "Alpha-Omega", no naming the vendor company or specific staff).
    Canonical PMC-facing wordings: "our scan vendor partner" / "the vendor's enrollment form" / "the scan pipeline".
    The Glasswing *program name* is fine (it's already in the `[GLASSWING]` subject line);
    Anthropic + Apache Magpie + Claude OSS are fine to name.
    What's redacted is **who runs the pipeline downstream of the Security team**.

## Inputs the SKILL needs before submitting

| Input | Source |
| --- | --- |
| Explicit operator instruction | Conversation (no inference from sheet state alone) |
| PMC name and slug | From the request, or the user supplies it |
| Repos to submit | The subset of `Repositories requested` that passed pre-flight, ordered by OSSF Criticality Score (descending) — read from the Repositories sheet. If pre-flight passed for *all* repos in `Repositories requested`, the submit list equals that cell. If pre-flight passed for only some, submit only those — the rest land in a later batch once their discoverability is fixed. **Always show the per-repo verdict explicitly when drafting** so the operator can see why some repos are in this batch and others aren't. |
| Threat-model URL | From the PMC sheet's `Security Model` column + the verify SKILL's notes; if the model is on a project site, that URL |
| Primary + backup PMC contacts | From the PMC sheet's `Contact Person` + `Backup contact` cells (already `@apache.org` per scan-request verification) — for the PMC notification email AND for the Additional Information block on the headline form |
| Scan-result recipients | Tracked separately for the PMC notification email's CC (derived from `Contact Person` + `Backup contact` cells + the original `[GLASSWING]` request body's "send results to" list). **Not used in the form's Additional Information** — the form is the vendor-facing intake and shouldn't pin the downstream forwarding destination; the Security team handles forwarding manually when results land. |
| Expedite addresses | From the PMC sheet's `Expedite Claude OSS Requests` column. May be empty or `none` — in which case the headline form's checkbox stays unchecked and the expedite-block in Additional Information is omitted. |
| Submission notes (optional) | From the PMC sheet's `Submission notes` column. Free-text operator notes rendered verbatim in the headline form's Additional Information under a `Submission notes (operator-supplied):` section. Vendor-facing only: use for per-PMC quirks the vendor's scan team should know (branch-level scope, repo opt-outs, model-URL caveats). Do NOT put internal-process overrides here (no scan-result delivery destinations — that's an ASF-internal forwarding detail). Empty cell = no section appended. |
| `Security model verified` date | From the PMC sheet — confirms pre-flight gate |
| Submitter identity | From `~/.config/asf-security/glasswing/submitter.json` (Name, @apache.org email, GitHub profile URL). One-time setup. |

If any of these are missing or ambiguous, surface as a question to the user before submitting.

## PMC notification email template

**Vendor opacity reminder** — this email is PMC-facing.
Per `glasswing-scan-response` hard rule 5, the body must not name the scan vendor.
Canonical phrasing is "our scan vendor partner" / "the vendor's enrollment form" / "the scan pipeline".
Anthropic + Apache Magpie + Claude OSS are fine to mention by name in the expedite block of the body;
vendor identity is what's redacted.

**To**: primary PMC contact (the `Contact Person` cell's `@apache.org` address)

**CC**: backup PMC contact(s) (from `Backup contact`), `private@<pmc>.apache.org`, `security@<pmc>.apache.org` *(if exists)*, `security@apache.org`, every `@apache.org` address from the original `[GLASSWING]` request's "send results to" list.

**Subject**: reply on the PMC's original `[GLASSWING]` request thread —
reuse that thread's subject with a `Re:` prefix (e.g. `Re: [GLASSWING] <PMC name>: request to scan repositories`).
Do **not** invent a new subject:
a distinct subject is what used to split the notification off into its own Gmail thread.
Keeping the original subject (and replying in-thread per step 12) keeps the whole engagement — scoping → submission → eventual forward — on a single thread.
(Vendor opacity still applies to the subject: never name the vendor in it.)

**Body**:

```text
Hi <Primary contact first name>,

The scan request for Apache <PMC name> has been submitted
through the vendor's enrollment form by the ASF Security
team. Queue position is TBD — usually a few days to a
couple of weeks, with no commitment.

Repos submitted (one form submission per repo, ordered
by OSSF Criticality Score):
  1. <repo URL 1>  (highest criticality — the headline
     submission for this PMC)
  2. <repo URL 2>
  3. <repo URL 3>
  ...

The headline submission for Apache <PMC name> includes
the full maintainer roster and scan-result recipient
list in its Additional Information field, so the
vendor's scan team has full context. Subsequent
submissions are slimmer and point back to the headline
submission for that context.

A program-shape note for context.

In parallel with the vendor-relay path above, the ASF Security,
ASF Infrastructure, and ASF Tooling teams are jointly pursuing
direct-access scanning of ASF projects without the third-party
vendor relay. This is what we're currently working on at the
ASF in parallel. Both paths feed the same internal queue; we
work whichever lands fastest for any given PMC, to make the
best use of the opportunities each party involved has made
available. From the PMC's perspective the process is identical
either way: pre-flight gate, scan, sanity-check, forward
results to your named recipients. We mention it so you have
the full picture of how the program is wired — nothing changes
about what shows up in your inbox.

You don't need to do anything until the results arrive
— we'll sanity-check the vendor's report and forward it
verbatim to your named scan-result recipients on a fresh
thread.

<IF the Expedite Claude OSS Requests cell was non-empty
and not "none", include this block; otherwise omit>
Anthropic Claude-for-OSS expedite request:
The headline submission ticked the "I'm interested in
Claude Max 20x for my Open Source work" checkbox on the
form and explained in the Additional Information field
that the request refers specifically to the following
@apache.org addresses you nominated:

  - <addr1@apache.org>
  - <addr2@apache.org>
  - ...

That should be the expedite signal the program team
needs. No promises from us or from Anthropic — the
vendor's team makes the call. The named PMC members
should already have registered at
https://claude.com/contact-sales/claude-for-oss with
their @apache.org address (which is the prerequisite
the expedite ask references).
</block>

Best,
<sign-off>
```

## Procedure

1. **Confirm explicit operator instruction.** This SKILL does not fire on pre-flight pass alone.
   If the operator hasn't named the PMC + said "submit" / "queue" / "send the request" or similar, refuse and surface the PMC as `pre-flight-passed-awaiting-operator-decision` instead.

2. **Refresh state (per hard rule 4a) before anything else.** Re-fetch the PMC's `[GLASSWING]` Gmail thread and the PMC's row from the spreadsheet **in this session** —
   not from a prior sweep.
   Surface to the operator any divergence the spreadsheet doesn't reflect:
   - late OSS-expedite ask ("please include X in your expedite ask") that isn't in `Expedite Claude OSS Requests` yet;
   - branch-level scope ("scan main + 2.x of <repo>") that isn't captured in `Submission notes`;
   - recipient override ("send results to project alias / to addr X") that isn't in `Submission notes`' `Scan-result destination:` line;
   - the explicit submission green-light (operator instruction).
   Apply missing updates via `glasswing-scan-update apply` **before** running `--dry-run`.
   The spreadsheet is the durable record; don't try to pass values inline.

3. **Confirm pre-flight passed.** Read the PMC's row in the tracker via `glasswing-scan-status` (or directly via the Sheets API per the truncation caveat in `glasswing-scan-run` Step 2).
   Verify:
   - `Repositories requested` is non-empty (scope was confirmed by the PMC via `glasswing-scan-response` gate 4);
   - `Security model verified` is non-empty;
   - `Security Model` is non-empty;
   - `Contact Person` and `Backup contact` are non-empty and `@apache.org`-rooted.

   If any is missing, surface the gap and stop.
   Do not submit against half-verified inputs.
   In particular, do not "fill in" a missing `Repositories requested` cell yourself —
   scope confirmation is the PMC's call, not the agent's.

4. **Gather the rest of the inputs** from:
   - the PMC sheet's `Repositories requested` cell (the confirmed scope; parse newline-separated URLs);
   - the Repositories sheet (read each repo's Criticality Score to determine the headline-form ordering);
   - the original `[GLASSWING]` thread (for the scan-result recipient list — used in the PMC notification CC AND in the headline form's Additional Information);
   - the `PR/Issues` cell (for any discoverability PR URL to reference in submission notes);
   - the `Expedite Claude OSS Requests` cell (parse newline-separated `@apache.org` addresses; empty cell or `none` = no expedite block and unchecked OSS checkbox on the headline form);
   - the `Submission notes` cell (free-text vendor-facing notes; rendered verbatim in the headline form's Additional Information).

5. **Look up the per-PMC `security@<pmc>` alias** at <https://security.apache.org/projects/> (or the source-of-truth JSON at <https://github.com/apache/security-site/blob/main/scripts/project-coordinates.json>).
   If the alias exists, add it to the PMC notification email's CC list.
   (It is NOT a form field; the form doesn't have a per-PMC alias slot.)

6. **Render the form-submission plan.** Show the operator:
   - The PMC name + slug.
   - The repo ordering (each repo URL with its Criticality Score, sorted descending).
   - The exact text that will go into the Additional Information field on each form (headline + subsequent).
   - Which checkboxes will be ticked on each (always: authorization confirm; per-repo conditional: SECURITY.md presence; headline only conditional on expedite cell: Claude Max 20x).
   - The submitter identity from `~/.config/asf-security/glasswing/submitter.json`.

   Cite inputs ("repos from the `Repositories requested` cell, ordered by `Criticality Score` from the Repositories sheet; expedite addresses from the `Expedite Claude OSS Requests` cell").

7. **Wait for explicit approval on the submission plan.** "ok" / "submit" / "go" / similar.
   If the user wants edits, revise and re-render before re-asking.
   Substantive rewrites need fresh approval.

8. **Run `form-submitter submit-pmc --dry-run`** with the PMC slug.
   The helper prints what it *would* submit on each form (verifies the plan from step 6 matches reality; catches missing config, missing repos in the Repositories sheet, etc.). The operator confirms the dry-run output matches expectations.

9. **Run `form-submitter submit-pmc` live.** The helper drives the form for each repo in order.
   Captures the confirmation URL (or screenshot path) per submission.
   Reports completion + the list of submitted repo URLs + the submission timestamp.

   If the helper errors out mid-batch (e.g. one form fails to submit because the persistent profile got signed out), surface the error and which repos completed vs didn't.
   The operator can re-run `setup` if needed and resume by passing `--starting-from <slug>` to skip the already-completed repos.

10. **Render the PMC notification email draft.** Show To / CC / Subject / Body, using the list of repos that were actually submitted (from step 9's output), the submission timestamp, and the expedite-block toggle based on whether the headline form ticked the OSS checkbox.

11. **Wait for explicit approval on the PMC notification email.**

12. **Create the PMC notification Gmail draft** via `mcp__claude_ai_Gmail__create_draft`.
    Pass:
    - `to`: the primary contact's `@apache.org` address
    - `cc`: the full CC list from step 5
    - `subject`: `Re: ` + the PMC's original `[GLASSWING]` request thread subject (so Gmail keeps it on that thread)
    - `body`: the rendered body
    - `replyToMessageId`: **the latest message id in the PMC's original `[GLASSWING]` request thread.** Resolve it with `mcp__claude_ai_Gmail__get_thread` on that thread and take the newest message's id.
      This threads the notification onto the existing request thread instead of opening a new one,
      so the whole engagement stays in a single thread.
      Note: when `replyToMessageId` is set, `create_draft` appends the rendered body below the quoted original —
      that is the intended reply shape.

13. **Hand off to `glasswing-scan-update`.** Surface the line:

    > Forms submitted: <N> repos for <slug> at <timestamp>.
    > Drafted in Gmail: PMC notification draft id `<id>`.
    > After you send the notification, flip
    > `Date scan requested` + `Repositories submitted` on
    > the `<slug>` row via `glasswing-scan-update`.
    > Suggested values:
    >   - Date scan requested: <submission date>
    >   - Repositories submitted: <newline-separated repo URLs>

    Do not invoke the update SKILL yourself;
    the user runs it once they've actually sent the notification email.

## `form-submitter` helper

Lives at [`tools/form_submitter/`](../../../tools/form_submitter/) — a standalone Python project with `pyproject.toml`, unit tests, and CI.
Invoke as `uv run --project tools/form_submitter form-submitter <subcommand>`.
See [`tools/form_submitter/README.md`](../../../tools/form_submitter/README.md) for the full setup + usage docs.

Auth model: a persistent Chromium profile at `~/.config/asf-security/glasswing/playwright-profile/`, created on first run via `setup`.
The operator signs in to Google once (with whatever account they prefer — see hard rule 7);
subsequent `submit-pmc` invocations reuse the authenticated session.

Subcommands:

- `setup` — launches a non-headless Chromium with the persistent profile and navigates to the form URL.
  The operator signs in to Google manually, confirms the form loads with the sign-in completed, then closes the browser.
  The persistent profile is now populated.

- `submit-pmc --slug <slug> [--dry-run] [--starting-from <repo>]` — reads the PMC's row from the tracker via the Sheets API (using the same OAuth artifacts as `sheets_writer.py`), enumerates the repos in `Repositories requested`, orders them by Criticality Score, and submits one form per repo.
  With `--dry-run`, prints the per-form fill plan and exits without submitting.
  With `--starting-from <repo>`, skips repos earlier in the ordering than the named one (used to resume after a mid-batch error).

- `setup-submitter` — interactive prompt to populate `~/.config/asf-security/glasswing/submitter.json` with the submitter's Name, `@apache.org` email, and GitHub profile URL.
  Idempotent — re-running overwrites.

The helper does NOT write to the tracker;
it returns the values for `glasswing-scan-update` to apply.

## Style notes

- **Don't restate what the recipient already knows.** The PMC has already heard the pipeline mechanics (sanity-check, verbatim forward, no per-finding triage on our side) in the pre-flight-pass email.
  The notification email is a status update —
  submission happened,
  here are the repos, here's the expedite-ask block if applicable.
  Cut "what happens next" recaps and process preambles;
  keep substance (repo list, expedite addresses, the reassurance that no PMC action is needed yet).
- **One PMC per submission run.** Don't batch multiple PMCs into a single form-submission run.
  Each PMC has its own ordering, its own headline form, its own expedite ask.
  Run them sequentially; one PMC submission run produces one PMC notification email.
- **No marketing.** The audience is the vendor's program staff (form Additional Information) + Apache PMC members (notification email);
  neither needs "cutting-edge" or "next-generation" framing.
- **Be specific about per-repo discoverability.** If a repo's SECURITY.md is only present via a pending PR, leave the "valid security.txt or SECURITY.md" checkbox unchecked for that form and note it in the Additional Information ("AGENTS.md+SECURITY.md is pending in apache/<repo>#NN, expected to merge before the scan agent runs").
  Don't tick a checkbox the form's assertion contradicts.
- **Don't promise PMC-side response times** in the notification email.
  "PMC contacts will triage" is a *commitment to attempt* — not a service-level guarantee.
- **Sign in the human's voice, not the agent's.** This SKILL drafts; the human signs.
  Leave a `<sign-off>` placeholder in the email body rather than baking a specific signature into the draft.

## Examples of bad submissions (avoid)

- Submitting forms with the "I'm interested in Claude Max 20x" checkbox ticked when the `Expedite Claude OSS Requests` cell is empty or `none`.
  The checkbox is conditional — only the headline form, only when the PMC has nominated addresses.
- Ticking the "There is a valid security.txt or SECURITY.md" checkbox for a repo whose discoverability is only pending in an open PR.
  The form's assertion needs to be true at submit time.
  If the PR is still open, leave it unchecked and note the PR in Additional Information.
- Submitting a PMC whose `Security model verified` cell is blank.
  Violates hard rule 1.
- Submitting on pre-flight pass alone, without explicit operator instruction.
  Violates hard rule 2.
- Forgetting the PMC notification email entirely.
  The PMC needs to know the scan has been queued;
  the form submissions don't notify the PMC on their own.
- Putting the maintainer roster + OSS expedite block on every form.
  The headline form (highest Criticality Score) carries that;
  subsequent forms point back to it.
  Repeating the roster on every form is verbose and means the vendor's team has to dedupe.
- Naming the scan vendor in the PMC notification email body (per hard rule 11).
  The form is internal vendor-side;
  the email is PMC-side;
  the names of vendor staff or company go on the form's submissions, never in the email.

## Provenance

This SKILL captures the handoff step between the ASF Security team's pre-flight (which lives in `glasswing-model-verify`) and the scan vendor actually running the scan.
The 2026-05-19 form-based submission flow replaces the earlier `mirko@alpha-omega.dev`-by-email flow (which itself was the 2026-05-17 evolution of an even earlier auto-fire-on-pre-flight-pass shape).
The vendor's project-enrollment Google Form is now the canonical submission channel.

Reasons for the form transition:

- The vendor needs structured per-repo intake;
  the free-form email Mirko was triaging by hand didn't scale as more PMCs opted in.
- The form bundles the Claude-for-OSS expedite ask ("I'm interested in Claude Max 20x for my Open Source work" checkbox) directly into the intake flow so the vendor's program team doesn't have to forward expedite asks as a separate step.
- Per-repo submissions match the vendor's actual scan cardinality —
  each scan is per-repo, so each enrollment should be too.

The PMC notification email shape is unchanged from the prior flow except for wording updates that reflect the new submission channel (the vendor's enrollment form replaces the email to vendor staff).
The operator-gated trigger and the `pre-flight-passed-awaiting-operator-decision` pipeline state both stay;
submission still requires explicit operator say-so, not just pre-flight pass.
