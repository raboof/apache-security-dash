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
"""Shared pytest fixtures.

Two main fixtures:

  tmp_pat        — writes a fake PAT to a tmp path with mode 0o600 and
                   monkeypatches auth.TOKEN_PATH to point at it. Tests
                   that don't care about file-mode validation use this.

  mock_urlopen   — patches urllib.request.urlopen used inside
                   client.api_call. Yields a callable the test can
                   configure with the response body / status.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tmp_pat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a PAT file at tmp_path/token (mode 0o600) and patch
    auth.TOKEN_PATH to point at it.
    """
    token = tmp_path / "token"
    token.write_text("test-pat-value")
    token.chmod(0o600)
    monkeypatch.setattr("jira_writer.auth.TOKEN_PATH", token)
    return token


@pytest.fixture
def mock_urlopen():
    """Patch urllib.request.urlopen inside jira_writer.client.

    Yields a MagicMock that the test configures by setting
    ``mock_urlopen.return_value`` (for success) or
    ``mock_urlopen.side_effect`` (for HTTPError).

    Use the ``success`` / ``http_error`` helpers below to construct
    response payloads without remembering the urllib boilerplate.
    """
    with patch("jira_writer.client.urllib.request.urlopen") as m:
        yield m


def success(body: dict | None = None) -> MagicMock:
    """Build a context-manager mock that yields a urlopen-style
    response whose .read() returns the JSON-encoded ``body``.
    """
    payload = json.dumps(body or {}).encode("utf-8")
    response = MagicMock()
    response.read.return_value = payload
    # Mock the context-manager protocol so `with urlopen(...) as resp` works.
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=response)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def http_error(code: int, reason: str, body: str = "") -> urllib.error.HTTPError:
    """Build a urllib.error.HTTPError configured for tests."""
    return urllib.error.HTTPError(
        url="https://issues.apache.org/jira/rest/api/2/test",
        code=code,
        msg=reason,
        hdrs=None,
        fp=io.BytesIO(body.encode("utf-8")),
    )
