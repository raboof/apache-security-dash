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
"""Pure functions over the LDAP people JSON shape.

Input shape: ``{"people": {"<apache-id>": {"name": "<full name>", ...}, ...}}``.
"""

from __future__ import annotations

from whimsy_lookup.fetch import normalize_name


def resolve_ids(people: dict, name: str) -> list[tuple[str, str]]:
    """Find Apache IDs whose LDAP ``name`` matches ``name`` (case-insensitive substring).

    Args:
        people: the ``"people"`` sub-dict of ``public_ldap_people.json``.
        name: full or partial name (Apache LDAP names vary; loose match).

    Returns:
        Sorted list of ``(apache_id, ldap_name)`` tuples — empty if no
        match. The caller picks the right one (typically there's exactly
        one; rarely two for common names).
    """
    needle = normalize_name(name)
    if not needle:
        return []
    hits = [
        (apache_id, entry.get("name", ""))
        for apache_id, entry in people.items()
        if needle in normalize_name(entry.get("name", ""))
    ]
    return sorted(hits)
