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
"""Functional tests for the insert-column command paths."""

from __future__ import annotations

import argparse
import json

import pytest

from sheets_writer import schema

SHEET = "OSS Subscriptions"
GRID = [
    ["Apache Address", "PMCs", "Status"],
    ["acosentino@apache.org", "camel", "Expedite requested"],
    ["zwoop@apache.org", "trafficserver", "Expedite requested"],
    ["unknown@apache.org", "x", "Expedite requested"],
]


def _ns(**kw) -> argparse.Namespace:
    base = dict(
        spreadsheet_id="X",
        sheet=SHEET,
        header="Name",
        after=None,
        before=None,
        at_start=False,
        fill=None,
        dry_run=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def _patch(monkeypatch, service) -> None:
    monkeypatch.setattr(schema, "get_service", lambda: service)


def test_insert_at_start_with_keyed_fill(monkeypatch, tmp_path, make_service) -> None:
    svc = make_service(SHEET, GRID)
    _patch(monkeypatch, svc)
    fill = tmp_path / "fill.json"
    fill.write_text(
        json.dumps(
            {
                "key": "Apache Address",
                "map": {
                    "acosentino@apache.org": "Andrea Cosentino",
                    "zwoop@apache.org": "Leif Hedstrom",
                },
            }
        )
    )
    schema.cmd_insert_column(_ns(at_start=True, fill=fill))

    # Column inserted at index 0 without inheriting format from a (nonexistent) prior column.
    ins = next(c for c in svc.calls if c[0] == "spreadsheets.batchUpdate")
    dim = ins[1]["body"]["requests"][0]["insertDimension"]
    assert dim["range"]["startIndex"] == 0 and dim["range"]["endIndex"] == 1
    assert dim["inheritFromBefore"] is False

    # Header + one value per data row, keyed by Apache Address; unknown -> blank.
    upd = next(c for c in svc.calls if c[0] == "values.update")
    assert upd[1]["range"] == f"{SHEET}!A1:A4"
    assert upd[1]["body"]["values"] == [
        ["Name"],
        ["Andrea Cosentino"],
        ["Leif Hedstrom"],
        [""],
    ]


def test_insert_before_inherits_format(monkeypatch, make_service) -> None:
    svc = make_service(SHEET, GRID)
    _patch(monkeypatch, svc)
    schema.cmd_insert_column(_ns(header="New", before="PMCs"))

    ins = next(c for c in svc.calls if c[0] == "spreadsheets.batchUpdate")
    dim = ins[1]["body"]["requests"][0]["insertDimension"]
    # "PMCs" is index 1, so the new column lands at index 1 and inherits from before.
    assert dim["range"]["startIndex"] == 1
    assert dim["inheritFromBefore"] is True


def test_insert_list_fill_length_mismatch_exits(monkeypatch, tmp_path, make_service) -> None:
    svc = make_service(SHEET, GRID)
    _patch(monkeypatch, svc)
    fill = tmp_path / "fill.json"
    fill.write_text(json.dumps(["only", "two"]))  # sheet has 3 data rows
    with pytest.raises(SystemExit):
        schema.cmd_insert_column(_ns(at_start=True, fill=fill))


def test_insert_existing_header_is_idempotent(monkeypatch, make_service) -> None:
    svc = make_service(SHEET, GRID)
    _patch(monkeypatch, svc)
    schema.cmd_insert_column(_ns(header="Status", at_start=True))
    # No structural change attempted when the header already exists.
    assert not any(c[0] == "spreadsheets.batchUpdate" for c in svc.calls)
