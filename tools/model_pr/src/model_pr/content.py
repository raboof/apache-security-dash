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

# Full Apache License v2.0 source header, wrapped in an HTML comment so it is
# invisible in rendered Markdown. We use the *full* header (not a short SPDX
# one-liner) because Apache RAT is the gate that matters here, and older RAT
# versions (e.g. 0.13, still used by some PMCs) do not recognise the SPDX
# identifier — they match only the canonical AL-2.0 boilerplate below. The full
# header is recognised by every RAT version, so the generated files pass the
# license check directly and no ``.ratignore`` exemption is needed.
ASF_HTML_HEADER = (
    "<!--\n"
    "Licensed to the Apache Software Foundation (ASF) under one\n"
    "or more contributor license agreements.  See the NOTICE file\n"
    "distributed with this work for additional information\n"
    "regarding copyright ownership.  The ASF licenses this file\n"
    "to you under the Apache License, Version 2.0 (the\n"
    '"License"); you may not use this file except in compliance\n'
    "with the License.  You may obtain a copy of the License at\n"
    "\n"
    "  http://www.apache.org/licenses/LICENSE-2.0\n"
    "\n"
    "Unless required by applicable law or agreed to in writing,\n"
    "software distributed under the License is distributed on an\n"
    '"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY\n'
    "KIND, either express or implied.  See the License for the\n"
    "specific language governing permissions and limitations\n"
    "under the License.\n"
    "-->"
)


def ensure_asf_header(content: str) -> str:
    """Prepend the short SPDX Apache-2.0 header (HTML comment) unless
    ``content`` already carries an Apache-2.0 header. Idempotent.

    The threat-model document supplied via ``--model`` is authored without a
    header, so the CLI runs it through this before writing. The full AL-2.0
    header is what Apache RAT matches, so the file passes the license check on
    every RAT version without any ``.ratignore`` exemption.
    """
    stripped = content.lstrip()
    head = "\n".join(stripped.splitlines()[:30]).lower()
    # Only count it as headered if the file *opens* with an HTML-comment that
    # carries the license — a threat model that merely *mentions* the Apache
    # License in its prose must still get a real header (RAT scans the top).
    has_header = stripped.startswith("<!--") and (
        "apache license" in head
        or "licenses/license-2.0" in head
        or "spdx-license-identifier: apache-2.0" in head
    )
    if has_header:
        return content
    return f"{ASF_HTML_HEADER}\n\n{stripped}"


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
            f"{ASF_HTML_HEADER}\n\n"
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
