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
"""Build the 'Scan Results' tab — one row per archived scan bundle.

Per-scan outcome reporting for the Frontier Model Preparation programme: what
was scanned, how many findings the scan produced, how the pre-forward
assessment dispositioned them (counts + percentages), and what the PMC said
back.

Two classes of column, and the split is the whole design:

* **Auto** columns are derived on every rebuild from the ``apache/
  tooling-agents-private`` archive clone (``scans/mythos/**/metadata.yml`` and
  ``pre-forward-results/mythos/**/metadata.yml``) plus the PMCs sheet. They are
  never hand-edited; a rebuild overwrites them.
* **Carried** columns (``Feedback received``, ``Sentiment``, ``Feedback
  summary``, ``Improvements suggested``) have **no automated source** — PMC
  feedback arrives as prose on a ``[GLASSWING]`` email thread and the summary /
  sentiment / improvement read is a human-or-agent judgement. They are
  **carried over** across rebuilds keyed by ``Scan ID``, exactly as the Scan
  Queue tab carries its per-scan tracking block, and are written by
  ``scan-results-set``.

Only ``scans/mythos/`` is enumerated. Sibling ensembles in the archive (e.g.
``scans/opus-sonnet-haiku/``) and ``failed-scans/`` are deliberately **out of
scope** for this tab — they are not part of the delivery pipeline.
"""

from __future__ import annotations

import argparse
import os
import sys

from sheets_writer import PMCS_SHEET, SCAN_RESULTS_SHEET
from sheets_writer.columns import col_letter
from sheets_writer.sheets_api import fetch_sheet_grid, get_service

#: Disposition buckets, in the order the assessment framework lists them.
DISPOSITIONS = [
    "VALID",
    "VALID-HARDENING",
    "OUT-OF-MODEL",
    "BY-DESIGN",
    "KNOWN-NON-FINDING",
    "MODEL-GAP",
]

#: Buckets that mean "not a defect for this project to fix".
NOT_APPLICABLE = ["OUT-OF-MODEL", "BY-DESIGN", "KNOWN-NON-FINDING"]

SCAN_RESULTS_AUTO = [
    "PMC",
    "Repo",
    "Scan ID",
    "Scan date",
    "Scan type",
    "Model",
    "Findings (scan)",
    "Assessed",
    *DISPOSITIONS,
    "VALID %",
    "Hardening %",
    "Not-applicable %",
    "Sanity check",
    "Forwarded",
]

SCAN_RESULTS_CARRIED = [
    "Feedback received",
    "Sentiment",
    "Feedback summary",
    "Improvements suggested",
]

SCAN_RESULTS_HEADER = SCAN_RESULTS_AUTO + SCAN_RESULTS_CARRIED

#: 0-based indices of the carried (non-auto) columns.
SCAN_RESULTS_CARRIED_COLS = [len(SCAN_RESULTS_AUTO) + i for i in range(len(SCAN_RESULTS_CARRIED))]

SCAN_ID_COL = SCAN_RESULTS_AUTO.index("Scan ID")

#: Free-prose columns. These hold multi-sentence PMC feedback, so they are
#: wrapped and widened — unwrapped they clip at the neighbouring cell and the
#: feedback silently reads as a fragment, which is the opposite of the point.
PROSE_COLS = [
    SCAN_RESULTS_HEADER.index("Sentiment"),
    SCAN_RESULTS_HEADER.index("Feedback summary"),
    SCAN_RESULTS_HEADER.index("Improvements suggested"),
]

#: Pixel widths for the prose columns. Wrapping a narrow column just yields a
#: very tall row, so width and wrap are set together.
COL_WIDTHS = {
    SCAN_RESULTS_HEADER.index("Scan ID"): 260,
    SCAN_RESULTS_HEADER.index("Sentiment"): 180,
    SCAN_RESULTS_HEADER.index("Feedback summary"): 460,
    SCAN_RESULTS_HEADER.index("Improvements suggested"): 460,
}


def parse_flat_yaml(text: str) -> dict:
    """Pure: parse the archive's flat ``metadata.yml`` dialect into a dict.

    The dialect is deliberately small — ``key: value`` lines, plus one level of
    nesting for the ``dispositions:`` block:

        findings_assessed:     93
        dispositions:
          VALID:               8
          VALID-HARDENING:     82

    Nested blocks become a sub-dict. ``[a, b]`` inline lists become a list of
    stripped strings. Everything else stays a string — callers coerce. Comments
    (``#``) and blank lines are ignored. This avoids a PyYAML dependency for a
    format the archive controls; anything richer should switch to a real parser
    rather than grow this one.
    """
    out: dict = {}
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indented = line[:1].isspace()
        key, sep, val = line.strip().partition(":")
        if not sep:
            continue
        key = key.strip()
        val = val.strip()
        if indented and current is not None:
            current[key] = val
            continue
        if not val:
            current = {}
            out[key] = current
            continue
        current = None
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            out[key] = [p.strip() for p in inner.split(",") if p.strip()]
        else:
            out[key] = val
    return out


def as_int(value, default: int = 0) -> int:
    """Pure: best-effort int coercion; non-numeric / missing yields ``default``."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def pct(part: int, whole: int) -> str:
    """Pure: ``part`` as a percentage of ``whole``, one decimal, or '' if whole<=0."""
    if whole <= 0:
        return ""
    return f"{100.0 * part / whole:.1f}%"


def scan_type(meta: dict) -> str:
    """Pure: the human-facing scan-type label, e.g. ``ASVS L3``.

    Only ASVS runs exist today; the level comes from ``asvs_level``. A bundle
    with no level still reports ``ASVS`` rather than blank, so a future
    non-ASVS scan type shows up as an obvious anomaly instead of silently
    inheriting this label.
    """
    level = str(meta.get("asvs_level", "") or "").strip()
    return f"ASVS {level}".strip() if level else "ASVS"


def pmc_cell(row: list[str], idx: dict[str, int], name: str) -> str:
    """Pure: one PMCs-sheet cell by header name; '' when absent or short."""
    c = idx.get(name)
    return row[c].strip() if c is not None and c < len(row) else ""


def find_scan_dirs(archive_root: str) -> list[str]:
    """Impure (filesystem): every ``scans/mythos/**`` bundle dir, sorted.

    A bundle is any directory directly containing a ``metadata.yml``. Sibling
    ensembles under ``scans/`` are not walked — see the module docstring.
    """
    base = os.path.join(archive_root, "scans", "mythos")
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(base):
        if "metadata.yml" in filenames:
            found.append(dirpath)
    return sorted(found)


def assessment_dir_for(archive_root: str, scan_dir: str) -> str:
    """Pure-ish: the ``pre-forward-results/`` path mirroring ``scan_dir``.

    The assessment tree mirrors ``scans/`` exactly, so the mapping is a single
    path-prefix swap.
    """
    rel = os.path.relpath(scan_dir, os.path.join(archive_root, "scans"))
    return os.path.join(archive_root, "pre-forward-results", rel)


def build_scan_row(
    scan_meta: dict,
    assess_meta: dict | None,
    pmc_name: str,
    forwarded: str,
    scan_id: str,
) -> list:
    """Pure: the auto-column cells for one scan bundle.

    ``assess_meta`` is ``None`` when no pre-forward assessment exists yet — the
    disposition and percentage cells then render blank and ``Sanity check``
    reads ``NOT ASSESSED``, so an unassessed scan is visible rather than
    looking like a zero-finding one.
    """
    disp = (assess_meta or {}).get("dispositions", {}) or {}
    counts = {d: as_int(disp.get(d), 0) for d in DISPOSITIONS}
    assessed = as_int((assess_meta or {}).get("findings_assessed"), 0)

    if assess_meta is None:
        disp_cells: list = [""] * len(DISPOSITIONS)
        pct_cells: list = ["", "", ""]
        sanity = "NOT ASSESSED"
        assessed_cell: object = ""
    else:
        disp_cells = [counts[d] for d in DISPOSITIONS]
        na = sum(counts[d] for d in NOT_APPLICABLE)
        pct_cells = [
            pct(counts["VALID"], assessed),
            pct(counts["VALID-HARDENING"], assessed),
            pct(na, assessed),
        ]
        sanity = str(assess_meta.get("sanity_check", "") or "")
        assessed_cell = assessed

    models = scan_meta.get("audit_models", [])
    model = ", ".join(models) if isinstance(models, list) else str(models)

    return [
        pmc_name,
        str(scan_meta.get("repo", "") or ""),
        scan_id,
        str(scan_meta.get("scan_date", "") or "")[:10],
        scan_type(scan_meta),
        model,
        as_int(scan_meta.get("findings_total"), 0),
        assessed_cell,
        *disp_cells,
        *pct_cells,
        sanity,
        forwarded,
    ]


def parse_scan_results(grid: list[list[str]]) -> dict[str, list[str]]:
    """Pure: map ``Scan ID -> previous full row`` from the existing tab.

    Keyed by Scan ID because that is the archive's own stable identifier for a
    bundle (project + repo + date + short SHA); it survives re-sorting and new
    scans landing above a row. A tab whose header doesn't match yields ``{}``
    (the rebuild then re-seeds the carried columns blank).
    """
    if not grid:
        return {}
    width = len(SCAN_RESULTS_HEADER)
    header_at = -1
    for i, row in enumerate(grid):
        if [c.strip() for c in row[:width]] == SCAN_RESULTS_HEADER:
            header_at = i
            break
    if header_at < 0:
        return {}
    out: dict[str, list[str]] = {}
    for row in grid[header_at + 1 :]:
        sid = row[SCAN_ID_COL].strip() if SCAN_ID_COL < len(row) else ""
        if sid:
            out[sid] = [c.strip() for c in row]
    return out


def scan_results_carried(prev_row: list[str] | None) -> list[str]:
    """Pure: the carried (feedback) cells of a previous row, in column order."""
    row = prev_row or []
    return [row[j] if j < len(row) else "" for j in SCAN_RESULTS_CARRIED_COLS]


def normalize_repo(repo: str) -> str:
    """Pure: a repo reference reduced to its bare ``owner/name``.

    The archive writes ``repo`` inconsistently — ``apache/shiro``,
    ``apache/fineract/fineract`` (doubled), or a full GitHub URL in the tracker
    — so both sides are normalised to the last two path segments before
    comparison.
    """
    s = str(repo or "").strip().rstrip("/")
    if not s:
        return ""
    s = s.split("github.com/", 1)[-1]
    parts = [p for p in s.split("/") if p]
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        parts = parts[:-1]
    return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


def collect_scan_rows(
    archive_root: str,
    pmc_by_slug: dict[str, tuple[str, str]],
    carried: dict[str, list[str]],
    pmc_by_repo: dict[str, tuple[str, str]] | None = None,
) -> tuple[list[list], list[str]]:
    """Impure (filesystem): all Scan Results data rows + any anomalies found.

    ``pmc_by_slug`` maps a PMC slug to ``(PMC Name, Forwarded scan to PMC)``.
    ``pmc_by_repo`` maps a normalised ``owner/name`` to the same pair, and is
    the **fallback** when a scan's ``project`` is not a PMC slug — the archive
    sometimes records the repo name there (e.g. project
    ``apisix-ingress-controller``, which belongs to the ``apisix`` PMC).
    Resolving via the repo the PMC actually listed avoids hardcoding aliases.

    A scan that resolves by neither route is still emitted — with the raw slug
    and an anomaly note — rather than dropped, so an unexpected project in the
    archive is visible instead of silently missing.
    """
    rows: list[list] = []
    anomalies: list[str] = []
    for scan_dir in find_scan_dirs(archive_root):
        scan_id = os.path.basename(scan_dir)
        with open(os.path.join(scan_dir, "metadata.yml"), encoding="utf-8") as fh:
            scan_meta = parse_flat_yaml(fh.read())

        assess_path = os.path.join(assessment_dir_for(archive_root, scan_dir), "metadata.yml")
        assess_meta = None
        if os.path.exists(assess_path):
            with open(assess_path, encoding="utf-8") as fh:
                assess_meta = parse_flat_yaml(fh.read())
        else:
            anomalies.append(f"{scan_id}: no pre-forward assessment")

        slug = str(scan_meta.get("project", "") or "").strip().lower()
        repo_key = normalize_repo(scan_meta.get("repo", ""))
        if slug in pmc_by_slug:
            pmc_name, forwarded = pmc_by_slug[slug]
        elif pmc_by_repo and repo_key in pmc_by_repo:
            pmc_name, forwarded = pmc_by_repo[repo_key]
        else:
            pmc_name, forwarded = slug, ""
            anomalies.append(
                f"{scan_id}: project {slug!r} is not a PMC slug and repo "
                f"{repo_key!r} is in no PMC's repo list"
            )

        row = build_scan_row(scan_meta, assess_meta, pmc_name, forwarded, scan_id)
        rows.append(row + scan_results_carried(carried.get(scan_id)))

    rows.sort(key=lambda r: (str(r[3]), str(r[0])), reverse=True)
    return rows, anomalies


def totals_row(rows: list[list]) -> list:
    """Pure: an aggregate row across every assessed scan.

    Percentages are recomputed from summed counts (not averaged across rows),
    so a large scan weighs proportionally more than a small one.
    """
    fi = SCAN_RESULTS_AUTO.index("Findings (scan)")
    ai = SCAN_RESULTS_AUTO.index("Assessed")
    d0 = SCAN_RESULTS_AUTO.index(DISPOSITIONS[0])
    findings = sum(as_int(r[fi]) for r in rows)
    assessed = sum(as_int(r[ai]) for r in rows)
    counts = {d: sum(as_int(r[d0 + i]) for r in rows) for i, d in enumerate(DISPOSITIONS)}
    na = sum(counts[d] for d in NOT_APPLICABLE)
    return [
        f"TOTAL ({len(rows)} scans)",
        "",
        "",
        "",
        "",
        "",
        findings,
        assessed,
        *[counts[d] for d in DISPOSITIONS],
        pct(counts["VALID"], assessed),
        pct(counts["VALID-HARDENING"], assessed),
        pct(na, assessed),
        "",
        "",
    ] + [""] * len(SCAN_RESULTS_CARRIED)


def find_scan_results_row(grid: list[list[str]], scan_id: str) -> int | None:
    """Pure: 0-based grid row index of ``scan_id``'s row, or None."""
    width = len(SCAN_RESULTS_HEADER)
    header_at = -1
    for i, row in enumerate(grid):
        if [c.strip() for c in row[:width]] == SCAN_RESULTS_HEADER:
            header_at = i
            break
    if header_at < 0:
        return None
    for i in range(header_at + 1, len(grid)):
        row = grid[i]
        sid = row[SCAN_ID_COL].strip() if SCAN_ID_COL < len(row) else ""
        if sid == scan_id:
            return i
    return None


def cmd_scan_results_set(args: argparse.Namespace) -> int:
    """Write the carried feedback cells for one scan, keyed by Scan ID."""
    service = get_service()
    grid = fetch_sheet_grid(service, args.spreadsheet_id, SCAN_RESULTS_SHEET)
    row_idx = find_scan_results_row(grid, args.scan_id)
    if row_idx is None:
        print(
            f"No Scan Results row for scan-id {args.scan_id!r}. "
            "Run build-scan-results-tab first (the scan must be in the archive).",
            file=sys.stderr,
        )
        return 2

    fields = {
        "Feedback received": args.feedback_received,
        "Sentiment": args.sentiment,
        "Feedback summary": args.summary,
        "Improvements suggested": args.improvements,
    }
    row = grid[row_idx]
    data: list[dict] = []
    diffs: list[str] = []
    for field, value in fields.items():
        if value is None:
            continue
        c = len(SCAN_RESULTS_AUTO) + SCAN_RESULTS_CARRIED.index(field)
        current = row[c] if c < len(row) else ""
        a1 = f"'{SCAN_RESULTS_SHEET}'!{col_letter(c)}{row_idx + 1}"
        diffs.append(f"  {field}: {current!r} -> {value!r}   [{a1}]")
        data.append({"range": a1, "values": [[value]]})

    if not data:
        print("Nothing to set (no field values provided).")
        return 0

    print(f"Scan Results row {row_idx + 1} · {args.scan_id}:")
    for line in diffs:
        print(line)

    if args.dry_run:
        print(f"\nDry run — no changes written. ({len(data)} cells would change.)")
        return 0

    resp = (
        service.spreadsheets()
        .values()
        .batchUpdate(
            spreadsheetId=args.spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        )
        .execute()
    )
    print(f"\nApplied. totalUpdatedCells={resp.get('totalUpdatedCells')}")
    return 0


def cmd_build_scan_results_tab(args: argparse.Namespace) -> int:
    """Rebuild the Scan Results tab from the archive, preserving feedback cells."""
    from sheets_writer.status import _ensure_sheet, _Tab, _write_tab

    archive_root = os.path.expanduser(args.archive_root)
    if not os.path.isdir(os.path.join(archive_root, "scans", "mythos")):
        print(
            f"No scans/mythos/ under {archive_root!r}. Pass --archive-root pointing at "
            "an apache/tooling-agents-private clone.",
            file=sys.stderr,
        )
        return 2

    service = get_service()

    pmc_grid = fetch_sheet_grid(service, args.spreadsheet_id, PMCS_SHEET)
    idx = {h.strip(): i for i, h in enumerate(pmc_grid[0])}
    pmc_by_slug: dict[str, tuple[str, str]] = {}
    pmc_by_repo: dict[str, tuple[str, str]] = {}
    for row in pmc_grid[1:]:
        slug = pmc_cell(row, idx, "PMC Slug").lower()
        if not slug:
            continue
        entry = (
            pmc_cell(row, idx, "PMC Name") or slug,
            pmc_cell(row, idx, "Forwarded scan to PMC"),
        )
        pmc_by_slug[slug] = entry
        for listed in (
            pmc_cell(row, idx, "Repositories requested")
            + "\n"
            + pmc_cell(row, idx, "Repositories submitted")
        ).split("\n"):
            key = normalize_repo(listed)
            if key:
                pmc_by_repo.setdefault(key, entry)

    try:
        prev = fetch_sheet_grid(service, args.spreadsheet_id, SCAN_RESULTS_SHEET)
    except Exception:
        prev = []
    carried = parse_scan_results(prev)

    rows, anomalies = collect_scan_rows(archive_root, pmc_by_slug, carried, pmc_by_repo)

    tab = _Tab()
    tab.row([f"Scan Results — {len(rows)} scan(s) — rebuilt {args.today}"], bold=True)
    tab.row(
        [
            "Auto columns are rebuilt from the tooling-agents-private archive "
            "(scans/mythos + pre-forward-results). The four feedback columns have no "
            "automated source: they are written by 'scan-results-set' and carried over "
            "on every rebuild, keyed by Scan ID."
        ]
    )
    tab.row([])
    tab.row(SCAN_RESULTS_HEADER, header=True)
    for r in rows:
        tab.row(r)
    if rows:
        tab.row(totals_row(rows), bold=True)
    if anomalies:
        tab.row([])
        tab.row(["Anomalies"], bold=True)
        for a in anomalies:
            tab.row([a])

    by_title = {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in service.spreadsheets().get(spreadsheetId=args.spreadsheet_id).execute()["sheets"]
    }
    sheet_id = _ensure_sheet(service, args.spreadsheet_id, SCAN_RESULTS_SHEET, by_title)

    if args.dry_run:
        print(f"Dry run — {len(rows)} scan row(s) would be written to {SCAN_RESULTS_SHEET}.")
        for r in rows:
            print(f"  {r[SCAN_ID_COL]}  {r[0]}  findings={r[6]} assessed={r[7]}")
        for a in anomalies:
            print(f"  ANOMALY: {a}")
        return 0

    _write_tab(
        service,
        args.spreadsheet_id,
        SCAN_RESULTS_SHEET,
        sheet_id,
        tab,
        frozen=(4, 0),
        wrap_col=PROSE_COLS,
        col_widths=COL_WIDTHS,
    )
    carried_kept = sum(1 for r in rows if any(scan_results_carried(carried.get(r[SCAN_ID_COL]))))
    print(
        f"Refreshed: {SCAN_RESULTS_SHEET!r} ({len(rows)} scans, "
        f"{carried_kept} with carried feedback, {len(anomalies)} anomaly/-ies)."
    )
    return 0
