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
"""Pure-function lookups against the security-site project-coordinates JSON.

:func:`pmc_security_info` is the one-stop lookup the triage pipeline needs:
who to CC for a PMC (``security_contact``) and where its threat model lives.

``security_contact`` always resolves to a deliverable address — the PMC's own
``security@<pmc>.apache.org`` when it has registered one, else the
foundation-wide ``security@apache.org`` fallback. A per-PMC alias never
bounces (where unregistered it just routes to ``security@apache.org``), so a
caller can simply CC ``security_contact`` without branching on whether the PMC
runs its own security team.

The authoritative source is
``apache/security-site:scripts/project-coordinates.json``.
"""

from __future__ import annotations


def pmc_security_info(coordinates: dict, slug: str) -> dict:
    """Security record for a PMC from coordinates.json.

    Who to contact and where the project's threat model lives. A PMC absent
    from coordinates.json yields ``known: False``, the ``security@apache.org``
    fallback contact, and ``None`` for the optional fields.

    Returns a dict with:

      * ``slug``            — the queried slug (echoed back).
      * ``known``           — whether the slug has an entry in coordinates.json.
      * ``name``            — the project's display name, or ``None``.
      * ``security_contact``— the address to CC: the PMC's own
                              ``security@<pmc>.apache.org`` when registered,
                              else the foundation-wide ``security@apache.org``.
      * ``has_own_security_team`` — whether the PMC runs its own security
                              team, i.e. ``contact`` is a project-scoped
                              ``security@<pmc>.apache.org`` alias (case-
                              insensitive) rather than the foundation-wide
                              fallback / absent.
      * ``team_cc``         — the PMC-side channel to CC on a pre-disclosure
                              forward: the PMC's own
                              ``security@<pmc>.apache.org`` when it runs a
                              security team, else its ``private@<pmc>.apache.org``
                              list. Always a deliverable per-PMC address (never
                              the foundation-wide ``security@apache.org``), and
                              always canonical lowercase.
      * ``security_model_source`` — where to *read* the model: the raw
                              ``security_model_source`` (e.g. ``SECURITY.md``)
                              when present, else the human page, else ``None``.
                              Feed this to an assessor / WebFetch.
      * ``security_model_link`` — where to *cite* the model to a person: the
                              human ``security_model_link`` page when present,
                              else the raw source, else ``None``. Use this in a
                              PMC-facing or reporter-facing message.
      * ``advisory_link``   — the ``advisory_link`` field, or ``None``.
      * ``subprojects``     — for a PMC that registers a model per
                              sub-project, the list of
                              ``{name, security_model_source,
                              security_model_link}`` entries that carry one
                              (empty list when there are none).
    """
    entry = coordinates.get(slug) or {}
    contact = (entry.get("contact") or "").strip() or None
    source = entry.get("security_model_source")
    link = entry.get("security_model_link")

    subprojects = [
        {
            "name": sub.get("name"),
            "security_model_source": sub.get("security_model_source"),
            "security_model_link": sub.get("security_model_link"),
        }
        for sub in (entry.get("projects") or [])
    ]

    # The PMC runs its own security team iff its registered contact is a
    # project-scoped ``security@<slug>.apache.org`` alias. Real coordinates
    # entries are lowercase, but a stray mixed-case entry shouldn't defeat
    # detection, so compare case-insensitively. The foundation-wide
    # ``security@apache.org`` fallback (or an absent/null contact) means no own
    # team. ``team_cc`` is the PMC-side channel a pre-disclosure forward should
    # CC: the own security team when there is one, else the PMC's ``private@``
    # list. It differs from ``security_contact`` only in that no-own-team case
    # (``security_contact`` there is the foundation-wide ``security@apache.org``;
    # ``team_cc`` is the PMC's ``private@<slug>``). Both branches are canonical
    # lowercase, so a caller can CC it as-is.
    own_alias = f"security@{slug.lower()}.apache.org"
    has_own_security_team = (contact or "").lower() == own_alias
    team_cc = own_alias if has_own_security_team else f"private@{slug.lower()}.apache.org"

    return {
        "slug": slug,
        "known": slug in coordinates,
        "name": entry.get("name") or None,
        "security_contact": contact or "security@apache.org",
        "has_own_security_team": has_own_security_team,
        "team_cc": team_cc,
        "security_model_source": source or link or None,
        "security_model_link": link or source or None,
        "advisory_link": entry.get("advisory_link") or None,
        "subprojects": subprojects,
    }
