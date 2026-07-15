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
"""OAuth credential handling — deliberately identical in shape to the
Apache Magpie ``oauth-draft`` backend, so this helper reads the **same**
credentials file (``~/.config/apache-magpie/gmail-oauth.json``) the
plain-text Gmail MCP already uses. No new credential to provision.

The credentials JSON has four fields::

    {
      "client_id":     "...apps.googleusercontent.com",
      "client_secret": "...",
      "refresh_token": "...",
      "from_address":  "you@apache.org"
    }
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Same default as the Magpie oauth-draft backend, so the one credential
# file serves both. Override with --credentials or $GMAIL_OAUTH_CREDENTIALS.
DEFAULT_CREDENTIALS_PATH = pathlib.Path.home() / ".config" / "apache-magpie" / "gmail-oauth.json"


@dataclasses.dataclass
class Credentials:
    """OAuth credentials loaded from disk. ``from_address`` is the ``From:``
    header baked into the draft, so it is always required here."""

    client_id: str
    client_secret: str
    refresh_token: str
    from_address: str

    @classmethod
    def load(cls, path: pathlib.Path) -> Credentials:
        data = json.loads(path.read_text())
        required = ["client_id", "client_secret", "refresh_token", "from_address"]
        missing = [k for k in required if not data.get(k)]
        if missing:
            raise SystemExit(
                f"{path}: missing required fields: {', '.join(missing)}. "
                f"See tools/forward_draft/README.md for the expected shape."
            )
        return cls(
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            refresh_token=data["refresh_token"],
            from_address=data["from_address"],
        )


def locate_credentials(explicit: str | None) -> pathlib.Path:
    """Resolve the credentials path: ``--credentials`` -> env -> default."""
    candidates: list[str | None] = [
        explicit,
        os.environ.get("GMAIL_OAUTH_CREDENTIALS"),
        str(DEFAULT_CREDENTIALS_PATH),
    ]
    for c in candidates:
        if not c:
            continue
        p = pathlib.Path(c).expanduser()
        if p.is_file():
            return p
    raise SystemExit(
        "No Gmail OAuth credentials found. Tried: "
        + ", ".join(str(pathlib.Path(c).expanduser()) for c in candidates if c)
        + ". See tools/forward_draft/README.md."
    )


def refresh_access_token(creds: Credentials) -> str:
    """Trade the long-lived refresh token for a ~1h access token."""
    body = urllib.parse.urlencode(
        {
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "refresh_token": creds.refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 — fixed Google endpoint
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f"OAuth token refresh failed ({e.code}): {e.read().decode(errors='replace')}"
        ) from e
    token = payload.get("access_token")
    if not token:
        raise SystemExit(f"OAuth token refresh returned no access_token: {payload}")
    return str(token)
