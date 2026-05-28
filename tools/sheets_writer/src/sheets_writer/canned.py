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
"""Canned-responses sheet — init + append."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from sheets_writer import CANNED_HEADERS, CANNED_SHEET
from sheets_writer.sheets_api import get_service

CANNED_REQUIRED = ("topic", "question_pattern", "response", "author")


def build_canned_rows(entries: list[dict], today: str | None = None) -> list[list[str]]:
    """Build row payloads from canned-response entry dicts.

    Today's ISO date is auto-filled into the first column.

    Raises:
        ValueError: any entry missing a required field.
    """
    today = today or datetime.date.today().isoformat()
    rows: list[list[str]] = []
    for i, entry in enumerate(entries):
        for k in CANNED_REQUIRED:
            if k not in entry:
                raise ValueError(f"Entry #{i} missing required field: {k!r}")
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
    return rows


def cmd_init_canned(args: argparse.Namespace) -> None:
    service = get_service()
    meta = service.spreadsheets().get(spreadsheetId=args.spreadsheet_id).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if CANNED_SHEET in existing:
        print(f"Sheet '{CANNED_SHEET}' already exists; nothing to do.")
        return
    if args.dry_run:
        print(f"Would create sheet '{CANNED_SHEET}' with header row: {CANNED_HEADERS}")
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
    try:
        rows = build_canned_rows(entries)
    except ValueError as e:
        sys.exit(str(e))

    print(f"Planned append to '{CANNED_SHEET}' ({len(rows)} row(s)):")
    for idx, row in enumerate(rows):
        print(f"  Entry #{idx}:")
        for col, val in zip(CANNED_HEADERS, row, strict=True):
            display = val if len(val) <= 80 else val[:77] + "..."
            print(f"    {col}: {display!r}")
    if args.dry_run:
        print("\nDry run — no changes written.")
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
