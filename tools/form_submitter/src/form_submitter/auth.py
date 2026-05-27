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
"""OAuth credential loading.

Shares the ``token.json`` produced by ``sheets_writer.py setup`` —
form_submitter never mints its own token; it only reads the sheet via
the same scope (``spreadsheets``).
"""

from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from form_submitter import SCOPES, TOKEN_PATH


class AuthError(Exception):
    """OAuth token missing or unusable."""


def load_sheets_credentials() -> Credentials:
    """Load + refresh the Google OAuth credentials.

    Raises:
        AuthError: token file missing. The CLI converts this into a
            one-line error message pointing at ``sheets_writer.py setup``.
    """
    if not TOKEN_PATH.exists():
        raise AuthError(
            f"No OAuth token at {TOKEN_PATH}. "
            "Run sheets_writer.py setup first (the form_submitter "
            "shares its token)."
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds
