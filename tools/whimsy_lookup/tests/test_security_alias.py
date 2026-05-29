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

from whimsy_lookup.security_alias import classify_security_alias


def test_present_alias(security_coordinates) -> None:
    status, contact = classify_security_alias(security_coordinates, "tomcat")
    assert status == "present"
    assert contact == "security@tomcat.apache.org"


def test_generic_fallback_classifies_as_absent(security_coordinates) -> None:
    """Entry exists but contact = security@apache.org → no per-PMC alias."""
    status, contact = classify_security_alias(security_coordinates, "hop")
    assert status == "generic"
    assert contact == "security@apache.org"


def test_null_contact_classifies_as_absent(security_coordinates) -> None:
    """Real coordinates entries sometimes have a null contact field;
    the classifier must treat null the same as 'no per-PMC alias'."""
    status, contact = classify_security_alias(security_coordinates, "apisix")
    assert status == "generic"
    assert contact == ""


def test_missing_slug_classifies_as_absent(security_coordinates) -> None:
    """The Cassandra-style case: the slug isn't in coordinates at all.
    We have no evidence the alias exists — must classify as 'missing'
    (not 'present') so the SKILL doesn't CC."""
    status, contact = classify_security_alias(security_coordinates, "cassandra")
    assert status == "missing"
    assert contact == ""


def test_case_insensitive_alias_match(security_coordinates) -> None:
    """Real coordinates entries are observed lowercase, but if a future
    edit lands a mixed-case ``Security@<Pmc>.Apache.Org`` value the
    classifier should still recognise it as the project-scoped alias
    rather than falling through to 'generic'."""
    status, contact = classify_security_alias(security_coordinates, "kafka")
    assert status == "present"
    assert contact == "security@kafka.apache.org"


def test_empty_coordinates_yields_missing() -> None:
    """Defensive: if the fetch returns an empty document (shouldn't
    happen in practice but a partial-failure could), every slug
    classifies as missing rather than throwing."""
    status, contact = classify_security_alias({}, "tomcat")
    assert status == "missing"
    assert contact == ""
