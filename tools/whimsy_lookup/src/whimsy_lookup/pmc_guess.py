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

The PMC security page link comes from
``apache/security-site:scripts/project-coordinates.json`` (the ``link``
field), the same source ``security_info`` reads — see ``fetch`` for why we
go through the CLI/helper rather than WebFetch on the raw JSON.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from whimsy_lookup.committee import mail_list_of

_ADDR_HOST = re.compile(r"@([a-z0-9][a-z0-9-]*)\.apache\.org", re.IGNORECASE)
_EMAIL = re.compile(r"\S+@\S+")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class Pmc:
    """A guessed PMC:
    its committee id,
    the documented security-page name/link and contact/contributing links
    from project-coordinates.json,
    and the mail_list token from committee-info.

    ``contact`` is the raw project-coordinates value (``None`` when the PMC has no entry).
    """

    id: str
    name: str | None
    security_link: str | None
    contact: str | None
    contributing: str | None
    mail_list: str | None

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
    "http server": "httpd",
    "httpclient": "httpcomponents",
    "httpcore": "httpcomponents",
    "httpasyncclient": "httpcomponents",
}


def slugs_from_addresses(text: str, known_slugs) -> list[str]:
    """apache.org subdomain hosts in ``text`` that are real committee slugs.

    Order-preserving and de-duplicated. Restricting to ``known_slugs`` (the
    committee-info slug set) is what filters out infrastructure subdomains
    like ``lists`` / ``whimsy`` / ``selfserve`` — they simply aren't PMCs.
    """
    known = set(known_slugs)
    out: list[str] = []
    for m in _ADDR_HOST.finditer(text or ""):
        slug = m.group(1).lower()
        if slug in known and slug not in out:
            out.append(slug)
    return out


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

    for slug in slugs_from_addresses(text, known):
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
        entry.get("link"),
        entry.get("contact"),
        entry.get("contributing"),
        mail_list(committees, slug),
    )


def mail_list(committees: dict, slug: str) -> str | None:
    entry = committees.get(slug)
    if not isinstance(entry, dict):
        return None
    return mail_list_of(entry)


def security_link(coordinates: dict, slug: str) -> tuple[str, str] | None:
    """``(display_name, security_page_url)`` for ``slug`` from coordinates.json.

    Returns None if the slug has no coordinates entry or no ``link``. The
    ``link`` is the project's documented security page / security model — the
    page a triager wants when sizing up a report against a PMC.
    """
    entry = coordinates.get(slug)
    if not isinstance(entry, dict):
        return None
    link = entry.get("link")
    if not link:
        return None
    return (entry.get("name") or slug, link)
