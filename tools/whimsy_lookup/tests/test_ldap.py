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

from __future__ import annotations

from whimsy_lookup.ldap import resolve_ids


def test_resolve_ids_exact_match(ldap_people) -> None:
    people = ldap_people["people"]
    hits = resolve_ids(people, "Jarek Potiuk")
    assert hits == [("potiuk", "Jarek Potiuk")]


def test_resolve_ids_case_insensitive(ldap_people) -> None:
    people = ldap_people["people"]
    assert resolve_ids(people, "jarek potiuk") == [("potiuk", "Jarek Potiuk")]
    assert resolve_ids(people, "JAREK POTIUK") == [("potiuk", "Jarek Potiuk")]


def test_resolve_ids_substring_match(ldap_people) -> None:
    people = ldap_people["people"]
    # Substring "Potiuk" matches Jarek Potiuk.
    hits = resolve_ids(people, "Potiuk")
    assert hits == [("potiuk", "Jarek Potiuk")]


def test_resolve_ids_doris_incident_calvin_kirs(ldap_people) -> None:
    """The 2026-05-21 incident — searching by 'Calvin Kirs' must return
    the right ID (kirs), not a hallucinated one. This is the canonical
    case the helper was built for."""
    people = ldap_people["people"]
    assert resolve_ids(people, "Calvin Kirs") == [("kirs", "Calvin Kirs")]


def test_resolve_ids_cosentino_gmail_localpart_does_not_match(ldap_people) -> None:
    """Andrea Cosentino's Apache ID is `acosentino` (not `ancosen` —
    that's his gmail local-part). A name search must return the
    correct Apache ID, not be confused by the email local-part."""
    people = ldap_people["people"]
    hits = resolve_ids(people, "Andrea Cosentino")
    assert hits == [("acosentino", "Andrea Cosentino")]


def test_resolve_ids_multi_hit_sorted(ldap_people) -> None:
    """Two 'John Doe'-shaped entries must both be returned in
    alphabetical order so the human reviewer sees the disambiguation."""
    people = ldap_people["people"]
    hits = resolve_ids(people, "John Doe")
    assert hits == [
        ("jdoe1", "John Doe"),
        ("jdoe2", "John Doe Jr."),
    ]


def test_resolve_ids_no_match(ldap_people) -> None:
    assert resolve_ids(ldap_people["people"], "Nobody Real") == []


def test_resolve_ids_empty_needle_returns_empty(ldap_people) -> None:
    assert resolve_ids(ldap_people["people"], "") == []
    assert resolve_ids(ldap_people["people"], "   ") == []
