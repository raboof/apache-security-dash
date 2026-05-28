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
"""OAuth credential loading + setup flow.

Two artifacts live at ~/.config/asf-security/glasswing/:
  - oauth_client_secret.json: Google Cloud Console OAuth client. Manually
    placed before `setup` runs; the script doesn't create it.
  - token.json: refresh token written by `setup`. Auto-refreshed on use.
"""

from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from sheets_writer import CLIENT_SECRET_PATH, CONFIG_DIR, SCOPES, TOKEN_PATH


class AuthError(Exception):
    """OAuth client secret missing / token unusable."""


def load_credentials() -> Credentials:
    """Load + refresh the OAuth credentials. Raises AuthError on failure."""
    if not CLIENT_SECRET_PATH.exists():
        raise AuthError(
            f"OAuth client secret not found at {CLIENT_SECRET_PATH}.\n"
            "Run 'sheets-writer setup' first, or see the SKILL.md "
            "for one-time OAuth setup instructions."
        )
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        return creds
    raise AuthError("No valid OAuth token. Run 'sheets-writer setup' to authorize this machine.")


def run_setup() -> None:
    """Run the one-time OAuth installed-app flow.

    Reads CLIENT_SECRET_PATH, opens a browser, writes TOKEN_PATH (mode 0o600).
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CLIENT_SECRET_PATH.exists():
        raise AuthError(
            f"Place your OAuth client secret JSON at {CLIENT_SECRET_PATH} "
            "before running setup. See SKILL.md for how to create one in "
            "the Google Cloud Console."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    TOKEN_PATH.write_text(creds.to_json())
    TOKEN_PATH.chmod(0o600)
    print(f"OAuth token saved to {TOKEN_PATH} (mode 0o600).")
