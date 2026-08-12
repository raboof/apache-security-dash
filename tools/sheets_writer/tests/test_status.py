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

import re

from sheets_writer.status import (
    SCAN_QUEUE_FIXED,
    SCAN_QUEUE_HEADER,
    _parse_addrs,
    added_after_asf_tooling,
    classify_model_origin,
    compute_pmc_status,
    compute_subscription_syncs,
    fill_registry_names,
    parse_criticality,
    parse_scan_queue,
    parse_subscription_registry,
    repo_funnel_timeseries,
    repo_state_counts_asof,
    scan_queue_auto_rows,
    scan_queue_carried,
    scan_queue_has_data,
    subscription_email_rows,
)

PIPELINE_STATES = ["Pre-flight", "Ready", "Submitted", "Triaging", "Delivered"]


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


# 'Model rejected' — the PMC declined an AGENTS.md / agent-readable threat
# model. It outranks every other model status, and a sheet that predates the
# column keeps its old behaviour (HEADER above has no 'Model rejected').
HEADER_WITH_REJECTED = [*HEADER, "Model rejected"]


def test_compute_pmc_status_rejected_beats_nominated() -> None:
    """A draft we wrote does not count once the PMC has said no."""
    row, col_idx = _row(
        HEADER_WITH_REJECTED,
        **{
            "PMC Slug": "x",
            "Security Model": "https://gist.github.com/someone/draft",
            "Model rejected": "2026-07-11 — PMC declined AGENTS.md + agent-readable model",
        },
    )
    assert compute_pmc_status(row, col_idx)["model_status"] == "Rejected"


def test_compute_pmc_status_rejected_beats_verified() -> None:
    """Rejection is terminal: it outranks even a previously verified model."""
    row, col_idx = _row(
        HEADER_WITH_REJECTED,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org/model",
            "Security model verified": "2026-06-01",
            "Model rejected": "2026-07-11",
        },
    )
    assert compute_pmc_status(row, col_idx)["model_status"] == "Rejected"


def test_compute_pmc_status_empty_rejected_cell_is_ignored() -> None:
    """An empty cell in the new column must not change anything."""
    row, col_idx = _row(
        HEADER_WITH_REJECTED,
        **{"PMC Slug": "x", "Security Model": "https://x.org", "Model rejected": ""},
    )
    assert compute_pmc_status(row, col_idx)["model_status"] == "Nominated"


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


# The response SKILL writes the literal 'none' into the Expedite cell when a
# PMC declines the OSS-subscription offer, so the opt-out is recorded rather
# than left blank. It is a sentinel, not an address: it must never be copied
# into 'Claude OSS Subscriptions Submitted' (which asserts a granted
# subscription) nor become a person in the registry.


def test_subscription_sync_ignores_the_none_optout_sentinel() -> None:
    grid, idx = _sub_grid(
        {
            "PMC Slug": "kafka",
            "Date scan requested": "2026-06-14",
            "Expedite Claude OSS Requests": "none",
            "Claude OSS Subscriptions Submitted": "",
        }
    )
    assert compute_subscription_syncs(grid, idx) == []


def test_subscription_sync_keeps_addresses_alongside_a_sentinel() -> None:
    """A cell mixing prose with a real address still syncs the address."""
    grid, idx = _sub_grid(
        {
            "PMC Slug": "spark",
            "Date scan requested": "2026-05-26",
            "Expedite Claude OSS Requests": "none\nreal@apache.org",
            "Claude OSS Subscriptions Submitted": "",
        }
    )
    assert compute_subscription_syncs(grid, idx) == [(2, ["real@apache.org"], ["real@apache.org"])]


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


def test_subscription_email_rows_includes_unsubmitted() -> None:
    # A registrant is tracked the moment their address lands in the Expedite
    # cell — even before the PMC's scan is submitted (no Date scan requested).
    grid, idx = _reg_grid(
        {
            "PMC Slug": "grails",
            "Request date": "2026-05-13",
            "Expedite Claude OSS Requests": "g@apache.org",
        }
    )
    assert subscription_email_rows(grid, idx) == [
        ("g@apache.org", "grails", "2026-05-13"),
    ]


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


def test_fill_registry_names_resolves_annotated_email() -> None:
    # Expedite addresses carry status annotations (e.g. "(registered)"); the
    # bare address must still resolve to a name.
    rows = [
        ["", "jamesfredley@apache.org (registered)", "grails", "2026-05-13", ""],
        ["", "matrei@apache.org (nominated; registration unconfirmed)", "grails", "2026-05-13", ""],
    ]
    filled = fill_registry_names(rows, resolver=_stub_resolver)
    assert filled == 2
    assert rows[0][0] == "James Fredley"
    assert rows[1][0] == "Mattias Reichel"


def test_subscription_email_rows_strips_status_annotations() -> None:
    grid, idx = _reg_grid(
        {
            "PMC Slug": "superset",
            "Request date": "2026-06-08",
            "Date scan requested": "2026-06-11",
            "Expedite Claude OSS Requests": (
                "rusackas@apache.org (registered)\n"
                "villebro@apache.org (nominated; registration unconfirmed)"
            ),
        }
    )
    assert subscription_email_rows(grid, idx) == [
        ("rusackas@apache.org", "superset", "2026-06-08"),
        ("villebro@apache.org", "superset", "2026-06-08"),
    ]


def test_subscription_email_rows_skips_the_none_optout_sentinel() -> None:
    """'none' is an opt-out marker, not a person — it must not enter the registry."""
    grid, idx = _reg_grid(
        {
            "PMC Slug": "kafka",
            "Request date": "2026-05-13",
            "Date scan requested": "2026-06-14",
            "Expedite Claude OSS Requests": "none",
            "Claude OSS Subscriptions Submitted": "none",
        }
    )
    assert subscription_email_rows(grid, idx) == []


def test_subscription_email_rows_keeps_addresses_alongside_a_sentinel() -> None:
    grid, idx = _reg_grid(
        {
            "PMC Slug": "kafka",
            "Request date": "2026-05-13",
            "Date scan requested": "2026-06-14",
            "Expedite Claude OSS Requests": "none\nsomeone@apache.org",
        }
    )
    assert subscription_email_rows(grid, idx) == [("someone@apache.org", "kafka", "2026-05-13")]


def test_parse_registry_normalizes_annotated_email() -> None:
    os_grid = [
        ["Name", "Email", "PMC", "Date", "Submitted manually"],
        ["", "rusackas@apache.org (registered)", "superset", "2026-06-08", ""],
    ]
    rows, emails = parse_subscription_registry(os_grid)
    assert rows[0][1] == "rusackas@apache.org"  # annotation stripped on read
    assert emails == {"rusackas@apache.org"}


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
        "Report recipients",
        "PMC thread (ponymail)",
    ]
    grid = [
        header,
        [
            "Apache PDFBox",
            "pdfbox",
            "https://github.com/apache/pdfbox",
            "2026-06-08",
            "",
            "andrea@apache.org\ntilman@apache.org",
            "https://lists.apache.org/thread/pdfboxtid",
        ],
        [
            "Apache StormCrawler",
            "stormcrawler",
            "https://github.com/apache/stormcrawler",
            "2026-06-08",
            "",
            "jnioche@apache.org",
            "",
        ],
        # Delivered PMC: two repos, report already forwarded. Both repos mirror
        # the one PMC-level Report recipients + ponymail thread.
        [
            "Apache Dubbo",
            "dubbo",
            "https://github.com/apache/dubbo\nhttps://github.com/apache/dubbo-go",
            "2026-06-01",
            "2026-06-05",
            "rainyu@apache.org",
            "https://lists.apache.org/thread/dubbotid",
        ],
        # Not submitted — must be excluded.
        ["Apache Mahout", "mahout", "", "", "", "", ""],
    ]
    return grid, {h: i for i, h in enumerate(header)}


def _repos_grid() -> list[list[str]]:
    return [
        [
            "Repository URL",
            "Repository Name",
            "PMC Slug",
            "Criticality Score (%)",
            "Branches/tags to scan",
        ],
        ["https://github.com/apache/pdfbox", "pdfbox", "pdfbox", "48.3%", ""],
        ["https://github.com/apache/stormcrawler", "stormcrawler", "stormcrawler", "41.9%", ""],
        # Dubbo pinned specific refs -> mirrors into the Scan Queue per repo.
        ["https://github.com/apache/dubbo", "dubbo", "dubbo", "63.0%", "3.2, main"],
        ["https://github.com/apache/dubbo-go", "dubbo-go", "dubbo", "", ""],  # blank score
    ]


def _sq_row(cells: list[str]) -> list[str]:
    """Pad a Scan Queue data row out to the full header width."""
    return cells + [""] * (len(SCAN_QUEUE_HEADER) - len(cells))


def _sq_named(**cells: str) -> list[str]:
    """A Scan Queue data row built by column NAME, not position.

    Keyword keys are header names with non-identifier characters replaced by
    underscores (``Scan 1 · When scanned`` -> ``Scan_1___When_scanned``). Adding
    a fixed column then shifts these fixtures automatically instead of silently
    writing every value into the wrong cell — which is what made the positional
    fixtures miss the carry-over bug this suite now covers.
    """
    slug = {re.sub(r"\W", "_", name): j for j, name in enumerate(SCAN_QUEUE_HEADER)}
    row = [""] * len(SCAN_QUEUE_HEADER)
    for key, value in cells.items():
        row[slug[key]] = value
    return row


def _sq_col(name: str) -> int:
    """Current index of a Scan Queue column, by name."""
    return SCAN_QUEUE_HEADER.index(name)


def test_scan_queue_auto_rows_split_per_branch_sorted() -> None:
    grid, col_idx = _pmcs_grid()
    rows = scan_queue_auto_rows(grid, col_idx, _repos_grid())
    # dubbo pinned "3.2, main" -> two adjacent rows (first_in_group flags); the
    # other repos are one default-branch row each. Mahout excluded.
    assert [(r["repo"].split("/")[-1], r["branch"], r["first_in_group"]) for r in rows] == [
        ("dubbo", "3.2", True),
        ("dubbo", "main", False),
        ("pdfbox", "", True),
        ("stormcrawler", "", True),
        ("dubbo-go", "", True),
    ]
    by = {(r["repo"], r["branch"]): r for r in rows}
    pdf = by[("https://github.com/apache/pdfbox", "")]
    assert pdf["pmc"] == "Apache PDFBox"
    assert pdf["when_ready"] == "2026-06-08"
    # Requested 2026-06-08 (before ASF Tooling's 2026-07-15 internal start).
    assert pdf["added_after_asf_tooling"] == "No"
    assert pdf["report_recipients"] == "andrea@apache.org\ntilman@apache.org"
    assert pdf["model_discussion"] == "https://lists.apache.org/thread/pdfboxtid"
    # Both Dubbo repos share the one PMC-level recipients + ponymail thread.
    dubbo_go = by[("https://github.com/apache/dubbo-go", "")]
    assert dubbo_go["report_recipients"] == "rainyu@apache.org"
    assert by[("https://github.com/apache/dubbo", "main")]["crit"] == "63.0%"
    assert by[("https://github.com/apache/dubbo-go", "")]["crit"] == ""


def test_added_after_asf_tooling_boundary() -> None:
    # Blank when undated; "No" strictly before the 2026-07-15 cutover; "Yes" on
    # and after it (ISO dates compare lexically).
    assert added_after_asf_tooling("") == ""
    assert added_after_asf_tooling("   ") == ""
    assert added_after_asf_tooling("2026-07-01") == "No"
    assert added_after_asf_tooling("2026-07-14") == "No"
    assert added_after_asf_tooling("2026-07-15") == "Yes"
    assert added_after_asf_tooling("2026-07-20") == "Yes"


def test_scan_queue_auto_rows_flags_added_after_asf_tooling() -> None:
    grid, col_idx = _pmcs_grid()
    # Move PDFBox's scan request to after the ASF Tooling internal start.
    dsr = col_idx["Date scan requested"]
    for row in grid[1:]:
        if row[col_idx["PMC Slug"]] == "pdfbox":
            row[dsr] = "2026-07-20"
    rows = scan_queue_auto_rows(grid, col_idx, _repos_grid())
    by = {(r["repo"], r["branch"]): r for r in rows}
    assert by[("https://github.com/apache/pdfbox", "")]["added_after_asf_tooling"] == "Yes"
    # Dubbo (2026-06-01) stays on the legacy side for both its branch rows.
    assert by[("https://github.com/apache/dubbo", "main")]["added_after_asf_tooling"] == "No"
    assert by[("https://github.com/apache/dubbo", "3.2")]["added_after_asf_tooling"] == "No"


def test_scan_queue_auto_rows_blank_repositories_sheet_leaves_crit_blank() -> None:
    grid, col_idx = _pmcs_grid()
    rows = scan_queue_auto_rows(grid, col_idx, [])
    # No Repositories sheet -> no branch data -> one default-branch row per repo.
    assert all(r["crit"] == "" and r["crit_val"] is None and r["branch"] == "" for r in rows)
    assert len(rows) == 4


def test_parse_scan_queue_keys_by_repo_and_branch() -> None:
    dubbo = _sq_named(
        Repo="https://github.com/apache/dubbo",
        PMC="Apache Dubbo",
        Criticality_Score____="63.0%",
        Report_recipients="rainyu@apache.org",
        Branch_tag="main",
        Model_discussion__ponymail_="https://lists.apache.org/thread/dubbotid",
        When_ready="2026-06-01",
        Added_after_ASF_tooling_started="No",
        Scan_1___When_scanned="2026-06-03",
        Scan_1___Model_send_thread__ponymail_="https://lists.apache.org/thread/sendtid",
        Scan_1___When_report_sent="2026-06-05",
        Scan_1___Commit_hash="abc1234",
    )
    pdfbox = _sq_named(
        Repo="https://github.com/apache/pdfbox",
        PMC="Apache PDFBox",
        Criticality_Score____="48.3%",
        Report_recipients="andrea@apache.org",
        Branch_tag="",  # default branch
        Model_discussion__ponymail_="https://lists.apache.org/thread/pdfboxtid",
        When_ready="2026-06-08",
        Added_after_ASF_tooling_started="No",
    )
    sq_grid = [["t"], ["s"], ["c"], [""], SCAN_QUEUE_HEADER, dubbo, pdfbox]
    prev = parse_scan_queue(sq_grid)
    # Keyed by (repo, branch) — the full previous row is retained.
    assert set(prev.keys()) == {
        ("https://github.com/apache/dubbo", "main"),
        ("https://github.com/apache/pdfbox", ""),
    }
    d = scan_queue_carried(prev[("https://github.com/apache/dubbo", "main")])
    assert d[_sq_col("Scan 1 · When scanned")] == "2026-06-03"
    assert d[_sq_col("Scan 1 · Model send thread (ponymail)")] == (
        "https://lists.apache.org/thread/sendtid"
    )
    assert d[_sq_col("Scan 1 · When report sent")] == "2026-06-05"
    assert d[_sq_col("Scan 1 · Commit hash")] == "abc1234"
    assert scan_queue_has_data(prev[("https://github.com/apache/dubbo", "main")]) is True
    # A row with no per-scan cell filled has no scan data.
    assert scan_queue_has_data(prev[("https://github.com/apache/pdfbox", "")]) is False


def test_parse_scan_queue_carries_over_a_narrower_previous_header() -> None:
    """A tab written before a fixed column was added must still carry over.

    Regression: the header was matched by exact equality, so adding one column
    made ``parse_scan_queue`` return ``{}`` — read by the rebuild as "no previous
    rows", which then wrote blanks over every hand-entered per-scan cell. The
    per-scan columns have no automated source, so that loss is unrecoverable.
    Matching must be structural and values must map by column NAME.
    """
    # The header as it stood BEFORE "Security model" was inserted.
    old_fixed = [c for c in SCAN_QUEUE_FIXED if c != "Security model"]
    old_header = old_fixed + [c for c in SCAN_QUEUE_HEADER if c not in SCAN_QUEUE_FIXED]
    assert len(old_header) == len(SCAN_QUEUE_HEADER) - 1
    old_row = [""] * len(old_header)
    for name, value in {
        "Repo": "https://github.com/apache/apisix",
        "Branch/tag": "",
        "Scan 1 · When scanned": "2026-07-15",
        "Scan 1 · Commit hash": "6c68775",
    }.items():
        old_row[old_header.index(name)] = value

    prev = parse_scan_queue([["title"], [""], old_header, old_row])
    key = ("https://github.com/apache/apisix", "")
    assert key in prev, "structural header match must tolerate a narrower header"
    assert scan_queue_has_data(prev[key]) is True
    carried = scan_queue_carried(prev[key])
    # Values land on the CURRENT indices, not the old ones.
    assert carried[_sq_col("Scan 1 · When scanned")] == "2026-07-15"
    assert carried[_sq_col("Scan 1 · Commit hash")] == "6c68775"


def test_parse_scan_queue_unknown_layout_is_empty() -> None:
    assert parse_scan_queue([]) == {}
    assert parse_scan_queue([["wrong", "header"], ["x", "y"]]) == {}


def test_scan_queue_carry_over_and_retained_by_key() -> None:
    """Per-(repo, branch) carry-over: a branch still in the spec reattaches its
    scan data; a branch with scan data that has left the spec is retained (has
    data), never silently dropped."""

    def _dubbo_row(branch: str, when_scanned: str, commit: str) -> list[str]:
        return _sq_named(
            Repo="https://github.com/apache/dubbo",
            PMC="Apache Dubbo",
            Criticality_Score____="63.0%",
            Report_recipients="rainyu@apache.org",
            Branch_tag=branch,
            Model_discussion__ponymail_="https://lists.apache.org/thread/dubbotid",
            When_ready="2026-06-01",
            Added_after_ASF_tooling_started="No",
            Scan_1___When_scanned=when_scanned,
            Scan_1___Commit_hash=commit,
        )

    sq_grid = [
        ["t"],
        ["s"],
        ["c"],
        [""],
        SCAN_QUEUE_HEADER,
        # dubbo "main" is in the current spec (dubbo pins "3.2, main").
        _dubbo_row("main", "2026-06-09", "deadbee"),
        # dubbo "9.9" is NOT in the current spec but carries scan data.
        _dubbo_row("9.9", "2026-06-10", "cafef00"),
    ]
    prev = parse_scan_queue(sq_grid)
    grid, col_idx = _pmcs_grid()
    rows = scan_queue_auto_rows(grid, col_idx, _repos_grid())
    auto_keys = {(r["repo"], r["branch"]) for r in rows}
    # "main" is in the auto set -> its carried scan data reattaches by key.
    assert ("https://github.com/apache/dubbo", "main") in auto_keys
    carried = scan_queue_carried(prev[("https://github.com/apache/dubbo", "main")])
    assert carried[_sq_col("Scan 1 · When scanned")] == "2026-06-09"
    assert carried[_sq_col("Scan 1 · Commit hash")] == "deadbee"
    # "9.9" is not in the auto set but has scan data -> it must be retained.
    off = ("https://github.com/apache/dubbo", "9.9")
    assert off not in auto_keys
    assert scan_queue_has_data(prev[off]) is True


# --- Repo funnel over time -------------------------------------------------


def _funnel_entry(**over) -> dict:
    """A PMC entry with the date + repo-count keys the repo funnel reads."""
    e = {
        "request_date": "",
        "model_verified_date": "",
        "submitted_date": "",
        "received_date": "",
        "forwarded_date": "",
        "repos_requested_count": 0,
        "repos_submitted_count": 0,
    }
    e.update(over)
    return e


def _counts(e: dict, d: str) -> dict:
    return repo_state_counts_asof(e, d, PIPELINE_STATES)


def test_repo_state_counts_held_back_repos_stay_preflight_not_ready() -> None:
    # 3 requested, 1 submitted; full milestone history. The 2 unsubmitted repos
    # were held back once submission started -> they must NOT count as Ready.
    e = _funnel_entry(
        request_date="2026-05-01",
        model_verified_date="2026-05-05",
        submitted_date="2026-05-10",
        received_date="2026-05-15",
        forwarded_date="2026-05-20",
        repos_requested_count=3,
        repos_submitted_count=1,
    )
    # Before any milestone -> nothing counted.
    assert _counts(e, "2026-04-30") == dict.fromkeys(PIPELINE_STATES, 0)
    # Requested only -> all 3 Pre-flight.
    assert _counts(e, "2026-05-01")["Pre-flight"] == 3
    # Model verified but the PMC went on to submit only 1 -> the held-back 2 are
    # Pre-flight, and the to-be-submitted 1 is Ready at this point.
    c = _counts(e, "2026-05-05")
    assert c["Ready"] == 1 and c["Pre-flight"] == 2
    # Submitted -> 1 Submitted, 2 held-back stay Pre-flight (NOT Ready).
    c = _counts(e, "2026-05-10")
    assert c["Submitted"] == 1 and c["Pre-flight"] == 2 and c["Ready"] == 0
    # Received -> 1 Triaging, 2 Pre-flight.
    c = _counts(e, "2026-05-15")
    assert c["Triaging"] == 1 and c["Pre-flight"] == 2
    # Forwarded -> 1 Delivered, 2 Pre-flight.
    c = _counts(e, "2026-05-20")
    assert c["Delivered"] == 1 and c["Pre-flight"] == 2 and c["Ready"] == 0


def test_repo_state_counts_wholesale_ready_pmc_repos_are_ready() -> None:
    # Model verified, nothing submitted yet -> every requested repo is genuinely
    # waiting only for the operator go-ahead, so all count as Ready.
    e = _funnel_entry(
        request_date="2026-05-01",
        model_verified_date="2026-05-05",
        repos_requested_count=4,
        repos_submitted_count=0,
    )
    assert _counts(e, "2026-05-01")["Pre-flight"] == 4  # before model verified
    assert _counts(e, "2026-05-05")["Ready"] == 4  # verified, nothing submitted
    assert _counts(e, "2026-06-01")["Ready"] == 4


def test_repo_state_counts_total_per_pmc_is_constant_after_request() -> None:
    e = _funnel_entry(
        request_date="2026-05-01",
        model_verified_date="2026-05-05",
        submitted_date="2026-05-10",
        repos_requested_count=5,
        repos_submitted_count=2,
    )
    for d in ("2026-05-01", "2026-05-05", "2026-05-10", "2026-06-01"):
        assert sum(_counts(e, d).values()) == 5  # repos only ever shift state


def test_repo_funnel_timeseries_aggregates_across_pmcs() -> None:
    # e1: partially-submitted PMC (1 of 3) -> 2 held back stay Pre-flight.
    e1 = _funnel_entry(
        request_date="2026-05-01",
        model_verified_date="2026-05-05",
        submitted_date="2026-05-10",
        repos_requested_count=3,
        repos_submitted_count=1,
    )
    # e2: requested only, no model yet -> Pre-flight.
    e2 = _funnel_entry(
        request_date="2026-05-03",
        repos_requested_count=2,
        repos_submitted_count=0,
    )
    dates = ["2026-05-01", "2026-05-05", "2026-05-10"]
    series = repo_funnel_timeseries([e1, e2], dates, PIPELINE_STATES)
    by_date = {d: dict(zip(PIPELINE_STATES, counts, strict=True)) for d, counts in series}
    # 2026-05-01: e1 3 Pre-flight; e2 not requested yet.
    assert by_date["2026-05-01"]["Pre-flight"] == 3
    # 2026-05-05: e1 1 Ready (the to-be-submitted) + 2 Pre-flight (held back);
    #             e2 2 Pre-flight. -> Ready 1, Pre-flight 4.
    assert by_date["2026-05-05"]["Ready"] == 1 and by_date["2026-05-05"]["Pre-flight"] == 4
    # 2026-05-10: e1 1 Submitted + 2 Pre-flight (held back, NOT Ready);
    #             e2 2 Pre-flight. -> Submitted 1, Pre-flight 4, Ready 0.
    assert by_date["2026-05-10"]["Submitted"] == 1
    assert by_date["2026-05-10"]["Ready"] == 0 and by_date["2026-05-10"]["Pre-flight"] == 4
