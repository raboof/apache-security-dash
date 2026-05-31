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
"""Pure builders for the SECURITY.md / AGENTS.md discoverability scaffold.

These functions take the *existing* file content (or ``None`` if the file
does not exist) and return the new content. They are idempotent — re-running
against a file that already has the relevant section is a no-op — and they
never edit existing prose, only create a file or append one section. The
discoverability chain produced is the conventional
``AGENTS.md -> SECURITY.md -> <model>`` that the Glasswing scan agent follows.

No I/O here; the CLI does the git/gh side effects.
"""

from __future__ import annotations

ASF_HTML_HEADER = """<!--
SPDX-License-Identifier: Apache-2.0

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->"""


def branch_name(kind: str, date: str) -> str:
    """Branch name for a model/discoverability PR, e.g.
    ``asf-security/threat-model-2026-05-31``. ``kind`` is typically
    ``threat-model`` (in-repo model) or ``discoverability`` (pointer)."""
    return f"asf-security/{kind}-{date}"


def _agents_security_section(security_note: str = "") -> str:
    extra = f"\n\n{security_note.strip()}" if security_note.strip() else ""
    return (
        "## Security\n\n"
        "Security model: [SECURITY.md](./SECURITY.md)\n\n"
        "Agents that scan this repository should consult `SECURITY.md` and the\n"
        "threat model it links before reporting issues." + extra
    )


def build_agents_md(existing: str | None, repo: str, security_note: str = "") -> str:
    """Return AGENTS.md content with a ``## Security`` section pointing at
    ``SECURITY.md``. Creates the file (with the ASF header) when ``existing``
    is ``None``; appends the section otherwise. Idempotent: returns
    ``existing`` unchanged if it already has a ``## Security`` heading."""
    section = _agents_security_section(security_note)
    if existing is None:
        return (
            f"{ASF_HTML_HEADER}\n\n"
            f"# Agent Guide for {repo}\n\n"
            "This file is read by automated agents (security scanners, code\n"
            "analyzers, AI assistants) operating on this repository.\n\n"
            f"{section}\n"
        )
    if "## Security" in existing:
        return existing
    return f"{existing.rstrip()}\n\n{section}\n"


def _security_threat_section(model_ref: str) -> str:
    return (
        "## Threat Model\n\n"
        "What the project treats as in scope and out of scope, the security\n"
        "properties it provides and disclaims, the adversary model, and how\n"
        f"findings are triaged are documented in {model_ref}.\n"
    )


def build_security_md(existing: str | None, repo: str, model_ref: str) -> str:
    """Return SECURITY.md content with a ``## Threat Model`` section linking
    ``model_ref`` (e.g. ``[THREAT_MODEL.md](./THREAT_MODEL.md)`` for an in-repo
    model, or a cross-repo umbrella URL for a pointer). Creates a full policy
    file when ``existing`` is ``None``; appends the section otherwise.
    Idempotent: returns ``existing`` unchanged if it already has a
    ``## Threat Model`` heading."""
    section = _security_threat_section(model_ref)
    if existing is None:
        return (
            "# Security Policy\n\n"
            "## Reporting a Vulnerability\n\n"
            f"`{repo}` follows the [Apache Software Foundation security process]"
            "(https://www.apache.org/security/). Please report suspected\n"
            "vulnerabilities privately to `security@apache.org`; do not open public\n"
            "GitHub issues or pull requests for security reports.\n\n"
            f"{section}"
        )
    if "## Threat Model" in existing:
        return existing
    return f"{existing.rstrip()}\n\n{section}"
