#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
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
"""Guard against the Mermaid syntax that GitHub's renderer rejects.

This is NOT a full Mermaid parser. It catches the one failure class that has
broken README diagrams twice (see the git history: a "fix mermaid semicolon
parse error" commit, then a second regression): a raw semicolon inside a
```mermaid block. Mermaid treats ``;`` as a statement separator, so a ``;``
that ends up inside node, edge, or message text makes GitHub fail to render
with ``Unable to render rich display ... got 'INVALID'`` and show a parse
error instead of the diagram. Every diagram in this repo separates statements
with newlines, never ``;``, so any semicolon inside a mermaid block is a bug.

Usage: ``check_mermaid.py FILE [FILE ...]`` (prek passes the changed ``*.md``
files). Exits non-zero, listing ``path:line``, if any mermaid block contains a
semicolon; exits 0 otherwise.
"""

from __future__ import annotations

import re
import sys

OPEN_FENCE = re.compile(r"^ *(`{3,}|~{3,})\s*mermaid\s*$", re.IGNORECASE)
CLOSE_FENCE = re.compile(r"^ *(`{3,}|~{3,})\s*$")


def check_file(path: str) -> list[str]:
    """Return a list of ``path:line: message`` problems for one markdown file."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    problems: list[str] = []
    in_block = False
    for num, line in enumerate(lines, start=1):
        if not in_block:
            if OPEN_FENCE.match(line):
                in_block = True
            continue
        if CLOSE_FENCE.match(line):
            in_block = False
            continue
        if line.strip().startswith("%%"):  # Mermaid comment line.
            continue
        if ";" in line:
            problems.append(
                f"{path}:{num}: ';' inside a mermaid block breaks GitHub rendering"
                f" -> {line.strip()}"
            )
    return problems


def main(argv: list[str]) -> int:
    problems: list[str] = []
    for path in argv:
        if path.endswith(".md"):
            problems.extend(check_file(path))
    if problems:
        sys.stderr.write(
            "Mermaid lint failed. Remove ';' from diagram text — separate Mermaid "
            "statements with newlines, not semicolons:\n"
        )
        for problem in problems:
            sys.stderr.write(f"  {problem}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
