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
"""Build or refresh the 'OSS Subscriptions' tab in the Mythos tracker.

Aggregates the PMCs sheet's `Expedite Claude OSS Requests` and
`Claude OSS Subscriptions Submitted` columns into a per-Apache-address
view: one row per unique @apache.org address, with all PMCs that
expedited for that address listed in a single comma-separated cell.

Idempotent — first run creates the tab; subsequent runs clear and
rewrite. Designed to be run on demand from the SKILL flow, equivalent
in spirit to ``sheets-writer build-status-tab`` but kept out of the
main CLI for now (single-use, low traffic).

Usage:

    uv run --project tools/sheets_writer python \\
      tools/sheets_writer/scripts/build_oss_tab.py \\
      --spreadsheet-id <id>
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict

from sheets_writer.sheets_api import fetch_sheet_grid, get_service

TAB_NAME = "OSS Subscriptions"
PMCS_SHEET = "PMCs"

HEADER = [
    "Apache Address",
    "PMCs",
    "Earliest Expedite Asked",
    "Latest Subscription Confirmed",
    "Status",
    "Notes",
]


def build_rows(pmcs_grid: list[list[str]]) -> list[list[str]]:
    """Aggregate the PMCs grid into one row per unique Apache address."""
    header = pmcs_grid[0]

    def col(name: str) -> int:
        return header.index(name)

    exp_idx = col("Expedite Claude OSS Requests")
    sub_idx = col("Claude OSS Subscriptions Submitted")
    slug_idx = col("PMC Slug")
    date_idx = col("Request date")
    scan_req_idx = col("Scan Requested")

    agg: dict[str, dict] = defaultdict(
        lambda: {"pmcs": [], "exp_dates": [], "sub_dates": [], "sub_confirmed": set()}
    )

    for row in pmcs_grid[1:]:
        if len(row) <= scan_req_idx or row[scan_req_idx] != "Yes":
            continue
        slug = row[slug_idx]
        req_date = row[date_idx] if date_idx < len(row) else ""

        if exp_idx < len(row) and row[exp_idx].strip():
            for raw in re.split(r"[\n,]+", row[exp_idx]):
                addr = raw.strip()
                if addr and addr.lower() != "none" and "@" in addr:
                    if slug not in agg[addr]["pmcs"]:
                        agg[addr]["pmcs"].append(slug)
                    if req_date:
                        agg[addr]["exp_dates"].append(req_date)

        if sub_idx < len(row) and row[sub_idx].strip():
            for raw in re.split(r"[\n,]+", row[sub_idx]):
                addr = raw.strip()
                if addr and "@" in addr:
                    if slug not in agg[addr]["pmcs"]:
                        agg[addr]["pmcs"].append(slug)
                    agg[addr]["sub_confirmed"].add(slug)

    rows = []
    for addr in sorted(agg):
        info = agg[addr]
        pmcs = ", ".join(sorted(set(info["pmcs"])))
        earliest_exp = min(info["exp_dates"]) if info["exp_dates"] else ""
        latest_sub = max(info["sub_dates"]) if info["sub_dates"] else ""
        if info["sub_confirmed"]:
            confirmed = ", ".join(sorted(info["sub_confirmed"]))
            status = f"Confirmed (PMCs: {confirmed})"
        else:
            status = "Expedite requested"
        rows.append([addr, pmcs, earliest_exp, latest_sub, status, ""])

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create or refresh the 'OSS Subscriptions' tab in the Mythos tracker "
            "from the PMCs sheet's expedite + confirmed columns."
        )
    )
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    service = get_service()
    pmcs_grid = fetch_sheet_grid(service, args.spreadsheet_id, PMCS_SHEET)
    rows = build_rows(pmcs_grid)

    print(f"Aggregated {len(rows)} unique Apache addresses across PMCs.")
    print()
    print(f"{'Address':<35} {'PMCs':<25} {'Status'}")
    print("-" * 90)
    for r in rows:
        print(f"{r[0]:<35} {r[1]:<25} {r[4]}")

    if args.dry_run:
        print(f"\nDry run — no changes written to '{TAB_NAME}'.")
        return 0

    meta = service.spreadsheets().get(spreadsheetId=args.spreadsheet_id).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}

    if TAB_NAME not in existing:
        print(f"\nCreating sheet '{TAB_NAME}'…")
        service.spreadsheets().batchUpdate(
            spreadsheetId=args.spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": TAB_NAME,
                                "gridProperties": {
                                    "rowCount": max(100, len(rows) + 10),
                                    "columnCount": len(HEADER) + 2,
                                    "frozenRowCount": 1,
                                },
                            }
                        }
                    }
                ]
            },
        ).execute()
    else:
        print(f"\nSheet '{TAB_NAME}' exists; clearing and rewriting.")
        service.spreadsheets().values().clear(
            spreadsheetId=args.spreadsheet_id,
            range=f"{TAB_NAME}!A1:Z1000",
        ).execute()

    values = [HEADER] + rows
    result = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=args.spreadsheet_id,
            range=f"{TAB_NAME}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        )
        .execute()
    )

    print(
        f"Wrote {result.get('updatedRows')} rows, "
        f"{result.get('updatedCells')} cells to '{TAB_NAME}'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
