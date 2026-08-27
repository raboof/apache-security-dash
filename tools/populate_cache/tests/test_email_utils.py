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

import email
from email.policy import default

from populate_cache import email_utils


def _msg(date_header=None):
    head = "From: a@example.com\r\nTo: security@apache.org\r\nSubject: x\r\n"
    if date_header is not None:
        head += f"Date: {date_header}\r\n"
    return email.message_from_bytes((head + "\r\nbody\r\n").encode(), policy=default)


def test_message_date_normalises_to_utc():
    # +0900 just after midnight -> the previous calendar day in UTC.
    assert email_utils.message_date(_msg("Sat, 13 Jun 2026 01:00:00 +0900")) == "2026-06-12"
    # -0500 late evening -> the next calendar day in UTC.
    assert email_utils.message_date(_msg("Fri, 12 Jun 2026 22:00:00 -0500")) == "2026-06-13"
    # already UTC -> unchanged.
    assert email_utils.message_date(_msg("Sat, 13 Jun 2026 12:00:00 +0000")) == "2026-06-13"
    # unknown timezone (-0000) is treated as UTC.
    assert email_utils.message_date(_msg("Sat, 13 Jun 2026 12:00:00 -0000")) == "2026-06-13"


def test_missing_date_falls_back():
    assert email_utils.message_datetime(_msg(None)) is None
    # message_date still returns a yyyy-mm-dd (today, UTC).
    assert len(email_utils.message_date(_msg(None))) == len("2026-06-13")
