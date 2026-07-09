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
from whimsy_lookup.cli import build_parser, main


def test_argparse_routing() -> None:
    args = build_parser().parse_args(["resolve-id", "Calvin Kirs"])
    assert args.cmd == "resolve-id"
    assert args.name == "Calvin Kirs"

    args = build_parser().parse_args(["pmc-info", "hbase"])
    assert args.cmd == "pmc-info"
    assert args.slug == "hbase"

    args = build_parser().parse_args(["check-pmc-member", "hbase", "ndimiduk", "apurtell"])
    assert args.cmd == "check-pmc-member"
    assert args.slug == "hbase"
    assert args.apache_ids == ["ndimiduk", "apurtell"]

    args = build_parser().parse_args(["pmc-security-info", "tomcat"])
    assert args.cmd == "pmc-security-info"
    assert args.slug == "tomcat"
    assert args.json is False

    args = build_parser().parse_args(["pmc-security-info", "tomcat", "--json"])
    assert args.json is True


def test_argparse_check_pmc_member_requires_at_least_one_id() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["check-pmc-member", "hbase"])


def test_resolve_id_prints_hits(mock_urlopen, ldap_people, capsys) -> None:
    mock_urlopen.return_value = urlopen_returning(ldap_people)
    rc = main(["resolve-id", "Calvin Kirs"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "kirs" in out
    assert "Calvin Kirs" in out


def test_resolve_id_no_match_exits_nonzero(mock_urlopen, ldap_people, capsys) -> None:
    mock_urlopen.return_value = urlopen_returning(ldap_people)
    rc = main(["resolve-id", "Nobody Real"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "No Apache ID found" in out


def test_resolve_id_empty_argument_exits_nonzero(mock_urlopen, ldap_people, capsys) -> None:
    mock_urlopen.return_value = urlopen_returning(ldap_people)
    rc = main(["resolve-id", "   "])
    err = capsys.readouterr().err
    assert rc == 1
    assert "Empty name argument" in err


def test_pmc_info_prints_chair_and_roster(mock_urlopen, committee_info, capsys) -> None:
    mock_urlopen.return_value = urlopen_returning(committee_info)
    rc = main(["pmc-info", "hbase"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PMC: hbase" in out
    assert "Chair: ndimiduk" in out
    assert "ndimiduk" in out
    assert "apurtell" in out
    assert "Roster (3)" in out


def test_pmc_info_unknown_slug_exits_one(mock_urlopen, committee_info, capsys) -> None:
    mock_urlopen.return_value = urlopen_returning(committee_info)
    rc = main(["pmc-info", "not-a-real-pmc"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "PMC-NOT-FOUND" in err


def test_pmc_info_transitioning_pmc_shows_unknown_chair(
    mock_urlopen, committee_info, capsys
) -> None:
    mock_urlopen.return_value = urlopen_returning(committee_info)
    rc = main(["pmc-info", "transitioning"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Chair: ?" in out


def test_check_pmc_member_all_present_exits_zero(mock_urlopen, committee_info, capsys) -> None:
    mock_urlopen.return_value = urlopen_returning(committee_info)
    rc = main(["check-pmc-member", "hbase", "ndimiduk", "apurtell"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "YES" in out
    assert "NO" not in out


def test_check_pmc_member_some_missing_exits_one(mock_urlopen, committee_info, capsys) -> None:
    mock_urlopen.return_value = urlopen_returning(committee_info)
    rc = main(["check-pmc-member", "hbase", "ndimiduk", "not-a-member"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "YES" in out
    assert "NO" in out


def test_pmc_security_info_own_contact(mock_urlopen, security_coordinates, capsys) -> None:
    """A PMC with its own alias: security_contact is it; always exits 0."""
    mock_urlopen.return_value = urlopen_returning(security_coordinates)
    rc = main(["pmc-security-info", "tomcat"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "security_contact: security@tomcat.apache.org" in out
    assert (
        "threat_model:     https://raw.githubusercontent.com/apache/tomcat/main/SECURITY.md" in out
    )


def test_pmc_security_info_fallback_contact(mock_urlopen, security_coordinates, capsys) -> None:
    """No own alias (foundation-wide fallback): security_contact resolves to it."""
    mock_urlopen.return_value = urlopen_returning(security_coordinates)
    rc = main(["pmc-security-info", "hop"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "security_contact: security@apache.org" in out


def test_pmc_security_info_missing(mock_urlopen, security_coordinates, capsys) -> None:
    """Slug absent from coordinates: name unknown, security_contact is the fallback."""
    mock_urlopen.return_value = urlopen_returning(security_coordinates)
    rc = main(["pmc-security-info", "cassandra"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "name:             (unknown" in out
    assert "security_contact: security@apache.org" in out


def test_pmc_security_info_json(mock_urlopen, security_coordinates, capsys) -> None:
    import json as _json

    mock_urlopen.return_value = urlopen_returning(security_coordinates)
    rc = main(["pmc-security-info", "tomcat", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    rec = _json.loads(out)
    assert rec["slug"] == "tomcat"
    assert rec["security_contact"] == "security@tomcat.apache.org"
    assert rec["threat_model"] == "https://raw.githubusercontent.com/apache/tomcat/main/SECURITY.md"
    assert "specialized" not in rec
    assert "alias_status" not in rec


def test_fetch_error_exits_two(mock_urlopen, capsys) -> None:
    """FetchError surfaces as a separate exit code from PMCNotFound so
    callers (the SKILL prompt) can distinguish network failures from
    legitimate 'PMC missing' answers."""
    mock_urlopen.return_value = urlopen_failing(http_error_500("https://x"))
    rc = main(["resolve-id", "anyone"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "FETCH-ERROR" in err
