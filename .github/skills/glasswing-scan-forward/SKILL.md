---
name: glasswing-scan-forward
description: Process a scan report received from Mirko Svilus / Alpha-Omega and forward it to the appropriate PMC after a Security-team pre-forward sanity check. Identifies which PMC the scan belongs to, sanity-checks the report for catastrophic generation errors (wrong project, wrong/stale model, truncated output, accidentally-mixed PMCs, mangled formatting), archives the raw scan into the team's private `scans/` tree, and drafts a forwarding email to the PMC's listed scan-result recipients with the vendor's findings forwarded verbatim. The team does NOT do per-finding triage — that's the PMC's job against their own threat model. Output is a Gmail draft for human review — never sends directly. After send, hand off to glasswing-scan-update to set `Date scan received` and `Forwarded scan to PMC` on the PMC's row. Use whenever an email from `@alpha-omega.dev` arrives with a scan report, or whenever Jarek says "process the X scan results", "forward the X report", or "the X scan is back".
---

# glasswing-scan-forward SKILL

The "results path" of the Glasswing pipeline — the inverse of
`glasswing-scan-submit`. Where `submit` sends a request *to*
Mirko and waits, this SKILL handles the report coming *back*:
identify the PMC, do a **pre-forward sanity check** on the
report, archive the raw scan into the team's private `scans/`
tree, and forward the vendor's report to the PMC's named
recipients.

The Security team's role is **gatekeeping for catastrophic
generation errors** — wrong project, wrong/stale model,
truncated output, accidentally-mixed PMCs, mangled formatting.
The PMC gets the vendor's findings unedited; per-finding
triage is the PMC's job against their own threat model. The
goal is to spend a few minutes of a Security-team member's
time so the PMC isn't asked to read a clearly broken report
— not to second-guess individual findings.

## When to invoke

- An email arrives from `mirko@alpha-omega.dev` or
  `@alpha-omega.dev` with a scan report attached, inline, or
  linked.
- Jarek says "process the <PMC> scan results", "the <PMC>
  scan is back, let's forward it", "sanity-check the <PMC>
  scan", or anything similarly explicit.
- The Mythos tracker shows a PMC with `Date scan requested`
  filled but `Date scan received` blank, and a Mirko reply
  has landed in Gmail.

Skip when:
- The scan is for a PMC whose row indicates incomplete
  pre-flight (`Security model verified` blank). Should not
  happen — but if it does, surface the gap rather than
  proceed.

## Hard rules (do not skip)

1. **Sanity-check the report before forwarding.** Read
   through Mirko's output looking for catastrophic
   generation errors — wrong project, wrong/stale model
   metadata, truncated output, accidentally-mixed PMCs,
   mangled formatting, repos the PMC didn't submit (or
   submitted repos missing entirely). The checklist below
   ("Sanity-check checklist") names what to look for. If
   anything looks broken, surface to the user before
   drafting; typically that means going back to Mirko
   with the issue rather than forwarding a known-broken
   report.

2. **Forward the vendor's findings verbatim — no
   per-finding triage.** The PMC owns the read against
   their own threat model. The Security team does **not**
   classify findings, drop findings, filter findings,
   suppress findings, or annotate findings with model
   citations on the PMC's behalf. The team's role is the
   sanity check in rule 1 and nothing further on the
   substance of the findings. If a finding looks weak,
   misguided, or out of scope to the team — that's the
   PMC's call to make, not ours.

3. **When uncertain whether something is a generation
   error or a real finding, forward as-is.** Sanity-check
   bar is "the report is recognisably the vendor's actual
   output for this project at this model", not "the
   findings look correct to the team". If a finding looks
   odd but the report otherwise passes the checklist,
   forward — the PMC's reviewer decides.

4. **Use the PMC's specified scan-result destination — and
   every address on the To/Cc must be `@apache.org`-rooted.**
   The original `[GLASSWING]` request listed the scan-result
   email addresses explicitly (e.g. "Please send scan results
   to `security@logging.apache.org`" or a list of personal
   `@apache.org` addresses). That's the To: for the forward.

   **Hard restriction — `@apache.org` only:** every address on
   the To: and Cc: of the forward must end in `@apache.org` or
   `@<pmc>.apache.org`. Acceptable shapes:

   - personal `@apache.org` addresses of named PMC members,
   - `private@<pmc>.apache.org`,
   - `security@<pmc>.apache.org` (where the alias exists),
   - `security@apache.org` (Foundation audit trail — always Cc'd).

   **Not acceptable**, even if requested by a PMC member or
   recorded in the tracker:

   - personal `@gmail.com` / `@employer.com` / other addresses,
   - any address that isn't anchored to ASF identity.

   **Why**: scan reports contain pre-disclosure vulnerability
   candidates. The `@apache.org` rooting is the cheapest
   verification that the recipient is still an ASF member with
   the right to see them. The vendor (Alpha-Omega) also
   expects ASF-anchored recipient addresses as the trust
   boundary. A PMC member who wants results to land in their
   personal inbox can configure their `@apache.org` address to
   forward there — that's the standard Apache committer pattern
   and it keeps the boundary on our side.

   **If the tracker's results-destination cell or the request's
   stated destination contains a non-`@apache.org` address**:
   surface the conflict before drafting the forward. Do not
   silently substitute; flag to the user, who decides whether
   to (a) ask the PMC to designate an `@apache.org` alternative,
   or (b) route via the PMC's `private@<pmc>` list with the
   non-`@apache.org` address dropped from the recipient list.

5. **Draft + confirm before creating the Gmail draft.** Same
   pattern as every other write-capable SKILL: render the
   full draft (To / CC / Subject / body / finding count /
   sanity-check verdict), wait for "yes" / "send" / "go",
   then call `mcp__claude_ai_Gmail__create_draft`. Never
   call `send` directly.

6. **CC discipline.** The CC list:
   - `security@apache.org` (Foundation-level audit trail);
   - `private@<pmc>.apache.org` (PMC collective visibility);
   - the project's `security@<pmc>.apache.org` alias if one
     exists;
   - the PMC's primary + backup contacts (the named
     humans);
   - **not** Mirko/Alpha-Omega (the forward is internal to
     ASF; if Mirko needs follow-up, that's a separate
     thread).

7. **After the user sends, hand off to
   `glasswing-scan-update`** to write two cells on the PMC's
   row:
   - `Date scan received` — the date Mirko's email arrived
     (the original send date, not today).
   - `Forwarded scan to PMC` — today's date (when the user
     clicked Send on the forward).

   This SKILL does not write to the spreadsheet directly.

8. **Surface sanity-check observations explicitly when
   present.** If the sanity check turned up anything worth
   the PMC's awareness (e.g. "vendor's metadata cites a
   stale model commit; current model body is unchanged",
   "one of the three submitted repos is missing from the
   report — asked the vendor to re-run for it"), include
   a short `Sanity-check observations` block in the
   forwarding email. If the check passed cleanly with
   nothing to note, omit the block — don't pad with
   "everything looked fine".

9. **Always archive the scan into `scans/` before
   forwarding.** Per the spec in
   [`scans/README.md`](../../../scans/README.md), every
   Mirko-delivered scan that the team forwards must first
   land in `scans/<project>/<repo>/<project>-<repo>-<YYYY-
   MM-DD>-<short-sha>.md` (plus `.json` raw + `.notes.md`
   decision-log sidecars) and be committed with a `[scan]`
   prefixed message. The archive commit happens **before**
   the Gmail draft is created so the forwarding email can
   cite the canonical filename. A scan that has been
   forwarded without an archive entry is a process bug.

10. **Vendor opacity in the PMC-facing forwarding
    email.** This email is PMC-facing; per
    `glasswing-scan-response` hard rule 5, the body must
    not name the scan vendor (no "Mirko", no
    "Alpha-Omega", no "the Glasswing pipeline" used as
    vendor synonym, no `mirko@alpha-omega.dev`). The
    existing template uses generic "vendor" and "scan
    pipeline" phrasing throughout — keep it that way. The
    Glasswing **program name** is fine ("The Glasswing
    scan for Apache X is back" is what the template
    opens with — that's the program name in the subject
    line, not vendor identity). Anthropic / Apache Magpie
    / Claude OSS are fine to mention by name; vendor
    identity is what's redacted. Internal SKILL doc
    sections (the "Why" rationales, the procedure steps)
    can name Mirko / Alpha-Omega freely — those are
    internal context for the agent, not PMC-visible.

## Sanity-check checklist

Before forwarding, scan the vendor's output for catastrophic
generation errors:

| Check | What "fail" looks like |
| --- | --- |
| **Project identity** | The report's project / repo identifiers match what was submitted. Catches obvious cases like a scan accidentally run against `apache/foo` when we submitted `apache/bar`, or report metadata naming a different PMC. |
| **Model identity** | The threat model the vendor cites in metadata matches the model URL recorded for the PMC, at a recent enough commit. Catches "vendor ran against a stale or wrong model" cases. |
| **Repo coverage** | Every repo the team submitted appears somewhere in the report. A scan that silently dropped one of N submitted repos is a generation error worth surfacing back to the vendor. |
| **Truncation** | The report doesn't end mid-finding / mid-section / mid-line. Mirko's output is typically a single markdown document; if the last finding's body is cut off mid-sentence, that's a truncation. |
| **Cross-PMC leakage** | No findings or text from a different PMC's scan accidentally ended up in this report. Rare but high-blast-radius if it slips through. |
| **Formatting integrity** | Markdown actually renders; no half-escaped JSON blobs in the body; no obviously broken tables; no missing headings that would render as plain text. |
| **Plausibility** | Sanity-check that the finding count and topic distribution look reasonable for the project (e.g. a scan of a logging library returning 100 findings about cryptography is a signal the report may have been mis-routed). Not a triage step — just a "does this look like the vendor actually ran on the right thing" check. |

If any check fails: **stop**, surface to the user before drafting
the forward. Typically the resolution is asking Mirko to re-run
or re-send, not forwarding a known-broken report to the PMC.

If every check passes: the report is forwarded **verbatim** to
the PMC. The team does not add finding-by-finding annotations,
classifications, or filter decisions. Anything worth flagging
from the sanity check itself (e.g. "vendor metadata cites a
stale model commit; model body unchanged") goes into the
`Sanity-check observations` block in the forwarding email.

**This is not per-finding triage.** Do not classify findings
against the threat model, drop findings as "out of scope",
suppress findings as "known non-findings", or annotate findings
with model citations. The PMC owns that read.

## Inputs the SKILL needs

| Input | Source |
| --- | --- |
| PMC name and slug | From Mirko's email subject (`[GLASSWING] results for <PMC>` or similar), or the user supplies it |
| Scan report content | Attachment(s) or inline content of Mirko's email |
| PMC threat model URL | From the PMC sheet's `Security Model` column. Used only for the **model identity** sanity check (does the vendor's metadata cite this URL?) and as the URL the forward references — not for per-finding filtering. |
| Submitted repos list | From the PMC sheet's `Repositories submitted` cell (filled when `glasswing-scan-submit` ran). Used for the **repo coverage** sanity check. |
| Scan-result recipient list | From the original `[GLASSWING]` request thread (or the PMC sheet's `Notes` if recorded there) |
| Primary + backup PMC contacts | From the PMC sheet |
| `Date scan requested` (sanity check) | From the PMC sheet |

If the threat model URL, the submitted-repos list, the
recipient list, or the `Date scan requested` is missing,
refuse and surface the gap.

## Procedure

1. **Identify the PMC.** From the subject line of Mirko's
   email (`[GLASSWING] results for Apache <PMC name>` is the
   expected pattern). If ambiguous, surface a question
   listing the candidate PMCs.

2. **Pull the PMC's row** from the Mythos tracker (via the
   `glasswing-scan-status` flow or a direct read of the
   `mythos-tracker` reference memory file ID). Confirm:
   - `Scan Requested = Yes`
   - `Repositories submitted` is non-empty (matches what was
     sent to Mirko)
   - `Date scan requested` is filled
   - `Date scan received` is blank (no double-forward)
   - `Forwarded scan to PMC` is blank

   Refuse if any pre-condition is wrong.

3. **Note the threat model URL.** Used for the **model
   identity** sanity check (does the vendor's metadata
   cite this URL, at a recent enough commit?) and as the
   URL the forwarding email references. Do **not** read
   the model to triage findings — the team's job is
   sanity check, not classification.

4. **Run the sanity-check pass** described in the
   "Sanity-check checklist" section above. For each
   check, record one of `PASS` / `PASS-with-note: <text>`
   / `FAIL: <text>`. Produce a short sanity-check log:

   ```
   Project identity: PASS
   Model identity: PASS-with-note: vendor cites model
     commit abc123; current HEAD is def456, model body
     unchanged (verified by diff).
   Repo coverage: PASS — all 3 submitted repos present.
   Truncation: PASS.
   Cross-PMC leakage: PASS.
   Formatting integrity: PASS.
   Plausibility: PASS — finding mix matches project
     surface area.
   ```

   On any `FAIL`: stop, surface to user, escalate to Mirko
   before continuing. Do not draft the forward.

5. **Take the vendor's findings verbatim.** No
   classification, no filtering, no per-finding
   annotation. The forwarded-findings list is just
   Mirko's findings in the order Mirko provided.

6. **Archive the scan into the `scans/` tree** — per the
   [`scans/README.md`](../../../scans/README.md) spec. This
   step happens **before** the email is drafted so the
   forwarding email can cite the canonical filename, giving
   the PMC a stable identifier to refer back to without
   needing access to this private repo.

   For each repo that Mirko's report covers (a scan may
   cover multiple repos in one report; treat each as a
   separate archive entry):

   1. **Determine the head SHA** — extract from Mirko's
      report if present; otherwise query
      `gh api repos/apache/<repo>/commits/HEAD --jq .sha`
      using the date Mirko ran the scan (typically the
      `scan_date` Mirko reports, or the report's own
      received date if Mirko omitted it).

   2. **Compute the path**:

      ```
      scans/<project>/<repo>/<project>-<repo>-<YYYY-MM-DD>-<short-sha>.md
      ```

      where `<project>` is the PMC slug, `<repo>` is the
      `apache/<repo>` name, `<YYYY-MM-DD>` is the UTC scan
      completion date, and `<short-sha>` is the first 8
      hex chars of the head SHA. Create the parent
      directories if missing.

      If a file at this exact path already exists (rare —
      same repo scanned twice in one UTC day at the same
      SHA prefix), suffix the filename with `-2`, `-3`, …
      per the worked-examples table in
      [`scans/README.md`](../../../scans/README.md).

   3. **Write the canonical markdown file** with the YAML
      front-matter spelled out in the spec:

      ```yaml
      ---
      project:           <pmc-slug>
      repo:              apache/<repo>
      head_sha:          <full 40-char SHA>
      scan_date:         <YYYY-MM-DD>T<HH:MM:SS>Z
      glasswing_model:   <model id Mirko reported>
      threat_model:      <model URL recorded for the PMC in the tracker>
      findings_total:    <count from Mirko's report>
      sanity_check:      <PASS / PASS-with-notes / RETURNED-TO-VENDOR>
      sanity_checked_by: <agent operator's @apache.org>
      sanity_check_date: <YYYY-MM-DD>
      ---
      ```

      followed by the vendor's findings **verbatim** (one
      finding per `## ` heading, with whatever
      file/lines / property / reproducer / severity hint
      the vendor included — not re-formatted by the team).

   4. **Write the `.json` sidecar** with the same filename
      prefix and `.json` extension — Mirko's raw report
      verbatim, so the archive is auditable later. Use
      the exact filename:
      `<project>-<repo>-<YYYY-MM-DD>-<short-sha>.json`.

   5. **Write the `.notes.md` sidecar** with the
      sanity-check log from step 4 (the per-check
      PASS/PASS-with-note/FAIL lines, plus any free-form
      observation worth recording — e.g. "asked Mirko to
      re-run because the lucene-core repo was missing"
      or "current PMC model URL has moved since vendor
      ran; updated the canonical archive file with the
      live URL"). Same filename prefix, `.notes.md`
      extension. This is the audit record of *what we
      sanity-checked*, not a per-finding decision log.

   6. **Stage and commit** all three files (`<filename>.md`,
      `.json`, `.notes.md`) in **one** commit. Commit
      message format (per the spec's checklist):

      ```
      [scan] <project>/<repo> <YYYY-MM-DD>-<short-sha>

      Glasswing scan against apache/<repo> at <full-sha>.
      Findings: <N>. Sanity check: <PASS / PASS-with-notes
      / RETURNED-TO-VENDOR>. Forwarded to PMC verbatim.

      Generated-by: Claude Code (Claude Opus 4.7)
      ```

      Show the user the planned commit (file list + first
      ~10 lines of each file) and wait for explicit "yes"
      before running `git commit`. Push only after the
      forwarding email is also drafted (step 8) so the
      two artefacts land together.

   7. **Record the archive filename** — the forwarding
      email (next step) cites the canonical filename
      (e.g. `lucene-lucene-2026-05-13-a95e678d`) so the
      PMC has a stable, repo-independent identifier.

7. **Draft the forwarding email.** Template below. Cite
   the archive filename(s) from step 6 in the email body
   so the PMC has the canonical identifier. Show the full
   draft + the sanity-check log + the planned commit
   to the user.

8. **Wait for explicit approval** ("yes" / "send it" / "go"
   / similar). The approval covers both the commit (step 6)
   and the email draft (step 7). If the user wants edits
   to the sanity-check log (e.g. a check the agent missed),
   revise the log, regenerate the email + the archive files,
   re-show.

9. **Create the Gmail draft** via
   `mcp__claude_ai_Gmail__create_draft`. `replyToMessageId`
   is **omitted** — this is a new thread to the PMC's
   recipients, not a reply to Mirko's thread.

10. **Push the archive commit** to `origin/main` (or open a
    PR per local convention — the spec is that the
    canonical archive lives in `main`). The push happens
    *after* the Gmail draft is created, so an archive
    commit without a corresponding draft is rare; surface
    if it happens.

11. **Hand off to `glasswing-scan-update`** to write
    `Date scan received` (Mirko's send date) and
    `Forwarded scan to PMC` (today's date) on the PMC's
    row. The Gmail draft id and archive filename(s)
    should also land in the `Notes` cell so the next
    sweep sees a complete record.

## Email template

**To**: PMC's specified scan-result recipients (from the
original request; usually a list of `@apache.org` addresses
and/or `security@<pmc>.apache.org`).

**CC**: `security@apache.org`, `private@<pmc>.apache.org`,
[`security@<pmc>.apache.org` if exists, and not already on
To], primary + backup PMC contacts.

**Subject**: `[GLASSWING] Scan results for Apache <PMC name> — <YYYY-MM-DD>`

**Body**:

```text
Hi <primary contact first name (and any others)>,

The Glasswing scan for Apache <PMC name> is back. Before
passing it on, the Security team has done a quick pre-forward
sanity check to make sure the report isn't catastrophically
broken — right project, right model, no truncation, all
submitted repos covered, no cross-PMC leakage, plausible
finding mix. The report passed the check; the vendor's
findings are forwarded verbatim below.

We're explicitly not pre-classifying or pre-triaging the
findings on your behalf — that's your call against the
project's threat model at <model URL>, through your normal
private@<pmc>.apache.org triage process. Our role on results
is the sanity check only.

Canonical scan reference(s) (cite these in your tracker —
each archives the raw vendor output + our sanity-check notes
against apache/<repo> at the listed commit):

  - <project>-<repo>-<YYYY-MM-DD>-<short-sha>
  - <project>-<repo2>-<YYYY-MM-DD>-<short-sha>   [if multiple repos]

(Files are in the Security team's private archive at
scans/<project>/<repo>/; you don't have access to that repo,
but the filename is the stable identifier and the full
findings are in this email.)

Summary:
  Findings from Glasswing: <N>
  Sanity check: <PASS / PASS with notes — see block below>

Repos scanned (from the submission scope):
  - <repo URL 1>
  - <repo URL 2>
  - ...

Threat model the scan was run against:
  <model URL>

<IF the sanity check produced anything worth flagging, include
this block; otherwise omit entirely. Do not pad with
"everything looked fine".>
Sanity-check observations:
  - <one-line bullet per observation — e.g. "vendor cites
    threat-model commit abc123; current HEAD is def456,
    model body unchanged" or "the apache/lucene-solr repo
    in scope returned zero findings, flagging in case
    that's unexpected">

=== FINDINGS ===

[Vendor's findings, forwarded verbatim, in the order the
vendor provided. Each finding's heading, file/line refs,
property cited, severity hint, reproducer sketch — all left
as the vendor wrote them. The Security team does not
re-format, re-classify, or add notes inside individual
findings.]

[... one block per finding ...]

=== NEXT STEPS ===

Triage through your normal process:
  private@<pmc>.apache.org -> CVE / coordinated disclosure /
  release flow.

If on closer look you find findings that fall clearly outside
your threat model (§3 out-of-scope, §11a known non-findings,
§9 disclaimed properties), a one-line "this falls outside the
model" reply back to security@apache.org helps us pass that
back to the vendor for the next scan's suppression list — but
the disposition call is yours, not ours.

Best,
<sign-off in the human's voice — the SKILL doesn't sign>
```

The email is from the ASF Security team's voice. Plain text;
no marketing flourish. Length is proportional to the report —
a 50-finding scan with 5 forwarded is a short email; a
5-finding scan with all 5 forwarded is still short.

## Style notes

- **Preserve the vendor's output verbatim.** Don't reformat
  findings, don't merge them, don't re-order them, don't
  rename their IDs. The PMC's triagers will quote findings
  back by ID; the IDs and shape need to match what's in the
  archived raw report.
- **Don't editorialize on severity, scope, or validity.**
  These are the PMC's calls. If the team thinks a finding
  is off-base, the right move is to flag it back to Mirko
  for the next scan's tuning — not annotate it in the
  forward.
- **No PMC findings should leak across PMCs.** The
  forwarded email is per-PMC. Don't accidentally CC a
  different PMC's `private@` list or include another PMC's
  findings as context. (This is also one of the sanity
  checks in step 4.)
- **The `Sanity-check observations` block is optional.**
  Include it only when the check turned up something worth
  noting. A clean check produces no block — don't pad with
  "everything looked fine".
- **Sign in the human's voice.** The SKILL drafts; the
  human signs. Leave `<sign-off>` placeholder rather than
  baking a signature.

## Examples of bad forwards (avoid)

- Forwarding a report that failed sanity check (wrong
  project, wrong/stale model, truncated, missing repos)
  rather than escalating to Mirko first. The whole point
  of the sanity check is to **not** waste the PMC's time
  on a clearly broken report — bypass it and you've
  defeated the purpose.
- Per-finding triage in the forward — disposition labels,
  "filtered as out-of-model" appendix, "we dropped 30
  findings as known non-findings", per-finding model
  citations from the team. None of that. The PMC owns the
  read against their own model; the team's role is the
  sanity check.
- Re-formatting or condensing the vendor's findings to
  make the email shorter. The PMC needs the full vendor
  text; if it's long, it's long.
- Sending the forward back to Mirko. Mirko doesn't need
  the PMC-facing email; if the Security team has follow-up
  for Mirko, that's a separate reply on Mirko's thread.
- Setting `Forwarded scan to PMC` before the user has
  actually clicked Send in Gmail. That cell tracks real
  delivery turnaround; pre-filling it pollutes the metric.
- A forward that pads the `Sanity-check observations`
  block with "all checks passed, nothing to note" or
  similar boilerplate. Omit the block entirely when there
  is nothing to flag.

## Provenance

This SKILL completes the back half of the Glasswing pipeline.
Earlier versions had the Security team doing per-finding
triage (classifying against the threat model, dropping
out-of-scope findings, filtering known non-findings into an
appendix) before forwarding. That scope was narrowed: the
team's role on results is now a **pre-forward sanity check
only** — catch catastrophic generation errors so the PMC
isn't asked to read a clearly broken report. Per-finding
triage stays with the PMC against their own model. The shift
keeps the Security team out of the position of editorialising
the vendor's output, and keeps the PMC's relationship with
the report direct rather than mediated.
