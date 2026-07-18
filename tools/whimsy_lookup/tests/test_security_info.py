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

from whimsy_lookup.security_info import pmc_security_info


def test_pmc_security_info_own_contact(security_coordinates) -> None:
    """A PMC with its own security alias: security_contact is that alias."""
    assert pmc_security_info(security_coordinates, "tomcat") == {
        "slug": "tomcat",
        "known": True,
        "name": "Apache Tomcat",
        "security_contact": "security@tomcat.apache.org",
        "has_own_security_team": True,
        "team_cc": "security@tomcat.apache.org",
        # source-first for reading, page-first for citing.
        "security_model_source": "https://raw.githubusercontent.com/apache/tomcat/main/SECURITY.md",
        "security_model_link": "https://tomcat.apache.org/security.html",
        "advisory_link": None,
    }


def test_security_model_source_and_link_precedence(security_coordinates) -> None:
    """source is model_source-first; link is model_link-first; each falls back."""
    tomcat = pmc_security_info(security_coordinates, "tomcat")
    # tomcat has both: source -> raw SECURITY.md, link -> human page.
    assert (
        tomcat["security_model_source"]
        == "https://raw.githubusercontent.com/apache/tomcat/main/SECURITY.md"
    )
    assert tomcat["security_model_link"] == "https://tomcat.apache.org/security.html"

    # apisix has only security_model_link -> both resolve to it.
    apisix = pmc_security_info(security_coordinates, "apisix")
    page = "https://github.com/apache/apisix/blob/master/THREAT_MODEL.md"
    assert apisix["security_model_source"] == page
    assert apisix["security_model_link"] == page

    # hop has both fields null -> both None.
    hop = pmc_security_info(security_coordinates, "hop")
    assert hop["security_model_source"] is None
    assert hop["security_model_link"] is None


def test_pmc_security_info_generic_fallback(security_coordinates) -> None:
    """A coordinates contact of security@apache.org resolves to that fallback."""
    info = pmc_security_info(security_coordinates, "hop")
    assert info["known"] is True
    assert info["security_contact"] == "security@apache.org"
    assert info["security_model_source"] is None
    assert info["security_model_link"] is None


def test_pmc_security_info_null_contact_falls_back(security_coordinates) -> None:
    """A null contact resolves to the fallback; the model URLs still surface."""
    info = pmc_security_info(security_coordinates, "apisix")
    page = "https://github.com/apache/apisix/blob/master/THREAT_MODEL.md"
    assert info["known"] is True
    assert info["security_contact"] == "security@apache.org"
    assert info["security_model_source"] == page
    assert info["security_model_link"] == page


def test_pmc_security_info_missing_slug(security_coordinates) -> None:
    """A slug absent from coordinates: known False, fallback contact, no extras."""
    assert pmc_security_info(security_coordinates, "cassandra") == {
        "slug": "cassandra",
        "known": False,
        "name": None,
        "security_contact": "security@apache.org",
        "has_own_security_team": False,
        "team_cc": "private@cassandra.apache.org",
        "security_model_source": None,
        "security_model_link": None,
        "advisory_link": None,
    }


def test_pmc_security_info_empty_coordinates() -> None:
    """Defensive: an empty document still yields the fallback contact."""
    info = pmc_security_info({}, "tomcat")
    assert info["known"] is False
    assert info["security_contact"] == "security@apache.org"
    # No coordinates -> no own team -> the PMC's own private@ list is the CC.
    assert info["has_own_security_team"] is False
    assert info["team_cc"] == "private@tomcat.apache.org"


def test_team_cc_own_team_equals_security_contact(security_coordinates) -> None:
    """A PMC with its own alias: team_cc is that alias (== security_contact)."""
    info = pmc_security_info(security_coordinates, "tomcat")
    assert info["has_own_security_team"] is True
    assert info["team_cc"] == "security@tomcat.apache.org"
    assert info["team_cc"] == info["security_contact"]


def test_team_cc_fallback_uses_private_list(security_coordinates) -> None:
    """No own team: team_cc is the PMC private@ list, NOT the foundation contact.

    This is the whole reason team_cc exists — security_contact collapses to the
    foundation-wide security@apache.org here, but the PMC-side channel to CC is
    the project's own private@ list (as done for APISIX).
    """
    hop = pmc_security_info(security_coordinates, "hop")
    assert hop["has_own_security_team"] is False
    assert hop["security_contact"] == "security@apache.org"
    assert hop["team_cc"] == "private@hop.apache.org"


def test_team_cc_null_contact_uses_private_list(security_coordinates) -> None:
    """A null/absent contact classifies as no-own-team -> private@ list."""
    info = pmc_security_info(security_coordinates, "apisix")
    assert info["has_own_security_team"] is False
    assert info["team_cc"] == "private@apisix.apache.org"


def test_team_cc_missing_slug_uses_private_list(security_coordinates) -> None:
    """A slug absent from coordinates still gets a deliverable private@ CC."""
    info = pmc_security_info(security_coordinates, "cassandra")
    assert info["has_own_security_team"] is False
    assert info["team_cc"] == "private@cassandra.apache.org"


def test_team_cc_mixed_case_contact_detects_own_team(security_coordinates) -> None:
    """A mixed-case registered alias still classifies as own-team, canonicalised.

    kafka's fixture contact is ``Security@Kafka.Apache.Org``; detection is
    case-insensitive and team_cc is emitted canonical lowercase.
    """
    info = pmc_security_info(security_coordinates, "kafka")
    assert info["has_own_security_team"] is True
    assert info["team_cc"] == "security@kafka.apache.org"
