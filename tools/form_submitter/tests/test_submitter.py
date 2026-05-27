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

import json
from pathlib import Path

import pytest

from form_submitter.submitter import SubmitterError, load_submitter, write_submitter


def test_load_submitter_happy_path(tmp_path: Path) -> None:
    cfg_path = tmp_path / "submitter.json"
    cfg_path.write_text(
        json.dumps(
            {
                "name": "Jane Submitter",
                "email": "jane@apache.org",
                "github": "https://github.com/jane",
            }
        )
    )
    cfg = load_submitter(cfg_path)
    assert cfg["name"] == "Jane Submitter"
    assert cfg["email"] == "jane@apache.org"


def test_load_submitter_missing_file_message_points_at_setup(tmp_path: Path) -> None:
    with pytest.raises(SubmitterError) as excinfo:
        load_submitter(tmp_path / "missing.json")
    msg = str(excinfo.value)
    assert "No submitter config" in msg
    assert "setup-submitter" in msg


def test_load_submitter_rejects_blank_fields(tmp_path: Path) -> None:
    cfg_path = tmp_path / "submitter.json"
    cfg_path.write_text(json.dumps({"name": "", "email": "x@apache.org", "github": "https://x"}))
    with pytest.raises(SubmitterError) as excinfo:
        load_submitter(cfg_path)
    assert "'name'" in str(excinfo.value)


def test_load_submitter_rejects_non_apache_email(tmp_path: Path) -> None:
    cfg_path = tmp_path / "submitter.json"
    cfg_path.write_text(
        json.dumps({"name": "X", "email": "x@gmail.com", "github": "https://github.com/x"})
    )
    with pytest.raises(SubmitterError) as excinfo:
        load_submitter(cfg_path)
    assert "@apache.org" in str(excinfo.value)


def test_write_submitter_creates_mode_0600(tmp_path: Path) -> None:
    cfg_path = tmp_path / "submitter.json"
    write_submitter(
        name="Jane",
        email="jane@apache.org",
        github="https://github.com/jane",
        path=cfg_path,
    )
    assert cfg_path.exists()
    assert cfg_path.stat().st_mode & 0o777 == 0o600
    cfg = json.loads(cfg_path.read_text())
    assert cfg == {
        "name": "Jane",
        "email": "jane@apache.org",
        "github": "https://github.com/jane",
    }


def test_write_submitter_rejects_non_apache_email(tmp_path: Path) -> None:
    with pytest.raises(SubmitterError):
        write_submitter(
            name="Jane",
            email="jane@gmail.com",
            github="https://github.com/jane",
            path=tmp_path / "submitter.json",
        )


def test_write_submitter_is_idempotent(tmp_path: Path) -> None:
    cfg_path = tmp_path / "submitter.json"
    write_submitter("Jane", "jane@apache.org", "https://github.com/jane", cfg_path)
    write_submitter("Jane Updated", "jane@apache.org", "https://github.com/jane-2", cfg_path)
    cfg = json.loads(cfg_path.read_text())
    assert cfg["name"] == "Jane Updated"
    assert cfg["github"] == "https://github.com/jane-2"
