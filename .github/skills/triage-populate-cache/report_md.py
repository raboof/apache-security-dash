"""Read / write a report bundle's `report.md`.

Each bundle in `report-cache/` holds a single `report.md`: YAML front-matter
(the report's metadata, schema documented in SKILL.md) and then the original
plain-text body. Attachments and drafts sit next to it as separate files.

The format is the Jekyll/Hugo convention:

    ---
    field: value
    ...
    ---

    <report body>

read() returns (meta_dict, body_str); write() serializes both back, keeping
the field order from the dict (so meta.yaml's natural order survives).
"""

from __future__ import annotations

from pathlib import Path

import yaml

BUNDLE_FILE = "report.md"
DELIM = "---"


def write(path: Path, meta: dict, body: str) -> None:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100).rstrip(
        "\n"
    )
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
