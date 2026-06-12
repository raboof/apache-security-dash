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

from populate_cache.pmc import tier1_pmcs

KNOWN = {"tomcat", "kafka", "httpd"}


def test_address_domain_hit():
    assert tier1_pmcs("security@tomcat.apache.org", KNOWN) == ["tomcat"]


def test_central_list_is_not_a_pmc():
    # host is "apache", which is not a committee slug -> no PMC.
    assert tier1_pmcs("security@apache.org", KNOWN) == []


def test_unknown_subdomain_rejected():
    # Real apache.org host, but "lists" is not a committee slug.
    assert tier1_pmcs("dev@lists.apache.org", KNOWN) == []


def test_slug_not_in_known_set_rejected():
    assert tier1_pmcs("security@solr.apache.org", KNOWN) == []


def test_order_preserving_and_deduplicated():
    text = "a@kafka.apache.org, b@tomcat.apache.org, c@kafka.apache.org"
    assert tier1_pmcs(text, KNOWN) == ["kafka", "tomcat"]


def test_prose_token_is_not_a_match():
    # The weak prose-token signal is deliberately not applied here.
    assert tier1_pmcs("Please review the tomcat issue", KNOWN) == []


def test_empty_known_set_routes_nothing():
    assert tier1_pmcs("security@tomcat.apache.org", set()) == []


def test_blank_recipients():
    assert tier1_pmcs("", KNOWN) == []
    assert tier1_pmcs(None, KNOWN) == []
