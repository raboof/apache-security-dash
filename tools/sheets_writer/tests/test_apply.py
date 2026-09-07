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

import pytest

from sheets_writer.apply import build_apply_plan
from sheets_writer.columns import GridError


def test_build_apply_plan_single_cell() -> None:
    grid = [
        ["PMC Slug", "Scan Requested", "Notes"],
        ["alpha", "Yes", ""],
        ["beta", "No", ""],
    ]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "beta"},
            "set": {"Scan Requested": "Yes"},
        }
    ]
    api_data, diff = build_apply_plan(updates, {"PMCs": grid})
    # beta is row index 2 in the grid (header=0, alpha=1, beta=2) →
    # A1 row = 3, Scan Requested column = B.
    assert api_data == [{"range": "PMCs!B3", "values": [["Yes"]]}]
    assert "beta" in diff[0]
    assert "'No' -> 'Yes'" in diff[0]


def test_build_apply_plan_multiple_cells_one_row() -> None:
    grid = [
        ["PMC Slug", "Scan Requested", "Notes"],
        ["alpha", "No", "old note"],
    ]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"Scan Requested": "Yes", "Notes": "new note"},
        }
    ]
    api_data, _ = build_apply_plan(updates, {"PMCs": grid})
    assert len(api_data) == 2
    ranges = {x["range"] for x in api_data}
    assert ranges == {"PMCs!B2", "PMCs!C2"}


def test_build_apply_plan_multi_sheet() -> None:
    grids = {
        "PMCs": [["PMC Slug", "Notes"], ["alpha", ""]],
        "Repositories": [["Repository URL", "Notes"], ["https://x", ""]],
    }
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"Notes": "foo"},
        },
        {
            "sheet": "Repositories",
            "match": {"column": "Repository URL", "value": "https://x"},
            "set": {"Notes": "bar"},
        },
    ]
    api_data, _ = build_apply_plan(updates, grids)
    assert len(api_data) == 2
    assert api_data[0]["range"].startswith("PMCs!")
    assert api_data[1]["range"].startswith("Repositories!")


def test_build_apply_plan_unknown_set_column_raises() -> None:
    grid = [["PMC Slug"], ["alpha"]]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"NotAColumn": "x"},
        }
    ]
    with pytest.raises(ValueError) as excinfo:
        build_apply_plan(updates, {"PMCs": grid})
    assert "NotAColumn" in str(excinfo.value)


def test_build_apply_plan_zero_match_propagates_griderror() -> None:
    grid = [["PMC Slug"], ["alpha"]]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "nobody"},
            "set": {"PMC Slug": "x"},
        }
    ]
    with pytest.raises(GridError):
        build_apply_plan(updates, {"PMCs": grid})


def test_build_apply_plan_multi_match_propagates_griderror() -> None:
    grid = [["PMC Slug"], ["alpha"], ["alpha"]]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"PMC Slug": "x"},
        }
    ]
    with pytest.raises(GridError):
        build_apply_plan(updates, {"PMCs": grid})


def test_build_apply_plan_unknown_sheet_raises_keyerror() -> None:
    updates = [
        {
            "sheet": "Bogus",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"x": "y"},
        }
    ]
    with pytest.raises(KeyError):
        build_apply_plan(updates, {"PMCs": [["PMC Slug"], ["alpha"]]})


def test_build_apply_plan_empty_updates_returns_empty() -> None:
    api_data, diff = build_apply_plan([], {})
    assert api_data == []
    assert diff == []


def test_build_apply_plan_skips_cell_already_at_requested_value() -> None:
    """A re-run against an already-applied update must report nothing to do.

    This is what makes ``apply --dry-run`` usable to verify a write landed.
    """
    grid = [
        ["PMC Slug", "Scan Requested"],
        ["alpha", "Yes"],
    ]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"Scan Requested": "Yes"},
        }
    ]
    api_data, diff = build_apply_plan(updates, {"PMCs": grid})
    assert api_data == []
    assert diff == []


def test_build_apply_plan_mixed_changed_and_unchanged() -> None:
    """Only the genuinely-changing cell is written; the no-op is dropped."""
    grid = [
        ["PMC Slug", "Scan Requested", "Notes"],
        ["alpha", "Yes", "old note"],
    ]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"Scan Requested": "Yes", "Notes": "new note"},
        }
    ]
    api_data, diff = build_apply_plan(updates, {"PMCs": grid})
    assert api_data == [{"range": "PMCs!C2", "values": [["new note"]]}]
    assert len(diff) == 1
    assert "'old note' -> 'new note'" in diff[0]


def test_build_apply_plan_blank_cell_set_to_blank_is_a_no_op() -> None:
    """An absent trailing cell reads as '' and must not be rewritten with ''."""
    grid = [
        ["PMC Slug", "Scan Requested", "Notes"],
        ["alpha", "Yes"],  # Notes column absent from the row entirely
    ]
    updates = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"Notes": ""},
        }
    ]
    api_data, diff = build_apply_plan(updates, {"PMCs": grid})
    assert api_data == []
    assert diff == []


def test_build_apply_plan_non_string_value_compared_as_string() -> None:
    """JSON numbers compare against the grid's string form, not by identity."""
    grid = [
        ["PMC Slug", "Count"],
        ["alpha", "7"],
    ]
    same = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"Count": 7},
        }
    ]
    api_data, _ = build_apply_plan(same, {"PMCs": grid})
    assert api_data == []

    different = [
        {
            "sheet": "PMCs",
            "match": {"column": "PMC Slug", "value": "alpha"},
            "set": {"Count": 8},
        }
    ]
    api_data, _ = build_apply_plan(different, {"PMCs": grid})
    assert api_data == [{"range": "PMCs!B2", "values": [[8]]}]
