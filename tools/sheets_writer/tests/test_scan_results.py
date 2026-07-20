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
"""Tests for the pure layer of the Scan Results tab builder."""

from __future__ import annotations

from sheets_writer.scan_results import (
    DISPOSITIONS,
    SCAN_RESULTS_AUTO,
    SCAN_RESULTS_CARRIED,
    SCAN_RESULTS_HEADER,
    as_int,
    build_scan_row,
    find_scan_results_row,
    normalize_repo,
    parse_flat_yaml,
    parse_scan_results,
    pct,
    pmc_cell,
    scan_results_carried,
    scan_type,
    totals_row,
)

SHIRO_ASSESS = """\
project:               shiro
repo:                  apache/shiro
scan_id:               shiro-2026-07-17-cde5990
findings_assessed:     93
dispositions:
  VALID:                       8
  VALID-HARDENING:             82
  OUT-OF-MODEL:                3
  BY-DESIGN:                   0
  KNOWN-NON-FINDING:           0
  MODEL-GAP:                   0
model_gaps:            0
sanity_check:          PASS-with-notes
"""

SHIRO_SCAN = """\
project:           shiro
repo:              apache/shiro
scan_date:         2026-07-17T05:21:10Z
audit_models:      [mythos-5]
asvs_level:        L3
findings_total:    93
"""


class TestParseFlatYaml:
    def test_scalars_and_nested_block(self):
        d = parse_flat_yaml(SHIRO_ASSESS)
        assert d["project"] == "shiro"
        assert d["findings_assessed"] == "93"
        assert d["sanity_check"] == "PASS-with-notes"
        assert d["dispositions"]["VALID"] == "8"
        assert d["dispositions"]["VALID-HARDENING"] == "82"
        assert d["dispositions"]["MODEL-GAP"] == "0"

    def test_nested_block_does_not_swallow_following_scalars(self):
        """A key after the indented block must land at top level, not inside it."""
        d = parse_flat_yaml(SHIRO_ASSESS)
        assert "model_gaps" not in d["dispositions"]
        assert d["model_gaps"] == "0"

    def test_inline_list(self):
        assert parse_flat_yaml(SHIRO_SCAN)["audit_models"] == ["mythos-5"]

    def test_empty_inline_list(self):
        assert parse_flat_yaml("threat_model_refs:     []\n")["threat_model_refs"] == []

    def test_comments_and_blank_lines_ignored(self):
        d = parse_flat_yaml("# leading\n\nproject: x   # trailing\n")
        assert d == {"project": "x"}

    def test_value_containing_colon_is_kept_whole(self):
        d = parse_flat_yaml("threat_model: https://x.example/a:b\n")
        assert d["threat_model"] == "https://x.example/a:b"


class TestNumericHelpers:
    def test_as_int(self):
        assert as_int("42") == 42
        assert as_int(" 7 ") == 7
        assert as_int(None) == 0
        assert as_int("abc") == 0
        assert as_int("", 5) == 5

    def test_pct(self):
        assert pct(8, 93) == "8.6%"
        assert pct(0, 10) == "0.0%"
        assert pct(1, 3) == "33.3%"

    def test_pct_guards_zero_denominator(self):
        assert pct(0, 0) == ""
        assert pct(5, -1) == ""


class TestScanType:
    def test_level_included(self):
        assert scan_type({"asvs_level": "L3"}) == "ASVS L3"

    def test_missing_level_still_labelled(self):
        assert scan_type({}) == "ASVS"


class TestBuildScanRow:
    def _row(self):
        return build_scan_row(
            parse_flat_yaml(SHIRO_SCAN),
            parse_flat_yaml(SHIRO_ASSESS),
            "Apache Shiro",
            "2026-07-18",
            "shiro-2026-07-17-cde5990",
        )

    def test_identity_and_counts(self):
        r = self._row()
        get = lambda name: r[SCAN_RESULTS_AUTO.index(name)]  # noqa: E731
        assert get("PMC") == "Apache Shiro"
        assert get("Repo") == "apache/shiro"
        assert get("Scan ID") == "shiro-2026-07-17-cde5990"
        assert get("Scan date") == "2026-07-17"
        assert get("Scan type") == "ASVS L3"
        assert get("Model") == "mythos-5"
        assert get("Findings (scan)") == 93
        assert get("Assessed") == 93
        assert get("VALID") == 8
        assert get("VALID-HARDENING") == 82
        assert get("OUT-OF-MODEL") == 3
        assert get("Sanity check") == "PASS-with-notes"
        assert get("Forwarded") == "2026-07-18"

    def test_percentages(self):
        r = self._row()
        get = lambda name: r[SCAN_RESULTS_AUTO.index(name)]  # noqa: E731
        assert get("VALID %") == "8.6%"
        assert get("Hardening %") == "88.2%"
        # not-applicable = OUT-OF-MODEL + BY-DESIGN + KNOWN-NON-FINDING = 3
        assert get("Not-applicable %") == "3.2%"

    def test_row_width_matches_auto_header(self):
        assert len(self._row()) == len(SCAN_RESULTS_AUTO)

    def test_unassessed_scan_is_visible_not_zeroed(self):
        """No assessment must not read as 'assessed, zero findings'."""
        r = build_scan_row(parse_flat_yaml(SHIRO_SCAN), None, "Apache Shiro", "", "sid")
        get = lambda name: r[SCAN_RESULTS_AUTO.index(name)]  # noqa: E731
        assert get("Sanity check") == "NOT ASSESSED"
        assert get("Assessed") == ""
        assert get("VALID") == ""
        assert get("VALID %") == ""
        # the scan's own finding count is still reported
        assert get("Findings (scan)") == 93


class TestCarryOver:
    def _grid(self):
        return [
            ["Scan Results — 1 scan(s)"],
            ["blurb"],
            [],
            list(SCAN_RESULTS_HEADER),
            ["Apache Shiro", "apache/shiro", "sid-1"]
            + [""] * (len(SCAN_RESULTS_AUTO) - 3)
            + ["2026-07-18", "Positive", "no major issues", "attachment naming"],
        ]

    def test_parse_keys_by_scan_id(self):
        got = parse_scan_results(self._grid())
        assert list(got) == ["sid-1"]

    def test_carried_cells_round_trip(self):
        prev = parse_scan_results(self._grid())["sid-1"]
        assert scan_results_carried(prev) == [
            "2026-07-18",
            "Positive",
            "no major issues",
            "attachment naming",
        ]

    def test_carried_length_matches_carried_header(self):
        assert len(scan_results_carried(None)) == len(SCAN_RESULTS_CARRIED)

    def test_missing_row_yields_blanks_not_error(self):
        assert scan_results_carried(None) == [""] * len(SCAN_RESULTS_CARRIED)
        assert scan_results_carried(["short"]) == [""] * len(SCAN_RESULTS_CARRIED)

    def test_header_mismatch_yields_empty_map(self):
        """A tab whose header drifted must re-seed blank, not misattribute feedback."""
        assert parse_scan_results([["Totally", "Different"], ["a", "b"]]) == {}

    def test_empty_grid(self):
        assert parse_scan_results([]) == {}

    def test_find_row(self):
        assert find_scan_results_row(self._grid(), "sid-1") == 4
        assert find_scan_results_row(self._grid(), "nope") is None


class TestTotals:
    def test_totals_sum_counts_and_recompute_percentages(self):
        a = build_scan_row(
            parse_flat_yaml(SHIRO_SCAN), parse_flat_yaml(SHIRO_ASSESS), "A", "", "s1"
        )
        b = build_scan_row(
            parse_flat_yaml(SHIRO_SCAN), parse_flat_yaml(SHIRO_ASSESS), "B", "", "s2"
        )
        t = totals_row([a, b])
        get = lambda name: t[SCAN_RESULTS_AUTO.index(name)]  # noqa: E731
        assert get("Findings (scan)") == 186
        assert get("Assessed") == 186
        assert get("VALID") == 16
        # percentages recomputed from summed counts, not averaged
        assert get("VALID %") == "8.6%"
        assert t[0] == "TOTAL (2 scans)"

    def test_totals_width_matches_full_header(self):
        a = build_scan_row(
            parse_flat_yaml(SHIRO_SCAN), parse_flat_yaml(SHIRO_ASSESS), "A", "", "s1"
        )
        assert len(totals_row([a])) == len(SCAN_RESULTS_HEADER)

    def test_totals_ignores_unassessed_rows_in_percentages(self):
        assessed = build_scan_row(
            parse_flat_yaml(SHIRO_SCAN), parse_flat_yaml(SHIRO_ASSESS), "A", "", "s1"
        )
        un = build_scan_row(parse_flat_yaml(SHIRO_SCAN), None, "B", "", "s2")
        t = totals_row([assessed, un])
        get = lambda name: t[SCAN_RESULTS_AUTO.index(name)]  # noqa: E731
        assert get("Findings (scan)") == 186  # both scans' raw findings count
        assert get("Assessed") == 93  # only the assessed one
        assert get("VALID %") == "8.6%"


def test_header_is_auto_plus_carried():
    assert SCAN_RESULTS_HEADER == SCAN_RESULTS_AUTO + SCAN_RESULTS_CARRIED


def test_all_dispositions_are_columns():
    for d in DISPOSITIONS:
        assert d in SCAN_RESULTS_AUTO


class TestNormalizeRepo:
    def test_bare_owner_name(self):
        assert normalize_repo("apache/shiro") == "apache/shiro"

    def test_github_url(self):
        assert normalize_repo("https://github.com/apache/ws-neethi") == "apache/ws-neethi"

    def test_trailing_slash(self):
        assert normalize_repo("https://github.com/apache/arrow/") == "apache/arrow"

    def test_doubled_tail_collapsed(self):
        """The archive writes apache/fineract/fineract for single-repo projects."""
        assert normalize_repo("apache/fineract/fineract") == "apache/fineract"

    def test_subpath_repo_keeps_last_two(self):
        assert normalize_repo("apache/airflow/task-sdk") == "airflow/task-sdk"

    def test_blank(self):
        assert normalize_repo("") == ""
        assert normalize_repo(None) == ""


class TestPmcCell:
    IDX = {"PMC Slug": 0, "PMC Name": 1, "Forwarded scan to PMC": 2}

    def test_reads_by_header_name(self):
        row = ["shiro", "Apache Shiro", "2026-07-18"]
        assert pmc_cell(row, self.IDX, "PMC Slug") == "shiro"
        assert pmc_cell(row, self.IDX, "PMC Name") == "Apache Shiro"

    def test_strips_whitespace(self):
        assert pmc_cell(["  shiro  "], self.IDX, "PMC Slug") == "shiro"

    def test_unknown_header_is_blank(self):
        assert pmc_cell(["shiro"], self.IDX, "Nope") == ""

    def test_short_row_is_blank_not_indexerror(self):
        assert pmc_cell(["shiro"], self.IDX, "Forwarded scan to PMC") == ""
