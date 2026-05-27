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
"""Thin urllib wrapper for Apache JIRA REST API v2 calls.

Bearer-auth only (PAT). No third-party deps; the whole module is
stdlib. HTTP errors are surfaced as APIError with the response body
preserved (truncated to 1KB to keep the message readable when JIRA
returns a multi-line error envelope).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from jira_writer import JIRA_BASE
from jira_writer.auth import auth_header


class APIError(Exception):
    """HTTP-level failure from the JIRA REST API."""

    def __init__(self, status: int, reason: str, body: str) -> None:
        super().__init__(f"HTTP {status} {reason}: {body[:1000]}")
        self.status = status
        self.reason = reason
        self.body = body


def api_call(
    method: str,
    path: str,
    body: dict | None = None,
    token_path: Path | None = None,
) -> dict:
    """Issue an authenticated JIRA REST API v2 call.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: API path *after* ``/rest/api/2`` (e.g. ``"/issue"`` or
            ``"/issue/HBASE-30181/comment"``).
        body: JSON-serialisable payload for write methods. None for
            GETs (or for POSTs with no body, though JIRA rarely
            accepts those).
        token_path: optional override for the PAT file location.

    Returns:
        Parsed JSON response. Empty dict if the response body was
        empty (e.g. a 204).

    Raises:
        APIError: any non-2xx response.
        PATError: PAT missing / wrong mode / empty (propagated from
            ``auth.load_pat``).
    """
    url = f"{JIRA_BASE}/rest/api/2{path}"
    headers = auth_header(token_path) if token_path is not None else auth_header()
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310 (PAT-auth)
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise APIError(e.code, e.reason, body_text) from e


def get_myself(token_path: Path | None = None) -> dict:
    """GET /myself — verify auth + identify the authenticated user."""
    return api_call("GET", "/myself", token_path=token_path)


def create_issue(
    project: str,
    summary: str,
    description: str,
    issuetype: str = "Task",
    token_path: Path | None = None,
) -> dict:
    """POST /issue — file a new issue in ``project``.

    Returns the JIRA-server response dict, which includes ``key``
    (e.g. ``"HBASE-30181"``) and ``self`` (the canonical URL).
    """
    payload = {
        "fields": {
            "project": {"key": project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issuetype},
        }
    }
    return api_call("POST", "/issue", body=payload, token_path=token_path)


def add_comment(
    issue_key: str,
    body: str,
    token_path: Path | None = None,
) -> dict:
    """POST /issue/<key>/comment — append a comment."""
    return api_call(
        "POST",
        f"/issue/{issue_key}/comment",
        body={"body": body},
        token_path=token_path,
    )
