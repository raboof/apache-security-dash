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

"""Read / write a bundle's triage artifacts, by plain filename.

A bundle is a directory under ``report-cache/``: the report itself
(``report.md`` plus the verbatim ``raw.eml``) and any *triage artifacts* the
skills write beside it (``summary.md``, ``note.md``, ``reason.md``, ...).

These are the programmatic counterpart of the ``get-artifact`` / ``put-artifact`` /
``remove-artifact`` CLI verbs.

The reserved report files are never treated as artifacts:
:func:`list_artifacts` skips them, and :func:`write_artifact` / :func:`remove_artifact`
refuse to touch them.
Every name is a single filename confined to the bundle (no separators, no traversal).
"""

from __future__ import annotations

from pathlib import Path

from report_cache.report_md import BUNDLE_FILE

RAW_FILE = "raw.eml"  # verbatim message saved beside report.md by populate-cache
RESERVED = frozenset({BUNDLE_FILE, RAW_FILE})  # the report itself, never an artifact


def safe_name(name: str) -> str:
    """A single filename confined to the bundle: no separators, no traversal.

    Raises ``ValueError`` for an empty, dotted, or path-bearing name,
    so a caller can neither escape the bundle directory nor name a sub-path.
    """
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError(f"unsafe name {name!r}: pass a plain filename, no path.")
    return name


def list_artifacts(bundle_dir: Path) -> list[str]:
    """Every triage-artifact filename in ``bundle_dir``, sorted (the reserved files aside)."""
    return sorted(p.name for p in bundle_dir.iterdir() if p.is_file() and p.name not in RESERVED)


def read_artifact(bundle_dir: Path, name: str) -> str | None:
    """The text of triage artifact ``name``, or ``None`` when it does not exist."""
    try:
        return (bundle_dir / safe_name(name)).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def write_artifact(bundle_dir: Path, name: str, content: str) -> Path:
    """Write ``content`` to triage artifact ``name`` in ``bundle_dir``;
    returns its path."""
    safe = safe_name(name)
    if safe in RESERVED:
        raise ValueError(f"{safe!r} is a reserved bundle file; choose another name.")
    path = bundle_dir / safe
    path.write_text(content, encoding="utf-8")
    return path


def remove_artifact(bundle_dir: Path, name: str) -> bool:
    """Delete triage artifact ``name``; ``True`` if it existed, ``False`` when absent.

    Refuses the reserved bundle files, like :func:`write_artifact`, so a flipped
    triage decision can only ever drop a draft, never the report itself.
    """
    safe = safe_name(name)
    if safe in RESERVED:
        raise ValueError(f"{safe!r} is a reserved bundle file, not an artifact.")
    try:
        (bundle_dir / safe).unlink()
    except FileNotFoundError:
        return False
    return True
