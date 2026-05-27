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
"""Deterministic Apache Whimsy / LDAP lookups for the Glasswing scan
pipeline's identity + PMC-roster gates.

Gates 2 and 3 of ``glasswing-scan-response`` cross-check sender identity
and PMC-roster membership against two public Whimsy JSON files:

  * https://whimsy.apache.org/public/public_ldap_people.json
  * https://whimsy.apache.org/public/committee-info.json

These files are large (several MB) and have been observed to confuse
WebFetch-style summarising readers — they return hallucinated keys,
truncated rosters, or fabricated entries that look plausible but are
wrong. The 2026-05-21 Doris incident (Calvin Kirs) traces back to a
WebFetch summary that drove an unnecessary gate-3 challenge in a
PMC-facing email; this helper would have returned the correct answer.

CLI:

    whimsy-lookup resolve-id "<full name>"
    whimsy-lookup pmc-info <slug>
    whimsy-lookup check-pmc-member <slug> <apache-id> [<apache-id> ...]
"""

__version__ = "0.1.0"

LDAP_PEOPLE_URL = "https://whimsy.apache.org/public/public_ldap_people.json"
COMMITTEE_INFO_URL = "https://whimsy.apache.org/public/committee-info.json"
REQ_TIMEOUT_S = 30
