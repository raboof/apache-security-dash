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
"""Status tab — pipeline-state machine + tab rebuild logic."""

from __future__ import annotations

import argparse
import datetime
import sys

from sheets_writer import PIPELINE_STATES, STATE_COLOR, STATUS_SHEET
from sheets_writer.columns import col_letter
from sheets_writer.prs import parse_pr_urls, query_pr_states
from sheets_writer.sheets_api import fetch_sheet_grid, get_service


def compute_pmc_status(row: list[str], col_idx: dict[str, int]) -> dict:
    """Derive the pipeline state of a single PMC row.

    Calls ``query_pr_states`` per URL, which shells out to ``gh``. Pure
    logic for the state machine itself; the network side-effect is the
    PR-state lookup.
    """

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

    repo_count = len(
        [r for r in repos_requested.splitlines() if r.strip() and not r.strip().startswith("#")]
    )
    submitted_count = len(
        [r for r in repos_submitted.splitlines() if r.strip() and not r.strip().startswith("#")]
    )

    pr_urls = parse_pr_urls(pr_issues)
    pr_state = (
        query_pr_states(pr_urls) if pr_urls else {"open": 0, "merged": 0, "closed": 0, "errors": []}
    )

    return {
        "pmc": pmc,
        "slug": slug,
        "state": state,
        "model_status": model_status,
        "repos_requested_count": repo_count,
        "repos_submitted_count": submitted_count,
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
        scan_requested_idx = col_idx.get("Scan Requested", -1)
        scan_requested = (
            row[scan_requested_idx].strip() if 0 <= scan_requested_idx < len(row) else ""
        )
        if scan_requested != "Yes":
            continue
        entries.append(compute_pmc_status(row, col_idx))

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
            resp = (
                service.spreadsheets()
                .batchUpdate(
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
                )
                .execute()
            )
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
                        "cell": {"userEnteredFormat": {"backgroundColor": color}},
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            )

    # Header section.
    append_row([f"Glasswing scan pipeline — status as of {today}"])
    append_row(["Source: PMCs sheet · regenerated by sheets-writer build-status-tab"])
    append_row([""])

    # Program-wide rollup.
    total_pmcs = len(entries)
    total_open = sum(e["pr_open"] for e in entries)
    total_merged = sum(e["pr_merged"] for e in entries)
    total_closed = sum(e["pr_closed"] for e in entries)
    total_prs = total_open + total_merged + total_closed
    pmcs_with_prs = len(
        [e for e in entries if (e["pr_open"] + e["pr_merged"] + e["pr_closed"]) > 0]
    )
    state_counts = {s: sum(1 for e in entries if e["state"] == s) for s in PIPELINE_STATES}
    pmcs_sent_to_vendor = sum(
        state_counts.get(s, 0) for s in ("Submitted", "Triaging", "Delivered")
    )
    pmcs_results_back = sum(state_counts.get(s, 0) for s in ("Triaging", "Delivered"))
    total_repos_requested = sum(e["repos_requested_count"] for e in entries)
    total_repos_submitted = sum(e["repos_submitted_count"] for e in entries)

    append_row(["PROGRAM TOTALS"])
    append_row(["PMCs opted in (Scan Requested = Yes)", total_pmcs])
    append_row(["  Pre-flight (model not yet verified)", state_counts["Pre-flight"]])
    append_row(["  Ready (model verified, awaiting operator submit)", state_counts["Ready"]])
    append_row(
        [
            "  Submitted (sent to vendor, awaiting results)",
            state_counts["Submitted"],
        ]
    )
    append_row(
        [
            "  Triaging (results back, pre-forward sanity check)",
            state_counts["Triaging"],
        ]
    )
    append_row(["  Delivered (forwarded to PMC)", state_counts["Delivered"]])
    append_row(
        [
            "PMCs with scan request sent to vendor (Submitted+Triaging+Delivered)",
            pmcs_sent_to_vendor,
        ]
    )
    append_row(
        [
            "PMCs with scan results back from vendor (Triaging+Delivered)",
            pmcs_results_back,
        ]
    )
    append_row(["Total repos requested across in-flight PMCs", total_repos_requested])
    append_row(["Total repos submitted to vendor for scan", total_repos_submitted])
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
        except Exception:  # noqa: BLE001 — date parsing tolerant
            e2e = ""
        pr_total = e["pr_open"] + e["pr_merged"] + e["pr_closed"]
        prs_open_cell = e["pr_open"] if e["pr_urls"] else "—"
        prs_merged_cell = e["pr_merged"] if e["pr_urls"] else "—"
        prs_total_cell = pr_total if e["pr_urls"] else "—"
        append_row(
            [
                e["pmc"],
                e["slug"],
                len(
                    [
                        r
                        for r in e["repos_submitted"].splitlines()
                        if r.strip() and not r.strip().startswith("#")
                    ]
                ),
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

    # 5. Write values + apply colors.
    if args.dry_run:
        print(
            f"Would write {len(values)} rows to '{STATUS_SHEET}'; "
            f"in-flight={len(in_flight)}, completed={len(completed)}, "
            f"timeline-events={timeline_end - timeline_start}."
        )
        return

    a1_end_col = col_letter(max(len(r) for r in values) - 1)
    a1_range = f"{STATUS_SHEET}!A1:{a1_end_col}{len(values)}"
    service.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=a1_range,
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    # Bold header rows.
    def bold_request(row_idx, cols=8):
        return {
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
    for i, row in enumerate(values):
        if row and (row[0] == "COMPLETED" or row[0].startswith("TIMELINE DATA")):
            bold_rows.append(i)
            bold_rows.append(i + 1)

    clear_format_request = {
        "repeatCell": {
            "range": {"sheetId": sheet_id},
            "cell": {"userEnteredFormat": {}},
            "fields": "userEnteredFormat",
        }
    }

    requests = [clear_format_request]
    requests.extend(bold_request(i) for i in sorted(set(bold_rows)))
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
