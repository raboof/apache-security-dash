---
name: asvs-scan-assess
description: >-
  Produce the Security team's INTERNAL pre-forward assessment of an archived Glasswing scan —
  pull the scan bundle from the `apache/tooling-agents-private` archive (per its README layout),
  read the project's own threat model (the `metadata.yml` `threat_model` URL plus any delegated/umbrella model it points to),
  run the pre-forward sanity check, and triage every finding in `issues.md` against that model's disposition framework (e.g. the threat-model-producer §13 table: VALID / VALID-HARDENING / OUT-OF-MODEL / BY-DESIGN / KNOWN-NON-FINDING / MODEL-GAP).
  The assessment is written back into the private repo under `pre-forward-results/`, mirroring the exact `scans/` path structure — one assessment directory per scan, keyed by the same scan-id.
  The assessment is the team's own read; as of 2026-07-15 it is ATTACHED to the PMC forward (frontier-model-preparation-forward) as an ADVISORY guide — the dispositions help the PMC triage quickly, but the PMC still owns the authoritative per-finding call. It is NEVER published to a gist or any public surface (pre-disclosure candidates stay in the private repo and go only to the PMC's @apache.org recipients via the forward).
  Assess ONLY scans whose project has completed threat-model preparation — i.e. the Mythos tracker's `Security model verified` is set for that PMC (per frontier-model-preparation-model-verify); skip projects whose model is merely nominated or pending verification.
  Output is a set of files committed to `apache/tooling-agents-private` after explicit human approval — never auto-committed; shared with the PMC only as the forward's attachment, never to a public surface.
  Two optional Claude Code Security plugin steps sit alongside the model triage and never replace it: an opt-in per-finding truth panel (`claude-security:scan-verifier`, three lenses, votes TRUE_POSITIVE/FALSE_POSITIVE against the code at head_sha — answers "is this finding true", not "is it in scope"), and a routine fold-in of any plugin scan of the same repo already archived under `scans/claude-code-security-*/`, whose threat-model defects, report corrections and coverage gaps can change dispositions here. Neither the panel nor a fresh plugin scan runs by default — both cost real agent budget and need explicit operator instruction.
  Use whenever Jarek says "assess the <project> scan", "do the pre-forward assessment for <project>", "triage the <project> scan against its threat model", "assess the pending scans", or "store the assessment in pre-forward-results".
---

# asvs-scan-assess SKILL

The **pre-forward assessment** step of the Glasswing pipeline — a deeper, written-down companion to the sanity check that `frontier-model-preparation-forward` does inline.

`frontier-model-preparation-forward` delivers the scan bundle **and this assessment** to the PMC as attachments — the assessment as an **advisory** guide (the PMC still owns the authoritative per-finding call; the team does not decide findings on the PMC's behalf). This SKILL produces the team's read of a scan against the project's threat model and files it in the private archive. The assessment helps the team:

- catch catastrophic generation errors before a forward (the sanity check, written down rather than ad-hoc);
- give the PMC a starting-point read of where each finding likely lands against their model (attached to the forward), and let the team answer a PMC's later question or feed ASF Tooling's next-run suppression list;
- surface **model gaps** — findings whose disposition hinges on a trust boundary the project's model doesn't yet state — which become threat-model-producer follow-ups;
- keep an auditable per-scan record of "what we thought before forwarding," diffable against the next scan of the same repo.

**The assessment is advisory, and the PMC still owns the authoritative per-finding triage against their own model** (memory: PMC scan-report framing). As of 2026-07-15 it is **attached to the forward** as a guide (not pasted inline in the email body — it rides as `assessment.md`); its dispositions help the PMC decide quickly but do not decide for them. It never goes to a gist or any public surface — only to the PMC's `@apache.org` recipients via the forward, and otherwise stays in the private repo.

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

1. **Advisory, not a ruling.** The assessment is attached to the PMC forward (as of 2026-07-15) as an advisory guide; the PMC still owns the authoritative per-finding call, and the team does not decide findings on the PMC's behalf. The dispositions guide the PMC to triage quickly — they are not the team's verdict imposed on the PMC's copy. Deliver the assessment as the attached `assessment.md` (via `frontier-model-preparation-forward`); do not inline the dispositions into the email body.

2. **Eligible projects only — completed threat-model preparation.** Assess a scan **only if** the project's threat-model preparation is complete: the Mythos tracker's `Security model verified` cell for that PMC is set (the Model Status tab shows the model verified), per `frontier-model-preparation-model-verify`. A scan whose `metadata.yml` carries a `threat_model` URL is **not** sufficient — the URL existing only means the scanner found *a* doc; the gate is that the team has *verified* the model (discoverability + completeness against the threat-model-producer rubric). If the model is merely nominated or pending verification, **do not assess** — surface the gap and route to `frontier-model-preparation-model-verify`. Disposition without a verified contract is opinion, not triage.

3. **Never a gist, never public.** Results go **only** to `apache/tooling-agents-private/pre-forward-results/`. These are pre-disclosure vulnerability candidates (see the archive README's Confidentiality section). No public gist, no paste into a public tracker, no third-party surface. (This SKILL exists precisely because the one-off version wrote to a gist — the canonical home is the private repo.)

4. **Triage against the project's OWN model, not a generic checklist.** Read the `threat_model` URL from the scan's `metadata.yml`, and **follow delegation** — if that doc delegates to an umbrella / addendum model (as `directory-ldap-api/SECURITY.md` → `directory-server/THREAT_MODEL.md` does), read the umbrella too and use **its** disposition vocabulary (the threat-model-producer §13 table). Only fall back to the generic disposition set (below) when the project's model defines none.

5. **Mirror the `scans/` path exactly.** The assessment for a scan at `scans/<rel>/` is written to `pre-forward-results/<rel>/` — identical relative path, same scan-id leaf directory, same single-repo-collapse rule. A reader must be able to `diff -r scans/<rel> pre-forward-results/<rel>` and have the paths line up. See the layout in the archive README.

6. **Read the actual finding text — no triage from titles.** Disposition each finding from its body in `issues.md` (and `consolidated.md` / `_security_profile.md` for context), against the model. A disposition assigned from a heading alone is not acceptable; the model distinctions (in-scope adversary vs. operator-trusted input vs. privileged write vs. disclaimed property) live in the finding's details.

7. **Be decisive, but flag genuine MODEL-GAPs.** Assign each finding exactly one disposition. When a finding's disposition genuinely depends on a trust boundary the model does not state (e.g. "is LDIF admin-only import or untrusted app input?"), disposition it `MODEL-GAP` and record the specific ruling the PMC/model-owner would need to make. Do not invent a boundary the model doesn't have just to force a clean disposition.

8. **Separate the truth question from the scope question — and answer both.** Two orthogonal axes, never collapsed into one:
   - *Is the finding **true**?* — settled by the independent truth panel (step 5.5), which votes `TRUE_POSITIVE` / `FALSE_POSITIVE` against the code at `head_sha`.
   - *Is the finding **in scope**?* — settled by disposition against the project's model (step 5).

   A finding the panel refutes is dispositioned `WITHDRAWN` and does **not** get a scope disposition; disputing scope on a finding that isn't true is wasted PMC attention. Do not re-audit the whole codebase — the job is still disposition, not a fresh scan — but where the panel produces an evidenced, file:line-cited refutation, record it. The authoritative correctness call remains the PMC's; a `WITHDRAWN` is the team's evidenced recommendation, phrased as such.

   *(Superseded the pre-2026-07-26 rule "don't second-guess ASF Tooling's findings on substance". In practice that rule cost real signal: reviews that did look at substance withdrew findings that were factually wrong about the code, and surfaced true findings neither the scan nor the first-pass assessment had.)*

9. **Draft + confirm before any write to the private repo.** Show the planned files (paths + content) and the planned commit (message + file list) and wait for explicit "yes" / "go" before `git add/commit` and before `git push` / opening a PR. Pushing to a shared private repo is an outward-facing action — it gets a confirmation, every time.

10. **Commit hygiene.** Commit message starts with `[pre-forward] <project>/<repo>` (parallel to the archive's `[scan]` convention, so `git log --grep '\[pre-forward\]'` works). No PMC member / reporter names in commit metadata. End the message with the repo's `Generated-by:` trailer (memory: this repo uses `Generated-by:`, never `Co-Authored-By:`). Run `prek run --all-files` before committing if committing into a repo that runs it.

11. **Stamp provenance, including the model.** Every assessment records `assessed_with` (the model id that produced it, e.g. `claude-opus-4-8`), `assessed_by` (operator `@apache.org`), and `assessed_date`. The archive README's confidentiality note requires knowing which model touched pre-disclosure findings.

12. **Never spend agent budget by default.** The default assessment is the operator reading the bundle against the model — steps 1–5, then 6. The two Claude Code Security plugin steps cost real money and are **opt-in on explicit operator instruction**, never automatic and never proposed as "while we're here":

    | Step | Cost | Default |
    | --- | --- | --- |
    | 5.5 truth panel (`scan-verifier` × 3 lenses × N findings) | high — hundreds of `xhigh` agent dispatches on a large bundle | **OFF.** Run only when the operator asks. When they do, panel the load-bearing set unless they say otherwise; putting a whole bundle to the panel needs its own explicit go-ahead. |
    | Running a **full plugin scan** of the PMC repo (`/claude-security` → scan-codebase) | highest — a complete multi-agent scan of the repository | **OFF, and out of scope for this SKILL.** Never start one to support an assessment. If the operator wants one, it is a separate deliberate job with its own archive tree. |
    | 5.6 folding in a plugin review **already in the archive** | negligible — reading committed files | **ON.** Always check for a sibling bundle; reading one costs nothing. |

    So: step 5.6 is routine, step 5.5 is asked-for, and a fresh plugin scan is never this SKILL's call. If the panel would materially change the assessment, say so and let the operator decide — do not run it and present the bill afterwards.

13. **Cite the property, or it is not `VALID`.** Before dispositioning a finding `VALID`, **name and quote** the specific clause of the project's model that states the property it violates, *and* the clause that establishes the attacking principal as untrusted. If you cannot quote both, the finding is not `VALID` — it is `MODEL-GAP` (the model is silent and needs a ruling) or `OUT-OF-MODEL` (the model excludes it).

    *"It is obviously a security boundary"* is not a citation. Neither is the scanner's framing, nor the truth panel's — **both routinely assert boundaries the project has never undertaken to defend.** A scanner that says "cross-tenant" has told you what it thinks the impact is, not what the project promised.

    **The mirror matters as much, and skipping it drops real findings rather than keeping false ones.** Before excluding on an out-of-scope clause, read the *whole* clause and check for a carve-back. Models routinely disclaim a category and then hand scope straight back — APISIX §4.3 point 5 reads as a blanket "all plugins are opt-in" exclusion and then says "enabling a plugin and finding a bug in it **is in scope of §4.8**". §4.8 point 8 does the same in the other direction, pre-empting the exact "the config author made a typo" exclusion a first-pass assessment reached for.

    *(Added 2026-08-12 after the APISIX assessment. The first pass led with five "multi-tenant boundary crossings" including both HIGHs, having adopted the scanner's framing without opening §4.3 — which puts Kubernetes namespace isolation explicitly out of scope and treats a CRD creator as assumed-trusted. Its own stated test said "crosses a boundary the project claims"; nothing forced the model to be opened, so it wasn't. Applying this rule honestly moved that bundle from 19 asserted CVE candidates to 9, and promoted three findings the first pass had buried.)*

14. **Re-check survivors against the newest commit you hold, before reporting any of them.** Bundles are routinely scanned at **different commits per scanner** — weeks apart. A finding reported at the older commit may already be fixed at the newer one, in the same delivered bundle. For every finding you are about to put in front of the PMC, confirm it is still present at the newest commit available for that repository, and record `status: fixed-upstream` with the fixing commit for any that are not.

    Cheap to run (`git merge-base --is-ancestor`, then read the cited code at the newer tree) and it protects the PMC's attention and the team's credibility in one step. Reporting a fixed HIGH is the single most expensive error this SKILL can make.

    *(Added 2026-08-12. The APISIX ingress bundle was scanned at `611487c` (2026-07-08) and `39325e8` (2026-08-06); the fix landed at `be19f90` (2026-07-29), between them. Three findings — including **both** HIGHs and the expert panel's only unanimous CVE candidate — were already fixed 8 days before the bundle was delivered, and the assessment led with one of them as live. The exploitability pass had named this exact gap as a limitation and not acted on it.)*

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
| `WITHDRAWN` | **Not true.** The truth panel (step 5.5) refuted it against the code at `head_sha` — the finding is factually wrong about what it cites. Carries the panel's tally + decisive `file:line`; no scope disposition is assigned. |
| `FIXED-UPSTREAM` | **True when scanned, fixed since.** Step 5.7 confirmed the defect is gone at the newest commit held for the repo. Carries the fixing commit. The scan-time verdict stays as recorded — it described a different commit — and is not a contradiction. |

`WITHDRAWN` is a *truth* verdict and the only one the truth panel can produce; `FIXED-UPSTREAM` is a *currency* verdict from step 5.7; every other row is a *scope* verdict assigned against the project's model. A finding gets exactly one row, from whichever axis settles it first — truth, then currency, then scope. There is no point dispositioning the scope of something that is not true, and no point reporting the scope of something already fixed.

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
| `verification.yml` | Truth-panel record (step 5.5): finding id → the three lens votes, the code-computed tally, and the decisive `file:line`. Written only when the panel ran; its `WITHDRAWN` set feeds `dispositions.yml`. |

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

# --- step 5.5: independent truth panel (claude-security plugin) -------------
verification:
  status:              RAN             # RAN / PARTIAL / SKIPPED / NOT-APPLICABLE
  verifier:            claude-security:scan-verifier 0.10.0
  scan_root:           <org>/<repo> @ <head_sha>   # the checkout the panel judged against
  lenses:              [REACHABILITY, IMPACT, DEFENSES]
  quorum:              "2 of 3 FALSE_POSITIVE refutes"
  panelled:            <n>             # findings put to the panel
  not_panelled:        <n>             # and why — see verification.yml
  withdrawn:           <n>             # refuted; carry no scope disposition

# --- step 5.6: judgment applied from a plugin scan of the same repo ---------
plugin_review:
  source:              scans/claude-code-security-<model>-<effort>[-adversarial]/<project>/<scan-id>
  direction:           plugin-review -> this assessment   # which way the judgment flowed
  applied_date:        <YYYY-MM-DD>
  applied:             [<TM-n>, <AC-n>, ...]   # verified against the tree, dispositions changed
  unconfirmed:         [<TM-n>, ...]           # judgment recorded, could not be confirmed
  gate_impact:         "<AC-n> — model re-verification requested; routed to model-verify"
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
   - **Note every commit the bundle was scanned at.** Where scanners ran at different commits, record each and establish their order (`git merge-base --is-ancestor <older> <newer>`). This is the input to step 5.7 and is cheap to capture now.
   - Triage each finding in `issues.md` against the model, assigning exactly one disposition (hard rules 4, 6, 7). Note duplicates, coverage gaps (e.g. "no findings against the model's primary claimed property"), and MODEL-GAPs.
   - **Apply the cite-the-property gate to every candidate `VALID`** (hard rule 13). Quote the clause stating the property and the clause making the principal untrusted, into the `why` field. No pair of quotes → `MODEL-GAP` or `OUT-OF-MODEL`, not `VALID`. Before excluding on an out-of-scope clause, read the whole clause for a carve-back.

5.5. **Run the independent truth panel — only if the operator asked** (Claude Code Security plugin — `claude-security` ≥ 0.10.0). Off by default; see hard rule 12. If it was not asked for, record `verification: NOT-RUN` and go to 5.6.

   The panel answers *"is this finding true?"* — the axis the model triage in step 5 cannot reach. It is an independent second opinion on ASF Tooling's findings, not a re-scan.

   **Prerequisite — a `SCAN_ROOT`.** The verifier judges against *source*, not against the report, so this step needs a checkout of the PMC repo at the bundle's `head_sha` (step 2 only clones the archive). Clone `<repo>` to a scratch path and `git checkout <head_sha>` — the exact commit, never the branch tip, or the cited lines will have moved. If the commit is unreachable (force-push, deleted branch), **skip the panel** and record `verification: SKIPPED — head_sha unreachable`; do not verify against a different tree.

   **Dispatch.** For each finding in `issues.md` that carries a `file:line`, dispatch `claude-security:scan-verifier` **three times — once per lens** (`REACHABILITY`, `IMPACT`, `DEFENSES`), each with:
   - `SCAN_ROOT` as an absolute path (the agent runs `git -C <SCAN_ROOT>` and reads by absolute path; it does *not* assume the cwd);
   - the finding as written — title, rationale, cited `file:line`, evidence — quoted as data;
   - the lens name.

   Each returns `{verdict: TRUE_POSITIVE | FALSE_POSITIVE, reasoning}` — the reasoning must cite the decisive `file:line`.

   **Tally in code, not in a model** (this is why the plugin's own workflow computes it outside every agent): a finding is refuted when **≥ 2 of 3** lenses return `FALSE_POSITIVE`. Refuted → `WITHDRAWN`. Survivors carry on to the step-5 scope disposition unchanged.

   **What this step does *not* do.** The verifier's vocabulary is binary; it cannot re-bucket a scope disposition, audit scan coverage, or surface a finding the scan missed. Those remain manual assessment work — and in practice that is where a review finds most of its value: true findings the scan never reported, and coverage claims that turn out to be artefacts of how little of the tree was actually read. A clean panel is **not** evidence the assessment is sound. Findings with no `file:line` are un-panelable; list them as `verification: NOT-APPLICABLE` rather than silently dropping them.

   **Cost.** Three `xhigh` read-only agents per finding — a large bundle therefore costs hundreds of dispatches, so do not panel everything by reflex. Panel the load-bearing set first (every `VALID`, every `MODEL-GAP`, and any finding whose disposition rests on "a lower layer sanitises it"); panel the long `VALID-HARDENING` tail only on the operator's say-so. Record in `verification.yml` exactly which findings were panelled and which were not — a partial panel that reads as complete is worse than none.

5.6. **Apply any Claude Code Security plugin review of the same repo.**

   The plugin is also run as a *scanner* in its own right, archived in sibling trees — `scans/claude-code-security-<model>-<effort>[-adversarial]/<project>/<scan-id>/`. When one exists for the same repo (any commit, not just this `head_sha`), read its `consolidated.md`, `actions.md` and `issues.md` and fold its judgment into this assessment. It is an independent read of the same code by a different method, and the parts that bear on the assessment are worth more than its findings list.

   Four classes of judgment, in descending value:

   | Class | Where | What it does to the assessment |
   | --- | --- | --- |
   | **Threat-model defects** (`TM-n`, `actions.md` §3) | the model itself | **Highest value — apply first.** A disposition that rests on a model claim the plugin proved false against the tree is void. Re-disposition it and record why. Also the reverse: a §-gap the plugin names (no coverage for outbound TLS, PRNG quality, header sanitisation, …) can move a finding from `VALID-HARDENING` to `MODEL-GAP`, because "the model says nothing here" is a gap, not a soft yes. |
   | **Report corrections** (`actions.md` §4) | individual findings | Factual errors in the scan's own text — refuted mechanisms, wrong citations, misnamed vulnerability classes. Feeds the `WITHDRAWN` set and the correction notes. |
   | **Coverage gaps** (`actions.md` §6) | scan scope | Corroborates or refutes this assessment's own coverage statement. Directories assigned to no researcher, categories pruned everywhere, candidate sites never voted on — "no findings there" means *not examined*, and the forward must say so. |
   | **Programme actions** (`actions.md` §6) | the pipeline | May invalidate the **eligibility gate** itself: if the plugin shows the "verified" model contains maintainer-confirmed statements that are false against the code, hard rule 2's gate passed on a model that should not have cleared it. Surface to `frontier-model-preparation-model-verify`; do not silently proceed. |

   **Rules for applying it:**

   - **Verify before you apply.** The plugin's review is another agent's output, not ground truth. Re-read every cited `file:line` against the tree at the relevant commit before you let a judgment change a disposition. A judgment you could not confirm is recorded as *unconfirmed*, not applied.
   - **Never compare finding counts.** The plugin scan is not ASVS-driven (`asvs_level: N/A`) and is usually attack-surface-scoped; a Mythos bundle and a plugin bundle count completely different things. Comparing totals is meaningless and reads as one scanner beating the other.
   - **Check `_filter_drop_log.md` before claiming a miss.** Before recording that the plugin found something Mythos missed, confirm Mythos did not surface and deliberately drop it. The useful output of the cross-read is *what each side found alone*, with the drop log accounted for.
   - **Record the direction and the date.** Both directions happen — the plugin review gets amended by this assessment, and this assessment gets amended by the plugin review. Stamp which way the judgment flowed and when, in `metadata.yml`, or the two documents ping-pong with no audit trail. Never edit an earlier assessment in place: leave it intact and consolidate forward into a new version, exactly as `assessment.md` → `adversarial-review.md` → `assessment-v2.md` did.
   - **Cross-link both ways.** The plugin bundle's `see_also` should point here and this `metadata.yml` should point there, so a reader landing on either finds the other.

5.7. **Re-check the reportable set against the newest commit you hold** (hard rule 14). Always on — it costs a few greps and it is the last gate before the PMC sees anything.

   For every finding you would report (`VALID`, `MODEL-GAP`, and anything the operator is escalating), read the cited code at the **newest** commit available for that repository — which, when scanners ran at different commits, is not the commit the finding was reported at. If the defect is gone, disposition it `FIXED-UPSTREAM`, record the fixing commit, and drop it from the reportable set.

   - Establish ordering first: `git merge-base --is-ancestor <older> <newer>`. If the commits are on divergent branches, say so and re-check both rather than assuming.
   - `git log <older>..<newer> -S '<symbol>' -- <path>` finds the fixing commit cheaply once you know the defect is gone.
   - Keep the original verdict intact. A verdict describes the code at the commit the finding was **scanned** at and stays true; `FIXED-UPSTREAM` is a separate, later fact. Recording both is not a contradiction, and the assessment should say so explicitly so a reader does not "correct" one of them.
   - Report the count in the headline. "Three of twelve already fixed" is useful signal to both the PMC and ASF Tooling about scan currency.

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
- **Claude Code Security plugin** (`claude-security`, user-scope) — used here in two distinct roles, neither of which replaces the model triage:
  - its `claude-security:scan-verifier` agent supplies the step-5.5 truth panel (per-finding `TRUE_POSITIVE` / `FALSE_POSITIVE`, three lenses, code-computed quorum);
  - its *scanner* jobs (`/claude-security` → scan-codebase) produce the sibling `scans/claude-code-security-*/` bundles whose adversarial review is folded in at step 5.6.

  The plugin cannot do this SKILL's job: it has no notion of a threat-model disposition, no `pre-forward-results/` output, and no entrypoint that accepts someone else's scan report. It answers *is this true*; this SKILL answers *is this in scope*.

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
- Firing the step-5.5 truth panel — or, worse, a full plugin scan of the PMC repo — because it seemed thorough. Both are opt-in (hard rule 12); an unrequested panel spends the operator's budget on a decision that was theirs.
- Presenting a partial panel as if the whole bundle were verified. Record what was panelled *and* what was not.
- Comparing a plugin bundle's finding count with a Mythos bundle's. Different methodology, different scoping, usually not ASVS-driven — the counts are not commensurable and quoting them side by side invites a false conclusion.
- Letting a plugin review's judgment change a disposition without re-reading the cited `file:line` yourself. It is another agent's output, not ground truth.

## Provenance

Created when the one-off, gist-based pre-forward assessment (a manual triage of a single scan written to a public gist) was promoted into a repeatable SKILL with a proper home: the team's internal read now lands in `apache/tooling-agents-private/pre-forward-results/`, mirroring the `scans/` archive one-for-one, private and auditable. The forward-to-PMC-verbatim policy is unchanged — this is the team's working note alongside the forward, not a replacement for it.
