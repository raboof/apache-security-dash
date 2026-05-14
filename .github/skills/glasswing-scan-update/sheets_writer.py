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
          "Date Requested": "2026-05-14",
          "Status": "scan queued"
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

    args = parser.parse_args()
    if args.cmd == "setup":
        cmd_setup()
    elif args.cmd == "apply":
        cmd_apply(args)
    elif args.cmd == "init-canned-tab":
        cmd_init_canned(args)
    elif args.cmd == "append-canned":
        cmd_append_canned(args)


if __name__ == "__main__":
    main()
