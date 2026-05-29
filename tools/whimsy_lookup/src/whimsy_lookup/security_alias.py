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
"""Pure-function lookups against the security-site project-coordinates JSON.

The Glasswing scan-response SKILL was sending replies that CC'd
``security@<pmc>.apache.org`` for every PMC without first verifying the
alias existed. Many PMCs never registered the alias — qmail then
bounced the CC with ``#5.1.1 'Sorry, no mailbox here by that name'``.
Observed bounces so far: Cassandra (2026-05-28), Impala (2026-05-29).

The authoritative source for the alias-mapping is
``apache/security-site:scripts/project-coordinates.json``, whose
``contact`` field is either:

  * ``security@<slug>.apache.org`` — project-scoped alias, safe to CC.
  * ``security@apache.org``        — generic fallback; per-PMC alias
                                     does **not** exist, don't CC it.

A PMC missing from the file altogether has not registered an alias
either; treat as "don't CC".
"""

from __future__ import annotations

from typing import Literal

AliasStatus = Literal["present", "generic", "missing"]


def classify_security_alias(coordinates: dict, slug: str) -> tuple[AliasStatus, str]:
    """Classify a PMC's security@<pmc>.apache.org alias from coordinates.json.

    Returns ``(status, contact)`` where:

      * ``"present"`` — the PMC's coordinates entry has a project-
        scoped ``security@<slug>.apache.org`` contact; the alias
        exists and may be CC'd safely.
      * ``"generic"`` — the PMC's coordinates entry exists but its
        ``contact`` is the foundation-wide ``security@apache.org``;
        no per-PMC alias is registered.
      * ``"missing"`` — the slug has no entry in
        coordinates.json at all; we have no evidence the per-PMC
        alias exists.

    ``contact`` is the raw value from the JSON (``""`` when missing).
    """
    entry = coordinates.get(slug)
    if entry is None:
        return ("missing", "")
    contact = (entry.get("contact") or "").strip().lower()
    expected = f"security@{slug}.apache.org"
    if contact == expected:
        return ("present", contact)
    return ("generic", contact)
