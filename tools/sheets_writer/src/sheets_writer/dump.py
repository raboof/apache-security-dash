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
"""Read-only ``dump`` subcommand — print a sheet as JSON to stdout.

The Workspace Drive MCP silently truncates a spreadsheet export at
~80 KB of markdown (dropping rows past roughly the first ~140
alphabetically), so sweeps that rely on it miss in-flight PMCs that
sort late. This subcommand reads the full sheet straight off the
Sheets API v4 and emits it as JSON, with no truncation, for the
``glasswing-scan-run`` sweep (and any other read) to consume via
``jq`` without pulling the bytes into a model's context.
"""

from __future__ import annotations

import argparse
import json
import sys


def grid_to_objects(grid: list[list[str]]) -> list[dict[str, str]]:
    """Key each data row by the header row.

    Rows shorter than the header (the Sheets API omits trailing blanks)
    are padded with empty strings so every object has every key. Pure
    function — no API calls.
    """
    if not grid:
        return []
    header = grid[0]
    objects: list[dict[str, str]] = []
    for row in grid[1:]:
        padded = list(row) + [""] * (len(header) - len(row))
        objects.append({col: padded[i] for i, col in enumerate(header)})
    return objects


def cmd_dump(args: argparse.Namespace) -> int:
    # Imported lazily so the pure helper above stays import-light for tests.
    from sheets_writer.sheets_api import fetch_sheet_grid, get_service

    grid = fetch_sheet_grid(get_service(), args.spreadsheet_id, args.sheet)
    if args.objects:
        payload: object = grid_to_objects(grid)
    else:
        payload = {"header": grid[0] if grid else [], "rows": grid[1:] if grid else []}
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=None if args.compact else 2)
    sys.stdout.write("\n")
    return 0
