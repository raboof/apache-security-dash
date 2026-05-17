---
name: glasswing-scan-submit
description: Draft the two-email submission flow for putting a PMC's scan into Alpha-Omega's queue. Email 1 goes to Mirko Svilus (mirko@alpha-omega.dev) with only security@apache.org on CC — no PMC people, no private@<pmc>, no security@<pmc> — and includes any `Expedite Claude OSS Requests` addresses the PMC asked us to forward to Anthropic's OSS-subscription team. Email 2 is a separate PMC notification ("scan has been requested with the vendor; results will be forwarded after the team's pre-triage pass") sent to the PMC contacts + private@<pmc>. The SKILL only fires on **explicit operator instruction** ("submit X for scan" / "queue X with Mirko" / "OK send the request to Mirko") — never automatically on pre-flight pass. Output is two Gmail drafts for human review — never sends directly. After the human sends Email 1, hand off to glasswing-scan-update to set Date scan requested + Repositories submitted on the PMC's row.
---

# glasswing-scan-submit SKILL

The handoff step between the ASF Security team's pre-flight
work (verifying the model) and Alpha-Omega actually running
the scan. This SKILL drafts the two emails that put a PMC
into Mirko's queue.

The submission is a **two-email flow**:

1. **Email 1 — Mirko request.** To `mirko@alpha-omega.dev`,
   CC only `security@apache.org`. Lists repos to scan, links
   the verified threat model, and (if the PMC has nominated
   any expedite addresses) asks Mirko to forward an Anthropic
   Claude-for-OSS expedite request for those addresses.
   **PMC people are NOT on this email** — it goes vendor-side
   only.

2. **Email 2 — PMC notification.** Separate email to the
   PMC's primary contact, CC'd to the backup contacts +
   `private@<pmc>.apache.org` + `security@<pmc>.apache.org`
   (if it exists) + `security@apache.org`. Tells the PMC the
   scan has been queued + summarises what happens next +
   acknowledges the expedite request if one was sent.

This shape (vendor-side and PMC-side as separate threads)
came in 2026-05-17 to keep PMC names + the PMC private
list off vendor-side traffic and to give the PMC a clean
notification thread of their own.

## When to invoke

**Hard precondition: explicit operator instruction.** This
SKILL fires only when Jarek (or another Security-team
member) says something like:

- "submit X for scan"
- "queue X with Mirko"
- "OK send the request to Mirko"
- "request the scan for X"

Pre-flight passing is **not** a trigger by itself. When
`glasswing-model-verify` passes for a PMC, the next step is
**not** this SKILL — it's `glasswing-scan-response`'s
"options" template (the OSS-expedite pitch + ready-to-scan
notification), which goes to the PMC and asks them what
they'd like to do next. This SKILL fires only after the
operator decides to actually queue the scan with Mirko.

**Skip** when:
- Pre-flight hasn't run or didn't pass — point the user at
  `glasswing-model-verify` first; this SKILL is downstream
  of it.
- The PMC's row is missing primary/backup contacts or
  scan-result recipients — the PMC-notification email needs
  them, and we don't fabricate.
- The operator hasn't explicitly said "submit". Pre-flight
  pass alone is not enough — surface the PMC as
  `pre-flight-passed-awaiting-operator-decision` and stop.

## Hard rules (do not skip)

1. **Pre-flight must be done.** If
   `Security model verified` is blank on the PMC's row in the
   tracker, refuse and point the user at
   `glasswing-model-verify`. This SKILL doesn't bypass the
   gate; it's the next step *after* the gate.

2. **Explicit operator instruction is required.** Pre-flight
   passing does not auto-trigger this SKILL. The operator
   must say "submit" / "queue" / "send to Mirko" or similar
   for a specific named PMC. Surface PMCs in
   `pre-flight-passed-awaiting-operator-decision` state from
   `glasswing-scan-run`'s sweep; never fire on those
   automatically.

3. **Every named contact on the PMC notification must be
   `@apache.org`-rooted and on the PMC roster.** Cross-check
   against the PMC sheet's `Contact Person` + `Backup
   contact` cells (which already carry `@apache.org`
   addresses per the scan-request verification gates) and
   against Apache Whimsy's roster page for the PMC. If a row
   has a placeholder like "JB" or a bare handle without a
   verifiable `@apache.org` address, surface it as a
   question — don't put unverifiable names into the email.

4. **Draft + confirm before creating Gmail drafts.** Same
   pattern as the other Glasswing SKILLs: render both drafts
   (Email 1 Mirko, Email 2 PMC notification — To / CC /
   Subject / Body), wait for explicit approval on each, then
   call `mcp__claude_ai_Gmail__create_draft` twice. Never
   call `send` directly — the user reviews in the Gmail UI
   once more and presses Send themselves.

5. **CC discipline — Email 1 (Mirko).** The CC list is
   **exactly**:

   - `security@apache.org`

   No PMC people, no `private@<pmc>.apache.org`, no
   `security@<pmc>.apache.org` alias, no scan-result
   recipients. Email 1 is vendor-side traffic; PMC contacts
   are kept off it. The rationale is twofold: (a) it limits
   the information disclosed to the vendor about who's in
   the loop on PMC's side; (b) it avoids spamming the PMC
   private list with vendor-coordination back-and-forth.

   **Consequence**: the `Mirko thread (ponymail)` column on
   the PMC's row will stay blank for submissions made after
   2026-05-17 (the ponymail MCP blocks `security@apache.org`
   per the restricted-list policy, and no other public ASF
   list will see this thread). The audit trail lives in
   Jarek's Gmail Sent folder + the Sent record on
   `security@apache.org`. This is intentional, not a bug.

6. **CC discipline — Email 2 (PMC notification).** The CC
   list includes:

   - `security@apache.org` (Foundation-level audit trail);
   - `private@<pmc>.apache.org` (PMC collective
     visibility);
   - the project's `security@<pmc>.apache.org` alias if one
     exists (look it up via
     <https://security.apache.org/projects/>);
   - the backup PMC contact (the primary is on the To: line);
   - every `@apache.org` address listed in the original
     `[GLASSWING]` request as a scan-result recipient.

   These are the people who need to know the scan has been
   queued and who will receive the eventual forwarded
   results. Email 2 is the PMC's official notification
   thread; the Mirko thread is internal vendor coordination.

7. **Expedite request handling.** If the PMC has nominated
   one or more `@apache.org` addresses in the new
   `Expedite Claude OSS Requests` column on their row, Email
   1 (Mirko) includes an additional block asking Mirko to
   forward an expedite request to Anthropic's
   Claude-for-Open-Source subscription team for those
   addresses. If the column is empty, the expedite block is
   omitted entirely from Email 1. Either way, Email 2 (PMC
   notification) mentions whether an expedite ask was sent.

8. **After the user sends Email 1, hand off to
   `glasswing-scan-update`** to write two cells on the PMC's
   row to the date the email went out (the date the user
   actually clicked Send in Gmail, not the date this SKILL
   drafted):

   - `Date scan requested` — the submission date.
   - `Repositories submitted` — the exact list of repo URLs
     included in the Mirko email body (which may be a
     subset of `Repositories requested` when only some
     repos passed pre-flight). Newline-separated, same
     format as `Repositories requested`.

   This SKILL does **not** populate `Mirko thread
   (ponymail)` — per CC rule 5, that cell stays blank for
   submissions made after 2026-05-17.

   This SKILL does not write to the spreadsheet directly;
   it produces the two values (`Date scan requested`,
   `Repositories submitted`) and hands off to the update
   SKILL.

9. **Glasswing name is allowed here** because every
   recipient on either email is either inside the program's
   trust boundary (Mirko; `security@apache.org`) or on a
   private PMC list. The public-artefact name-discipline
   rule from `glasswing-model-verify` (rule 8) does not
   apply to these emails — Mirko *is* the program contact,
   naming it explicitly is precise communication, not a
   leak.

## Inputs the SKILL needs before drafting

| Input | Source |
| --- | --- |
| Explicit operator instruction | Conversation (no inference from sheet state alone) |
| PMC name and slug | From the request, or the user supplies it |
| Repos to submit | The subset of `Repositories requested` that passed pre-flight (per the `Initial Model assessment` cell + the per-repo verification done by `glasswing-model-verify`). If pre-flight passed for *all* repos in `Repositories requested`, the submit list equals that cell verbatim. If pre-flight passed for only some, submit only those — the rest land in a later batch once their discoverability is fixed. **Always show the per-repo verdict explicitly when drafting** so the user can see why some repos are in this batch and others aren't. |
| Threat-model URL | From the PMC sheet's `Security Model` column + the verify SKILL's notes; if the model is on a project site, that URL |
| Discoverability PR URL (if applicable) | From the PMC sheet's `PR/Issues` column |
| Primary + backup PMC contacts | From the PMC sheet's `Contact Person` + `Backup contact` cells (already `@apache.org` per scan-request verification) — for Email 2 |
| Scan-result recipients | From the original `[GLASSWING]` request body (the list of `@apache.org` addresses the PMC asked us to send results to) — for Email 2 |
| Expedite addresses | From the PMC sheet's `Expedite Claude OSS Requests` column. May be empty (PMC didn't request expedite) — in which case Email 1 omits the expedite block. |
| `Security model verified` date | From the PMC sheet — confirms gate 1 of this SKILL |

If any of these are missing or ambiguous, surface as a
question to the user before drafting.

## Email 1 template — Mirko request

**To**: `mirko@alpha-omega.dev`

**CC**: `security@apache.org` *(exactly this list, no PMC
recipients per hard rule 5)*

**Subject**: `[GLASSWING] Scan request for Apache <PMC name>`

(The `Apache <PMC name>` form is the canonical PMC title —
"Apache Logging Services", "Apache Tomcat", "Apache Shiro" —
not the slug.)

**Body**:

```text
Hi Mirko,

Requesting a Glasswing scan for Apache <PMC name>. The
project has gone through the ASF Security team's pre-flight
checks; details below.

PMC: Apache <PMC name>

Repos to scan:
  - <repo URL 1>
  - <repo URL 2>
  - ...

Pre-flight (per the Security team's glasswing-model-verify
SKILL):
  - Discoverability: PASS. <one-line description — e.g.
    "AGENTS.md in apache/logging-log4j2 points the scan
    agent at the threat model + VDR + FAQ" / "AGENTS.md +
    SECURITY.md added in apache/<repo>#NN, currently open
    and expected to merge before scan run">
  - Threat model: <URL of the model>
  - Completeness (minimum-bar rubric in apache/security's
    threat-model-producer SKILL): <PASS / PASS-with-soft-
    gaps — one sentence about what gaps if any remain. If
    gaps: note that they are advisory only, not blockers,
    and that the PMC has been informed.>

<IF the `Expedite Claude OSS Requests` cell is non-empty,
include this block; otherwise omit it entirely>
Expedite request — Anthropic Claude-for-OSS subscription:
The <PMC name> PMC has nominated the following @apache.org
addresses as committed scan-result triagers. Could you
forward an expedite request to Anthropic's
Claude-for-Open-Source subscription team
(https://claude.com/contact-sales/claude-for-oss) for these
addresses? They'll be registering via the form directly;
the expedite ask is the courtesy on top. No promises
needed — just the relay.

  - <addr1@apache.org>
  - <addr2@apache.org>
  - ...

</block>

Standard handling on our side: results come to the ASF
Security team first (security@apache.org) for a slop-
filter / pre-triage pass, then we forward to the PMC's
named contacts via a separate thread.

Please confirm receipt and let us know rough queue
position when you can. No timeline pressure from our side;
just want to make sure the request landed.

Thanks,
<sign-off in the human's voice>
```

The email is from the ASF Security team's voice, signed by
the human (Jarek or another team member). Plain text; no
marketing flourish; section lengths proportional to what
actually applies to that PMC. **No PMC contact names** in
the Mirko email body — the PMC roster is communicated
separately on Email 2; vendor-side, Mirko just needs the
repos + the model URL + the (optional) expedite list.

## Email 2 template — PMC notification

**To**: primary PMC contact (the `Contact Person` cell's
`@apache.org` address)

**CC**: backup PMC contact(s) (from `Backup contact`),
`private@<pmc>.apache.org`,
`security@<pmc>.apache.org` *(if exists)*,
`security@apache.org`,
every `@apache.org` address from the original `[GLASSWING]`
request's "send results to" list.

**Subject**: `[GLASSWING] Apache <PMC name> — scan request submitted to vendor`

(Distinct subject from Email 1; this is the PMC's
notification thread, not a forward of the vendor thread.)

**Body**:

```text
Hi <Primary contact first name>,

The scan request for Apache <PMC name> has been submitted
to Mirko Svilus at Alpha-Omega (the Glasswing pipeline).
The vendor's queue position is TBD — usually a few days to
a couple of weeks, with no commitment.

Repos submitted (current HEAD at submission time):
  - <repo URL 1>
  - <repo URL 2>
  - ...

What happens next:
  - Mirko's team runs the scan against each repo.
  - Scan results come back to the ASF Security team first
    at security@apache.org.
  - We do a slop-filter / pre-triage pass to remove
    obvious false positives.
  - We forward the curated results to your PMC's named
    contacts via a separate thread — typically a markdown
    file per repo with findings grouped by component,
    referencing the threat model for each disposition.

You don't need to do anything until the results arrive.

<IF the `Expedite Claude OSS Requests` cell was non-empty,
include this block; otherwise omit>
Expedite request:
We also asked Mirko to forward an Anthropic
Claude-for-Open-Source expedite request for the <N>
@apache.org address(es) you nominated:

  - <addr1@apache.org>
  - <addr2@apache.org>
  - ...

No promises from us or from Anthropic — just the relay.
PMC members should still register at
https://claude.com/contact-sales/claude-for-oss with their
@apache.org address; the expedite ask is the courtesy on
top.

</block>

Best,
<sign-off>
```

## Procedure

1. **Confirm explicit operator instruction.** This SKILL
   does not fire on pre-flight pass alone. If the operator
   hasn't named the PMC + said "submit" / "queue" / "send
   to Mirko" or similar, refuse and surface the PMC as
   `pre-flight-passed-awaiting-operator-decision` instead.

2. **Confirm pre-flight passed.** Read the PMC's row in the
   tracker via `glasswing-scan-status` (or directly via the
   Sheets API per the truncation caveat in
   `glasswing-scan-run` Step 2). Verify:
   - `Repositories requested` is non-empty (scope was
     confirmed by the PMC via `glasswing-scan-response`
     gate 4);
   - `Security model verified` is non-empty;
   - `Security Model` is non-empty;
   - `Contact Person` and `Backup contact` are non-empty and
     `@apache.org`-rooted.

   If any is missing, surface the gap and stop. Do not
   draft against half-verified inputs. In particular, do
   not "fill in" a missing `Repositories requested` cell
   yourself — scope confirmation is the PMC's call, not
   the agent's.

3. **Gather the rest of the inputs** from:
   - the PMC sheet's `Repositories requested` cell (the
     confirmed scope; parse newline-separated URLs);
   - the original `[GLASSWING]` thread (for the
     scan-result recipient list — that's the list the PMC
     supplied in their formal request — used in Email 2's
     CC);
   - the `PR/Issues` cell (for any discoverability PR URL
     to reference);
   - the new `Expedite Claude OSS Requests` cell (parse
     newline-separated `@apache.org` addresses; empty cell
     = no expedite block on either email).

4. **Look up the per-PMC `security@<pmc>` alias** at
   <https://security.apache.org/projects/> (or the
   source-of-truth JSON at
   <https://github.com/apache/security-site/blob/main/scripts/project-coordinates.json>).
   If the alias exists, add it to **Email 2's** CC list
   (not Email 1's — Email 1 is Mirko + security@apache.org
   only).

5. **Render Email 1 (Mirko) draft.** Show To / CC / Subject
   / Body. Cite the inputs ("Repos from the
   `Repositories requested` cell; expedite addresses from
   the `Expedite Claude OSS Requests` cell"). User
   verifies inputs as well as prose.

6. **Wait for explicit approval on Email 1.** "ok" / "send
   it" / "go" / similar. If the user wants edits, revise
   and re-render before re-asking. Substantive rewrites
   need fresh approval.

7. **Render Email 2 (PMC notification) draft.** Show To /
   CC / Subject / Body. Cite inputs same way.

8. **Wait for explicit approval on Email 2.**

9. **Create both Gmail drafts** via
   `mcp__claude_ai_Gmail__create_draft` (two calls). For
   each draft, pass:
   - `to`: the recipient(s) as a list of strings
   - `cc`: the CC list as a list of strings
   - `subject`: the rendered subject
   - `body`: the rendered body
   - `replyToMessageId`: **omit** for both — both are new
     threads. Mirko's queue should track each scan request
     as its own thread; the PMC notification is a fresh
     thread distinct from the original `[GLASSWING]`
     request thread.

10. **Hand off to `glasswing-scan-update`.** Surface the
    line:

    > Drafted in Gmail: Email 1 (Mirko) draft id `<id1>`,
    > Email 2 (PMC notification) draft id `<id2>`. After
    > you send Email 1, flip `Date scan requested` +
    > `Repositories submitted` on the `<slug>` row to the
    > send date / repos via `glasswing-scan-update`.

    Do not invoke the update SKILL yourself; the user runs
    it once they've actually sent the emails.

## Style notes

- **One PMC per submission.** Don't batch multiple PMCs
  into one Mirko request. Each scan goes through its own
  thread with Mirko so the conversation about results,
  queue position, and follow-ups stays clean.
- **No marketing.** The audience is Alpha-Omega program
  staff (Email 1) + Apache PMC members (Email 2); neither
  needs "cutting-edge" or "next-generation" framing.
- **Be specific about the model.** Link the model URL
  exactly; if the discoverability fix is still in a pending
  PR, say so explicitly. Mirko's team needs to know whether
  the scan agent will find the model when it runs, or
  whether they should wait for the PR to land first.
- **Don't promise PMC-side response times** in Email 2.
  "PMC contacts will triage" is a *commitment to attempt*
  — not a service-level guarantee.
- **Sign in the human's voice, not the agent's.** This
  SKILL drafts; the human signs. Leave a `<sign-off>`
  placeholder rather than baking a specific signature into
  the drafts.

## Examples of bad submissions (avoid)

- Drafting Email 1 (Mirko) with PMC people or
  `private@<pmc>` on CC. Violates hard rule 5; the whole
  point of the dual-email shape is to keep vendor and PMC
  threads separate.
- Submitting a PMC whose `Security model verified` cell is
  blank. Violates hard rule 1.
- Submitting on pre-flight pass alone, without explicit
  operator instruction. Violates hard rule 2.
- Forgetting Email 2 entirely. The PMC needs to know the
  scan has been queued; the Mirko thread doesn't reach
  them anymore under the new CC discipline.
- Including the expedite block on Email 1 when the
  `Expedite Claude OSS Requests` cell is empty. The block
  is conditional — empty cell = no block, no apologetic
  framing about "we don't have any expedite addresses".
- Glossing over a partial-completeness pass. If
  `glasswing-model-verify` flagged soft gaps that the PMC
  accepted, say so in Email 1's body ("§7 / §11a / §13
  gaps recorded as advisory; PMC informed in <thread>;
  scan proceeds against the existing model"). Hidden
  caveats land badly when Mirko's team triages results
  later.

## Provenance

This SKILL captures the handoff step between the ASF
Security team's pre-flight (which lives in
`glasswing-model-verify`) and Alpha-Omega's actual scan
execution. The `mirko@alpha-omega.dev` recipient and the
program contact shape come from Mirko's introduction in the
original Alpha-Omega coordination thread (the
`Alpha-Omega / Glasswing: Delays in Enrollment` thread on
2026-04-22 and follow-ups). The Glasswing program is run as
an Alpha-Omega / OpenAI partnership; Mirko coordinates the
ASF side of the queue.

The two-email shape + Mirko-only-CC discipline + the
expedite-request relay + the operator-gated trigger were
added 2026-05-17 to:

- Keep PMC identities off vendor-side traffic.
- Give the PMC a clean, separate notification thread.
- Open the alternative path of an Anthropic
  Claude-for-OSS subscription expedite — see
  `glasswing-scan-response`'s "OSS-expedite pitch"
  template for the conversation that collects the
  addresses.
- Stop auto-firing this SKILL on pre-flight pass; the
  operator owns the "do we send this to Mirko, or not"
  decision per PMC.
