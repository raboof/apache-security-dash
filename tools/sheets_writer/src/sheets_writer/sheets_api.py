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
"""Thin shims over the Google Sheets API v4 client."""

from __future__ import annotations

from googleapiclient.discovery import build

from sheets_writer.auth import load_credentials


def get_service():
    """Build the authenticated sheets v4 service client."""
    creds = load_credentials()
    return build("sheets", "v4", credentials=creds)


def fetch_sheet_grid(service, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
    """Return every row of ``sheet_name`` as a list of cell-string lists.

    The header row is the first element. Empty trailing cells are NOT
    padded; callers needing fixed-width access do their own padding (the
    Sheets API omits trailing blanks).
    """
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_name, majorDimension="ROWS")
        .execute()
    )
    return resp.get("values", [])
