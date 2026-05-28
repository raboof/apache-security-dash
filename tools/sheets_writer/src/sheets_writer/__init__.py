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
"""OAuth-authenticated writer for the Glasswing / Mythos scan-outreach
Google Sheet.

Reads OAuth client secret + refresh token from
``~/.config/asf-security/glasswing/`` (outside the repo). The user acts
as themselves — they must already have edit access to the spreadsheet.

CLI subcommands:

  setup
      Run the OAuth installed-app flow once and persist a refresh token
      at ``~/.config/asf-security/glasswing/token.json``.
  apply --spreadsheet-id ID --updates PATH [--dry-run]
      Apply a JSON list of row-level updates (match + set).
  init-canned-tab --spreadsheet-id ID [--dry-run]
      Create the 'Canned Responses' sheet idempotently.
  append-canned --spreadsheet-id ID --entries PATH [--dry-run]
      Append canned-response rows.
  append-pmc --spreadsheet-id ID --entries PATH [--dry-run]
      Append new PMC rows; aborts on duplicate slug.
  build-status-tab --spreadsheet-id ID [--dry-run]
      Refresh the 'Status' tab with in-flight + completed tables +
      timeline data, color-coded by pipeline state.
  rename-column --spreadsheet-id ID --sheet S --old H --new NEW [--dry-run]
  insert-column --spreadsheet-id ID --sheet S --after H --header NEW [--dry-run]
  add-columns --spreadsheet-id ID --sheet S --headers H... [--dry-run]
"""

from pathlib import Path

__version__ = "0.1.0"

CONFIG_DIR = Path.home() / ".config" / "asf-security" / "glasswing"
CLIENT_SECRET_PATH = CONFIG_DIR / "oauth_client_secret.json"
TOKEN_PATH = CONFIG_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CANNED_SHEET = "Canned Responses"
CANNED_HEADERS = [
    "Date Added",
    "Topic",
    "Question pattern",
    "Response",
    "Author",
    "Notes",
]

PMCS_SHEET = "PMCs"
PMCS_REQUIRED_FIELDS = ("PMC Name", "PMC Slug")

STATUS_SHEET = "Status"

# Pipeline states in progression order. Order matters: the state-detection
# function picks the latest applicable state, and colors render red->green
# by state index.
PIPELINE_STATES = [
    "Pre-flight",
    "Ready",
    "Submitted",
    "Triaging",
    "Delivered",
]

STATE_COLOR = {
    "Pre-flight": {"red": 0.96, "green": 0.78, "blue": 0.78},  # light red
    "Ready": {"red": 1.00, "green": 0.93, "blue": 0.70},  # yellow
    "Submitted": {"red": 0.84, "green": 0.95, "blue": 0.74},  # light green
    "Triaging": {"red": 0.62, "green": 0.86, "blue": 0.62},  # medium green
    "Delivered": {"red": 0.40, "green": 0.74, "blue": 0.42},  # dark green
}

MODEL_COLOR = {
    "Verified": {"red": 0.70, "green": 0.90, "blue": 0.70},
    "Nominated": {"red": 1.00, "green": 0.93, "blue": 0.70},
    "Missing": {"red": 0.96, "green": 0.78, "blue": 0.78},
}
