---
name: glasswing-scan-submit
description: Draft the scan-submission email to Mirko Svilus at Alpha-Omega (mirko@alpha-omega.dev) for a PMC whose pre-flight model verification has already passed. The email requests an actual Glasswing scan run, lists the repos to scan, links the verified threat model, and names the @apache.org-rooted PMC contacts who are committed to triage the results. PMC name in the subject; CC security@apache.org + private@<pmc>.apache.org + the named contacts + the scan-result recipients. Output is a Gmail draft for human review — never sends directly. After the human sends from Gmail, hand off to glasswing-scan-update to set Date scan requested on the PMC's row. Use this whenever glasswing-model-verify has passed for a PMC and the next step is putting the project into Alpha-Omega's scan queue, or whenever Jarek says "submit X for scan" / "queue X with Mirko" / "request the scan for X".
---

# glasswing-scan-submit SKILL

The handoff step between the ASF Security team's pre-flight
work (verifying the model) and Alpha-Omega actually running
the scan. This SKILL drafts the email that puts a PMC into
Mirko's queue.

## When to invoke

- `glasswing-model-verify` has passed for a PMC and the
  `Security model verified` cell in the tracker is filled.
- Jarek says "submit X for scan" / "queue X with Mirko" /
  "request the scan for X" or anything similarly explicit.
- A PMC's `Security Model` cell is filled, discoverability is
  confirmed (in-repo `AGENTS.md` chain resolves, or the model
  is reachable per the verify SKILL's rubric), and the named
  triage contacts on the row are all `@apache.org` and on the
  PMC roster.

**Skip** when:
- Pre-flight hasn't run or didn't pass — point the user at
  `glasswing-model-verify` first; this SKILL is downstream of
  it.
- The PMC's row is missing primary/backup contacts or
  scan-result recipients — the email needs them to name who
  will act on the scan output, and we don't fabricate.

## Hard rules (do not skip)

1. **Pre-flight must be done.** If
   `Security model verified` is blank on the PMC's row in the
   tracker, refuse and point the user at
   `glasswing-model-verify`. This SKILL doesn't bypass the
   gate; it's the next step *after* the gate.

2. **Every named contact must be `@apache.org`-rooted and on
   the PMC roster.** Cross-check against the PMC sheet's
   `Contact Person` + `Backup contact` cells (which already
   carry `@apache.org` addresses per the scan-request
   verification gates) and against Apache Whimsy's roster page
   for the PMC. If a row has a placeholder like "JB" or a
   bare handle without a verifiable `@apache.org` address,
   surface it as a question — don't put unverifiable names
   into the email.

3. **Draft + confirm before creating the Gmail draft.** Same
   pattern as the other Glasswing SKILLs: render the full
   draft (To / CC / Subject / body), wait for explicit
   approval, then call
   `mcp__claude_ai_Gmail__create_draft`. Never call `send`
   directly — the user reviews in the Gmail UI once more and
   presses Send themselves.

4. **CC discipline.** The CC list must include:
   - `security@apache.org` (Foundation-level audit trail);
   - `private@<pmc>.apache.org` (PMC collective visibility);
   - the project's `security@<pmc>.apache.org` alias if one
     exists (look it up via
     <https://security.apache.org/projects/>);
   - the primary + backup PMC contacts (the named humans);
   - every `@apache.org` address listed in the original
     `[GLASSWING]` request as a scan-result recipient.

   These are the people who need to know the scan is queued
   and who are accountable for acting on the output. CCing
   them on the queue request keeps everyone synced.

5. **After the user sends, hand off to
   `glasswing-scan-update`** to write three cells on the
   PMC's row to the date the email went out (the date the
   user actually clicked Send in Gmail, not the date this
   SKILL drafted):

   - `Date scan requested` — the submission date.
   - `Repositories submitted` — the exact list of repo URLs
     included in the Mirko email body (which may be a subset
     of `Repositories requested` when only some repos passed
     pre-flight). Newline-separated, same format as
     `Repositories requested`.
   This SKILL does **not** populate `Mirko thread (ponymail)`
   itself — that cell only ever holds a direct thread
   permalink (`https://lists.apache.org/thread/<tid>`), which
   `glasswing-scan-run` resolves via ponymail-API search on
   the relevant `private@<pmc>.apache.org` list (the Mirko
   thread is CC'd there per CC rule 4 above; the
   `security@apache.org` list is blocked by the ponymail
   MCP's restricted-list policy, so the PMC's private list
   is the resolution path). The cell stays blank until that
   sync has run.

   This SKILL does not write to the spreadsheet directly; it
   produces the two values (`Date scan requested`,
   `Repositories submitted`) and hands off to the update
   SKILL.

6. **Glasswing name is allowed here** because every recipient
   is either inside the program's trust boundary (Mirko;
   `security@apache.org`) or on a private PMC list. The
   public-artefact name-discipline rule from
   `glasswing-model-verify` (rule 8) does not apply to this
   email — Mirko *is* the program contact, naming it
   explicitly is precise communication, not a leak.

## Inputs the SKILL needs before drafting

| Input | Source |
| --- | --- |
| PMC name and slug | From the request, or the user supplies it |
| Repos to submit | The subset of `Repositories requested` that passed pre-flight (per the `Initial Model assessment` cell + the per-repo verification done by `glasswing-model-verify`). If pre-flight passed for *all* repos in `Repositories requested`, the submit list equals that cell verbatim. If pre-flight passed for only some, submit only those — the rest land in a later batch once their discoverability is fixed. **Always show the per-repo verdict explicitly when drafting** so the user can see why some repos are in this batch and others aren't. |
| Threat-model URL | From the PMC sheet's `Security Model` column + the verify SKILL's notes; if the model is on a project site, that URL |
| Discoverability PR URL (if applicable) | From the PMC sheet's `PR/Issues` column |
| Primary + backup PMC contacts | From the PMC sheet's `Contact Person` + `Backup contact` cells (already `@apache.org` per scan-request verification) |
| Scan-result recipients | From the original `[GLASSWING]` request body (the list of `@apache.org` addresses the PMC asked us to send results to) |
| `Security model verified` date | From the PMC sheet — confirms gate 1 of this SKILL |

If any of these are missing or ambiguous, surface as a
question to the user before drafting.

## Email template

**To**: `mirko@alpha-omega.dev`

**CC**: `security@apache.org`, `private@<pmc>.apache.org`,
[`security@<pmc>.apache.org` if it exists], primary contact,
backup contact, each `@apache.org` address from the original
request's "send results to" list.

**Subject**: `[GLASSWING] Scan request for Apache <PMC name>`

(The `Apache <PMC name>` form is the canonical PMC title —
"Apache Logging Services", "Apache Tomcat", "Apache Shiro" —
not the slug.)

**Body**:

```text
Hi Mirko,

Requesting a Glasswing scan for Apache <PMC name>. The
project has gone through the ASF Security team's pre-flight
checks; the details below.

PMC: Apache <PMC name>

Repos to scan:
  - <repo URL 1>
  - <repo URL 2>
  - ...

Pre-flight (per the Security team's glasswing-model-verify
SKILL):
  - Discoverability: PASS. <one-line description — e.g.
    "AGENTS.md in apache/logging-log4j2 points the scan agent
    at the threat model + VDR + FAQ" / "AGENTS.md +
    SECURITY.md added in apache/<repo>#NN, currently open and
    expected to merge before scan run">
  - Threat model: <URL of the model>
  - Completeness (minimum-bar rubric in apache/security's
    threat-model-producer SKILL): <PASS / PASS-with-soft-gaps
    — one sentence about what gaps if any remain. If gaps:
    note that they are advisory only, not blockers, and that
    the PMC has been informed (link the email thread / private
    list reference if relevant).>

PMC contacts committed to triage results:
  - Primary: <Full Name> <handle@apache.org>
  - Backup:  <Full Name> <handle@apache.org>

Scan results to be forwarded to:
  - <addr 1@apache.org>
  - <addr 2@apache.org>
  - ...

Standard handling on our side: results come to the ASF
Security team first for a slop-filter pass, then we forward
to the PMC contacts above for triage through their normal
process (private@<pmc>.apache.org -> CVE / coordinated
disclosure / release flow).

Please confirm receipt and let us know rough queue position
when you can. No timeline pressure from our side; just want
to make sure the request landed.

Thanks,
<sign-off in the human's voice>
```

The email is from the ASF Security team's voice, signed by
the human (Jarek or another team member). Plain text; no
marketing flourish; section lengths proportional to what
actually applies to that PMC.

## Procedure

1. **Confirm pre-flight passed.** Read the PMC's row in the
   tracker via `glasswing-scan-status` (or directly via the
   Drive MCP). Verify:
   - `Repositories requested` is non-empty (scope was confirmed by the
     PMC via `glasswing-scan-response` gate 4);
   - `Security model verified` is non-empty;
   - `Security Model` is non-empty;
   - `Contact Person` and `Backup contact` are non-empty and
     `@apache.org`-rooted.

   If any is missing, surface the gap and stop. Do not draft
   the email against half-verified inputs. In particular, do
   not "fill in" a missing `Repositories requested` cell yourself —
   scope confirmation is the PMC's call, not the agent's.

2. **Gather the rest of the inputs** from:
   - the PMC sheet's `Repositories requested` cell (the confirmed scope;
     parse newline-separated URLs);
   - the original `[GLASSWING]` thread (for the scan-result
     recipient list — that's the list the PMC supplied in
     their formal request);
   - the `PR/Issues` cell (for any discoverability PR URL to
     reference).

3. **Look up the per-PMC `security@<pmc>` alias** at
   <https://security.apache.org/projects/> (or the source-of-
   truth JSON at
   <https://github.com/apache/security-site/blob/main/scripts/project-coordinates.json>).
   If the alias exists, add it to the CC list.

4. **Render the draft** (To / CC / Subject / Body) into a
   readable preview for the user. Cite which row in the
   tracker is sourcing each input ("Repos from the
   Repositories sheet; result recipients from the original
   request thread on YYYY-MM-DD"). The user verifies the
   inputs as well as the prose.

5. **Wait for explicit approval.** "ok" / "send it" / "go" /
   similar. If the user wants edits, revise and re-render
   before re-asking. Substantive rewrites need fresh approval
   — the prior "ok" only covered the prior text.

6. **Create the Gmail draft** via
   `mcp__claude_ai_Gmail__create_draft`. Pass:
   - `to`: `["mirko@alpha-omega.dev"]`
   - `cc`: the full CC list as a list of strings
   - `subject`: the rendered subject
   - `body`: the rendered body
   - `replyToMessageId`: **omit** — this is a new thread to
     Mirko, not a reply to the PMC's request thread. Mirko's
     queue should track each scan request as its own thread.

7. **Hand off to `glasswing-scan-update`.** Surface the line:

   > Drafted in Gmail (draft id `<id>`). After you send,
   > flip `Date scan requested` on the `<slug>` row to the
   > send date via `glasswing-scan-update`.

   Do not invoke the update SKILL yourself; the user runs it
   once they've actually sent the email.

## Style notes

- **One PMC per email.** Don't batch multiple PMCs into one
  request. Each scan goes through its own thread with Mirko
  so the conversation about results, queue position, and
  follow-ups stays clean.
- **No marketing.** The audience is Alpha-Omega program
  staff; they don't need "cutting-edge" or "next-generation"
  framing. Plain operational request.
- **Be specific about the model.** Link the model URL
  exactly; if the discoverability fix is still in a pending
  PR, say so explicitly. Mirko's team needs to know whether
  the scan agent will find the model when it runs, or whether
  they should wait for the PR to land first.
- **Don't promise PMC-side response times.** "PMC contacts
  will triage" is a *commitment to attempt* — not a
  service-level guarantee. Phrase carefully.
- **Sign in the human's voice, not the agent's.** This SKILL
  drafts; the human signs. Leave a `<sign-off>` placeholder
  rather than baking a specific signature into the draft.

## Examples of bad submissions (avoid)

- Submitting a PMC whose `Security model verified` cell is
  blank. Violates hard rule 1; the gate exists precisely so
  that scans don't run against undermodeled projects.
- CC list missing `security@apache.org` or
  `private@<pmc>.apache.org`. The Foundation-level audit
  trail and the PMC's collective security visibility are both
  non-negotiable.
- Listing the PMC contacts but not the scan-result
  recipients — Mirko needs to know who results are
  ultimately for, not just who's authorized.
- Glossing over a partial-completeness pass. If
  `glasswing-model-verify` flagged soft gaps that the PMC
  accepted, say so in the body ("§7 / §11a / §13 gaps
  recorded as advisory; PMC informed in <thread>; scan
  proceeds against the existing model"). Hidden caveats land
  badly when Mirko's team triages results later.
- Mass-CCing the entire `private@<pmc>` list AND the
  individual PMC members already named as contacts. The list
  fans out anyway; double-CC creates duplicate inboxes and
  signals carelessness.

## Provenance

This SKILL captures the handoff step between the ASF Security
team's pre-flight (which lives in `glasswing-model-verify`)
and Alpha-Omega's actual scan execution. The
`mirko@alpha-omega.dev` recipient and the program contact
shape come from Mirko's introduction in the original
Alpha-Omega coordination thread (the
`Alpha-Omega / Glasswing: Delays in Enrollment` thread on
2026-04-22 and follow-ups). The Glasswing program is run as
an Alpha-Omega / OpenAI partnership; Mirko coordinates the
ASF side of the queue.
