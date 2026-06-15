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

from inbox_manager.cli import is_thread_head


def _headers(**fields):
    """Build a header-only email.message.Message, as header_message() returns."""
    raw = "".join(f"{name}: {value}\r\n" for name, value in fields.items())
    return email.message_from_string(raw, policy=default)


def test_gmail_root_is_head():
    # Gmail thread root (msgid == thrid): a head even with References present.
    data = {b"X-GM-MSGID": b"1", b"X-GM-THRID": b"1"}
    headers = _headers(References="<parent@a>")
    assert is_thread_head(data, headers)


def test_no_references_is_head():
    # Fresh mail Gmail merged into an existing thread by subject (msgid != thrid)
    # but carrying no References, e.g. a recurring digest -> head.
    data = {b"X-GM-MSGID": b"2", b"X-GM-THRID": b"1"}
    headers = _headers(Subject="Currently open security reports")
    assert is_thread_head(data, headers)


def test_reply_with_references_is_not_head():
    # A genuine reply: different msgid/thrid *and* a References header -> dropped.
    data = {b"X-GM-MSGID": b"2", b"X-GM-THRID": b"1"}
    headers = _headers(References="<parent@a>")
    assert not is_thread_head(data, headers)


def test_forward_with_references_is_not_head():
    # A forward carries References but often omits In-Reply-To; keying off
    # References (not In-Reply-To) keeps it from being mistaken for a head.
    data = {b"X-GM-MSGID": b"2", b"X-GM-THRID": b"1"}
    headers = _headers(References="<parent@a> <grandparent@a>")
    assert not is_thread_head(data, headers)
