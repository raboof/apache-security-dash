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

import json
import os

from sheets_writer import scan_results
from sheets_writer.scan_results import (
    COL_WIDTHS,
    PROSE_COLS,
    SCAN_RESULTS_AUTO,
    SCAN_RESULTS_CARRIED,
    SCAN_RESULTS_CARRIED_COLS,
    SCAN_RESULTS_HEADER,
    as_int,
    build_scan_row,
    compose_scan_id,
    find_scan_dirs,
    find_scan_results_row,
    load_scan_meta,
    normalize_repo,
    parse_flat_yaml,
    parse_scan_results,
    pmc_cell,
    present_trees,
    scan_date_from_dirname,
    scan_results_carried,
    scan_type,
    totals_row,
    tree_of,
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


class TestScanType:
    def test_level_included(self):
        assert scan_type({"asvs_level": "L3"}) == "ASVS L3"

    def test_missing_level_still_labelled(self):
        assert scan_type({}) == "ASVS"

    def test_declared_kind_wins(self):
        assert scan_type({"scan_kind": "Glasswing", "asvs_level": "L3"}) == "Glasswing"


class TestBuildScanRow:
    def _row(self):
        return build_scan_row(
            parse_flat_yaml(SHIRO_SCAN),
            "Apache Shiro",
            "2026-07-18",
            "shiro-2026-07-17-cde5990",
            "scans/mythos/shiro/shiro-2026-07-17-cde5990",
        )

    def test_folder_locates_the_bundle(self):
        """A scan id no longer says which tree the report is in."""
        r = self._row()
        assert r[SCAN_RESULTS_AUTO.index("Folder")] == (
            "scans/mythos/shiro/shiro-2026-07-17-cde5990"
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
        assert get("Forwarded") == "2026-07-18"

    def test_row_width_matches_auto_header(self):
        assert len(self._row()) == len(SCAN_RESULTS_AUTO)

    def test_no_assessment_columns_remain(self):
        """The pre-forward assessment is retired; its columns must be gone."""
        for gone in ("Assessed", "Sanity check", "VALID", "VALID %", "Not-applicable %"):
            assert gone not in SCAN_RESULTS_AUTO


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

    def test_short_input_is_padded_not_discarded(self):
        """A truncated row keeps the feedback it does have.

        Sheets omits trailing empty cells, so a row whose later feedback
        columns were never filled comes back short. Padding preserves the
        earlier cells; blanking the whole thing would throw away real feedback.
        """
        assert scan_results_carried(["2026-07-20"]) == ["2026-07-20", "", "", ""]

    def test_unrecognisable_header_yields_empty_map(self):
        """A grid with no Scan ID / feedback columns must re-seed blank."""
        assert parse_scan_results([["Totally", "Different"], ["a", "b"]]) == {}

    def test_feedback_survives_auto_column_changes(self):
        """The auto columns may change shape; PMC feedback cannot be regenerated.

        Carry-over locates the header and the carried columns by NAME, so a tab
        written by an older build -- with extra auto columns that no longer
        exist -- still yields its feedback rather than silently dropping it.
        """
        legacy_header = [
            "PMC",
            "Repo",
            "Scan ID",
            "Scan date",
            "Scan type",
            "Model",
            "Findings (scan)",
            "Assessed",
            "VALID",
            "Sanity check",
            "Forwarded",
            *SCAN_RESULTS_CARRIED,
        ]
        grid = [
            ["Scan Results"],
            legacy_header,
            [
                "Apache Shiro",
                "apache/shiro",
                "sid-1",
                "",
                "",
                "",
                "93",
                "93",
                "8",
                "PASS",
                "2026-07-18",
                "2026-07-20",
                "Negative",
                "descriptions unreadable",
                "shorter reports",
            ],
        ]
        got = parse_scan_results(grid)
        assert scan_results_carried(got["sid-1"]) == [
            "2026-07-20",
            "Negative",
            "descriptions unreadable",
            "shorter reports",
        ]

    def test_empty_grid(self):
        assert parse_scan_results([]) == {}

    def test_find_row(self):
        assert find_scan_results_row(self._grid(), "sid-1") == 4
        assert find_scan_results_row(self._grid(), "nope") is None


class TestTotals:
    def _row(self, pmc, sid):
        return build_scan_row(parse_flat_yaml(SHIRO_SCAN), pmc, "", sid)

    def test_totals_sum_findings(self):
        t = totals_row([self._row("A", "s1"), self._row("B", "s2")])
        assert t[SCAN_RESULTS_AUTO.index("Findings (scan)")] == 186
        assert t[0] == "TOTAL (2 scans)"

    def test_totals_width_matches_full_header(self):
        assert len(totals_row([self._row("A", "s1")])) == len(SCAN_RESULTS_HEADER)

    def test_totals_of_nothing(self):
        assert totals_row([])[0] == "TOTAL (0 scans)"


def test_header_is_auto_plus_carried():
    assert SCAN_RESULTS_HEADER == SCAN_RESULTS_AUTO + SCAN_RESULTS_CARRIED


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


class TestProseFormatting:
    def test_prose_cols_are_the_free_text_ones(self):
        names = [SCAN_RESULTS_HEADER[i] for i in PROSE_COLS]
        assert names == ["Sentiment", "Feedback summary", "Improvements suggested"]

    def test_prose_cols_are_in_the_carried_block(self):
        """Wrapping must target the agent-authored columns, not an auto one."""
        for i in PROSE_COLS:
            assert i in SCAN_RESULTS_CARRIED_COLS

    def test_every_prose_col_has_a_width(self):
        """A wrapped column with no width just makes very tall rows."""
        for i in PROSE_COLS:
            assert COL_WIDTHS.get(i, 0) > 0

    def test_widths_are_valid_column_indices(self):
        for i in COL_WIDTHS:
            assert 0 <= i < len(SCAN_RESULTS_HEADER)


class TestGlasswingBundles:
    """Glasswing bundles carry no metadata.yml — identity comes from TRIAGE.json."""

    @staticmethod
    def _bundle(tmp_path, repo, stamp, target, commit, total):
        d = tmp_path / "scans" / "glasswing" / repo / stamp
        d.mkdir(parents=True)
        (d / "TRIAGE.json").write_text(
            json.dumps(
                {
                    "triage_context": {"target": target, "commit": commit},
                    "summary": {"total": total},
                }
            )
        )
        return str(d)

    def test_finds_glasswing_bundles_without_metadata_yml(self, tmp_path):
        self._bundle(tmp_path, "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 253)
        assert len(find_scan_dirs(str(tmp_path))) == 1

    def test_still_finds_mythos_metadata_bundles(self, tmp_path):
        d = tmp_path / "scans" / "mythos" / "shiro" / "shiro-2026-07-17-cde5990"
        d.mkdir(parents=True)
        (d / "metadata.yml").write_text(SHIRO_SCAN)
        assert find_scan_dirs(str(tmp_path)) == [str(d)]

    def test_missing_tree_is_skipped_not_raised(self, tmp_path):
        assert find_scan_dirs(str(tmp_path)) == []

    def test_meta_derived_from_triage_json(self, tmp_path):
        d = self._bundle(tmp_path, "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb683e412", 253)
        m = load_scan_meta(d)
        assert m["repo"] == "apache/nuttx"
        assert m["project"] == "nuttx"
        assert m["scan_date"] == "2026-08-11"
        assert m["findings_total"] == 253
        assert m["scan_kind"] == "Glasswing"

    def test_metadata_yml_wins_when_present(self, tmp_path):
        d = tmp_path / "scans" / "glasswing" / "shiro" / "s"
        d.mkdir(parents=True)
        (d / "metadata.yml").write_text(SHIRO_SCAN)
        (d / "TRIAGE.json").write_text(json.dumps({"triage_context": {"target": "wrong/repo"}}))
        assert load_scan_meta(str(d))["repo"] == "apache/shiro"

    def test_unreadable_bundle_yields_empty_meta(self, tmp_path):
        d = tmp_path / "scans" / "glasswing" / "x" / "s"
        d.mkdir(parents=True)
        (d / "TRIAGE.json").write_text("{not json")
        assert load_scan_meta(str(d)) == {}

    def test_glasswing_is_not_labelled_asvs(self, tmp_path):
        d = self._bundle(tmp_path, "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 1)
        assert scan_type(load_scan_meta(d)) == "Glasswing"


class TestAugustScansTree:
    """The delivery tree moved to a top-level ``august-scans/`` on 2026-09-08.

    It re-drops most of ``scans/glasswing/`` and adds bundles the old tree never
    had, so both trees are walked and a scan present in both must yield one row.
    """

    @staticmethod
    def _bundle(root, tree, repo, stamp, target, commit, total):
        d = root.joinpath(*tree.split("/")) / repo / stamp
        d.mkdir(parents=True)
        (d / "TRIAGE.json").write_text(
            json.dumps(
                {
                    "triage_context": {"target": target, "commit": commit},
                    "summary": {"total": total},
                }
            )
        )
        return str(d)

    def test_finds_bundles_in_the_top_level_august_scans_tree(self, tmp_path):
        """``august-scans/`` is not under ``scans/`` — the old join missed it entirely."""
        d = self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 253
        )
        assert find_scan_dirs(str(tmp_path)) == [d]

    def test_august_scans_is_walked_before_glasswing(self, tmp_path):
        """Tree order is load-bearing: it decides which copy of a bundle wins."""
        gw = self._bundle(
            tmp_path, "scans/glasswing", "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 253
        )
        aug = self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 253
        )
        assert find_scan_dirs(str(tmp_path)) == [aug, gw]

    def test_folder_column_records_the_tree_the_row_came_from(self, tmp_path):
        """The whole point of the column: which of the live trees holds this scan."""
        self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5da", 1
        )
        rows, _ = scan_results.collect_scan_rows(str(tmp_path), {"nuttx": ("Apache NuttX", "")}, {})
        assert rows[0][SCAN_RESULTS_AUTO.index("Folder")] == ("august-scans/nuttx/20260811T231034Z")

    def test_folder_shows_the_winning_copy_after_a_supersession(self, tmp_path):
        """A superseded row must not point at the copy that lost."""
        self._bundle(
            tmp_path, "scans/glasswing", "nuttx", "20260811T231034Z", "apache/nuttx", "5da", 9
        )
        self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5da", 1
        )
        rows, _ = scan_results.collect_scan_rows(str(tmp_path), {"nuttx": ("Apache NuttX", "")}, {})
        assert len(rows) == 1
        assert rows[0][SCAN_RESULTS_AUTO.index("Folder")].startswith("august-scans/")

    def test_present_trees_finds_the_top_level_tree(self, tmp_path):
        """The guard on ``build-scan-results-tab`` reads this; a ``scans/`` prefix
        here made the command refuse every real archive clone.
        """
        self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5da", 1
        )
        assert present_trees(str(tmp_path)) == ["august-scans"]

    def test_present_trees_is_empty_for_a_non_archive(self, tmp_path):
        assert present_trees(str(tmp_path)) == []

    def test_tree_of_names_the_tree(self, tmp_path):
        aug = self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 1
        )
        gw = self._bundle(
            tmp_path, "scans/glasswing", "shiro", "20260810T152236Z", "apache/shiro", "abc1234", 1
        )
        assert tree_of(aug, str(tmp_path)) == "august-scans"
        assert tree_of(gw, str(tmp_path)) == "scans/glasswing"
        assert tree_of(str(tmp_path / "scans" / "experiments" / "x"), str(tmp_path)) == ""

    def test_redropped_bundle_yields_one_row_from_august_scans(self, tmp_path):
        """~228 bundles sit in both trees; two rows would split their carried feedback."""
        self._bundle(
            tmp_path, "scans/glasswing", "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 999
        )
        self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 253
        )
        rows, anomalies = scan_results.collect_scan_rows(
            str(tmp_path), {"nuttx": ("Apache NuttX", "")}, {}
        )
        assert anomalies == []
        assert len(rows) == 1
        assert rows[0][SCAN_RESULTS_HEADER.index("Findings (scan)")] == 253

    def test_bundle_only_in_glasswing_is_still_emitted(self, tmp_path):
        """The old tree kept the bundles that were never re-dropped."""
        self._bundle(
            tmp_path, "scans/glasswing", "shiro", "20260810T152236Z", "apache/shiro", "abc1234", 7
        )
        rows, anomalies = scan_results.collect_scan_rows(
            str(tmp_path), {"shiro": ("Apache Shiro", "")}, {}
        )
        assert anomalies == []
        assert len(rows) == 1

    def test_same_id_twice_in_one_tree_is_an_anomaly(self, tmp_path):
        """Within a tree a duplicate id is a data problem, not a supersession."""
        self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T231034Z", "apache/nuttx", "5dafb68", 253
        )
        self._bundle(
            tmp_path, "august-scans", "nuttx", "20260811T235959Z", "apache/nuttx", "5dafb68", 253
        )
        rows, anomalies = scan_results.collect_scan_rows(
            str(tmp_path), {"nuttx": ("Apache NuttX", "")}, {}
        )
        assert len(rows) == 1
        assert len(anomalies) == 1
        assert "same scan id" in anomalies[0]


class TestComposeScanId:
    """Batch-shared timestamps must not collapse distinct repos into one row."""

    def test_composed_from_repo_date_and_sha(self):
        meta = {"repo": "apache/nuttx", "scan_date": "2026-08-11", "commit": "5dafb683e412ce2"}
        assert compose_scan_id("/a/scans/glasswing/nuttx/20260811T231034Z", meta) == (
            "nuttx-2026-08-11-5dafb68"
        )

    def test_same_batch_timestamp_yields_distinct_ids(self):
        """17 repos share 20260811T043305Z in the archive; basenames would collide."""
        stamp = "20260811T043305Z"
        a = compose_scan_id(
            f"/a/scans/glasswing/arrow/{stamp}",
            {"repo": "apache/arrow", "scan_date": "2026-08-11", "commit": "aaaaaaa1"},
        )
        b = compose_scan_id(
            f"/a/scans/glasswing/nuttx/{stamp}",
            {"repo": "apache/nuttx", "scan_date": "2026-08-11", "commit": "bbbbbbb2"},
        )
        assert a != b
        assert os.path.basename(f"/a/scans/glasswing/arrow/{stamp}") == os.path.basename(
            f"/a/scans/glasswing/nuttx/{stamp}"
        )

    def test_falls_back_to_dir_repo_when_meta_bare(self):
        assert compose_scan_id("/a/scans/glasswing/hop/20260811T042420Z", {}) == ("hop-2026-08-11")

    def test_date_recovered_from_dirname_when_meta_lacks_it(self):
        meta = {"repo": "apache/hop", "commit": "deadbeefcafe"}
        assert compose_scan_id("/a/scans/glasswing/hop/20260811T042420Z", meta) == (
            "hop-2026-08-11-deadbee"
        )


class TestScanDateFromDirname:
    def test_parses_stamp(self):
        assert scan_date_from_dirname("20260811T231034Z") == "2026-08-11"

    def test_non_stamp_yields_blank(self):
        assert scan_date_from_dirname("shiro-2026-07-17-cde5990") == ""


# --- repo-directory resolution (Repositories sheet fallback) ---------------

REPOS_GRID = [
    ["Repository URL", "Repository Name", "PMC Slug", "Criticality Score (%)"],
    ["https://github.com/apache/camel-k", "camel-k", "camel", "44.9%"],
    ["https://github.com/apache/commons-vfs", "commons-vfs", "commons", ""],
    ["", "pekko-http", "pekko", "51.3%"],
    ["https://github.com/apache/orphan", "orphan", "", ""],
]


def test_build_repo_directory_maps_url_and_name_forms():
    d = scan_results.build_repo_directory(REPOS_GRID)
    assert d["apache/camel-k"] == "camel"
    assert d["apache/commons-vfs"] == "commons"
    # falls back to Repository Name when the URL cell is blank
    assert d["apache/pekko-http"] == "pekko"
    # a row with no PMC slug contributes nothing
    assert "apache/orphan" not in d


def test_build_repo_directory_tolerates_missing_sheet():
    assert scan_results.build_repo_directory([]) == {}
    assert scan_results.build_repo_directory([["Repository Name"]]) == {}


def test_repo_directory_resolves_scan_whose_project_is_a_repo_name(tmp_path):
    """A scan keyed by repo name resolves to its PMC via the Repositories sheet.

    This is the 2026-08-26 anomaly class: the archive keys scans by repo
    (``camel-k``) while the tracker keys by PMC slug (``camel``), so 147 of
    241 scans were emitted with a bare repo name and an anomaly note.
    """
    scan_dir = tmp_path / "scans" / "glasswing" / "camel-k" / "20260811T042439Z"
    scan_dir.mkdir(parents=True)
    (scan_dir / "metadata.yml").write_text(
        "project: camel-k\nrepo: apache/camel-k\nscan_date: 2026-08-11\n"
    )

    pmc_by_slug = {"camel": ("Apache Camel", "2026-08-17")}
    directory = scan_results.build_repo_directory(REPOS_GRID)

    rows, anomalies = scan_results.collect_scan_rows(str(tmp_path), pmc_by_slug, {}, {}, directory)
    assert anomalies == []
    assert rows[0][0] == "Apache Camel"


def test_unknown_repo_still_emitted_with_anomaly(tmp_path):
    scan_dir = tmp_path / "scans" / "glasswing" / "mystery" / "20260811T000000Z"
    scan_dir.mkdir(parents=True)
    (scan_dir / "metadata.yml").write_text(
        "project: mystery\nrepo: apache/mystery\nscan_date: 2026-08-11\n"
    )
    rows, anomalies = scan_results.collect_scan_rows(
        str(tmp_path),
        {"camel": ("Apache Camel", "")},
        {},
        {},
        scan_results.build_repo_directory(REPOS_GRID),
    )
    assert len(rows) == 1  # never silently dropped
    assert len(anomalies) == 1
    assert "mystery" in anomalies[0]


def test_repo_directory_indexes_bare_repo_names():
    """The archive records ``repo`` unqualified ("camel-k"), not "apache/camel-k".

    Indexing only the owner-qualified form was the reason the first fix for the
    147-anomaly run changed nothing: the lookup key never matched.
    """
    d = scan_results.build_repo_directory(REPOS_GRID)
    assert d["apache/camel-k"] == "camel"
    assert d["camel-k"] == "camel"


def test_bare_repo_name_in_metadata_resolves(tmp_path):
    scan_dir = tmp_path / "scans" / "glasswing" / "camel-k" / "20260811T042439Z"
    scan_dir.mkdir(parents=True)
    # note: bare ``repo``, exactly as the live archive writes it
    (scan_dir / "metadata.yml").write_text(
        "project: camel-k\nrepo: camel-k\nscan_date: 2026-08-11\n"
    )
    rows, anomalies = scan_results.collect_scan_rows(
        str(tmp_path),
        {"camel": ("Apache Camel", "2026-08-17")},
        {},
        {},
        scan_results.build_repo_directory(REPOS_GRID),
    )
    assert anomalies == []
    assert rows[0][0] == "Apache Camel"
