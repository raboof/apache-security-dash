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

"""Deterministic, address-only PMC detection for inbox ingest.

This is the *strong signal* tier of ``whimsy_lookup.pmc_guess`` and nothing
else: a PMC is named only when an ``@<slug>.apache.org`` address appears in the
message recipients (``security@tomcat.apache.org`` -> ``tomcat``), validated
against the authoritative committee-info slug set. Prose-token and product-name
guesses are deliberately *not* applied here - they are heuristics that a small
model resolves later (for bundles the tool drops into ``_unsorted``), so the
tool never misfiles into the canonical tree on a weak signal.

The committee-info slug set is fetched once per run via ``whimsy_lookup``; if
Whimsy is unreachable the set is empty, so every report routes to
``_unsorted`` rather than being misfiled.
"""

from __future__ import annotations

import re

from whimsy_lookup.fetch import FetchError, fetch_committee_info

# An @<slug>.apache.org host. The same pattern whimsy_lookup.pmc_guess uses for
# its address-domain (strong) signal.
_ADDR_HOST = re.compile(r"@([a-z0-9][a-z0-9-]*)\.apache\.org", re.IGNORECASE)

# Committee-info slugs that are not triageable PMCs: the central security team
# itself and the infra pseudo-committee. (``security@apache.org`` resolves to
# host ``apache``, which is not a committee slug, so it is already excluded.)
_NON_PMC = frozenset({"security", "infrastructureadministrator"})


def load_known_slugs() -> set[str]:
    """The authoritative set of triageable PMC slugs from Whimsy committee-info.

    Empty when Whimsy is unreachable so PMC routing degrades to ``_unsorted``
    rather than guessing.
    """
    try:
        committees = fetch_committee_info()
    except FetchError:
        return set()
    return {slug for slug in committees if slug not in _NON_PMC}


def tier1_pmcs(recipients: str, known_slugs: set[str]) -> list[str]:
    """PMC slugs named by an ``@<slug>.apache.org`` address in ``recipients``.

    Order-preserving and de-duplicated; only slugs present in ``known_slugs``
    are returned, so a stray infrastructure subdomain (``lists``, ``whimsy``)
    or a non-existent project never produces a bundle dir. Feed this the To/Cc
    recipients, not From, so a committer reporting from their own
    ``@<pmc>.apache.org`` address does not misfile the report.
    """
    out: list[str] = []
    for match in _ADDR_HOST.finditer(recipients or ""):
        slug = match.group(1).lower()
        if slug in known_slugs and slug not in out:
            out.append(slug)
    return out
