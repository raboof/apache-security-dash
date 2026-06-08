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

from __future__ import annotations

from sheets_writer.status import (
    SCAN_QUEUE_HEADER,
    _parse_addrs,
    classify_model_origin,
    compute_pmc_status,
    compute_subscription_syncs,
    fill_registry_names,
    parse_criticality,
    parse_scan_queue,
    parse_subscription_registry,
    scan_queue_auto_rows,
    subscription_email_rows,
)


def _row(header: list[str], **overrides) -> tuple[list[str], dict[str, int]]:
    row = [""] * len(header)
    for col, val in overrides.items():
        row[header.index(col)] = val
    col_idx = {h: i for i, h in enumerate(header)}
    return row, col_idx


HEADER = [
    "PMC Name",
    "PMC Slug",
    "Request date",
    "Repositories requested",
    "Repositories submitted",
    "Contact Person",
    "Backup contact",
    "Security Model",
    "Security model verified",
    "Date scan requested",
    "Date scan received",
    "Forwarded scan to PMC",
    "PR/Issues",
    "Notes",
]


def test_compute_pmc_status_pre_flight() -> None:
    """Model not yet verified → Pre-flight."""
    row, col_idx = _row(
        HEADER,
        **{"PMC Slug": "x", "PMC Name": "Apache X", "Security Model": "https://x.org"},
    )
    result = compute_pmc_status(row, col_idx)
    assert result["state"] == "Pre-flight"
    assert result["model_status"] == "Nominated"


def test_compute_pmc_status_no_model_is_missing() -> None:
    row, col_idx = _row(HEADER, **{"PMC Slug": "x"})
    assert compute_pmc_status(row, col_idx)["model_status"] == "Missing"


def test_compute_pmc_status_ready() -> None:
    """Model verified, no submission yet → Ready."""
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
        },
    )
    result = compute_pmc_status(row, col_idx)
    assert result["state"] == "Ready"
    assert result["model_status"] == "Verified"


def test_compute_pmc_status_submitted() -> None:
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
            "Date scan requested": "2026-05-15",
        },
    )
    assert compute_pmc_status(row, col_idx)["state"] == "Submitted"


def test_compute_pmc_status_triaging() -> None:
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
            "Date scan requested": "2026-05-15",
            "Date scan received": "2026-05-20",
        },
    )
    assert compute_pmc_status(row, col_idx)["state"] == "Triaging"


def test_compute_pmc_status_delivered() -> None:
    """Once Forwarded is filled, it wins regardless of earlier columns."""
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
            "Date scan requested": "2026-05-15",
            "Date scan received": "2026-05-20",
            "Forwarded scan to PMC": "2026-05-21",
        },
    )
    assert compute_pmc_status(row, col_idx)["state"] == "Delivered"


def test_compute_pmc_status_repo_counts() -> None:
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Repositories requested": (
                "https://github.com/apache/x\n# commented out\n\nhttps://github.com/apache/y"
            ),
            "Repositories submitted": "https://github.com/apache/x",
        },
    )
    result = compute_pmc_status(row, col_idx)
    assert result["repos_requested_count"] == 2  # blank + comment lines skipped
    assert result["repos_submitted_count"] == 1


def test_compute_pmc_status_pr_urls_when_no_pr_cell() -> None:
    """Empty PR/Issues → no shell-out, all PR counts zero."""
    row, col_idx = _row(HEADER, **{"PMC Slug": "x"})
    result = compute_pmc_status(row, col_idx)
    assert result["pr_urls"] == []
    assert result["pr_open"] == result["pr_merged"] == result["pr_closed"] == 0


def test_compute_pmc_status_tolerant_to_missing_columns() -> None:
    """col_idx missing a column → that field reads as empty string."""
    row, col_idx = _row(HEADER, **{"PMC Slug": "x"})
    # Drop a column from col_idx to simulate a narrower sheet.
    del col_idx["Notes"]
    result = compute_pmc_status(row, col_idx)
    assert result["notes"] == ""


def test_classify_model_origin_none() -> None:
    assert classify_model_origin("", "") == "none"
    assert classify_model_origin("   ", "some notes") == "none"


def test_classify_model_origin_security_team() -> None:
    assert classify_model_origin("https://x.org/tm", "Path 3 — we drafted it") == "security-team"
    assert classify_model_origin("drafted via threat-model-producer", "") == "security-team"


def test_classify_model_origin_pmc_scovetta() -> None:
    assert classify_model_origin("PMC is writing one", "path 2") == "pmc-scovetta"
    assert (
        classify_model_origin("fresh model per the Apache Security threat-model rubric", "")
        == "pmc-scovetta"
    )


def test_classify_model_origin_reviewed() -> None:
    assert classify_model_origin("https://x.org/model", "discoverability PR opened") == "reviewed"
    assert classify_model_origin("existing model", "we added §11a additions") == "reviewed"


def test_classify_model_origin_existing() -> None:
    # Has a model, no correction/path markers → accepted as-is.
    assert classify_model_origin("https://x.org/threat-model.md", "looks complete") == "existing"


def test_compute_pmc_status_sets_model_origin() -> None:
    row, col_idx = _row(
        HEADER,
        **{"PMC Slug": "x", "Security Model": "https://x.org", "Notes": "Path 3 — we drafted it"},
    )
    assert compute_pmc_status(row, col_idx)["model_origin"] == "security-team"


# --- OSS-subscription sync (Expedite -> Subscriptions Submitted) ---

_SUB_HEADER = [
    "PMC Slug",
    "Date scan requested",
    "Expedite Claude OSS Requests",
    "Claude OSS Subscriptions Submitted",
]


def _sub_grid(*rows: dict) -> tuple[list[list[str]], dict[str, int]]:
    grid = [_SUB_HEADER]
    for r in rows:
        grid.append([r.get(h, "") for h in _SUB_HEADER])
    return grid, {h: i for i, h in enumerate(_SUB_HEADER)}


def test_parse_addrs_splits_newlines_and_commas_dedup() -> None:
    assert _parse_addrs("a@x.org\nb@x.org, a@x.org\n") == ["a@x.org", "b@x.org"]
    assert _parse_addrs("") == []


def test_subscription_sync_submitted_pmc_appends_expedite() -> None:
    grid, idx = _sub_grid(
        {
            "PMC Slug": "airflow",
            "Date scan requested": "2026-06-01",
            "Expedite Claude OSS Requests": "a@apache.org\nb@apache.org",
        }
    )
    syncs = compute_subscription_syncs(grid, idx)
    assert syncs == [(2, ["a@apache.org", "b@apache.org"], ["a@apache.org", "b@apache.org"])]


def test_subscription_sync_skips_unsubmitted_pmc() -> None:
    # Verified/expedited but no Date scan requested -> not yet relayed, skip.
    grid, idx = _sub_grid({"PMC Slug": "grails", "Expedite Claude OSS Requests": "a@apache.org"})
    assert compute_subscription_syncs(grid, idx) == []


def test_subscription_sync_is_append_only_and_idempotent() -> None:
    # Existing address preserved; only the genuinely-new one is appended.
    grid, idx = _sub_grid(
        {
            "PMC Slug": "spark",
            "Date scan requested": "2026-05-26",
            "Expedite Claude OSS Requests": "old@apache.org\nnew@apache.org",
            "Claude OSS Subscriptions Submitted": "old@apache.org",
        }
    )
    assert compute_subscription_syncs(grid, idx) == [
        (2, ["old@apache.org", "new@apache.org"], ["new@apache.org"])
    ]
    # Once both are present, a re-run produces no change (idempotent).
    grid2, idx2 = _sub_grid(
        {
            "PMC Slug": "spark",
            "Date scan requested": "2026-05-26",
            "Expedite Claude OSS Requests": "old@apache.org\nnew@apache.org",
            "Claude OSS Subscriptions Submitted": "old@apache.org\nnew@apache.org",
        }
    )
    assert compute_subscription_syncs(grid2, idx2) == []


def test_subscription_sync_no_expedite_column_is_noop() -> None:
    grid = [["PMC Slug"], ["airflow"]]
    assert compute_subscription_syncs(grid, {"PMC Slug": 0}) == []


# --- OSS-subscription registry (the persistent 'OSS Subscriptions' tab) ---

_REG_HEADER = [
    "PMC Slug",
    "Request date",
    "Date scan requested",
    "Expedite Claude OSS Requests",
    "Claude OSS Subscriptions Submitted",
]


def _reg_grid(*rows: dict) -> tuple[list[list[str]], dict[str, int]]:
    grid = [_REG_HEADER]
    for r in rows:
        grid.append([r.get(h, "") for h in _REG_HEADER])
    return grid, {h: i for i, h in enumerate(_REG_HEADER)}


def test_subscription_email_rows_unions_dedups_and_carries_request_date() -> None:
    grid, idx = _reg_grid(
        {
            "PMC Slug": "camel",
            "Request date": "2026-05-13",
            "Date scan requested": "2026-05-26",
            "Expedite Claude OSS Requests": "a@apache.org",
            "Claude OSS Subscriptions Submitted": "a@apache.org\nb@apache.org",
        },
        {
            "PMC Slug": "spark",
            "Request date": "2026-05-15",
            "Date scan requested": "2026-05-26",
            "Expedite Claude OSS Requests": "a@apache.org\nc@apache.org",  # a@ dups camel
        },
    )
    assert subscription_email_rows(grid, idx) == [
        ("a@apache.org", "camel", "2026-05-13"),
        ("b@apache.org", "camel", "2026-05-13"),
        ("c@apache.org", "spark", "2026-05-15"),
    ]


def test_subscription_email_rows_skips_unsubmitted() -> None:
    grid, idx = _reg_grid(
        {
            "PMC Slug": "grails",
            "Request date": "2026-05-13",
            "Expedite Claude OSS Requests": "g@apache.org",
        }
    )
    assert subscription_email_rows(grid, idx) == []


def test_parse_registry_reads_data_rows_and_emails() -> None:
    os_grid = [
        ["Glasswing — OSS Subscriptions · title"],
        ["some note"],
        ["3 people"],
        [""],
        ["Name", "Email", "PMC", "Date", "Submitted manually"],
        ["Andrea Cosentino", "acosentino@apache.org", "camel", "2026-05-13", "Expedite requested"],
        ["", "b@apache.org", "spark", "2026-05-15", ""],
        ["", "", "", "", ""],  # blank email -> ignored
    ]
    rows, emails = parse_subscription_registry(os_grid)
    assert emails == {"acosentino@apache.org", "b@apache.org"}
    assert rows[0] == [
        "Andrea Cosentino",
        "acosentino@apache.org",
        "camel",
        "2026-05-13",
        "Expedite requested",
    ]


def test_parse_registry_unknown_layout_is_empty() -> None:
    # No matching header (e.g. an older tab layout) -> re-seed from scratch.
    assert parse_subscription_registry([["PMC", "Slug", "addrs"], ["x", "y", "z"]]) == ([], set())
    assert parse_subscription_registry([]) == ([], set())


# --- registry Name resolution (auto-fill from the committer directory) ---


def _stub_resolver(emails):
    table = {
        "jamesfredley@apache.org": "James Fredley",
        "matrei@apache.org": "Mattias Reichel",
        "new@apache.org": "New Person",
    }
    return {e: table[e] for e in emails if e in table}


def test_fill_registry_names_fills_blanks_and_preserves_manual() -> None:
    rows = [
        ["Andrea Cosentino", "acosentino@apache.org", "camel", "2026-05-13", "Expedite requested"],
        ["", "jamesfredley@apache.org", "grails", "2026-05-13", ""],  # blank -> fill
        ["", "matrei@apache.org", "grails", "2026-05-13", ""],  # blank -> fill
        ["", "unknown@apache.org", "x", "2026-05-13", ""],  # unresolved -> stays blank
    ]
    filled = fill_registry_names(rows, resolver=_stub_resolver)
    assert filled == 2
    assert rows[0][0] == "Andrea Cosentino"  # manual name preserved
    assert rows[1][0] == "James Fredley"
    assert rows[2][0] == "Mattias Reichel"
    assert rows[3][0] == ""  # unresolved left blank


def test_fill_registry_names_no_blanks_skips_resolver() -> None:
    rows = [["Andrea Cosentino", "acosentino@apache.org", "camel", "2026-05-13", "x"]]

    def _boom(_emails):  # must not be called when nothing is pending
        raise AssertionError("resolver should not be called")

    assert fill_registry_names(rows, resolver=_boom) == 0


# --- Scan Queue tab --------------------------------------------------------


def test_parse_criticality_handles_percent_fraction_and_blank() -> None:
    assert parse_criticality("48.3%") == 48.3
    assert parse_criticality("41.9") == 41.9
    assert parse_criticality("0.483") == 48.3  # 0..1 fraction scaled to percent
    assert parse_criticality("") is None
    assert parse_criticality("   ") is None
    assert parse_criticality("n/a") is None


def _pmcs_grid() -> tuple[list[list[str]], dict]:
    header = [
        "PMC Name",
        "PMC Slug",
        "Repositories submitted",
        "Date scan requested",
        "Forwarded scan to PMC",
    ]
    grid = [
        header,
        ["Apache PDFBox", "pdfbox", "https://github.com/apache/pdfbox", "2026-06-08", ""],
        [
            "Apache StormCrawler",
            "stormcrawler",
            "https://github.com/apache/stormcrawler",
            "2026-06-08",
            "",
        ],
        # Delivered PMC: two repos, report already forwarded.
        [
            "Apache Dubbo",
            "dubbo",
            "https://github.com/apache/dubbo\nhttps://github.com/apache/dubbo-go",
            "2026-06-01",
            "2026-06-05",
        ],
        # Not submitted — must be excluded.
        ["Apache Mahout", "mahout", "", "", ""],
    ]
    return grid, {h: i for i, h in enumerate(header)}


def _repos_grid() -> list[list[str]]:
    return [
        ["Repository URL", "Repository Name", "PMC Slug", "Criticality Score (%)"],
        ["https://github.com/apache/pdfbox", "pdfbox", "pdfbox", "48.3%"],
        ["https://github.com/apache/stormcrawler", "stormcrawler", "stormcrawler", "41.9%"],
        ["https://github.com/apache/dubbo", "dubbo", "dubbo", "63.0%"],
        ["https://github.com/apache/dubbo-go", "dubbo-go", "dubbo", ""],  # blank score
    ]


def test_scan_queue_auto_rows_expands_sorts_and_carries_dates() -> None:
    grid, col_idx = _pmcs_grid()
    rows = scan_queue_auto_rows(grid, col_idx, _repos_grid())
    # One row per submitted repo (4 total); Mahout excluded.
    assert [r["repo"] for r in rows] == [
        "https://github.com/apache/dubbo",  # 63.0 — highest
        "https://github.com/apache/pdfbox",  # 48.3
        "https://github.com/apache/stormcrawler",  # 41.9
        "https://github.com/apache/dubbo-go",  # blank score sorts last
    ]
    by_repo = {r["repo"]: r for r in rows}
    assert by_repo["https://github.com/apache/pdfbox"]["pmc"] == "Apache PDFBox"
    assert by_repo["https://github.com/apache/pdfbox"]["when_ready"] == "2026-06-08"
    assert by_repo["https://github.com/apache/pdfbox"]["when_report_sent"] == ""
    # Delivered repo carries the forwarded date through automatically.
    assert by_repo["https://github.com/apache/dubbo"]["when_report_sent"] == "2026-06-05"
    assert by_repo["https://github.com/apache/dubbo-go"]["crit"] == ""


def test_scan_queue_auto_rows_blank_repositories_sheet_leaves_crit_blank() -> None:
    grid, col_idx = _pmcs_grid()
    rows = scan_queue_auto_rows(grid, col_idx, [])
    # No criticality data -> all blank, all sort last together (by URL).
    assert all(r["crit"] == "" and r["crit_val"] is None for r in rows)
    assert len(rows) == 4


def test_parse_scan_queue_keys_manual_columns_by_repo() -> None:
    sq_grid = [
        ["Glasswing scan pipeline — Scan Queue · as of 2026-06-08"],
        ["Every repo submitted ..."],
        ["4 repo(s) submitted to the vendor."],
        [""],
        SCAN_QUEUE_HEADER,
        [
            "https://github.com/apache/dubbo",
            "Apache Dubbo",
            "63.0%",
            "2026-06-01",
            "2026-06-03",  # when scanned (manual)
            "abc1234",  # commit hash (manual)
            "2026-06-05",
        ],
        [
            "https://github.com/apache/pdfbox",
            "Apache PDFBox",
            "48.3%",
            "2026-06-08",
            "",  # not yet scanned
            "",
            "",
        ],
    ]
    manual = parse_scan_queue(sq_grid)
    assert manual["https://github.com/apache/dubbo"] == ("2026-06-03", "abc1234")
    # Blank manual cells round-trip as empty (no spurious entry suppression).
    assert manual["https://github.com/apache/pdfbox"] == ("", "")


def test_parse_scan_queue_unknown_layout_is_empty() -> None:
    assert parse_scan_queue([]) == {}
    assert parse_scan_queue([["wrong", "header"], ["x", "y"]]) == {}


def test_scan_queue_manual_data_follows_repo_across_resort() -> None:
    """The preservation contract: hand-entered values are keyed by repo, so when
    a higher-criticality repo is added later the manual data stays attached to
    its original repo even though the row index changes."""
    # Round 1: only pdfbox + stormcrawler submitted; operator hand-fills pdfbox.
    sq_round1 = [
        ["title"],
        ["summary"],
        ["count"],
        [""],
        SCAN_QUEUE_HEADER,
        [
            "https://github.com/apache/pdfbox",
            "Apache PDFBox",
            "48.3%",
            "2026-06-08",
            "2026-06-09",  # manual when-scanned
            "deadbee",  # manual commit
            "",
        ],
    ]
    manual = parse_scan_queue(sq_round1)
    # Round 2: dubbo (higher criticality) now submitted -> it sorts ABOVE pdfbox.
    grid, col_idx = _pmcs_grid()
    rows = scan_queue_auto_rows(grid, col_idx, _repos_grid())
    rendered = [(r["repo"], *manual.get(r["repo"], ("", ""))) for r in rows]
    # pdfbox is no longer row 0, but its manual data is still attached to it.
    pdfbox = next(t for t in rendered if t[0] == "https://github.com/apache/pdfbox")
    assert pdfbox == ("https://github.com/apache/pdfbox", "2026-06-09", "deadbee")
    # The newly-added higher-criticality repo has no manual data yet.
    dubbo = next(t for t in rendered if t[0] == "https://github.com/apache/dubbo")
    assert dubbo == ("https://github.com/apache/dubbo", "", "")
