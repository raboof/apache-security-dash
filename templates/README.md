<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# Triage reply / forward templates

These Markdown files are the team's boilerplate for the `triage-assess` SKILL.
Each is filled in **two stages**:

1. **`draft.py`** (triage-assess) picks the right template, fills the
   *content* markers the model authored, and saves the result as
   `draft-forward.md` / `draft-receipt.md` / `draft-reply.md` inside the
   report-cache bundle.
2. **`inbox_manager`** fills the remaining *identity / PMC / infra* markers at
   send time (when the live message, the operator identity, and the PMC
   coordinates are all known), then **drops any line whose marker is still
   empty**.

Because of step 2's drop rule, a marker is safe to leave unfilled **only** if
its whole line may disappear. Required markers must always be fillable at the
stage that owns them.

Markers are written in the templates markdown-escaped as `\<marker>` so they
render literally if something goes wrong; both fillers match `\<marker>` and
`<marker>`.

## Markers

### Filled by `draft.py` (content)

| Marker | Templates | Meaning | If unfilled |
| --- | --- | --- | --- |
| `<summary>` | forward, forward-duplicate | the model's concise PMC summary (finding / code verification / scope assessment) | required |
| `<reason>` | reject | why the report is out of scope (the model's wording, or the PMC's prior reason for a known non-issue) | required |
| `<model>` | forward, forward-duplicate | the AI model that wrote the summary (for the disclaimer line) | required |
| `<duplicate>` | forward-duplicate | link to the still-open original report this one duplicates | required for this template |
| `<note>` | receipt, receipt-specialized | optional extra paragraph to the reporter | line dropped by `inbox_manager` |

### Filled by `inbox_manager` (identity / PMC / infra, at send)

| Marker | Templates | Meaning | If unfilled |
| --- | --- | --- | --- |
| `<PMC name>` | forward, forward-duplicate, receipt, receipt-specialized | project display name (e.g. "Apache Tomcat") | required |
| `<PMC security address>` | receipt-specialized | the PMC's own `security@<pmc>.apache.org` | required (this template only) |
| `<Reporter name>` | receipt, receipt-specialized, reject | the reporter's display name (from the live message) | required |
| `<Triager full name>` | all | the sender / operator name | required |
| `<link>` | forward, forward-duplicate, receipt, receipt-specialized | the project's threat-model page (the `pmc-security-info` `threat_model`) | line dropped |
| `<model link>` | reject | the project's threat-model page (kept a distinct marker from `<link>`) | line dropped |
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
- **Adding a marker.** Decide who owns it: model-authored text -> `draft.py`;
  anything derived from the PMC, the live message, or the operator ->
  `inbox_manager`. Put it on its own line if it should disappear when empty.
