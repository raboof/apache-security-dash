<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# Triage reply / forward templates

These Markdown files are the team's boilerplate for the report-triage pipeline.
**`inbox_manager` is the only renderer:** at send time (when the live message,
the operator identity, and the PMC coordinates are all known) it picks the right
template, fills every marker, and **drops any line whose marker is still empty**.

The markers fall into two groups by where their *value* comes from:

1. **Content** - authored by the model during `triage-assess` and stored in the report-cache bundle:
   the free-text fragments `summary.md` / `note.md` / `reason.md` and the model id `model.md`,
   all written with `report-cache put-artifact`,
   plus the `duplicate_ponymail_link` index field set with `report-cache set`.
   `triage-assess` renders nothing; it only supplies these values.
2. **Identity / PMC / infra** - derived by `inbox_manager` from the PMC
   coordinates, the live message, and the operator identity.

Because of the drop rule, a marker is safe to leave unfilled **only** if its
whole line may disappear. Required markers must always have a value.

Markers are written in the templates markdown-escaped as `\<marker>` so they
render literally if something goes wrong; the renderer matches `\<marker>` and
`<marker>`.

## Markers

### Content (value from the `triage-assess` bundle)

| Marker | Templates | Source | Meaning | If unfilled |
| --- | --- | --- | --- | --- |
| `<summary>` | forward, forward-duplicate | `summary.md` | the model's concise PMC summary (finding / code verification / scope assessment) | required |
| `<reason>` | reject | `reason.md` | why the report is out of scope (the model's wording, or the PMC's prior reason for a known non-issue) | required |
| `<model>` | forward, forward-duplicate | `model.md` artifact | the AI model that wrote the summary (for the disclaimer line) | required |
| `<duplicate>` | forward-duplicate | `duplicate_ponymail_link` index field | link to the still-open original report this one duplicates | required for this template |
| `<note>` | receipt, receipt-specialized | `note.md` | optional extra paragraph to the reporter | line dropped |

### Identity / PMC / infra (derived by `inbox_manager` at send)

| Marker | Templates | Meaning | If unfilled |
| --- | --- | --- | --- |
| `<PMC name>` | forward, forward-duplicate, receipt, receipt-specialized | project display name (e.g. "Apache Tomcat") | required |
| `<PMC security address>` | receipt-specialized | the PMC's own `security@<pmc>.apache.org` | required (this template only) |
| `<Reporter name>` | receipt, receipt-specialized, reject | the reporter's display name (from the live message) | required |
| `<Triager full name>` | all | the sender / operator name | required |
| `<link>` | forward, forward-duplicate, receipt, receipt-specialized | the project's human security page (the PMC's `security_model_link`, not the raw `security_model_source` that feeds the assessors) | line dropped |
| `<model link>` | reject | the project's human security page (the PMC's `security_model_link`; kept a distinct marker from `<link>`) | line dropped |
| `<contributing link>` | reject | the project's contribution-guidelines page | line dropped |
| `<dashboard link>` | forward, forward-duplicate | the per-PMC open-reports dashboard URL | line dropped |

The drop rule is uniform: `inbox_manager` fills every infra marker it can,
then removes any line that still contains a `<...>` placeholder. So the four
link markers (`<link>`, `<model link>`, `<contributing link>`,
`<dashboard link>`) and an empty `<note>` simply vanish when there is nothing
to put there.

## Per-template quick reference

- **forward.md** - `<PMC name>`, `<Triager full name>`, `<dashboard link>`, `<model>`, `<link>`, `<summary>`
- **forward-duplicate.md** - `<PMC name>`, `<duplicate>`, `<Triager full name>`, `<dashboard link>`, `<model>`, `<link>`, `<summary>`
- **receipt.md** - `<Reporter name>`, `<note>`, `<PMC name>`, `<link>`, `<Triager full name>`
- **receipt-specialized.md** - `<Reporter name>`, `<PMC name>`, `<PMC security address>`, `<note>`, `<link>`, `<Triager full name>`
- **reject.md** - `<Reporter name>`, `<reason>`, `<model link>`, `<contributing link>`, `<Triager full name>`

## Notes

- **`reject.md` and the drop rule.** `<model link>` sits on its own line
  ("See the [security model](\<model link>) for more information."), kept
  separate from the lead-in sentence on purpose. A PMC that has no
  threat-model link on record simply loses that one line; the lead-in
  ("based on the project's security model, this behaviour does not appear to
  be a vulnerability:") and the `<reason>` block still read correctly. Keep
  any future `<model link>` reference on a droppable line of its own.
- **Adding a marker.** Decide where its *value* comes from:
  model-authored text -> a bundle artifact or index field that `triage-assess` writes through the `report-cache` CLI
  (and that `inbox_manager` reads in `fill_*_template`);
  anything derived from the PMC, the live message, or the operator -> add it to `fill_markers`.
  Either way `inbox_manager` does the substitution.
  Put it on its own line if it should disappear when empty.
