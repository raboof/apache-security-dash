<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# sheets-writer

OAuth-authenticated writer for the Glasswing / Mythos
scan-outreach Google Sheet (the tracker that
`frontier-model-preparation-update` and friends mutate). Largest of the
`tools/` projects; covers row-level applies, canned-response
management, PMC-row appends, the Status-tab rebuild, and
column-schema mutations.

Used by the `frontier-model-preparation-update` SKILL.

## Why this exists

The Claude Workspace Google Drive MCP is read-only — it can
fetch a sheet's contents but can't call `values.batchUpdate`
/ `values.append` / `batchUpdate(addSheet)`. SKILLs that need
to write to the tracker go through this CLI, which holds its
own OAuth refresh token under
`~/.config/asf-security/glasswing/` and talks to the Sheets
v4 API directly. Same operator identity as the human running
the SKILL — no shared service account.

## One-time OAuth setup

1. In Google Cloud Console, create a project (any name).
   Enable the Sheets API. Under APIs & Services → Credentials,
   create an OAuth client credential of type **Desktop app**.
   Download the JSON.

2. Place the JSON at the canonical location:

   ```bash
   mkdir -p ~/.config/asf-security/glasswing
   mv ~/Downloads/client_secret_*.json \
      ~/.config/asf-security/glasswing/oauth_client_secret.json
   chmod 600 ~/.config/asf-security/glasswing/oauth_client_secret.json
   ```

3. Run the installed-app OAuth flow once:

   ```bash
   uv run --project tools/sheets_writer sheets-writer setup
   ```

   A browser opens, you grant the `spreadsheets` scope, and
   the script writes `~/.config/asf-security/glasswing/token.json`
   with a refresh token (mode 0o600). Subsequent runs reuse
   the refresh token transparently.

`form_submitter` shares the same `token.json` (read-only),
so completing setup here is sufficient for both.

## Subcommands

All write subcommands accept `--dry-run` to preview the cell
payload without contacting the API.

| Subcommand | Purpose |
| --- | --- |
| `setup` | One-time OAuth installed-app flow. |
| `dump --spreadsheet-id ID --sheet S [--objects] [--compact]` | **Read-only.** Print a whole sheet as JSON to stdout, straight off the Sheets API (no Drive-MCP ~80 KB truncation). Default shape is `{header, rows}`; `--objects` keys each row by header. Pipe to `jq` to read without pulling bytes into model context. |
| `apply --spreadsheet-id ID --updates PATH [--dry-run]` | Apply row-level updates from a JSON file. Match step requires exactly one row per update. Cells already holding the requested value are skipped, so `totalUpdatedCells` counts real changes and re-running an applied file with `--dry-run` reports `Nothing to do` — which is how you verify a write landed. |
| `init-canned-tab --spreadsheet-id ID [--dry-run]` | Create the `Canned Responses` sheet idempotently. |
| `append-canned --spreadsheet-id ID --entries PATH [--dry-run]` | Append canned-response rows. Today's date auto-fills the `Date Added` column. |
| `append-pmc --spreadsheet-id ID --entries PATH [--dry-run]` | Append new PMC rows. `PMC Name` + `PMC Slug` required. Duplicate-slug appends abort with the existing row number. |
| `build-status-tab --spreadsheet-id ID [--dry-run]` | Recreate the `Status` tab with in-flight + completed tables, program-wide rollup, color-coded by pipeline state, and a wide-format timeline block for charting. |
| `rename-column --spreadsheet-id ID --sheet S --old H --new NEW [--dry-run]` | Rename a single column header at row 1. |
| `insert-column --spreadsheet-id ID --sheet S --after H --header NEW [--dry-run]` | Insert a new column directly after an anchor column. Idempotent. |
| `add-columns --spreadsheet-id ID --sheet S --headers H... [--dry-run]` | Append column headers at the end of a sheet. Idempotent per header. |
| `backfill-security-cc --spreadsheet-id ID [--dry-run]` | Deterministically write the `PMC team Cc` column on the `PMCs` sheet — each PMC's own `security@<pmc>.apache.org` when it runs a security team, else its `private@<pmc>.apache.org` list. Determination via `whimsy_lookup` reading security-site `project-coordinates.json` (no WebFetch). Creates the column after `Report recipients` if missing; re-runnable (refreshes every cell). |

## Apply — updates JSON shape

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

Safety properties baked into the helper:

- Match step requires exactly one row; multi-match and
  zero-match both abort with a clear error (the row numbers
  of duplicates are surfaced so the operator can resolve
  manually).
- Unknown column names in `match` or `set` abort.
- Dates / numbers are written under `valueInputOption=USER_ENTERED`
  — pass dates as ISO `YYYY-MM-DD`.

## append-pmc — entries JSON shape

```json
[
  {
    "PMC Name": "Apache Foo",
    "PMC Slug": "foo",
    "Scan Requested": "Yes",
    "Contact Person": "alice@apache.org"
  }
]
```

`PMC Name` and `PMC Slug` are required and must be non-blank;
all other columns are optional. Unknown column keys abort
before any write. The dup-slug check reads the existing
slugs from the live sheet — if `foo` is already there, the
append fails and you're told to use `apply` instead.

## Invocation from Claude Code SKILLs

```bash
uv run --project tools/sheets_writer sheets-writer <subcommand> ...
```

This bypasses the need for any global install. The first run
on a machine materialises a `uv` virtualenv with
google-api-python-client + google-auth-oauthlib; subsequent
runs reuse it.

## Test coverage

The test suite covers the **pure-function** layer (the bulk
of the logic):

- `columns.col_letter` — A1-letter math across A/Z/AA/ZZ/AAA boundaries.
- `columns.find_unique_row` — hit / miss / multi-match / missing-column / empty-grid.
- `prs.parse_pr_urls` — URL extraction + dedupe + ignoring non-PR lines.
- `status.compute_pmc_status` — pipeline state machine across all 5 states + model-status logic + repo-count parsing.
- `apply.build_apply_plan` — diff lines + `values.batchUpdate` payload shape, multi-sheet, error propagation.
- `canned.build_canned_rows` — auto-filled date column, required-field validation, multi-entry ordering.
- `pmcs.build_pmc_rows` — required-field check, unknown-column abort, dup-slug abort, dry-run dup-check skip.
- CLI argparse routing for all 9 subcommands.

What's **not** unit-tested: the Google API side-effects
themselves (the actual `service.spreadsheets().*` calls).
Those are exercised through manual operator use and through
the SKILL's draft-and-confirm flow — every write subcommand
has `--dry-run` so the operator sees the payload before any
API call fires.

## Development

```bash
cd tools/sheets_writer
uv sync --extra test
uv run pytest
uvx ruff check src tests
uvx ruff format src tests --check
```

## Layout

```
tools/sheets_writer/
├── pyproject.toml         — hatchling build, google-api-python-client +
│                            google-auth + google-auth-oauthlib runtime deps
├── README.md              — this file
├── src/sheets_writer/
│   ├── __init__.py        — version + config paths + sheet names + state colors
│   ├── __main__.py        — `python -m sheets_writer` entry
│   ├── auth.py            — load_credentials + run_setup (OAuth installed-app)
│   ├── sheets_api.py      — get_service + fetch_sheet_grid (thin API shims)
│   ├── columns.py         — col_letter + find_unique_row (pure)
│   ├── prs.py             — parse_pr_urls (pure) + query_pr_states (shells out to gh)
│   ├── status.py          — compute_pmc_status + cmd_build_status_tab
│   ├── apply.py           — build_apply_plan (pure) + cmd_apply
│   ├── canned.py          — build_canned_rows (pure) + cmd_init_canned + cmd_append_canned
│   ├── pmcs.py            — build_pmc_rows (pure) + cmd_append_pmc
│   ├── schema.py          — cmd_rename_column / cmd_insert_column / cmd_add_columns
│   └── cli.py             — argparse + dispatch
└── tests/
    ├── conftest.py        — FakeSheetsService + sample PMC grids
    ├── test_columns.py    — A1 math + row matching
    ├── test_prs.py        — URL extraction
    ├── test_status.py     — pipeline state machine
    ├── test_apply.py      — apply diff builder
    ├── test_canned.py     — canned-row builder
    ├── test_pmcs.py       — PMC-row builder
    └── test_cli.py        — argparse routing
```

## Provenance

Promoted from `sheets_writer.py` (1165-line single-file
helper) in `.github/skills/frontier-model-preparation-update/`
2026-05-28, fourth in the `tools/` promotion series after
`jira_writer` (#72), `whimsy_lookup` (#73), and
`form_submitter` (#75).

The split into per-subcommand modules makes the test
coverage tractable — `compute_pmc_status` had no unit tests
in its monolithic life despite being the most state-machine-y
function in the codebase; now it's isolated and locked in.
