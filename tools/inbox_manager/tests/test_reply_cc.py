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
"""Replies leave through the relay unmoderated, so a public list a reporter
Cc'ed must never survive into one. The tests below pin that filter."""

from __future__ import annotations

import email
from email.policy import default

import pytest

from inbox_manager import email_utils


def make_message(cc):
    """A report from a reporter, Cc'ing `cc`."""
    return email.message_from_string(
        "From: Jane Reporter <jane@example.com>\n"
        "To: security@apache.org\n"
        f"Cc: {cc}\n"
        "Subject: A report\n\nbody\n",
        policy=default,
    )


@pytest.mark.parametrize(
    "addr",
    [
        "dev@demo.apache.org",  # project lists all live on a subdomain
        "user@demo.apache.org",
        "users@demo.apache.org",
        "commits@demo.apache.org",
        "Demo Dev <dev@demo.apache.org>",  # display name doesn't hide it
        "DEV@Demo.Apache.Org",  # nor does casing
        "dev+tag@demo.apache.org",  # nor plus-addressing
        "general@incubator.apache.org",
        "announce@apache.org",  # foundation-wide public list
    ],
)
def test_public_lists_recognised(addr):
    assert email_utils.is_public_list(addr)


@pytest.mark.parametrize(
    "addr",
    [
        "private@demo.apache.org",  # the PMC's own private list
        "security@demo.apache.org",  # its security alias
        "security@apache.org",
        "jane@example.com",
        "dev@example.com",  # a non-ASF list is not recognisable, so kept
        "someid@apache.org",  # a committer's personal address
        "",
    ],
)
def test_non_public_recipients_kept(addr):
    assert not email_utils.is_public_list(addr)


def test_reply_drops_public_list_and_keeps_the_rest():
    original = make_message(
        "Demo Dev <dev@demo.apache.org>, Co Reporter <co@example.com>, "
        "private@demo.apache.org"
    )
    reply = email_utils.make_receipt(original, "Thanks for the report.")
    assert "dev@demo.apache.org" not in reply["Cc"]
    assert "co@example.com" in reply["Cc"]
    assert "private@demo.apache.org" in reply["Cc"]
    assert "Co Reporter" in reply["Cc"]  # display names survive the filter


def test_reply_has_no_cc_when_only_public_lists_were_copied():
    original = make_message("dev@demo.apache.org, user@demo.apache.org")
    reject = email_utils.make_reject(original, "This is not a vulnerability.")
    assert reject["Cc"] is None
    assert reject["To"] == "Jane Reporter <jane@example.com>"
