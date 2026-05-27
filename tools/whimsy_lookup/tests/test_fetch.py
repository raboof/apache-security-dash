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

import pytest

from tests.conftest import http_error_500, urlopen_failing, urlopen_returning
from whimsy_lookup import COMMITTEE_INFO_URL, LDAP_PEOPLE_URL
from whimsy_lookup.fetch import (
    FetchError,
    fetch_committee_info,
    fetch_json,
    fetch_ldap_people,
    normalize_name,
)


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        ("Andrea Cosentino", "andrea cosentino"),
        ("  Jarek   Potiuk  ", "jarek potiuk"),
        ("Colm O hEigeartaigh", "colm o heigeartaigh"),
        ("\tDuo\tZhang\n", "duo zhang"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_name(inp: str, expected: str) -> None:
    assert normalize_name(inp) == expected


def test_fetch_json_happy_path(mock_urlopen, ldap_people) -> None:
    mock_urlopen.return_value = urlopen_returning(ldap_people)
    assert fetch_json("https://example/x.json") == ldap_people


def test_fetch_json_wraps_network_error(mock_urlopen) -> None:
    mock_urlopen.return_value = urlopen_failing(http_error_500("https://x/y"))
    with pytest.raises(FetchError) as excinfo:
        fetch_json("https://x/y")
    assert "FETCH-ERROR" in str(excinfo.value)
    assert excinfo.value.url == "https://x/y"
    assert isinstance(excinfo.value.original, Exception)


def test_fetch_json_wraps_json_decode_error(mock_urlopen) -> None:
    """Non-JSON response body should also surface as FetchError."""
    from unittest.mock import MagicMock

    response = MagicMock()
    response.read.return_value = b"not json at all <<<<"
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=response)
    cm.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = cm
    with pytest.raises(FetchError):
        fetch_json("https://example/bad.json")


def test_fetch_ldap_people_uses_canonical_url(mock_urlopen, ldap_people) -> None:
    mock_urlopen.return_value = urlopen_returning(ldap_people)
    fetch_ldap_people()
    assert mock_urlopen.call_args.args[0] == LDAP_PEOPLE_URL


def test_fetch_committee_info_uses_canonical_url(mock_urlopen, committee_info) -> None:
    mock_urlopen.return_value = urlopen_returning(committee_info)
    fetch_committee_info()
    assert mock_urlopen.call_args.args[0] == COMMITTEE_INFO_URL
