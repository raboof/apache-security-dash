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

from sheets_writer.cli import build_parser
from sheets_writer.dump import grid_to_objects


def test_grid_to_objects_pads_short_rows() -> None:
    grid = [
        ["PMC Slug", "Scan Requested", "Notes"],
        ["alpha", "Yes", "first"],
        ["beta", "No"],  # trailing blank omitted by the Sheets API
    ]
    assert grid_to_objects(grid) == [
        {"PMC Slug": "alpha", "Scan Requested": "Yes", "Notes": "first"},
        {"PMC Slug": "beta", "Scan Requested": "No", "Notes": ""},
    ]


def test_grid_to_objects_empty() -> None:
    assert grid_to_objects([]) == []
    assert grid_to_objects([["only", "header"]]) == []


def test_dump_argparse() -> None:
    args = build_parser().parse_args(
        ["dump", "--spreadsheet-id", "X", "--sheet", "PMCs", "--objects", "--compact"]
    )
    assert args.cmd == "dump"
    assert args.sheet == "PMCs"
    assert args.objects is True
    assert args.compact is True
