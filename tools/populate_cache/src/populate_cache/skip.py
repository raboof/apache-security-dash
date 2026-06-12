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

"""Header-only skips for thread heads that are never a fresh security report.

These are automated notifications and CVE-process churn, adapted from the
``inbox_manager`` triage tool's ``skip_reason``. Reply detection is handled
upstream by the Gmail thread-head filter (``id == threadId``), so this module
deliberately omits the ``In-Reply-To`` / ``References`` / ``Re:`` rules: those
would also drop a legitimate report that arrives as a reply to a thread not in
this mailbox.
"""

from __future__ import annotations

# Mail injected by the ASF CVE-process system (cveprocess.apache.org) carries
# this host in its Received chain; a CVE reservation/notification is never an
# inbound report.
_AUTOMATION_HOSTS = ("security-vm-he-fi.apache.org",)
# CERT/CC's VINCE platform sends notifications/updates, not fresh reports.
_VINCE_FROM = "cert+donotreply@cert.org"


def skip_reason(info: dict) -> str | None:
    """Why a thread head can be skipped from its headers alone, else None.

    ``info`` is a header bundle as returned by ``gmail.fetch_metadata`` (keys
    ``subject``, ``from``, ``received``). The return value is a short tag used
    for the run funnel.
    """
    subject = info.get("subject") or ""
    sender = (info.get("from") or "").lower()
    received = " ".join(info.get("received") or []).lower()

    if any(host in received for host in _AUTOMATION_HOSTS):
        return "cve-process"
    if _VINCE_FROM in sender:
        return "vince"
    if subject.startswith("svn commit: r"):
        return "svn-commit"
    return None
