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

from __future__ import annotations

from sheets_writer.status import compute_pmc_status


def _row(header: list[str], **overrides) -> tuple[list[str], dict[str, int]]:
    row = [""] * len(header)
    for col, val in overrides.items():
        row[header.index(col)] = val
    col_idx = {h: i for i, h in enumerate(header)}
    return row, col_idx


HEADER = [
    "PMC Name",
    "PMC Slug",
    "Request date",
    "Repositories requested",
    "Repositories submitted",
    "Contact Person",
    "Backup contact",
    "Security Model",
    "Security model verified",
    "Date scan requested",
    "Date scan received",
    "Forwarded scan to PMC",
    "PR/Issues",
    "Notes",
]


def test_compute_pmc_status_pre_flight() -> None:
    """Model not yet verified → Pre-flight."""
    row, col_idx = _row(
        HEADER,
        **{"PMC Slug": "x", "PMC Name": "Apache X", "Security Model": "https://x.org"},
    )
    result = compute_pmc_status(row, col_idx)
    assert result["state"] == "Pre-flight"
    assert result["model_status"] == "Nominated"


def test_compute_pmc_status_no_model_is_missing() -> None:
    row, col_idx = _row(HEADER, **{"PMC Slug": "x"})
    assert compute_pmc_status(row, col_idx)["model_status"] == "Missing"


def test_compute_pmc_status_ready() -> None:
    """Model verified, no submission yet → Ready."""
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
        },
    )
    result = compute_pmc_status(row, col_idx)
    assert result["state"] == "Ready"
    assert result["model_status"] == "Verified"


def test_compute_pmc_status_submitted() -> None:
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
            "Date scan requested": "2026-05-15",
        },
    )
    assert compute_pmc_status(row, col_idx)["state"] == "Submitted"


def test_compute_pmc_status_triaging() -> None:
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
            "Date scan requested": "2026-05-15",
            "Date scan received": "2026-05-20",
        },
    )
    assert compute_pmc_status(row, col_idx)["state"] == "Triaging"


def test_compute_pmc_status_delivered() -> None:
    """Once Forwarded is filled, it wins regardless of earlier columns."""
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Security Model": "https://x.org",
            "Security model verified": "2026-05-10",
            "Date scan requested": "2026-05-15",
            "Date scan received": "2026-05-20",
            "Forwarded scan to PMC": "2026-05-21",
        },
    )
    assert compute_pmc_status(row, col_idx)["state"] == "Delivered"


def test_compute_pmc_status_repo_counts() -> None:
    row, col_idx = _row(
        HEADER,
        **{
            "PMC Slug": "x",
            "Repositories requested": (
                "https://github.com/apache/x\n# commented out\n\nhttps://github.com/apache/y"
            ),
            "Repositories submitted": "https://github.com/apache/x",
        },
    )
    result = compute_pmc_status(row, col_idx)
    assert result["repos_requested_count"] == 2  # blank + comment lines skipped
    assert result["repos_submitted_count"] == 1


def test_compute_pmc_status_pr_urls_when_no_pr_cell() -> None:
    """Empty PR/Issues → no shell-out, all PR counts zero."""
    row, col_idx = _row(HEADER, **{"PMC Slug": "x"})
    result = compute_pmc_status(row, col_idx)
    assert result["pr_urls"] == []
    assert result["pr_open"] == result["pr_merged"] == result["pr_closed"] == 0


def test_compute_pmc_status_tolerant_to_missing_columns() -> None:
    """col_idx missing a column → that field reads as empty string."""
    row, col_idx = _row(HEADER, **{"PMC Slug": "x"})
    # Drop a column from col_idx to simulate a narrower sheet.
    del col_idx["Notes"]
    result = compute_pmc_status(row, col_idx)
    assert result["notes"] == ""
