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

from report_cache import index
from report_cache.report_md import Header, read_meta

from populate_cache import cli


def make_msg(
    *,
    to="security@tomcat.apache.org",
    cc="",
    subject="SSRF in the admin console",
    message_id="<report-123@example.com>",
    frm="Jane Reporter <jane@example.com>",
    reply_to="",
    date="Tue, 27 May 2026 10:00:00 +0000",
    body="Here is the issue.",
):
    raw = (
        f"From: {frm}\r\n"
        f"To: {to}\r\n"
        + (f"Cc: {cc}\r\n" if cc else "")
        + (f"Reply-To: {reply_to}\r\n" if reply_to else "")
        + f"Subject: {subject}\r\n"
        f"Message-ID: {message_id}\r\n"
        f"Date: {date}\r\n"
        f"\r\n{body}\r\n"
    ).encode()
    return email.message_from_bytes(raw, policy=default), raw


def header_for(msg, *, gmail_id="g1", labels=None):
    """A Header from the message, with the Gmail-API fields filled in (as main does)."""
    header = Header.from_message(msg)
    header.gmail_id = gmail_id
    header.labels = labels
    return header


def download(cache, msg, raw, *, pmc_slug="tomcat", gmail_id="g1", labels=None, known=("tomcat",)):
    """Mimic main()'s per-message step: header -> bundle -> seeded Entry."""
    header = header_for(msg, gmail_id=gmail_id, labels=labels)
    bundle = cli.write_bundle(cache, msg, raw, header=header, pmc_slug=pmc_slug)
    committees = {slug: {"mail_list": slug} for slug in known}
    entry = index.Entry.from_report(cache, bundle, header, committees)
    entry.reporter_name = cli.reporter_name(msg)
    return bundle, header, entry


# --- small helpers ----------------------------------------------------------


def test_slugify():
    assert cli.slugify("<report-123@example.com>") == "report-123-example.com"
    assert cli.slugify("") == ""
    assert cli.slugify("<@>") == ""


def test_clean_header_keeps_printable_ascii():
    assert cli._clean_header("a\x00b\x07c") == "abc"
    assert cli._clean_header("aéb") == "ab"
    assert cli._clean_header("line1\r\nline2") == "line1 line2"
    assert cli._clean_header(None) == ""


def test_safe_attachment_name_strips_path_and_unsafe():
    assert cli.safe_attachment_name("../../etc/passwd", "x") == "passwd"
    assert cli.safe_attachment_name("a b!.txt", "x") == "a_b_.txt"
    assert cli.safe_attachment_name("", "fallback") == "fallback"


# --- write_bundle -----------------------------------------------------------


def test_write_bundle_flat_layout(tmp_path):
    msg, raw = make_msg()
    header = header_for(msg)
    bundle = cli.write_bundle(tmp_path, msg, raw, header=header, pmc_slug="tomcat")
    assert bundle.relative_to(tmp_path).as_posix() == "tomcat/2026-05-27-report-123-example.com"
    assert (bundle / cli.BUNDLE_FILE).exists()


def test_write_bundle_unsorted_routing(tmp_path):
    msg, raw = make_msg(to="security@apache.org", message_id="<no-pmc@example.com>")
    header = header_for(msg)
    bundle = cli.write_bundle(tmp_path, msg, raw, header=header, pmc_slug=None)
    assert bundle.relative_to(tmp_path).parts[0] == cli.UNSORTED


def test_write_bundle_saves_raw_message(tmp_path):
    msg, raw = make_msg()
    header = header_for(msg)
    bundle = cli.write_bundle(tmp_path, msg, raw, header=header, pmc_slug="tomcat")
    assert (bundle / "raw.eml").read_bytes() == raw


def test_write_bundle_unparsable_message_id_falls_back_to_hash(tmp_path):
    msg, raw = make_msg(message_id="<@>")
    header = header_for(msg)
    bundle = cli.write_bundle(tmp_path, msg, raw, header=header, pmc_slug="tomcat")
    assert bundle.name.startswith("2026-05-27-")
    assert (bundle / cli.BUNDLE_FILE).exists()


def test_write_bundle_collision_gets_unique_dir(tmp_path):
    msg, raw = make_msg()
    header = header_for(msg)
    first = cli.write_bundle(tmp_path, msg, raw, header=header, pmc_slug="tomcat")
    second = cli.write_bundle(tmp_path, msg, raw, header=header, pmc_slug="tomcat")
    assert second.name == f"{first.name}-2"


def test_report_md_is_gmail_only(tmp_path):
    msg, raw = make_msg()
    header = header_for(msg, labels=["Inbox"])
    bundle = cli.write_bundle(tmp_path, msg, raw, header=header, pmc_slug="tomcat")
    meta, body = read_meta(bundle / cli.BUNDLE_FILE)
    for triage in ("status", "pmc", "disposition", "keywords", "reporter", "reporter_name"):
        assert triage not in meta
    assert meta["message_id"] == "<report-123@example.com>"
    assert meta["gmail_id"] == "g1"
    assert "Here is the issue." in body


# --- Entry seeding + reporter name -----------------------------------------


def test_download_seeds_downloaded_entry(tmp_path):
    _, _, entry = download(tmp_path, *make_msg(), labels=["Inbox"])
    assert entry.status is index.Status.DOWNLOADED
    assert entry.disposition is None
    assert entry.pmc == "tomcat"
    assert entry.reporter_name == "Jane Reporter"
    assert entry.labels == ["Inbox"]


def test_reporter_name_resolves_via_security_rewrite():
    msg, _ = make_msg(frm="Jane via security <security@apache.org>", reply_to="Jane Real <j@x.com>")
    assert cli.reporter_name(msg) == "Jane Real"


# --- inbox ids + delete-handled ---------------------------------------------


def test_inbox_message_ids_skips_failed_fetches():
    metadata = {
        "a": {"message_id": "<a@x>"},
        "b": {"message_id": ""},
        "c": {},
        "d": {"message_id": "<d@x>"},
    }
    assert cli.inbox_message_ids(metadata) == {"<a@x>", "<d@x>"}


def test_delete_handled_removes_absent_and_empty_parent(tmp_path):
    p_bundle, _, p_entry = download(tmp_path, *make_msg(message_id="<still@x>"), pmc_slug="tomcat")
    a_bundle, _, a_entry = download(
        tmp_path, *make_msg(message_id="<gone@x>"), pmc_slug="spark", known=("spark",)
    )
    idx = {"<still@x>": p_entry, "<gone@x>": a_entry}

    removed = cli.delete_handled(tmp_path, idx, {"<still@x>"}, dry_run=False)

    assert removed == [a_entry.path]
    assert p_bundle.exists()  # still in the inbox
    assert not a_bundle.exists()  # left the inbox -> deleted
    assert "<gone@x>" not in idx
    assert not (tmp_path / "spark").exists()  # empty parent removed
    assert (tmp_path / "tomcat").exists()  # parent with survivors kept


def test_delete_handled_dry_run_deletes_nothing(tmp_path):
    bundle, _, entry = download(tmp_path, *make_msg(message_id="<gone@x>"))
    idx = {"<gone@x>": entry}
    removed = cli.delete_handled(tmp_path, idx, set(), dry_run=True)
    assert removed == [entry.path]
    assert bundle.exists()
    assert "<gone@x>" in idx
