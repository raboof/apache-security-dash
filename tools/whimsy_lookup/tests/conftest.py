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
"""Shared pytest fixtures + sample Whimsy JSON shapes.

The samples are minimal but structurally faithful to the live Whimsy
JSON. The Andrea Cosentino + Calvin Kirs entries are the canonical
"don't trust WebFetch" cases — both have appeared in PMC-facing
emails where the wrong ID was inferred from a summarised JSON.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

# Sample LDAP people. Andrea Cosentino has Apache ID `acosentino`
# (not `ancosen` — that's his gmail local-part). Calvin Kirs is the
# Doris-incident name; he's `kirs` in LDAP and the Doris PMC.
LDAP_PEOPLE_SAMPLE = {
    "people": {
        "potiuk": {"name": "Jarek Potiuk"},
        "ndimiduk": {"name": "Nick Dimiduk"},
        "apurtell": {"name": "Andrew Purtell"},
        "zhangduo": {"name": "Duo Zhang"},
        "acosentino": {"name": "Andrea Cosentino"},
        "kirs": {"name": "Calvin Kirs"},
        "coheigea": {"name": "Colm O hEigeartaigh"},
        "dkulp": {"name": "Daniel Kulp"},
        # Two people with overlapping names — verifies multi-hit
        # behaviour in resolve_ids.
        "jdoe1": {"name": "John Doe"},
        "jdoe2": {"name": "John Doe Jr."},
    }
}

COMMITTEE_INFO_SAMPLE = {
    "committees": {
        "hbase": {
            "mail_list": "hbase",
            "chair": {"ndimiduk": {"name": "Nick Dimiduk"}},
            "roster": {
                "ndimiduk": {"name": "Nick Dimiduk", "date": "2014-08-10"},
                "apurtell": {"name": "Andrew Purtell", "date": "2010-04-21"},
                "zhangduo": {"name": "Duo Zhang", "date": "2018-03-15"},
            },
        },
        "santuario": {
            "mail_list": "santuario",
            "chair": {"coheigea": {"name": "Colm O hEigeartaigh"}},
            "roster": {
                "coheigea": {
                    "name": "Colm O hEigeartaigh",
                    "date": "2010-05-24",
                },
                "dkulp": {"name": "Daniel Kulp", "date": "2018-10-01"},
            },
        },
        # httpcomponents is the canonical case where mail_list ('hc') differs
        # from the slug; brand has a full-address mail_list (no bare token).
        "httpcomponents": {"mail_list": "hc", "chair": {}, "roster": {}},
        "brand": {"mail_list": "trademarks@apache.org", "chair": {}, "roster": {}},
        # Edge case — chair entry exists but is empty (happens
        # transiently during chair transitions). chair_of() must
        # return ("?", "?") rather than crash.
        "transitioning": {
            "chair": {},
            "roster": {
                "someone": {"name": "Some One", "date": "2024-01-01"},
            },
        },
    }
}


# Sample security-site project-coordinates JSON. Tomcat has a project-
# scoped alias (security@tomcat.apache.org); Cassandra is missing from
# coordinates entirely (security@cassandra just routes to security@apache.org).
# Hop has an entry but ``contact`` is the foundation-wide fallback, which
# means there is no distinct per-PMC list. APISIX is contact-null
# (some entries omit the field entirely) and must classify the same
# way as "generic".
SECURITY_COORDINATES_SAMPLE = {
    # Has both model URLs: threat_model resolves to security_model_source
    # (the raw SECURITY.md), NOT the human-readable security_model_link.
    "tomcat": {
        "name": "Apache Tomcat",
        "security_model_source": "https://raw.githubusercontent.com/apache/tomcat/main/SECURITY.md",
        "security_model_link": "https://tomcat.apache.org/security.html",
        "contact": "security@tomcat.apache.org",
    },
    "hop": {
        "name": "Apache Hop",
        "security_model_source": None,
        "security_model_link": None,
        "contact": "security@apache.org",
    },
    # security_model_source absent: threat_model falls back to
    # security_model_link.
    "apisix": {
        "name": "Apache APISIX",
        "security_model_link": "https://github.com/apache/apisix/blob/master/THREAT_MODEL.md",
        "contact": None,
    },
    # Mixed-case in the JSON (real entries are observed lowercase but
    # the classifier normalises so a stray mixed-case entry shouldn't
    # break detection).
    "kafka": {
        "name": "Apache Kafka",
        "security_model_source": "https://raw.githubusercontent.com/apache/kafka/trunk/SECURITY.md",
        "security_model_link": "https://kafka.apache.org/security",
        "contact": "Security@Kafka.Apache.Org",
    },
}


# Sample public_podlings.json. 'amoro' is still incubating (merged into the
# committee map); 'wave' graduated and 'odftoolkit' retired (both ignored).
PODLINGS_SAMPLE = {
    "podling": {
        "amoro": {"name": "Amoro", "status": "current", "resource": "amoro"},
        "wave": {"name": "Wave", "status": "graduated", "resource": "wave"},
        "odftoolkit": {"name": "ODF Toolkit", "status": "retired", "resource": "odftoolkit"},
    }
}


@pytest.fixture
def ldap_people() -> dict:
    """Sample ``public_ldap_people.json`` payload."""
    return LDAP_PEOPLE_SAMPLE


@pytest.fixture
def podlings() -> dict:
    """Sample ``public_podlings.json`` payload."""
    return PODLINGS_SAMPLE


@pytest.fixture
def committee_info() -> dict:
    """Sample ``committee-info.json`` payload."""
    return COMMITTEE_INFO_SAMPLE


@pytest.fixture
def security_coordinates() -> dict:
    """Sample ``project-coordinates.json`` payload from security-site."""
    return SECURITY_COORDINATES_SAMPLE


@pytest.fixture
def mock_urlopen():
    """Patch urllib.request.urlopen inside whimsy_lookup.fetch."""
    with patch("whimsy_lookup.fetch.urllib.request.urlopen") as m:
        yield m


def urlopen_returning(payload: dict) -> MagicMock:
    """Build a context-manager mock that yields a JSON-able response."""
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=response)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def urlopen_failing(exc: Exception) -> MagicMock:
    """Build a mock whose ``__enter__`` raises ``exc``."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(side_effect=exc)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


__all__ = [
    "COMMITTEE_INFO_SAMPLE",
    "LDAP_PEOPLE_SAMPLE",
    "PODLINGS_SAMPLE",
    "SECURITY_COORDINATES_SAMPLE",
    "committee_info",
    "ldap_people",
    "mock_urlopen",
    "podlings",
    "security_coordinates",
    "urlopen_failing",
    "urlopen_returning",
]


# Re-export an HTTPError builder for tests that need to exercise the
# urllib failure path.
def http_error_500(url: str) -> urllib.error.HTTPError:
    import io

    return urllib.error.HTTPError(
        url=url, code=500, msg="Server Error", hdrs=None, fp=io.BytesIO(b"")
    )
