---
name: triage-assess
description: >-
  Assess filed security reports against the project's threat model and source,
  then draft the right response. For each filed report in report-cache, look up
  the PMC: if it is a specialized team (its own security contact in
  project-coordinates.json) the Security team only TRACKS it (no drafts);
  otherwise assess whether the report is a real in-scope issue. If it is a
  high-confidence false positive or hardening suggestion, draft a non-assertive
  note to the reporter (they may take it to the public tracker). If it is
  plausible, draft a forward to the PMC (templates/forward.md) plus a receipt
  to the reporter (templates/receipt.md). The final non-issue / hardening / CVE
  call always belongs to the PMC, so drafts never use assertive language and
  the skill never sends. A deterministic helper (draft.py) fills the templates
  and stamps the bundle's report.md front-matter; the model supplies the
  judgement, summary, and reply text. Use whenever the team says "assess the
  cached reports", "triage report
  X against its threat model", "draft the forwards/replies", or after filing to
  work through report-cache. Project source is read from a --workspace dir
  (default ~/workspace/<pmc>).
---

# triage-assess SKILL

The **assessment + drafting** phase of the report-triage pipeline. After
`triage-populate-cache` sweeps, filters, and files reports under
`report-cache/<date>/<pmc>/<keywords>/`, this SKILL works through them: decide
whether each is the Security team's to act on, assess plausibility against the
project's threat model, and draft the response for a human to review and send.

See `triage-populate-cache/SKILL.md` for the cache layout + the `report.md`
front-matter schema. This SKILL writes drafts into the bundle and advances
the front-matter `status`; it leaves the provenance block alone and **never
sends**.

## Hard rules

1. **The PMC owns the verdict.** Whether something is a non-issue, hardening,
   or a CVE is the PMC's decision, never ours. Drafts to the reporter use
   tentative, non-assertive language ("this appears to be...", "the PMC may
   consider..."), never "this is not a vulnerability".
2. **Track only when the PMC's own list was the addressee.** A report is the
   PMC's to handle (no triage) **only if it was sent `To: security@<pmc>`**
   (its own security list). A report that reached the central
   `security@apache.org` list needs triage and a forward **even if the PMC runs
   its own security team** — the central list is where we add value. This is a
   recipient test (the bundle's `to` header / `pmc_candidates`), NOT the
   `specialized` flag. `draft.py track` enforces it and refuses a
   central-addressed report.
3. **Bias to forwarding.** Only draft a push-back reply when the report is a
   false positive or pure hardening **with high confidence**. Anything
   plausible, or where confidence is not high, gets forwarded to the PMC (they
   decide). When in doubt, forward.
4. **Drafts only.** Output is Markdown in the bundle for a human to review and
   send; the SKILL never emails anyone.

## Inputs

- **`coordinates.yaml`** (in this skill dir): per-PMC `specialized` flag,
  `contact`, and `threat_model` link. Generated from apache/security-site's
  `project-coordinates.json` by `build_coordinates.py`; re-run it to refresh.
  A PMC absent from the file is treated as central triage with no known threat
  model. The `specialized` flag does **not** gate triage (rule 2); on a
  *forward* it picks the recipient address (the PMC's own `contact` vs
  `private@<pmc>`) and the receipt variant (see Draft).
- **Project source** under `--workspace` (default `~/workspace`): the SKILL
  reads `<workspace>/<pmc>` to check the report against real code. If that
  checkout is absent, assess from the report + threat model alone and say so in
  the summary (do not auto-clone).
- **Templates** `templates/forward.md`, `templates/receipt.md`, and
  `templates/receipt-specialized.md` (repo root).

## Workflow

For each filed bundle (`status: filed`) under `report-cache/`:

1. **Classify by recipient** (the bundle's `to` header).
   - `To: security@<pmc>.apache.org` (its own list) -> `draft.py track <id>`.
     Done (status `tracked`); the PMC already has it.
   - `To: security@apache.org` (central) -> assess (below), even for a PMC that
     runs its own team. `draft.py track` will refuse these.
2. **Assess.** Read the bundle's `report.md` (+ `attachments/`). Pull the
   project's threat model from the `threat_model` link (WebFetch it; if null,
   fall back to the project's `SECURITY.md` / general ASF expectations and note
   the gap). Read the relevant code under `<workspace>/<pmc>` if present.
   Judge: is the reported behaviour in scope and plausibly a vulnerability, or
   a false positive / hardening item?
3. **Draft.**
   - **High-confidence false positive or hardening** -> write your
     non-assertive note to a temp file and run
     `draft.py reply <id> --body-file <file> [--kind false-positive|hardening]`.
     Write only the message body: tentatively, why it looks out of scope or
     like hardening (cite the specific code path / call when you can), the
     app-side mitigation if relevant, and an explicit invitation for the
     reporter's reasoning if they see it differently ("we are open to your
     arguments...") rather than asserting a final verdict; note they are
     welcome to raise hardening ideas on the project's public issue tracker.
     **Exception:** when the project's own threat model explicitly documents
     the reported behaviour as expected / out of scope, cite that statement
     directly — that is a high-confidence false positive and the push-back can
     be correspondingly firm (still grounded in the project's words, not our
     opinion). `draft.py reply` classifies the report by prefixing its tag with
     `zzz-non-issue/` (which sorts it out of the active queue and *replaces* a
     `wf: non-issue-feedback` marker — a report is never both), and wraps the
     body with `Hi <reporter>,` and a `Best regards, <triager>` sign-off into
     `draft-reply.md`.
   - **Plausible (or not high-confidence)** -> write a concise PMC summary to a
     temp file (what was reported, affected component, why it is plausible,
     any caveats) and run `draft.py forward <id> --summary-file <file>`. It
     renders `templates/forward.md` -> `draft-forward.md` (with the AI-model
     disclaimer) and a receipt -> `draft-receipt.md`. For a `specialized` PMC
     the forward is addressed to its own security list and the receipt uses
     `templates/receipt-specialized.md`, which tells the reporter we forwarded
     it and points them to the project's own address (and
     `https://security.apache.org/projects/`) for direct follow-up; otherwise
     it goes to `private@<pmc>` with the standard `templates/receipt.md`.
     Add `--reporter-note <file>` to insert a paragraph into the receipt (e.g.
     a "this is probably not a security issue, but we forwarded it" hint when
     you lean non-issue but still want the PMC's call), and `--wf <marker>` to
     stamp the tag.
4. **Review.** Open the draft(s); the leading `To:`/`Subject:` comment is a
   hint for whoever sends them.

## Helper commands

```bash
A=.github/skills/triage-assess
$A/build_coordinates.py                       # (re)generate coordinates.yaml
$A/draft.py track   <id>
$A/draft.py forward <id> --summary-file SUM.md  [--reporter-note NOTE.md] [--wf MARKER] [--triager "Name"] [--model "..."]
$A/draft.py reply   <id> --body-file REPLY.md   [--kind hardening] [--triager "Name"]
```

`reply` always classifies the report `zzz-non-issue/` (no `wf` marker).
`forward`'s `--wf` is one of `reporter`, `cve-allocation`, `non-issue-docs`
(`non-issue-feedback` is the `zzz-non-issue/` case, handled by `reply`); it
appends `wf <marker>` to the tag and records `wf` in the front-matter.

`<id>` is the bundle's Ponymail id or any unique prefix. `--triager` defaults
to `git config user.name`; `--model` defaults to the running model and fills
the forward template's "generated by AI using ..." disclaimer.

## Status values this SKILL sets

- `tracked` — specialized PMC; the Security team only tracks it.
- `drafted-forward` — `draft-forward.md` + `draft-receipt.md` written.
- `drafted-reply` — `draft-reply.md` written (false-positive / hardening).

`handled` stays `false` until a human actually sends the drafted mail.

## Scope

- Reads `report-cache/`, `coordinates.yaml`, templates, and project source.
- May WebFetch threat-model links on `*.apache.org` / `github.com`.
- Writes only draft Markdown + `report.md` front-matter status inside the bundle.
- Never sends, never edits the provenance block, never touches Ponymail.
