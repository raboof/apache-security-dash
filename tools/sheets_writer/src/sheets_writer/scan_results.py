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
was scanned, how many findings the scan produced, and what the PMC said back.

Two classes of column, and the split is the whole design:

* **Auto** columns are derived on every rebuild from the ``apache/
  tooling-agents-private`` archive clone plus the PMCs sheet. They are never
  hand-edited; a rebuild overwrites them.
* **Carried** columns (``Feedback received``, ``Sentiment``, ``Feedback
  summary``, ``Improvements suggested``) have **no automated source** — PMC
  feedback arrives as prose on a ``[GLASSWING]`` email thread and the summary /
  sentiment / improvement read is a human-or-agent judgement. They are
  **carried over** across rebuilds keyed by ``Scan ID``, exactly as the Scan
  Queue tab carries its per-scan tracking block, and are written by
  ``scan-results-set``.

``scans/glasswing/`` is the delivery tree and is enumerated; ``scans/mythos/``
is still read when present (the older layout). Sibling ensembles in the archive
(e.g. ``scans/experiments/``) and ``failed-scans/`` are deliberately **out of
scope** for this tab — they are not part of the delivery pipeline.

Two bundle layouts coexist and both are supported:

* **mythos** — a flat ``metadata.yml`` carries every identity field.
* **glasswing** — there is **no** ``metadata.yml``; identity comes from
  ``TRIAGE.json`` (``triage_context.target`` / ``.commit``, ``summary.total``)
  plus the ``<repo>/<YYYYMMDDTHHMMSSZ>`` directory layout.

Scan ID is composed as ``<repo>-<YYYY-MM-DD>-<sha7>``, never the bundle
directory's basename. Glasswing scans run in fleet batches that share one
timestamp — 17 repos sit under ``20260811T043305Z`` — so a basename key would
collapse those rows into one and cross-wire their carried PMC feedback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from sheets_writer import PMCS_SHEET, SCAN_RESULTS_SHEET
from sheets_writer.columns import col_letter
from sheets_writer.sheets_api import fetch_sheet_grid, get_service

SCAN_RESULTS_AUTO = [
    "PMC",
    "Repo",
    "Scan ID",
    "Scan date",
    "Scan type",
    "Model",
    "Findings (scan)",
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
    nesting for any indented block:

        project:               shiro
        repo:                  apache/shiro

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


def scan_type(meta: dict) -> str:
    """Pure: the human-facing scan-type label, e.g. ``ASVS L3`` or ``Glasswing``.

    A bundle that names its own kind (``scan_kind``) reports that verbatim —
    that is how glasswing bundles, which are not ASVS runs, avoid inheriting
    the ASVS label. Otherwise the label is ASVS with the ``asvs_level`` suffix
    when one is recorded; a bundle with no level still reports ``ASVS`` rather
    than blank, so an unrecognised scan type shows up as an obvious anomaly.
    """
    kind = str(meta.get("scan_kind", "") or "").strip()
    if kind:
        return kind
    level = str(meta.get("asvs_level", "") or "").strip()
    return f"ASVS {level}".strip() if level else "ASVS"


def pmc_cell(row: list[str], idx: dict[str, int], name: str) -> str:
    """Pure: one PMCs-sheet cell by header name; '' when absent or short."""
    c = idx.get(name)
    return row[c].strip() if c is not None and c < len(row) else ""


#: Scan trees walked, in order. Both layouts are delivery-pipeline trees; other
#: siblings under ``scans/`` are out of scope (see the module docstring).
SCAN_TREES = ["glasswing", "mythos"]

#: Files that mark a directory as a scan bundle. ``metadata.yml`` is the mythos
#: layout; glasswing bundles have no metadata file and are identified by their
#: triage output instead.
BUNDLE_MARKERS = ("metadata.yml", "TRIAGE.json")


def find_scan_dirs(archive_root: str) -> list[str]:
    """Impure (filesystem): every scan-bundle dir under the delivery trees, sorted.

    A bundle is any directory directly containing one of ``BUNDLE_MARKERS``.
    Missing trees are skipped rather than raising, so an archive carrying only
    one layout enumerates cleanly.
    """
    found: list[str] = []
    for tree in SCAN_TREES:
        base = os.path.join(archive_root, "scans", tree)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            if any(m in filenames for m in BUNDLE_MARKERS):
                found.append(dirpath)
    return sorted(found)


def scan_date_from_dirname(name: str) -> str:
    """Pure: ``YYYY-MM-DD`` from a ``YYYYMMDDTHHMMSSZ`` bundle dirname, else ''."""
    stamp = name.strip()
    if len(stamp) >= 8 and stamp[:8].isdigit():
        return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    return ""


def load_scan_meta(scan_dir: str) -> dict:
    """Impure (filesystem): a bundle's identity dict, whichever layout it uses.

    A ``metadata.yml`` is authoritative when present (mythos layout). Otherwise
    the fields downstream needs are derived from ``TRIAGE.json`` and the
    ``<repo>/<stamp>`` directory layout, and the bundle is labelled
    ``Glasswing`` so it does not inherit the ASVS scan-type label.

    Returns ``{}`` for a directory carrying neither, which the caller reports
    as an anomaly rather than crashing the whole rebuild.
    """
    meta_path = os.path.join(scan_dir, "metadata.yml")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            return parse_flat_yaml(fh.read())

    triage_path = os.path.join(scan_dir, "TRIAGE.json")
    if not os.path.exists(triage_path):
        return {}
    try:
        with open(triage_path, encoding="utf-8") as fh:
            triage = json.load(fh)
    except (OSError, ValueError):
        return {}

    ctx = triage.get("triage_context") or {}
    summary = triage.get("summary") or {}
    target = str(ctx.get("target", "") or "")
    repo_dir = os.path.basename(os.path.dirname(scan_dir))
    findings = summary.get("total")
    if findings is None:
        findings = len(triage.get("findings") or [])
    return {
        "project": repo_dir,
        "repo": target or repo_dir,
        "commit": str(ctx.get("commit", "") or ""),
        "scan_date": scan_date_from_dirname(os.path.basename(scan_dir)),
        "findings_total": findings,
        "scan_kind": "Glasswing",
    }


def compose_scan_id(scan_dir: str, meta: dict) -> str:
    """Pure-ish: the tab's stable key, ``<repo>-<YYYY-MM-DD>-<sha7>``.

    Never the bundle basename: glasswing fleet batches share one timestamp
    across many repos, so a basename key would merge unrelated scans into a
    single row and carry one repo's PMC feedback onto another's. Each component
    is omitted when unknown, and a bundle yielding none of them falls back to
    the directory path relative to ``scans/`` — still unique, just uglier.
    """
    repo = normalize_repo(meta.get("repo", "")) or os.path.basename(os.path.dirname(scan_dir))
    name = repo.split("/")[-1] if repo else ""
    date = str(meta.get("scan_date", "") or "")[:10] or scan_date_from_dirname(
        os.path.basename(scan_dir)
    )
    sha = str(meta.get("commit", "") or meta.get("head_sha", "") or "")[:7]
    parts = [p for p in (name, date, sha) if p]
    return "-".join(parts) if parts else os.path.basename(scan_dir)


def build_scan_row(
    scan_meta: dict,
    pmc_name: str,
    forwarded: str,
    scan_id: str,
) -> list:
    """Pure: the auto-column cells for one scan bundle."""
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
        forwarded,
    ]


def parse_scan_results(grid: list[list[str]]) -> dict[str, list[str]]:
    """Pure: map ``Scan ID -> that row's carried (feedback) cells``.

    Keyed by Scan ID because that is the tab's stable per-bundle identifier
    (repo + date + short SHA); it survives re-sorting and new scans landing
    above a row.

    The header is located by *name*, not by exact equality with
    ``SCAN_RESULTS_HEADER``, and the carried cells are read at whatever offsets
    that header puts them. PMC feedback is the only content on this tab a
    rebuild cannot regenerate, so it has to survive the auto columns changing
    shape — an exact-match lookup would silently drop every feedback cell the
    first time a column was added or removed. A grid with no recognisable
    header yields ``{}``.
    """
    if not grid:
        return {}
    for row in grid:
        cells = [c.strip() for c in row]
        if "Scan ID" not in cells or not all(c in cells for c in SCAN_RESULTS_CARRIED):
            continue
        sid_col = cells.index("Scan ID")
        carried_cols = [cells.index(c) for c in SCAN_RESULTS_CARRIED]
        out: dict[str, list[str]] = {}
        for data in grid[grid.index(row) + 1 :]:
            sid = data[sid_col].strip() if sid_col < len(data) else ""
            if sid:
                out[sid] = [data[j].strip() if j < len(data) else "" for j in carried_cols]
        return out
    return {}


def scan_results_carried(prev_carried: list[str] | None) -> list[str]:
    """Pure: a row's carried (feedback) cells, padded to the carried width."""
    row = prev_carried or []
    return [row[i] if i < len(row) else "" for i in range(len(SCAN_RESULTS_CARRIED))]


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


def build_repo_directory(repos_grid: list[list[str]]) -> dict[str, str]:
    """Pure: normalised ``owner/name`` -> PMC slug, from the Repositories sheet.

    The Repositories sheet maps every public github.com/apache repo to its
    owning PMC, so it resolves scans of repos no PMC listed explicitly in its
    ``Repositories requested`` / ``submitted`` cells — which is most of the
    archive, because Tooling scans beyond the enrolled set.
    """
    if not repos_grid:
        return {}
    idx = {h.strip(): i for i, h in enumerate(repos_grid[0])}
    url_i = idx.get("Repository URL")
    name_i = idx.get("Repository Name")
    slug_i = idx.get("PMC Slug")
    if slug_i is None or (url_i is None and name_i is None):
        return {}
    out: dict[str, str] = {}
    for row in repos_grid[1:]:
        slug = (row[slug_i] if slug_i < len(row) else "").strip().lower()
        if not slug:
            continue
        ref = ""
        if url_i is not None and url_i < len(row):
            ref = row[url_i].strip()
        if not ref and name_i is not None and name_i < len(row):
            ref = f"apache/{row[name_i].strip()}"
        key = normalize_repo(ref)
        if not key:
            continue
        out.setdefault(key, slug)
        # The archive frequently records ``repo`` as a bare name ("camel-k")
        # rather than "apache/camel-k", so index the unqualified form too.
        # Unambiguous here: every row in this sheet is a github.com/apache repo,
        # and one org cannot hold two repos of the same name.
        bare = key.split("/")[-1]
        if bare != key:
            out.setdefault(bare, slug)
    return out


def collect_scan_rows(
    archive_root: str,
    pmc_by_slug: dict[str, tuple[str, str]],
    carried: dict[str, list[str]],
    pmc_by_repo: dict[str, tuple[str, str]] | None = None,
    repo_directory: dict[str, str] | None = None,
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
        scan_meta = load_scan_meta(scan_dir)
        if not scan_meta:
            anomalies.append(
                f"{os.path.relpath(scan_dir, archive_root)}: no metadata.yml and no "
                f"readable TRIAGE.json — bundle skipped"
            )
            continue
        scan_id = compose_scan_id(scan_dir, scan_meta)

        slug = str(scan_meta.get("project", "") or "").strip().lower()
        repo_key = normalize_repo(scan_meta.get("repo", ""))
        _dir = repo_directory or {}
        directory_slug = _dir.get(repo_key, "") or _dir.get(slug, "")
        if slug in pmc_by_slug:
            pmc_name, forwarded = pmc_by_slug[slug]
        elif pmc_by_repo and repo_key in pmc_by_repo:
            pmc_name, forwarded = pmc_by_repo[repo_key]
        elif directory_slug in pmc_by_slug:
            pmc_name, forwarded = pmc_by_slug[directory_slug]
        else:
            pmc_name, forwarded = slug, ""
            anomalies.append(
                f"{scan_id}: project {slug!r} is not a PMC slug and repo "
                f"{repo_key!r} is in no PMC's repo list nor the Repositories sheet"
            )

        row = build_scan_row(scan_meta, pmc_name, forwarded, scan_id)
        rows.append(row + scan_results_carried(carried.get(scan_id)))

    rows.sort(key=lambda r: (str(r[3]), str(r[0])), reverse=True)
    return rows, anomalies


def totals_row(rows: list[list]) -> list:
    """Pure: an aggregate row — scan count and total findings across the tab."""
    fi = SCAN_RESULTS_AUTO.index("Findings (scan)")
    findings = sum(as_int(r[fi]) for r in rows)
    cells: list = [""] * len(SCAN_RESULTS_AUTO)
    cells[0] = f"TOTAL ({len(rows)} scans)"
    cells[fi] = findings
    return cells + [""] * len(SCAN_RESULTS_CARRIED)


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
    trees = [t for t in SCAN_TREES if os.path.isdir(os.path.join(archive_root, "scans", t))]
    if not trees:
        print(
            f"No scans/{{{','.join(SCAN_TREES)}}}/ under {archive_root!r}. Pass "
            "--archive-root pointing at an apache/tooling-agents-private clone.",
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
        repos_grid = fetch_sheet_grid(service, args.spreadsheet_id, "Repositories")
    except Exception:
        repos_grid = []
    repo_directory = build_repo_directory(repos_grid)

    try:
        prev = fetch_sheet_grid(service, args.spreadsheet_id, SCAN_RESULTS_SHEET)
    except Exception:
        prev = []
    carried = parse_scan_results(prev)

    rows, anomalies = collect_scan_rows(
        archive_root, pmc_by_slug, carried, pmc_by_repo, repo_directory
    )

    tab = _Tab()
    tab.row([f"Scan Results — {len(rows)} scan(s) — rebuilt {args.today}"], bold=True)
    tab.row(
        [
            "Auto columns are rebuilt from the tooling-agents-private archive "
            "(scans/glasswing + scans/mythos). The four feedback columns have no "
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
