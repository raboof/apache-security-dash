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
"""Template rendering is inbox_manager's job: the triage-assess bundle supplies
only the content values, and these fill_*_template helpers apply the templates
at send time. The tests below pin that single rendering contract - template
selection, marker fill, and the empty-line drop rule."""

from __future__ import annotations

import email
from email.policy import default
from types import SimpleNamespace

import pytest

from inbox_manager import email_utils

TRIAGER = "Jordan Triager"

# Every marker that must never survive into a sent message.
MARKERS = (
    "<PMC name>",
    "<PMC security address>",
    "<Reporter name>",
    "<Triager full name>",
    "<link>",
    "<model link>",
    "<contributing link>",
    "<dashboard link>",
    "<summary>",
    "<reason>",
    "<note>",
    "<model>",
    "<duplicate>",
)


def make_pmc(*, specialized=False, security_model_link="https://demo.apache.org/security"):
    """A stub Pmc with just the attributes the renderer reads.

    The renderer cites the human security page (``security_model_link``), not
    the raw ``security_model_source`` that feeds the assessors.
    """
    return SimpleNamespace(
        id="demo",
        name="Apache Demo",
        specialized=specialized,
        security_contact="security@demo.apache.org" if specialized else "security@apache.org",
        security_model_source="https://raw.githubusercontent.com/apache/demo/main/SECURITY.md",
        security_model_link=security_model_link,
        contributing="https://demo.apache.org/contributing",
    )


def make_message(from_addr="Jane Reporter <jane@example.com>"):
    return email.message_from_string(
        f"From: {from_addr}\nSubject: A report\n\nbody\n", policy=default
    )


def no_markers_left(text):
    return not any(m in text for m in MARKERS)


def test_forward_fills_content_and_infra_markers():
    out = email_utils.fill_forward_template(
        make_pmc(), make_message(), "The flaw is real.", "Claude Opus 4.8", TRIAGER
    )
    assert "The flaw is real." in out
    assert "Claude Opus 4.8" in out  # the AI-disclaimer model line
    assert "https://dash.security.apache.org/project/demo" in out  # dashboard
    assert TRIAGER in out
    assert no_markers_left(out)


def test_forward_duplicate_template_selected_when_duplicate_of_set():
    dup = "https://lists.apache.org/thread/abc"
    out = email_utils.fill_forward_template(
        make_pmc(),
        make_message(),
        "Same as the open one.",
        "Claude Opus 4.8",
        TRIAGER,
        duplicate_of=dup,
    )
    assert dup in out
    assert "duplicate" in out.lower()  # forward-duplicate.md, not forward.md
    assert no_markers_left(out)


def test_receipt_central_vs_specialized():
    central = email_utils.fill_receipt_template(make_pmc(), make_message(), "", TRIAGER)
    assert "passed it on to the appropriate team" in central
    assert no_markers_left(central)

    specialized = email_utils.fill_receipt_template(
        make_pmc(specialized=True), make_message(), "", TRIAGER
    )
    assert "project's own security team" in specialized
    assert "security@demo.apache.org" in specialized  # PMC security address
    assert no_markers_left(specialized)


def test_receipt_note_line_dropped_when_empty_kept_when_present():
    without = email_utils.fill_receipt_template(make_pmc(), make_message(), "", TRIAGER)
    with_note = email_utils.fill_receipt_template(
        make_pmc(), make_message(), "One more thing to check.", TRIAGER
    )
    assert "One more thing to check." in with_note
    assert "One more thing" not in without
    assert no_markers_left(without) and no_markers_left(with_note)


def test_reject_drops_model_link_line_when_pmc_has_none():
    reason = "This is out of the project's security model."
    with_link = email_utils.fill_reject_template(make_pmc(), make_message(), reason, TRIAGER)
    assert reason in with_link
    assert "security model" in with_link  # the [security model](<model link>) line

    without_link = email_utils.fill_reject_template(
        make_pmc(security_model_link=None), make_message(), reason, TRIAGER
    )
    assert reason in without_link  # the reason survives
    assert "See the [security model]" not in without_link  # the link line is gone
    assert no_markers_left(with_link) and no_markers_left(without_link)


@pytest.mark.parametrize(
    "from_addr, greeting",
    [
        ("Jane Reporter <jane@example.com>", "Jane Reporter"),
        # No display name to greet by. The bare address is deliberately not used
        # as a fallback: "Hello jane@example.com," reads worse than "Hello there,".
        ("jane@example.com", "there"),
    ],
)
def test_reporter_greeting_falls_back_to_there(from_addr, greeting):
    out = email_utils.fill_receipt_template(make_pmc(), make_message(from_addr), "", TRIAGER)
    assert f"Hello {greeting}," in out
    assert "jane@example.com" not in out
    assert no_markers_left(out)


def test_text_to_html():
    out = email_utils._html_to_text("""
        def receive_command(self):<br>
            data = self.client.recv(1024).decode().strip()<br>
            print(f"[<] {data}")<br>
            return data<br>
        <br>
        def handle_commands(self):<br>
            parts = cmd.split(' ', 1)<br>
            args = parts[1] if len(parts) > 1 else ""<br>
    """)

    assert (
        out
        == """
        def receive_command(self):
            data = self.client.recv(1024).decode().strip()
            print(f"[<] {data}")
            return data

        def handle_commands(self):
            parts = cmd.split(' ', 1)
            args = parts[1] if len(parts) > 1 else ""
"""
    )
