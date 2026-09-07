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
"""Argparse CLI for sheets-writer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sheets_writer import CANNED_SHEET, PMCS_SHEET
from sheets_writer.apply import cmd_apply
from sheets_writer.auth import AuthError, run_setup
from sheets_writer.canned import cmd_append_canned, cmd_init_canned
from sheets_writer.dump import cmd_dump
from sheets_writer.pmcs import cmd_append_pmc
from sheets_writer.scan_queue import cmd_scan_queue_set
from sheets_writer.scan_results import cmd_build_scan_results_tab, cmd_scan_results_set
from sheets_writer.schema import cmd_add_columns, cmd_insert_column, cmd_rename_column
from sheets_writer.security_cc import cmd_backfill_security_cc
from sheets_writer.status import cmd_build_status_tab


def cmd_setup(_args: argparse.Namespace) -> int:
    run_setup()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sheets-writer",
        description=(
            "OAuth-authenticated writer for the Glasswing / Mythos scan-outreach Google Sheet."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Run OAuth installed-app flow once.")

    dump_p = sub.add_parser(
        "dump",
        help="Read a sheet and print it as JSON to stdout (read-only; no truncation).",
    )
    dump_p.add_argument("--spreadsheet-id", required=True)
    dump_p.add_argument("--sheet", required=True, help="Sheet name (e.g. 'PMCs').")
    dump_p.add_argument(
        "--objects",
        action="store_true",
        help="Emit a list of row objects keyed by header instead of {header, rows}.",
    )
    dump_p.add_argument(
        "--compact",
        action="store_true",
        help="Single-line JSON instead of indented.",
    )

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
        help=(f"Append one or more new PMC rows to '{PMCS_SHEET}'. Errors on duplicate slug."),
    )
    apppmc_p.add_argument("--spreadsheet-id", required=True)
    apppmc_p.add_argument(
        "--entries",
        required=True,
        type=Path,
        help=(
            "Path to JSON list of objects keyed by PMC-sheet column header. "
            "'PMC Name' + 'PMC Slug' required."
        ),
    )
    apppmc_p.add_argument("--dry-run", action="store_true")

    status_p = sub.add_parser(
        "build-status-tab",
        help=(
            "Create or refresh the 'Status' tab with in-flight + completed "
            "tables and timeline data, color-coded by pipeline state."
        ),
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
    pos = inscol_p.add_mutually_exclusive_group(required=True)
    pos.add_argument(
        "--after",
        help="Header of the column the new one should be inserted directly after.",
    )
    pos.add_argument(
        "--before",
        help="Header of the column the new one should be inserted directly before.",
    )
    pos.add_argument(
        "--at-start",
        action="store_true",
        help="Insert the new column as the first column of the sheet.",
    )
    inscol_p.add_argument("--header", required=True, help="Header for the new column.")
    inscol_p.add_argument(
        "--fill",
        type=Path,
        help=(
            "Optional JSON file to fill the new column's data rows. Either a list "
            'of cell values in row order, or an object {"key": <existing header>, '
            '"map": {key-cell: value}} to look each row up by another column.'
        ),
    )
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

    bsc_p = sub.add_parser(
        "backfill-security-cc",
        help=(
            "Deterministically write the 'PMC team Cc' column on the PMCs sheet: "
            "each PMC's own security@<pmc> when it runs a security team, else its "
            "private@<pmc> list. Creates the column if missing; re-runnable."
        ),
    )
    bsc_p.add_argument("--spreadsheet-id", required=True)
    bsc_p.add_argument("--dry-run", action="store_true")

    sq_p = sub.add_parser(
        "scan-queue-set",
        help="Set a repo's per-scan tracking cells (Scan N block) in the 'Scan Queue' tab.",
    )
    sq_p.add_argument("--spreadsheet-id", required=True)
    sq_p.add_argument(
        "--repo", required=True, help="Repo URL exactly as in the Scan Queue 'Repo' column."
    )
    sq_p.add_argument(
        "--branch", default="", help="Branch/tag ('' = the default-branch row; the default)."
    )
    sq_p.add_argument(
        "--scan", type=int, default=1, help="Which Scan N block to write (1..5; default 1)."
    )
    sq_p.add_argument("--when-scanned", help="'When scanned' date (YYYY-MM-DD).")
    sq_p.add_argument(
        "--model-thread",
        help="'Model send thread (ponymail)' — the scan-delivery thread permalink.",
    )
    sq_p.add_argument("--when-report-sent", help="'When report sent' date (YYYY-MM-DD).")
    sq_p.add_argument("--commit", help="'Commit hash' — the scanned head SHA (short or full).")
    sq_p.add_argument("--dry-run", action="store_true")

    bsr_p = sub.add_parser(
        "build-scan-results-tab",
        help=(
            "Rebuild the 'Scan Results' tab from the tooling-agents-private archive: "
            "one row per archived scan bundle with findings "
            "(counts + percentages), sanity verdict and forwarded date. The four "
            "feedback columns are carried over, keyed by Scan ID."
        ),
    )
    bsr_p.add_argument("--spreadsheet-id", required=True)
    bsr_p.add_argument(
        "--archive-root",
        required=True,
        help="Path to an apache/tooling-agents-private clone (scans/glasswing/ + scans/mythos/).",
    )
    bsr_p.add_argument("--today", default="", help="Date stamp for the tab header (YYYY-MM-DD).")
    bsr_p.add_argument("--dry-run", action="store_true")

    sr_p = sub.add_parser(
        "scan-results-set",
        help="Set the carried feedback cells for one scan in the 'Scan Results' tab.",
    )
    sr_p.add_argument("--spreadsheet-id", required=True)
    sr_p.add_argument(
        "--scan-id", required=True, help="Scan bundle id, e.g. shiro-2026-07-17-cde5990."
    )
    sr_p.add_argument("--feedback-received", help="Date the PMC replied (YYYY-MM-DD).")
    sr_p.add_argument(
        "--sentiment",
        help="Sentiment read of the PMC's reply (e.g. Positive / Neutral / Critical / Mixed).",
    )
    sr_p.add_argument("--summary", help="One-or-two-sentence summary of the PMC's feedback.")
    sr_p.add_argument(
        "--improvements", help="Programme improvements the feedback points at, if any."
    )
    sr_p.add_argument("--dry-run", action="store_true")

    return parser


DISPATCH = {
    "setup": cmd_setup,
    "dump": cmd_dump,
    "apply": cmd_apply,
    "init-canned-tab": cmd_init_canned,
    "append-canned": cmd_append_canned,
    "append-pmc": cmd_append_pmc,
    "build-status-tab": cmd_build_status_tab,
    "rename-column": cmd_rename_column,
    "insert-column": cmd_insert_column,
    "add-columns": cmd_add_columns,
    "backfill-security-cc": cmd_backfill_security_cc,
    "scan-queue-set": cmd_scan_queue_set,
    "build-scan-results-tab": cmd_build_scan_results_tab,
    "scan-results-set": cmd_scan_results_set,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = DISPATCH[args.cmd](args)
    except AuthError as e:
        print(str(e), file=sys.stderr)
        return 1
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
