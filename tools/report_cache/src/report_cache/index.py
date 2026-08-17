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

"""Read / write ``report-cache/index.json`` - the shared bundle index.

``report.md`` holds only what is already in Gmail (the raw headers + body).
Everything the triage pipeline computes about a report lives here instead,
keyed by the report's RFC ``Message-ID``::

    {
      "<message-id>": {
        "path": "spark/2026-05-24-xxe-rest-api",  # relative to the cache root
        "subject": "...",
        "pmc": "spark",                            # guessed from To/Cc, then classified
        "delivered_pmcs": ["spark"],               # PMCs whose security list received it
        "reporter_name": "Jane Reporter",          # how to address the reporter
        "labels": ["spark/2026-05-24 xxe rest api"],
        "status": "downloaded",                    # lifecycle stage (see Status)
        "disposition": null,                       # e.g. "track", "forward"
        "assessment_model": null,                  # AI model that assessed the report
        "duplicate_ponymail_link": null,           # link to a report this one duplicates
        "security_model_source": null,             # PMC security model, machine-readable (see URL)
        "security_model_link": null                # PMC security model, human-readable page
      },
      ...
    }

Classifying renames a bundle's leaf from its message-id slug to the keyword slug,
so the Message-ID is no longer recoverable from the path;
the index keeps every bundle findable by Message-ID
without scanning every ``report.md``.

The index is the shared state store:
``populate-cache`` (download + dedup),
the ``report-cache`` CLI (labelling / disposition)
and ``inbox-manager`` (send + archive) all read and write it.
``load`` returns each record as an ``Entry``,
so callers reach the fields by attribute (``e.status``, ``e.disposition``, ``e.labels``)
rather than by string key.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import attrs
from whimsy_lookup.pmc_guess import slugs_delivered_from_addresses, slugs_from_domains

from report_cache.report_md import Header

INDEX_FILE = "index.json"  # under the cache root; Message-ID -> bundle record


class URL(str):
    """A validated absolute http(s) URL, stored as its plain string form.

    A ``str`` subclass, so it serializes to JSON as an ordinary string,
    while its construction rejects anything that is not an absolute http(s) URL.
    Entry fields typed ``URL`` are coerced through it by their ``converter``,
    so the same check runs on a fresh value and on one loaded back from ``index.json``.
    """

    __slots__ = ()

    def __new__(cls, value: str) -> URL:
        split = urlsplit(str(value))
        if split.scheme not in ("http", "https") or not split.netloc:
            raise ValueError(f"not an absolute http(s) URL: {value!r}")
        return cast("URL", super().__new__(cls, value))


class Status(StrEnum):
    """A report's lifecycle stage; every bundle starts at ``DOWNLOADED``."""

    DOWNLOADED = "downloaded"  # needs classification (PMC + label)
    CLASSIFIED = "classified"  # needs assessment against the threat model
    ASSESSED = "assessed"  # disposition decided, any drafts written
    FILED = "filed"  # terminal: handled in the Gmail inbox


class Disposition(StrEnum):
    """What the team decided to do about a report (its triage outcome).

    ``track`` / ``forward`` / ``decline`` are handled by the skill; ``skip`` is
    left for a human.
    """

    TRACK = "track"  # the PMC handles it; the team only tracks
    FORWARD = "forward"  # forward to the PMC, receipt to the reporter
    DECLINE = "decline"  # reply to the reporter (false positive / hardening / non-issue)
    SKIP = "skip"  # out of the skill's scope; handle manually (e.g. spam, a digest)


def guess_pmcs(header: Header, committees: dict) -> list[str]:
    """PMC slugs named by a ``<host>.apache.org`` address in the To/Cc headers.

    The guess is only based on the e-mail addresses of the recipients,
    and answers which PMC a report is *meant* for, not where it was delivered.
    """
    domains = (a.domain for a in [*header.to, *header.cc])
    return slugs_from_domains(domains, committees)


def delivered_pmcs(header: Header, committees: dict, coordinates: dict) -> list[str]:
    """PMC slugs a report was actually *delivered* to via its To/Cc recipients.

    Unlike :func:`guess_pmcs` (which only matches a recipient host),
    a PMC counts here only when the correct security list was reached.
    """
    addresses = (a.addr_spec for a in [*header.to, *header.cc])
    return slugs_delivered_from_addresses(addresses, committees, coordinates)


def _to_str_list(value: list[str] | None) -> list[str]:
    """A plain list copy; a missing / ``null`` value becomes an empty list."""
    return list(value or [])


def _to_disposition(value: Disposition | str | None) -> Disposition | None:
    """Coerce to a ``Disposition``; ``None`` stays ``None``, a bad value raises ``ValueError``."""
    return Disposition(value) if value is not None else None


def _to_url(value: URL | str | None) -> URL | None:
    """Coerce to a validated ``URL``; ``None`` stays ``None``, a bad value raises ``ValueError``."""
    return URL(value) if value is not None else None


def _record_value(_inst, _field, value):
    """``attrs.asdict`` serializer: narrow ``StrEnum`` / ``URL`` back to a plain ``str``,
    so a record is ordinary JSON-native types throughout; everything else passes through."""
    if isinstance(value, StrEnum | URL):
        return str(value)
    return value


@attrs.define
class Entry:
    """One index record: where a bundle lives, plus its triage state.

    ``path`` is relative to the cache root.
    ``pmc`` is the project the report should be *assigned* to: seeded from an
    unambiguous To/Cc guess, otherwise left for classification to resolve.
    ``delivered_pmcs`` is where the report was actually *delivered*: the PMCs
    whose security list (its ``security@`` or ``private@`` list, not a bare
    alias) is among the recipients, so a later track-only decision can rest on it.
    ``assessment_model`` names the AI model that assessed the report and wrote
    its summary, so a forward's disclaimer can credit it without an artifact.
    ``duplicate_ponymail_link`` is a Ponymail archive link to an earlier report
    this one duplicates with high confidence, to cite in a forward
    (the duplicated report's label goes in ``labels``, where filing reads it).
    ``security_model_source`` / ``security_model_link`` point at the PMC's
    security model, and are validated as absolute http(s) URLs (see ``URL``).
    """

    path: str
    subject: str | None = None
    pmc: str | None = None
    delivered_pmcs: list[str] = attrs.field(factory=list, converter=_to_str_list)
    reporter_name: str | None = None
    labels: list[str] = attrs.field(factory=list, converter=_to_str_list)
    status: Status = attrs.field(default=Status.DOWNLOADED, converter=Status)
    disposition: Disposition | None = attrs.field(default=None, converter=_to_disposition)
    assessment_model: str | None = None
    duplicate_ponymail_link: URL | None = attrs.field(default=None, converter=_to_url)
    security_model_source: URL | None = attrs.field(default=None, converter=_to_url)
    security_model_link: URL | None = attrs.field(default=None, converter=_to_url)

    @classmethod
    def from_report(
        cls, cache: Path, bundle: Path, header: Header, committees: dict, coordinates: dict
    ) -> Entry:
        """Build the initial record for a freshly downloaded bundle.

        Reads only Gmail-derived data from the ``report.md`` ``Header`` (subject,
        From, To/Cc, labels) and initializes the triage state:
        ``status`` ``Status.DOWNLOADED``,
        no ``disposition`` yet,
        ``pmc`` set only when the To/Cc guess is unambiguous,
        and ``reporter_name`` seeded from the ``From`` display name
        (the skill refines it from the reporter's signature).

        ``pmc`` is the project the report should be *assigned* to based on e-mail addresses,
        not proof of where it was delivered.
        ``delivered_pmcs`` records the latter, and needs the ``coordinates`` to
        tell a real ``security@`` list from a bare alias (see ``delivered_pmcs``).
        """
        pmcs = guess_pmcs(header, committees)
        delivered = delivered_pmcs(header, committees, coordinates)
        reporter_name = header.from_[0].display_name or None if header.from_ else None
        return cls(
            path=str(bundle.relative_to(cache)),
            subject=header.subject,
            pmc=pmcs[0] if len(pmcs) == 1 else None,
            delivered_pmcs=delivered,
            reporter_name=reporter_name,
            labels=header.labels,
            status=Status.DOWNLOADED,
            disposition=None,
        )

    @classmethod
    def from_record(cls, record: dict) -> Entry:
        """Rebuild an ``Entry`` from its ``index.json`` mapping.

        Raises ``TypeError`` if ``record`` is not a mapping,
        and ``ValueError`` if it is one but carries an unknown ``status`` / ``disposition``.
        """
        if not isinstance(record, dict):
            raise TypeError(f"expected a JSON object, got {type(record).__name__}")
        known = {f.name for f in attrs.fields(cls)}
        return cls(**{k: v for k, v in record.items() if k in known})

    def to_record(self) -> dict:
        """The plain-dict form written to ``index.json``.

        Enums and URLs are narrowed back to plain ``str`` (see ``_record_value``).
        """
        return attrs.asdict(self, value_serializer=_record_value)


def load(cache: Path) -> dict[str, Entry]:
    """Load ``index.json`` as ``{message_id: Entry}``; ``{}`` when it does not exist.

    A missing index is ignored;
    a malformed index raises an exception.
    """
    path = cache / INDEX_FILE
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise TypeError(f"{path}: expected a JSON object, got {type(raw).__name__}")
    entries: dict[str, Entry] = {}
    for mid, record in raw.items():
        try:
            entries[mid] = Entry.from_record(record)
        except (TypeError, ValueError) as exc:
            # Re-raise as the same kind, with additional context.
            raise type(exc)(f"{path}: invalid record for {mid!r} ({exc})") from exc
    return entries


def write(cache: Path, index: dict[str, Entry]) -> None:
    """Serialise ``{message_id: Entry}`` to ``index.json`` (sorted keys, trailing newline)."""
    payload = {mid: record.to_record() for mid, record in index.items()}
    (cache / INDEX_FILE).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
