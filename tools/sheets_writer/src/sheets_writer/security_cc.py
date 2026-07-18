# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""backfill-security-cc — write the deterministic 'PMC team Cc' column.

For every PMC row, resolve the PMC-side channel a scan-result forward should CC
(its own ``security@<pmc>.apache.org`` when the project runs a security team,
else its ``private@<pmc>.apache.org`` list) and write it into the ``PMC team Cc``
column of the PMCs sheet. The determination is deterministic — it comes from
``whimsy_lookup.pmc_security_info`` reading apache/security-site's
``project-coordinates.json`` (the authoritative record of which PMCs have
registered a ``security@<pmc>`` alias), the same helper the response/triage
pipeline uses. No WebFetch guessing.

Re-runnable: creates the column when missing (inserted after ``Report
recipients``, else appended), and refreshes every cell on each run so the column
tracks changes to coordinates.json over time.
"""

from __future__ import annotations

import argparse
import sys

from whimsy_lookup.fetch import FetchError, fetch_security_coordinates
from whimsy_lookup.security_info import pmc_security_info

from sheets_writer import PMCS_SHEET
from sheets_writer.columns import col_letter
from sheets_writer.sheets_api import fetch_sheet_grid, get_service

TEAM_CC_HEADER = "PMC team Cc"
SLUG_HEADER = "PMC Slug"
# The new column is inserted directly after the To:-recipient column so the
# PMC-side CC sits next to the PMC-side recipients. Appended at the end if the
# anchor isn't present.
ANCHOR_HEADER = "Report recipients"


def team_cc_values(header: list[str], rows: list[list[str]], coordinates: dict) -> list[str]:
    """Resolve the ``PMC team Cc`` value for each data row (pure).

    One value per row in ``rows``, aligned by position. A row with a blank
    ``PMC Slug`` yields ``""`` (nothing to resolve). Raises ``ValueError`` if the
    sheet has no ``PMC Slug`` column.
    """
    if SLUG_HEADER not in header:
        raise ValueError(f"Sheet has no '{SLUG_HEADER}' column. Header: {header}")
    slug_idx = header.index(SLUG_HEADER)
    values: list[str] = []
    for row in rows:
        slug = (row[slug_idx] if slug_idx < len(row) else "").strip()
        values.append(pmc_security_info(coordinates, slug)["team_cc"] if slug else "")
    return values


def build_backfill_diff(
    header: list[str], rows: list[list[str]], values: list[str]
) -> tuple[list[str], int]:
    """Diff lines for the rows whose ``PMC team Cc`` cell would change (pure).

    Compares each resolved value against the current cell (``""`` when the
    column is new or the cell is empty). Returns ``(diff_lines, changed_count)``.
    """
    col_idx = header.index(TEAM_CC_HEADER) if TEAM_CC_HEADER in header else None
    slug_idx = header.index(SLUG_HEADER)
    diff_lines: list[str] = []
    for i, (row, new_value) in enumerate(zip(rows, values, strict=True)):
        current = ""
        if col_idx is not None and col_idx < len(row):
            current = row[col_idx]
        if current == new_value:
            continue
        slug = (row[slug_idx] if slug_idx < len(row) else "").strip() or "(no slug)"
        # +2: 1 for the header row, 1 for 1-based sheet rows.
        diff_lines.append(f"  row {i + 2} ({slug}): {current!r} -> {new_value!r}")
    return diff_lines, len(diff_lines)


def _pmcs_sheet_id(service, spreadsheet_id: str) -> int:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_meta = next(
        (s for s in meta.get("sheets", []) if s["properties"]["title"] == PMCS_SHEET),
        None,
    )
    if sheet_meta is None:
        sys.exit(f"Sheet '{PMCS_SHEET}' not found.")
    return sheet_meta["properties"]["sheetId"]


def cmd_backfill_security_cc(args: argparse.Namespace) -> None:
    service = get_service()
    try:
        coordinates = fetch_security_coordinates()
    except FetchError as e:
        sys.exit(str(e))

    grid = fetch_sheet_grid(service, args.spreadsheet_id, PMCS_SHEET)
    if not grid:
        sys.exit(f"Sheet '{PMCS_SHEET}' has no header row.")
    header = list(grid[0])
    rows = grid[1:]

    try:
        values = team_cc_values(header, rows, coordinates)
    except ValueError as e:
        sys.exit(str(e))

    diff_lines, changed = build_backfill_diff(header, rows, values)

    column_exists = TEAM_CC_HEADER in header
    if column_exists:
        target_idx = header.index(TEAM_CC_HEADER)
        insert_needed = False
        where = f"existing column {col_letter(target_idx)}"
    elif ANCHOR_HEADER in header:
        target_idx = header.index(ANCHOR_HEADER) + 1
        insert_needed = True
        where = f"new column inserted after '{ANCHOR_HEADER}' (column {col_letter(target_idx)})"
    else:
        target_idx = len(header)
        insert_needed = False  # appending past the last column auto-extends
        where = f"new column appended at {col_letter(target_idx)}"

    col = col_letter(target_idx)
    print(f"backfill-security-cc — '{TEAM_CC_HEADER}' on '{PMCS_SHEET}' ({where}).")
    print(f"{len(rows)} PMC row(s); {changed} cell(s) would change.")
    if diff_lines:
        print("Changes:")
        for line in diff_lines:
            print(line)
    else:
        print("No changes — every cell already matches the deterministic value.")

    if args.dry_run:
        print("\nDry run — no changes written.")
        return
    if column_exists and not diff_lines:
        # Column already present and every cell matches — nothing to write.
        print("\nNothing to write.")
        return

    if insert_needed:
        sheet_id = _pmcs_sheet_id(service, args.spreadsheet_id)
        service.spreadsheets().batchUpdate(
            spreadsheetId=args.spreadsheet_id,
            body={
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": target_idx,
                                "endIndex": target_idx + 1,
                            },
                            "inheritFromBefore": True,
                        }
                    }
                ]
            },
        ).execute()

    column_cells = [[TEAM_CC_HEADER]] + [[v] for v in values]
    end_row = len(column_cells)
    service.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=f"{PMCS_SHEET}!{col}1:{col}{end_row}",
        valueInputOption="RAW",
        body={"values": column_cells},
    ).execute()
    print(f"\nWrote '{TEAM_CC_HEADER}' for {len(values)} PMC row(s) at column {col}.")
