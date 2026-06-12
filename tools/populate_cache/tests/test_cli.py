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

from populate_cache import cli
from populate_cache.report_md import BUNDLE_FILE
from populate_cache.report_md import read as read_md


def make_msg(
    *,
    to="security@tomcat.apache.org",
    cc="",
    subject="SSRF in the admin console",
    message_id="<report-123@example.com>",
    frm="Jane Reporter <jane@example.com>",
    date="Tue, 27 May 2026 10:00:00 +0000",
    body="Here is the issue.",
):
    raw = (
        f"From: {frm}\r\n"
        f"To: {to}\r\n" + (f"Cc: {cc}\r\n" if cc else "") + f"Subject: {subject}\r\n"
        f"Message-ID: {message_id}\r\n"
        f"Date: {date}\r\n"
        f"\r\n{body}\r\n"
    ).encode()
    return email.message_from_bytes(raw, policy=default), raw


def test_slugify():
    assert cli.slugify("<report-123@example.com>") == "report-123-example.com"
    # No built-in fallback: an empty / all-unsafe input slugs to "" and the
    # caller (write_bundle) supplies a content-hash fallback.
    assert cli.slugify("") == ""
    assert cli.slugify("   ") == ""
    assert cli.slugify("<@>") == ""


def test_clean_header_keeps_printable_ascii():
    assert cli._clean_header("a\x00b\x07c") == "abc"  # control bytes dropped
    assert cli._clean_header("a\u202eb") == "ab"  # bidi override dropped
    assert cli._clean_header("a\u00e9b") == "ab"  # non-ASCII letter dropped
    # Address / message-id punctuation is printable ASCII -> preserved.
    assert cli._clean_header("<id@example.com>") == "<id@example.com>"
    assert cli._clean_header("line1\r\nline2") == "line1 line2"  # fold -> one space
    assert cli._clean_header("a\t\tb   c") == "a b c"  # whitespace runs collapsed
    assert cli._clean_header("a \u00e9 b") == "a b"  # one fold closes the gap left by removal
    assert cli._clean_header("  trim  ") == "trim"
    # Absent header: msg["X"] is None -> "" (caller maps "" to its field default).
    assert cli._clean_header(None) == ""
    assert cli._clean_header("") == ""


def test_safe_attachment_name_strips_path_and_unsafe():
    assert cli.safe_attachment_name("../../etc/passwd", "x") == "passwd"
    assert cli.safe_attachment_name("a b!.txt", "x") == "a_b_.txt"
    assert cli.safe_attachment_name("", "fallback") == "fallback"


def test_write_bundle_tier1_routing(tmp_path):
    msg, raw = make_msg()
    bundle = cli.write_bundle(tmp_path, msg, raw, pmc_slug="tomcat", candidates=["tomcat"])
    rel = bundle.relative_to(tmp_path)
    assert rel.parts[0] == "2026-05-27"
    assert rel.parts[1] == "tomcat"
    assert rel.parts[2] == "report-123-example.com"

    meta, body = read_md(bundle / BUNDLE_FILE)
    assert meta["pmc"] == "tomcat"
    assert meta["pmc_candidates"] == ["tomcat"]
    assert meta["status"] == "downloaded"
    assert meta["keywords"] is None
    assert meta["message_id"] == "<report-123@example.com>"
    assert meta["reporter"] == "jane@example.com"
    assert meta["subject"] == "SSRF in the admin console"
    assert "Here is the issue." in body


def test_write_bundle_saves_raw_message(tmp_path):
    msg, raw = make_msg()
    bundle = cli.write_bundle(tmp_path, msg, raw, pmc_slug="tomcat", candidates=["tomcat"])
    # The verbatim RFC822 bytes are kept alongside report.md as a safety net.
    assert (bundle / "raw.eml").read_bytes() == raw


def test_write_bundle_unparsable_message_id_falls_back_to_hash(tmp_path):
    # A Message-ID of only unsafe chars slugs to "" -> content-hash leaf, never
    # an empty dir name.
    msg, raw = make_msg(message_id="<@>")
    bundle = cli.write_bundle(tmp_path, msg, raw, pmc_slug="tomcat", candidates=["tomcat"])
    assert bundle.name and bundle.name != "tomcat"
    assert (bundle / BUNDLE_FILE).exists()


def test_write_bundle_unsorted_routing(tmp_path):
    msg, raw = make_msg(to="security@apache.org", message_id="<no-pmc@example.com>")
    bundle = cli.write_bundle(tmp_path, msg, raw, pmc_slug=None, candidates=[])
    rel = bundle.relative_to(tmp_path)
    assert rel.parts[1] == cli.UNSORTED

    meta, _ = read_md(bundle / BUNDLE_FILE)
    assert meta["pmc"] is None
    assert meta["pmc_candidates"] is None


def test_write_bundle_records_gmail_labels_as_tags(tmp_path):
    # The message's existing Gmail labels seed the unified `tags` field.
    msg, raw = make_msg()
    bundle = cli.write_bundle(
        tmp_path,
        msg,
        raw,
        pmc_slug="tomcat",
        candidates=["tomcat"],
        tags=["tomcat/2026-05-27 xxe-digester"],
    )
    meta, _ = read_md(bundle / BUNDLE_FILE)
    assert meta["tags"] == ["tomcat/2026-05-27 xxe-digester"]


def test_write_bundle_without_labels_is_none(tmp_path):
    msg, raw = make_msg()
    bundle = cli.write_bundle(tmp_path, msg, raw, pmc_slug="tomcat", candidates=["tomcat"])
    meta, _ = read_md(bundle / BUNDLE_FILE)
    assert meta["tags"] is None


def test_load_seen_message_ids_roundtrip(tmp_path):
    assert cli.load_seen_message_ids(tmp_path) == set()
    msg, raw = make_msg()
    cli.write_bundle(tmp_path, msg, raw, pmc_slug="tomcat", candidates=["tomcat"])
    assert cli.load_seen_message_ids(tmp_path) == {"<report-123@example.com>"}


def test_write_bundle_collision_gets_unique_dir(tmp_path):
    msg, raw = make_msg()
    first = cli.write_bundle(tmp_path, msg, raw, pmc_slug="tomcat", candidates=["tomcat"])
    second = cli.write_bundle(tmp_path, msg, raw, pmc_slug="tomcat", candidates=["tomcat"])
    assert first != second
    assert second.name == f"{first.name}-2"


def test_inbox_message_ids_skips_failed_fetches():
    metadata = {
        "a": {"message_id": "<a@x>"},
        "b": {"message_id": ""},  # failed metadata fetch -> no id
        "c": {},  # ditto
        "d": {"message_id": "<d@x>"},
    }
    assert cli.inbox_message_ids(metadata) == {"<a@x>", "<d@x>"}


def test_reconcile_moves_absent_and_keeps_present(tmp_path):
    present = cli.write_bundle(
        tmp_path, *make_msg(message_id="<still@x>"), pmc_slug="tomcat", candidates=["tomcat"]
    )
    absent = cli.write_bundle(
        tmp_path, *make_msg(message_id="<gone@x>"), pmc_slug="spark", candidates=["spark"]
    )
    rel_absent = absent.relative_to(tmp_path)

    moved = cli.reconcile_handled(tmp_path, {"<still@x>"}, dry_run=False)

    assert moved == [rel_absent]
    assert present.exists()  # still in the inbox -> untouched
    assert not absent.exists()  # left the inbox -> moved
    handled = tmp_path / cli.HANDLED / rel_absent
    assert (handled / BUNDLE_FILE).exists()
    # the moved bundle stays inside the cache, so dedup still sees it
    assert "<gone@x>" in cli.load_seen_message_ids(tmp_path)


def test_reconcile_ignores_handled_and_unkeyed(tmp_path):
    # A bundle already under handled/ is never moved again.
    cli.write_bundle(
        tmp_path / cli.HANDLED, *make_msg(message_id="<old@x>"), pmc_slug="tomcat", candidates=[]
    )
    moved = cli.reconcile_handled(tmp_path, set(), dry_run=False)
    assert moved == []


def test_reconcile_dry_run_moves_nothing(tmp_path):
    bundle = cli.write_bundle(
        tmp_path, *make_msg(message_id="<gone@x>"), pmc_slug="tomcat", candidates=["tomcat"]
    )
    moved = cli.reconcile_handled(tmp_path, set(), dry_run=True)
    assert moved == [bundle.relative_to(tmp_path)]
    assert bundle.exists()  # dry-run reports but does not move
