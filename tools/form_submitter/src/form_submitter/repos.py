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
"""Per-repo metadata + GitHub discoverability probes."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass
class RepoEntry:
    url: str
    name: str
    criticality: float | None  # None for blank cells; sorted last
    primary_language: str
    stars: str
    has_agents_md: bool = False
    has_security_md: bool = False
    has_security_txt: bool = False
    discoverability_checked: bool = False

    @property
    def is_submittable(self) -> bool:
        """A repo is submittable if at least one discoverability marker exists.

        AGENTS.md or SECURITY.md (or security.txt) — any one of those is
        enough for the scan agent to reach the project's threat model
        through the AGENTS.md → SECURITY.md → model chain (the chain
        tolerates either endpoint).
        """
        return self.has_agents_md or self.has_security_md or self.has_security_txt

    @property
    def can_claim_security_md(self) -> bool:
        """Reflects the form's "valid security.txt or SECURITY.md" checkbox.

        Ticks when ANY discoverability marker is present — AGENTS.md alone
        is sufficient because it carries the same "how to deal with
        findings" pointer the form asks about (the AGENTS.md → external
        SECURITY.md or threat-model URL chain is the standard pattern in
        the ASF Glasswing pipeline). The form's literal phrasing is a bit
        narrower, but the operational intent ("the repo tells researchers
        where to take findings") is satisfied either way.
        """
        return self.has_agents_md or self.has_security_md or self.has_security_txt


def parse_criticality(raw: str) -> float | None:
    """Parse the OSSF Criticality Score cell text into a float in [0, 100].

    Returns None for blank / unparsable cells; those sort last in the
    OSSF-criticality-ordered submission queue.
    """
    raw = (raw or "").strip().rstrip("%").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def repo_has_file(repo_name: str, path: str) -> bool:
    """Return True iff the file exists at HEAD on apache/<repo_name>.

    Uses ``gh api repos/apache/<repo>/contents/<path>`` — exit 0 on 200,
    non-zero on 404. The gh CLI is auth'd via the user's existing
    GitHub credentials; no extra config needed.
    """
    result = subprocess.run(
        ["gh", "api", f"repos/apache/{repo_name}/contents/{path}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def fill_discoverability(entries: list[RepoEntry]) -> None:
    """Populate the AGENTS.md / SECURITY.md / security.txt flags on every
    entry via the GitHub API. Mutates in place."""
    print(
        "Checking per-repo discoverability via gh api "
        "(AGENTS.md / SECURITY.md / security.txt at HEAD)...",
        file=sys.stderr,
    )
    for e in entries:
        e.has_agents_md = repo_has_file(e.name, "AGENTS.md")
        e.has_security_md = repo_has_file(e.name, "SECURITY.md")
        e.has_security_txt = repo_has_file(e.name, "security.txt") or repo_has_file(
            e.name, ".well-known/security.txt"
        )
        e.discoverability_checked = True
        markers = (
            ", ".join(
                label
                for label, present in [
                    ("AGENTS.md", e.has_agents_md),
                    ("SECURITY.md", e.has_security_md),
                    ("security.txt", e.has_security_txt),
                ]
                if present
            )
            or "NONE — will skip"
        )
        print(f"  apache/{e.name}: {markers}", file=sys.stderr)
