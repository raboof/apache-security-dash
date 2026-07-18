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

"""Render a report attachment to text for the agent CLI.

The classifying / assessing agent reads reports through ``report-cache``,
so an attachment it needs to consider must come back as text,
never as raw bytes it would have to decode itself.
Four content types are supported
(``text/plain``, ``text/markdown``, ``text/html``, ``application/pdf``);
anything else raises :class:`UnsupportedAttachment`
so the caller can print a short notice instead of dumping binary.

The type is taken from the attachment's recorded content type when present,
falling back to its filename extension
(``populate-cache`` records the content type, but a hand-dropped file may not).
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING

from markdownify import markdownify
from pypdf import PdfReader

if TYPE_CHECKING:
    from email.headerregistry import Address

    from report_cache.index import Entry
    from report_cache.report_md import Header


class UnsupportedAttachment(Exception):
    """The attachment's type has no text rendering; the caller reports it."""

    def __init__(self, content_type: str | None) -> None:
        self.content_type = content_type
        super().__init__(content_type or "unknown type")


# content-type (bare, lower-cased) -> renderer key; extensions cover a missing type.
_BY_TYPE = {
    "text/plain": "text",
    "text/markdown": "text",
    "text/html": "html",
    "application/pdf": "pdf",
}
_BY_EXT = {
    ".txt": "text",
    ".text": "text",
    ".md": "text",
    ".markdown": "text",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
}


def _bare_type(content_type: str | None) -> str | None:
    """The ``maintype/subtype`` of a Content-Type value, params and case stripped.

    Uses the stdlib header parser (``EmailMessage.get_content_type``) rather than hand-splitting;
    ``None`` when no type is recorded, so the caller falls back to the filename extension.
    """
    if not content_type:
        return None
    parsed = EmailMessage()
    parsed["Content-Type"] = content_type
    return parsed.get_content_type()


def _kind(path: Path, content_type: str | None) -> str:
    """The renderer key for ``path``: prefer the declared type, else the extension."""
    kind = _BY_TYPE.get(_bare_type(content_type) or "") or _BY_EXT.get(path.suffix.lower())
    if kind is None:
        raise UnsupportedAttachment(content_type)
    return kind


def render_attachment(path: Path, content_type: str | None = None) -> str:
    """The attachment at ``path`` as text.

    Raises :class:`UnsupportedAttachment` for a type we do not convert,
    and lets the underlying file / parse errors propagate.
    """
    kind = _kind(path, content_type)
    if kind == "text":
        return path.read_text(encoding="utf-8", errors="replace")
    if kind == "html":
        return markdownify(path.read_text(encoding="utf-8", errors="replace")).strip()
    return _pdf_text(path)


def _pdf_text(path: Path) -> str:
    """The extractable text of a PDF, one blank line between pages."""
    reader = PdfReader(str(path))
    pages = (page.extract_text() or "" for page in reader.pages)
    return "\n\n".join(p.strip() for p in pages if p.strip())


def format_size(n: int | None) -> str:
    """A byte count as a short human string (``1.2 KB``)."""
    size = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _addr_line(addresses: list[Address]) -> str:
    """A header address list rendered back to one string, or ``(none)``."""
    return ", ".join(str(a) for a in addresses) if addresses else "(none)"


def render_report(header: Header, body: str, entry: Entry, artifacts: list[str]) -> str:
    """The agent-facing text view of a report: a labeled metadata block, then the body.

    Merges the Gmail provenance (``header``) with the triage state (``entry``),
    so the agent reads one document and never has to parse the storage.
    ``artifacts`` are the bundle's triage-artifact filenames (the caller lists them).
    The body is appended verbatim, since it is the payload the agent reasons over.
    """
    attachments = header.attachments or []
    att_line = (
        ", ".join(
            f"{a.filename} ({a.content_type or '?'}, {format_size(a.size)})" for a in attachments
        )
        if attachments
        else "(none)"
    )
    day = header.date.date().isoformat() if header.date else "-"
    lines = [
        f"Message-ID: {header.message_id or '-'}",
        f"Date:       {day}",
        f"From:       {_addr_line(header.from_)}",
        f"To:         {_addr_line(header.to)}",
        f"Cc:         {_addr_line(header.cc)}",
        f"Subject:    {header.subject or '(none)'}",
        "",
        f"pmc:         {entry.pmc or '-'}",
        f"delivered:   {', '.join(entry.delivered_pmcs) if entry.delivered_pmcs else '(none)'}",
        f"model:       {entry.security_model_source or '(none)'}",
        f"status:      {entry.status}",
        f"disposition: {entry.disposition or '-'}",
        f"assessed by: {entry.assessment_model or '-'}",
        f"reporter:    {entry.reporter_name or '-'}",
        f"labels:      {', '.join(entry.labels) if entry.labels else '(none)'}",
        f"attachments: {att_line}",
        f"artifacts:   {', '.join(artifacts) if artifacts else '(none)'}",
        "",
        "---",
        "",
        body.rstrip("\n"),
    ]
    return "\n".join(lines)
