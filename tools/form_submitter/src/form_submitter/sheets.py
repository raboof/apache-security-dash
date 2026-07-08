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
"""Google Sheets reads: tracker spreadsheet → PMC row + repo list."""

from __future__ import annotations

import sys

from googleapiclient.discovery import build

from form_submitter import SPREADSHEET_ID
from form_submitter.auth import load_sheets_credentials
from form_submitter.repos import RepoEntry, fill_discoverability, parse_criticality


class PMCStateError(Exception):
    """PMC not found, missing required fields, or no usable repo URLs."""


def read_grid(svc, sheet_name: str, rng: str = "A1:Z3000") -> list[dict]:
    """Return a list of dicts keyed by the header row.

    Each row is padded to header length so missing trailing cells become
    empty strings rather than KeyError on access.
    """
    result = (
        svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!{rng}",
            majorDimension="ROWS",
        )
        .execute()
    )
    rows = result.get("values", [])
    if not rows:
        return []
    headers = rows[0]
    out = []
    for r in rows[1:]:
        padded = r + [""] * (len(headers) - len(r))
        out.append({headers[i]: padded[i] for i in range(len(headers))})
    return out


def fetch_pmc_state(slug: str) -> dict:
    """Return PMC row + ordered repo list for a slug.

    Raises:
        PMCStateError: slug missing, required fields blank, or no usable
            repo URLs.
    """
    creds = load_sheets_credentials()
    svc = build("sheets", "v4", credentials=creds)

    pmcs = read_grid(svc, "PMCs")
    pmc_row = next((r for r in pmcs if r.get("PMC Slug", "").strip() == slug), None)
    if pmc_row is None:
        raise PMCStateError(f"PMC slug {slug!r} not found in PMCs sheet.")

    required_fields = {
        "Scan Requested": "Yes",
        "Security model verified": None,  # any non-blank
        "Repositories requested": None,
        "Contact Person": None,
        "Security Model": None,
    }
    missing = []
    for field, expected in required_fields.items():
        val = pmc_row.get(field, "").strip()
        if expected is None and not val:
            missing.append(f"{field} (blank)")
        elif expected is not None and val != expected:
            missing.append(f"{field} (got {val!r}, expected {expected!r})")
    if missing:
        raise PMCStateError(
            f"PMC {slug!r} not ready for submission:\n  - " + "\n  - ".join(missing)
        )

    # Backup contact is optional: some PMCs operate with a single confirmed
    # contact (e.g. Santuario — Colm O hEigeartaigh, solo by the PMC's own
    # statement). A blank backup is a warning, not a blocker; the headline
    # form's Additional Information renders it as "(none — solo PMC contact)".
    if not pmc_row.get("Backup contact", "").strip():
        print(
            f"WARN: Backup contact on {slug!r} is blank — proceeding with a "
            "single (solo) PMC contact.",
            file=sys.stderr,
        )

    requested_urls = [
        line.strip()
        for line in pmc_row["Repositories requested"].splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not requested_urls:
        raise PMCStateError(f"PMC {slug!r} has no usable URLs in Repositories requested.")

    repos_sheet = read_grid(svc, "Repositories")
    by_url = {r.get("Repository URL", "").strip(): r for r in repos_sheet}

    entries: list[RepoEntry] = []
    for url in requested_urls:
        meta = by_url.get(url)
        if meta is None:
            entries.append(
                RepoEntry(
                    url=url,
                    name=url.rsplit("/", 1)[-1],
                    criticality=None,
                    primary_language="",
                    stars="",
                )
            )
            continue
        entries.append(
            RepoEntry(
                url=url,
                name=meta.get("Repository Name", url.rsplit("/", 1)[-1]).strip(),
                criticality=parse_criticality(meta.get("Criticality Score (%)", "")),
                primary_language=meta.get("Primary Language", "").strip(),
                stars=meta.get("GitHub Stars", "").strip(),
            )
        )

    entries.sort(key=lambda e: (-(e.criticality or -1), e.name))

    fill_discoverability(entries)

    return {"pmc": pmc_row, "repos": entries}
