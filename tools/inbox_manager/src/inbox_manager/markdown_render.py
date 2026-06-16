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

"""Render the triage replies (CommonMark) to the two forms an email needs.

The team templates (`forward.md`, `receipt.md`, `reject.md`, ...) and the
model-authored fragments the triage-assess SKILL writes (`summary.md`,
`note.md`, `reason.md`) are Markdown. An outgoing message wants both an HTML
part and a plain-text part, so this module renders one parse two ways:

- ``md_to_html`` - CommonMark -> HTML (links stay inline ``<a href>``). The
  caller is expected to run the result through the same nh3 allowlist used for
  forwarded content (``email_utils._sanitize_html``).
- ``md_to_text`` - CommonMark -> plain text wrapped to 78 columns, with every
  ``[label](url)`` link turned into a numbered ``label[n]`` reference and the
  URLs collected into a ``[n] <url>`` footnote block at the end (lynx style).
  Bare/autolinked URLs (where the visible text already *is* the URL) stay
  inline and get no footnote.

Both share one ``MarkdownIt`` parser so the two renderings never drift.
"""

from __future__ import annotations

import textwrap

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

DEFAULT_WIDTH = 78

# CommonMark, but with raw-HTML passthrough OFF: our drafts and templates are
# pure Markdown, so a literal `<...>` (e.g. an unfilled `<reason>` placeholder,
# or a stray angle bracket in an AI summary) is treated as text and escaped,
# not parsed as markup. No bare-URL linkify either - the templates spell their
# links out as [text](url), so linkify-it is never needed.
_md = MarkdownIt("commonmark", {"html": False})


def md_to_html(md_text: str) -> str:
    """Render Markdown to an HTML fragment (caller sanitises)."""
    return _md.render(md_text or "")


def md_to_text(md_text: str, width: int = DEFAULT_WIDTH) -> str:
    """Render Markdown to wrapped plain text with numbered link footnotes."""
    root = SyntaxTreeNode(_md.parse(md_text or ""))
    links: list[tuple[int, str]] = []
    blocks = _blocks(root, width, links)
    text = "\n\n".join(b for b in blocks if b)
    if links:
        footer = "\n".join(f"[{n}] {href}" for n, href in links)
        text = f"{text}\n\n{footer}" if text else footer
    return text.strip()


# ---- plain-text rendering ----------------------------------------------------


def _link_number(links: list[tuple[int, str]], href: str) -> int:
    """The footnote number for `href`, reusing one if the URL repeats."""
    for n, existing in links:
        if existing == href:
            return n
    n = len(links) + 1
    links.append((n, href))
    return n


def _inline(node: SyntaxTreeNode, links: list[tuple[int, str]]) -> str:
    """Flatten an inline subtree to a single string with link references."""
    parts: list[str] = []
    for child in node.children:
        kind = child.type
        if kind == "text":
            parts.append(child.content)
        elif kind == "code_inline":
            # Plain text drops the backticks and keeps the literal content.
            parts.append(child.content)
        elif kind in ("softbreak", "hardbreak"):
            # Keep the author's line breaks (signatures, addresses); only
            # over-long single lines are folded later.
            parts.append("\n")
        elif kind == "link":
            label = _inline(child, links)
            href = child.attrs.get("href", "")
            if href and href != label:
                parts.append(f"{label}[{_link_number(links, href)}]")
            else:
                parts.append(label or href)
        else:
            # strong / em / s / sup / ... : keep the text, drop the styling.
            # A leaf node with content but no children (defensive) keeps its
            # text verbatim rather than vanishing.
            inner = _inline(child, links)
            parts.append(inner if inner or not child.content else child.content)
    return "".join(parts)


def _fold(text: str, width: int, initial: str = "", subsequent: str = "") -> str:
    """Fold `text` to `width`, preserving its embedded line breaks.

    Each existing line is wrapped on its own (so author line breaks survive);
    the first physical line takes `initial`, the rest take `subsequent`. URLs,
    emails and code-ish identifiers are never split.
    """
    out = []
    for i, line in enumerate(text.split("\n")):
        if line.strip():
            out.append(
                textwrap.fill(
                    line,
                    width=width,
                    initial_indent=initial if i == 0 else subsequent,
                    subsequent_indent=subsequent,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
        else:
            out.append("")
    return "\n".join(out)


def _item_text(item: SyntaxTreeNode, width: int, links: list[tuple[int, str]]) -> str:
    """Render a list item's blocks; paragraphs flatten, the rest recurse."""
    pieces: list[str] = []
    for child in item.children:
        if child.type == "paragraph":
            pieces.append(_inline(child, links))
        else:
            pieces.extend(_blocks_one(child, width, links))
    return "\n\n".join(p for p in pieces if p)


def _list(
    node: SyntaxTreeNode,
    width: int,
    links: list[tuple[int, str]],
    ordered: bool,
) -> str:
    lines = []
    for i, item in enumerate(node.children, 1):
        marker = f"{i}. " if ordered else "- "
        hang = " " * len(marker)
        body = _item_text(item, width, links)
        lines.append(_fold(body, width, initial=marker, subsequent=hang))
    return "\n".join(lines)


def _blocks_one(
    node: SyntaxTreeNode, width: int, links: list[tuple[int, str]]
) -> list[str]:
    """Render a single block node to zero or more block strings."""
    kind = node.type
    if kind in ("paragraph", "heading"):
        return [_fold(_inline(node, links), width)]
    if kind in ("fence", "code_block"):
        return [node.content.rstrip("\n")]  # verbatim, never wrapped
    if kind == "bullet_list":
        return [_list(node, width, links, ordered=False)]
    if kind == "ordered_list":
        return [_list(node, width, links, ordered=True)]
    if kind == "blockquote":
        inner = "\n\n".join(_blocks(node, width, links))
        return ["\n".join("> " + ln for ln in inner.split("\n"))]
    if kind == "hr":
        return ["-" * min(width, 70)]
    # Unknown container: recurse into its children.
    return _blocks(node, width, links)


def _blocks(
    node: SyntaxTreeNode, width: int, links: list[tuple[int, str]]
) -> list[str]:
    out: list[str] = []
    for child in node.children:
        out.extend(_blocks_one(child, width, links))
    return out
