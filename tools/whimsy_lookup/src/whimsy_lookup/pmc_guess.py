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
"""Best-effort PMC guessing from free text (e.g. an inbound email's headers).

Two signals, strongest first:

  1. ``@<slug>.apache.org`` hosts appearing as email-address domains —
     a report addressed to ``security@tomcat.apache.org`` names its PMC
     unambiguously.
  2. A committee slug appearing as a standalone token (e.g. the word
     "tomcat" in the subject).
  3. A project's descriptive name rather than its slug (e.g. "HTTP Server"
     for ``httpd``) — the weakest signal, ranked last.

Both are validated against the authoritative committee-info slug set so a
stray word that merely *looks* like a slug isn't reported. The result is a
ranked list of candidates the operator reviews — never an automated action.

The PMC security-model URL comes from
``apache/security-site:scripts/project-coordinates.json`` (its
``security_model_source`` field, falling back to ``security_model_link``),
the same source ``security_info`` reads — see ``fetch`` for why we
go through the CLI/helper rather than WebFetch on the raw JSON.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from whimsy_lookup.committee import mail_list_of

# Free-text extraction: the ``<host>.apache.org`` domain of an email address.
_ADDR_DOMAIN = re.compile(r"@([a-z0-9][a-z0-9-]*\.apache\.org)", re.IGNORECASE)
_EMAIL = re.compile(r"\S+@\S+")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class Pmc:
    """A guessed PMC:
    its committee id,
    the documented security-model URLs and contact/contributing links
    from project-coordinates.json,
    and the mail_list token from committee-info.

    Two security-model URLs, because they serve different consumers:

    * ``security_model_source`` — the machine-readable model (the raw
      ``SECURITY.md``) when present, else the human page. Use this to *read*
      the model (WebFetch, feeding an assessor).
    * ``security_model_link`` — the human-readable security page when present,
      else the raw source. Use this to *cite* the model in a message to a
      person (the PMC-facing / reporter-facing email templates).

    Each falls back to the other, so neither is ``None`` when the PMC has at
    least one model URL on record.

    ``contact`` is the raw project-coordinates value (``None`` when the PMC has no entry).

    Some PMCs (``axis``, ``ws``) register one model per sub-project;
    those land in ``subprojects``.
    """

    id: str
    name: str | None
    security_model_source: str | None
    security_model_link: str | None
    contact: str | None
    contributing: str | None
    mail_list: str | None
    subprojects: tuple[dict, ...] = ()

    @property
    def security_contact(self) -> str:
        return self.contact or "security@apache.org"

    @property
    def specialized(self) -> bool:
        return self.security_contact != "security@apache.org"

    @property
    def internal_security_contact(self) -> str:
        """Where the Security team forwards a report for this PMC:
        its own ``security@<pmc>`` when it runs its own security team,
        else its ``private@<pmc>`` list.
        """
        if self.specialized:
            return self.security_contact
        return f"private@{self.mail_list or self.id}.apache.org"


# Product names that don't contain their PMC slug as a token, mapped to it. The
# weakest signal - a project's prose/product name rather than its slug. The
# HttpComponents products (HttpClient/HttpCore/...) share the 'httpcomponents'
# PMC even though none of them tokenises to it.
_NAME_ALIASES = {
    "axiom": "ws",
    "neethi": "ws",
    "woden": "ws",
    "wss4j": "ws",
    "xmlschema": "ws",
    "http server": "httpd",
    "httpclient": "httpcomponents",
    "httpcore": "httpcomponents",
    "httpasyncclient": "httpcomponents",
}


def slugs_from_domains(domains: Iterable[str], committees: dict) -> list[str]:
    """Committee slugs for the ``<host>.apache.org`` mailing-list domains in ``domains``.

    The host is usually the committee slug, but not always:
    HttpComponents takes mail at ``hc.apache.org``,
    so ``hc`` maps to ``httpcomponents``.
    Non-apache.org and unknown hosts are skipped.
    The result preserves input order and is deduplicated.

    The domain form of :func:`slugs_from_addresses`,
    for callers that already hold parsed addresses
    (``email.headerregistry.Address.domain``).
    """
    by_host: dict[str, str] = {}
    for slug, entry in committees.items():
        host = mail_list_of(entry)
        if host:
            by_host.setdefault(host.lower() + ".apache.org", slug)
    out: list[str] = []
    for domain in domains:
        # Domains are case-insensitive;
        # the committee-info hosts are lower-cased.
        slug = by_host.get((domain or "").lower())
        if slug and slug not in out:
            out.append(slug)
    return out


def slugs_delivered_from_addresses(
    addresses: Iterable[str], committees: dict, coordinates: dict
) -> list[str]:
    """Committee slugs a report was actually *delivered* to via ``addresses``.

    :func:`slugs_from_domains` guesses which PMC a report is *meant* for from its recipient hosts,
    while this function checks which PMC security contact was actually reached.

    ``addresses`` are the report's recipient addr-specs (To + Cc).
    Order follows :func:`slugs_from_domains`;
    the result is deduplicated.
    """
    recipients = [a.lower() for a in addresses if a]
    wanted = set(recipients)
    domains = [addr.split("@", 1)[1] for addr in recipients if "@" in addr]
    delivered: list[str] = []
    for slug in slugs_from_domains(domains, committees):
        pmc = pmc_for(slug, committees, coordinates)
        if pmc.internal_security_contact.lower() in wanted:
            delivered.append(slug)
    return delivered


def slugs_from_addresses(text: str, committees: dict) -> list[str]:
    """Committee slugs for the apache.org mailing-list hosts appearing in free ``text``.

    A thin wrapper over :func:`slugs_from_domains`
    for callers holding raw header or prose text rather than parsed addresses
    (an inbound email blob).
    Email addresses in arbitrary text have no reliable grammar,
    so the hosts are extracted with a regex rather than an address parser.
    """
    domains = (m.group(1) for m in _ADDR_DOMAIN.finditer(text or ""))
    return slugs_from_domains(domains, committees)


def guess_pmcs(text: str, committees: dict, coordinates: dict) -> list[Pmc]:
    """Ranked PMC guesses for ``text``, validated against committee-info.

    Address-domain matches (strong signal) come first, in the order they
    appear; standalone-token matches (weaker) follow, sorted for stability.
    Only slugs present in ``committees`` (the committee-info mapping) are
    returned, each built into a full :class:`Pmc` with its security
    coordinates and mail_list token resolved.
    """
    known = set(committees)
    ranked: list[str] = []

    for slug in slugs_from_addresses(text, committees):
        if slug not in ranked:
            ranked.append(slug)

    # Token-match on prose only: strip email addresses first so a mailing
    # list's local part ("security@...") or domain doesn't masquerade as a
    # slug token. Address *hosts* are handled by the strong signal above.
    prose = _EMAIL.sub(" ", text or "").lower()
    tokens = set(_TOKEN.findall(prose))
    for slug in sorted(known & tokens):
        if slug not in ranked:
            ranked.append(slug)

    # Weakest signal: a project's descriptive name (e.g. "HTTP Server") rather
    # than its slug. Appended last so it ranks below the token matches.
    lowered = (text or "").lower()
    for phrase, slug in _NAME_ALIASES.items():
        if phrase in lowered and slug in known and slug not in ranked:
            ranked.append(slug)

    return [pmc_for(slug, committees, coordinates) for slug in ranked]


def pmc_for(slug: str, committees: dict, coordinates: dict) -> Pmc:
    """Build the full :class:`Pmc` for ``slug`` from committee-info + coordinates."""
    entry = coordinates.get(slug)
    if not isinstance(entry, dict):
        entry = {}
    # The raw contact is stored as-is (None when absent); Pmc.security_contact /
    # Pmc.specialized resolve the foundation-wide fallback off it.
    return Pmc(
        slug,
        entry.get("name"),
        # source-first: read/fetch the model
        entry.get("security_model_source") or entry.get("security_model_link"),
        # page-first: cite the model to a person
        entry.get("security_model_link") or entry.get("security_model_source"),
        entry.get("contact"),
        entry.get("contributing"),
        mail_list(committees, slug),
        tuple(
            {
                "name": sub.get("name"),
                "security_model_source": sub.get("security_model_source"),
                "security_model_link": sub.get("security_model_link"),
            }
            for sub in (entry.get("projects") or [])
        ),
    )


def mail_list(committees: dict, slug: str) -> str | None:
    entry = committees.get(slug)
    if not isinstance(entry, dict):
        return None
    return mail_list_of(entry)
