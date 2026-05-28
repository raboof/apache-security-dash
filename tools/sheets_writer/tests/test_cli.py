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

from sheets_writer.cli import build_parser


def test_argparse_routing_setup() -> None:
    args = build_parser().parse_args(["setup"])
    assert args.cmd == "setup"


def test_argparse_routing_apply() -> None:
    args = build_parser().parse_args(
        ["apply", "--spreadsheet-id", "ABC", "--updates", "/tmp/u.json", "--dry-run"]
    )
    assert args.cmd == "apply"
    assert args.spreadsheet_id == "ABC"
    assert str(args.updates) == "/tmp/u.json"
    assert args.dry_run is True


def test_argparse_apply_requires_updates() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["apply", "--spreadsheet-id", "ABC"])


def test_argparse_routing_append_canned() -> None:
    args = build_parser().parse_args(
        ["append-canned", "--spreadsheet-id", "X", "--entries", "/tmp/e.json"]
    )
    assert args.cmd == "append-canned"
    assert args.dry_run is False


def test_argparse_routing_append_pmc() -> None:
    args = build_parser().parse_args(
        ["append-pmc", "--spreadsheet-id", "X", "--entries", "/tmp/p.json"]
    )
    assert args.cmd == "append-pmc"


def test_argparse_routing_build_status_tab() -> None:
    args = build_parser().parse_args(["build-status-tab", "--spreadsheet-id", "X", "--dry-run"])
    assert args.cmd == "build-status-tab"
    assert args.dry_run is True


def test_argparse_routing_rename_column() -> None:
    args = build_parser().parse_args(
        [
            "rename-column",
            "--spreadsheet-id",
            "X",
            "--sheet",
            "PMCs",
            "--old",
            "A",
            "--new",
            "B",
        ]
    )
    assert args.cmd == "rename-column"
    assert args.old == "A" and args.new == "B"


def test_argparse_routing_insert_column() -> None:
    args = build_parser().parse_args(
        [
            "insert-column",
            "--spreadsheet-id",
            "X",
            "--sheet",
            "PMCs",
            "--after",
            "Notes",
            "--header",
            "NewCol",
        ]
    )
    assert args.cmd == "insert-column"
    assert args.after == "Notes" and args.header == "NewCol"


def test_argparse_routing_add_columns() -> None:
    args = build_parser().parse_args(
        [
            "add-columns",
            "--spreadsheet-id",
            "X",
            "--sheet",
            "PMCs",
            "--headers",
            "Col1",
            "Col2",
            "Col3",
        ]
    )
    assert args.cmd == "add-columns"
    assert args.headers == ["Col1", "Col2", "Col3"]


def test_argparse_no_subcommand_exits() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
