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
"""Per-row PR-state lookup helpers (parse URLs + shell out to gh)."""

from __future__ import annotations

import json
import re
import subprocess

_PR_URL_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+")


def parse_pr_urls(cell_text: str) -> list[str]:
    """Extract every github.com/<owner>/<repo>/pull/<n> URL from a cell.

    The PR/Issues cell is a newline-separated list of references; each
    line typically has the URL followed by free-text description
    ('discoverability PR', 'Email reply sent 2026-05-14', etc.). We
    extract every PR URL we find via regex; non-PR lines (email
    references) are ignored.
    """
    if not cell_text:
        return []
    urls = []
    for match in _PR_URL_RE.finditer(cell_text):
        url = match.group(0)
        if url not in urls:
            urls.append(url)
    return urls


def query_pr_states(urls: list[str]) -> dict:
    """Return ``{'open': n, 'merged': n, 'closed': n, 'errors': [...]}``.

    Uses ``gh pr view --json state`` per URL. The state values are
    OPEN / MERGED / CLOSED (gh treats merged PRs as a distinct state
    from closed-but-not-merged). Best-effort: a failure on one URL
    (auth, network, deleted PR) is recorded as an error but doesn't
    block the rest.
    """
    result = {"open": 0, "merged": 0, "closed": 0, "errors": []}
    for url in urls:
        try:
            p = subprocess.run(
                ["gh", "pr", "view", url, "--json", "state"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if p.returncode != 0:
                result["errors"].append(f"{url}: gh exit {p.returncode}: {p.stderr.strip()[:80]}")
                continue
            data = json.loads(p.stdout)
            state = data.get("state", "").upper()
            if state == "MERGED":
                result["merged"] += 1
            elif state == "OPEN":
                result["open"] += 1
            elif state == "CLOSED":
                result["closed"] += 1
            else:
                result["errors"].append(f"{url}: unknown state {state!r}")
        except Exception as e:  # noqa: BLE001 — single boundary for diagnostics
            result["errors"].append(f"{url}: {e}")
    return result


_PR_PARTS_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")

# How strongly a path in a merged PR looks like "the threat/security model
# document itself" (highest score wins). A pointer file (SECURITY.md) scores
# low — it's usually just a link to the model, not the model — but still beats
# nothing when a PR added only that.
_MODEL_FILE_PATTERNS = [
    (re.compile(r"(^|/)THREAT[_-]?MODEL\.(md|adoc|rst|txt)$", re.I), 100),
    (re.compile(r"(^|/)SECURITY[_-]THREAT[_-]MODEL\.(md|adoc|rst|txt)$", re.I), 95),
    (re.compile(r"threat[_-]?model", re.I), 80),
    (re.compile(r"security[_-]?model", re.I), 70),
    (re.compile(r"(^|/)SECURITY\.(md|adoc|rst|txt)$", re.I), 40),
]


def resolve_model_file_url(pr_url: str) -> str | None:
    """Given a *merged* PR URL, return the blob URL of the threat/security
    model document the PR added — i.e. the model itself, not the PR page.

    Shells out to ``gh pr view --json state,files,baseRefName``. Returns
    ``None`` (so the caller can fall back) when the PR isn't merged, has no
    model-looking file, or any gh/network error occurs. Best-effort: never
    raises.
    """
    m = _PR_PARTS_RE.search(pr_url or "")
    if not m:
        return None
    owner, repo, _num = m.groups()
    try:
        p = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "state,files,baseRefName"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if p.returncode != 0:
            return None
        data = json.loads(p.stdout)
        if data.get("state", "").upper() != "MERGED":
            return None
        base = data.get("baseRefName") or "HEAD"
        best_path, best_score = None, 0
        for f in data.get("files", []):
            path = f.get("path", "")
            for pat, score in _MODEL_FILE_PATTERNS:
                if pat.search(path) and score > best_score:
                    best_path, best_score = path, score
        if not best_path:
            return None
        return f"https://github.com/{owner}/{repo}/blob/{base}/{best_path}"
    except Exception:  # noqa: BLE001 — best-effort; fall back on any failure
        return None
