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

from whimsy_lookup.pmc_guess import (
    guess_pmcs,
    mail_list,
    pmc_for,
    security_link,
    slugs_from_addresses,
)

# committee-info mapping: most mail_lists equal the slug; httpcomponents is the
# canonical differing case (mail_list 'hc'), brand has a full-address mail_list.
KNOWN = {
    "tomcat": {"mail_list": "tomcat"},
    "kafka": {"mail_list": "kafka"},
    "ant": {"mail_list": "ant"},
    "airflow": {"mail_list": "airflow"},
    "commons": {"mail_list": "commons"},
    "httpcomponents": {"mail_list": "hc"},
    "httpd": {"mail_list": "httpd"},
    "brand": {"mail_list": "trademarks@apache.org"},
}

COORDINATES = {
    "tomcat": {
        "name": "Apache Tomcat",
        "link": "https://tomcat.apache.org/security.html",
        "contact": "security@tomcat.apache.org",
    },
    "kafka": {"name": "Apache Kafka", "link": None, "contact": "security@apache.org"},
    "ant": {"name": "Apache Ant"},
}


def _slugs(pmcs):
    return [p.id for p in pmcs]


def test_slugs_from_addresses_extracts_subdomain():
    text = "To: security@tomcat.apache.org, Cc: dev@kafka.apache.org"
    assert slugs_from_addresses(text, KNOWN) == ["tomcat", "kafka"]


def test_slugs_from_addresses_drops_non_committee_hosts():
    # 'whimsy'/'lists' are real apache.org hosts but not committee slugs.
    text = "From: noreply@whimsy.apache.org via dev@lists.apache.org"
    assert slugs_from_addresses(text, KNOWN) == []


def test_slugs_from_addresses_dedupes_preserving_order():
    text = "tomcat@tomcat.apache.org and users@tomcat.apache.org and x@kafka.apache.org"
    assert slugs_from_addresses(text, KNOWN) == ["tomcat", "kafka"]


def test_guess_prefers_address_over_token():
    # 'ant' appears as a bare token; 'kafka' appears as an address host.
    text = "Subject: an ant problem <x@kafka.apache.org>"
    guesses = guess_pmcs(text, KNOWN, COORDINATES)
    assert guesses[0].id == "kafka"
    assert "ant" in _slugs(guesses)


def test_guess_matches_capitalised_project_name():
    # Real subjects capitalise the project name; matching must be
    # case-insensitive (regression: 'Fory' once tokenised as 'ory').
    known = {**KNOWN, "fory": {"mail_list": "fory"}}
    subj = "Apache Fory C++ SDK — uncontrolled memory allocation in deserialize"
    assert _slugs(guess_pmcs(subj, known, COORDINATES)) == ["fory"]


def test_guess_maps_product_name_to_pmc():
    # HttpClient is a product of the httpcomponents PMC; its name doesn't
    # tokenise to the slug, so the alias map must carry it.
    subj = "Security disclosure — Apache HttpClient 4.5.14: cross-origin redirect leaks headers"
    assert _slugs(guess_pmcs(subj, KNOWN, COORDINATES)) == ["httpcomponents"]


def test_guess_matches_standalone_token_only():
    # 'antics' must NOT match the 'ant' slug (token boundary, not substring).
    assert guess_pmcs("Subject: shenanigans and antics", KNOWN, COORDINATES) == []
    assert _slugs(guess_pmcs("Subject: the ant build", KNOWN, COORDINATES)) == ["ant"]


def test_guess_ignores_slugs_inside_email_addresses():
    # 'ant' is a known slug but here appears only as a mail local part — it
    # must not be token-matched. Addresses are scanned for apache.org *hosts*
    # only (the strong signal), not tokenised for prose matches.
    assert guess_pmcs("Subject: a parser bug\nTo: ant@example.com", KNOWN, COORDINATES) == []


def test_guess_validates_against_known_slugs():
    # 'nonesuch' is a well-formed apache.org host but not a real committee.
    assert guess_pmcs("x@nonesuch.apache.org", KNOWN, COORDINATES) == []


def test_guess_empty_text():
    assert guess_pmcs("", KNOWN, COORDINATES) == []
    assert guess_pmcs(None, KNOWN, COORDINATES) == []


def test_guess_resolves_full_pmc():
    # A guess carries its security coordinates and mail_list token.
    (tomcat,) = guess_pmcs("To: security@tomcat.apache.org", KNOWN, COORDINATES)
    assert tomcat.id == "tomcat"
    assert tomcat.name == "Apache Tomcat"
    assert tomcat.security_link == "https://tomcat.apache.org/security.html"
    assert tomcat.security_contact == "security@tomcat.apache.org"
    assert tomcat.mail_list == "tomcat"


def test_mail_list_present_and_differing():
    assert mail_list(KNOWN, "tomcat") == "tomcat"
    assert mail_list(KNOWN, "httpcomponents") == "hc"  # mail_list differs from slug


def test_mail_list_none_for_address_or_missing():
    assert mail_list(KNOWN, "brand") is None  # full-address mail_list
    assert mail_list(KNOWN, "missing") is None  # no committee entry


def test_pmc_for_drops_generic_contact():
    # The foundation-wide security@apache.org fallback is not a project alias.
    assert pmc_for("kafka", KNOWN, COORDINATES).security_contact is None
    assert pmc_for("tomcat", KNOWN, COORDINATES).security_contact == "security@tomcat.apache.org"


def test_pmc_for_unknown_slug_is_bare():
    pmc = pmc_for("nosuch", KNOWN, COORDINATES)
    assert pmc.id == "nosuch"
    assert pmc.name is None and pmc.security_link is None
    assert pmc.security_contact is None and pmc.contributing is None
    assert pmc.mail_list is None


def test_security_link_present():
    assert security_link(COORDINATES, "tomcat") == (
        "Apache Tomcat",
        "https://tomcat.apache.org/security.html",
    )


def test_security_link_none_when_no_link():
    assert security_link(COORDINATES, "kafka") is None  # link is None
    assert security_link(COORDINATES, "ant") is None  # no link key
    assert security_link(COORDINATES, "missing") is None  # no entry
