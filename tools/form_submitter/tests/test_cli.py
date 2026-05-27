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

from form_submitter.cli import build_parser


def test_argparse_routing_setup() -> None:
    args = build_parser().parse_args(["setup"])
    assert args.cmd == "setup"


def test_argparse_routing_setup_submitter() -> None:
    args = build_parser().parse_args(
        [
            "setup-submitter",
            "--name",
            "Jane",
            "--email",
            "jane@apache.org",
            "--github",
            "https://github.com/jane",
        ]
    )
    assert args.cmd == "setup-submitter"
    assert args.name == "Jane"
    assert args.email == "jane@apache.org"
    assert args.github == "https://github.com/jane"


def test_argparse_setup_submitter_requires_all_three() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["setup-submitter", "--name", "Jane"])
    with pytest.raises(SystemExit):
        parser.parse_args(["setup-submitter", "--name", "Jane", "--email", "x@apache.org"])


def test_argparse_routing_submit_pmc_dry_run() -> None:
    args = build_parser().parse_args(["submit-pmc", "--slug", "hbase", "--dry-run"])
    assert args.cmd == "submit-pmc"
    assert args.slug == "hbase"
    assert args.dry_run is True
    assert args.starting_from is None


def test_argparse_submit_pmc_starting_from() -> None:
    args = build_parser().parse_args(
        ["submit-pmc", "--slug", "tomcat", "--starting-from", "tomcat-native"]
    )
    assert args.starting_from == "tomcat-native"


def test_argparse_submit_pmc_requires_slug() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["submit-pmc"])
