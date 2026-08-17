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

Each bundle in ``report-cache/`` holds a single ``report.md``:
YAML front-matter (the report's metadata) followed by the original plain-text body.
Attachments sit next to it under ``attachments/``.

The format is the Jekyll/Hugo convention::

    ---
    field: value
    ...
    ---

    <report body>

``read()`` / ``write()`` are the primary API: they return / accept a ``Header``,
the structured view of the front-matter - only what Gmail gives us about the message
(addresses, Message-ID, threading, subject, labels, ...),
with the address headers parsed into ``email.headerregistry.Address`` objects.
Triage state the pipeline computes (status, disposition, assigned PMC) is not here;
it lives in ``index.json`` (see ``report_cache.index``).

``read_meta()`` / ``write_meta()`` are the low-level front-matter I/O underneath:
they return / accept the raw ``(meta_dict, body)`` and preserve the field order of ``meta``.
Prefer ``read`` / ``write`` unless you need a key ``Header`` does not model.

This is the canonical implementation for the whole triage pipeline:
the ``report-cache`` CLI, ``populate-cache`` and ``inbox-manager`` all import it
rather than keeping their own copy.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.headerregistry import Address
from email.message import Message
from email.utils import format_datetime, getaddresses, parsedate_to_datetime
from pathlib import Path

import attrs
import yaml

BUNDLE_FILE = "report.md"
DELIM = "---"
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _header_str(value) -> str | None:
    """A header value as one clean line:
    control chars stripped,
    folds/runs of whitespace collapsed to a single space,
    Unicode preserved;
    ``None`` if empty."""
    if value is None:
        return None
    return " ".join(_CONTROL.sub("", str(value)).split()) or None


def write_meta(path: Path, meta: dict, body: str) -> None:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100).rstrip("\n")
    body = (body or "").rstrip("\n")
    path.write_text(f"{DELIM}\n{front}\n{DELIM}\n\n{body}\n", encoding="utf-8")


def read_meta(path: Path) -> tuple[dict, str]:
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


def _parse_addresses(value: list[Address] | Address | str | None) -> list[Address]:
    """RFC 5322 addresses from a header value: a string, or an already-parsed list."""
    if not value:
        return []
    if isinstance(value, Address):
        return [value]
    if isinstance(value, str):
        specs = [value]
    else:
        items = list(value)
        if all(isinstance(item, Address) for item in items):
            return items
        specs = [str(item) for item in items]
    return [
        Address(display_name=name, addr_spec=addr) for name, addr in getaddresses(specs) if addr
    ]


def _parse_references(value: list[str] | str | None) -> list[str]:
    """Message-IDs from a References/In-Reply-To value (whitespace-separated or a list)."""
    if not value:
        return []
    if isinstance(value, str):
        return value.split()
    return [str(v) for v in value]


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    """The RFC 5322 ``Date`` header parsed to a timezone-aware UTC ``datetime``.

    ``report.md`` stores the message's ``Date`` header verbatim ("Sun, 24 May 2026 06:43:54 +0200").
    Reports arrive from every timezone, so the instant is normalized to UTC,
    and the calendar day never oscillates with the sender's offset;
    a naive value (RFC's ``-0000`` "unknown zone") is assumed to be UTC.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_datetime(value: datetime) -> str:
    """The RFC 5322 ``Date`` header for ``value``, normalised to UTC."""
    return format_datetime(value.astimezone(UTC))


def _to_str_list(value: list[str] | None) -> list[str]:
    """A plain list copy; the converter for the ``labels`` field."""
    return list(value or [])


@attrs.define
class Attachment:
    """A file attached to a report, saved under the bundle's ``attachments/``."""

    filename: str
    content_type: str | None = None
    size: int | None = None
    hash: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Attachment:
        known = {f.name for f in attrs.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict:
        return attrs.asdict(self)


def _parse_attachments(value: list[Attachment | dict] | None) -> list[Attachment]:
    """An ``Attachment`` list from already-parsed items or their front-matter dicts."""
    return [a if isinstance(a, Attachment) else Attachment.from_dict(a) for a in (value or [])]


@attrs.define
class Header:
    """The Gmail-derived provenance of a report, the structured view of ``report.md``.

    Each field's ``converter`` normalizes it from its raw header form,
    so the constructor accepts either raw strings or already-parsed values
    while the attribute always reads back as the parsed type:
    the address headers as ``email.headerregistry.Address`` lists,
    ``date`` a UTC ``datetime``,
    ``attachments`` an ``Attachment`` list.
    """

    message_id: str | None = None
    from_: list[Address] = attrs.field(default=None, converter=_parse_addresses)
    sender: list[Address] = attrs.field(default=None, converter=_parse_addresses)
    to: list[Address] = attrs.field(default=None, converter=_parse_addresses)
    cc: list[Address] = attrs.field(default=None, converter=_parse_addresses)
    reply_to: list[Address] = attrs.field(default=None, converter=_parse_addresses)
    in_reply_to: str | None = None
    references: list[str] = attrs.field(default=None, converter=_parse_references)
    subject: str | None = None
    gmail_id: str | None = None
    labels: list[str] = attrs.field(default=None, converter=_to_str_list)
    date: datetime | None = attrs.field(default=None, converter=_parse_datetime)
    attachments: list[Attachment] = attrs.field(default=None, converter=_parse_attachments)

    @classmethod
    def from_meta(cls, meta: dict) -> Header:
        """Build a ``Header`` from a front-matter mapping.

        A plain splat: the constructor normalizes the values and fills defaults for absent keys.
        Only the YAML ``from`` key needs remapping to the ``from_`` field
        (``from`` is a Python keyword).
        """
        return cls(**{"from_" if key == "from" else key: value for key, value in meta.items()})

    @classmethod
    def from_message(cls, message: Message) -> Header:
        """Build a ``Header`` from a parsed ``email.message.Message``.

        Reads the message's own headers
        (RFC 2047 encoded-words already decoded by the parser's policy)
        and lets the constructor do the address parsing / date normalization.
        """
        return cls(
            message_id=_header_str(message["Message-ID"]),
            from_=_header_str(message["From"]),
            sender=_header_str(message["Sender"]),
            to=_header_str(message["To"]),
            cc=_header_str(message["Cc"]),
            reply_to=_header_str(message["Reply-To"]),
            in_reply_to=_header_str(message["In-Reply-To"]),
            references=_header_str(message["References"]),
            subject=_header_str(message["Subject"]),
            date=_header_str(message["Date"]),
        )

    def to_meta(self) -> dict:
        """The front-matter mapping for this header (empty fields omitted)."""
        # The converters have already narrowed each field, so no guards are needed.
        pairs = [
            ("message_id", self.message_id),
            ("subject", self.subject),
            ("from", [str(a) for a in self.from_]),
            ("sender", [str(a) for a in self.sender]),
            ("to", [str(a) for a in self.to]),
            ("cc", [str(a) for a in self.cc]),
            ("reply_to", [str(a) for a in self.reply_to]),
            ("in_reply_to", self.in_reply_to),
            ("references", self.references),
            ("date", _format_datetime(self.date) if self.date else None),
            ("gmail_id", self.gmail_id),
            ("labels", self.labels),
            ("attachments", [a.to_dict() for a in self.attachments]),
        ]
        return {key: value for key, value in pairs if value}


def read(path: Path) -> tuple[Header, str]:
    """Read ``report.md`` and return its ``(Header, body)``."""
    meta, body = read_meta(path)
    return Header.from_meta(meta), body


def write(path: Path, header: Header, body: str) -> None:
    """Serialise ``header`` (and ``body``) to ``report.md``."""
    write_meta(path, header.to_meta(), body)
