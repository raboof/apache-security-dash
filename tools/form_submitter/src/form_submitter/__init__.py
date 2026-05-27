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
"""Glasswing scan-submission helper.

Fills the vendor's project-enrollment Google Form once per repo for a
given PMC, ordered by OSSF Criticality Score (highest first). Headline
repo carries the maintainer roster + OSS-expedite addresses + the
Claude Max 20x checkbox; subsequent forms point back to the headline.

Auth model: a persistent Chromium profile lives at
``~/.config/asf-security/glasswing/playwright-profile/``. Run the
``setup`` subcommand once to sign in to Google interactively; subsequent
``submit-pmc`` invocations reuse the authenticated session in headless
mode.

Submitter identity (Name / @apache.org email / GitHub profile URL)
lives at ``~/.config/asf-security/glasswing/submitter.json`` — set
via ``setup-submitter``.

PMC data is read from the Mythos tracker spreadsheet that
``sheets_writer.py`` writes to, using the same OAuth refresh token at
``~/.config/asf-security/glasswing/token.json``.

CLI:

    form-submitter setup
    form-submitter setup-submitter --name NAME --email APACHE_EMAIL --github URL
    form-submitter submit-pmc --slug SLUG [--dry-run] [--starting-from REPO_NAME]
"""

from pathlib import Path

__version__ = "0.1.0"

CONFIG_DIR = Path.home() / ".config" / "asf-security" / "glasswing"
TOKEN_PATH = CONFIG_DIR / "token.json"
SUBMITTER_PATH = CONFIG_DIR / "submitter.json"
PROFILE_DIR = CONFIG_DIR / "playwright-profile"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1pxaWKXYtZ-89cKk3OYE99-ewPMh2kXKvSDaqjR-I1o8"
FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSckkDKXcMnMREC8GTWDE7trx6Rhx0DP_aUP-gAduJhHEWsGcQ/viewform"
)
