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
"""Append rows to the PMCs sheet — dup-slug protected."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sheets_writer import PMCS_REQUIRED_FIELDS, PMCS_SHEET
from sheets_writer.sheets_api import fetch_sheet_grid, get_service


def build_pmc_rows(
    entries: list[dict],
    header: list[str],
    existing_slugs: dict[str, int] | None = None,
) -> list[list[str]]:
    """Validate entries against ``header`` and build per-row cell payloads.

    Args:
        entries: list of dicts keyed by PMCs-sheet column header.
        header: the PMCs-sheet header row.
        existing_slugs: optional mapping of slug -> row number (1-based)
            used to error out on duplicate-slug appends. Pass None to
            skip the dup-slug check (e.g. when running in dry-run mode
            without a service).

    Raises:
        ValueError: any entry missing a required field, has an unknown
            column key, or duplicates an existing slug.
    """
    rows: list[list[str]] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry #{i} must be a JSON object.")
        for k in PMCS_REQUIRED_FIELDS:
            if k not in entry or not str(entry[k]).strip():
                raise ValueError(f"Entry #{i} missing required field: {k!r}")
        unknown = [k for k in entry.keys() if k not in header]
        if unknown:
            raise ValueError(f"Entry #{i} has unknown columns: {unknown}. Available: {header}")
        slug = str(entry["PMC Slug"]).strip()
        if existing_slugs is not None and slug in existing_slugs and slug != "":
            raise ValueError(
                f"Entry #{i}: PMC Slug {slug!r} already exists at "
                f"{PMCS_SHEET} row {existing_slugs[slug]}. Use 'apply' to "
                f"update it instead of appending a duplicate."
            )
        rows.append([str(entry.get(col, "")) for col in header])
    return rows


def cmd_append_pmc(args: argparse.Namespace) -> None:
    entries = json.loads(Path(args.entries).read_text())
    if not isinstance(entries, list):
        sys.exit("Entries JSON must be a list of objects.")

    service = get_service()
    grid = fetch_sheet_grid(service, args.spreadsheet_id, PMCS_SHEET)
    if not grid:
        sys.exit(f"'{PMCS_SHEET}' sheet is empty (no header row).")
    header = grid[0]
    if "PMC Slug" not in header:
        sys.exit(f"'{PMCS_SHEET}' header has no 'PMC Slug' column.")
    slug_col_idx = header.index("PMC Slug")
    existing_slugs = {
        (row[slug_col_idx].strip() if slug_col_idx < len(row) else ""): r_idx
        for r_idx, row in enumerate(grid[1:], start=2)
    }

    try:
        rows = build_pmc_rows(entries, header, existing_slugs)
    except ValueError as e:
        sys.exit(str(e))

    print(f"Planned append to '{PMCS_SHEET}' ({len(rows)} new row(s)):")
    for idx, row in enumerate(rows):
        entry = entries[idx]
        print(f"  Entry #{idx} — {entry.get('PMC Name', '?')} ({entry.get('PMC Slug', '?')}):")
        for col, val in zip(header, row, strict=True):
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
