<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# Glasswing scans — archive

This directory is the canonical archive of **Glasswing security
scan reports** produced for ASF projects. Each scan is the
markdown output of one Glasswing run against one Apache repository
at one specific commit, after the ASF Security team's
slop-filter / pre-review pass.

Scans live here because:

- the Security team needs a **single audit trail** of what got
  scanned, when, against which commit, and with which model —
  rather than reconstructing the history from email threads;
- when the same project is **re-scanned** (which happens often —
  after PMC fixes findings, after a new release, after threat-
  model updates that should suppress prior false-positives), the
  diff between two scan files is the answer to "what did we miss
  last time" and "what did we add this time" — the files are
  plain markdown, so `diff` / GitHub's blob compare just works;
- the `apache/security` repo is private, which is the correct
  trust level for un-disclosed vulnerability candidates (see
  "Confidentiality" below).

The PMC itself does **not** need access to this repo to use a
scan reference — see "Identifiers PMCs can cite" below.

This directory ships **empty** initially — it's seeded by this
README and grows scan-by-scan.

## Layout

```
scans/
├── README.md                                                          # this file
└── <project>/<repo>/<project>-<repo>-<YYYY-MM-DD>-<short-sha>.md
```

The path resolves with **three required segments after `scans/`**:

| Segment | Meaning | Example |
| --- | --- | --- |
| `<project>` | Lowercase PMC slug (the part of `private@<x>.apache.org`). | `lucene`, `solr`, `airflow`, `kafka` |
| `<repo>` | Lowercase GitHub repository name *within `apache/`* that was scanned. | `lucene`, `solr`, `airflow`, `airflow-site` |
| `<project>-<repo>-<YYYY-MM-DD>-<short-sha>.md` | Filename: project slug + repo name + ISO date (UTC) of scan completion + first 8 hex chars of the head commit SHA. | `lucene-lucene-2026-05-13-a95e678d.md` |

The hash lives **in the filename, not in a folder name**, so a
single `<project>/<repo>/` directory holds the full history of
scans for that repo, sorted chronologically by filename. `ls
scans/<project>/<repo>/` is the audit trail.

### Identifiers PMCs can cite

The project and repo segments are duplicated inside the filename
on purpose: it lets a PMC reference a scan **by filename alone**
(without the directory path) and still have a globally unique
identifier within the archive. That matters because:

- the PMC does **not** have access to this private repo, so
  citing a path here would be confusing;
- the filename is unique across the whole archive
  (`<project>-<repo>-<YYYY-MM-DD>-<short-sha>` collides only if
  the same repo is scanned twice in the same UTC day against the
  same 8-char SHA prefix — vanishingly rare; resolve with a `-N`
  suffix per the worked examples below);
- when the Security team forwards a scan's findings to a PMC,
  the email needs only the filename, e.g. *"see scan
  `lucene-lucene-2026-05-13-a95e678d`"*, and the PMC can refer
  to that token in their own private issue tracker without
  pulling anything from this repo.

### Worked examples

| Repo scanned | Path |
| --- | --- |
| `apache/lucene` at SHA `a95e678d3c43c71e9f0e8628293c055eb8076283`, scanned 2026-05-13 | `scans/lucene/lucene/lucene-lucene-2026-05-13-a95e678d.md` |
| `apache/airflow` at SHA `4b1995d5d6...`, scanned 2026-05-13 | `scans/airflow/airflow/airflow-airflow-2026-05-13-4b1995d5.md` |
| `apache/airflow-site` at SHA `...`, scanned 2026-06-01 | `scans/airflow/airflow-site/airflow-airflow-site-2026-06-01-<short-sha>.md` |
| `apache/solr` at SHA `...`, second scan within the same day against the same SHA prefix (rare — use a `-N` suffix on the filename) | `scans/solr/solr/solr-solr-2026-05-13-<sha>-2.md` |

### Why `<YYYY-MM-DD>` and `<short-sha>` instead of full SHA

- The date prefix makes scans **sortable** by `ls`. The Security
  team triages a repo's scans newest-first; alphabetic sort on
  filename = chronological without any extra tooling.
- The 8-character short SHA is unique within any one Apache
  project's repo history at human scale (collision probability
  is negligible) and is much easier to eyeball than a 40-character
  full SHA.
- The header of the scan file itself records the **full** SHA,
  so reproducibility doesn't depend on the filename being lossless.

### Sidecar files (raw JSON, attachments)

If a scan run produces auxiliary artifacts (raw Glasswing JSON
output, a CSV of findings, attached screenshots, etc.), commit
them next to the markdown file with the **same prefix** and an
appropriate extension:

```
scans/<project>/<repo>/<project>-<repo>-2026-05-13-a95e678d.md       ← canonical, human-readable
scans/<project>/<repo>/<project>-<repo>-2026-05-13-a95e678d.json     ← raw Glasswing output
scans/<project>/<repo>/<project>-<repo>-2026-05-13-a95e678d.notes.md ← Security team's pre-review notes
```

`ls scans/<project>/<repo>/<project>-<repo>-2026-05-13-a95e678d*`
then returns the complete record of that scan run.

## What goes in each scan file

The scan markdown is the artifact Glasswing produces, after the
ASF Security team's pre-review pass. Each file MUST contain, at
the top, a metadata block in the shape below — agents and humans
both rely on this header to triage:

```markdown
---
project:         lucene
repo:            apache/lucene
head_sha:        a95e678d3c43c71e9f0e8628293c055eb8076283
scan_date:       2026-05-13T14:21:00Z
glasswing_model: glasswing-v<NN>-<YYYY-MM-DD>
threat_model:    https://github.com/apache/lucene/blob/<sha>/SECURITY.md
findings_total:  <N>
findings_after_slop_filter: <M>
pre_reviewed_by: <asf-security-team-member>@apache.org
pre_review_date: 2026-05-13
---
```

Followed by the findings. Each finding under its own heading,
including:

- the affected file(s) and line range(s),
- the security property violated (cite the threat-model section
  by number),
- a short reproducer (where feasible),
- a severity hint,
- the disposition decided by the Security team's pre-review
  (`forward-to-PMC`, `slop-rejected`, `duplicate-of-finding-<N>`,
  etc.).

The complete Glasswing scan output (pre-filter) goes in the
`.json` sidecar so the pre-review is auditable later.

### Markdown is the format on purpose

The format is deliberately plain markdown — both human- and
agent-readable — without a rigid schema beyond the YAML
front-matter above. The same shape is used by other ASF
agentic-security artifacts (ASVS findings, Mythos scan
output, etc.), and agents read all of them without needing a
strict schema declaration. The benefit: **two scan files
against the same repo at different commits diff cleanly with
`diff` or GitHub's blob-compare view**, which is the primary
way the Security team and PMCs answer "what's new vs last scan,
what got fixed, what stayed."

## Workflow (end-to-end)

1. **PMC opts in.** The PMC sends a request per the announcement
   procedure (see [`glasswing-scan-response`](../.github/skills/glasswing-scan-response/SKILL.md)
   skill for the response template).
2. **Threat model lands** — *only if the PMC asks for one*.
   Most ASF projects already have a security/threat model in
   their `SECURITY.md` (in-repo) or as an HTML page on their
   project website (cf.
   [`security.apache.org/projects/`](https://security.apache.org/projects/));
   the Security team's default is to use what the PMC already
   has. When the PMC explicitly asks the Security team to draft
   or update one, the producer runs the
   [`threat-model-producer`](../.github/skills/threat-model-producer/SKILL.md)
   skill against the public artifacts and submits a PR to the
   project's repo. **Canonical location for the model is
   `SECURITY.md`** (the standard most projects already use); if
   the document grows large enough that splitting it is useful,
   keep `SECURITY.md` as the entry point and link out to a
   longer doc from there. The project's `AGENTS.md` (per
   [agents.md](https://agents.md/)'s "Security considerations"
   section) carries a one-line pointer to `SECURITY.md` so
   scanners and other agents find the model deterministically.
   The PMC merges the PR.
2a. **Discoverability gate (hard requirement).** Before the
    scan is queued, the Security team's own agent runs a
    pre-flight pass against the project's repo at the
    designated commit and confirms it can locate the threat
    model via `AGENTS.md` → `SECURITY.md` (or whichever
    artifact `SECURITY.md` links to). **If the agent cannot
    find the model, the scan is refused**, and the Security
    team responds to the PMC asking them to make the model
    reachable through this discovery path before re-requesting.
    The reason: without a model the scan produces a high false-
    positive rate that the PMC cannot reasonably triage, and
    rejecting a noise-heavy scan after the fact wastes more
    cycles than refusing upfront. We don't want to put PMCs in
    that position. This gate is non-negotiable — even for
    projects the Security team already knows well, the agent
    must be able to *mechanically* discover the model so that
    re-scans and future re-runs by other Security-team members
    don't depend on tribal knowledge.
3. **Scan runs.** Glasswing scans the repo at HEAD (or at a
   PMC-designated tag), reading the threat model from
   `SECURITY.md` (via `AGENTS.md`'s pointer).
4. **Pre-review.** The Security team filters slop (prompt-injection
   echoes, false positives obviously discharged by the threat
   model, duplicates of prior findings).
5. **Commit to this folder.** The pre-reviewed markdown + raw
   JSON go in at the path described above. Each commit covers
   one scan run.
6. **Forward to PMC.** The Security team emails the surviving
   findings to `security@<project>.apache.org` (or `private@<pmc>`
   if no project-level security alias exists), citing the scan's
   filename so the PMC has a stable identifier to refer back to.
7. **PMC triages**, files CVEs as needed via their normal
   coordinated-disclosure path, lands fixes, ships a release.
8. **Loop back.** The PMC tells the Security team how many
   findings were real vs false-positive vs duplicates. That
   feedback shapes the project's threat-model `SECURITY.md`
   (typically the "known non-findings" section) before the next
   scan, breaking the false-positive spiral.

### Where the threat model lives — quick reference

The Security team does **not** invent a new file format here.
Projects already commonly use `SECURITY.md` for their security
policy and threat-model statements. The convention this archive
expects:

| File | Purpose |
| --- | --- |
| `SECURITY.md` (in the project's own repo) | Canonical threat-model + disclosure-process document. May embed the model directly, or link out to a longer doc; either is fine. Widely adopted; most ASF projects already have one or a website equivalent. |
| `AGENTS.md` (in the project's own repo) | Standard agent-discovery file per [agents.md](https://agents.md/). Its "Security considerations" section (which the agents.md standard explicitly calls out as a popular section to include) holds a one-line pointer to `SECURITY.md` so scanners locate the threat model without guessing. |

Nothing new is invented; the only request to a participating
PMC is that *whatever they already use* is reachable from the
two files above so an automated scan can find it.

## Confidentiality

This repo is **private** to the ASF Security team. Findings
committed here are *un-disclosed vulnerability candidates* until
the PMC publishes them through its normal disclosure process.

- **Do not link from public bug trackers** to files in this
  archive without consulting the affected PMC first. Even a
  filename hints at scan timing.
- **Do not paste scan content into AI-assisted code editors that
  send context to a third-party model**, unless the model is
  one the ASF Security team has explicitly approved for handling
  pre-disclosure findings.
- **Do not delete** scan files even after the corresponding
  vulnerabilities have been published. The history of which
  scan caught what (and when) is valuable for future
  retro-triage.

If a scan was performed against a repository that is itself
private (an in-development branch, a not-yet-public fork), say
so explicitly in the metadata header (`source_visibility: private`)
and double-check the commit message does not leak excerpts.

## Adding a new scan — checklist

- [ ] Path matches `scans/<project>/<repo>/<project>-<repo>-<YYYY-MM-DD>-<short-sha>.md`.
- [ ] Metadata header is complete (project, repo, head_sha,
      scan_date, glasswing_model, threat_model URL,
      findings_total, findings_after_slop_filter,
      pre_reviewed_by, pre_review_date).
- [ ] Findings reference threat-model sections by number where
      possible.
- [ ] Sidecar `.json` (raw output) committed alongside.
- [ ] Commit message starts with `[scan] <project>/<repo>` for
      consistent search (`git log --grep '\[scan\]'`).
- [ ] No PMC member name, reporter name, or other identifying
      detail in commit metadata unless they're an ASF Security
      team member acting in that capacity.

## Relationship to the SKILLs directory

- [`.github/skills/glasswing-scan-response/`](../.github/skills/glasswing-scan-response/SKILL.md)
  — drafts replies to PMC inquiries that get the workflow
  rolling.
- [`.github/skills/threat-model-producer/`](../.github/skills/threat-model-producer/SKILL.md)
  — bootstraps the project's threat model when (and only when)
  the PMC explicitly asks for one. The default assumption is
  that the project already has a `SECURITY.md` (or website
  equivalent) and the scan uses that.

This `scans/` directory is the output side; the SKILLs are the
input side.
