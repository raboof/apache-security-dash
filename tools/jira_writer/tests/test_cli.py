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

from pathlib import Path

import pytest

from jira_writer.cli import build_parser, main
from tests.conftest import http_error, success


def test_argparse_routing_whoami() -> None:
    args = build_parser().parse_args(["whoami"])
    assert args.cmd == "whoami"


def test_argparse_routing_create_issue() -> None:
    args = build_parser().parse_args(
        [
            "create-issue",
            "--project",
            "HBASE",
            "--summary",
            "x",
            "--description",
            "y",
        ]
    )
    assert args.cmd == "create-issue"
    assert args.project == "HBASE"
    assert args.summary == "x"
    assert args.description == "y"
    assert args.description_file is None
    assert args.issuetype == "Task"
    assert args.dry_run is False


def test_argparse_description_and_file_are_mutually_exclusive() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "create-issue",
                "--project",
                "HBASE",
                "--summary",
                "x",
                "--description",
                "y",
                "--description-file",
                "/tmp/z",
            ]
        )


def test_argparse_description_or_file_required() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create-issue", "--project", "HBASE", "--summary", "x"])


def test_whoami_prints_identity(tmp_pat, mock_urlopen, capsys) -> None:
    mock_urlopen.return_value = success(
        {
            "displayName": "Jarek Potiuk",
            "name": "potiuk",
            "key": "higrys",
            "emailAddress": "jarek@potiuk.com",
        }
    )
    rc = main(["whoami"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Jarek Potiuk" in captured.out
    assert "name=potiuk" in captured.out
    assert "key=higrys" in captured.out
    assert "jarek@potiuk.com" in captured.out


def test_create_issue_dry_run_skips_api(tmp_pat, mock_urlopen, capsys) -> None:
    rc = main(
        [
            "create-issue",
            "--project",
            "HBASE",
            "--summary",
            "hello",
            "--description",
            "world",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "Dry run" in captured.out
    assert mock_urlopen.call_count == 0


def test_create_issue_applies_and_prints_browse_url(tmp_pat, mock_urlopen, capsys) -> None:
    mock_urlopen.return_value = success({"key": "HBASE-30181"})
    rc = main(
        [
            "create-issue",
            "--project",
            "HBASE",
            "--summary",
            "Add SECURITY.md",
            "--description",
            "long description...",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "Created:" in captured.out
    assert "https://issues.apache.org/jira/browse/HBASE-30181" in captured.out


def test_create_issue_reads_description_file(tmp_pat, mock_urlopen, capsys, tmp_path: Path) -> None:
    desc = tmp_path / "desc.md"
    desc.write_text("# Description\n\nFrom file.\n")
    mock_urlopen.return_value = success({"key": "HBASE-1"})
    rc = main(
        [
            "create-issue",
            "--project",
            "HBASE",
            "--summary",
            "x",
            "--description-file",
            str(desc),
        ]
    )
    assert rc == 0
    # Inspect the body that was POSTed.
    import json

    payload = json.loads(mock_urlopen.call_args.args[0].data)
    assert "From file." in payload["fields"]["description"]


def test_add_comment_dry_run(tmp_pat, mock_urlopen, capsys) -> None:
    rc = main(
        [
            "add-comment",
            "--issue",
            "HBASE-30181",
            "--body",
            "hello",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "Dry run" in captured.out
    assert mock_urlopen.call_count == 0


def test_add_comment_applies(tmp_pat, mock_urlopen, capsys) -> None:
    mock_urlopen.return_value = success({"id": "100"})
    rc = main(["add-comment", "--issue", "HBASE-30181", "--body", "hello"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Comment added" in captured.out


def test_missing_pat_exits_nonzero_with_setup_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    # No tmp_pat fixture — point TOKEN_PATH at a missing file.
    monkeypatch.setattr("jira_writer.auth.TOKEN_PATH", tmp_path / "missing")
    rc = main(["whoami"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "No PAT at" in captured.err
    assert "Personal Access Tokens" in captured.err


def test_api_error_exits_nonzero(tmp_pat, mock_urlopen, capsys) -> None:
    mock_urlopen.side_effect = http_error(401, "Unauthorized", "Bad token")
    rc = main(["whoami"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "HTTP 401" in captured.err
