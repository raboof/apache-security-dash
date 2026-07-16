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

import email
import email.policy

import pytest

from forward_draft.draft import (
    assert_no_inline_html,
    build_mime,
    guess_attachment_type,
)


def _parse(raw: bytes) -> email.message.EmailMessage:
    return email.message_from_bytes(raw, policy=email.policy.default)


def test_guess_attachment_type_known_and_fallback() -> None:
    assert guess_attachment_type("x.zip") == ("application", "zip")
    assert guess_attachment_type("REPORT.MD") == ("text", "markdown")  # case-insensitive
    assert guess_attachment_type("a.json") == ("application", "json")
    assert guess_attachment_type("a.yml") == ("application", "yaml")
    # Unknown extension -> octet-stream (never guesses text/html).
    assert guess_attachment_type("mystery.zzz") == ("application", "octet-stream")


def _mk(tmp_path):
    scan = tmp_path / "apisix-2026-07-15-611487c.zip"
    scan.write_bytes(b"PK\x03\x04 not-a-real-zip but binary \x00\xff payload")
    assess = tmp_path / "assessment.md"
    assess.write_text("# assessment\n\n- VALID: 16\n", encoding="utf-8")
    return scan, assess


def test_build_mime_multipart_mixed_with_attachments(tmp_path) -> None:
    scan, assess = _mk(tmp_path)
    raw = build_mime(
        from_addr="jarek@apache.org",
        to=["alice@apache.org", "bob@apache.org"],
        cc=["security@apache.org", "private@tooling.apache.org"],
        subject="[GLASSWING] ASVS Tooling security scan results Apache APISIX",
        body="Hello team,\n\nAttached is the security scan.\n\nBest,\nJarek\n",
        attachments=[scan, assess],
    )
    msg = _parse(raw)

    assert msg.get_content_type() == "multipart/mixed"
    assert msg["To"] == "alice@apache.org, bob@apache.org"
    assert msg["Cc"] == "security@apache.org, private@tooling.apache.org"
    assert msg["From"] == "jarek@apache.org"
    assert "APISIX" in msg["Subject"]

    parts = list(msg.iter_parts())
    # Body (text/plain) + two attachments.
    body = parts[0]
    assert body.get_content_type() == "text/plain"
    assert "Attached is the security scan." in body.get_content()
    assert body.get_content_disposition() != "attachment"

    by_name = {p.get_filename(): p for p in parts[1:]}
    zip_part = by_name["apisix-2026-07-15-611487c.zip"]
    md_part = by_name["assessment.md"]

    assert zip_part.get_content_type() == "application/zip"
    assert zip_part.get_content_disposition() == "attachment"
    assert zip_part.get_content() == scan.read_bytes()  # binary round-trips

    assert md_part.get_content_type() == "text/markdown"
    assert md_part.get_content_disposition() == "attachment"
    assert "VALID: 16" in md_part.get_content()

    # Each attachment must also carry the legacy Content-Type `name` param
    # (mirroring its filename) so Apple Mail distinguishes them; the body
    # part must not (it isn't an attachment). Without a per-part `name`,
    # Apple Mail collapses different attachments to the same fallback name.
    assert zip_part.get_param("name") == "apisix-2026-07-15-611487c.zip"
    assert md_part.get_param("name") == "assessment.md"
    assert body.get_param("name") is None


def test_build_mime_no_inline_html_and_no_cc_header(tmp_path) -> None:
    scan, assess = _mk(tmp_path)
    raw = build_mime(
        from_addr="jarek@apache.org",
        to=["alice@apache.org"],
        cc=[],
        subject="s",
        body="plain body",
        attachments=[scan, assess],
    )
    msg = _parse(raw)
    # No Cc header when cc is empty.
    assert msg["Cc"] is None
    # No text/html part anywhere in the message.
    assert not any(p.get_content_type() == "text/html" for p in msg.walk())


def test_build_mime_missing_attachment_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        build_mime(
            from_addr="jarek@apache.org",
            to=["alice@apache.org"],
            cc=[],
            subject="s",
            body="b",
            attachments=[tmp_path / "does-not-exist.zip"],
        )


def test_assert_no_inline_html_blocks_inline_but_allows_attachment() -> None:
    # An inline text/html body part is rejected.
    inline = email.message.EmailMessage()
    inline.set_content("plain")
    inline.add_alternative("<p>rich</p>", subtype="html")
    with pytest.raises(ValueError, match="inline text/html"):
        assert_no_inline_html(inline)

    # A text/html *attachment* (Content-Disposition: attachment) is allowed.
    with_att = email.message.EmailMessage()
    with_att.set_content("plain")
    with_att.add_attachment("<p>report</p>", subtype="html", filename="report.html")
    assert_no_inline_html(with_att)  # does not raise
