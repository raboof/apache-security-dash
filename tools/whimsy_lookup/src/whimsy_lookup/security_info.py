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
      * ``security_model_source`` — where to *read* the model: the raw
                              ``security_model_source`` (e.g. ``SECURITY.md``)
                              when present, else the human page, else ``None``.
                              Feed this to an assessor / WebFetch.
      * ``security_model_link`` — where to *cite* the model to a person: the
                              human ``security_model_link`` page when present,
                              else the raw source, else ``None``. Use this in a
                              PMC-facing or reporter-facing message.
      * ``advisory_link``   — the ``advisory_link`` field, or ``None``.
    """
    entry = coordinates.get(slug) or {}
    contact = (entry.get("contact") or "").strip() or None
    source = entry.get("security_model_source")
    link = entry.get("security_model_link")
    return {
        "slug": slug,
        "known": slug in coordinates,
        "name": entry.get("name") or None,
        "security_contact": contact or "security@apache.org",
        "security_model_source": source or link or None,
        "security_model_link": link or source or None,
        "advisory_link": entry.get("advisory_link") or None,
    }
