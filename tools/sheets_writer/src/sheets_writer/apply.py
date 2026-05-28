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
"""Row-level apply — diff builder + Sheets API batch update."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sheets_writer.columns import col_letter, find_unique_row
from sheets_writer.sheets_api import fetch_sheet_grid, get_service


def build_apply_plan(
    updates: list[dict], grids: dict[str, list[list[str]]]
) -> tuple[list[dict], list[str]]:
    """Compute the cell-write payload + diff lines from a parsed updates list.

    ``grids`` maps sheet name to its full grid (header + rows). Pure
    function: no API calls. Returns ``(api_data, diff_lines)`` where
    ``api_data`` is the ``values.batchUpdate``-shaped ``data`` payload.
    """
    api_data: list[dict] = []
    diff_lines: list[str] = []

    for i, update in enumerate(updates):
        sheet = update["sheet"]
        match = update["match"]
        sets = update["set"]
        if sheet not in grids:
            raise KeyError(f"Update #{i} references sheet {sheet!r} not in grids dict")
        grid = grids[sheet]
        row_idx, row = find_unique_row(grid, match["column"], match["value"])
        header = grid[0]
        for set_col, new_value in sets.items():
            if set_col not in header:
                raise ValueError(
                    f"Update #{i}: set column {set_col!r} not in header of sheet {sheet!r}."
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

    return api_data, diff_lines


def cmd_apply(args: argparse.Namespace) -> None:
    updates = json.loads(Path(args.updates).read_text())
    if not isinstance(updates, list):
        sys.exit("Updates JSON must be a list of objects.")
    service = get_service()

    # Fetch every distinct sheet referenced by the updates exactly once.
    grids: dict[str, list[list[str]]] = {}
    for u in updates:
        sheet = u["sheet"]
        if sheet not in grids:
            grids[sheet] = fetch_sheet_grid(service, args.spreadsheet_id, sheet)

    try:
        api_data, diff_lines = build_apply_plan(updates, grids)
    except (KeyError, ValueError) as e:
        sys.exit(str(e))

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
