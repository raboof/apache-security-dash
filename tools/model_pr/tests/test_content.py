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
from model_pr.content import (
    branch_name,
    build_agents_md,
    build_security_md,
    ensure_asf_header,
    merge_ratignore,
)


def test_branch_name() -> None:
    assert branch_name("threat-model", "2026-05-31") == "asf-security/threat-model-2026-05-31"
    assert branch_name("discoverability", "2026-05-31") == "asf-security/discoverability-2026-05-31"


def test_build_security_md_create_inrepo() -> None:
    out = build_security_md(None, "apache/jspwiki", "[THREAT_MODEL.md](./THREAT_MODEL.md)")
    assert out.startswith("<!--")  # ASF license header (RAT)
    assert "# Security Policy" in out
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


# --- SPDX license header (short form) + RAT exemption on generated files ---


def test_security_md_create_has_spdx_header() -> None:
    out = build_security_md(None, "apache/x", "[THREAT_MODEL.md](./THREAT_MODEL.md)")
    assert out.startswith("<!--")
    assert "SPDX-License-Identifier: Apache-2.0" in out[:200]


def test_agents_md_create_has_spdx_header() -> None:
    out = build_agents_md(None, "x")
    assert out.startswith("<!--")
    assert "SPDX-License-Identifier: Apache-2.0" in out[:200]


def test_ensure_asf_header_prepends_when_missing() -> None:
    out = ensure_asf_header("# Apache Foo — Threat Model\n\nbody\n")
    assert out.startswith("<!--")
    assert "SPDX-License-Identifier: Apache-2.0" in out[:200]
    assert "# Apache Foo" in out


def test_ensure_asf_header_idempotent_on_existing_header() -> None:
    once = ensure_asf_header("# Model\n\nbody\n")
    assert ensure_asf_header(once) == once  # already has a header -> unchanged


def test_ensure_asf_header_detects_existing_spdx() -> None:
    already = "<!--\nSPDX-License-Identifier: Apache-2.0\n-->\n\n# Model\n"
    assert ensure_asf_header(already) == already


def test_ensure_asf_header_adds_when_apache_only_in_prose() -> None:
    # A model that *mentions* the Apache License in its body (not a top comment)
    # must still get a real header — RAT scans the file's top.
    doc = "# Apache Foo Threat Model\n\nFoo ships under the Apache License 2.0.\n"
    out = ensure_asf_header(doc)
    assert out.startswith("<!--")
    assert "SPDX-License-Identifier: Apache-2.0" in out[:200]
    assert out.count("# Apache Foo Threat Model") == 1


def test_merge_ratignore_create() -> None:
    out = merge_ratignore(None, ["THREAT_MODEL.md", "SECURITY.md", "AGENTS.md"])
    for f in ("THREAT_MODEL.md", "SECURITY.md", "AGENTS.md"):
        assert f in out.splitlines()
    assert out.endswith("\n")


def test_merge_ratignore_appends_preserving_existing() -> None:
    existing = "target/\n*.log\n"
    out = merge_ratignore(existing, ["THREAT_MODEL.md"])
    assert out.startswith("target/\n*.log\n")
    assert "THREAT_MODEL.md" in out.splitlines()


def test_merge_ratignore_idempotent() -> None:
    once = merge_ratignore("target/\n", ["THREAT_MODEL.md", "AGENTS.md"])
    assert merge_ratignore(once, ["THREAT_MODEL.md", "AGENTS.md"]) == once


def test_merge_ratignore_noop_when_all_present() -> None:
    existing = "THREAT_MODEL.md\nSECURITY.md\n"
    assert merge_ratignore(existing, ["THREAT_MODEL.md", "SECURITY.md"]) == existing


def test_security_md_pointer_autolink_keeps_period_outside() -> None:
    # cli wraps pointer URLs in <...>; the template's trailing '.' must land
    # outside the autolink so link-checkers don't grab "<url>." and 404.
    url = "https://github.com/apache/cxf/blob/main/THREAT_MODEL.md"
    out = build_security_md(None, "apache/x", f"<{url}>")
    assert f"<{url}>." in out
    assert f"{url}.\n" not in out  # never a bare url immediately before a period
