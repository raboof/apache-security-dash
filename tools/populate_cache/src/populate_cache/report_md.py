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

"""Read / write a report bundle's ``report.md``.

Each bundle in ``report-cache/`` holds a single ``report.md``: YAML
front-matter (the report's metadata) followed by the original plain-text body.
Attachments sit next to it under ``attachments/``.

The format is the Jekyll/Hugo convention::

    ---
    field: value
    ...
    ---

    <report body>

``read()`` returns ``(meta_dict, body_str)``; ``write()`` serialises both back,
preserving the field order of ``meta`` so the schema's natural order survives.

Kept in sync with the ``report_md`` helper in the triage-populate-cache SKILL;
vendored here so the tool is self-contained and imports no SKILL code.
"""

from __future__ import annotations

from pathlib import Path

import yaml

BUNDLE_FILE = "report.md"
DELIM = "---"


def write(path: Path, meta: dict, body: str) -> None:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100).rstrip("\n")
    body = (body or "").rstrip("\n")
    path.write_text(f"{DELIM}\n{front}\n{DELIM}\n\n{body}\n", encoding="utf-8")


def read(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIM:
        raise ValueError(f"{path}: missing YAML front-matter (expected leading '---')")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == DELIM:
            end = i
            break
    if end is None:
        raise ValueError(f"{path}: front-matter has no closing '---'")
    front = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    meta = yaml.safe_load(front) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: front-matter must be a YAML mapping")
    return meta, body
