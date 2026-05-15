---
name: glasswing-scan-forward
description: Process a scan report received from Mirko Svilus / Alpha-Omega and forward it to the appropriate PMC after a Security-team slop-filter pass. Identifies which PMC the scan belongs to, reads the report against that PMC's threat model + known non-findings, removes obvious false positives, annotates remaining findings with the model section that licenses each disposition, and drafts a forwarding email to the PMC's listed scan-result recipients. Output is a Gmail draft for human review — never sends directly. After send, hand off to glasswing-scan-update to set `Date scan received` and `Forwarded scan to PMC` on the PMC's row. Use whenever an email from `@alpha-omega.dev` arrives with a scan report, or whenever Jarek says "process the X scan results", "forward the X report", or "the X scan is back".
---

# glasswing-scan-forward SKILL

The "results path" of the Glasswing pipeline — the inverse of
`glasswing-scan-submit`. Where `submit` sends a request *to*
Mirko and waits, this SKILL handles the report coming *back*:
identify the PMC, do the Security-team's slop-filter pass
against the PMC's own threat model + known non-findings, and
forward the curated output to the PMC's named recipients.

The Security team owes the PMC pre-reviewed findings, not raw
vendor output — the goal of the slop-filter is to spend an
hour of one Security-team member's time so the PMC doesn't
spend a day chasing scanner noise.

## When to invoke

- An email arrives from `mirko@alpha-omega.dev` or
  `@alpha-omega.dev` with a scan report attached, inline, or
  linked.
- Jarek says "process the <PMC> scan results", "the <PMC>
  scan is back, let's forward it", "slop-filter the <PMC>
  report", or anything similarly explicit.
- The Mythos tracker shows a PMC with `Date scan requested`
  filled but `Date scan received` blank, and a Mirko reply
  has landed in Gmail.

Skip when:
- The report needs PMC-specific context the Security team
  doesn't have (e.g. a finding the model explicitly punts on
  to deployment-specific decisions). In that case forward
  with the framing "we'd defer to PMC judgment on this one"
  rather than silently passing or filtering.
- The scan is for a PMC whose row indicates incomplete
  pre-flight (`Security model verified` blank). Should not
  happen — but if it does, surface the gap rather than
  proceed.

## Hard rules (do not skip)

1. **Always slop-filter before forwarding.** Mirko's output
   is raw — true positives, false positives, low-quality
   advisory items, and scanner noise are all in there. The
   Security team's job is to read all of it and forward
   *only* what's worth a PMC reviewer's time, with rationale
   for what was filtered.

2. **Cite the PMC's threat model for every filter
   decision.** If a finding is dropped because it's in
   §11a "known non-findings", say so. If it's out of
   scope per §3, cite that. If it's a `BY-DESIGN:
   property-disclaimed` case from §9, cite. **Never** drop
   a finding without a citable reason — that's the
   difference between curation and censorship.

3. **When uncertain, forward — don't filter.** A finding
   that looks like noise but isn't a clean §11a match
   should be forwarded with a `MODEL-GAP` note, not
   dropped. The PMC's reviewer is the final judge; the
   Security team is just a noise filter on the way there.

4. **Use the PMC's specified scan-result destination.** This
   is *not* the named contacts. The original `[GLASSWING]`
   request listed the scan-result email addresses
   explicitly (e.g. "Please send scan results to
   security@logging.apache.org" or a list of `@apache.org`
   addresses). That's the To: for the forward.

5. **Draft + confirm before creating the Gmail draft.** Same
   pattern as every other write-capable SKILL: render the
   full draft (To / CC / Subject / body / filtered count /
   forwarded count), wait for "yes" / "send" / "go", then
   call `mcp__claude_ai_Gmail__create_draft`. Never call
   `send` directly.

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

8. **Preserve every filtered finding in the slop-filter
   appendix.** The forward to the PMC includes a section
   titled "Filtered as known non-findings" (or similar) with
   one line per filtered finding + the section citation that
   licensed the filter. The PMC can spot-check the filter
   decisions, and the next scan (six months later, when the
   suppression list has grown) inherits the rationale.

## The slop-filter rubric

For each finding in Mirko's report, classify into exactly one
disposition (these mirror the threat-model-producer §13
triage labels):

| Label | Meaning | Action |
| --- | --- | --- |
| `VALID` | Violates a property the PMC's model claims, in-scope adversary + input. | Forward to PMC. Annotate with the §8 property violated. |
| `VALID-HARDENING` | Not a §8 violation, but matches §11 misuse pattern the PMC has elected to harden. | Forward to PMC, marked as `HARDENING`. |
| `OUT-OF-MODEL: trusted-input` | Requires attacker control of a parameter the model marks trusted (§6). | **Filter.** Note the §6 row that says trusted. |
| `OUT-OF-MODEL: adversary-not-in-scope` | Requires an attacker capability the model excludes (§7). | **Filter.** Note the §7 line. |
| `OUT-OF-MODEL: unsupported-component` | Lands in `contrib/`, `examples/`, or §3 explicit out-of-scope. | **Filter.** Note §3. |
| `OUT-OF-MODEL: non-default-build` | Only manifests under a discouraged §5a flag. | **Filter.** Note §5a. |
| `BY-DESIGN: property-disclaimed` | Concerns a property §9 explicitly says the project doesn't provide. | **Filter.** Note §9. |
| `KNOWN-NON-FINDING` | Matches a §11a entry. | **Filter.** Note the §11a row. |
| `MODEL-GAP` | Cannot be cleanly routed to any of the above. | **Forward** with a `MODEL-GAP` flag and one-line rationale. PMC judges + may update the model. |

The disposition column is what the slop-filter produces.
Forwarded findings get the full text + the disposition
label + the citing model section. Filtered findings appear
in the "Filtered" appendix with just the disposition label +
citation (the PMC can ask for the full text of any if
they want to spot-check).

## Inputs the SKILL needs

| Input | Source |
| --- | --- |
| PMC name and slug | From Mirko's email subject (`[GLASSWING] results for <PMC>` or similar), or the user supplies it |
| Scan report content | Attachment(s) or inline content of Mirko's email |
| PMC threat model URL | From the PMC sheet's `Security Model` column + the verified discoverability chain (model-verify SKILL) |
| §11a known non-findings | From the linked threat model (or its companion FAQ — Logging Services for example links to `logging.apache.org/security/faq.html`) |
| Scan-result recipient list | From the original `[GLASSWING]` request thread (or the PMC sheet's `Notes` if recorded there) |
| Primary + backup PMC contacts | From the PMC sheet |
| `Date scan requested` (sanity check) | From the PMC sheet |

If the threat model URL, the recipient list, or the
`Date scan requested` is missing, refuse and surface the gap.

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

3. **Fetch the threat model + §11a known non-findings.**
   Use the model URL recorded for the PMC. Some PMCs split
   non-findings into a separate FAQ doc (Logging Services
   does this); fetch both if so.

4. **Walk each finding in Mirko's report and assign a
   disposition** from the rubric above. Produce a per-
   finding decision log:

   ```
   Finding F-001: SQL injection in QueryBuilder.append()
     Disposition: OUT-OF-MODEL: trusted-input
     Rationale: §6 marks application code calling
       QueryBuilder as trusted. Caller must validate input
       before passing to .append(); not a framework bug.
     Action: filter.
   ```

5. **Build the forwarded-findings list** — only the
   `VALID`, `VALID-HARDENING`, and `MODEL-GAP` dispositions
   make it through. The `OUT-OF-MODEL:*`, `BY-DESIGN:*`,
   and `KNOWN-NON-FINDING` dispositions land in the
   "Filtered" appendix.

6. **Draft the forwarding email.** Template below. Show the
   full draft + the filter rationale list to the user.

7. **Wait for explicit approval** ("yes" / "send it" / "go"
   / similar). If the user wants edits to filter decisions,
   revise the decision log first, regenerate the email,
   re-show.

8. **Create the Gmail draft** via
   `mcp__claude_ai_Gmail__create_draft`. `replyToMessageId`
   is **omitted** — this is a new thread to the PMC's
   recipients, not a reply to Mirko's thread.

9. **Hand off to `glasswing-scan-update`** to write
   `Date scan received` (Mirko's send date) and
   `Forwarded scan to PMC` (today's date) on the PMC's row.

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

The Glasswing scan for Apache <PMC name> is back. The Security
team has done a slop-filter pass against the project's threat
model at <model URL>; the curated findings follow.

Summary:
  Total findings from Glasswing: <N>
  Forwarded (VALID / VALID-HARDENING / MODEL-GAP): <K>
  Filtered as out-of-model / known non-findings: <N - K>

Repos scanned (from the submission scope):
  - <repo URL 1>
  - <repo URL 2>
  - ...

Threat model the scan was run against:
  <model URL>
  (Scan rubric: apache/security threat-model-producer
  SKILL §13 dispositions.)

=== FORWARDED FINDINGS ===

[For each forwarded finding:]

Finding <ID> — <one-line title>
  Disposition: VALID  (or VALID-HARDENING / MODEL-GAP)
  Property violated (per your model): §8 — <property name>
  Reachability per your model: §4 — <preconditions>
  File / lines: <citation from scan>
  Severity hint (vendor): <severity>
  Reproducer sketch (if provided by vendor): <text>

  Security-team note (optional): <one-line rationale for
  why we kept this — particularly for MODEL-GAP findings,
  where we couldn't cleanly classify and want the PMC's
  read.>

[... one block per forwarded finding ...]

=== FILTERED FINDINGS (appendix) ===

We filtered <N - K> findings as out-of-model or known
non-findings. Each is one line below with the model section
that licensed the filter. Spot-check at will; happy to
forward the full text of any if you want a closer look.

  F-NNN — <short label>  ·  OUT-OF-MODEL: trusted-input  ·  §6 / trust assumption row N
  F-NNN — <short label>  ·  KNOWN-NON-FINDING  ·  §11a "<row title>"
  F-NNN — <short label>  ·  BY-DESIGN: property-disclaimed  ·  §9 "<property>"
  ...

=== NEXT STEPS ===

Triage through your normal process:
  private@<pmc>.apache.org -> CVE / coordinated disclosure /
  release flow.

If any of the FORWARDED findings turn out to be invalid on
closer look, ping security@apache.org with the finding ID
and the reason — it sharpens the slop-filter for the next
scan run. Same for MODEL-GAP entries: a one-line "this is
the right disposition" from the PMC lets us update §11a
(via a small PR if you like) so the next scan doesn't
re-discover them.

Best,
<sign-off in the human's voice — the SKILL doesn't sign>
```

The email is from the ASF Security team's voice. Plain text;
no marketing flourish. Length is proportional to the report —
a 50-finding scan with 5 forwarded is a short email; a
5-finding scan with all 5 forwarded is still short.

## Style notes

- **One finding per block.** Don't pack multiple findings
  into a paragraph — the PMC will quote individual findings
  back when triaging; one-per-block keeps the quoting
  clean.
- **Preserve the vendor's finding IDs.** Mirko's scans
  assign IDs (e.g. `F-001`). Keep them — they're the
  shared reference for follow-up conversation.
- **Don't editorialize on severity.** Mirko's severity hint
  is what it is; the PMC may disagree, and that's fine.
  Don't recompute severity in the forward.
- **Be explicit about MODEL-GAP rationale.** This is the
  one disposition the SKILL drives toward "PMC, please
  judge". The note should make clear why the existing
  model didn't cleanly cover the finding — that's the
  signal the PMC needs to update §11a or §9.
- **No PMC findings should leak across PMCs.** The
  forwarded email is per-PMC. Don't accidentally CC a
  different PMC's `private@` list or include another PMC's
  findings as context.
- **Sign in the human's voice.** The SKILL drafts; the
  human signs. Leave `<sign-off>` placeholder rather than
  baking a signature.

## Examples of bad forwards (avoid)

- Forwarding Mirko's raw output to the PMC without a slop-
  filter pass. The PMC doesn't want raw scanner output;
  they want the team's curated read.
- Filtering findings without citing the model section. A
  "we dropped 30 findings" line with no rationale is worse
  than no filter at all.
- Filtering aggressively to keep the forward small. The
  KPI isn't "small email"; it's "every kept finding is
  worth the reviewer's time". If 40 of 45 findings are
  valid, forward 40.
- Sending the forward back to Mirko. Mirko doesn't need
  the PMC-facing email; if the Security team has follow-up
  for Mirko, that's a separate reply on Mirko's thread.
- Setting `Forwarded scan to PMC` before the user has
  actually clicked Send in Gmail. That cell tracks real
  delivery turnaround; pre-filling it pollutes the metric.
- A forward that doesn't include the §11a appendix
  (filtered list). The appendix is the audit trail; it's
  also how the next scan can re-use the filter rationale.

## Provenance

This SKILL completes the back half of the Glasswing pipeline.
The "slop-filter before forwarding" principle has been a
team norm since the program started; this SKILL codifies it.
The disposition labels are imported verbatim from
`threat-model-producer` §13, which makes the labels in
the forward directly cite-able back at the model that
licenses them.
