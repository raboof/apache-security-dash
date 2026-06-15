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

"""Read the `report-cache/` produced by the triage SKILLs.

`triage-populate-cache` downloads each inbound report into
`report-cache/<date>/<pmc>/<keywords>/report.md` and records a
Message-ID -> bundle map in `report-cache/index.json`; `triage-assess` then
writes `draft-forward.md` / `draft-receipt.md` / `draft-reply.md` next to it
and advances the front-matter `status`. This module lets `inbox_manager` join
a live inbox message (by RFC Message-ID) to its bundle so it can act on the
disposition the SKILLs already decided, instead of re-deriving everything.

Read-only: nothing here mutates the cache. If the cache is missing (a machine
that has not run the SKILLs) every lookup returns ``None`` and the caller falls
back to its own interactive triage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from os import getenv
from pathlib import Path

import yaml

# report-cache/ lives at the repo root: .../tools/inbox_manager/src/inbox_manager/
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = REPO_ROOT / "report-cache"

BUNDLE_FILE = "report.md"
INDEX_FILE = "index.json"

# A draft's leading "<!-- DRAFT for human review ... -->" header (To:/Subject:
# hints for the sender); stripped off before the body is rendered.
_DRAFT_HEADER = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)
_HEADER_FIELD = re.compile(r"^(To|Subject):\s*(.*)$", re.MULTILINE)


def cache_dir() -> Path:
    """The report-cache root (override with REPORT_CACHE_DIR)."""
    override = getenv("REPORT_CACHE_DIR")
    return Path(override) if override else DEFAULT_CACHE_DIR


def load_index(root: Path | None = None) -> dict:
    """The Message-ID -> {path, pmc, status, tags, ...} map, or {} if absent."""
    root = root or cache_dir()
    path = root / INDEX_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_front_matter(bundle_md: Path) -> dict:
    """Parse the YAML front-matter of a bundle's report.md."""
    text = bundle_md.read_text(encoding="utf-8")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = yaml.safe_load("\n".join(lines[1:i])) or {}
            return meta if isinstance(meta, dict) else {}
    return {}


@dataclass
class Bundle:
    """A filed report bundle: its directory plus the report.md front-matter."""

    path: Path
    meta: dict

    @property
    def status(self) -> str:
        return self.meta.get("status") or ""

    @property
    def pmc(self) -> str:
        return self.meta.get("pmc") or ""

    @property
    def forwarded_to(self) -> str:
        return self.meta.get("forwarded_to") or ""

    @property
    def is_digest(self) -> bool:
        return (self.meta.get("keywords") or []) == ["digest"]

    @property
    def is_non_issue(self) -> bool:
        return (self.meta.get("collection") or "") == "zzz-non-issue"

    def draft(self, name: str) -> tuple[str, str, str] | None:
        """``(to_hint, subject_hint, body)`` for a draft file, or None.

        The leading ``<!-- DRAFT ... -->`` comment is parsed for the To/Subject
        hints and then stripped, so ``body`` is just the Markdown to send.
        """
        path = self.path / name
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        header = _DRAFT_HEADER.match(raw)
        to_hint = subject_hint = ""
        if header:
            for field, value in _HEADER_FIELD.findall(header.group(0)):
                if field == "To":
                    to_hint = value.strip()
                elif field == "Subject":
                    subject_hint = value.strip()
        body = _DRAFT_HEADER.sub("", raw).strip()
        return to_hint, subject_hint, body


def lookup(message_id: str, index: dict, root: Path | None = None) -> Bundle | None:
    """Find the bundle for a live message's RFC Message-ID, or None."""
    if not message_id:
        return None
    entry = index.get(message_id.strip())
    if not entry:
        return None
    root = root or cache_dir()
    bundle_md = root / entry["path"] / BUNDLE_FILE
    try:
        meta = _read_front_matter(bundle_md)
    except OSError:
        return None
    if not meta:
        return None
    return Bundle(path=bundle_md.parent, meta=meta)
