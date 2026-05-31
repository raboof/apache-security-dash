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
"""Guard against Mermaid syntax that GitHub's renderer rejects.

This is NOT a full Mermaid parser. It catches specific failure classes that
have broken README diagrams in this repo — each slipped through review and only
surfaced as "Unable to render rich display ... got '...'" on github.com:

1. A raw ``;`` anywhere inside a ```mermaid block. Mermaid treats ``;`` as a
   statement separator, so a ``;`` inside node / edge / message text aborts the
   parse. The repo's diagrams separate statements with newlines, never ``;``.
2. An ``@`` inside an edge label (``-->|... @ ...|``). Newer Mermaid uses ``@``
   for edge ids and node-shape metadata, so an ``@`` inside a pipe-delimited
   edge label is lexed as a link-id token and the parse fails. (``@`` inside
   *node* text — e.g. an email address — is fine and is left alone.)

Each rule is a deliberately narrow, low-false-positive pattern, not a grammar;
a genuinely new render failure may need a new rule added here.

Usage: ``check_mermaid.py FILE [FILE ...]`` (prek passes the changed ``*.md``
files). Exits non-zero, listing ``path:line: reason`` for every hit; 0 if clean.
"""

from __future__ import annotations

import re
import sys

OPEN_FENCE = re.compile(r"^ *(`{3,}|~{3,})\s*mermaid\s*$", re.IGNORECASE)
CLOSE_FENCE = re.compile(r"^ *(`{3,}|~{3,})\s*$")
# Pipe-delimited edge labels, e.g. the `...` in `A -->|...| B`.
EDGE_LABEL = re.compile(r"\|([^|\n]*)\|")


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
        if any("@" in label for label in EDGE_LABEL.findall(line)):
            problems.append(
                f"{path}:{num}: '@' inside a mermaid edge label (|...|) breaks GitHub"
                f" rendering -> {line.strip()}"
            )
    return problems


def main(argv: list[str]) -> int:
    problems: list[str] = []
    for path in argv:
        if path.endswith(".md"):
            problems.extend(check_file(path))
    if problems:
        sys.stderr.write(
            "Mermaid lint failed — GitHub would refuse to render these diagrams:\n"
        )
        for problem in problems:
            sys.stderr.write(f"  {problem}\n")
        sys.stderr.write(
            "Fixes: separate statements with newlines (not ';'); keep '@' out of edge "
            "labels (it's fine inside node text).\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
