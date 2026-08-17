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

from datetime import UTC, datetime
from email.headerregistry import Address

import pytest

from report_cache import report_md
from report_cache.report_md import Attachment, Header


def test_round_trip_preserves_meta_and_body(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    meta = {"subject": "S", "pmc": "spark", "status": "downloaded"}
    body = "Line one.\n\nLine two."
    report_md.write_meta(path, meta, body)
    got_meta, got_body = report_md.read_meta(path)
    assert got_meta == meta
    # write() rstrips then re-appends a single trailing newline; the body
    # round-trips modulo that normalisation.
    assert got_body == body + "\n"


def test_write_preserves_field_order(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    report_md.write_meta(path, {"z": 1, "a": 2, "m": 3}, "b")
    text = path.read_text(encoding="utf-8")
    assert text.index("z:") < text.index("a:") < text.index("m:")


def test_read_missing_front_matter_raises(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    path.write_text("no front matter here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing YAML front-matter"):
        report_md.read_meta(path)


def test_read_unclosed_front_matter_raises(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    path.write_text("---\nsubject: S\n\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no closing"):
        report_md.read_meta(path)


def test_read_non_mapping_front_matter_raises(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    path.write_text("---\n- a\n- b\n---\n\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        report_md.read_meta(path)


# --- Header ----------------------------------------------------------------


def test_header_parses_addresses_into_objects():
    header = Header.from_meta(
        {
            "from": "Jane Reporter <jane@example.com>",
            "to": "security@spark.apache.org, security@apache.org",
            "cc": None,
        }
    )
    assert header.from_ == [Address("Jane Reporter", "jane", "example.com")]
    assert [a.addr_spec for a in header.to] == [
        "security@spark.apache.org",
        "security@apache.org",
    ]
    assert header.cc == []


def test_header_from_message_maps_fields():
    import email
    from email.policy import default

    raw = (
        b"From: Jane Reporter <jane@example.com>\r\n"
        b"To: security@spark.apache.org\r\n"
        b"Subject: XXE in the REST API\r\n"
        b"Message-ID: <report-1@example.com>\r\n"
        b"Date: Sun, 24 May 2026 06:43:54 +0200\r\n\r\nbody\r\n"
    )
    message = email.message_from_bytes(raw, policy=default)
    header = Header.from_message(message)
    assert header.message_id == "<report-1@example.com>"
    assert [a.addr_spec for a in header.from_] == ["jane@example.com"]
    assert [a.addr_spec for a in header.to] == ["security@spark.apache.org"]
    assert header.subject == "XXE in the REST API"
    assert header.date == datetime(2026, 5, 24, 4, 43, 54, tzinfo=UTC)
    # gmail_id / labels are not on the message; the caller fills them in.
    assert header.gmail_id is None
    assert header.labels == []


def test_header_from_message_strips_control_chars_keeps_unicode():
    import email
    from email.policy import default

    raw = b"From: jane@example.com\r\nSubject: =?utf-8?q?Jos=C3=A9?=\r\n\r\nbody\r\n"
    message = email.message_from_bytes(raw, policy=default)
    assert Header.from_message(message).subject == "José"


def test_header_normalizes_already_parsed_values():
    # The constructor accepts already-parsed values as well as raw strings.
    addr = Address("Jane", "jane", "example.com")
    header = Header(from_=[addr], date=datetime(2026, 5, 24, 4, 43, 54, tzinfo=UTC))
    assert header.from_ == [addr]
    assert header.date == datetime(2026, 5, 24, 4, 43, 54, tzinfo=UTC)


def test_header_attachments_round_trip(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    original = Header(
        message_id="<m@h>",
        attachments=[Attachment(filename="poc.txt", content_type="text/plain", size=3, hash="abc")],
    )
    report_md.write(path, original, "body")
    loaded, _ = report_md.read(path)
    assert loaded.attachments == [
        Attachment(filename="poc.txt", content_type="text/plain", size=3, hash="abc")
    ]


def test_header_references_split_from_string():
    header = Header.from_meta({"references": "<a@h> <b@h>", "in_reply_to": "<a@h>"})
    assert header.references == ["<a@h>", "<b@h>"]
    assert header.in_reply_to == "<a@h>"


def test_header_to_meta_omits_empty_fields():
    meta = Header(message_id="<m@h>", subject="S").to_meta()
    assert meta == {"message_id": "<m@h>", "subject": "S"}


def test_header_date_rfc_5322_normalised_to_utc():
    header = Header.from_meta({"date": "Sun, 24 May 2026 06:43:54 +0200"})
    assert header.date == datetime(2026, 5, 24, 4, 43, 54, tzinfo=UTC)


def test_header_date_does_not_oscillate_with_timezone():
    # Same instant expressed in two zones must parse to the same UTC datetime.
    plus_two = Header.from_meta({"date": "Sun, 24 May 2026 06:43:54 +0200"})
    utc = Header.from_meta({"date": "Sun, 24 May 2026 04:43:54 +0000"})
    assert plus_two.date == utc.date


def test_header_date_serialises_as_rfc_5322_utc():
    header = Header(date=datetime(2026, 5, 24, 6, 43, 54, tzinfo=UTC))
    assert header.to_meta()["date"] == "Sun, 24 May 2026 06:43:54 +0000"


def test_header_date_round_trips_through_report_md(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    original = Header.from_meta({"date": "Sun, 24 May 2026 06:43:54 +0200"})
    report_md.write(path, original, "body")
    loaded, _ = report_md.read(path)
    assert loaded.date == original.date


def test_header_round_trips_through_report_md(tmp_path):
    path = tmp_path / report_md.BUNDLE_FILE
    original = Header.from_meta(
        {
            "message_id": "<m@h>",
            "subject": "XXE",
            "from": "Jane Reporter <jane@example.com>",
            "to": "security@spark.apache.org",
            "references": "<a@h> <b@h>",
            "labels": ["Inbox"],
            "gmail_id": "18f2c",
        }
    )
    report_md.write(path, original, "the body")
    loaded, body = report_md.read(path)
    assert loaded == original
    assert body == "the body\n"
