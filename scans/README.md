<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# Glasswing scans — archive

This directory is the canonical archive of **Glasswing security
scan reports** produced for ASF projects. Each scan is the
markdown output of one Glasswing run against one Apache repository
at one specific commit, after the ASF Security team's
slop-filter / pre-review pass.

Scans live here because:

- the PMC needs a stable, citeable URL when triaging findings
  (an issue tracker comment can refer to the scan file at this
  exact path);
- when the same project is re-scanned, the diff between two
  scan files is the answer to "what did we miss last time";
- the `apache/security` repo is private, which is the correct
  trust level for un-disclosed vulnerability candidates (see
  "Confidentiality" below).

This directory ships **empty** initially — it's seeded by this
README and grows scan-by-scan.

## Layout

```
scans/
├── README.md                                  # this file
└── <project>/<repo>/<YYYY-MM-DD>-<short-sha>.md
```

The path resolves with **three required segments after `scans/`**:

| Segment | Meaning | Example |
| --- | --- | --- |
| `<project>` | Lowercase PMC slug (the part of `private@<x>.apache.org`). | `lucene`, `solr`, `airflow`, `kafka` |
| `<repo>` | Lowercase GitHub repository name *within `apache/`* that was scanned. | `lucene`, `solr`, `airflow`, `airflow-site` |
| `<YYYY-MM-DD>-<short-sha>.md` | Filename: ISO date (UTC) of scan completion, then a literal `-`, then the first 8 hex chars of the head commit SHA the scan ran against. | `2026-05-13-a95e678d.md` |

The hash lives **in the filename, not in a folder name**, so a
single `<project>/<repo>/` directory holds the full history of
scans for that repo, sorted chronologically by filename. `ls
scans/<project>/<repo>/` is the audit trail.

### Worked examples

| Repo scanned | Path |
| --- | --- |
| `apache/lucene` at SHA `a95e678d3c43c71e9f0e8628293c055eb8076283`, scanned 2026-05-13 | `scans/lucene/lucene/2026-05-13-a95e678d.md` |
| `apache/airflow` at SHA `4b1995d5d6...`, scanned 2026-05-13 | `scans/airflow/airflow/2026-05-13-4b1995d5.md` |
| `apache/airflow-site` at SHA `...`, scanned 2026-06-01 | `scans/airflow/airflow-site/2026-06-01-<short-sha>.md` |
| `apache/solr` at SHA `...`, second scan within the same day (rare — use a `-N` suffix on the SHA segment) | `scans/solr/solr/2026-05-13-<sha>-2.md` |

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
scans/<project>/<repo>/2026-05-13-a95e678d.md       ← canonical, human-readable
scans/<project>/<repo>/2026-05-13-a95e678d.json     ← raw Glasswing output
scans/<project>/<repo>/2026-05-13-a95e678d.notes.md ← Security team's pre-review notes
```

`ls scans/<project>/<repo>/2026-05-13-a95e678d*` then returns the
complete record of that scan run.

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
threat_model:    https://github.com/apache/lucene/blob/<sha>/THREAT-MODEL.md
findings_total:  <N>
findings_after_slop_filter: <M>
pre_reviewed_by: <asf-security-team-member>@apache.org
pre_review_date: 2026-05-13
---
```

Followed by the findings. Each finding under its own heading,
including:

- the affected file(s) and line range(s),
- the security property violated (cite the threat model section
  by number),
- a short reproducer (where feasible),
- a severity hint,
- the disposition decided by the Security team's pre-review
  (`forward-to-PMC`, `slop-rejected`, `duplicate-of-finding-<N>`,
  etc.).

The complete Glasswing scan output (pre-filter) goes in the
`.json` sidecar so the pre-review is auditable later.

## Workflow (end-to-end)

1. **PMC opts in.** The PMC sends a request per the announcement
   procedure (see [`glasswing-scan-response`](../.github/skills/glasswing-scan-response/SKILL.md)
   skill for the response template).
2. **Threat model lands.** The Security team drafts (or the PMC
   confirms) a `THREAT-MODEL.md` for the project. The PR merges
   to the project's repo, with an `AGENTS.md` linking to it.
3. **Scan runs.** Glasswing scans the repo at HEAD (or at a
   PMC-designated tag).
4. **Pre-review.** The Security team filters slop (prompt-injection
   echoes, false positives obviously discharged by the threat
   model, duplicates of prior findings).
5. **Commit to this folder.** The pre-reviewed markdown + raw
   JSON go in at the path described above. Each commit covers
   one scan run.
6. **Forward to PMC.** The Security team emails the surviving
   findings to `security@<project>.apache.org` referencing this
   archive path so the PMC can cite a stable URL when triaging.
7. **PMC triages**, files CVEs as needed via their normal
   coordinated-disclosure path, lands fixes, ships a release.
8. **Loop back.** The PMC tells the Security team how many
   findings were real vs false-positive vs duplicates. That
   feedback shapes the threat model's §4.11a "known non-findings"
   section before the next scan, breaking the false-positive
   spiral.

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

- [ ] Path matches `scans/<project>/<repo>/<YYYY-MM-DD>-<short-sha>.md`.
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
  — bootstraps the project's threat model that the scan reads
  against.

This `scans/` directory is the output side; the SKILLs are the
input side.
