#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "google-api-python-client>=2.0",
#     "google-auth>=2.0",
#     "google-auth-oauthlib>=1.0",
# ]
# ///
"""OAuth-authenticated writer for the Glasswing / Mythos scan tracker.

Reads OAuth client secret + refresh token from
~/.config/asf-security/glasswing/ (outside the repo). The user acts as
themselves — they must already have edit access to the spreadsheet.

Subcommands:
  setup
      Run the OAuth installed-app flow once and persist a refresh token
      at ~/.config/asf-security/glasswing/token.json. Required before
      the first apply.

  apply --spreadsheet-id ID --updates PATH [--dry-run]
      Apply a JSON list of row-level updates. With --dry-run, prints the
      cell-by-cell diff and exits without writing. Without --dry-run,
      sends a values.batchUpdate to the Sheets API.

The updates JSON is a list of objects of the form:

    [
      {
        "sheet": "PMCs",
        "match": {"column": "PMC Slug", "value": "apisix"},
        "set": {
          "Scan Requested": "Yes",
          "Request date": "2026-05-14"
        }
      },
      ...
    ]

Row matching requires exactly one row. The script errors out on zero or
multiple matches rather than guessing.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CONFIG_DIR = Path.home() / ".config" / "asf-security" / "glasswing"
CLIENT_SECRET_PATH = CONFIG_DIR / "oauth_client_secret.json"
TOKEN_PATH = CONFIG_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def col_letter(idx_zero_based: int) -> str:
    """Convert a zero-based column index to A1 letter form (0 -> A, 26 -> AA)."""
    n = idx_zero_based + 1
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def load_credentials() -> Credentials:
    if not CLIENT_SECRET_PATH.exists():
        sys.exit(
            f"OAuth client secret not found at {CLIENT_SECRET_PATH}.\n"
            "Run 'sheets_writer.py setup' first, or see the SKILL.md "
            "for one-time OAuth setup instructions."
        )
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        return creds
    sys.exit(
        "No valid OAuth token. Run 'sheets_writer.py setup' to "
        "authorize this machine."
    )


def get_service():
    creds = load_credentials()
    return build("sheets", "v4", credentials=creds)


CANNED_SHEET = "Canned Responses"
CANNED_HEADERS = [
    "Date Added",
    "Topic",
    "Question pattern",
    "Response",
    "Author",
    "Notes",
]


def cmd_setup() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CLIENT_SECRET_PATH.exists():
        sys.exit(
            f"Place your OAuth client secret JSON at {CLIENT_SECRET_PATH} "
            "before running setup. See SKILL.md for how to create one in "
            "the Google Cloud Console."
        )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH), SCOPES
    )
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    TOKEN_PATH.write_text(creds.to_json())
    TOKEN_PATH.chmod(0o600)
    print(f"OAuth token saved to {TOKEN_PATH} (mode 0600).")


def fetch_sheet_grid(service, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_name, majorDimension="ROWS")
        .execute()
    )
    return resp.get("values", [])


def find_unique_row(
    grid: list[list[str]], match_column: str, match_value: str
) -> tuple[int, list[str]]:
    if not grid:
        sys.exit("Sheet is empty.")
    header = grid[0]
    if match_column not in header:
        sys.exit(
            f"Match column '{match_column}' not found in header. "
            f"Available: {header}"
        )
    col_idx = header.index(match_column)
    hits = []
    for row_idx, row in enumerate(grid[1:], start=1):
        if col_idx < len(row) and row[col_idx] == match_value:
            hits.append((row_idx, row))
    if not hits:
        sys.exit(f"No row matches {match_column}={match_value!r}.")
    if len(hits) > 1:
        sys.exit(
            f"Multiple rows match {match_column}={match_value!r}: "
            f"row numbers {[h[0] for h in hits]}. Refusing to update "
            "ambiguously."
        )
    return hits[0]


def cmd_apply(args: argparse.Namespace) -> None:
    updates = json.loads(Path(args.updates).read_text())
    if not isinstance(updates, list):
        sys.exit("Updates JSON must be a list of objects.")
    service = get_service()

    grid_cache: dict[str, list[list[str]]] = {}
    api_data = []
    diff_lines = []

    for i, update in enumerate(updates):
        sheet = update["sheet"]
        match = update["match"]
        sets = update["set"]
        grid = grid_cache.setdefault(
            sheet, fetch_sheet_grid(service, args.spreadsheet_id, sheet)
        )
        row_idx, row = find_unique_row(grid, match["column"], match["value"])
        header = grid[0]
        for set_col, new_value in sets.items():
            if set_col not in header:
                sys.exit(
                    f"Update #{i}: set column '{set_col}' not in "
                    f"header of sheet '{sheet}'."
                )
            set_col_idx = header.index(set_col)
            current = row[set_col_idx] if set_col_idx < len(row) else ""
            a1 = f"{sheet}!{col_letter(set_col_idx)}{row_idx + 1}"
            diff_lines.append(
                f"  {sheet} row {row_idx + 1} ({match['column']}="
                f"{match['value']!r}) · {set_col}: "
                f"{current!r} -> {str(new_value)!r}   [{a1}]"
            )
            api_data.append({"range": a1, "values": [[new_value]]})

    if not api_data:
        print("No cell changes computed.")
        return

    print("Planned cell updates:")
    for line in diff_lines:
        print(line)

    if args.dry_run:
        print(f"\nDry run — no changes written. ({len(api_data)} cells would change.)")
        return

    resp = (
        service.spreadsheets()
        .values()
        .batchUpdate(
            spreadsheetId=args.spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": api_data},
        )
        .execute()
    )
    print(
        f"\nApplied. totalUpdatedCells={resp.get('totalUpdatedCells')} "
        f"totalUpdatedRows={resp.get('totalUpdatedRows')} "
        f"totalUpdatedRanges={len(resp.get('responses', []))}"
    )


def cmd_init_canned(args: argparse.Namespace) -> None:
    service = get_service()
    meta = service.spreadsheets().get(spreadsheetId=args.spreadsheet_id).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if CANNED_SHEET in existing:
        print(f"Sheet '{CANNED_SHEET}' already exists; nothing to do.")
        return
    if args.dry_run:
        print(
            f"Would create sheet '{CANNED_SHEET}' with header row: "
            f"{CANNED_HEADERS}"
        )
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=args.spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": CANNED_SHEET,
                            "gridProperties": {"frozenRowCount": 1},
                        }
                    }
                }
            ]
        },
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=f"{CANNED_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": [CANNED_HEADERS]},
    ).execute()
    print(f"Created sheet '{CANNED_SHEET}' with header row and frozen header.")


def cmd_append_canned(args: argparse.Namespace) -> None:
    entries = json.loads(Path(args.entries).read_text())
    if not isinstance(entries, list):
        sys.exit("Entries JSON must be a list of objects.")
    today = datetime.date.today().isoformat()
    required = ("topic", "question_pattern", "response", "author")
    rows = []
    for i, entry in enumerate(entries):
        for k in required:
            if k not in entry:
                sys.exit(f"Entry #{i} missing required field: {k!r}")
        rows.append(
            [
                today,
                entry["topic"],
                entry["question_pattern"],
                entry["response"],
                entry["author"],
                entry.get("notes", ""),
            ]
        )
    print(f"Planned append to '{CANNED_SHEET}' ({len(rows)} row(s)):")
    for idx, row in enumerate(rows):
        print(f"  Entry #{idx}:")
        for col, val in zip(CANNED_HEADERS, row):
            display = val if len(val) <= 80 else val[:77] + "..."
            print(f"    {col}: {display!r}")
    if args.dry_run:
        print(f"\nDry run — no changes written.")
        return
    service = get_service()
    resp = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=args.spreadsheet_id,
            range=CANNED_SHEET,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        .execute()
    )
    updated_range = resp.get("updates", {}).get("updatedRange", "<unknown>")
    print(f"\nAppended {len(rows)} row(s). updatedRange={updated_range}")


PMCS_SHEET = "PMCs"
PMCS_REQUIRED_FIELDS = ("PMC Name", "PMC Slug")


def cmd_append_pmc(args: argparse.Namespace) -> None:
    """Append one or more new PMC rows to the 'PMCs' sheet.

    Entries JSON is a list of objects keyed by PMC-sheet column header.
    'PMC Name' and 'PMC Slug' are required; everything else is optional.
    Unknown column keys abort. Duplicate-slug appends abort
    (use 'apply' to update an existing row instead).
    """
    entries = json.loads(Path(args.entries).read_text())
    if not isinstance(entries, list):
        sys.exit("Entries JSON must be a list of objects.")

    service = get_service()
    grid = fetch_sheet_grid(service, args.spreadsheet_id, PMCS_SHEET)
    if not grid:
        sys.exit(f"'{PMCS_SHEET}' sheet is empty (no header row).")
    header = grid[0]
    slug_col_idx = header.index("PMC Slug") if "PMC Slug" in header else None
    if slug_col_idx is None:
        sys.exit(f"'{PMCS_SHEET}' header has no 'PMC Slug' column.")
    existing_slugs = {
        (row[slug_col_idx].strip() if slug_col_idx < len(row) else ""): r_idx
        for r_idx, row in enumerate(grid[1:], start=2)
    }

    rows: list[list[str]] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            sys.exit(f"Entry #{i} must be a JSON object.")
        for k in PMCS_REQUIRED_FIELDS:
            if k not in entry or not str(entry[k]).strip():
                sys.exit(f"Entry #{i} missing required field: {k!r}")
        unknown = [k for k in entry.keys() if k not in header]
        if unknown:
            sys.exit(
                f"Entry #{i} has unknown columns: {unknown}. "
                f"Available: {header}"
            )
        slug = str(entry["PMC Slug"]).strip()
        if slug in existing_slugs and slug != "":
            sys.exit(
                f"Entry #{i}: PMC Slug {slug!r} already exists at "
                f"{PMCS_SHEET} row {existing_slugs[slug]}. Use 'apply' to "
                f"update it instead of appending a duplicate."
            )
        rows.append([str(entry.get(col, "")) for col in header])

    print(f"Planned append to '{PMCS_SHEET}' ({len(rows)} new row(s)):")
    for idx, row in enumerate(rows):
        entry = entries[idx]
        print(f"  Entry #{idx} — {entry.get('PMC Name', '?')} ({entry.get('PMC Slug', '?')}):")
        for col, val in zip(header, row):
            if not val:
                continue
            display = val if len(val) <= 80 else val[:77] + "..."
            print(f"    {col}: {display!r}")
    if args.dry_run:
        print(f"\nDry run — no changes written. ({len(rows)} rows would be appended.)")
        return
    resp = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=args.spreadsheet_id,
            range=PMCS_SHEET,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        .execute()
    )
    updated_range = resp.get("updates", {}).get("updatedRange", "<unknown>")
    print(f"\nAppended {len(rows)} row(s) to '{PMCS_SHEET}'. updatedRange={updated_range}")


STATUS_SHEET = "Status"

# Pipeline states in progression order. Order matters: the state-detection
# function picks the latest applicable state, and the colors render
# red->green by state index.
PIPELINE_STATES = [
    "Pre-flight",
    "Ready",
    "Submitted",
    "Triaging",
    "Delivered",
]

STATE_COLOR = {
    "Pre-flight": {"red": 0.96, "green": 0.78, "blue": 0.78},  # light red
    "Ready":      {"red": 1.00, "green": 0.93, "blue": 0.70},  # yellow
    "Submitted":  {"red": 0.84, "green": 0.95, "blue": 0.74},  # light green
    "Triaging":   {"red": 0.62, "green": 0.86, "blue": 0.62},  # medium green
    "Delivered":  {"red": 0.40, "green": 0.74, "blue": 0.42},  # dark green
}

MODEL_COLOR = {
    "Verified":    {"red": 0.70, "green": 0.90, "blue": 0.70},
    "Nominated":   {"red": 1.00, "green": 0.93, "blue": 0.70},
    "Missing":     {"red": 0.96, "green": 0.78, "blue": 0.78},
}


_PR_URL_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+")


def parse_pr_urls(cell_text: str) -> list[str]:
    """Extract every github.com/<owner>/<repo>/pull/<n> URL from a cell.

    The PR/Issues cell is a newline-separated list of references; each
    line typically has the URL followed by free-text description
    ('discoverability PR', 'Email reply sent 2026-05-14', etc.). We
    extract every PR URL we find via regex; non-PR lines (email
    references) are ignored.
    """
    if not cell_text:
        return []
    urls = []
    for match in _PR_URL_RE.finditer(cell_text):
        url = match.group(0)
        if url not in urls:
            urls.append(url)
    return urls


def query_pr_states(urls: list[str]) -> dict:
    """Return {'open': n, 'merged': n, 'closed': n, 'errors': [...]}.

    Uses `gh pr view --json state` per URL. The state values are
    OPEN, MERGED, or CLOSED (gh treats merged PRs as a distinct
    state from closed-but-not-merged). Best-effort: a failure on
    one URL (auth, network, deleted PR) is recorded as an error
    but doesn't block the rest.
    """
    result = {"open": 0, "merged": 0, "closed": 0, "errors": []}
    for url in urls:
        try:
            p = subprocess.run(
                ["gh", "pr", "view", url, "--json", "state"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if p.returncode != 0:
                result["errors"].append(f"{url}: gh exit {p.returncode}: {p.stderr.strip()[:80]}")
                continue
            data = json.loads(p.stdout)
            state = data.get("state", "").upper()
            if state == "MERGED":
                result["merged"] += 1
            elif state == "OPEN":
                result["open"] += 1
            elif state == "CLOSED":
                result["closed"] += 1
            else:
                result["errors"].append(f"{url}: unknown state {state!r}")
        except Exception as e:
            result["errors"].append(f"{url}: {e}")
    return result


def compute_pmc_status(row: list[str], col_idx: dict[str, int]) -> dict:
    """Derive the pipeline state of a single PMC row."""
    def cell(name: str) -> str:
        idx = col_idx.get(name)
        if idx is None or idx >= len(row):
            return ""
        return (row[idx] or "").strip()

    pmc = cell("PMC Name")
    slug = cell("PMC Slug")
    requested_date = cell("Request date")
    repos_requested = cell("Repositories requested")
    repos_submitted = cell("Repositories submitted")
    contact = cell("Contact Person")
    backup = cell("Backup contact")
    model = cell("Security Model")
    model_verified = cell("Security model verified")
    submitted_date = cell("Date scan requested")
    received_date = cell("Date scan received")
    forwarded_date = cell("Forwarded scan to PMC")
    pr_issues = cell("PR/Issues")
    notes = cell("Notes")

    # State machine.
    if forwarded_date:
        state = "Delivered"
    elif received_date:
        state = "Triaging"
    elif submitted_date:
        state = "Submitted"
    elif model_verified:
        state = "Ready"
    else:
        state = "Pre-flight"

    if model_verified:
        model_status = "Verified"
    elif model:
        model_status = "Nominated"
    else:
        model_status = "Missing"

    repo_count = len([r for r in repos_requested.splitlines() if r.strip() and not r.strip().startswith("#")])

    pr_urls = parse_pr_urls(pr_issues)
    pr_state = query_pr_states(pr_urls) if pr_urls else {"open": 0, "merged": 0, "closed": 0, "errors": []}

    return {
        "pmc": pmc,
        "slug": slug,
        "state": state,
        "model_status": model_status,
        "repos_requested_count": repo_count,
        "repos_requested": repos_requested,
        "repos_submitted": repos_submitted,
        "request_date": requested_date,
        "model_verified_date": model_verified,
        "submitted_date": submitted_date,
        "received_date": received_date,
        "forwarded_date": forwarded_date,
        "contact": contact,
        "backup": backup,
        "model": model,
        "pr_issues": pr_issues,
        "pr_urls": pr_urls,
        "pr_open": pr_state["open"],
        "pr_merged": pr_state["merged"],
        "pr_closed": pr_state["closed"],
        "pr_errors": pr_state["errors"],
        "notes": notes,
    }


def cmd_build_status_tab(args: argparse.Namespace) -> None:
    service = get_service()
    today = datetime.date.today().isoformat()

    # 1. Read source data.
    grid = fetch_sheet_grid(service, args.spreadsheet_id, "PMCs")
    if not grid or len(grid) < 2:
        sys.exit("PMCs sheet has no data rows.")
    header = grid[0]
    col_idx = {h: i for i, h in enumerate(header)}
    rows = grid[1:]

    entries = []
    for row in rows:
        if (row[col_idx.get("Scan Requested", -1)].strip() if col_idx.get("Scan Requested", -1) < len(row) else "") != "Yes":
            continue
        entries.append(compute_pmc_status(row, col_idx))

    # Sort in-flight by state index (most progressed first), then by request_date.
    state_order = {s: i for i, s in enumerate(PIPELINE_STATES)}
    in_flight = sorted(
        [e for e in entries if e["state"] != "Delivered"],
        key=lambda e: (-state_order.get(e["state"], 0), e["request_date"]),
    )
    completed = sorted(
        [e for e in entries if e["state"] == "Delivered"],
        key=lambda e: e["forwarded_date"],
    )

    # 2. Get or create Status sheet.
    meta = service.spreadsheets().get(spreadsheetId=args.spreadsheet_id).execute()
    sheet_meta = next(
        (s for s in meta.get("sheets", []) if s["properties"]["title"] == STATUS_SHEET),
        None,
    )
    if sheet_meta is None:
        if args.dry_run:
            print(f"Would create sheet '{STATUS_SHEET}'.")
            sheet_id = 0  # placeholder; no API calls in dry-run
        else:
            resp = service.spreadsheets().batchUpdate(
                spreadsheetId=args.spreadsheet_id,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {
                                    "title": STATUS_SHEET,
                                    "gridProperties": {"frozenRowCount": 1},
                                }
                            }
                        }
                    ]
                },
            ).execute()
            sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    else:
        sheet_id = sheet_meta["properties"]["sheetId"]

    # 3. Clear existing content (unless dry-run).
    if not args.dry_run and sheet_meta is not None:
        service.spreadsheets().values().clear(
            spreadsheetId=args.spreadsheet_id,
            range=STATUS_SHEET,
        ).execute()

    # 4. Build the values payload and the per-row color requests.
    values: list[list] = []
    color_requests: list[dict] = []

    def append_row(row: list, color: dict | None = None, col_span: int = 11):
        row_index = len(values)
        values.append(row)
        if color is not None:
            color_requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index,
                            "endRowIndex": row_index + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": col_span,
                        },
                        "cell": {
                            "userEnteredFormat": {"backgroundColor": color}
                        },
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            )

    # Header section.
    append_row([f"Glasswing scan pipeline — status as of {today}"])
    append_row([f"Source: PMCs sheet · regenerated by sheets_writer.py build-status-tab"])
    append_row([""])

    # Program-wide rollup.
    total_pmcs = len(entries)
    total_open = sum(e["pr_open"] for e in entries)
    total_merged = sum(e["pr_merged"] for e in entries)
    total_closed = sum(e["pr_closed"] for e in entries)
    total_prs = total_open + total_merged + total_closed
    pmcs_with_prs = len([e for e in entries if (e["pr_open"] + e["pr_merged"] + e["pr_closed"]) > 0])
    append_row(["PROGRAM TOTALS"])
    append_row(["PMCs opted in (Scan Requested = Yes)", total_pmcs])
    append_row(["PMCs with at least one PR opened", pmcs_with_prs])
    append_row(["PRs opened (not yet merged)", total_open])
    append_row(["PRs merged", total_merged])
    append_row(["PRs total", total_prs])
    if total_closed:
        append_row([f"  (of which closed without merge: {total_closed})"])
    append_row([""])

    # In-flight table.
    append_row(["IN FLIGHT"])
    append_row(
        [
            "PMC",
            "Slug",
            "Status",
            "Repos requested",
            "Model",
            "PRs opened (not yet merged)",
            "PRs merged",
            "PRs total",
            "Request date",
            "Last touch (model verified)",
            "Notes / PR / Issues",
        ]
    )
    if not in_flight:
        append_row(["(none in flight)"])
    for e in in_flight:
        pr_total = e["pr_open"] + e["pr_merged"] + e["pr_closed"]
        prs_open_cell = e["pr_open"] if e["pr_urls"] else "—"
        prs_merged_cell = e["pr_merged"] if e["pr_urls"] else "—"
        prs_total_cell = pr_total if e["pr_urls"] else "—"
        append_row(
            [
                e["pmc"],
                e["slug"],
                e["state"],
                e["repos_requested_count"],
                e["model_status"],
                prs_open_cell,
                prs_merged_cell,
                prs_total_cell,
                e["request_date"],
                e["model_verified_date"] or "—",
                (e["pr_issues"] or "") + (("  ·  " + e["notes"]) if e["notes"] else ""),
            ],
            color=STATE_COLOR[e["state"]],
        )

    append_row([""])

    # Completed table.
    append_row(["COMPLETED"])
    append_row(
        [
            "PMC",
            "Slug",
            "Repos submitted",
            "PRs opened (not yet merged)",
            "PRs merged",
            "PRs total",
            "Submitted",
            "Received",
            "Forwarded",
            "Days end-to-end",
        ]
    )
    if not completed:
        append_row(["(none yet)"])
    for e in completed:
        try:
            d1 = datetime.date.fromisoformat(e["request_date"])
            d2 = datetime.date.fromisoformat(e["forwarded_date"])
            e2e = (d2 - d1).days
        except Exception:
            e2e = ""
        pr_total = e["pr_open"] + e["pr_merged"] + e["pr_closed"]
        prs_open_cell = e["pr_open"] if e["pr_urls"] else "—"
        prs_merged_cell = e["pr_merged"] if e["pr_urls"] else "—"
        prs_total_cell = pr_total if e["pr_urls"] else "—"
        append_row(
            [
                e["pmc"],
                e["slug"],
                len([r for r in e["repos_submitted"].splitlines() if r.strip() and not r.strip().startswith("#")]),
                prs_open_cell,
                prs_merged_cell,
                prs_total_cell,
                e["submitted_date"] or "—",
                e["received_date"] or "—",
                e["forwarded_date"] or "—",
                e2e,
            ],
            color=STATE_COLOR["Delivered"],
        )

    append_row([""])

    # Timeline data — wide format so a scatter chart can plot:
    # X = date (any column 2..6), Y = PMC (column 1), series-color by
    # milestone column. Missing milestones are blank cells (chart
    # doesn't plot blanks).
    append_row(["TIMELINE DATA (wide format — chart-ready: X=date columns, Y=PMC)"])
    append_row(["PMC", "Requested", "Ready", "Submitted", "Received", "Forwarded"])
    timeline_start = len(values)
    timeline_data_first_row = timeline_start  # for chart range
    for e in sorted(entries, key=lambda x: x["request_date"]):
        append_row(
            [
                e["pmc"],
                e["request_date"] or "",
                e["model_verified_date"] or "",
                e["submitted_date"] or "",
                e["received_date"] or "",
                e["forwarded_date"] or "",
            ]
        )
    timeline_end = len(values)
    timeline_data_last_row = timeline_end - 1

    # 5. Write values + apply colors.
    if args.dry_run:
        print(f"Would write {len(values)} rows to '{STATUS_SHEET}'; "
              f"in-flight={len(in_flight)}, completed={len(completed)}, "
              f"timeline-events={timeline_end - timeline_start}.")
        return

    a1_end_col = col_letter(max(len(r) for r in values) - 1)
    a1_range = f"{STATUS_SHEET}!A1:{a1_end_col}{len(values)}"
    service.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=a1_range,
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    # Bold header rows (line 1, "IN FLIGHT", "COMPLETED", "TIMELINE DATA"
    # banner rows + the two table header rows).
    bold_request = lambda row_idx, cols=8: {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_idx,
                "endRowIndex": row_idx + 1,
                "startColumnIndex": 0,
                "endColumnIndex": cols,
            },
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }
    }
    bold_rows = [0, 3, 4]  # Title + IN FLIGHT banner + IN FLIGHT header.
    # Find COMPLETED + TIMELINE DATA banners by scanning values.
    for i, row in enumerate(values):
        if row and row[0] in ("COMPLETED", "TIMELINE DATA (one row per milestone reached)"):
            bold_rows.append(i)
            bold_rows.append(i + 1)  # The table header right below.

    requests = [bold_request(i) for i in sorted(set(bold_rows))]
    requests.extend(color_requests)

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=args.spreadsheet_id,
            body={"requests": requests},
        ).execute()

    print(
        f"Status tab refreshed: {len(in_flight)} in flight, "
        f"{len(completed)} completed, "
        f"{timeline_end - timeline_start} timeline events. "
        f"Chart: not embedded (create from the TIMELINE DATA block manually "
        f"— scatter chart with X=Date, Y=PMC, series-color by Milestone)."
    )


def cmd_rename_column(args: argparse.Namespace) -> None:
    service = get_service()
    grid = fetch_sheet_grid(service, args.spreadsheet_id, args.sheet)
    if not grid:
        sys.exit(f"Sheet '{args.sheet}' has no header row.")
    header = grid[0]
    if args.new in header:
        sys.exit(f"Header '{args.new}' already exists; refusing to overwrite.")
    if args.old not in header:
        sys.exit(
            f"Header '{args.old}' not found in sheet '{args.sheet}'. "
            f"Available: {header}"
        )
    col_idx = header.index(args.old)
    a1 = f"{args.sheet}!{col_letter(col_idx)}1"
    print(f"Planned rename: {a1}  '{args.old}' -> '{args.new}'")
    if args.dry_run:
        print("Dry run — no changes written.")
        return
    service.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=a1,
        valueInputOption="RAW",
        body={"values": [[args.new]]},
    ).execute()
    print(f"Renamed column at {a1}.")


def cmd_insert_column(args: argparse.Namespace) -> None:
    service = get_service()
    meta = service.spreadsheets().get(spreadsheetId=args.spreadsheet_id).execute()
    sheet_meta = next(
        (s for s in meta.get("sheets", []) if s["properties"]["title"] == args.sheet),
        None,
    )
    if sheet_meta is None:
        sys.exit(f"Sheet '{args.sheet}' not found.")
    sheet_id = sheet_meta["properties"]["sheetId"]
    grid = fetch_sheet_grid(service, args.spreadsheet_id, args.sheet)
    if not grid:
        sys.exit(f"Sheet '{args.sheet}' has no header row; cannot insert.")
    header = grid[0]
    if args.header in header:
        print(
            f"Header '{args.header}' already exists at column "
            f"{col_letter(header.index(args.header))}; skipping."
        )
        return
    if args.after not in header:
        sys.exit(
            f"Anchor column '{args.after}' not found in header. Available: {header}"
        )
    insert_idx = header.index(args.after) + 1
    a1_new = f"{args.sheet}!{col_letter(insert_idx)}1"
    print(
        f"Planned: insert new column at index {insert_idx} (after "
        f"'{args.after}'); write header '{args.header}' to {a1_new}."
    )
    if args.dry_run:
        print("Dry run — no changes written.")
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=args.spreadsheet_id,
        body={
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": insert_idx,
                            "endIndex": insert_idx + 1,
                        },
                        "inheritFromBefore": True,
                    }
                }
            ]
        },
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=a1_new,
        valueInputOption="RAW",
        body={"values": [[args.header]]},
    ).execute()
    print(f"Inserted column '{args.header}' at {a1_new}.")


def cmd_add_columns(args: argparse.Namespace) -> None:
    service = get_service()
    grid = fetch_sheet_grid(service, args.spreadsheet_id, args.sheet)
    if not grid:
        sys.exit(f"Sheet '{args.sheet}' is empty; cannot extend header.")
    header = list(grid[0])
    additions = []
    for h in args.headers:
        if h in header:
            print(f"Header '{h}' already exists at column {col_letter(header.index(h))}; skipping.")
            continue
        additions.append(h)
    if not additions:
        print("No new columns to add.")
        return
    start_idx = len(header)
    a1 = f"{args.sheet}!{col_letter(start_idx)}1:{col_letter(start_idx + len(additions) - 1)}1"
    print(f"Planned header writes to {a1}: {additions}")
    if args.dry_run:
        print("Dry run — no changes written.")
        return
    service.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=a1,
        valueInputOption="RAW",
        body={"values": [additions]},
    ).execute()
    print(f"Added {len(additions)} column(s) at {a1}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Run OAuth installed-app flow once.")

    apply_p = sub.add_parser("apply", help="Apply row updates from a JSON file.")
    apply_p.add_argument("--spreadsheet-id", required=True)
    apply_p.add_argument("--updates", required=True, type=Path)
    apply_p.add_argument("--dry-run", action="store_true")

    init_p = sub.add_parser(
        "init-canned-tab",
        help=f"Create the '{CANNED_SHEET}' sheet with its header row (idempotent).",
    )
    init_p.add_argument("--spreadsheet-id", required=True)
    init_p.add_argument("--dry-run", action="store_true")

    appc_p = sub.add_parser(
        "append-canned",
        help=f"Append one or more canned-response rows to '{CANNED_SHEET}'.",
    )
    appc_p.add_argument("--spreadsheet-id", required=True)
    appc_p.add_argument(
        "--entries",
        required=True,
        type=Path,
        help="Path to JSON list of {topic, question_pattern, response, author, notes?}.",
    )
    appc_p.add_argument("--dry-run", action="store_true")

    apppmc_p = sub.add_parser(
        "append-pmc",
        help=f"Append one or more new PMC rows to '{PMCS_SHEET}'. Errors on duplicate slug.",
    )
    apppmc_p.add_argument("--spreadsheet-id", required=True)
    apppmc_p.add_argument(
        "--entries",
        required=True,
        type=Path,
        help="Path to JSON list of objects keyed by PMC-sheet column header. 'PMC Name' + 'PMC Slug' required.",
    )
    apppmc_p.add_argument("--dry-run", action="store_true")

    status_p = sub.add_parser(
        "build-status-tab",
        help="Create or refresh the 'Status' tab with in-flight + completed tables and timeline data, color-coded by pipeline state.",
    )
    status_p.add_argument("--spreadsheet-id", required=True)
    status_p.add_argument("--dry-run", action="store_true")

    rencol_p = sub.add_parser(
        "rename-column",
        help="Rename a column header (cell at row 1 of the named column).",
    )
    rencol_p.add_argument("--spreadsheet-id", required=True)
    rencol_p.add_argument("--sheet", required=True, help="Sheet name (e.g. 'PMCs').")
    rencol_p.add_argument("--old", required=True, help="Current header text.")
    rencol_p.add_argument("--new", required=True, help="New header text.")
    rencol_p.add_argument("--dry-run", action="store_true")

    inscol_p = sub.add_parser(
        "insert-column",
        help="Insert a new column at a specific position in a sheet (idempotent).",
    )
    inscol_p.add_argument("--spreadsheet-id", required=True)
    inscol_p.add_argument("--sheet", required=True, help="Sheet name (e.g. 'PMCs').")
    inscol_p.add_argument(
        "--after",
        required=True,
        help="Header of the column the new one should be inserted directly after.",
    )
    inscol_p.add_argument("--header", required=True, help="Header for the new column.")
    inscol_p.add_argument("--dry-run", action="store_true")

    addcol_p = sub.add_parser(
        "add-columns",
        help="Append new column headers to an existing sheet (idempotent per header).",
    )
    addcol_p.add_argument("--spreadsheet-id", required=True)
    addcol_p.add_argument("--sheet", required=True, help="Sheet name (e.g. 'PMCs').")
    addcol_p.add_argument(
        "--headers",
        required=True,
        nargs="+",
        help="One or more header strings to append (in order).",
    )
    addcol_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "setup":
        cmd_setup()
    elif args.cmd == "apply":
        cmd_apply(args)
    elif args.cmd == "init-canned-tab":
        cmd_init_canned(args)
    elif args.cmd == "append-canned":
        cmd_append_canned(args)
    elif args.cmd == "append-pmc":
        cmd_append_pmc(args)
    elif args.cmd == "add-columns":
        cmd_add_columns(args)
    elif args.cmd == "insert-column":
        cmd_insert_column(args)
    elif args.cmd == "rename-column":
        cmd_rename_column(args)
    elif args.cmd == "build-status-tab":
        cmd_build_status_tab(args)


if __name__ == "__main__":
    main()
