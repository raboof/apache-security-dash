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

import pytest

from form_submitter.repos import RepoEntry, parse_criticality


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("63.5%", 63.5),
        ("63.5", 63.5),
        ("  63.5  ", 63.5),
        ("100%", 100.0),
        ("0", 0.0),
        ("", None),
        ("   ", None),
        ("not a number", None),
        (None, None),
    ],
)
def test_parse_criticality(raw, expected) -> None:
    assert parse_criticality(raw) == expected


def test_is_submittable_with_agents_md() -> None:
    r = RepoEntry(
        url="https://github.com/apache/x",
        name="x",
        criticality=50.0,
        primary_language="Python",
        stars="100",
        has_agents_md=True,
    )
    assert r.is_submittable is True


def test_is_submittable_with_security_md() -> None:
    r = RepoEntry(
        url="https://github.com/apache/y",
        name="y",
        criticality=50.0,
        primary_language="Python",
        stars="100",
        has_security_md=True,
    )
    assert r.is_submittable is True


def test_is_submittable_with_security_txt() -> None:
    r = RepoEntry(
        url="https://github.com/apache/z",
        name="z",
        criticality=50.0,
        primary_language="Python",
        stars="100",
        has_security_txt=True,
    )
    assert r.is_submittable is True


def test_not_submittable_when_no_markers() -> None:
    r = RepoEntry(
        url="https://github.com/apache/w",
        name="w",
        criticality=50.0,
        primary_language="Python",
        stars="100",
    )
    assert r.is_submittable is False


def test_can_claim_security_md_tracks_is_submittable() -> None:
    """Per the SKILL: AGENTS.md alone qualifies, matching the form's
    operational-intent reading of the checkbox."""
    r_agents = RepoEntry(
        url="https://github.com/apache/a",
        name="a",
        criticality=50.0,
        primary_language="Python",
        stars="100",
        has_agents_md=True,
    )
    r_security = RepoEntry(
        url="https://github.com/apache/b",
        name="b",
        criticality=50.0,
        primary_language="Python",
        stars="100",
        has_security_md=True,
    )
    r_none = RepoEntry(
        url="https://github.com/apache/c",
        name="c",
        criticality=50.0,
        primary_language="Python",
        stars="100",
    )
    assert r_agents.can_claim_security_md is True
    assert r_security.can_claim_security_md is True
    assert r_none.can_claim_security_md is False


def test_criticality_sort_ordering() -> None:
    """High criticality first; None sorts last."""
    a = RepoEntry(url="u1", name="a", criticality=80.0, primary_language="", stars="")
    b = RepoEntry(url="u2", name="b", criticality=60.0, primary_language="", stars="")
    c = RepoEntry(url="u3", name="c", criticality=None, primary_language="", stars="")
    items = [c, a, b]
    items.sort(key=lambda e: (-(e.criticality or -1), e.name))
    assert [i.name for i in items] == ["a", "b", "c"]


def test_criticality_sort_breaks_ties_alphabetically() -> None:
    a = RepoEntry(url="u1", name="zebra", criticality=50.0, primary_language="", stars="")
    b = RepoEntry(url="u2", name="apple", criticality=50.0, primary_language="", stars="")
    items = [a, b]
    items.sort(key=lambda e: (-(e.criticality or -1), e.name))
    assert [i.name for i in items] == ["apple", "zebra"]
