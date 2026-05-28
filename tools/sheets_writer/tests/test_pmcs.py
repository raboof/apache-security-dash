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

from sheets_writer.pmcs import build_pmc_rows

HEADER = [
    "PMC Name",
    "PMC Slug",
    "Scan Requested",
    "Contact Person",
    "Notes",
]


def test_build_pmc_rows_happy_path() -> None:
    rows = build_pmc_rows(
        [
            {"PMC Name": "Apache X", "PMC Slug": "x", "Scan Requested": "Yes"},
        ],
        header=HEADER,
        existing_slugs={},
    )
    assert rows == [["Apache X", "x", "Yes", "", ""]]


def test_build_pmc_rows_fills_blank_for_missing_optional() -> None:
    rows = build_pmc_rows(
        [{"PMC Name": "Y", "PMC Slug": "y"}],
        header=HEADER,
        existing_slugs={},
    )
    assert rows == [["Y", "y", "", "", ""]]


def test_build_pmc_rows_missing_required() -> None:
    with pytest.raises(ValueError) as excinfo:
        build_pmc_rows(
            [{"PMC Name": "Z"}],  # no PMC Slug
            header=HEADER,
            existing_slugs={},
        )
    assert "PMC Slug" in str(excinfo.value)


def test_build_pmc_rows_blank_required_value() -> None:
    """Required-field check rejects empty strings, not just absent keys."""
    with pytest.raises(ValueError) as excinfo:
        build_pmc_rows(
            [{"PMC Name": "Z", "PMC Slug": "   "}],
            header=HEADER,
            existing_slugs={},
        )
    assert "PMC Slug" in str(excinfo.value)


def test_build_pmc_rows_unknown_column_aborts() -> None:
    with pytest.raises(ValueError) as excinfo:
        build_pmc_rows(
            [{"PMC Name": "Z", "PMC Slug": "z", "TotallyNew": "?"}],
            header=HEADER,
            existing_slugs={},
        )
    assert "unknown columns" in str(excinfo.value).lower()
    assert "TotallyNew" in str(excinfo.value)


def test_build_pmc_rows_duplicate_slug_aborts() -> None:
    with pytest.raises(ValueError) as excinfo:
        build_pmc_rows(
            [{"PMC Name": "Z", "PMC Slug": "z"}],
            header=HEADER,
            existing_slugs={"z": 17},
        )
    assert "already exists" in str(excinfo.value)
    assert "row 17" in str(excinfo.value)


def test_build_pmc_rows_dup_check_disabled() -> None:
    """existing_slugs=None skips the dup check (dry-run flow)."""
    rows = build_pmc_rows(
        [{"PMC Name": "Z", "PMC Slug": "z"}],
        header=HEADER,
        existing_slugs=None,
    )
    assert len(rows) == 1


def test_build_pmc_rows_non_dict_entry() -> None:
    with pytest.raises(ValueError) as excinfo:
        build_pmc_rows(
            ["not a dict"],
            header=HEADER,
            existing_slugs={},
        )
    assert "must be a JSON object" in str(excinfo.value)
