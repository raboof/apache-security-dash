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
"""Column-schema mutations: rename / insert / add."""

from __future__ import annotations

import argparse
import sys

from sheets_writer.columns import col_letter
from sheets_writer.sheets_api import fetch_sheet_grid, get_service


def cmd_rename_column(args: argparse.Namespace) -> None:
    service = get_service()
    grid = fetch_sheet_grid(service, args.spreadsheet_id, args.sheet)
    if not grid:
        sys.exit(f"Sheet '{args.sheet}' has no header row.")
    header = grid[0]
    if args.new in header:
        sys.exit(f"Header '{args.new}' already exists; refusing to overwrite.")
    if args.old not in header:
        sys.exit(f"Header '{args.old}' not found in sheet '{args.sheet}'. Available: {header}")
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
        sys.exit(f"Anchor column '{args.after}' not found in header. Available: {header}")
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
