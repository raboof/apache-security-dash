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

from sheets_writer.scan_queue import find_scan_queue_row, scan_field_col
from sheets_writer.status import FIXED_COLS, SCAN_QUEUE_FIXED, SCAN_QUEUE_HEADER

_BRANCH_COL = SCAN_QUEUE_FIXED.index("Branch/tag")


def test_scan_field_col_layout() -> None:
    # Scan 1 block begins at FIXED_COLS; fields in order:
    # When scanned, Model send thread (ponymail), When report sent, Commit hash.
    assert scan_field_col(1, "When scanned") == FIXED_COLS
    assert scan_field_col(1, "Model send thread (ponymail)") == FIXED_COLS + 1
    assert scan_field_col(1, "When report sent") == FIXED_COLS + 2
    assert scan_field_col(1, "Commit hash") == FIXED_COLS + 3
    # Scan 2 block is one SCAN_BLOCK (4) further along.
    assert scan_field_col(2, "When scanned") == FIXED_COLS + 4
    assert scan_field_col(5, "Commit hash") == FIXED_COLS + 4 * 4 + 3


def test_scan_field_col_invalid() -> None:
    with pytest.raises(ValueError, match="scan number"):
        scan_field_col(0, "When scanned")
    with pytest.raises(ValueError, match="scan number"):
        scan_field_col(6, "When scanned")
    with pytest.raises(ValueError, match="unknown scan field"):
        scan_field_col(1, "Not A Field")


def _row(repo: str, branch: str) -> list[str]:
    cells = [""] * len(SCAN_QUEUE_HEADER)
    cells[0] = repo
    cells[_BRANCH_COL] = branch
    return cells


def test_find_scan_queue_row_by_repo_and_branch() -> None:
    grid = [
        ["Scan Queue title"],
        ["desc"],
        ["count"],
        [""],
        SCAN_QUEUE_HEADER,
        _row("https://github.com/apache/apisix-ingress-controller", ""),
        _row("https://github.com/apache/dubbo", "3.2"),
        _row("https://github.com/apache/dubbo", "main"),
    ]
    assert find_scan_queue_row(grid, "https://github.com/apache/apisix-ingress-controller") == 5
    assert find_scan_queue_row(grid, "https://github.com/apache/dubbo", "3.2") == 6
    assert find_scan_queue_row(grid, "https://github.com/apache/dubbo", "main") == 7
    # Unknown repo, and right repo + wrong branch, both miss.
    assert find_scan_queue_row(grid, "https://github.com/apache/nope") is None
    assert find_scan_queue_row(grid, "https://github.com/apache/dubbo", "") is None


def test_find_scan_queue_row_no_header() -> None:
    assert find_scan_queue_row([["wrong"], ["header"]], "repo") is None
    assert find_scan_queue_row([], "repo") is None
