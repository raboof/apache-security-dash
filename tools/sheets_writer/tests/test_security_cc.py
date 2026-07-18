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
"""Functional tests for the backfill-security-cc command paths."""

from __future__ import annotations

import argparse

import pytest

from sheets_writer import security_cc

# tomcat runs its own security team; apisix (null contact) does not; "ghost" is
# absent from coordinates entirely (still classifies as no-own-team).
COORDINATES = {
    "tomcat": {"name": "Apache Tomcat", "contact": "security@tomcat.apache.org"},
    "apisix": {"name": "Apache APISIX", "contact": None},
}

HEADER = ["PMC Name", "PMC Slug", "Report recipients", "Notes"]


def _grid(*rows: list[str]) -> list[list[str]]:
    return [HEADER, *rows]


def _row(
    name: str, slug: str, recipients: str = "", notes: str = "", team_cc: str = ""
) -> list[str]:
    base = [name, slug, recipients, notes]
    if team_cc:
        # Append a trailing 'PMC team Cc' cell (tests that add the column set HEADER too).
        base.append(team_cc)
    return base


def _ns(**kw) -> argparse.Namespace:
    base = dict(spreadsheet_id="X", dry_run=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _patch(monkeypatch, service) -> None:
    monkeypatch.setattr(security_cc, "get_service", lambda: service)
    monkeypatch.setattr(security_cc, "fetch_security_coordinates", lambda: COORDINATES)


# --- pure helpers -----------------------------------------------------------


def test_team_cc_values_resolves_own_team_and_private_fallback() -> None:
    rows = [
        _row("Apache Tomcat", "tomcat"),
        _row("Apache APISIX", "apisix"),
        _row("Apache Ghost", "ghost"),  # absent from coordinates
    ]
    assert security_cc.team_cc_values(HEADER, rows, COORDINATES) == [
        "security@tomcat.apache.org",
        "private@apisix.apache.org",
        "private@ghost.apache.org",
    ]


def test_team_cc_values_blank_slug_is_empty() -> None:
    rows = [_row("Apache Blank", ""), ["Apache Short"]]  # short row: no slug cell
    assert security_cc.team_cc_values(HEADER, rows, COORDINATES) == ["", ""]


def test_team_cc_values_requires_slug_column() -> None:
    with pytest.raises(ValueError, match="PMC Slug"):
        security_cc.team_cc_values(["PMC Name", "Notes"], [["x", "y"]], COORDINATES)


def test_build_backfill_diff_new_column_reports_every_nonempty() -> None:
    rows = [_row("Apache Tomcat", "tomcat"), _row("Apache APISIX", "apisix")]
    values = ["security@tomcat.apache.org", "private@apisix.apache.org"]
    diff, changed = security_cc.build_backfill_diff(HEADER, rows, values)
    assert changed == 2
    assert "row 2 (tomcat): '' -> 'security@tomcat.apache.org'" in diff[0]


def test_build_backfill_diff_existing_column_only_changed_rows() -> None:
    header = [*HEADER, "PMC team Cc"]
    rows = [
        _row("Apache Tomcat", "tomcat", team_cc="security@tomcat.apache.org"),  # unchanged
        _row("Apache APISIX", "apisix", team_cc="security@apache.org"),  # stale -> changes
    ]
    values = ["security@tomcat.apache.org", "private@apisix.apache.org"]
    diff, changed = security_cc.build_backfill_diff(header, rows, values)
    assert changed == 1
    assert "apisix" in diff[0]
    assert "'security@apache.org' -> 'private@apisix.apache.org'" in diff[0]


# --- command paths ----------------------------------------------------------


def test_backfill_inserts_after_report_recipients(monkeypatch, make_service) -> None:
    grid = _grid(_row("Apache Tomcat", "tomcat"), _row("Apache APISIX", "apisix"))
    svc = make_service("PMCs", grid)
    _patch(monkeypatch, svc)

    security_cc.cmd_backfill_security_cc(_ns())

    # New column inserted right after "Report recipients" (index 2 -> new col at 3 = D).
    ins = next(c for c in svc.calls if c[0] == "spreadsheets.batchUpdate")
    dim = ins[1]["body"]["requests"][0]["insertDimension"]
    assert dim["range"]["startIndex"] == 3 and dim["range"]["endIndex"] == 4

    upd = next(c for c in svc.calls if c[0] == "values.update")
    assert upd[1]["range"] == "PMCs!D1:D3"
    assert upd[1]["body"]["values"] == [
        ["PMC team Cc"],
        ["security@tomcat.apache.org"],
        ["private@apisix.apache.org"],
    ]


def test_backfill_appends_when_no_anchor(monkeypatch, make_service) -> None:
    header = ["PMC Name", "PMC Slug", "Notes"]  # no "Report recipients"
    grid = [header, ["Apache Tomcat", "tomcat", "n"]]
    svc = make_service("PMCs", grid)
    _patch(monkeypatch, svc)

    security_cc.cmd_backfill_security_cc(_ns())

    # No structural insert — appended past the last column (index 3 = D).
    assert not any(c[0] == "spreadsheets.batchUpdate" for c in svc.calls)
    upd = next(c for c in svc.calls if c[0] == "values.update")
    assert upd[1]["range"] == "PMCs!D1:D2"
    assert upd[1]["body"]["values"] == [["PMC team Cc"], ["security@tomcat.apache.org"]]


def test_backfill_existing_column_updates_without_insert(monkeypatch, make_service) -> None:
    header = [*HEADER, "PMC team Cc"]
    grid = [
        header,
        _row("Apache Tomcat", "tomcat", team_cc="security@tomcat.apache.org"),  # unchanged
        _row("Apache APISIX", "apisix", team_cc="security@apache.org"),  # stale
    ]
    svc = make_service("PMCs", grid)
    _patch(monkeypatch, svc)

    security_cc.cmd_backfill_security_cc(_ns())

    assert not any(c[0] == "spreadsheets.batchUpdate" for c in svc.calls)
    upd = next(c for c in svc.calls if c[0] == "values.update")
    # Existing column is at index 4 = E; whole column rewritten idempotently.
    assert upd[1]["range"] == "PMCs!E1:E3"
    assert upd[1]["body"]["values"] == [
        ["PMC team Cc"],
        ["security@tomcat.apache.org"],
        ["private@apisix.apache.org"],
    ]


def test_backfill_existing_column_no_changes_is_noop(monkeypatch, make_service) -> None:
    header = [*HEADER, "PMC team Cc"]
    grid = [
        header,
        _row("Apache Tomcat", "tomcat", team_cc="security@tomcat.apache.org"),
        _row("Apache APISIX", "apisix", team_cc="private@apisix.apache.org"),
    ]
    svc = make_service("PMCs", grid)
    _patch(monkeypatch, svc)

    security_cc.cmd_backfill_security_cc(_ns())

    # Nothing changed -> no writes at all.
    assert not any(c[0] == "values.update" for c in svc.calls)
    assert not any(c[0] == "spreadsheets.batchUpdate" for c in svc.calls)


def test_backfill_dry_run_writes_nothing(monkeypatch, make_service) -> None:
    grid = _grid(_row("Apache Tomcat", "tomcat"))
    svc = make_service("PMCs", grid)
    _patch(monkeypatch, svc)

    security_cc.cmd_backfill_security_cc(_ns(dry_run=True))

    assert not any(c[0] == "values.update" for c in svc.calls)
    assert not any(c[0] == "spreadsheets.batchUpdate" for c in svc.calls)
