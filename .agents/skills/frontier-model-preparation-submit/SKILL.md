---
name: frontier-model-preparation-submit
description: >-
  Enroll a PMC's scan by recording it in the Mythos tracker spreadsheet
  (set `Date scan requested` + `Repositories submitted`, criticality-ordered),
  then draft the PMC notification email.
  ASF Tooling runs the scan internally (Mythos-5), picking the queue up from the
  tracker + the `apache/tooling-agents-private` archive — there is NO external
  form to submit (the legacy Alpha-Omega Google-Form / "Email 1 to Mirko" intake
  is retired).
  The SKILL only fires on **explicit operator instruction** ("submit X for scan" /
  "queue X" / "OK send the request").
  After the tracker cells are set, it drafts a PMC-notification email for human
  review and hands off to `frontier-model-preparation-update` to write the cells.
---

# frontier-model-preparation-submit SKILL

The handoff step between the ASF Security team's pre-flight work (verifying the
model) and ASF Tooling actually running the scan.
This SKILL **enrolls a PMC's scan by setting the tracker spreadsheet** — there is
no external form to submit — and drafts the PMC notification email.

The enrollment is a **spreadsheet-then-email flow**:

1. **Set the tracker (the enrollment).** On the PMC's row, set `Date scan
   requested` (today) and `Repositories submitted` (the pre-flight-passing repos,
   newline-separated, ordered by OSSF Criticality Score, highest first). ASF
   Tooling reads the queue from the tracker: the `build-status-tab` refresh
   projects every submitted repo into the **Scan Queue** tab (one row per repo ×
   branch/tag, criticality-ranked), and flags each as `Added after ASF tooling
   started` = Yes (enrolled on/after ASF Tooling's 2026-07-15 internal start).
   Everything ASF Tooling needs — the verified threat-model URL, the maintainer
   roster, the scan-result recipients, the OSS-expedite ask, any per-PMC
   `Submission notes` — already lives on the PMC's row and its linked tabs; the
   enrollment is just flipping the two date/scope cells.

2. **PMC notification email.** After the tracker is set, the SKILL drafts a single
   email to the PMC's primary contact, CC'd to the backup contacts +
   `private@<pmc>.apache.org` + `security@<pmc>.apache.org` (if it exists) +
   `security@apache.org` + **`private@tooling.apache.org`** (the ASF Tooling PMC
   private list — the Tooling team's channel for the scanning effort; always
   Cc'd, no personal introduction needed) + every `@apache.org` scan-result
   recipient from the original `[GLASSWING]` request.
   Body says the scan has been queued, lists the repos, summarises what happens
   next, and acknowledges the expedite ask if one was recorded.

The scan program moved in-house: ASF Tooling (VP Tooling + Infra + Security) now
runs scans internally on the Mythos-5 model, and results land directly in the
`apache/tooling-agents-private` archive. The external project-enrollment Google
Form (and the earlier `mirko@alpha-omega.dev` email intake) is **retired** — do
not submit any form. Enrollment is recording the scan in the tracker.

## When to invoke

**Hard precondition: explicit operator instruction.** This SKILL fires only when Jarek (or another Security-team member) says something like:

- "submit X for scan"
- "queue X"
- "OK send the scan request for X"
- "request the scan for X"

Pre-flight passing is **not** a trigger by itself.
When `frontier-model-preparation-model-verify` passes for a PMC, the next step is **not** this SKILL —
it's `frontier-model-preparation-response`'s "options" template (the OSS-expedite pitch + ready-to-scan notification), which goes to the PMC and asks them what they'd like to do next.
This SKILL fires only after the operator decides to actually queue the scan.

**Skip** when:
- Pre-flight hasn't run or didn't pass —
  point the user at `frontier-model-preparation-model-verify` first;
  this SKILL is downstream of it.
- The PMC's row is missing primary/backup contacts or scan-result recipients —
  the PMC-notification email needs them, and we don't fabricate.
- The operator hasn't explicitly said "submit".
  Pre-flight pass alone is not enough —
  surface the PMC as `pre-flight-passed-awaiting-operator-decision` and stop.

## Hard rules (do not skip)

1. **Pre-flight must be done.** If `Security model verified` is blank on the PMC's row in the tracker, refuse and point the user at `frontier-model-preparation-model-verify`.
   This SKILL doesn't bypass the gate; it's the next step *after* the gate.

2. **Explicit operator instruction is required.** Pre-flight passing does not auto-trigger this SKILL.
   The operator must say "submit" / "queue" / "send the request" or similar for a specific named PMC.
   Surface PMCs in `pre-flight-passed-awaiting-operator-decision` state from `frontier-model-preparation-run`'s sweep;
   never fire on those automatically.

3. **Never submit an external form.** ASF Tooling enrolls scans internally from the tracker; there is no Google Form to fill and the `form-submitter` tool is retired (see "Retired: the `form-submitter` helper" below). Enrollment is setting `Date scan requested` + `Repositories submitted` on the PMC's row. Do not drive `form-submitter`, and do not draft any form submission.

4. **Every named contact on the PMC notification must be `@apache.org`-rooted and on the PMC roster.** Cross-check against the PMC sheet's `Contact Person` + `Backup contact` cells (which already carry `@apache.org` addresses per the scan-request verification gates) and against Apache Whimsy's roster page for the PMC.
   If a row has a placeholder like "JB" or a bare handle without a verifiable `@apache.org` address, surface it as a question —
   don't put unverifiable names into the email.

5. **Draft + confirm before writing the tracker or creating Gmail drafts.** Two confirmation gates apply to this SKILL:

   - **Enrollment gate.** Render the enrollment plan (the repo list ordered by Criticality Score with each repo's pre-flight verdict, and the exact `Date scan requested` + `Repositories submitted` values that will be written). The operator reviews and approves explicitly, then the update SKILL writes the cells (see step 8 — the *user* runs the update SKILL).
   - **PMC notification email gate.** After the tracker is set, render the PMC notification draft (To / CC / Subject / Body) and wait for explicit approval, then call `mcp__claude_ai_Gmail__create_draft`.
     Never call `send` directly —
     the user reviews in the Gmail UI once more and presses Send themselves.

5a.
**Refresh email threads and the spreadsheet before enrolling.** State on PMC threads and on the tracker moves fast —
late OSS-expedite requests, scope amendments, contact changes, additional questions, and chair-level go-aheads commonly land between sweeps.
An enrollment based on stale state can miss an expedite address the PMC asked for, submit the wrong scope, or skip a branch the PMC explicitly named.
Before rendering the enrollment plan:

   1. **Re-read the PMC's `[GLASSWING]` Gmail thread** via `mcp__claude_ai_Gmail__get_thread`.
      Look specifically for messages that arrived after the most recent `frontier-model-preparation-run` sweep:
      explicit submission green-lights, branch-level scope, OSS-expedite asks ("please include X in your expedite ask"), scope amendments.
      Surface any that the spreadsheet doesn't yet reflect.

   2. **Re-read the PMC's row** from the PMCs sheet via the Sheets API.
      Compare `Expedite Claude OSS Requests`, `Repositories requested`, `Contact Person`, `Backup contact`, `Security Model`, and any `Submission notes` against what the thread says.

   3. **If divergence is found**, apply the missing updates via `frontier-model-preparation-update apply` (Expedite, scope, submission notes) **before** rendering the enrollment plan.
      Don't try to short-circuit by passing values inline —
      the spreadsheet is the durable record the rest of the pipeline reads from, and ASF Tooling reads the scan queue straight off it.

   The enrollment plan the operator approves must reflect a spreadsheet snapshot that's been reconciled against the PMC thread in this session.
   Skipping this refresh is a bug, not an optimisation.

6. **Scope, ordering, and the per-repo discoverability filter.** `Repositories submitted` is the subset of the PMC's confirmed scope (`Repositories requested`) that passed pre-flight, with two filters:

   - **Only discoverability-passing repos.** A repo is enrolled only if the scan agent can reach its threat model — i.e. it has `AGENTS.md` (or a `SECURITY.md` / `security.txt` anchor) at HEAD, per `frontier-model-preparation-model-verify`'s Check A. Repos that fail discoverability are **held back**, not enrolled; land discoverability via `frontier-model-preparation-model-verify` and enroll them in a later batch. The natural "phased submission" pattern (e.g. Logging's wave 1 = log4j2 + log4net + log4cxx, wave 2+ as `AGENTS.md` lands) falls out of this filter without any separate phasing knob.

   - **Ordering by OSSF Criticality Score (descending).** Write `Repositories submitted` high-to-low by `Criticality Score (%)` (read from the Repositories sheet); repos with a blank score sort last. This is the order the Scan Queue tab presents them to ASF Tooling.

   Always show the per-repo verdict explicitly in the enrollment plan so the operator can see why some repos are in this batch and others are held back. Silently dropping a repo without surfacing it is a bug.

7. **What ASF Tooling reads — everything is already on the tracker.** The enrollment doesn't restate scan context anywhere; ASF Tooling reads it from the PMC's row and its linked tabs:

   - **Threat model** — the verified `Security Model` cell (surfaced on the Model Status tab). Must be non-empty and verified (`Security model verified` set).
   - **Maintainer roster / contacts** — `Contact Person` + `Backup contact`.
   - **Scan-result recipients** — derived from the contacts + the original `[GLASSWING]` request. Used for the PMC notification CC and the eventual `frontier-model-preparation-forward`; ASF Tooling delivers results back to the ASF Security team, which forwards manually, so the recipient list is **not** something the enrollment pins into a queue field.
   - **OSS-expedite ask** — the `Expedite Claude OSS Requests` cell (non-empty and not `none`). On enrollment (`Date scan requested` set), `build-status-tab` relays each expedite address into `Claude OSS Subscriptions Submitted` and the OSS Subscriptions registry automatically. There is no per-scan checkbox anymore; the tracker cell IS the expedite signal.
   - **Per-PMC quirks** — the `Submission notes` cell (branch-level scope, repo opt-outs, model-URL caveats). ASF-Tooling-facing free text; do NOT put internal-process overrides there (no scan-result delivery destinations — that's an ASF-internal forwarding detail).

8. **After the tracker is set AND the user sends the PMC notification email, `frontier-model-preparation-update` writes two cells** on the PMC's row to the dates the work actually happened:

    - `Date scan requested` — today (the enrollment date).
    - `Repositories submitted` — the exact list of repo URLs enrolled, newline-separated, in descending-Criticality order.

    Setting `Date scan requested` is what moves the PMC to the `Submitted` state and what projects its repos into the Scan Queue tab (flagged `Added after ASF tooling started` = Yes).

    This SKILL does not write to the spreadsheet directly;
    it produces the two values (`Date scan requested`, `Repositories submitted`) and hands off to the update SKILL.

9. **CC discipline on the PMC notification.** The PMC notification email's CC list is:

   - `security@apache.org` (Foundation-level audit trail);
   - `private@<pmc>.apache.org` (PMC collective visibility);
   - the project's `security@<pmc>.apache.org` alias if one exists (look it up via <https://security.apache.org/projects/>);
   - **`private@tooling.apache.org`** (the ASF Tooling PMC private list);
   - the backup PMC contact (the primary is on the To: line);
   - every `@apache.org` address listed in the original `[GLASSWING]` request as a scan-result recipient.

   These are the people who need to know the scan has been queued and who will receive the eventual forwarded results.
   The notification is sent as a reply on the PMC's original `[GLASSWING]` request thread (step 7 of the procedure),
   so the whole engagement stays on one thread of record.

10. **Program-cost confidentiality on PMC-facing email.** The PMC notification email follows `frontier-model-preparation-response`'s hard rule 5 (Program-cost confidentiality):
    the body must not disclose the program's cost mechanics (the $1M credit value, per-MTok credit pricing, or seat/provisioning mechanics).
    ASF Tooling (the runner), the Frontier Model Preparation *program name* (already in the `[GLASSWING]` subject line),
    Mythos / Mythos-5, Anthropic, Apache Magpie, and Claude OSS are all fine to name.
    What stays out is only the program's cost mechanics.

## Inputs the SKILL needs before enrolling

| Input | Source |
| --- | --- |
| Explicit operator instruction | Conversation (no inference from sheet state alone) |
| PMC name and slug | From the request, or the user supplies it |
| Repos to enroll | The subset of `Repositories requested` that passed pre-flight (discoverability), ordered by OSSF Criticality Score (descending) — read from the Repositories sheet. If pre-flight passed for *all* repos, the enroll list equals that cell; if only some, enroll only those and hold the rest for a later batch. **Always show the per-repo verdict explicitly** so the operator can see why some repos are in this batch and others aren't. |
| Threat-model URL | The PMC sheet's `Security Model` column + the verify SKILL's notes — must be verified (`Security model verified` set). ASF Tooling reads it off the tracker / Model Status tab. |
| Primary + backup PMC contacts | The PMC sheet's `Contact Person` + `Backup contact` cells (already `@apache.org` per scan-request verification) — for the PMC notification email. |
| Scan-result recipients | Derived from `Contact Person` + `Backup contact` + the original `[GLASSWING]` request body's "send results to" list. Used for the PMC notification CC and the eventual forward; the Security team handles delivery manually when results land. |
| Expedite addresses | The PMC sheet's `Expedite Claude OSS Requests` column. May be empty or `none`. `build-status-tab` relays these into the OSS-subscriptions columns on enrollment. |
| Submission notes (optional) | The PMC sheet's `Submission notes` column. Free-text ASF-Tooling-facing notes (branch-level scope, repo opt-outs, model-URL caveats). Do NOT put internal-process overrides here. |
| `Security model verified` date | The PMC sheet — confirms pre-flight gate |

If any of these are missing or ambiguous, surface as a question to the user before enrolling.

## PMC notification email template

**Program-cost confidentiality reminder** — this email is PMC-facing.
Per `frontier-model-preparation-response` hard rule 5, the body must not disclose the program's cost mechanics (the $1M credit value, per-MTok credit pricing, or seat/provisioning mechanics).
ASF Tooling (the runner), the Frontier Model Preparation program name, Mythos / Mythos-5, Anthropic, Apache Magpie, and Claude OSS are all fine to mention by name in the body;
only the cost mechanics are what stays out.

**To**: primary PMC contact (the `Contact Person` cell's `@apache.org` address)

**CC**: backup PMC contact(s) (from `Backup contact`), `private@<pmc>.apache.org`, `security@<pmc>.apache.org` *(if exists)*, `security@apache.org`, `private@tooling.apache.org`, every `@apache.org` address from the original `[GLASSWING]` request's "send results to" list.

**Subject**: reply on the PMC's original `[GLASSWING]` request thread —
reuse that thread's subject with a `Re:` prefix (e.g. `Re: [GLASSWING] <PMC name>: request to scan repositories`).
Do **not** invent a new subject:
a distinct subject is what used to split the notification off into its own Gmail thread.
Keeping the original subject (and replying in-thread) keeps the whole engagement — scoping → enrollment → eventual forward — on a single thread.
(Program-cost confidentiality still applies to the subject: keep the program's cost mechanics out of it.)

**Body**:

```text
Hi <Primary contact first name>,

The scan request for Apache <PMC name> has been queued by
the ASF Security team. Repos are scanned in the sequence of
submission; we'd rather not give you a date we can't stand
behind.

Repos queued (ordered by OSSF Criticality Score):
  1. <repo URL 1>  (highest criticality)
  2. <repo URL 2>
  3. <repo URL 3>
  ...

A program-shape note for context.

The scans are run internally by the ASF — the ASF Security,
ASF Infrastructure, and ASF Tooling teams jointly (ASF Tooling),
on the Mythos-5 model. From the PMC's perspective the process
is pre-flight gate, scan, sanity-check, and forward of results
to your named recipients. We mention it so you have the full
picture of how the program is wired — nothing changes about
what shows up in your inbox.

You don't need to do anything until the results arrive
— we'll sanity-check ASF Tooling's report and forward it
verbatim to your named scan-result recipients on a fresh
thread.

<IF the Expedite Claude OSS Requests cell was non-empty
and not "none", include this block; otherwise omit>
Anthropic Claude-for-OSS expedite request:
We've recorded an expedite ask for the following @apache.org
addresses you nominated, so the ASF Tooling scan team has it
alongside the scan enrollment:

  - <addr1@apache.org>
  - <addr2@apache.org>
  - ...

No promises from us or from Anthropic — the ASF Tooling scan
team makes the call. The named PMC members should already have
registered at https://claude.com/contact-sales/claude-for-oss
with their @apache.org address (which is the prerequisite the
expedite ask references).
</block>

Best,
<sign-off>
```

## Procedure

1. **Confirm explicit operator instruction.** This SKILL does not fire on pre-flight pass alone.
   If the operator hasn't named the PMC + said "submit" / "queue" / "send the request" or similar, refuse and surface the PMC as `pre-flight-passed-awaiting-operator-decision` instead.

2. **Refresh state (per hard rule 5a) before anything else.** Re-fetch the PMC's `[GLASSWING]` Gmail thread and the PMC's row from the spreadsheet **in this session** —
   not from a prior sweep.
   Surface to the operator any divergence the spreadsheet doesn't reflect:
   - late OSS-expedite ask ("please include X in your expedite ask") that isn't in `Expedite Claude OSS Requests` yet;
   - branch-level scope ("scan main + 2.x of <repo>") that isn't captured in `Submission notes`;
   - recipient override ("send results to project alias / to addr X") that isn't reflected in the contacts;
   - the explicit submission green-light (operator instruction).
   Apply missing updates via `frontier-model-preparation-update apply` **before** rendering the enrollment plan.
   The spreadsheet is the durable record ASF Tooling reads the queue from; don't try to pass values inline.

3. **Confirm pre-flight passed.** Read the PMC's row in the tracker via `frontier-model-preparation-status` (or directly via the Sheets API per the truncation caveat in `frontier-model-preparation-run` Step 2).
   Verify:
   - `Repositories requested` is non-empty (scope was confirmed by the PMC via `frontier-model-preparation-response` gate 4);
   - `Security model verified` is non-empty;
   - `Security Model` is non-empty;
   - `Contact Person` and `Backup contact` are non-empty and `@apache.org`-rooted.

   If any is missing, surface the gap and stop.
   Do not enroll against half-verified inputs.
   In particular, do not "fill in" a missing `Repositories requested` cell yourself —
   scope confirmation is the PMC's call, not the agent's.

4. **Gather the rest of the inputs** from:
   - the PMC sheet's `Repositories requested` cell (the confirmed scope; parse newline-separated URLs);
   - the Repositories sheet (read each repo's Criticality Score for the enrollment ordering);
   - each repo's discoverability at HEAD (the pre-flight Check A verdict — only discoverability-passing repos are enrolled);
   - the original `[GLASSWING]` thread (for the scan-result recipient list — used in the PMC notification CC);
   - the `Expedite Claude OSS Requests` cell (parse newline-separated `@apache.org` addresses; empty or `none` = no expedite block);
   - the `Submission notes` cell (free-text ASF-Tooling-facing notes; ASF Tooling reads them off the tracker).

5. **Look up the per-PMC `security@<pmc>` alias** at <https://security.apache.org/projects/> (or the source-of-truth JSON at <https://github.com/apache/security-site/blob/main/scripts/project-coordinates.json>).
   If the alias exists, add it to the PMC notification email's CC list.

6. **Render the enrollment plan and wait for explicit approval.** Show the operator:
   - The PMC name + slug.
   - The repo list, each with its Criticality Score and pre-flight (discoverability) verdict, sorted descending — and which repos are held back and why.
   - The exact values that will be written: `Date scan requested` (today) and `Repositories submitted` (newline-separated repo URLs, in that order).
   - A note that on enrollment the Scan Queue tab will project these repos (flagged `Added after ASF tooling started` = Yes) and `build-status-tab` will relay any expedite addresses into the OSS-subscription columns.

   Cite inputs ("repos from the `Repositories requested` cell, ordered by `Criticality Score` from the Repositories sheet; expedite addresses from the `Expedite Claude OSS Requests` cell").
   Wait for "ok" / "submit" / "go" / similar. If the user wants edits, revise and re-render before re-asking. Substantive rewrites need fresh approval.

7. **Render + draft the PMC notification email.** Show To / CC / Subject / Body using the enrolled repo list and the expedite-block toggle (based on whether the `Expedite Claude OSS Requests` cell is non-empty and not `none`). Wait for explicit approval, then create the Gmail draft via `mcp__claude_ai_Gmail__create_draft`:
    - `to`: the primary contact's `@apache.org` address
    - `cc`: the full CC list from step 5
    - `subject`: `Re: ` + the PMC's original `[GLASSWING]` request thread subject (so Gmail keeps it on that thread)
    - `body`: the rendered body
    - `replyToMessageId`: **the latest message id in the PMC's original `[GLASSWING]` request thread.** Resolve it with `mcp__claude_ai_Gmail__get_thread` on that thread and take the newest message's id.
      This threads the notification onto the existing request thread instead of opening a new one.
      Note: when `replyToMessageId` is set, `create_draft` appends the rendered body below the quoted original — that is the intended reply shape.

8. **Hand off to `frontier-model-preparation-update`.** Surface the line:

    > Queued: <N> repos for <slug>, enrollment date <today>.
    > Drafted in Gmail: PMC notification draft id `<id>`.
    > After you send the notification, set
    > `Date scan requested` + `Repositories submitted` on
    > the `<slug>` row via `frontier-model-preparation-update`,
    > then refresh `build-status-tab` so the Scan Queue picks
    > up the enrollment.
    > Suggested values:
    >   - Date scan requested: <today>
    >   - Repositories submitted: <newline-separated repo URLs>

    Do not invoke the update SKILL yourself;
    the user runs it once they've actually sent the notification email.

## Retired: the `form-submitter` helper

The scan program used to enroll via ASF Tooling's project-enrollment **Google Form**, driven by the `form-submitter` CLI in [`tools/form_submitter/`](../../../tools/form_submitter/) (a Playwright helper that filled one form per repo). That intake is **retired** — ASF Tooling now enrolls scans internally from the tracker + the `apache/tooling-agents-private` archive.

- **Do not run `form-submitter`.** It is kept in-tree as a legacy reference only (see its README); it is not part of the enrollment flow.
- There is **no** form to fill, no per-repo form submission, no headline/subsequent form, no "I'm interested in Claude Max 20x" checkbox. The expedite ask is conveyed by the `Expedite Claude OSS Requests` tracker cell (relayed into the OSS-subscription columns on enrollment); the threat model, roster, and per-PMC notes are conveyed by their tracker cells.

## Style notes

- **Don't restate what the recipient already knows.** The PMC has already heard the pipeline mechanics (sanity-check, verbatim forward, no per-finding triage on our side) in the pre-flight-pass email.
  The notification email is a status update — the scan is queued, here are the repos, here's the expedite-ask block if applicable.
  Cut "what happens next" recaps and process preambles; keep substance (repo list, expedite addresses, the reassurance that no PMC action is needed yet).
- **One PMC per enrollment run.** Don't batch multiple PMCs into a single enrollment. Each PMC has its own ordering and its own expedite ask; one enrollment produces one PMC notification email.
- **No marketing.** The audience is Apache PMC members (notification email); they don't need "cutting-edge" or "next-generation" framing.
- **Be specific about per-repo discoverability.** If a repo's discoverability is only present via a pending PR, hold it back from this batch and note it ("apache/<repo> enrolls once AGENTS.md+SECURITY.md merges in apache/<repo>#NN") rather than enrolling a repo the scan agent can't reach the model for.
- **Don't promise PMC-side response times** in the notification email. "PMC contacts will triage" is a *commitment to attempt* — not a service-level guarantee.
- **Sign in the human's voice, not the agent's.** This SKILL drafts; the human signs. Leave a `<sign-off>` placeholder in the email body.

## Examples of bad enrollments (avoid)

- Submitting or drafting any external Google Form, or running `form-submitter`. There is no form — enrollment is setting the tracker (hard rule 3).
- Enrolling a repo whose discoverability is only pending in an open PR. Hold it back until the PR merges (hard rule 6).
- Enrolling a PMC whose `Security model verified` cell is blank. Violates hard rule 1.
- Enrolling on pre-flight pass alone, without explicit operator instruction. Violates hard rule 2.
- Forgetting the PMC notification email entirely. Setting the tracker doesn't notify the PMC; the notification email does.
- Disclosing the program's cost mechanics — the $1M credit value, per-MTok credit pricing, or seat/provisioning details — in the PMC notification email body (per hard rule 10). ASF Tooling (the runner), the program name, Mythos / Mythos-5, and Anthropic are all fine to name; only the cost mechanics stay out.

## Provenance

This SKILL captures the handoff step between the ASF Security team's pre-flight (which lives in `frontier-model-preparation-model-verify`) and ASF Tooling actually running the scan.

Enrollment history: the earliest shape auto-fired on pre-flight pass; a 2026-05-17 revision made it operator-gated and email-based (`mirko@alpha-omega.dev`); a 2026-05-19 revision moved intake to an external Google Form (driven by `form-submitter`). With the program moving in-house to **ASF Tooling** (Mythos-5, officially provisioned 2026-07-01), the external form/relay is **retired**: ASF Tooling runs scans internally and reads the queue directly from the Mythos tracker and the `apache/tooling-agents-private` archive. Enrollment is therefore just recording the scan in the tracker — set `Date scan requested` + `Repositories submitted`, criticality-ordered.

The operator-gated trigger and the `pre-flight-passed-awaiting-operator-decision` pipeline state both stay;
enrollment still requires explicit operator say-so, not just pre-flight pass.
