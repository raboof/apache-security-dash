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
        # security_model_source wins over security_model_link.
        "threat_model": "https://raw.githubusercontent.com/apache/tomcat/main/SECURITY.md",
        "advisory_link": None,
    }


def test_threat_model_prefers_source_falls_back_to_link(security_coordinates) -> None:
    """threat_model is security_model_source, else security_model_link, else None."""
    # tomcat has both -> the source (raw SECURITY.md) is preferred.
    assert (
        pmc_security_info(security_coordinates, "tomcat")["threat_model"]
        == "https://raw.githubusercontent.com/apache/tomcat/main/SECURITY.md"
    )
    # apisix has only security_model_link -> falls back to it.
    assert (
        pmc_security_info(security_coordinates, "apisix")["threat_model"]
        == "https://github.com/apache/apisix/blob/master/THREAT_MODEL.md"
    )
    # hop has both fields null -> None.
    assert pmc_security_info(security_coordinates, "hop")["threat_model"] is None


def test_pmc_security_info_generic_fallback(security_coordinates) -> None:
    """A coordinates contact of security@apache.org resolves to that fallback."""
    info = pmc_security_info(security_coordinates, "hop")
    assert info["known"] is True
    assert info["security_contact"] == "security@apache.org"
    assert info["threat_model"] is None


def test_pmc_security_info_null_contact_falls_back(security_coordinates) -> None:
    """A null contact resolves to the fallback; the threat model still surfaces."""
    info = pmc_security_info(security_coordinates, "apisix")
    assert info["known"] is True
    assert info["security_contact"] == "security@apache.org"
    assert info["threat_model"] == ("https://github.com/apache/apisix/blob/master/THREAT_MODEL.md")


def test_pmc_security_info_missing_slug(security_coordinates) -> None:
    """A slug absent from coordinates: known False, fallback contact, no extras."""
    assert pmc_security_info(security_coordinates, "cassandra") == {
        "slug": "cassandra",
        "known": False,
        "name": None,
        "security_contact": "security@apache.org",
        "threat_model": None,
        "advisory_link": None,
    }


def test_pmc_security_info_empty_coordinates() -> None:
    """Defensive: an empty document still yields the fallback contact."""
    info = pmc_security_info({}, "tomcat")
    assert info["known"] is False
    assert info["security_contact"] == "security@apache.org"
