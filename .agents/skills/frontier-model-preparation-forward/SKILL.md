---
name: frontier-model-preparation-forward
description: >-
  Forward an ASF Tooling scan result to the PMC by email, with the scan bundle (.zip) and the pre-forward assessment (.md) as ATTACHMENTS.
  Retrieves the scan from the `apache/tooling-agents-private` archive (`scans/mythos/...`) and its assessment (`pre-forward-results/mythos/...`),
  extracts the PMC + repo + date from the scan's `metadata.yml`,
  confirms the assessment's recommended sanity verdict is PASS,
  and drafts the forwarding email to the PMC's designated scan-result recipients (Cc Security + Tooling; Marketing & Publicity is named in the body as a consultation contact but is NOT Cc'd).
  The draft is created via the `forward-draft` tool (OAuth Gmail, plain-text body + attachments, no tracking) and left UNSENT for human review.
  After the human sends, hand off to `frontier-model-preparation-update` to set `Date scan received` and `Forwarded scan to PMC`.
  Use when an ASF Tooling scan (and its assessment) is in the archive and Jarek says "forward the X scan", "the X scan is back", or "send the X results".
---

# frontier-model-preparation-forward SKILL

The "results path" of the Frontier Model Preparation pipeline — the inverse of `frontier-model-preparation-submit`.
Where `submit` enrolls a request *with* ASF Tooling, this SKILL delivers the result *back* to the PMC:
retrieve the scan bundle and its assessment from the private archive, attach both to a PMC-facing email, and record the delivery in the tracker.

The PMC receives two attachments:

1. **The scan bundle**, zipped — the ASF Tooling scan output (`issues.md`, `metadata.yml`, and the rest of the bundle) from `apache/tooling-agents-private/scans/mythos/<project>/<scan-id>/`.
2. **The pre-forward assessment** (`.md`) — the team's read of the findings against the project's threat model, with likely dispositions, from `apache/tooling-agents-private/pre-forward-results/mythos/<project>/<scan-id>/assessment.md` (produced by [`asvs-scan-assess`](../../../.claude/skills/asvs-scan-assess/SKILL.md)).

The assessment is shared with the PMC as an **advisory guide** — the dispositions help the PMC triage quickly, but the PMC's own assessment is authoritative. The team does not decide findings on the PMC's behalf; it hands them the scan plus a starting-point read.

> **Policy note (2026-07-15):** the assessment used to be a strictly *internal* artefact (never forwarded). It is now **attached to the forward** as an advisory guide. `asvs-scan-assess` is updated to match; its dispositions are still the team's working read, not a ruling on the PMC's behalf.

## When to invoke

- An ASF Tooling scan **and** its assessment are in the `apache/tooling-agents-private` archive (`scans/mythos/...` + `pre-forward-results/mythos/...`), and the scan hasn't been forwarded yet.
- Jarek says "forward the <PMC> scan", "the <PMC> scan is back, send it", "send the <PMC> results".
- The Mythos tracker shows a PMC with `Date scan requested` filled but `Date scan received` / `Forwarded scan to PMC` blank, and the archive has the scan + assessment.

Skip when:
- The scan has **no assessment** in `pre-forward-results/mythos/...` yet — run [`asvs-scan-assess`](../../../.claude/skills/asvs-scan-assess/SKILL.md) first (the assessment is a required attachment).
- The assessment's recommended sanity verdict is `RETURNED` (a broken scan) — surface it and escalate to ASF Tooling rather than forwarding.
- The PMC's row indicates incomplete pre-flight (`Security model verified` blank) — should not happen; surface the gap.

## Hard rules (do not skip)

1. **Both artefacts come from the archive, and both are ATTACHED.** Retrieve the scan bundle from `scans/mythos/<project>/<scan-id>/` and the assessment from `pre-forward-results/mythos/<project>/<scan-id>/assessment.md` (against a clean local clone of `apache/tooling-agents-private`). Attach the scan as a single `.zip` (zip the scan-id directory) and the assessment as its `.md`. Do **not** paste findings into the email body — the full content rides in the attachments.

2. **Forward only on a passing assessment.** Read the assessment's `metadata.yml` `sanity_check` field (produced by `asvs-scan-assess`). Forward only when it is `PASS` or `PASS-with-notes`. If it is `RETURNED` (or the assessment is missing), stop: surface to the operator and escalate to ASF Tooling — do not forward a broken scan. The assessment IS the sanity gate; this SKILL does not re-run the full checklist, it confirms the recorded verdict.

3. **Extract identity from the scan, not from memory.** PMC slug, repo, branch, and scan date come from the scan bundle's `metadata.yml` (`project`, `repo`, `head_sha`, `scan_date`; branch defaults to the repo's default branch unless the scan pinned one). These drive the subject line and the tracker cells.

4. **Recipients — designated PMC recipients + Security + Tooling + Marketing/Publicity, all `@apache.org`-rooted.**
   - **To:** the PMC's designated scan-result recipients — the `@apache.org` addresses from the original `[GLASSWING]` request ("send results to …"), i.e. the people who were supposed to be informed.
   - **Cc:** `security@apache.org` and `private@tooling.apache.org` — **only these two.** Do **not** Cc `private@<pmc>.apache.org`, the `security@<pmc>` alias, the primary/backup contacts, or `markpub@apache.org`. The designated scan-result recipients on **To** are the PMC-side audience; the Cc is just the Security + Tooling audit trail. Widening to the whole `private@<pmc>` list would broaden the pre-disclosure scope beyond the named recipients; Marketing & Publicity is a body consultation contact, not a recipient of the findings.

   **Every** To/Cc address must end in `@apache.org` or `@<pmc>.apache.org`. Scan results are pre-disclosure vulnerability candidates; `@apache.org` rooting is the cheapest verification the recipient is still an ASF member entitled to see them. If the request's stated destination contains a non-`@apache.org` address, surface the conflict — do not silently substitute; a committer can forward their `@apache.org` address to a personal inbox on their side.

5. **Draft via the `forward-draft` tool — never the claude.ai Gmail connector.** The email has attachments and is PMC-facing (in the operator's name), so it must be plain-text with real links and no tracking. Use [`tools/forward_draft/`](../../../tools/forward_draft/) (`forward-draft create …`), which builds a `multipart/mixed` draft (plain-text body + the two attachments) via the OAuth Gmail API and leaves it **UNSENT**. Do **not** use `mcp__claude_ai_Gmail__create_draft` (it rewrites links / adds tracking and can't attach files). The operator reviews the draft in Gmail and presses Send.

6. **Draft + confirm before creating the draft.** Render the full plan — To / Cc / Subject / body / the two attachment paths + sizes / the assessment's headline (VALID count + sanity verdict) — and wait for explicit "yes" / "send" / "go" before running `forward-draft create` live. (`forward-draft create --dry-run` builds + validates without touching the network — use it in the plan.)

7. **After the operator sends, record it in the tracker — including the tooling-list ponymail permalink.** Hand off to `frontier-model-preparation-update` to write:
   - `Date scan received` — the scan bundle's commit date in the archive (when ASF Tooling delivered it — not today).
   - `Forwarded scan to PMC` — today's date (when the operator clicked Send).
   - the **tooling-list ponymail permalink** of the sent message — `private@tooling.apache.org` is Cc'd, so the forward lands in the ASF Tooling list archive; resolve its `https://lists.apache.org/thread/<tid>` permalink via ponymail (see procedure step 13). Record it in the results-thread ponymail cell (`Scan delivery thread (ponymail)` / `Notes` if no dedicated column exists).
   - the draft id + scan-id in `Notes` so the next sweep sees a complete record.

   This SKILL does not write to the spreadsheet directly.

   **Also record the per-scan status in the Scan Queue tab** via `sheets-writer scan-queue-set` for the scanned repo — the `Scan N` block: `When scanned` (the scan's `scan_date`), `Model send thread (ponymail)` (the forward's tooling-list permalink from step 12), `When report sent` (today), `Commit hash` (the scanned `head_sha`). These per-scan cells are carried over across `build-status-tab` refreshes keyed by (Repo, Branch/tag), so they persist.

   **Then refresh the derived tabs — MANDATORY, not optional.** Run `sheets-writer build-status-tab` so the PMC shows Delivered/forwarded-closed across the Status / Completed / Timeline / Program-totals / Model-Status tabs and the dashboard gist (it also carries over the Scan Queue per-scan cells just written). A forward is **not complete** until this refresh has run. Do it after **every** forward (i.e. after all reports in a batch are sent), every time.

8. **Ponymail must be authenticated to resolve the permalink.** Before the post-send permalink lookup, run `mcp__ponymail__auth_status`; if it reports "Not authenticated", `mcp__ponymail__login` first (the private `tooling` list is not readable anonymously). If ponymail can't be authenticated, don't block the forward — record the permalink as pending and surface a one-line note so a later sweep can fill it. (Note: the ponymail MCP blocks `security@apache.org` entirely, so resolve via the `private@tooling.apache.org` list, not the Security list.)

9. **Program-cost confidentiality + publicity guidance live in the template body.** The email must not disclose the program's cost mechanics (the $1M credit value, per-MTok pricing, seat/provisioning). ASF Tooling, the program name, Mythos / Mythos 5, Anthropic, and Claude are all nameable. The template also carries the **attribution + publicity** guidance (don't describe the program's capabilities/models/methods in advisories; the attribution wording; consult Marketing & Publicity) — keep those paragraphs verbatim.

## Inputs the SKILL needs

| Input | Source |
| --- | --- |
| Scan bundle | `apache/tooling-agents-private/scans/mythos/<project>/<scan-id>/` (zip the scan-id directory for the attachment) |
| Assessment `.md` + sanity verdict | `apache/tooling-agents-private/pre-forward-results/mythos/<project>/<scan-id>/assessment.md` (+ its `metadata.yml` `sanity_check`) |
| PMC slug / repo / branch / scan date | The scan bundle's `metadata.yml` (`project`, `repo`, `head_sha`, `scan_date`) |
| Designated scan-result recipients (the To: list) | The PMC row's `Report recipients` cell (falls back to the original `[GLASSWING]` request's "send results to …" list) |
| Primary + backup PMC contacts (for the `<NAMES HERE>` first-names in the body) | The PMC sheet's `Contact Person` + `Backup contact` |
| `Date scan requested` (pre-condition) | The PMC sheet — must be filled; `Date scan received` / `Forwarded scan to PMC` blank |

If the assessment is missing, its verdict is `RETURNED`, the recipient list is missing, or the scan `metadata.yml` is unreadable — stop and surface the gap.

## Attachment preparation

1. **Clone/refresh** `apache/tooling-agents-private` (clean tree; reaching the private repo over `gh`/git needs the keychain — bypass the sandbox with the loud banner per the user's rule).
2. **Zip the scan bundle**: `zip -r -j <scan-id>.zip scans/mythos/<project>/<scan-id>/` (or keep the directory structure with `-r` without `-j` — operator preference; default to a flat zip of the bundle files). Name the zip `<scan-id>.zip`. Write it under `$TMPDIR` (not the job tmp dir — Bash can't write there).
3. **Copy the assessment** `pre-forward-results/mythos/<project>/<scan-id>/assessment.md` to `$TMPDIR/pre-forward-assessment-<scan-id>.md` (the `pre-forward-assessment-` prefix names it clearly for the PMC and distinguishes it from the scan `.zip`).
4. Both files become `--attach` arguments to `forward-draft create`.

## Email template

**Subject**: `[GLASSWING] ASVS Tooling security scan results <PMC> <repository>/<branch> <YYYY-MM-DD>`
(e.g. `[GLASSWING] ASVS Tooling security scan results Apache APISIX apisix-ingress-controller/main 2026-07-15`)

**To**: the PMC's designated scan-result recipients (the `@apache.org` addresses from the request).

**Cc**: `security@apache.org`, `private@tooling.apache.org` — **only these two.** (Not `private@<pmc>`, the `security@<pmc>` alias, the primary/backup contacts, or `markpub@apache.org`.)

**Attachments**: `<scan-id>.zip` (the scan bundle) and `pre-forward-assessment-<scan-id>.md` (the assessment).

**Body** (plain text — `<NAMES HERE>` are the To: recipients' first names; adjust the sign-off if a different operator sends):

```text
Hello <NAMES HERE>,

Attached is the security scan with ASVS using Glasswing Mythos5 - the tooling
team ran it as part of our scanning effort. It's been re-validated with
adversarial review against the security threat/model you have - and the
assessment with likely dispositions are also attached.

The report includes a list of vulnerabilities with severity: we recommend that
you look at all of them to determine if those are actual vulnerabilities, a
hardening fix to be treated as a normal issue, or a false positive to be
ignored. The automated dispositions might guide you with that, but your
assessment is what counts - the dispositions should help you to do it quickly.

The VALID issues are the ones you should pay special attention to - but we
encourage you to take a look at all - even hardening opportunities - if you
have time.

Since this is the first time ASF runs such scans, we need your help - please
provide feedback on the results received.

We also ask that you not describe the program's capabilities, models, or
methods in greater detail in advisories.

Attribution advisories should read:

"[Apache <project> researcher or team] in collaboration with Claude and
Anthropic Research"

Consult with Marketing & Publicity about any other public statements. We may
provide additional guidance in the future.

Best,

Jarek

Contacts:

Security: security@apache.org
Tooling: private@tooling.apache.org
Marketing and Publicity: markpub@apache.org
```

Plain text; no marketing flourish; links verbatim (no tracking). The findings and dispositions are in the attachments — do not inline them in the body.

## Procedure

1. **Identify the scan.** From Jarek's instruction (a project name) or a new bundle in `scans/mythos/`. Resolve to the `<project>/<scan-id>` directory. If ambiguous, list candidates and ask.

2. **Refresh the archive locally** (`git pull` on a clean clone of `apache/tooling-agents-private`; sandbox-bypass for the private-repo fetch, loud banner).

3. **Read the scan `metadata.yml`** — extract `project` (PMC slug), `repo`, `head_sha`, `scan_date`, and the branch (default branch unless pinned). These build the subject line and the tracker dates.

4. **Confirm the assessment + its verdict.** Read `pre-forward-results/mythos/<project>/<scan-id>/metadata.yml`. If it's absent, stop and route to `asvs-scan-assess`. If `sanity_check` is `RETURNED`, stop and escalate to ASF Tooling. Note the assessment's headline (VALID count) for the plan. Proceed only on `PASS` / `PASS-with-notes`.

5. **Pull the PMC's row** from the Mythos tracker (via the `frontier-model-preparation-status` flow or a direct Sheets read). Confirm `Scan Requested = Yes`, `Repositories submitted` non-empty, `Date scan requested` filled, `Date scan received` + `Forwarded scan to PMC` blank. Refuse on any wrong pre-condition.

6. **Assemble recipients** (hard rule 4). To: the designated scan-result recipients (the PMC row's `Report recipients` / the `[GLASSWING]` request). Cc: `security@apache.org` + `private@tooling.apache.org` **only** (not `private@<pmc>`, the alias, contacts, or `markpub`). Verify every address is `@apache.org`-rooted; surface any that isn't.

7. **Prepare the attachments** (see "Attachment preparation"): zip the scan bundle and copy the assessment `.md` into `$TMPDIR`.

8. **Write the body** from the template (fill `<NAMES HERE>`, `<project>`; keep the attribution + publicity paragraphs verbatim) to a plain-text file in `$TMPDIR`.

9. **Render the plan + dry-run.** Show To / Cc / Subject / body / the two attachment paths + sizes / the assessment headline (VALID count + sanity verdict). Run `forward-draft create … --dry-run` to validate (attachments exist, no inline HTML, sizes). Show the operator.

10. **Wait for explicit approval** ("yes" / "send" / "go").

11. **Create the draft** with `forward-draft create` (live — same args, without `--dry-run`). It builds the `multipart/mixed` draft (plain-text body + `.zip` + `.md`) via the OAuth Gmail API and prints the draft's Gmail URL. The draft is **UNSENT** — the operator reviews it in Gmail (including that both attachments are present) and presses Send.

12. **Resolve the tooling-list ponymail permalink** (after the operator confirms they've sent). Ensure ponymail is authenticated (`mcp__ponymail__auth_status`; `mcp__ponymail__login` if not). Then `mcp__ponymail__search_list` with `list=private`, `domain=tooling.apache.org`, and the forward's subject (`[GLASSWING] ASVS Tooling security scan results …`), matching the message the operator just sent (the newest thread whose subject matches, from the operator's `@apache.org` address). Take its `tid` and build `https://lists.apache.org/thread/<tid>`. The archive may take a minute or two to index the message — if it isn't there yet, note the permalink as pending rather than blocking. Do this via the `private@tooling.apache.org` list (the Cc'd Tooling list), never `security@apache.org` (ponymail blocks it).

13. **Hand off to `frontier-model-preparation-update`** (hard rules 7 + 8) once the operator confirms they've sent: set `Date scan received` (archive commit date) + `Forwarded scan to PMC` (today) + the tooling-list ponymail permalink (from step 12) + the draft id / scan-id in `Notes`. Do not set `Forwarded scan to PMC` before the operator has actually sent.

14. **Record the per-scan status in the Scan Queue tab** (hard rule 7). Run `sheets-writer scan-queue-set` for the scanned repo and its `Scan N` block (Scan 1 for a first scan):

    ```bash
    uv run --project tools/sheets_writer sheets-writer scan-queue-set \
      --spreadsheet-id <id> \
      --repo <repo URL, exactly as in the Scan Queue 'Repo' column> \
      --branch <ref, or omit for the default-branch row> \
      --scan 1 \
      --when-scanned <scan_date> \
      --model-thread <tooling-list ponymail permalink from step 12> \
      --when-report-sent <today> \
      --commit <head_sha>
    ```

    (`--dry-run` first to confirm it targets the right row/cells.) A repo with a branch-scoped scan uses that `--branch`; a multi-repo PMC runs this once per scanned repo.

15. **Refresh the derived tabs — MANDATORY closing step (hard rule 7).** Run `sheets-writer build-status-tab` so the PMC shows Delivered/forwarded-closed across the Status / Completed / Timeline / Program-totals / Model-Status tabs and the dashboard gist (it carries over the Scan Queue per-scan cells from step 14). The forward is not complete until this has run — do it after every forward (after all reports in a batch are sent), every time. This is not optional.

## Style notes

- **The body is the template; the substance is the attachments.** Don't summarise findings in the body, don't paste dispositions inline — the PMC opens the `.zip` and the `.md`.
- **Keep the attribution + publicity paragraphs verbatim.** They are program guidance, not prose to trim.
- **One PMC per forward.** Don't batch; don't Cc another PMC's `private@` list. A scan covering multiple repos of the same PMC is still one PMC forward (attach the relevant bundle(s)).
- **`@apache.org` rooting is non-negotiable** on To and Cc (hard rule 4).
- **Sign in the operator's voice.** The template signs "Jarek"; if a different Security-team member sends, adjust the sign-off before drafting.
- **The draft is UNSENT.** `forward-draft` never sends; the human presses Send after reviewing the attachments in Gmail.

## Examples of bad forwards (avoid)

- Forwarding without the assessment attached, or before `asvs-scan-assess` has produced it — the assessment is a required attachment and the sanity gate.
- Forwarding a scan whose assessment verdict is `RETURNED` — that's a broken scan; escalate to ASF Tooling.
- Pasting the findings / dispositions into the email body instead of attaching them.
- Using `mcp__claude_ai_Gmail__create_draft` — it can't attach files and adds tracking. Use `forward-draft`.
- Dropping `security@apache.org` or `private@tooling.apache.org` from the Cc, or **Cc'ing anything else** — `private@<pmc>` / the whole PMC list / the `security@<pmc>` alias / `markpub@apache.org` / the contacts (widens the pre-disclosure scope past the named To recipients), or using a non-`@apache.org` recipient.
- Setting `Forwarded scan to PMC` before the operator has actually clicked Send.
- Naming the program's cost mechanics ($1M value, per-MTok pricing, seat/provisioning) in the body.

## Provenance

This SKILL completes the back half of the Frontier Model Preparation pipeline.
Two shifts landed 2026-07-15 when the program moved in-house to ASF Tooling:
(1) the scan and its assessment are retrieved from the `apache/tooling-agents-private` archive and delivered as **attachments** (scan `.zip` + assessment `.md`) rather than pasted verbatim into the email body;
(2) the pre-forward **assessment is now shared** with the PMC as an advisory guide (previously internal-only) — the PMC still owns the authoritative disposition call.
The forwarding email is drafted via the `forward-draft` OAuth helper (plain-text body + attachments, no tracking), never the claude.ai Gmail connector.
