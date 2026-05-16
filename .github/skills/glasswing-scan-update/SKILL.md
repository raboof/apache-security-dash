---
name: glasswing-scan-update
description: Apply updates to the Glasswing / Mythos scan-outreach tracker (Piotr Karwasz's Google Sheet) on behalf of the ASF Security team — mark a PMC as scan-requested, fill in Request date / Date scan requested / Date scan received / Forwarded scan to PMC, set Security Model + Security model verified, update a repo's PMC mapping, etc. Uses a bundled Python helper that authenticates via OAuth as the running user (Claude Workspace MCP for Google Drive is read-only and cannot do these writes). Always reads the current row, shows a diff, and waits for explicit confirmation before writing. Use whenever Jarek says "mark PMC X as requested", "set the scan date for Y", "the scan for Z is back / has been forwarded", or anything else that mutates a row in the sheet.
---

# Glasswing scan-update SKILL

Write-side companion to `glasswing-scan-status`. The status skill
**reads** the tracker via the Google Drive MCP; this skill
**writes** to it via a bundled Python helper that holds its own
OAuth credentials.

The write path is needed because the Claude Workspace Google Drive
MCP only exposes read tools (no `values.update` / `batchUpdate`).
The helper script (`sheets_writer.py` in this directory) calls the
Google Sheets API v4 directly.

## When to invoke

- Jarek says "mark PMC X as scan-requested" (or any equivalent
  mutation of the `Scan Requested`, `Repositories requested`,
  `Repositories submitted`, `Request date`,
  `Date scan requested`, `Date scan received`,
  `Forwarded scan to PMC`, `Contact Person`, `Backup contact`,
  `Security Model`, `Security model verified`, `Notes`,
  `Initial Model assessment`, `PR/Issues`,
  `PMC thread (ponymail)`, or `Mirko thread (ponymail)`
  columns).
- The scan for a PMC progresses through one of its workflow
  stages: request received (`Request date`), submitted to
  Glasswing (`Date scan requested`), results back
  (`Date scan received`), or forwarded to the PMC
  (`Forwarded scan to PMC`). Each transition writes one or more
  date cells.
- The pre-flight discoverability check passes — set
  `Security model verified`.
- A repo needs its `PMC Slug` / `PMC Agreed` / `Security model`
  column updated (e.g. an `(unmapped)` repo gets mapped to its
  owning PMC after research).
- A genuinely-new PMC needs a row added to the `PMCs` sheet
  (e.g. a PMC that didn't exist when the sheet was last
  regenerated, or one that was trimmed). Use the `append-pmc`
  subcommand — `apply` errors on zero-match by design and won't
  create rows.

Skip this skill when the user is only asking for the *current*
state — that's `glasswing-scan-status`. Skip it when the user is
drafting an email reply — that's `glasswing-scan-response`. This
skill mutates the sheet.

## Hard rules (do not skip)

1. **Always diff before writing.** Run the helper in `--dry-run`
   first, show the diff to the user (every cell: current value
   `->` proposed value), and wait for explicit approval before
   re-running without `--dry-run`. This is the same draft-and-
   confirm rule that applies to outbound messages — the
   spreadsheet is a shared coordination artefact and a wrong cell
   can mislead reviewers as badly as a wrong email.

2. **Match by a stable identifier.** Use `PMC Slug` for PMC-sheet
   updates and `Repository URL` for repo-sheet updates. Do not
   match on `PMC Name`, `Contact Person`, or anything else
   editable; the helper will refuse multi-match and silently-
   correct results, but the matching key should be unambiguous
   to start with.

3. **Never touch rows for PMCs whose data was sourced from
   `private@<pmc>` correspondence the team should not echo
   publicly into a shared sheet.** The tracker is internal but
   not airtight — names + contacts are fine, quoted private
   discussion is not. If asked to paste a sensitive note,
   summarize abstractly in the `Notes` cell.

4. **Confirm before sending** applies twice: once to the cell
   diff (rule 1), and once to the absence of side-effects on
   other rows (rule 2). After applying, read the affected rows
   back to verify the change took.

5. **The spreadsheet ID is not stored in this SKILL or in the
   repo.** Look it up from user-scope reference memory under
   the entry name `mythos-tracker` (the same entry
   `glasswing-scan-status` uses). Pass the ID to the helper via
   `--spreadsheet-id` on the CLI.

## One-time OAuth setup

The helper needs an OAuth 2.0 client ID + a refresh token. Both
artefacts live at `~/.config/asf-security/glasswing/`, outside
the code folder.

1. **Create or pick a Google Cloud project** at
   <https://console.cloud.google.com/>. Free tier is fine; the
   project just hosts the OAuth client.

2. **Enable the Google Sheets API** for that project
   (`APIs & Services` → `Library` → search "Google Sheets API"
   → Enable).

3. **Configure the OAuth consent screen** as an internal/external
   "Desktop" client. For a single Security-team member, "External"
   in Testing mode with the user's own Google account as a Test
   User is sufficient — no app verification needed.

4. **Create OAuth client credentials**: `APIs & Services` →
   `Credentials` → `Create Credentials` → `OAuth client ID` →
   Application type `Desktop app`. Name it something like
   `asf-security glasswing writer`. Click `Download JSON`.

5. **Place the JSON** at
   `~/.config/asf-security/glasswing/oauth_client_secret.json`
   (create the directory if it doesn't exist; the helper does
   not create it for security reasons).

6. **Confirm the user has edit access** to the sheet. The OAuth
   flow authenticates the running user; they must already be on
   the sheet's share list with editor rights, or the API will
   return 403 on the first write. Ask Piotr (the sheet owner)
   for edit access before running setup.

7. **Run the OAuth flow once**:

   ```
   uv run .github/skills/glasswing-scan-update/sheets_writer.py setup
   ```

   This opens a browser, asks the user to grant
   `https://www.googleapis.com/auth/spreadsheets` to the OAuth
   client, then writes a refresh token to
   `~/.config/asf-security/glasswing/token.json` (mode 0600).

After setup, future invocations of `apply` reuse the refresh
token silently.

### Troubleshooting setup

- **`setup` exits with "Place your OAuth client secret JSON at
  …".** Step 5 above (placing `oauth_client_secret.json`) has
  not happened yet. The script does *not* create the JSON for
  you — you have to go through steps 1–4 in the Google Cloud
  Console, download the JSON, and `mv` it to the documented
  path. Re-run `setup` after. The error message is brief
  (one line + exit code 1) and easy to miss if scrolled past;
  the script is *not* hanging silently if the browser doesn't
  open — scroll back and check stderr.

- **`test -f ~/.config/asf-security/glasswing/token.json`
  returns false from inside Claude Code.** The default
  sandbox denies reads of `~/.config/asf-security/`. A
  negative result from `test -f` (or `Path.exists()`) here
  doesn't mean the file is missing — it can also mean the
  sandbox blocked the read. Verify with
  `dangerouslyDisableSandbox: true` before assuming OAuth
  isn't set up.

- **`gh gist create` / other GitHub API calls fail with
  `tls: failed to verify certificate: x509: OSStatus -26276`
  on macOS.** Known macOS / `gh` CLI cert-chain issue inside
  the sandbox. Bypass with `dangerouslyDisableSandbox: true`
  for the affected commands (`gh gist create`, `gh pr view`,
  etc.). Operations against the *Sheets* API use a different
  HTTP path and work fine; only `gh`'s GraphQL path hits
  this.

### Why this directory

`~/.config/asf-security/glasswing/` is XDG-compliant, user-
scoped, outside any git working tree, and not shared with the
team. Each Security-team member runs their own setup and keeps
their own token — there is no shared service account, so every
write is attributable to the actual person who ran it.

`~/.config/asf-security/` (the parent) is also a natural place
to add future ASF-Security secrets (other tracker tokens, the
private mailing-list bouncer creds, etc.). The
`glasswing/` subdirectory keeps this tool's artefacts scoped.

## Procedure

1. **Resolve the sheet ID** from user reference memory
   (`mythos-tracker`). If the entry is missing, point the user
   at the `glasswing-scan-status` SKILL — that one creates the
   entry on first use.

2. **Resolve the target rows** by reading the current sheet
   state. Prefer reusing the read SKILL's output if it's
   already in the conversation; otherwise call
   `mcp__claude_ai_Google_Drive__read_file_content` with the
   file ID. Identify each row by `PMC Slug` (for PMCs sheet) or
   `Repository URL` (for Repositories sheet).

3. **Build the updates JSON.** Each entry is one row update:

   ```json
   [
     {
       "sheet": "PMCs",
       "match": {"column": "PMC Slug", "value": "apisix"},
       "set": {
         "Scan Requested": "Yes",
         "Request date": "2026-05-14"
       }
     }
   ]
   ```

   Write the file to a temp path (e.g.
   `$TMPDIR/glasswing-update-<timestamp>.json`). Do not check
   the file into the repo.

4. **Dry-run the helper.** Invoke from the project root:

   ```
   uv run .github/skills/glasswing-scan-update/sheets_writer.py apply \
       --spreadsheet-id "<id from memory>" \
       --updates "$TMPDIR/glasswing-update-<timestamp>.json" \
       --dry-run
   ```

   The helper prints one line per cell change, in the form:

   ```
   PMCs row 17 (PMC Slug='apisix') · Scan Requested: '' -> 'Yes'   [PMCs!C17]
   PMCs row 17 (PMC Slug='apisix') · Request date: '' -> '2026-05-14'   [PMCs!D17]
   ...
   Dry run — no changes written. (N cells would change.)
   ```

5. **Show the diff to the user and ask for approval.** Format:

   > Proposed updates to the Mythos tracker:
   >
   > - PMC apisix · Scan Requested: empty → `Yes`
   > - PMC apisix · Request date: empty → `2026-05-14`
   >
   > Apply? (yes / no / edits)

   Wait for explicit "yes" / "apply" / "go" / similar. If the
   user wants edits, revise the updates JSON and re-run
   `--dry-run` before re-asking.

6. **Apply.** Re-run the same command without `--dry-run`:

   ```
   uv run .github/skills/glasswing-scan-update/sheets_writer.py apply \
       --spreadsheet-id "<id from memory>" \
       --updates "$TMPDIR/glasswing-update-<timestamp>.json"
   ```

   The helper prints
   `Applied. totalUpdatedCells=N totalUpdatedRows=M …` on
   success.

7. **Verify** by re-reading the affected rows (one
   `mcp__claude_ai_Google_Drive__read_file_content` call is
   fine; you can also re-run the helper with `--dry-run` against
   the same updates JSON — it should now show every cell as
   `'<value>' -> '<value>'`, i.e. nothing to change).

## Helper script reference

`sheets_writer.py` is a self-contained Python script using PEP
723 inline metadata. It declares its own dependencies
(`google-api-python-client`, `google-auth`,
`google-auth-oauthlib`), so `uv run` resolves and runs it without
a separate virtualenv setup. If `uv` is unavailable, fall back
to a regular `pip install` of the three packages in an
appropriate env and then `python sheets_writer.py …`.

Subcommands:

| Subcommand | Purpose |
| --- | --- |
| `setup` | One-time OAuth installed-app flow. Reads `~/.config/asf-security/glasswing/oauth_client_secret.json`, opens a browser, writes `token.json` next to it. |
| `apply --spreadsheet-id ID --updates PATH [--dry-run]` | Apply updates from a JSON file. `--dry-run` prints the diff and exits. |
| `init-canned-tab --spreadsheet-id ID [--dry-run]` | Idempotently create the `Canned Responses` sheet (header row + frozen first row). Run once per workbook. |
| `append-canned --spreadsheet-id ID --entries PATH [--dry-run]` | Append one or more canned-response rows. `Date Added` is auto-filled to today; all other fields come from the JSON. |
| `append-pmc --spreadsheet-id ID --entries PATH [--dry-run]` | Append one or more new PMC rows to the `PMCs` sheet. Entries JSON is a list of objects keyed by `PMCs`-sheet column header; `PMC Name` and `PMC Slug` are required; unknown columns abort; duplicate-slug appends abort (use `apply` to update existing rows instead). For genuinely-new PMCs that don't yet have a row — `apply` errors on zero-match by design. |
| `insert-column --spreadsheet-id ID --sheet S --after H --header NEW [--dry-run]` | Insert a new column at a specific position in a sheet (right after the column with header `H`). Idempotent. |
| `add-columns --spreadsheet-id ID --sheet S --headers H1 H2 ... [--dry-run]` | Append new column headers to the end of a sheet. Idempotent per header. |
| `rename-column --spreadsheet-id ID --sheet S --old H --new NEW [--dry-run]` | Rename the header text at row 1 of a sheet's column. |
| `build-status-tab --spreadsheet-id ID [--dry-run]` | Create or refresh the `Status` derived view: an in-flight table (color-coded by pipeline state), a completed table (with end-to-end days), and a wide-format timeline block ready for a Sheets chart. See `glasswing-scan-status` SKILL for the state taxonomy + color scheme. Idempotent; overwrites existing Status sheet contents. |

Safety properties baked into the helper:

- Match step requires exactly one row; multi-match and zero-match
  both abort with a clear error.
- Unknown column names in `match` or `set` abort.
- Defaults to `--dry-run` *off*, but the SKILL always runs
  `--dry-run` first per rule 1; nothing applies without the
  agent explicitly omitting the flag after user approval.
- `USER_ENTERED` value-input-option: dates / numbers are parsed
  as if a user typed them. Pass dates as ISO `YYYY-MM-DD`.

## Canned responses (workflow)

The `Canned Responses` sheet accumulates reusable answer
fragments — every time the `glasswing-scan-response` SKILL
drafts a *novel* answer that's been approved by the user, it's
a candidate to save here so the next similar request can reuse
it verbatim or with light edits.

### One-time bootstrap

1. **Create the sheet** (idempotent — no-op if it already
   exists):

   ```
   uv run .github/skills/glasswing-scan-update/sheets_writer.py \
       init-canned-tab --spreadsheet-id "<id from memory>"
   ```

2. **Seed with the initial entries** distilled from this repo's
   SKILL fragments. The seed file ships in this directory:

   ```
   uv run .github/skills/glasswing-scan-update/sheets_writer.py \
       append-canned --spreadsheet-id "<id from memory>" \
       --entries .github/skills/glasswing-scan-update/seed_canned_responses.json \
       --dry-run
   ```

   Review the diff, then re-run without `--dry-run` to load.

   The seed file is a bootstrap snapshot — once it's loaded,
   the spreadsheet becomes the source of truth and the seed
   file is no longer authoritative. Don't edit the seed file
   to mutate live canned responses; edit the spreadsheet via
   the response SKILL or the `apply` subcommand.

### Adding a new canned response

When the `glasswing-scan-response` SKILL has drafted a novel
answer the user has approved, and the user agrees it's worth
saving for reuse, build a one-element entries file at
`$TMPDIR/canned-add-<timestamp>.json`:

```json
[
  {
    "topic": "scope",
    "question_pattern": "asks whether monorepo can be scanned end-to-end",
    "response": "<the canned response text — multi-paragraph markdown is fine>",
    "author": "jarek@apache.org",
    "notes": "Mention chunking-by-component for Lucene+Solr+Tika-scale repos."
  }
]
```

Then dry-run the append, show the user, and on approval apply:

```
uv run .github/skills/glasswing-scan-update/sheets_writer.py \
    append-canned --spreadsheet-id "<id from memory>" \
    --entries "$TMPDIR/canned-add-<timestamp>.json" \
    --dry-run
```

Same draft-and-confirm rule as `apply` — never write without
explicit user approval of the printed diff.

### Updating an existing canned response

Use `apply` matching by the `Question pattern` column (it's the
most stable identifier for a canned row). Example updates JSON:

```json
[
  {
    "sheet": "Canned Responses",
    "match": {"column": "Question pattern", "value": "asks which threat-modeling framework we expect — STRIDE / LINDDUN / PASTA"},
    "set": {"Response": "<new text>", "Author": "<editor's address>"}
  }
]
```

If multiple rows share the same `Question pattern` (they
shouldn't, but it can happen if the sheet wasn't curated), the
helper aborts rather than guessing — manually disambiguate
first by adjusting the patterns.

## Style notes

- The skill writes; it does not summarize. After applying, the
  agent's reply should be a short confirmation
  ("Applied — 3 cells in PMCs row 17."), not a re-statement of
  the entire row.
- Don't batch unrelated updates into one apply call without
  user approval of the combined diff. "While you're in there,
  also set X" is the wrong instinct here — every change goes
  through the same diff-and-confirm gate.
- The PMC sheet has no free-form `Status` cell — workflow stage
  is implicit from which of the four date columns
  (`Request date`, `Date scan requested`, `Date scan received`,
  `Forwarded scan to PMC`) is the last one filled. Don't
  invent a Status column; write the relevant date instead.
- All four date columns plus `Security model verified` are
  dates, not datetimes. Use `YYYY-MM-DD`. If a user gives a
  relative date ("today", "yesterday"), resolve to the
  absolute date *before* writing it (the same way memory
  entries resolve relative dates).

## Examples of bad updates (avoid)

- Updating the row by `PMC Name` instead of `PMC Slug`. The
  slug is the join key with the repos sheet; updating by name
  invites typos and capitalization mismatches.
- Filling `Date scan received` or `Forwarded scan to PMC`
  before the underlying event actually happened — those cells
  exist to track real leg turnaround, and pre-filling them
  pollutes the metric. Each date column should be written only
  when its event genuinely occurred.
- Setting `Scan Requested = Yes` for a PMC that has only
  expressed informal interest (e.g. on a public mailing list).
  The column means "the PMC sent a `[GLASSWING]` request from
  an `@apache.org` identity" — anything looser muddies the
  Security-team queue.
- Quoting `private@<pmc>` correspondence into the `Notes`
  cell. Summarize abstractly instead.

## Provenance

This SKILL was added when the team realised that the read-only
status SKILL needed a write counterpart, and that the Claude
Workspace Drive MCP could not provide one. The helper script's
shape mirrors what Piotr Karwasz manually does in the sheet
when he tracks scan progress — the skill exists so the agent
can do those same updates while leaving an auditable diff
trail. Credentials live outside the repo by deliberate choice;
the sheet itself remains Piotr's source of truth.
