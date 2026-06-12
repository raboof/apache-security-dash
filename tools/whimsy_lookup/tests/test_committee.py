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

from whimsy_lookup.committee import (
    PMCNotFound,
    chair_of,
    check_membership,
    mail_list_of,
    pmc_entry,
)


def test_pmc_entry_known_slug(committee_info) -> None:
    entry = pmc_entry(committee_info["committees"], "hbase")
    assert "roster" in entry
    assert "chair" in entry


def test_pmc_entry_unknown_slug_raises(committee_info) -> None:
    with pytest.raises(PMCNotFound) as excinfo:
        pmc_entry(committee_info["committees"], "definitely-not-a-pmc")
    assert excinfo.value.slug == "definitely-not-a-pmc"
    assert "PMC-NOT-FOUND" in str(excinfo.value)


def test_chair_of_hbase(committee_info) -> None:
    entry = committee_info["committees"]["hbase"]
    assert chair_of(entry) == ("ndimiduk", "Nick Dimiduk")


def test_chair_of_transitioning_pmc_returns_unknown(committee_info) -> None:
    """A PMC mid-chair-transition has chair={}; the helper must not
    crash, returning ('?', '?') for the human to investigate."""
    entry = committee_info["committees"]["transitioning"]
    assert chair_of(entry) == ("?", "?")


def test_chair_of_missing_chair_key() -> None:
    """If the entry has no 'chair' key at all."""
    assert chair_of({"roster": {}}) == ("?", "?")


def test_check_membership_all_present(committee_info) -> None:
    roster = committee_info["committees"]["hbase"]["roster"]
    results = check_membership(roster, ["ndimiduk", "apurtell", "zhangduo"])
    assert all(m is not None for m in results.values())
    assert results["ndimiduk"]["name"] == "Nick Dimiduk"


def test_check_membership_some_missing(committee_info) -> None:
    roster = committee_info["committees"]["hbase"]["roster"]
    results = check_membership(roster, ["ndimiduk", "not-a-member"])
    assert results["ndimiduk"] is not None
    assert results["not-a-member"] is None


def test_check_membership_preserves_input_order(committee_info) -> None:
    """The mapping must be ordered like ``apache_ids`` so the CLI
    output prints in the order the caller specified."""
    roster = committee_info["committees"]["hbase"]["roster"]
    results = check_membership(roster, ["zhangduo", "apurtell", "ndimiduk"])
    assert list(results.keys()) == ["zhangduo", "apurtell", "ndimiduk"]


def test_check_membership_empty_id_list(committee_info) -> None:
    roster = committee_info["committees"]["hbase"]["roster"]
    assert check_membership(roster, []) == {}


def test_mail_list_of_bare_token(committee_info) -> None:
    # Usually equals the slug, but httpcomponents' list is 'hc'.
    assert mail_list_of(committee_info["committees"]["hbase"]) == "hbase"
    assert mail_list_of(committee_info["committees"]["httpcomponents"]) == "hc"


def test_mail_list_of_full_address_returns_none(committee_info) -> None:
    # A mail_list that is itself an email (board committees) is unusable for
    # deriving private@<token>.apache.org, so callers fall back to the slug.
    assert mail_list_of(committee_info["committees"]["brand"]) is None


def test_mail_list_of_missing_returns_none() -> None:
    assert mail_list_of({}) is None
