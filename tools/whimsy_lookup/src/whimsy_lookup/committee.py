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
"""Pure functions over the committee-info JSON shape.

Input shape: ``{"committees": {"<slug>": {"chair": {...}, "roster": {...}}, ...}}``.
"""

from __future__ import annotations


class PMCNotFound(Exception):
    """Raised when a PMC slug is not in committee-info.json."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            f"PMC-NOT-FOUND: slug {slug!r} not in committee-info.json. "
            f"(Common misnames: 'logging-services' vs 'logging', "
            f"'<group>-go' split repos belong to the parent PMC, etc.)"
        )
        self.slug = slug


def pmc_entry(committees: dict, slug: str) -> dict:
    """Return the committee-info entry for ``slug``.

    Raises:
        PMCNotFound: if the slug isn't in ``committee-info.json``.
    """
    entry = committees.get(slug)
    if entry is None:
        raise PMCNotFound(slug)
    return entry


def mail_list_of(entry: dict) -> str | None:
    """The committee's ``mail_list`` token, used to derive its mailing lists.

    A PMC's private list is ``private@<mail_list>.apache.org``; the token
    usually equals the slug but differs for some PMCs (e.g. ``httpcomponents``
    has ``mail_list`` ``hc``). Returns None when the field is absent or is
    already a full address (the handful of board committees whose ``mail_list``
    is itself an email) so callers can fall back to the slug.
    """
    ml = entry.get("mail_list")
    if not isinstance(ml, str) or not ml or "@" in ml:
        return None
    return ml


def chair_of(entry: dict) -> tuple[str, str]:
    """Extract (chair_apache_id, chair_name) from a PMC entry.

    Returns ``("?", "?")`` if the structure is unexpected (chairs are
    occasionally missing during transitions).
    """
    chair = entry.get("chair")
    if not isinstance(chair, dict) or not chair:
        return ("?", "?")
    chair_id = next(iter(chair))
    chair_name = chair.get(chair_id, {}).get("name", "?")
    return (chair_id, chair_name)


def check_membership(roster: dict, apache_ids: list[str]) -> dict[str, dict | None]:
    """For each Apache ID, return its roster entry (or None if absent).

    Args:
        roster: the ``"roster"`` sub-dict of a committee-info PMC entry.
        apache_ids: IDs to check.

    Returns:
        Ordered dict (insertion order matches ``apache_ids``) mapping
        each ID to the roster entry dict (with ``name`` / ``date``) or
        None if the ID isn't on the roster.
    """
    return {apache_id: roster.get(apache_id) for apache_id in apache_ids}
