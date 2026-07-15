---
name: asvs-scan-assess
description: >-
  Produce the Security team's INTERNAL pre-forward assessment of an archived Glasswing scan —
  pull the scan bundle from the `apache/tooling-agents-private` archive (per its README layout),
  read the project's own threat model (the `metadata.yml` `threat_model` URL plus any delegated/umbrella model it points to),
  run the pre-forward sanity check, and triage every finding in `issues.md` against that model's disposition framework (e.g. the threat-model-producer §13 table: VALID / VALID-HARDENING / OUT-OF-MODEL / BY-DESIGN / KNOWN-NON-FINDING / MODEL-GAP).
  The assessment is written back into the private repo under `pre-forward-results/`, mirroring the exact `scans/` path structure — one assessment directory per scan, keyed by the same scan-id.
  This is an INTERNAL working artifact for the team — it is NOT the PMC forward, it does NOT replace the verbatim-forward policy (frontier-model-preparation-forward still forwards ASF Tooling's findings unedited), and it is NEVER published to a gist or any public surface (pre-disclosure candidates stay in the private repo).
  Assess ONLY scans whose project has completed threat-model preparation — i.e. the Mythos tracker's `Security model verified` is set for that PMC (per frontier-model-preparation-model-verify); skip projects whose model is merely nominated or pending verification.
  Output is a set of files committed to `apache/tooling-agents-private` after explicit human approval — never auto-committed, never sent anywhere.
  Use whenever Jarek says "assess the <project> scan", "do the pre-forward assessment for <project>", "triage the <project> scan against its threat model", "assess the pending scans", or "store the assessment in pre-forward-results".
---

# asvs-scan-assess SKILL

The **pre-forward assessment** step of the Glasswing pipeline — a deeper, written-down companion to the sanity check that `frontier-model-preparation-forward` does inline.

Where `frontier-model-preparation-forward` forwards ASF Tooling's findings to the PMC **verbatim** (no per-finding triage on the PMC's behalf — that policy is unchanged), this SKILL produces the team's **own internal read** of a scan against the project's threat model and files it in the private archive. The assessment helps the team:

- catch catastrophic generation errors before a forward (the sanity check, written down rather than ad-hoc);
- understand where each finding likely lands against the project's model (so the team can answer a PMC's later question, or feed ASF Tooling's next-run suppression list);
- surface **model gaps** — findings whose disposition hinges on a trust boundary the project's model doesn't yet state — which become threat-model-producer follow-ups;
- keep an auditable per-scan record of "what we thought before forwarding," diffable against the next scan of the same repo.

**This is an internal artifact, not a PMC-facing one.** The PMC still owns the authoritative per-finding triage against their own model (memory: PMC scan-report framing). The assessment never gets pasted into the forwarding email as a disposition appendix, and it never leaves the private repo.

## When to invoke

- Jarek says "assess the `<project>` scan", "do the pre-forward assessment for `<project>`", "triage the `<project>` scan against its threat model", "assess the pending scans", "re-assess `<project>`".
- A new scan lands in `apache/tooling-agents-private/scans/` with `sanity_check: PENDING` and no corresponding `pre-forward-results/` entry, and the team wants the internal read before forwarding.
- `frontier-model-preparation-run`'s sweep flags a scan as "results back, not yet assessed."

Skip / refuse when:
- **The project has not completed threat-model preparation** — the Mythos tracker's `Security model verified` cell for the PMC is blank (model merely nominated, or pending verification). See hard rule 2. Without a *verified* model there is no stable contract to disposition against; surface the gap and route to `frontier-model-preparation-model-verify` instead.
- The scan bundle is missing `issues.md` or `metadata.yml` — surface the gap; there is nothing to triage.
- The `metadata.yml` `threat_model` URL is absent or unreachable — refuse and surface; an assessment without the model is just opinion, not a disposition against the contract.

For "assess the pending scans", the eligible set is the **intersection** of (scans archived but not yet assessed) and (projects whose `Security model verified` is set). Projects with an archived scan but an unverified model are listed as "skipped — model not verified", not assessed.

## Hard rules (do not skip)

1. **This is internal, not the forward.** The assessment never replaces or modifies the verbatim-forward policy. `frontier-model-preparation-forward` still sends ASF Tooling's findings unedited; this SKILL's dispositions are the team's private working note, not labels applied to the PMC's copy. Do not let an assessment leak into a PMC-facing email as a per-finding triage appendix.

2. **Eligible projects only — completed threat-model preparation.** Assess a scan **only if** the project's threat-model preparation is complete: the Mythos tracker's `Security model verified` cell for that PMC is set (the Model Status tab shows the model verified), per `frontier-model-preparation-model-verify`. A scan whose `metadata.yml` carries a `threat_model` URL is **not** sufficient — the URL existing only means the scanner found *a* doc; the gate is that the team has *verified* the model (discoverability + completeness against the threat-model-producer rubric). If the model is merely nominated or pending verification, **do not assess** — surface the gap and route to `frontier-model-preparation-model-verify`. Disposition without a verified contract is opinion, not triage.

3. **Never a gist, never public.** Results go **only** to `apache/tooling-agents-private/pre-forward-results/`. These are pre-disclosure vulnerability candidates (see the archive README's Confidentiality section). No public gist, no paste into a public tracker, no third-party surface. (This SKILL exists precisely because the one-off version wrote to a gist — the canonical home is the private repo.)

4. **Triage against the project's OWN model, not a generic checklist.** Read the `threat_model` URL from the scan's `metadata.yml`, and **follow delegation** — if that doc delegates to an umbrella / addendum model (as `directory-ldap-api/SECURITY.md` → `directory-server/THREAT_MODEL.md` does), read the umbrella too and use **its** disposition vocabulary (the threat-model-producer §13 table). Only fall back to the generic disposition set (below) when the project's model defines none.

5. **Mirror the `scans/` path exactly.** The assessment for a scan at `scans/<rel>/` is written to `pre-forward-results/<rel>/` — identical relative path, same scan-id leaf directory, same single-repo-collapse rule. A reader must be able to `diff -r scans/<rel> pre-forward-results/<rel>` and have the paths line up. See the layout in the archive README.

6. **Read the actual finding text — no triage from titles.** Disposition each finding from its body in `issues.md` (and `consolidated.md` / `_security_profile.md` for context), against the model. A disposition assigned from a heading alone is not acceptable; the model distinctions (in-scope adversary vs. operator-trusted input vs. privileged write vs. disclaimed property) live in the finding's details.

7. **Be decisive, but flag genuine MODEL-GAPs.** Assign each finding exactly one disposition. When a finding's disposition genuinely depends on a trust boundary the model does not state (e.g. "is LDIF admin-only import or untrusted app input?"), disposition it `MODEL-GAP` and record the specific ruling the PMC/model-owner would need to make. Do not invent a boundary the model doesn't have just to force a clean disposition.

8. **Don't second-guess ASF Tooling's findings on substance beyond the model.** The job is *disposition against the contract*, not re-auditing the code. If a finding looks technically wrong, note it briefly as an observation — but the disposition is about scope/model, and the authoritative correctness call is still the PMC's.

9. **Draft + confirm before any write to the private repo.** Show the planned files (paths + content) and the planned commit (message + file list) and wait for explicit "yes" / "go" before `git add/commit` and before `git push` / opening a PR. Pushing to a shared private repo is an outward-facing action — it gets a confirmation, every time.

10. **Commit hygiene.** Commit message starts with `[pre-forward] <project>/<repo>` (parallel to the archive's `[scan]` convention, so `git log --grep '\[pre-forward\]'` works). No PMC member / reporter names in commit metadata. End the message with the repo's `Generated-by:` trailer (memory: this repo uses `Generated-by:`, never `Co-Authored-By:`). Run `prek run --all-files` before committing if committing into a repo that runs it.

11. **Stamp provenance, including the model.** Every assessment records `assessed_with` (the model id that produced it, e.g. `claude-opus-4-8`), `assessed_by` (operator `@apache.org`), and `assessed_date`. The archive README's confidentiality note requires knowing which model touched pre-disclosure findings.

## Disposition framework

Use the project model's own table when it has one. The threat-model-producer rubric (which most of these models follow) defines a **§13 triage dispositions** table — use those labels verbatim. The generic fallback set, when the model defines none:

| Disposition | Meaning |
| --- | --- |
| `VALID` | Breaks a claimed property via an in-scope adversary/input in a default/secure config. |
| `VALID-HARDENING` | No claimed property broken, but a documented misuse is easy enough to warrant a safer default / guard. |
| `OUT-OF-MODEL: trusted-input` | Requires control of config / schema / ACI / policy / keytab / stored data. |
| `OUT-OF-MODEL: adversary-not-in-scope` | Requires operator / admin / key-holder capability. |
| `OUT-OF-MODEL: unsupported-component` | Lands in examples, tests, build/CI tooling, or a component the model scopes out. |
| `OUT-OF-MODEL: non-default-build` | Only reachable with an insecure non-default option enabled. |
| `BY-DESIGN: property-disclaimed` | Concerns a property the model explicitly disclaims (e.g. "no security without configuration"; "client ≠ server"). |
| `KNOWN-NON-FINDING` | Matches a model's known-non-findings / recurring-false-positive list. |
| `MODEL-GAP` | Routes to none of the above → the model needs a ruling (record which one). |

The headline the team cares about: **how many `VALID`** (real, default-config, in-scope) vs. how many are hardening / out-of-model / disclaimed — and any `MODEL-GAP`s that should become model updates.

## Inputs the SKILL needs

| Input | Source |
| --- | --- |
| Which scan(s) to assess | The user names a project (and repo, if multi-repo), or "the pending scans". Resolve to scan-id directory/directories under `scans/`. |
| Threat-model-prep status (eligibility gate) | The Mythos tracker's `Security model verified` cell for the PMC (PMCs sheet / Model Status tab). Required: assess only projects where this is set (hard rule 2). Read via the `frontier-model-preparation-status` flow or the `mythos-tracker` reference (fileId `1pxaWKXYtZ-89cKk3OYE99-ewPMh2kXKvSDaqjR-I1o8`). |
| Scan bundle | `apache/tooling-agents-private/scans/<rel>/` — at minimum `metadata.yml`, `issues.md`; also `consolidated.md`, `_security_profile.md`, `_filter_drop_log.md`, `_review_queue.md`, `issues_cross_reference.md` when present. |
| Project threat model | The `threat_model` URL in the scan's `metadata.yml`, **plus** any model it delegates to (follow the chain). |
| Operator identity | The operator's `@apache.org` for `assessed_by`. |

If the threat model URL is missing/unreachable, or `issues.md`/`metadata.yml` is absent — refuse and surface.

## Output structure (`pre-forward-results/`)

Mirror `scans/` exactly. For a scan at `scans/<rel>/<scan-id>/`, write `pre-forward-results/<rel>/<scan-id>/` (single-repo-collapse applies identically). On first run, also create `pre-forward-results/README.md` (bootstrap — see step 6).

Each assessment leaf directory holds:

| File | Purpose |
| --- | --- |
| `metadata.yml` | Assessment header — back-pointer to the scan, threat-model chain, disposition framework used, disposition counts, recommended sanity verdict, model-gap count, provenance. |
| `assessment.md` | The full write-up — threat-model context, sanity-check log, the per-finding disposition table, the headline, and structural notes (duplicates, coverage gaps, model gaps). |
| `dispositions.yml` | Machine-readable per-finding map: finding id → `{disposition, one-line rationale}`. Lets a later run diff dispositions across re-scans without re-parsing prose. |

### `metadata.yml` shape

```yaml
project:               directory-ldap-api
repo:                  apache/directory-ldap-api/directory-ldap-api
scan_id:               directory-ldap-api-directory-ldap-api-2026-06-18-dcdf704
scan_path:             scans/directory-ldap-api/directory-ldap-api-directory-ldap-api-2026-06-18-dcdf704
head_sha:              be666c2fcd27ec809703dec50e508c2fdc7f6654
short_sha:             dcdf704
threat_model:          https://github.com/apache/directory-ldap-api/blob/dcdf704/SECURITY.md
threat_model_refs:     [https://github.com/apache/directory-server/blob/master/THREAT_MODEL.md]   # delegated/umbrella models followed
disposition_framework: "umbrella THREAT_MODEL.md §13"
findings_assessed:     20
dispositions:                          # counts by disposition
  VALID:                       0
  VALID-HARDENING:             13
  OUT-OF-MODEL:                5
  BY-DESIGN:                   1
  KNOWN-NON-FINDING:           0
  MODEL-GAP:                   1
model_gaps:            1               # findings flagged MODEL-GAP, worth a model ruling
sanity_check:          PASS            # recommended verdict: PENDING / PASS / PASS-with-notes / RETURNED
assessed_by:           <operator>@apache.org
assessed_date:         2026-06-24
assessed_with:         claude-opus-4-8
```

### `assessment.md` shape

```markdown
# <project>/<repo> — pre-forward assessment (<scan-id>)

**Scan:** scans/<rel>/<scan-id>  ·  **Commit:** <short-sha>  ·  **ASVS:** <level>
**Threat model:** <threat_model URL> → <delegated/umbrella URL if any>
**Assessed:** <date> by <operator>@apache.org with <model>

## Threat-model context
<2–5 bullets: what the model actually claims for THIS component, the disclaimers
that bear on disposition, the operator-trusted inputs, the known-non-findings.>

## Sanity check
<per-check PASS / PASS-with-note / FAIL — project identity, model identity,
coverage, truncation, cross-PMC leakage, formatting, plausibility>
Recommended verdict: <PASS / PASS-with-notes / RETURNED>

## Dispositions
| # | Finding (file) | Disposition | Why |
|---|---|---|---|
| 001 | <title> (<file>) | <disposition> | <one-line model rationale> |
| ... |

## Headline
- VALID: <n> · VALID-HARDENING: <n> · OUT-OF-MODEL: <n> · BY-DESIGN: <n> · MODEL-GAP: <n>
- <the standout finding(s)>
- Structural notes: <duplicates to merge, coverage gaps, model gaps to feed back>

*Internal pre-forward assessment. Per-finding triage authority is the PMC's against their own model.*
```

## Procedure

1. **Resolve the scan(s) and apply the eligibility gate.** From the user's project/repo (or "pending"), locate the scan-id directory under `scans/`. For "pending", select scans whose `metadata.yml` has `sanity_check: PENDING` **and** no existing `pre-forward-results/<rel>/<scan-id>/` directory. Then **filter to eligible projects only** (hard rule 2): check each candidate PMC's `Security model verified` cell in the Mythos tracker, and drop any whose model is not verified. List what you'll assess **and** what you're skipping (`skipped — model not verified`), and confirm scope if more than one. If the user named a single project whose model is not verified, refuse and route to `frontier-model-preparation-model-verify`.

2. **Get the archive locally.** Work against a clone of `apache/tooling-agents-private` (clone if absent, else `git pull` on a clean tree). Reading individual files via `gh api .../contents/...` is fine for a single scan, but writing the assessment + committing wants a local checkout. (Reaching the private repo over `gh`/git needs the keychain — bypass the sandbox for those calls, with the loud banner per the user's rule.)

3. **Read the scan bundle.** `metadata.yml` (project, repo, head_sha, threat_model, asvs_level, findings_total), `issues.md` (the findings), and for context `consolidated.md`, `_security_profile.md`, `_filter_drop_log.md`, `_review_queue.md`, `issues_cross_reference.md` where present.

4. **Read the project's threat model.** Fetch the `threat_model` URL at the scanned commit; **follow delegation** to any umbrella/addendum model and read that too. Identify the disposition framework (its §13 table, or the generic fallback). Extract: what the model claims for this component, its disclaimers, its operator-trusted inputs, its known-non-findings, its out-of-scope list.

5. **Run the sanity check + triage.**
   - Sanity check (same checklist as `frontier-model-preparation-forward`): project identity, model identity, repo coverage, truncation, cross-PMC leakage, formatting, plausibility. Record per-check PASS / PASS-with-note / FAIL and a recommended verdict. On a FAIL, surface it — a broken scan should go back to ASF Tooling, not be assessed as if sound.
   - Triage each finding in `issues.md` against the model, assigning exactly one disposition (hard rules 4, 6, 7). Note duplicates, coverage gaps (e.g. "no findings against the model's primary claimed property"), and MODEL-GAPs.

6. **Write the assessment files** into `pre-forward-results/<rel>/<scan-id>/` — `metadata.yml`, `assessment.md`, `dispositions.yml` (shapes above). If `pre-forward-results/README.md` doesn't exist yet, create it: a short doc stating that this tree mirrors `scans/` one-for-one, that each leaf is the team's internal pre-forward assessment of the same-named scan, the file roles, and a pointer to the Confidentiality section of the archive README (these are pre-disclosure candidates; private repo only).

7. **Show + confirm.** Present the planned file paths, the assessment content (at least the disposition table + headline + sanity verdict), and the planned commit message. Wait for explicit "yes".

8. **Commit + push** (after approval). One commit per scan (or one per batch if assessing several — operator's call), message prefixed `[pre-forward] <project>/<repo> <YYYY-MM-DD>-<short-sha>`, `Generated-by:` trailer, `prek run --all-files` first if applicable. Push to `main` (or open a PR per local convention). The push is a second confirmation point if the operator wants to review the commit before it lands.

9. **Hand off.** Surface the headline to the operator and, where relevant:
   - feed `MODEL-GAP`s to **threat-model-producer** (the model needs a ruling/addendum);
   - feed `KNOWN-NON-FINDING` / clearly-out-of-model patterns to the next ASF Tooling run's suppression list;
   - note the recommended sanity verdict so the operator (or `frontier-model-preparation-forward`) can stamp `sanity_check` on the scan's own `metadata.yml` — **this SKILL does not mutate the scan bundle**, only `pre-forward-results/`.

## Relationship to the other Glasswing skills

- **`frontier-model-preparation-forward`** — forwards ASF Tooling's findings to the PMC **verbatim**. This SKILL does *not* change that; the assessment is internal and stays in the private repo. The two are complementary: assess (internal read) → forward (verbatim to PMC).
- **`frontier-model-preparation-model-verify`** — the upstream eligibility gate. A project is only assessable here once its model is verified there (`Security model verified` set in the tracker — hard rule 2). Projects with an archived scan but an unverified model are skipped and routed back to model-verify.
- **`threat-model-producer`** — consumes this SKILL's `MODEL-GAP` findings; produces the model additions that close them.
- **`frontier-model-preparation-run`** — the sweep can flag scans that are archived but not yet assessed, routing here.
- **`triage-assess`** — that SKILL triages *inbound security@ reports* against a model and drafts replies; this one triages *archived ASF Tooling scans* into the private `pre-forward-results/` tree. Same disposition discipline, different input and output surface.

## Style notes

- **Decisive table, short rationales.** One disposition per finding, one line of model-grounded "why." The table is the artifact; don't bury it in prose.
- **Lead with the headline.** VALID count first — that's the number that decides urgency. Then the standout finding(s) and structural notes.
- **Name the model section/clause** in rationales (e.g. "§9 disclaimed", "§6 operator-trusted", "§11a known non-finding") so a reader can check the call against the model.
- **MODEL-GAP is a feature, not a cop-out** — but only for genuine boundary ambiguity. Record the exact ruling needed.
- **No padding.** A clean sanity check needs one line, not a paragraph. An assessment with zero VALID is a fine, common result — say so plainly.

## Examples of bad assessments (avoid)

- Writing the assessment to a gist or any public surface. The canonical home is `pre-forward-results/` in the private repo; pre-disclosure candidates do not go public. (This SKILL exists to stop exactly that.)
- Letting the internal dispositions bleed into the PMC forward as a per-finding triage appendix. The PMC owns that read; the forward is verbatim.
- Triaging from finding titles without reading the bodies — the model distinctions live in the details.
- Assigning dispositions against a generic checklist when the project's model has its own §13 table — use the project's vocabulary.
- Forcing a clean disposition on a finding whose scope genuinely depends on an unstated trust boundary, instead of flagging `MODEL-GAP`.
- Mutating the scan bundle (`scans/...`) — this SKILL only writes under `pre-forward-results/`.
- Auto-committing / pushing without showing the files and the commit and getting an explicit "yes".

## Provenance

Created when the one-off, gist-based pre-forward assessment (a manual triage of a single scan written to a public gist) was promoted into a repeatable SKILL with a proper home: the team's internal read now lands in `apache/tooling-agents-private/pre-forward-results/`, mirroring the `scans/` archive one-for-one, private and auditable. The forward-to-PMC-verbatim policy is unchanged — this is the team's working note alongside the forward, not a replacement for it.
