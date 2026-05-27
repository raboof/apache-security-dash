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
"""Shared fixtures — sample PMC rows + RepoEntry lists.

Mirrors the live tracker shape so plan-builder tests run against
realistic input without touching Google Sheets.
"""

from __future__ import annotations

import pytest

from form_submitter.repos import RepoEntry


@pytest.fixture
def submitter() -> dict:
    return {
        "name": "Jane Submitter",
        "email": "jsubmitter@apache.org",
        "github": "https://github.com/jsubmitter",
    }


@pytest.fixture
def hbase_pmc_row() -> dict:
    """A PMC row in 'ready for submission' state."""
    return {
        "PMC Slug": "hbase",
        "PMC Name": "Apache HBase",
        "Scan Requested": "Yes",
        "Security model verified": "2026-05-26",
        "Repositories requested": "https://github.com/apache/hbase",
        "Contact Person": "Nick Dimiduk <ndimiduk@apache.org>",
        "Backup contact": "Andrew Purtell <apurtell@apache.org>",
        "Security Model": "https://hbase.apache.org/security-model/",
        "Expedite Claude OSS Requests": "ndimiduk@apache.org\napurtell@apache.org",
        "Submission notes": "",
    }


@pytest.fixture
def repo_hbase() -> RepoEntry:
    return RepoEntry(
        url="https://github.com/apache/hbase",
        name="hbase",
        criticality=63.0,
        primary_language="Java",
        stars="5500",
        has_agents_md=True,
        has_security_md=True,
        has_security_txt=False,
        discoverability_checked=True,
    )


@pytest.fixture
def repo_hbase_only_agents() -> RepoEntry:
    """Repo with AGENTS.md but no SECURITY.md — submittable, can't claim
    the SECURITY.md checkbox literally."""
    return RepoEntry(
        url="https://github.com/apache/hbase-thirdparty",
        name="hbase-thirdparty",
        criticality=45.0,
        primary_language="Java",
        stars="120",
        has_agents_md=True,
        has_security_md=False,
        has_security_txt=False,
        discoverability_checked=True,
    )


@pytest.fixture
def repo_no_markers() -> RepoEntry:
    """Repo with no discoverability — not submittable, will be skipped."""
    return RepoEntry(
        url="https://github.com/apache/hbase-operator-tools",
        name="hbase-operator-tools",
        criticality=20.0,
        primary_language="Java",
        stars="30",
        has_agents_md=False,
        has_security_md=False,
        has_security_txt=False,
        discoverability_checked=True,
    )
