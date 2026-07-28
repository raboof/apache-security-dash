---
name: frontier-model-preparation-status
description: >-
  Summarize the current status of the ASF Security team's Frontier Model Preparation (a.k.a. Mythos) scan-outreach effort
  by reading the shared Google Sheet that Piotr Karwasz maintains.
  Reports which PMCs have requested scans,
  who the named contacts are,
  which projects have a Security Model documented,
  where unmapped/high-criticality repos sit,
  and what's outstanding.
  Use whenever someone asks "where do we stand on Frontier Model Preparation scans",
  "how many PMCs have signed up",
  "what's the status of project X in the tracker",
  or "give me a scan-program rollup".
  Reads only — never writes to the sheet.
---

# Frontier Model Preparation scan-status SKILL

Read-only reporting skill for the Frontier Model Preparation / Mythos scan outreach tracker.
The deliverable is a markdown summary the user can paste into a status update,
a private@security@apache.org note,
or a meeting agenda.
The skill never writes back to the sheet.

## Data source

The tracker is a Google Sheet titled `Mythos scan`, owned by Piotr Karwasz.
"Mythos" is Piotr's internal name for the same effort the ASF Security team announces externally as "Frontier Model Preparation" —
the two terms refer to the same scan program and the same tracker.
The skill keeps both names so it stays discoverable either way.

**The sheet's file ID and view URL are not embedded in this SKILL.**
They live in the user's Claude reference memory,
in an entry named `mythos-tracker` (see `MEMORY.md` → `mythos-tracker.md` under the user's per-project memory directory, typically `~/.claude/projects/<project>/memory/mythos-tracker.md`).
This keeps the coordination URL out of the public `apache/security` repo.
A Security-team member running the skill for the first time should add the same memory entry to their own profile —
ask Jarek (or whoever currently owns the tracker) for the file ID,
then save it as a `type: reference` memory under the name `mythos-tracker`.

Read the sheet with the Google Drive MCP tool `mcp__claude_ai_Google_Drive__read_file_content` against the file ID from memory.
The tool returns a markdown-table rendering of the three sheets concatenated in order.
Get the last-modified timestamp via `mcp__claude_ai_Google_Drive__get_file_metadata` on the same file ID.

**Important — the Drive MCP truncates large spreadsheets.**
`read_file_content` silently caps its output at ~80KB of markdown.
For the current ~210-PMC `Mythos scan` workbook this means rows past roughly the first ~140 (alphabetically up through "Apache Phoenix") are dropped from the rendering without any indication that truncation occurred.
PMCs whose slugs sort later —
including Polaris, Shiro, Spark, Struts, Thrift, Tomcat, Traffic Server,
and any not-yet-added PMC that lands after `P` alphabetically —
will be **invisible** to a status pass that trusts the MCP output alone.

When the *row count itself* matters (verifying which PMCs have `Scan Requested = Yes`,
checking whether a given PMC has a row at all,
computing program totals,
enumerating slugs),
query the Sheets API directly via the `sheets_writer.py` helper in the `frontier-model-preparation-update` SKILL
(or a one-off Python script using the same OAuth credentials).
Reading just the `PMCs!A:C` range is enough to enumerate slugs + Scan-Requested state across the whole sheet;
drill into specific rows with targeted reads after.
The MCP read remains useful for the *content* of rows you've already identified.

### Sheet layout

The workbook has up to five sheets:

1. **README** — short prose describing the workbook and its data sources
   (Apache Whimsy `committee-info.json` for the PMC list,
   the github.com/orgs/apache scrape for repos,
   the OSSF `criticality_score` 2025-07-25 snapshot for scores).
   Useful for stating provenance in the summary; otherwise informational.

2. **PMCs** (~210 rows) — one row per Apache PMC.
   Columns in sheet order:

   | Column | Meaning |
   | --- | --- |
   | `PMC Name` | Full name, e.g. `Apache Logging Services`. |
   | `PMC Slug` | Short identifier used as the join key on the repos sheet, e.g. `logging`. |
   | `Scan Requested` | `Yes` if the PMC has formally opted in via the `[GLASSWING]` request flow; blank otherwise. |
   | `Repositories requested` | The repos the PMC asked for / confirmed as in-scope for the scan — what they *want* scanned. One URL per line (newline-separated). Populated by `frontier-model-preparation-response` gate 4 after the PMC confirms scope. Empty when scope hasn't been confirmed yet. This is the *input* scope; model-verify reads it. |
   | `Repositories submitted` | The repos actually submitted to ASF Tooling — typically the subset of `Repositories requested` that passed pre-flight discoverability + completeness. Written by `frontier-model-preparation-update` after the human sends the PMC notification email from `frontier-model-preparation-submit` (which submits one form per repo via ASF Tooling's project-enrollment Google Form, ordered by OSSF Criticality Score). May be smaller than `Repositories requested` when some repos couldn't be verified before the first submit (their AGENTS.md / SECURITY.md was missing and the fix is still in flight); those land in a later batch. |
   | `Request date` | Date the PMC's `[GLASSWING]` request arrived at `security@apache.org`. `YYYY-MM-DD`. Blank if not yet requested. |
   | `Contact Person` | Primary PMC contact — name + `@apache.org` address. |
   | `Backup contact` | Backup PMC contact, same shape. |
   | `Security Model` | Free-text name of the threat model the PMC has agreed to be scanned against (e.g. `Logging Services Security Model`). Blank if the PMC has not yet supplied or accepted a model. |
   | `Security model verified` | Marker (date or `Yes`) for when the Security team's pre-flight has **fully** passed for this PMC. Two conditions must both hold: (a) the threat model itself passes the minimum-bar completeness rubric, and (b) **every repo in `Repositories requested` independently passes discoverability** (`AGENTS.md` → `SECURITY.md` → model URL chain resolves at the designated commit). Setting this flag too early (e.g. when only the model is good but some repos still lack `AGENTS.md`) leads to the PMC appearing as `Ready` in status views while in reality the team is still waiting on PMC follow-up — keep it blank until both conditions hold. |
   | `Date scan requested` | Date the Security team submitted the scan run to Frontier Model Preparation. `YYYY-MM-DD`. Blank if not yet queued. |
   | `Date scan received` | Date the scan output came back from Frontier Model Preparation to the Security team. `YYYY-MM-DD`. Blank if not yet received. |
   | `Forwarded scan to PMC` | Date (or `Yes`) marking when the Security team forwarded the scan output to the PMC's listed recipients. Blank if not yet forwarded. |
   | `Notes` | Free-text. |
   | `Initial Model assessment` | Free-text snapshot of the pre-flight findings for this PMC — per-repo discoverability status, model completeness verdict, open questions. Set by `frontier-model-preparation-model-verify`. |
   | `Expedite Claude OSS Requests` | Newline-separated `@apache.org` addresses the PMC has nominated for an Anthropic Claude-for-Open-Source subscription expedite request, relayed via the ASF Tooling relationship. Populated by `frontier-model-preparation-update apply` after the PMC replies to the pre-flight-pass OSS-tooling offer sent by `frontier-model-preparation-response`. **Prerequisite**: each address must have already registered at https://claude.com/contact-sales/claude-for-oss before the PMC confirms it for the expedite ask — we don't write addresses that haven't registered yet because the expedite would be a no-op. The literal string `none` means the PMC explicitly opted out (deliberate-and-recorded rather than blank-and-unclear). Empty = the offer hasn't been sent yet, or the PMC hasn't replied to it. Added 2026-05-17. |
   | `Claude OSS Subscriptions Submitted` | Newline-separated `@apache.org` addresses for which Anthropic has actually confirmed/granted the Claude-for-Open-Source subscription (typically via reply to the expedite-ask thread). Populated by `frontier-model-preparation-update apply` (append-mode — preserve existing rows) as confirmations come back. Distinct from `Expedite Claude OSS Requests` (which tracks who the PMC asked us to expedite *for*); this column tracks the actually-granted outcomes. Added 2026-05-17. |
   | `PR/Issues` | URLs of PRs the Security team has opened on the PMC's repos (AGENTS.md / SECURITY.md / model-additions PRs), one per line. Multiple PRs for the same PMC (e.g. discoverability fixes across several repos) are kept as separate lines — `frontier-model-preparation-response` and `frontier-model-preparation-model-verify` **append** rather than overwrite. Free-text annotations on the same line (`(discoverability PR)`, `+ Email reply 2026-05-14`) are allowed and ignored by parsers that only care about the PR URLs. `build-status-tab` parses every PR URL out of this cell and queries `gh pr view` to count open vs merged for the Status tab. |
   | `PMC thread (ponymail)` | **Direct** lists-apache.org thread permalink (`https://lists.apache.org/thread/<tid>`) to the PMC-side correspondence — the original `[GLASSWING]` request + all replies between Security team and the PMC. Resolved by `frontier-model-preparation-run` via ponymail search on `private@<pmc>.apache.org` filtered by `subject:GLASSWING`. Requires `mcp__ponymail__login` to have been run first (private lists need auth). Left blank when ponymail-auth isn't set up — never populated with a non-direct fallback URL, since those would mislead readers expecting a single click into the thread. |

   The four date-tracking columns
   (`Request date`, `Date scan requested`, `Date scan received`, `Forwarded scan to PMC`)
   and the `Security model verified` marker were added by Jarek by hand after the workbook was first generated —
   they split the original single-date model into four observable legs
   (request received → submitted to Frontier Model Preparation → results back → results forwarded to PMC),
   so the team can see queue / ASF Tooling / forwarding lag separately.
   If they're absent in an older snapshot, the skill should gracefully degrade:
   skip the turnaround-leg computation and surface a one-line note that the columns are missing rather than failing.

3. **Repositories** (~3,107 rows) —
   one row per public repo in `github.com/orgs/apache`.
   Columns:

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

4. **Canned Responses** (variable rows) — one row per reusable answer fragment.
   Created lazily on first use by the `frontier-model-preparation-update` SKILL's `init-canned-tab` helper.
   Columns:

   | Column | Meaning |
   | --- | --- |
   | `Date Added` | `YYYY-MM-DD` the entry was appended. |
   | `Topic` | One-word tag (e.g. `framework`, `scope`, `tooling`, `roster`, `process`, `discoverability`). Groups entries for human browsing. |
   | `Question pattern` | One-line description of when this answer applies (e.g. "asks which threat-modeling framework we expect — STRIDE / LINDDUN / PASTA"). |
   | `Response` | The canned reply text. May be multi-paragraph markdown; reuse verbatim or lightly adapt for register. |
   | `Author` | Who wrote the entry — `@apache.org` address or "ASF Security team". |
   | `Notes` | Caveats — when this answer applies, when to NOT reuse it, what to swap in for thread specifics. |

   This sheet is the source of truth for canned answers.
   The `frontier-model-preparation-response` SKILL consults it before drafting any reply and appends new entries (via `frontier-model-preparation-update`) after the user approves a novel response.
   Older snapshots of the workbook (from before `init-canned-tab` was first run) will not have this sheet —
   the response SKILL falls back to its in-SKILL fragments in that case.

5. **Status** (auto-generated, refreshable) —
   a derived view of the scan-pipeline state,
   regenerated on demand by `frontier-model-preparation-update`'s `build-status-tab` subcommand.
   This sheet is **not** human-edited;
   every refresh overwrites it from the PMCs sheet.
   Four blocks:

   - **PROGRAM TOTALS** header — one-screen rollup surfaced above the in-flight table:
     PMCs opted in (count of rows with `Scan Requested = Yes`),
     PMCs with at least one PR opened,
     `PRs opened (not yet merged)`, `PRs merged`, `PRs total`.
     If any PRs were closed without merge,
     a parenthetical line below the total reports the count so the math reconciles
     (`total = open + merged + closed-without-merge`).

   - **IN FLIGHT** table —
     one row per PMC where the scan is still moving through the pipeline (not yet `Delivered`).
     Columns: `PMC`, `Slug`, `Status`, `Repos requested` (count),
     `Model` status, `PRs opened (not yet merged)`, `PRs merged`,
     `PRs total` (all three derived from the `PR/Issues` cell via `gh pr view`),
     `Request date`, `Last touch` (model-verified date if filled),
     `Notes / PR / Issues`.
     Each row is background-colored by its pipeline state.

   - **COMPLETED** table — one row per PMC where `Forwarded scan to PMC` is set.
     Columns: `PMC`, `Slug`, `Repos submitted` (count),
     `PRs opened (not yet merged)`, `PRs merged`, `PRs total`,
     `Submitted`, `Received`, `Forwarded`,
     `Days end-to-end` (the turnaround in days from Request date to Forwarded).
     Rows colored dark green.

   - **TIMELINE DATA** block —
     wide-format table (`PMC` | `Requested` | `Ready` | `Submitted` | `Received` | `Forwarded`),
     one row per PMC with the filled milestone dates and blanks for the unreached ones.
     Chart-ready:
     select the block in Sheets and `Insert > Chart` produces a usable timeline
     (a scatter chart with PMC on Y and dates on X;
     one series per milestone column reads as differently-colored markers per milestone).

### Pipeline-state taxonomy

The `Status` column on the in-flight table comes from the following state machine (latest applicable state wins):

| State | Condition | Color |
| --- | --- | --- |
| Pre-flight | Scan requested, model not yet verified | light red |
| Ready | `Security model verified` set, not yet submitted to ASF Tooling | yellow |
| Submitted | `Date scan requested` set, results not yet back | light green |
| Triaging | `Date scan received` set, not yet forwarded. (Legacy state-column name written to the sheet by `sheets_writer.py`; the team's actual activity in this state is a pre-forward sanity check for catastrophic generation errors, not per-finding triage — see `frontier-model-preparation-forward`.) | medium green |
| Delivered | `Forwarded scan to PMC` set | dark green (appears in the COMPLETED table, not in-flight) |

The `Triaging → Delivered` transition includes a side-effect that does **not** get its own state column:
the `frontier-model-preparation-forward` SKILL commits ASF Tooling's scan + sidecars (raw `.json` + `.notes.md` sanity-check log)
to the [`scans/`](../../../scans/README.md) tree before drafting the forwarding email
(ASF Tooling findings verbatim — no per-finding triage).
The archive commit and the email draft are produced together under a single approval gate,
so a PMC normally moves Triaging → Delivered in one operator interaction.
If something abnormal interrupts that flow (archive committed but email never drafted),
the `frontier-model-preparation-run` classifier surfaces it as `archived-not-forwarded`
rather than letting the row sit in `Triaging` indefinitely.

The `Model` column is independent of the pipeline state and indicates how far the threat-model verification has progressed:

| Model status | Condition |
| --- | --- |
| Verified | `Security model verified` cell is set |
| Nominated | `Security Model` cell set, `Security model verified` blank |
| Missing | `Security Model` cell blank |

### Refreshing the Status tab

Run from the project root:

```
uv run .github/skills/frontier-model-preparation-update/sheets_writer.py \
    build-status-tab --spreadsheet-id "<id from memory>"
```

The subcommand is idempotent:
it creates the `Status` sheet if absent,
clears it if present,
then writes the three blocks plus per-row background colors.
Run before any status-report moment (PMC-facing rollup,
weekly check-in,
before sending a foundation-level update).
It is safe to run as often as you like —
the underlying PMCs sheet is the source of truth;
this is just a refreshed view.

### Why the chart is not embedded programmatically

The Status tab leaves the `TIMELINE DATA` block as a chart-ready table rather than embedding a chart object via the Sheets API.
Reasons:

- Sheets' API chart objects don't natively render the "timeline" intuition
  (X = continuous date, Y = categorical PMC, colored markers per milestone) —
  the closest match (basic SCATTER with per-column series)
  needs careful range plumbing that's brittle across refreshes.
- A user-built chart from the block survives sheet rebuilds
  (since the block's range stays at the same cells);
  embedded charts would have to be deleted and recreated on every refresh.
- A one-time manual chart insert from the block (Insert
  > Chart > Scatter, or Chart Type > Timeline if the
  Sheets UI offers it for the data shape) takes ~30 seconds and gives a better-looking result than the API can produce.

If a future Sheets API change makes API-embedded timeline charts cleaner,
this SKILL should be updated to do the embed.

## When to invoke

- A team-mate or Jarek asks for a rollup:
  "how many PMCs have signed up?",
  "list the projects we're waiting on",
  "what does the Frontier Model Preparation tracker look like right now?".
- A PMC contact asks where their project sits in the queue and Jarek needs to look up the row.
- Drafting a status note to `security@apache.org` or a quarterly Foundation report about the program's reach.

Skip this skill when the user is asking about a *finding* from a scan that already ran —
that's a different artefact (the scan output markdown), not the outreach tracker.

## Procedure

1. **Resolve the sheet ID from memory.**
   Look up the `mythos-tracker` entry in user-scope reference memory and extract the `File ID`.
   If the entry is missing,
   ask the user for the spreadsheet URL once,
   save it as a new `mythos-tracker` reference memory,
   then continue.
   Never inline the ID in this SKILL or in commit-bound files.

2. **Fetch the sheet.**
   Call `mcp__claude_ai_Google_Drive__read_file_content` with the file ID from memory.
   The response is one long markdown document —
   the README sheet first, then PMCs, then Repositories.
   Sheets are separated by blank lines and a fresh header row.
   Also call `mcp__claude_ai_Google_Drive__get_file_metadata` once to grab `modifiedTime` and `viewUrl` —
   both are used in the summary footer.

3. **Parse the three sheets.**
   Split on the header rows (`| PMC Name | PMC Slug | ...` for PMCs,
   `| Repository URL | Repository Name | ...` for Repositories).
   Treat each remaining markdown table row as one record.
   Cells containing the literal `\<` / `\>` are Markdown-escaped email brackets —
   keep them when reproducing contact names,
   but strip when extracting a bare email.

4. **Compute the summary.** At minimum:
   - **Top-line counts**: total PMCs,
     PMCs with `Scan Requested = Yes`,
     PMCs with a non-empty `Security Model`,
     PMCs with `Security model verified` set,
     PMCs with a primary contact filled in,
     PMCs whose `Date scan received` is non-empty (results back from Frontier Model Preparation),
     PMCs whose `Forwarded scan to PMC` is non-empty (fully closed out).
   - **Active engagements**: for every PMC where `Scan Requested = Yes`,
     list `PMC Name`, primary contact,
     `Security Model` + `Security model verified` status,
     `Request date`, `Date scan requested`, `Date scan received`,
     and `Forwarded scan to PMC` (use `—` for blank cells).
     Flag rows where the scan is requested but no model is yet documented or verified —
     that's the work the Security team has next.
   - **Turnaround legs**
     (only show legs that have at least one row with both endpoints set;
     skip the rest silently):
     - *Queue lag*: `Request date` → `Date scan requested` —
       how long requests sit in the Security team's queue.
     - *ASF Tooling lag*: `Date scan requested` → `Date scan received` —
       how long Frontier Model Preparation takes per run.
     - *Forwarding lag*: `Date scan received` → `Forwarded scan to PMC` —
       how long results sit in pre-forward sanity check.
     - *End-to-end*: `Request date` → `Forwarded scan to PMC`.

     For each, report min / median / max in days.
   - **Backlog age**: for PMCs with `Request date` filled but `Forwarded scan to PMC` blank,
     sort by `Request date` ascending and show the top few —
     these are the longest-waiting requests.
     Tag each by the next unfilled date column (`awaiting submit` / `scan running` / `pending forward`) so the bottleneck is visible at a glance.
     Internal pressure signal; do not paste into a PMC-facing reply.
   - **Repository coverage**: of the repos owned by `Scan Requested = Yes` PMCs,
     how many have `PMC Agreed = Yes` (this is the actual scan-queue size).
     List the top ~10 by criticality score within the agreed-scan set,
     since those are the ones reviewers will care most about pre-scan.
   - **Unmapped repos**: count the repos with `PMC Slug = (unmapped)`.
     Call out any unmapped repos with a criticality score above ~50% —
     those are high-signal repos missing a PMC mapping
     and might warrant a follow-up with infrastructure / the Attic.
   - **Notable gaps**: PMCs with high-criticality repos but no `Scan Requested` yet —
     these are the prospecting list.

5. **Render the summary.**
   Produce one markdown document with sections in the order above.
   Keep the active-engagements table small enough to read in one screen;
   truncate long lists with a "(N more, ask if you want the full list)" tail rather than dumping every row.

6. **Cite the source.**
   End the summary with a one-line footer showing the `viewUrl` and `modifiedTime` from Drive metadata
   so the reader knows how fresh the data is.

## Output template

```
# Frontier Model Preparation / Mythos scan — status as of <modifiedTime>

## Top-line
- PMCs in tracker: <total>
- PMCs with scan requested: <n> (<%>)
- PMCs with a documented Security Model: <n>
- PMCs with Security model verified: <n>
- PMCs with a primary contact recorded: <n>
- PMCs whose scan has come back from Frontier Model Preparation: <n>
- PMCs whose scan has been forwarded to the PMC: <n>

## Active engagements
| PMC | Primary contact | Security Model | Model verified | Request date | Date scan requested | Date scan received | Forwarded |
|---|---|---|---|---|---|---|---|
| Apache <name> | <contact> | <model or "—"> | <date or "—"> | YYYY-MM-DD | YYYY-MM-DD or "—" | YYYY-MM-DD or "—" | YYYY-MM-DD or "—" |
| …

## Turnaround legs (where data is present)
- Queue lag (request → submit): min/median/max days
- ASF Tooling lag (submit → result): min/median/max days
- Forwarding lag (result → forward): min/median/max days
- End-to-end (request → forward): min/median/max days

## Backlog age (requested, not yet forwarded)
| PMC | Request date | Days waiting | Next bottleneck |
|---|---|---|---|
| Apache <name> | YYYY-MM-DD | <d> | <"awaiting submit" / "scan running" / "pending forward"> |
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

Adjust the buckets to whatever the user actually asked for —
if they asked just "how many signed up",
a one-line answer is better than the full template.
The template is the default for "give me the rollup, no specifics".

## Style notes

- Numbers, not adjectives.
  "4 PMCs have requested scans" beats "a small handful of PMCs have signed up".
  The audience is the ASF Security team and Foundation officers,
  both of whom prefer counted facts.
- Don't editorialize on which projects "should" sign up —
  the skill reports the state of the tracker.
  Recommendations are a separate conversation.
- Don't reveal contents of `private@<pmc>` or `security@` correspondence in the summary (same rule as `frontier-model-preparation-response`).
  The tracker itself is internal coordination data;
  references to PMCs by name are fine,
  but do not quote anything that was sent privately to the Security team.
- The view URL points at Piotr's personal-Gmail-owned sheet.
  When sharing the rollup outside the immediate Security team,
  paste the table — don't paste the URL —
  since most recipients won't have access to the underlying file.

## Examples of bad summaries (avoid)

- A summary that lists every PMC's row verbatim.
  The point of the rollup is aggregation;
  the user can read the sheet themselves if they want the raw rows.
- A summary that claims a PMC is "not interested" because `Scan Requested` is blank.
  Blank means *not yet contacted / not yet responded* — silence, not refusal.
- A summary that treats the criticality scores as live.
  The scores are a 2025-07-25 OSSF snapshot,
  so phrase them as "criticality (2025-07-25 snapshot)" if precision matters.
- A summary that adds new columns or speculative status fields ("estimated readiness", "blocker") —
  those belong in a follow-up note, not in the rollup.
  The skill reports what the sheet says, no more.

## Provenance

This SKILL captures the structure of Piotr Karwasz's "Mythos scan" coordination spreadsheet (built 2026-05-06) and the rollup shape Jarek uses when summarizing the program's state to the ASF Security team.
The spreadsheet itself is a coordination tool —
the source of truth for PMC opt-in remains the `[GLASSWING]` email requests on `security@apache.org`.
