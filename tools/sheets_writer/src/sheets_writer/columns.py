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
"""Pure helpers over the column space: A1 letter math + row matching."""

from __future__ import annotations


class GridError(Exception):
    """Raised by find_unique_row on miss / multi-match / bad column."""


def col_letter(idx_zero_based: int) -> str:
    """Convert a zero-based column index to A1 letter form (0 -> A, 26 -> AA)."""
    n = idx_zero_based + 1
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def find_unique_row(
    grid: list[list[str]], match_column: str, match_value: str
) -> tuple[int, list[str]]:
    """Find exactly one row in ``grid`` where ``grid[i][match_col_idx] == match_value``.

    Returns ``(row_idx_in_grid, row)``. Raises GridError on:
      - empty grid (no header)
      - match_column not in header
      - zero matches
      - multiple matches (refuses to update ambiguously)
    """
    if not grid:
        raise GridError("Sheet is empty.")
    header = grid[0]
    if match_column not in header:
        raise GridError(f"Match column '{match_column}' not found in header. Available: {header}")
    col_idx = header.index(match_column)
    hits = []
    for row_idx, row in enumerate(grid[1:], start=1):
        if col_idx < len(row) and row[col_idx] == match_value:
            hits.append((row_idx, row))
    if not hits:
        raise GridError(f"No row matches {match_column}={match_value!r}.")
    if len(hits) > 1:
        raise GridError(
            f"Multiple rows match {match_column}={match_value!r}: "
            f"row numbers {[h[0] for h in hits]}. Refusing to update ambiguously."
        )
    return hits[0]
