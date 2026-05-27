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

from jira_writer.client import APIError, add_comment, api_call, create_issue, get_myself
from tests.conftest import http_error, success


def test_api_call_get_returns_parsed_json(tmp_pat, mock_urlopen) -> None:
    mock_urlopen.return_value = success({"key": "value"})
    assert api_call("GET", "/myself") == {"key": "value"}

    # Inspect the Request object that was passed to urlopen.
    req = mock_urlopen.call_args.args[0]
    assert req.full_url == "https://issues.apache.org/jira/rest/api/2/myself"
    assert req.get_method() == "GET"
    assert req.headers["Authorization"] == "Bearer test-pat-value"


def test_api_call_post_serialises_body_and_sets_content_type(tmp_pat, mock_urlopen) -> None:
    mock_urlopen.return_value = success({"key": "HBASE-1"})
    api_call("POST", "/issue", body={"fields": {"summary": "x"}})

    req = mock_urlopen.call_args.args[0]
    assert req.get_method() == "POST"
    # Header lookup on a Request is case-insensitive only for some attrs;
    # the headers dict uses title-case.
    assert req.headers["Content-type"] == "application/json"
    assert json.loads(req.data) == {"fields": {"summary": "x"}}


def test_api_call_empty_body_returns_empty_dict(tmp_pat, mock_urlopen) -> None:
    """A 204 response (no body) should return {} rather than crash on json.loads('')."""
    mock_urlopen.return_value = success()
    # Override read() to return an empty bytes object.
    mock_urlopen.return_value.__enter__.return_value.read.return_value = b""
    assert api_call("DELETE", "/issue/HBASE-1/comment/42") == {}


def test_api_call_http_error_raises_api_error_with_body(tmp_pat, mock_urlopen) -> None:
    mock_urlopen.side_effect = http_error(401, "Unauthorized", "Bad token")
    with pytest.raises(APIError) as excinfo:
        api_call("GET", "/myself")
    err = excinfo.value
    assert err.status == 401
    assert err.reason == "Unauthorized"
    assert "Bad token" in err.body
    assert "HTTP 401" in str(err)


def test_api_call_long_error_body_truncates_in_message(tmp_pat, mock_urlopen) -> None:
    long_body = "X" * 5000
    mock_urlopen.side_effect = http_error(500, "Server Error", long_body)
    with pytest.raises(APIError) as excinfo:
        api_call("POST", "/issue", body={"fields": {}})
    # The .body attr preserves the full body; the str() truncates to 1KB.
    assert len(excinfo.value.body) == 5000
    assert len(str(excinfo.value)) < 1200  # 1000-char body slice + prefix


def test_get_myself_calls_correct_endpoint(tmp_pat, mock_urlopen) -> None:
    mock_urlopen.return_value = success({"displayName": "Jarek", "name": "potiuk"})
    assert get_myself()["name"] == "potiuk"
    req = mock_urlopen.call_args.args[0]
    assert req.full_url.endswith("/rest/api/2/myself")
    assert req.get_method() == "GET"


def test_create_issue_payload_shape(tmp_pat, mock_urlopen) -> None:
    mock_urlopen.return_value = success({"key": "HBASE-30181", "self": "..."})
    result = create_issue(
        project="HBASE",
        summary="Add SECURITY.md",
        description="long description here",
    )
    assert result["key"] == "HBASE-30181"

    req = mock_urlopen.call_args.args[0]
    payload = json.loads(req.data)
    assert payload == {
        "fields": {
            "project": {"key": "HBASE"},
            "summary": "Add SECURITY.md",
            "description": "long description here",
            "issuetype": {"name": "Task"},
        }
    }


def test_create_issue_respects_custom_issuetype(tmp_pat, mock_urlopen) -> None:
    mock_urlopen.return_value = success({"key": "HBASE-30182"})
    create_issue("HBASE", "Bug X", "details", issuetype="Bug")

    payload = json.loads(mock_urlopen.call_args.args[0].data)
    assert payload["fields"]["issuetype"] == {"name": "Bug"}


def test_add_comment_endpoint_and_payload(tmp_pat, mock_urlopen) -> None:
    mock_urlopen.return_value = success({"id": "100", "body": "hi"})
    add_comment("HBASE-30181", "hi")

    req = mock_urlopen.call_args.args[0]
    assert req.full_url.endswith("/rest/api/2/issue/HBASE-30181/comment")
    assert json.loads(req.data) == {"body": "hi"}
