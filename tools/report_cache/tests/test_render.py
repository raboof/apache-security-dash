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

import pytest

from report_cache.index import Entry, Status
from report_cache.render import UnsupportedAttachment, format_size, render_attachment, render_report
from report_cache.report_md import Header


def test_render_text_is_passed_through(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello\nworld\n")
    assert render_attachment(f, "text/plain") == "hello\nworld\n"


def test_render_markdown_is_passed_through(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Title\n")
    assert render_attachment(f, "text/markdown") == "# Title\n"


def test_render_html_becomes_markdown(tmp_path):
    f = tmp_path / "poc.html"
    f.write_text("<h1>Title</h1><p>a <b>bold</b> claim</p>")
    out = render_attachment(f, "text/html")
    assert "Title" in out
    assert "**bold**" in out


def test_render_uses_stdlib_content_type_parser(tmp_path):
    # A charset parameter and odd casing must not defeat the type match; the
    # extension (.bin) is deliberately unhelpful, so only the parsed type routes.
    f = tmp_path / "part.bin"
    f.write_text("<p>hi</p>")
    assert "hi" in render_attachment(f, "TEXT/HTML; charset=utf-8")


def test_render_falls_back_to_extension_when_type_absent(tmp_path):
    f = tmp_path / "poc.html"
    f.write_text("<p>hi</p>")
    assert "hi" in render_attachment(f, None)


def test_render_unsupported_type_raises(tmp_path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"\x00\x01\x02")
    with pytest.raises(UnsupportedAttachment):
        render_attachment(f, "application/octet-stream")


def test_render_pdf_joins_pages(tmp_path, monkeypatch):
    # pypdf's own text extraction is its concern; we only test our routing and
    # the blank-line page join, so a fake reader stands in for it.
    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, _path):
            self.pages = [FakePage("Page one"), FakePage(""), FakePage("Page two")]

    monkeypatch.setattr("report_cache.render.PdfReader", FakeReader)
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    assert render_attachment(f, "application/pdf") == "Page one\n\nPage two"


def test_format_size():
    assert format_size(None) == "0 B"
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(5 * 1024 * 1024) == "5.0 MB"


def test_render_report_merges_metadata_and_body():
    header = Header.from_meta(
        {
            "message_id": "<r@h>",
            "subject": "SSRF in the admin console",
            "date": "Sun, 24 May 2026 06:43:54 +0000",
            "from": "Jane Reporter <jane@example.com>",
            "to": "security@spark.apache.org",
            "attachments": [{"filename": "poc.html", "content_type": "text/html", "size": 2048}],
        }
    )
    entry = Entry(
        path="spark/2026-05-24-ssrf",
        subject="SSRF",
        pmc="spark",
        delivered_pmcs=["spark"],
        security_model_source="https://spark.apache.org/security.html",
        status=Status.DOWNLOADED,
        assessment_model="Claude Opus 4.7",
    )

    out = render_report(header, "The body.\n", entry, ["summary.md"])

    assert "Message-ID: <r@h>" in out
    assert "Date:       2026-05-24" in out
    assert "From:       Jane Reporter <jane@example.com>" in out
    assert "pmc:         spark" in out
    assert "delivered:   spark" in out
    assert "model:       https://spark.apache.org/security.html" in out
    assert "status:      downloaded" in out
    assert "assessed by: Claude Opus 4.7" in out
    assert "attachments: poc.html (text/html, 2.0 KB)" in out
    assert "artifacts:   summary.md" in out
    # metadata block, then a separator, then the verbatim body
    assert out.index("Subject:") < out.index("\n---\n") < out.index("The body.")
    assert out.rstrip().endswith("The body.")


def test_render_report_shows_no_delivery_as_none():
    header = Header.from_meta({"message_id": "<r@h>", "to": "security@apache.org"})
    entry = Entry(path="_unsorted/2026-05-24-x", pmc="spark", status=Status.DOWNLOADED)
    out = render_report(header, "body", entry, [])
    assert "delivered:   (none)" in out
    assert "model:       (none)" in out
