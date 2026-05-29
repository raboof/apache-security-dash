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
"""HTTP fetch helpers + string normalisation.

Kept narrow on purpose: pure functions that consume the fetched JSON live
in ``ldap.py`` and ``committee.py``, so tests for the matching logic don't
need to mock urllib.
"""

from __future__ import annotations

import json
import re
import urllib.request

from whimsy_lookup import (
    COMMITTEE_INFO_URL,
    LDAP_PEOPLE_URL,
    REQ_TIMEOUT_S,
    SECURITY_COORDINATES_URL,
)


class FetchError(Exception):
    """Surface for any network / JSON-parse failure against Whimsy."""

    def __init__(self, url: str, exc: Exception) -> None:
        super().__init__(f"FETCH-ERROR: {url}: {exc}")
        self.url = url
        self.original = exc


def fetch_json(url: str, timeout: float = REQ_TIMEOUT_S) -> dict:
    """Fetch + parse a JSON document over HTTPS.

    Raises FetchError (with the original exception attached) on any
    network or JSON-decode failure so CLI callers can convert it to a
    one-line error message.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return json.load(resp)
    except Exception as exc:  # noqa: BLE001 — single boundary for diagnostics
        raise FetchError(url, exc) from exc


def fetch_ldap_people(timeout: float = REQ_TIMEOUT_S) -> dict:
    """GET the public Whimsy LDAP people JSON dump."""
    return fetch_json(LDAP_PEOPLE_URL, timeout=timeout)


def fetch_committee_info(timeout: float = REQ_TIMEOUT_S) -> dict:
    """GET the public Whimsy committee-info JSON dump."""
    return fetch_json(COMMITTEE_INFO_URL, timeout=timeout)


def fetch_security_coordinates(timeout: float = REQ_TIMEOUT_S) -> dict:
    """GET the apache/security-site project-coordinates.json.

    The file is the authoritative source for whether a PMC has a
    project-scoped ``security@<pmc>.apache.org`` mail alias. Maps
    PMC slug to a small object whose ``contact`` field is either a
    project-scoped alias (``security@<pmc>.apache.org``) or the
    foundation-wide ``security@apache.org`` fallback. PMCs absent
    from the file have not registered an alias.
    """
    return fetch_json(SECURITY_COORDINATES_URL, timeout=timeout)


def normalize_name(s: str) -> str:
    """Lowercase + collapse whitespace; preserves word order.

    LDAP ``name`` fields vary in casing and sometimes include middle
    names or honorifics; loose matching is enough for ``resolve_ids``
    since the caller reviews candidate IDs before acting on them.
    """
    return re.sub(r"\s+", " ", s.strip().lower())
