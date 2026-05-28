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

from sheets_writer.columns import GridError, col_letter, find_unique_row


@pytest.mark.parametrize(
    ("idx", "letter"),
    [
        (0, "A"),
        (1, "B"),
        (25, "Z"),
        (26, "AA"),
        (27, "AB"),
        (51, "AZ"),
        (52, "BA"),
        (701, "ZZ"),
        (702, "AAA"),
        (703, "AAB"),
    ],
)
def test_col_letter_boundaries(idx: int, letter: str) -> None:
    assert col_letter(idx) == letter


def test_find_unique_row_happy_path() -> None:
    grid = [
        ["PMC Slug", "Status"],
        ["alpha", "Yes"],
        ["beta", "No"],
        ["gamma", "Yes"],
    ]
    row_idx, row = find_unique_row(grid, "PMC Slug", "beta")
    assert row_idx == 2
    assert row == ["beta", "No"]


def test_find_unique_row_first_data_row() -> None:
    grid = [["PMC Slug"], ["alpha"], ["beta"]]
    row_idx, _ = find_unique_row(grid, "PMC Slug", "alpha")
    assert row_idx == 1  # 1-based-after-header


def test_find_unique_row_zero_match_raises() -> None:
    grid = [["PMC Slug"], ["alpha"]]
    with pytest.raises(GridError) as excinfo:
        find_unique_row(grid, "PMC Slug", "missing")
    assert "No row matches" in str(excinfo.value)


def test_find_unique_row_multi_match_raises() -> None:
    grid = [["PMC Slug"], ["alpha"], ["alpha"]]
    with pytest.raises(GridError) as excinfo:
        find_unique_row(grid, "PMC Slug", "alpha")
    assert "Multiple rows match" in str(excinfo.value)
    # Surface the row numbers so the caller can resolve manually.
    assert "[1, 2]" in str(excinfo.value)


def test_find_unique_row_missing_column_raises() -> None:
    grid = [["PMC Slug"], ["alpha"]]
    with pytest.raises(GridError) as excinfo:
        find_unique_row(grid, "Nonexistent", "alpha")
    assert "Match column 'Nonexistent' not found" in str(excinfo.value)


def test_find_unique_row_empty_grid_raises() -> None:
    with pytest.raises(GridError) as excinfo:
        find_unique_row([], "PMC Slug", "x")
    assert "Sheet is empty" in str(excinfo.value)


def test_find_unique_row_with_trailing_blank_cells() -> None:
    """A row shorter than the header (missing trailing cells) shouldn't crash."""
    grid = [["PMC Slug", "Status", "Notes"], ["alpha"]]
    # Match-column index out-of-range for the row → no match.
    with pytest.raises(GridError):
        find_unique_row(grid, "Status", "Yes")
