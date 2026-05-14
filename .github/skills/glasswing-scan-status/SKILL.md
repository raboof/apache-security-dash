---
name: glasswing-scan-status
description: Summarize the current status of the ASF Security team's Glasswing (a.k.a. Mythos) scan-outreach effort by reading the shared Google Sheet that Piotr Karwasz maintains. Reports which PMCs have requested scans, who the named contacts are, which projects have a Security Model documented, where unmapped/high-criticality repos sit, and what's outstanding. Use whenever someone asks "where do we stand on Glasswing scans", "how many PMCs have signed up", "what's the status of project X in the tracker", or "give me a scan-program rollup". Reads only — never writes to the sheet.
---

# Glasswing scan-status SKILL

Read-only reporting skill for the Glasswing / Mythos scan outreach tracker.
The deliverable is a markdown summary the user can paste into a
status update, a private@security@apache.org note, or a meeting
agenda. The skill never writes back to the sheet.

## Data source

The tracker is a Google Sheet titled `Mythos scan`, owned by
Piotr Karwasz. "Mythos" is Piotr's internal name for the same
effort the ASF Security team announces externally as "Glasswing"
— the two terms refer to the same scan program and the same
tracker. The skill keeps both names so it stays discoverable
either way.

**The sheet's file ID and view URL are not embedded in this
SKILL.** They live in the user's Claude reference memory, in an
entry named `mythos-tracker` (see `MEMORY.md` →
`mythos-tracker.md` under the user's per-project memory
directory, typically
`~/.claude/projects/<project>/memory/mythos-tracker.md`). This
keeps the coordination URL out of the public `apache/security`
repo. A Security-team member running the skill for the first
time should add the same memory entry to their own profile — ask
Jarek (or whoever currently owns the tracker) for the file ID,
then save it as a `type: reference` memory under the name
`mythos-tracker`.

Read the sheet with the Google Drive MCP tool
`mcp__claude_ai_Google_Drive__read_file_content` against the
file ID from memory. The tool returns a markdown-table rendering
of the three sheets concatenated in order. Get the last-modified
timestamp via `mcp__claude_ai_Google_Drive__get_file_metadata`
on the same file ID.

### Sheet layout

The workbook has up to four sheets, in order:

1. **README** — short prose describing the workbook and its data
   sources (Apache Whimsy `committee-info.json` for the PMC list,
   the github.com/orgs/apache scrape for repos, the OSSF
   `criticality_score` 2025-07-25 snapshot for scores). Useful
   for stating provenance in the summary; otherwise informational.

2. **PMCs** (~210 rows) — one row per Apache PMC. Columns:

   | Column | Meaning |
   | --- | --- |
   | `PMC Name` | Full name, e.g. `Apache Logging Services`. |
   | `PMC Slug` | Short identifier used as the join key on the repos sheet, e.g. `logging`. |
   | `Scan Requested` | `Yes` if the PMC has formally opted in via the `[GLASSWING]` request flow; blank otherwise. |
   | `Date Requested` | Date the PMC sent the `[GLASSWING]` request (or otherwise formally opted in). Blank if not yet requested. Used for measuring backlog age. |
   | `Date Scan Received` | Date the PMC received the scan-result markdown back from the Security team. Blank if the scan hasn't completed yet. The gap between `Date Requested` and `Date Scan Received` is the turnaround. |
   | `Status` | Free-form short text describing the current state — e.g. `awaiting threat model`, `scan queued`, `report under PMC review`, `findings triaged`, `closed`. The skill treats this as opaque text in the summary; it doesn't try to parse a state machine out of it. |
   | `Contact Person` | Primary PMC contact — name + `@apache.org` address. |
   | `Backup contact` | Backup PMC contact, same shape. |
   | `Security Model` | Free-text name of the threat model the PMC has agreed to be scanned against (e.g. `Logging Services Security Model`). Blank if the PMC has not yet supplied or accepted a model. |
   | `Notes` | Free-text. |

   The three date/status columns (`Date Requested`,
   `Date Scan Received`, `Status`) are recent additions to the
   workbook. If they're absent in a fetched copy (older snapshot,
   or Piotr hasn't merged the column-add yet), the skill should
   gracefully degrade: skip the turnaround calculation and the
   status-bucket roll-up, and surface a one-line note that those
   columns are missing rather than failing.

3. **Repositories** (~3,107 rows) — one row per public repo in
   `github.com/orgs/apache`. Columns:

   | Column | Meaning |
   | --- | --- |
   | `Repository URL` | `https://github.com/apache/<repo>`. |
   | `Repository Name` | Repo slug. |
   | `Security model` | Inherited from the owning PMC's `Security Model` cell. |
   | `PMC Slug` | Owning PMC's slug, or the literal `(unmapped)` for sandbox / retired / non-PMC repos. |
   | `PMC Agreed` | `Yes` when the PMC has agreed to a scan covering this repo; blank otherwise. |
   | `GitHub Stars` | Star count, with commas. |
   | `Criticality Score (%)` | OSSF score formatted as percent. 669 of 3,107 repos have a score; the rest blank. |
   | `Primary Language` | GitHub-detected primary language; sometimes blank. |

4. **Canned Responses** (variable rows) — one row per reusable
   answer fragment. Created lazily on first use by the
   `glasswing-scan-update` SKILL's `init-canned-tab` helper.
   Columns:

   | Column | Meaning |
   | --- | --- |
   | `Date Added` | `YYYY-MM-DD` the entry was appended. |
   | `Topic` | One-word tag (e.g. `framework`, `scope`, `tooling`, `roster`, `process`, `discoverability`). Groups entries for human browsing. |
   | `Question pattern` | One-line description of when this answer applies (e.g. "asks which threat-modeling framework we expect — STRIDE / LINDDUN / PASTA"). |
   | `Response` | The canned reply text. May be multi-paragraph markdown; reuse verbatim or lightly adapt for register. |
   | `Author` | Who wrote the entry — `@apache.org` address or "ASF Security team". |
   | `Notes` | Caveats — when this answer applies, when to NOT reuse it, what to swap in for thread specifics. |

   This sheet is the source of truth for canned answers. The
   `glasswing-scan-response` SKILL consults it before drafting
   any reply and appends new entries (via
   `glasswing-scan-update`) after the user approves a novel
   response. Older snapshots of the workbook (from before
   `init-canned-tab` was first run) will not have this sheet —
   the response SKILL falls back to its in-SKILL fragments in
   that case.

## When to invoke

- A team-mate or Jarek asks for a rollup: "how many PMCs have
  signed up?", "list the projects we're waiting on", "what does
  the Glasswing tracker look like right now?".
- A PMC contact asks where their project sits in the queue and
  Jarek needs to look up the row.
- Drafting a status note to `security@apache.org` or a quarterly
  Foundation report about the program's reach.

Skip this skill when the user is asking about a *finding* from a
scan that already ran — that's a different artefact (the scan
output markdown), not the outreach tracker.

## Procedure

1. **Resolve the sheet ID from memory.** Look up the
   `mythos-tracker` entry in user-scope reference memory and
   extract the `File ID`. If the entry is missing, ask the user
   for the spreadsheet URL once, save it as a new
   `mythos-tracker` reference memory, then continue. Never
   inline the ID in this SKILL or in commit-bound files.

2. **Fetch the sheet.** Call
   `mcp__claude_ai_Google_Drive__read_file_content` with the
   file ID from memory. The response is one long markdown
   document — the README sheet first, then PMCs, then
   Repositories. Sheets are separated by blank lines and a
   fresh header row. Also call
   `mcp__claude_ai_Google_Drive__get_file_metadata` once to grab
   `modifiedTime` and `viewUrl` — both are used in the summary
   footer.

3. **Parse the three sheets.** Split on the header rows
   (`| PMC Name | PMC Slug | ...` for PMCs,
   `| Repository URL | Repository Name | ...` for Repositories).
   Treat each remaining markdown table row as one record.
   Cells containing the literal `\<` / `\>` are Markdown-escaped
   email brackets — keep them when reproducing contact names,
   but strip when extracting a bare email.

4. **Compute the summary.** At minimum:
   - **Top-line counts**: total PMCs, PMCs with `Scan Requested =
     Yes`, PMCs with a non-empty `Security Model`, PMCs with a
     primary contact filled in, PMCs whose `Date Scan Received`
     is non-empty (i.e. scan completed).
   - **Active engagements**: for every PMC where
     `Scan Requested = Yes`, list `PMC Name`, primary contact,
     `Security Model` presence, `Date Requested`,
     `Date Scan Received` (or `—` if blank), and `Status`. Flag
     rows where the scan is requested but no model is yet
     documented — that's the work the Security team has next.
   - **Turnaround**: for PMCs where both `Date Requested` and
     `Date Scan Received` are filled, compute the gap in days
     and show the min / median / max across the cohort. Skip
     this block silently if no row has both dates set.
   - **Backlog age**: for PMCs with `Date Requested` filled but
     `Date Scan Received` blank, sort by `Date Requested`
     ascending and show the top few — these are the longest-
     waiting requests. Use this as an internal pressure signal,
     not as something to paste into a PMC-facing reply.
   - **Status bucket roll-up**: a small frequency table of the
     `Status` free-text values (case-insensitive grouping; do
     not try to normalize). Helps Piotr/Jarek see how many
     PMCs are at each informal stage at a glance.
   - **Repository coverage**: of the repos owned by
     `Scan Requested = Yes` PMCs, how many have `PMC Agreed =
     Yes` (this is the actual scan-queue size). List the top ~10
     by criticality score within the agreed-scan set, since those
     are the ones reviewers will care most about pre-scan.
   - **Unmapped repos**: count the repos with `PMC Slug =
     (unmapped)`. Call out any unmapped repos with a criticality
     score above ~50% — those are high-signal repos missing a PMC
     mapping and might warrant a follow-up with infrastructure /
     the Attic.
   - **Notable gaps**: PMCs with high-criticality repos but no
     `Scan Requested` yet — these are the prospecting list.

5. **Render the summary.** Produce one markdown document with
   sections in the order above. Keep the active-engagements
   table small enough to read in one screen; truncate long lists
   with a "(N more, ask if you want the full list)" tail rather
   than dumping every row.

6. **Cite the source.** End the summary with a one-line footer
   showing the `viewUrl` and `modifiedTime` from Drive metadata
   so the reader knows how fresh the data is.

## Output template

```
# Glasswing / Mythos scan — status as of <modifiedTime>

## Top-line
- PMCs in tracker: <total>
- PMCs with scan requested: <n> (<%>)
- PMCs with a documented Security Model: <n>
- PMCs with a primary contact recorded: <n>
- PMCs whose scan has been delivered: <n>

## Active engagements
| PMC | Primary contact | Security Model | Date Requested | Date Scan Received | Status |
|---|---|---|---|---|---|
| Apache <name> | <contact> | <model or "—"> | YYYY-MM-DD | YYYY-MM-DD or "—" | <free-text status> |
| …

## Turnaround (completed scans only)
- Scans completed: <n>
- Days from request to delivery — min: <d>, median: <d>, max: <d>

## Backlog age (requested, not yet delivered)
| PMC | Date Requested | Days waiting | Status |
|---|---|---|---|
| Apache <name> | YYYY-MM-DD | <d> | <free-text status> |
| …

## Status bucket roll-up
| Status (verbatim) | PMC count |
|---|---|
| <"awaiting threat model" / "scan queued" / …> | <n> |
| …

## Repository coverage (within scan-requested PMCs)
- Repos owned by scan-requested PMCs: <n>
- Repos with PMC Agreed = Yes: <n>
- Top-criticality agreed repos:
  | Repo | Criticality | PMC |
  |---|---|---|
  | …

## Unmapped high-criticality repos
- Total unmapped: <n>
- Unmapped with criticality ≥ 50%:
  | Repo | Criticality |
  |---|---|
  | …

## Prospecting list (high-criticality repos in not-yet-requested PMCs)
| PMC | Top repo | Criticality |
|---|---|---|
| …

---
Source: <view-url>  · sheet last modified <modifiedTime>
```

Adjust the buckets to whatever the user actually asked for — if
they asked just "how many signed up", a one-line answer is better
than the full template. The template is the default for "give me
the rollup, no specifics".

## Style notes

- Numbers, not adjectives. "4 PMCs have requested scans" beats
  "a small handful of PMCs have signed up". The audience is the
  ASF Security team and Foundation officers, both of whom prefer
  counted facts.
- Don't editorialize on which projects "should" sign up — the
  skill reports the state of the tracker. Recommendations are a
  separate conversation.
- Don't reveal contents of `private@<pmc>` or `security@`
  correspondence in the summary (same rule as
  `glasswing-scan-response`). The tracker itself is internal
  coordination data; references to PMCs by name are fine, but
  do not quote anything that was sent privately to the Security
  team.
- The view URL points at Piotr's personal-Gmail-owned sheet.
  When sharing the rollup outside the immediate Security team,
  paste the table — don't paste the URL — since most recipients
  won't have access to the underlying file.

## Examples of bad summaries (avoid)

- A summary that lists every PMC's row verbatim. The point of
  the rollup is aggregation; the user can read the sheet
  themselves if they want the raw rows.
- A summary that claims a PMC is "not interested" because
  `Scan Requested` is blank. Blank means *not yet contacted /
  not yet responded* — silence, not refusal.
- A summary that treats the criticality scores as live. The
  scores are a 2025-07-25 OSSF snapshot, so phrase them as
  "criticality (2025-07-25 snapshot)" if precision matters.
- A summary that adds new columns or speculative status fields
  ("estimated readiness", "blocker") — those belong in a
  follow-up note, not in the rollup. The skill reports what the
  sheet says, no more.

## Provenance

This SKILL captures the structure of Piotr Karwasz's "Mythos
scan" coordination spreadsheet (built 2026-05-06) and the rollup
shape Jarek uses when summarizing the program's state to the
ASF Security team. The spreadsheet itself is a coordination
tool — the source of truth for PMC opt-in remains the
`[GLASSWING]` email requests on `security@apache.org`.
