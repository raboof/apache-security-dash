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

import io

import pytest

from report_cache import cli, index
from report_cache.index import Disposition, Entry, Status
from report_cache.report_md import BUNDLE_FILE, Header


def make_bundle(
    cache, *, date="2026-05-24", pmc="spark", slug="msgid-abc", mid="<abc@host>", **hdr
):
    """Create a downloaded bundle on disk + its index entry; return (mid, leaf)."""
    bundle = cache / date / pmc / slug
    (bundle / "attachments").mkdir(parents=True)
    header = Header.from_meta(
        {
            "message_id": mid,
            "subject": "XXE in the REST API",
            "date": "Sun, 24 May 2026 06:43:54 +0000",
            "to": f"security@{pmc}.apache.org",
            "labels": ["Inbox"],
            **hdr,
        }
    )
    from report_cache.report_md import write as write_report

    write_report(bundle / BUNDLE_FILE, header, "The report body.")
    idx = index.load(cache)
    idx[mid] = Entry.from_report(cache, bundle, header, {pmc: {"mail_list": pmc}}, {})
    index.write(cache, idx)
    return mid, slug


def entry_for(cache, mid):
    return index.load(cache)[mid]


# --- find -------------------------------------------------------------------


def test_find_entry_by_leaf_and_message_id(tmp_path):
    mid, _ = make_bundle(tmp_path)
    idx = index.load(tmp_path)
    assert cli.find_entry(idx, "msgid-abc")[0] == mid
    assert cli.find_entry(idx, "<abc@host>")[0] == mid
    assert cli.find_entry(idx, "msgid")[0] == mid  # unique prefix


def test_find_entry_unknown_raises(tmp_path):
    make_bundle(tmp_path)
    with pytest.raises(SystemExit, match="No index entry"):
        cli.find_entry(index.load(tmp_path), "nope")


# --- move -------------------------------------------------------------------


def test_move_relocates_and_updates_index(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_move(tmp_path, _ns(id="msgid-abc", pmc="spark", keywords="xxe rest api"))

    target = tmp_path / "spark" / "2026-05-24-xxe-rest-api"
    assert target.is_dir()
    assert not (tmp_path / "2026-05-24" / "spark" / "msgid-abc").exists()
    assert entry_for(tmp_path, mid).path == "spark/2026-05-24-xxe-rest-api"


def test_move_uses_slug_over_keywords(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_move(tmp_path, _ns(id="msgid-abc", pmc="hadoop", slug="aaa-dependencies"))
    assert (tmp_path / "hadoop" / "2026-05-24-aaa-dependencies").is_dir()
    assert entry_for(tmp_path, mid).path == "hadoop/2026-05-24-aaa-dependencies"
    assert entry_for(tmp_path, mid).pmc == "hadoop"


def test_move_resolves_slug_collisions(tmp_path):
    make_bundle(tmp_path, slug="msgid-abc", mid="<a@h>")
    make_bundle(tmp_path, slug="msgid-def", mid="<b@h>")
    cli.cmd_move(tmp_path, _ns(id="<a@h>", pmc="spark", keywords="xxe"))
    cli.cmd_move(tmp_path, _ns(id="<b@h>", pmc="spark", keywords="xxe"))
    assert entry_for(tmp_path, "<a@h>").path == "spark/2026-05-24-xxe"
    assert entry_for(tmp_path, "<b@h>").path == "spark/2026-05-24-xxe-2"


# --- set --------------------------------------------------------------------


def test_set_status_and_disposition(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(tmp_path, _ns(id="msgid-abc", status="classified", disposition="track"))
    stored = entry_for(tmp_path, mid)
    assert stored.status is Status.CLASSIFIED
    assert stored.disposition is Disposition.TRACK


def test_set_composes_label(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(tmp_path, _ns(id="msgid-abc", pmc="spark", keywords="xxe rest api"))
    assert "spark/2026-05-24 xxe rest api" in entry_for(tmp_path, mid).labels


def test_set_composes_collection_label_without_date_key(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(
        tmp_path,
        _ns(id="msgid-abc", collection="zzz-non-issue", pmc="hadoop", keywords="aaa_dependencies"),
    )
    assert "zzz-non-issue/hadoop/aaa_dependencies" in entry_for(tmp_path, mid).labels


def test_set_composes_label_with_cve_and_waiting_for(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(
        tmp_path,
        _ns(
            id="msgid-abc", pmc="spark", keywords="deser", cve="CVE-2026-1", waiting_for="reporter"
        ),
    )
    assert "spark/CVE-2026-1 deser wf reporter" in entry_for(tmp_path, mid).labels


def test_set_add_and_remove_label(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(tmp_path, _ns(id="msgid-abc", add_label=["Inbox", "manual"]))
    cli.cmd_set(tmp_path, _ns(id="msgid-abc", remove_label=["Inbox"]))
    labels = entry_for(tmp_path, mid).labels
    assert "manual" in labels
    assert "Inbox" not in labels


def test_set_rejects_unknown_status(tmp_path):
    make_bundle(tmp_path)
    with pytest.raises(ValueError):
        cli.cmd_set(tmp_path, _ns(id="msgid-abc", status="bogus"))


def test_set_rejects_unknown_disposition(tmp_path):
    make_bundle(tmp_path)
    with pytest.raises(ValueError):
        cli.cmd_set(tmp_path, _ns(id="msgid-abc", disposition="bogus"))


def test_set_reporter_name(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(tmp_path, _ns(id="msgid-abc", reporter_name="Jane"))
    assert entry_for(tmp_path, mid).reporter_name == "Jane"


def test_set_assessment_model(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(tmp_path, _ns(id="msgid-abc", assessment_model="Claude Opus 4.7"))
    assert entry_for(tmp_path, mid).assessment_model == "Claude Opus 4.7"


def test_set_duplicate_ponymail_link(tmp_path):
    mid, _ = make_bundle(tmp_path)
    link = "https://lists.apache.org/thread/abc123"
    cli.cmd_set(tmp_path, _ns(id="msgid-abc", duplicate_ponymail_link=link))
    assert entry_for(tmp_path, mid).duplicate_ponymail_link == link


def test_set_rejects_a_non_http_duplicate_ponymail_link(tmp_path):
    make_bundle(tmp_path)
    with pytest.raises(ValueError, match="absolute http"):
        cli.cmd_set(tmp_path, _ns(id="msgid-abc", duplicate_ponymail_link="not a url"))


def test_set_security_model_urls(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_set(
        tmp_path,
        _ns(
            id="msgid-abc",
            security_model_source="https://raw.githubusercontent.com/apache/spark/master/SECURITY.md",
            security_model_link="https://spark.apache.org/security.html",
        ),
    )
    stored = entry_for(tmp_path, mid)
    assert (
        stored.security_model_source
        == "https://raw.githubusercontent.com/apache/spark/master/SECURITY.md"
    )
    assert stored.security_model_link == "https://spark.apache.org/security.html"


def test_set_rejects_a_non_http_security_model_url(tmp_path):
    make_bundle(tmp_path)
    with pytest.raises(ValueError, match="absolute http"):
        cli.cmd_set(tmp_path, _ns(id="msgid-abc", security_model_link="not a url"))


# --- classify ---------------------------------------------------------------


def test_classify_moves_labels_and_defaults_to_classified(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_classify(tmp_path, _ns(id="msgid-abc", pmc="spark", keywords="xxe rest api"))
    stored = entry_for(tmp_path, mid)
    assert stored.path == "spark/2026-05-24-xxe-rest-api"
    assert stored.status is Status.CLASSIFIED
    assert stored.disposition is None
    assert "spark/2026-05-24 xxe rest api" in stored.labels
    assert (tmp_path / "spark" / "2026-05-24-xxe-rest-api" / BUNDLE_FILE).exists()


def test_classify_track_only_shortcuts_to_assessed(tmp_path):
    mid, _ = make_bundle(tmp_path)
    cli.cmd_classify(tmp_path, _ns(id="msgid-abc", pmc="spark", keywords="xxe", track_only=True))
    stored = entry_for(tmp_path, mid)
    assert stored.status is Status.ASSESSED
    assert stored.disposition is Disposition.TRACK


def test_classify_leaves_report_md_gmail_only(tmp_path):
    make_bundle(tmp_path)
    cli.cmd_classify(tmp_path, _ns(id="msgid-abc", pmc="spark", keywords="xxe"))
    from report_cache.report_md import read_meta

    meta, _ = read_meta(tmp_path / "spark" / "2026-05-24-xxe" / BUNDLE_FILE)
    assert "status" not in meta
    assert "disposition" not in meta
    assert "pmc" not in meta


def _ns(**over):
    """An argparse-like namespace with every option the commands read defaulted."""
    defaults = {
        "id": None,
        "pmc": None,
        "keywords": None,
        "slug": None,
        "collection": None,
        "status": None,
        "disposition": None,
        "reporter_name": None,
        "assessment_model": None,
        "duplicate_ponymail_link": None,
        "security_model_source": None,
        "security_model_link": None,
        "cve": None,
        "waiting_for": None,
        "track_only": False,
        "add_label": [],
        "remove_label": [],
        "name": None,
        "from_file": None,
    }
    defaults.update(over)
    return type("Args", (), defaults)()


def bundle_dir_of(cache, mid):
    return cache / index.load(cache)[mid].path


# --- list -------------------------------------------------------------------


def test_list_filters_by_status(tmp_path, capsys):
    make_bundle(tmp_path, mid="<a@h>", slug="downloaded-a")
    make_bundle(tmp_path, mid="<b@h>", slug="downloaded-b")
    cli.cmd_classify(tmp_path, _ns(id="<a@h>", pmc="spark", keywords="xxe"))  # leaves 'downloaded'
    capsys.readouterr()  # drop the classify move message

    cli.cmd_list(tmp_path, _ns(status="downloaded"))
    out = capsys.readouterr().out
    assert "downloaded-b" in out
    assert "downloaded-a" not in out  # now classified, filtered out
    assert "2026-05-24-xxe" not in out


def test_list_empty_is_reported(tmp_path, capsys):
    cli.cmd_list(tmp_path, _ns(status=None))
    assert "no matching bundles" in capsys.readouterr().out


# --- show -------------------------------------------------------------------


def test_show_renders_metadata_and_body(tmp_path, capsys):
    make_bundle(tmp_path, mid="<s@h>", slug="showme")
    cli.cmd_show(tmp_path, _ns(id="showme"))
    out = capsys.readouterr().out
    assert "Message-ID: <s@h>" in out
    assert "Subject:    XXE in the REST API" in out
    assert "pmc:         spark" in out
    assert "status:      downloaded" in out
    assert "artifacts:   (none)" in out
    assert "The report body." in out


def test_show_lists_attachments_and_artifacts(tmp_path, capsys):
    make_bundle(
        tmp_path,
        mid="<s2@h>",
        slug="s2",
        attachments=[{"filename": "poc.html", "content_type": "text/html", "size": 20}],
    )
    bundle = bundle_dir_of(tmp_path, "<s2@h>")
    (bundle / "attachments" / "poc.html").write_text("<p>x</p>")
    (bundle / "summary.md").write_text("summary")

    cli.cmd_show(tmp_path, _ns(id="s2"))
    out = capsys.readouterr().out
    assert "poc.html (text/html, 20 B)" in out
    assert "artifacts:   summary.md" in out


# --- get-attachment ---------------------------------------------------------


def test_get_attachment_renders_html(tmp_path, capsys):
    make_bundle(
        tmp_path,
        mid="<g@h>",
        slug="g",
        attachments=[{"filename": "poc.html", "content_type": "text/html", "size": 11}],
    )
    (bundle_dir_of(tmp_path, "<g@h>") / "attachments" / "poc.html").write_text("<h1>Hi</h1>")
    cli.cmd_get_attachment(tmp_path, _ns(id="g", name="poc.html"))
    assert "Hi" in capsys.readouterr().out


def test_get_attachment_unsupported_prints_notice(tmp_path, capsys):
    make_bundle(
        tmp_path,
        mid="<u@h>",
        slug="u",
        attachments=[
            {"filename": "blob.bin", "content_type": "application/octet-stream", "size": 3}
        ],
    )
    (bundle_dir_of(tmp_path, "<u@h>") / "attachments" / "blob.bin").write_bytes(b"\x00\x01\x02")
    cli.cmd_get_attachment(tmp_path, _ns(id="u", name="blob.bin"))
    assert "unsupported attachment type application/octet-stream" in capsys.readouterr().out


def test_get_attachment_missing_raises(tmp_path):
    make_bundle(tmp_path, mid="<m@h>", slug="m")
    with pytest.raises(SystemExit, match="no attachment"):
        cli.cmd_get_attachment(tmp_path, _ns(id="m", name="nope.txt"))


# --- get / put artifact -----------------------------------------------------


def test_put_and_get_artifact_roundtrip(tmp_path, capsys, monkeypatch):
    make_bundle(tmp_path, mid="<p@h>", slug="p")
    monkeypatch.setattr("sys.stdin", io.StringIO("the summary\n"))
    cli.cmd_put_artifact(tmp_path, _ns(id="p", name="summary.md"))
    capsys.readouterr()
    cli.cmd_get_artifact(tmp_path, _ns(id="p", name="summary.md"))
    assert capsys.readouterr().out == "the summary\n"


def test_put_artifact_from_file(tmp_path):
    make_bundle(tmp_path, mid="<pf@h>", slug="pf")
    src = tmp_path / "src.md"
    src.write_text("from file")
    cli.cmd_put_artifact(tmp_path, _ns(id="pf", name="reason.md", from_file=str(src)))
    assert (bundle_dir_of(tmp_path, "<pf@h>") / "reason.md").read_text() == "from file"


def test_put_artifact_rejects_reserved_name(tmp_path):
    make_bundle(tmp_path, mid="<r@h>", slug="r")
    with pytest.raises(SystemExit, match="reserved"):
        cli.cmd_put_artifact(tmp_path, _ns(id="r", name="report.md"))


def test_artifact_name_rejects_traversal(tmp_path):
    make_bundle(tmp_path, mid="<t@h>", slug="t")
    with pytest.raises(SystemExit, match="unsafe name"):
        cli.cmd_get_artifact(tmp_path, _ns(id="t", name="../escape"))
