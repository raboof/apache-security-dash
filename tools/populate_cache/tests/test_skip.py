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

from populate_cache.gmail import MessageMeta
from populate_cache.skip import skip_reason


def info(subject="", sender=""):
    return MessageMeta(subject=subject, sender=sender)


def test_cveprocess():
    sender = "cveprocess site <security@apache.org>"
    assert skip_reason(info(sender=sender)) == "cveprocess"


def test_cve_subject_alone_is_not_skipped():
    # CVE-process churn ("Comment added on CVE-...", "is now REVIEW") is caught
    # by the originating host above, not by subject - so a CVE subject without
    # that host (e.g. a human CVE request) is kept.
    assert skip_reason(info(subject="Comment added on CVE-2026-1234")) is None
    assert skip_reason(info(subject="CVE-2026-1234 is now REVIEW")) is None


def test_vince_from():
    assert skip_reason(info(sender="VINCE <cert+donotreply@cert.org>")) == "vince"


def test_svn_commit():
    assert skip_reason(info(subject="svn commit: r1900001 - /dev/foo")) == "svn-commit"


def test_open_reports_digest_is_not_skipped():
    # The team's own "Currently open security reports for/in <pmc>" digest is
    # deliberately NOT skipped: it is downloaded like any head and given the
    # 'digest' disposition by the SKILL (it lists which reports a PMC still has
    # open).
    assert skip_reason(info(subject="Currently open security reports for Doris")) is None
    assert skip_reason(info(subject="Currently open security reports in Guacamole")) is None


def test_real_report_not_skipped():
    real = info(subject="XXE in Foo parser", sender="Jane Reporter <jane@example.com>")
    assert skip_reason(real) is None


def test_orphan_reply_not_skipped():
    # "Re:" and In-Reply-To are NOT skip reasons here - the Gmail thread-head
    # filter owns reply detection, and orphan replies are kept on purpose.
    orphan = info(subject="Re: SSRF in Bar")
    assert skip_reason(orphan) is None
