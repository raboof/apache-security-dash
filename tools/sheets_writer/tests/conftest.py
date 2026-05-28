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
"""Shared fixtures + a minimal Google Sheets API stand-in for tests.

The real `googleapiclient` Resource chain is:
    service.spreadsheets().values().get(...).execute()
    service.spreadsheets().values().batchUpdate(...).execute()
    service.spreadsheets().values().append(...).execute()
    service.spreadsheets().values().update(...).execute()
    service.spreadsheets().values().clear(...).execute()
    service.spreadsheets().get(...).execute()
    service.spreadsheets().batchUpdate(...).execute()

`FakeSheetsService` reproduces enough of that chain so the apply /
append / status code paths can run end-to-end without a real API.
Calls are recorded as ``(method, kwargs)`` tuples in
``service.calls`` for assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class FakeRequest:
    """One leaf of the resource chain — has an ``.execute()`` method."""

    _result: Any = None

    def execute(self) -> Any:
        return self._result


@dataclass
class FakeValuesResource:
    parent: FakeSheetsService

    def get(self, **kwargs) -> FakeRequest:
        self.parent.calls.append(("values.get", kwargs))
        sheet_range = kwargs.get("range", "")
        # Range like "PMCs!A1:Z3000" or "PMCs" — strip the !A1 part.
        sheet_name = sheet_range.split("!", 1)[0]
        rows = self.parent.grids.get(sheet_name, [])
        return FakeRequest({"values": rows} if rows else {})

    def batchUpdate(self, **kwargs) -> FakeRequest:
        self.parent.calls.append(("values.batchUpdate", kwargs))
        return FakeRequest(self.parent.batch_update_response)

    def append(self, **kwargs) -> FakeRequest:
        self.parent.calls.append(("values.append", kwargs))
        return FakeRequest(self.parent.append_response)

    def update(self, **kwargs) -> FakeRequest:
        self.parent.calls.append(("values.update", kwargs))
        return FakeRequest({})

    def clear(self, **kwargs) -> FakeRequest:
        self.parent.calls.append(("values.clear", kwargs))
        return FakeRequest({})


@dataclass
class FakeSpreadsheetsResource:
    parent: FakeSheetsService

    def values(self) -> FakeValuesResource:
        return FakeValuesResource(self.parent)

    def get(self, **kwargs) -> FakeRequest:
        self.parent.calls.append(("spreadsheets.get", kwargs))
        return FakeRequest({"sheets": self.parent.sheet_meta})

    def batchUpdate(self, **kwargs) -> FakeRequest:
        self.parent.calls.append(("spreadsheets.batchUpdate", kwargs))
        return FakeRequest(self.parent.spreadsheets_batch_update_response)


@dataclass
class FakeSheetsService:
    """A Google Sheets v4 client stand-in good enough for the tests."""

    grids: dict[str, list[list[str]]] = field(default_factory=dict)
    sheet_meta: list[dict] = field(default_factory=list)
    calls: list[tuple[str, dict]] = field(default_factory=list)
    batch_update_response: dict = field(
        default_factory=lambda: {
            "totalUpdatedCells": 1,
            "totalUpdatedRows": 1,
            "responses": [{}],
        }
    )
    append_response: dict = field(
        default_factory=lambda: {"updates": {"updatedRange": "PMCs!A99:Z99"}}
    )
    spreadsheets_batch_update_response: dict = field(
        default_factory=lambda: {"replies": [{"addSheet": {"properties": {"sheetId": 42}}}]}
    )

    def spreadsheets(self) -> FakeSpreadsheetsResource:
        return FakeSpreadsheetsResource(self)


# Sample grids used in multiple tests.
PMCS_HEADER = [
    "PMC Name",
    "PMC Slug",
    "Scan Requested",
    "Repositories requested",
    "Repositories submitted",
    "Request date",
    "Contact Person",
    "Backup contact",
    "Security Model",
    "Security model verified",
    "Date scan requested",
    "Date scan received",
    "Forwarded scan to PMC",
    "Notes",
    "PR/Issues",
]


def make_pmc_row(**overrides: str) -> list[str]:
    """Build a PMCs-sheet row dict-style; fills unspecified columns with ''."""
    row = [""] * len(PMCS_HEADER)
    for col, val in overrides.items():
        row[PMCS_HEADER.index(col)] = val
    return row


@pytest.fixture
def pmcs_grid() -> list[list[str]]:
    """A small PMCs sheet with one each of the 5 pipeline states."""
    return [
        PMCS_HEADER,
        make_pmc_row(
            **{
                "PMC Name": "Apache PreFlightOnly",
                "PMC Slug": "pre",
                "Scan Requested": "Yes",
                "Request date": "2026-05-01",
                "Repositories requested": "https://github.com/apache/pre",
                "Security Model": "https://pre.apache.org/sec",
            }
        ),
        make_pmc_row(
            **{
                "PMC Name": "Apache Ready",
                "PMC Slug": "ready",
                "Scan Requested": "Yes",
                "Request date": "2026-05-05",
                "Repositories requested": "https://github.com/apache/ready",
                "Security Model": "https://ready.apache.org/sec",
                "Security model verified": "2026-05-10",
            }
        ),
        make_pmc_row(
            **{
                "PMC Name": "Apache Submitted",
                "PMC Slug": "submitted",
                "Scan Requested": "Yes",
                "Request date": "2026-05-05",
                "Repositories requested": (
                    "https://github.com/apache/submitted\nhttps://github.com/apache/submitted-other"
                ),
                "Repositories submitted": (
                    "https://github.com/apache/submitted\nhttps://github.com/apache/submitted-other"
                ),
                "Security Model": "https://x.org",
                "Security model verified": "2026-05-10",
                "Date scan requested": "2026-05-15",
            }
        ),
        make_pmc_row(
            **{
                "PMC Name": "Apache Triaging",
                "PMC Slug": "triaging",
                "Scan Requested": "Yes",
                "Request date": "2026-05-05",
                "Repositories requested": "https://github.com/apache/triaging",
                "Security Model": "https://x.org",
                "Security model verified": "2026-05-10",
                "Date scan requested": "2026-05-15",
                "Date scan received": "2026-05-20",
            }
        ),
        make_pmc_row(
            **{
                "PMC Name": "Apache Delivered",
                "PMC Slug": "delivered",
                "Scan Requested": "Yes",
                "Request date": "2026-05-05",
                "Repositories requested": "https://github.com/apache/delivered",
                "Repositories submitted": "https://github.com/apache/delivered",
                "Security Model": "https://x.org",
                "Security model verified": "2026-05-10",
                "Date scan requested": "2026-05-15",
                "Date scan received": "2026-05-20",
                "Forwarded scan to PMC": "2026-05-21",
            }
        ),
        # Not-requested PMC — should be filtered out of status entries.
        make_pmc_row(
            **{
                "PMC Name": "Apache NotRequested",
                "PMC Slug": "notreq",
            }
        ),
    ]


@pytest.fixture
def fake_service(pmcs_grid: list[list[str]]) -> FakeSheetsService:
    """A `FakeSheetsService` pre-loaded with the PMCs sample grid."""
    return FakeSheetsService(grids={"PMCs": pmcs_grid})
