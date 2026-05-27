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

from jira_writer.auth import PATError, auth_header, load_pat


def test_load_pat_happy_path(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("my-secret-pat\n")
    token.chmod(0o600)

    assert load_pat(token) == "my-secret-pat"


def test_load_pat_missing_file_explains_setup(tmp_path: Path) -> None:
    token = tmp_path / "token"
    with pytest.raises(PATError) as excinfo:
        load_pat(token)
    msg = str(excinfo.value)
    # The error message must walk the operator through the one-time
    # setup, since this is the most common first-run failure mode.
    assert "No PAT at" in msg
    assert "Personal Access Tokens" in msg
    assert "chmod 600" in msg


def test_load_pat_rejects_loose_mode(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("my-secret-pat")
    token.chmod(0o644)
    with pytest.raises(PATError) as excinfo:
        load_pat(token)
    assert "0o644" in str(excinfo.value) or "0o600" in str(excinfo.value)
    assert "chmod 600" in str(excinfo.value)


def test_load_pat_rejects_empty(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("   \n\t  \n")
    token.chmod(0o600)
    with pytest.raises(PATError) as excinfo:
        load_pat(token)
    assert "empty" in str(excinfo.value)


def test_load_pat_strips_whitespace(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("  pat-value  \n\n")
    token.chmod(0o600)
    assert load_pat(token) == "pat-value"


def test_skip_mode_check_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JIRA_WRITER_SKIP_MODE_CHECK=1 bypasses the 0o600 check (Windows escape hatch)."""
    token = tmp_path / "token"
    token.write_text("pat-value")
    token.chmod(0o644)
    monkeypatch.setenv("JIRA_WRITER_SKIP_MODE_CHECK", "1")
    assert load_pat(token) == "pat-value"


def test_auth_header_format(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("my-pat")
    token.chmod(0o600)
    assert auth_header(token) == {"Authorization": "Bearer my-pat"}
