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

from model_pr.cli import build_parser
from model_pr.content import branch_name, build_agents_md, build_security_md


def test_branch_name() -> None:
    assert branch_name("threat-model", "2026-05-31") == "asf-security/threat-model-2026-05-31"
    assert branch_name("discoverability", "2026-05-31") == "asf-security/discoverability-2026-05-31"


def test_build_security_md_create_inrepo() -> None:
    out = build_security_md(None, "apache/jspwiki", "[THREAT_MODEL.md](./THREAT_MODEL.md)")
    assert out.startswith("# Security Policy")
    assert "## Reporting a Vulnerability" in out
    assert "## Threat Model" in out
    assert "[THREAT_MODEL.md](./THREAT_MODEL.md)" in out


def test_build_security_md_append_when_exists() -> None:
    existing = (
        "# Security Policy\n\n## Reporting a Vulnerability\n\nReport to security@apache.org.\n"
    )
    out = build_security_md(existing, "apache/cxf", "[THREAT_MODEL.md](./THREAT_MODEL.md)")
    assert out.startswith(existing.rstrip())  # existing prose untouched
    assert out.count("## Reporting a Vulnerability") == 1
    assert "## Threat Model" in out


def test_build_security_md_idempotent() -> None:
    once = build_security_md(None, "apache/x", "URL")
    twice = build_security_md(once, "apache/x", "URL")
    assert twice == once


def test_build_security_md_pointer_ref() -> None:
    out = build_security_md(
        None, "apache/cxf-xjc-utils", "https://github.com/apache/cxf/blob/main/THREAT_MODEL.md"
    )
    assert "https://github.com/apache/cxf/blob/main/THREAT_MODEL.md" in out


def test_build_agents_md_create() -> None:
    out = build_agents_md(None, "jspwiki")
    assert "# Agent Guide for jspwiki" in out
    assert "## Security" in out
    assert "[SECURITY.md](./SECURITY.md)" in out
    assert "SPDX-License-Identifier: Apache-2.0" in out


def test_build_agents_md_append_and_note() -> None:
    existing = "# Agent Guide\n\nSome build notes.\n"
    out = build_agents_md(
        existing, "cxf-xjc-utils", security_note="This repo is build-time tooling."
    )
    assert out.startswith(existing.rstrip())
    assert "## Security" in out
    assert "build-time tooling" in out


def test_build_agents_md_idempotent() -> None:
    once = build_agents_md(None, "x")
    assert build_agents_md(once, "x") == once


def test_open_requires_one_of_model_or_pointer() -> None:
    # mutually exclusive group is required → neither fails
    with pytest.raises(SystemExit):
        build_parser().parse_args(["open", "--repo", "apache/x", "--date", "2026-05-31"])


def test_open_argparse_model() -> None:
    args = build_parser().parse_args(
        ["open", "--repo", "jspwiki", "--model", "/tmp/m.md", "--date", "2026-05-31"]
    )
    assert args.cmd == "open"
    assert args.repo == "jspwiki"
    assert args.model == "/tmp/m.md"
    assert args.pointer is None
