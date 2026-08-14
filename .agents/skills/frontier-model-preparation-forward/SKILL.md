---
name: frontier-model-preparation-forward
description: >-
  Close out a Glasswing scan delivery: clear it for release, then record it once ASF Tooling has sent it to the PMC.
  ASF Tooling now sends the PMC email itself, from `vp-tooling@apache.org`, per `docs/pmc-email.txt` in the `apache/tooling-agents-private` archive — this SKILL no longer drafts, addresses or sends any PMC-facing mail.
  What it does own: reading the scan directory (`scans/glasswing/<repo>/<scan-id>/`), confirming the report was rendered and its fact-preservation verdict is clean before it goes out, resolving the delivery's ponymail permalink on the Tooling list afterwards, and writing the tracker — `Date scan received`, `Forwarded scan to PMC`, the Scan Queue per-scan block, the Scan Results row, and the mandatory `build-status-tab` refresh.
  Use when Jarek says "the <PMC> scan is ready to go", "Tooling sent the <PMC> report", "record the <PMC> delivery", or when a sweep finds a scan Tooling has delivered that the tracker does not yet show as forwarded.
---

# frontier-model-preparation-forward SKILL

The "results path" of the Frontier Model Preparation pipeline — the inverse of `frontier-model-preparation-submit`.

**The send half is retired.** ASF Tooling delivers scan results to PMCs directly, from `vp-tooling@apache.org`, using the template at `docs/pmc-email.txt` in the archive. That is the correct division: Tooling runs the scans, so Tooling reports them. The Security team must never be framed as running them.

What remains here is the half either side of the send:

- **Before** — clear the scan for release: the report exists, it was rendered into the canonical format, and its fact-preservation verdict is clean.
- **After** — record the delivery: resolve its permalink on the Tooling list and write the tracker so the programme's status views are true.

This SKILL never drafts a PMC email, never resolves PMC recipients, and never sends anything.

## When to invoke

- Jarek says "the <PMC> scan is ready to go" / "clear <PMC> for release" (the *before* half).
- Jarek says "Tooling sent the <PMC> report" / "record the <PMC> delivery" (the *after* half).
- A sweep finds a scan in `scans/glasswing/` that Tooling has delivered while the tracker still shows `Forwarded scan to PMC` blank.

Skip when:

- **The scan has no `MAINTAINER-REPORT.md`** — there is nothing to release. Route to [`pre-forward-report-preparation`](../pre-forward-report-preparation/SKILL.md).
- **The report was never rendered, or its verdict is not clean** — see hard rule 2. Surface it; do not clear it.
- **The PMC's pre-flight is incomplete** (`Security model verified` blank) — should not happen at this stage; surface the gap.

## Hard rules (do not skip)

1. **Never draft, address or send a PMC email.** No recipients, no Cc list, no body template, no `forward-draft`. If asked to send the results, say that Tooling sends them and point at `docs/pmc-email.txt`. The one exception is answering a PMC that has written to `security@apache.org` about a delivered report — that is ordinary Security-team correspondence, not a forward.

2. **Clearance is a gate, and it is about the report, not the findings.** Before telling Tooling a scan is ready, confirm in the scan directory that:
   - `MAINTAINER-REPORT.md` exists (and `CRITICAL-CANDIDATES.md`, where the run nominated critical candidates);
   - it was rendered by `maintainer-report-plain-language` — an un-rendered report is unreadable by its audience;
   - its fact-preservation verdict is clean (`report-verification.json` beside the assessment: no `missing`, no `altered`, no `invented`).

   A report that fails any of these does not go out. Surface it and route back to [`pre-forward-report-preparation`](../pre-forward-report-preparation/SKILL.md). This is the last gate before a document reaches a PMC, and the failures it catches are invisible to the person receiving it.

3. **Extract identity from the scan, not from memory.** Repo URL, branch, full commit SHA and clone date come from `PROVENANCE.md` in the scan directory; the run's execution detail is in `METHODOLOGY.md`. **Glasswing scan directories have no `metadata.yml`** — that file belongs to the older `scans/mythos/` layout and reaching for it here is the most likely way to get the identity wrong.

4. **`Forwarded scan to PMC` records when *Tooling* sent it, not when we cleared it.** Never set it on clearance. The evidence that a delivery happened is the message on the Tooling list, not our intention to release.

5. **Ponymail must be authenticated to resolve the permalink.** Run `mcp__ponymail__auth_status`; if it reports "Not authenticated", `mcp__ponymail__login` first — the private `tooling` list is not readable anonymously. If ponymail cannot be authenticated, record the permalink as pending and surface a one-line note rather than blocking the tracker write. (The ponymail MCP blocks `security@apache.org` entirely, so always resolve via `private@tooling.apache.org`.)

6. **Refresh the derived tabs — MANDATORY, not optional.** After the tracker writes, run `sheets-writer build-status-tab`. A delivery is **not** recorded until the Status / Completed / Timeline / Program-totals / Model-Status tabs and the dashboard gist reflect it. Do this after every delivery, every time.

7. **Programme confidentiality still applies to anything we write.** No cost mechanics (credit value, per-token pricing, seat/provisioning) in tracker notes, replies or summaries. In public, these are "security scans" or "Claude security scans"; the methodology in the reports stays PMC-confidential.

## Inputs the SKILL needs

| Input | Source |
| --- | --- |
| Scan directory | `apache/tooling-agents-private/scans/glasswing/<repo>/<scan-id>/` |
| Report + critical candidates | `MAINTAINER-REPORT.md`, `CRITICAL-CANDIDATES.{json,md}` (present only when the run nominated critical candidates) |
| Fact-preservation verdict | `report-verification.json` beside the assessment in `pre-forward-results/` |
| Repo / branch / commit / clone date | `PROVENANCE.md` in the scan directory (**not** `metadata.yml` — it does not exist here) |
| Findings + verdicts, for the Scan Results row | `TRIAGE.{json,md}` — the authoritative verdict record; the report is generated from it |
| Delivery evidence + permalink | The `private@tooling.apache.org` list thread, subject `[ASF CLAUDE SECURITY SCAN] - <repo>` |
| `Date scan requested` (pre-condition) | The PMC sheet — must be filled |

If `MAINTAINER-REPORT.md` is missing, the verification verdict is unclean or absent, or `PROVENANCE.md` is unreadable — stop and surface the gap.

## What ASF Tooling sends (reference only — we do not write it)

Recorded here so the delivery can be recognised on the list and its permalink resolved, **not** as a template to fill. The authoritative copy is `docs/pmc-email.txt` in the archive; if it and this section disagree, the archive wins.

- **From** `vp-tooling@apache.org`, **Reply-to** `private@tooling.apache.org`.
- **To** `private@<project>.apache.org`, `private@tooling.apache.org`, `security@apache.org`.
- **Subject** `[ASF CLAUDE SECURITY SCAN] - <short repo name>`.
- **One attachment**, `scan-<project>-<date>.zip`, holding the full artefact set plus `FAQ.md`.
- The body points the PMC at `MAINTAINER-REPORT.md` first, lists the critical vulnerabilities inline, names `TRIAGE.md` and `PATCHES.md`, and routes critical findings through `cveprocess.apache.org`.
- Signed by ASF Tooling and ASF Security jointly.

`security@apache.org` is a direct recipient, so the delivery lands in the Security team's own inbox — that is the normal signal to run the *after* half.

## Procedure

### A. Clear the scan for release

1. **Identify the scan.** From Jarek's instruction (a project name) or a new directory in `scans/glasswing/`. Resolve to `<repo>/<scan-id>`. Where a repo has several scan directories, take the most recent unless told otherwise. If ambiguous, list candidates and ask.

2. **Refresh the archive locally** — `git pull` on a clean clone of `apache/tooling-agents-private`. (Reaching the private repo over `gh`/git needs the keychain: bypass the sandbox, with the loud banner per the user's rule.)

3. **Read `PROVENANCE.md`** for repo, branch, full commit SHA and clone date. These drive the tracker cells and identify the run.

4. **Run the clearance gate** (hard rule 2): report present, rendered, verdict clean. Report the result plainly — cleared, or the specific failure and where it routes.

5. **Tell the operator the scan is cleared**, naming the scan directory and what Tooling will be sending. Stop there. Handing off to Tooling is the operator's action, not this SKILL's.

### B. Record the delivery, once Tooling has sent it

6. **Confirm it actually went out.** The delivery is Cc'd to `security@apache.org`, so it is in the Security inbox; the durable evidence is the Tooling-list thread. Do not take "Tooling said they would send it" as the trigger.

7. **Resolve the ponymail permalink.** Authenticate (hard rule 5), then `mcp__ponymail__search_list` with `list=private`, `domain=tooling.apache.org`, matching the subject `[ASF CLAUDE SECURITY SCAN] - <repo>` from `vp-tooling@apache.org`. Take its `tid` and build `https://lists.apache.org/thread/<tid>`. The archive can take a minute or two to index — if it is not there yet, record the permalink as pending rather than blocking.

8. **Hand off to [`frontier-model-preparation-update`](../frontier-model-preparation-update/SKILL.md)** to write:
   - `Date scan received` — when the scan landed in the archive (its commit date there), **not** today;
   - `Forwarded scan to PMC` — the date Tooling sent it (hard rule 4);
   - the Tooling-list ponymail permalink from step 7;
   - the scan-id in `Notes`, so the next sweep sees a complete record.

   This SKILL does not write to the spreadsheet directly.

9. **Record the per-scan status in the Scan Queue tab:**

   ```bash
   uv run --project tools/sheets_writer sheets-writer scan-queue-set \
     --spreadsheet-id <id> \
     --repo <repo URL, exactly as in the Scan Queue 'Repo' column> \
     --branch <ref, or omit for the default-branch row> \
     --scan 1 \
     --when-scanned <scan date from PROVENANCE.md> \
     --model-thread <tooling-list permalink from step 7> \
     --when-report-sent <the date Tooling sent it> \
     --commit <full commit SHA>
   ```

   (`--dry-run` first to confirm it targets the right row and cells.) A branch-scoped scan uses that `--branch`; a multi-repo PMC runs this once per scanned repo.

10. **Refresh the `Scan Results` tab:**

    ```bash
    uv run --project tools/sheets_writer sheets-writer build-scan-results-tab \
        --spreadsheet-id "<id>" --archive-root ~/code/tooling-agents-private \
        --today <YYYY-MM-DD>
    ```

    It leaves the four feedback columns blank, which is correct at delivery time — the PMC has not replied yet.

11. **Refresh the derived tabs — MANDATORY closing step** (hard rule 6): `sheets-writer build-status-tab`. The delivery is not recorded until this has run.

### C. When the PMC replies

12. **Record the feedback** with `sheets-writer scan-results-set --scan-id <the same scan id>` (`Feedback received` / `Sentiment` / `Feedback summary` / `Improvements suggested`). See [`frontier-model-preparation-run`](../frontier-model-preparation-run/SKILL.md) Step 6 for how to write those cells — read the whole reply rather than the snippet, quote the load-bearing phrase verbatim, and judge sentiment on the **report**, not on the politeness of the message. A courteous reply saying the findings were not worth the triage effort is `Negative`.

    Tooling's template asks for feedback explicitly and gives `private@tooling.apache.org` as the reply-to, so some replies will not reach us directly — check the Tooling list as well as the Security inbox before recording a scan as having had no response.

    This closes the loop the programme most needs: the reply is the only evidence of whether a scan was worth what it cost the PMC to triage.

## Style notes

- **We clear and we record; Tooling reports.** Any phrasing that puts the Security team in the sending seat is wrong, in the tracker as much as in an email.
- **The gate is about the document, not the findings.** Whether a finding is real is the PMC's call and was settled upstream; whether the report is readable and faithful to its own evidence is ours.
- **One PMC per delivery record.** A scan covering several repos of one PMC is still one delivery, with a Scan Queue row per repo.
- **Pending beats wrong.** A permalink that is not indexed yet gets recorded as pending, never guessed.

## Examples of bad closures (avoid)

- Drafting or sending a PMC email from this SKILL, or reintroducing recipient logic. Tooling sends; `docs/pmc-email.txt` is theirs.
- Setting `Forwarded scan to PMC` on clearance, before Tooling has actually sent.
- Clearing a scan whose report was never rendered, or whose fact-preservation verdict was not clean — both failures are invisible to the PMC receiving it.
- Reading `metadata.yml` for identity in a `scans/glasswing/` directory. It does not exist there; use `PROVENANCE.md`.
- Treating a finding count from `VULN-FINDINGS` as the verdict. `TRIAGE.json` is authoritative; `VULN-FINDINGS` is pre-triage and includes items later rejected.
- Recording a scan as having had no feedback without checking the Tooling list — the template's reply-to points there, not at us.
- Skipping `build-status-tab`. The delivery is not recorded until the derived tabs show it.

## Provenance

This SKILL originally drafted and sent the PMC email itself, in the operator's name, attaching the scan bundle and the pre-forward assessment.

That half was **retired on 2026-08-14**. ASF Tooling now delivers results directly from `vp-tooling@apache.org` using `docs/pmc-email.txt`, agreed in the archive and co-signed by both teams. The change follows the standing scope ruling: threat-model preparation is the Security team's remit, Tooling runs the scans, and Security must never be framed as running them. Reporting sits with whoever ran the scan.

The delivery also moved to the `scans/glasswing/` layout, whose artefact set (`MAINTAINER-REPORT.md`, `TRIAGE`, `VULN-FINDINGS`, `PATCHES`, `PROVENANCE`, `METHODOLOGY`) replaced the older `scans/mythos/` bundle, and whose report is rendered and fact-checked by `maintainer-report-plain-language` before release.

`tools/forward_draft/` was built for the retired half and now has no caller in this repository.
