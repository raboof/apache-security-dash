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

from imapclient import IMAPClient
from dotenv import load_dotenv
from os import getenv
from inbox_manager.vendor.oauth2 import RefreshToken

load_dotenv()

# This tool authenticates over IMAP with a read/write Gmail OAuth token: it
# moves, files and junks messages. Its credentials are named GMAIL_READWRITE_*
# to make that explicit, and to keep them distinct from populate_cache's
# read-only token (GMAIL_READONLY_OAUTH_*) so both can live in one .env.
USER_ID = getenv("GMAIL_READWRITE_OAUTH_USER_ID")
CLIENT_ID = getenv("GMAIL_READWRITE_OAUTH_CLIENT_ID")
CLIENT_SECRET = getenv("GMAIL_READWRITE_OAUTH_CLIENT_SECRET")
REFRESH_TOKEN = getenv("GMAIL_READWRITE_OAUTH_REFRESH_TOKEN")

# The env vars connect() needs, kept here so the CLI can check them up front.
REQUIRED_ENV = (
    "GMAIL_READWRITE_OAUTH_USER_ID",
    "GMAIL_READWRITE_OAUTH_CLIENT_ID",
    "GMAIL_READWRITE_OAUTH_CLIENT_SECRET",
    "GMAIL_READWRITE_OAUTH_REFRESH_TOKEN",
)


def _create_accesstoken():
    # Use our refresh token to get a token for this session
    response = RefreshToken(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
    if "error" in response:
        raise ValueError("Authentication failed: %s" % response["error"])
    return response["access_token"]


def connect():
    missing = [name for name in REQUIRED_ENV if not getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing read/write Gmail IMAP OAuth2 credentials in environment "
            "(.env supported): " + ", ".join(missing)
        )
    server = IMAPClient("imap.gmail.com")
    server.oauth2_login(USER_ID, _create_accesstoken())
    server.select_folder("INBOX")
    return server
