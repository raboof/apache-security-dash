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

import pytest

from forward_draft.credentials import Credentials, locate_credentials


def _write_creds(tmp_path, **overrides):
    data = {
        "client_id": "cid.apps.googleusercontent.com",
        "client_secret": "secret",
        "refresh_token": "rtok",
        "from_address": "jarek@apache.org",
    }
    data.update(overrides)
    p = tmp_path / "gmail-oauth.json"
    p.write_text(json.dumps(data))
    return p


def test_credentials_load_ok(tmp_path) -> None:
    creds = Credentials.load(_write_creds(tmp_path))
    assert creds.client_id == "cid.apps.googleusercontent.com"
    assert creds.from_address == "jarek@apache.org"


def test_credentials_load_missing_field(tmp_path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"client_id": "x", "client_secret": "y", "refresh_token": "z"}))
    with pytest.raises(SystemExit, match="from_address"):
        Credentials.load(p)


def test_locate_credentials_explicit_then_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GMAIL_OAUTH_CREDENTIALS", raising=False)
    p = _write_creds(tmp_path)
    assert locate_credentials(str(p)) == p
    # Nonexistent explicit + no env + (default almost certainly absent in CI) -> SystemExit.
    monkeypatch.setattr(
        "forward_draft.credentials.DEFAULT_CREDENTIALS_PATH", tmp_path / "nope.json"
    )
    with pytest.raises(SystemExit, match="No Gmail OAuth credentials found"):
        locate_credentials(str(tmp_path / "missing.json"))


def test_locate_credentials_env(tmp_path, monkeypatch) -> None:
    p = _write_creds(tmp_path)
    monkeypatch.setenv("GMAIL_OAUTH_CREDENTIALS", str(p))
    assert locate_credentials(None) == p
