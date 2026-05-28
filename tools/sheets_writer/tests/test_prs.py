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

from sheets_writer.prs import parse_pr_urls


def test_parse_pr_urls_single() -> None:
    assert parse_pr_urls("https://github.com/apache/hbase/pull/8275") == [
        "https://github.com/apache/hbase/pull/8275"
    ]


def test_parse_pr_urls_with_free_text() -> None:
    """Real cells have descriptions after each URL."""
    cell = (
        "https://github.com/apache/hbase/pull/8275 (SECURITY.md — OPEN 2026-05-26)\n"
        "https://github.com/apache/polaris/pull/4433 (threat model, MERGED)"
    )
    assert parse_pr_urls(cell) == [
        "https://github.com/apache/hbase/pull/8275",
        "https://github.com/apache/polaris/pull/4433",
    ]


def test_parse_pr_urls_dedupes() -> None:
    cell = (
        "https://github.com/apache/x/pull/1 (one)\nhttps://github.com/apache/x/pull/1 (duplicate)\n"
    )
    assert parse_pr_urls(cell) == ["https://github.com/apache/x/pull/1"]


def test_parse_pr_urls_ignores_non_pr_lines() -> None:
    """Email-reference lines without /pull/ in them are skipped."""
    cell = "Email reply sent 2026-05-14\nhttps://github.com/apache/x/pull/1 (the only PR)"
    assert parse_pr_urls(cell) == ["https://github.com/apache/x/pull/1"]


def test_parse_pr_urls_empty_cell() -> None:
    assert parse_pr_urls("") == []
    assert parse_pr_urls(None) == []  # tolerant to None


def test_parse_pr_urls_no_matches() -> None:
    """Cell has text but no PR URLs."""
    assert parse_pr_urls("waiting on PMC reply") == []
