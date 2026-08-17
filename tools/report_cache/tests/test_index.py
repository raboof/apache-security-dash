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

from report_cache.index import URL, Disposition, Entry, Status, load, write
from report_cache.report_md import Header

# committee-info mapping (slug -> entry); the guess reads each entry's mail_list.
# tomcat: mail_list == slug (the common case);
# httpcomponents: mail_list 'hc' differs from the slug (host resolution matters);
# polaris: a current podling, whose synthetic mail_list == its resource slug.
KNOWN = {
    "tomcat": {"mail_list": "tomcat"},
    "httpcomponents": {"mail_list": "hc"},
    "polaris": {"mail_list": "polaris"},
}

# project-coordinates: only tomcat runs its own security team, so its
# security@tomcat.apache.org is a real list; httpcomponents/polaris have no
# entry and fall back to their private@ list. This is what tells a backed
# security@ list from a bare alias when computing delivered_pmcs.
COORDS = {
    "tomcat": {"contact": "security@tomcat.apache.org"},
}


def _header(**meta) -> Header:
    return Header.from_meta(meta)


# --- Entry.from_report: the initial import from a downloaded report.md -------


def test_from_report_initial_state(tmp_path):
    bundle = tmp_path / "2026-05-24" / "tomcat" / "msgid-abc"
    header = _header(
        subject="XXE in the REST API",
        to="security@tomcat.apache.org",
        cc=None,
        labels=["Inbox"],
    )
    got = Entry.from_report(tmp_path, bundle, header, KNOWN, COORDS)
    assert got.path == "2026-05-24/tomcat/msgid-abc"
    assert got.subject == "XXE in the REST API"
    assert got.pmc == "tomcat"
    assert got.labels == ["Inbox"]
    assert got.status is Status.DOWNLOADED
    assert got.disposition is None


def test_from_report_guesses_pmc_from_cc(tmp_path):
    # httpcomponents receives mail at hc.apache.org; the host resolves to the slug.
    header = _header(to=None, cc="private@hc.apache.org")
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.pmc == "httpcomponents"


def test_from_report_guesses_podling(tmp_path):
    # A current podling is guessable like a PMC (synthetic mail_list == slug).
    header = _header(to="security@polaris.apache.org")
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.pmc == "polaris"


def test_from_report_seeds_reporter_name_from_from_display_name(tmp_path):
    header = _header(
        to="security@tomcat.apache.org", **{"from": "Jane Reporter <jane@example.com>"}
    )
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.reporter_name == "Jane Reporter"


def test_from_report_reporter_name_none_without_display_name(tmp_path):
    header = _header(to="security@tomcat.apache.org", **{"from": "jane@example.com"})
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.reporter_name is None


def test_from_report_ignores_from_header(tmp_path):
    # A committer reporting from their own @<pmc> address must not skew the guess.
    header = _header(**{"from": "dev@tomcat.apache.org", "to": "security@apache.org", "cc": None})
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.pmc is None


def test_from_report_no_pmc_for_central_list(tmp_path):
    header = _header(to="security@apache.org", cc=None)
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.pmc is None


def test_from_report_no_pmc_when_guess_is_ambiguous(tmp_path):
    # Two project lists named -> can't assign one; leave it for classification.
    header = _header(to="security@tomcat.apache.org", cc="private@hc.apache.org")
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.pmc is None


# --- delivered_pmcs: where the report was actually delivered -----------------


def test_from_report_records_every_delivered_pmc(tmp_path):
    # Ambiguous for assignment (pmc is None), but delivery is unambiguous: both
    # security lists received it - tomcat's own security@ (it runs a security
    # team) and httpcomponents' private@ - so a track-only decision can check them.
    header = _header(to="security@tomcat.apache.org", cc="private@hc.apache.org")
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.pmc is None
    assert set(got.delivered_pmcs) == {"tomcat", "httpcomponents"}


def test_from_report_own_security_list_counts_as_delivered(tmp_path):
    # tomcat runs its own security@ list (coordinates 'contact'), so being
    # addressed there is genuine delivery.
    header = _header(to="security@tomcat.apache.org")
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.delivered_pmcs == ["tomcat"]


def test_from_report_private_list_counts_as_delivered(tmp_path):
    # A PMC with no security team of its own is reached via its private@ list.
    header = _header(to=None, cc="private@hc.apache.org")
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.delivered_pmcs == ["httpcomponents"]


def test_from_report_bare_security_alias_is_not_delivered(tmp_path):
    # polaris has no security team, so security@polaris.apache.org is not backed
    # by a list: it still guesses the PMC, but is not proof of delivery.
    header = _header(to="security@polaris.apache.org")
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.pmc == "polaris"
    assert got.delivered_pmcs == []


def test_from_report_central_list_delivers_to_no_pmc(tmp_path):
    # The santuario case: only security@apache.org received it, so no PMC did.
    header = _header(to="security@apache.org", cc=None)
    got = Entry.from_report(tmp_path, tmp_path / "d" / "p" / "b", header, KNOWN, COORDS)
    assert got.delivered_pmcs == []


# --- serialisation ----------------------------------------------------------


def test_record_round_trips(tmp_path):
    original = Entry.from_report(
        tmp_path,
        tmp_path / "d" / "p" / "b",
        _header(to="security@tomcat.apache.org"),
        KNOWN,
        COORDS,
    )
    assert Entry.from_record(original.to_record()) == original


def test_status_serialises_as_plain_string(tmp_path):
    got = Entry(path="d/p/b", status=Status.FILED)
    assert got.to_record()["status"] == "filed"


def test_assessment_model_round_trips():
    record = Entry(path="d/p/b", assessment_model="Claude Opus 4.7").to_record()
    assert record["assessment_model"] == "Claude Opus 4.7"
    assert Entry.from_record(record).assessment_model == "Claude Opus 4.7"


def test_from_record_rejects_a_non_mapping():
    # A wrong-typed argument is a TypeError; a dict carrying a bad value is a
    # ValueError (see test_entry_rejects_unknown_status).
    with pytest.raises(TypeError, match="expected a JSON object, got NoneType"):
        Entry.from_record(None)


def test_from_record_ignores_unknown_keys():
    got = Entry.from_record({"path": "d/p/b", "status": "filed", "bogus": 1})
    assert got == Entry(path="d/p/b", status=Status.FILED)


def test_entry_rejects_unknown_status():
    with pytest.raises(ValueError):
        Entry(path="d/p/b", status="not-a-stage")


def test_entry_accepts_disposition_string():
    assert Entry(path="d/p/b", disposition="track").disposition is Disposition.TRACK


def test_entry_rejects_unknown_disposition():
    with pytest.raises(ValueError):
        Entry(path="d/p/b", disposition="whatever")


def test_disposition_serialises_as_plain_string():
    record = Entry(path="d/p/b", disposition=Disposition.SKIP).to_record()
    assert record["disposition"] == "skip"


def test_none_disposition_serialises_as_null():
    assert Entry(path="d/p/b").to_record()["disposition"] is None


def test_entry_accepts_status_string():
    assert Entry(path="d/p/b", status="filed").status is Status.FILED


# --- URL fields: the security-model pointers --------------------------------


def test_security_model_fields_coerce_to_url(tmp_path):
    got = Entry(
        path="d/p/b",
        security_model_source="https://github.com/apache/spark/blob/main/SECURITY.md",
        security_model_link="https://spark.apache.org/security.html",
    )
    assert isinstance(got.security_model_source, URL)
    assert isinstance(got.security_model_link, URL)


@pytest.mark.parametrize("bad", ["not a url", "example.com/model", "ftp://h/x", "/rel/path"])
def test_entry_rejects_a_non_http_url(bad):
    with pytest.raises(ValueError, match="absolute http"):
        Entry(path="d/p/b", security_model_link=bad)


def test_url_serialises_as_a_plain_string():
    record = Entry(path="d/p/b", security_model_link="https://h/x").to_record()
    assert record["security_model_link"] == "https://h/x"
    assert type(record["security_model_link"]) is str


def test_url_round_trips_through_a_record():
    original = Entry(path="d/p/b", security_model_source="https://h/model")
    assert Entry.from_record(original.to_record()) == original


def test_load_rejects_a_bad_url_naming_the_message_id(tmp_path):
    (tmp_path / "index.json").write_text(
        '{"<m@h>": {"path": "d/p/b", "security_model_link": "nonsense"}}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"invalid record for '<m@h>'.*absolute http"):
        load(tmp_path)


# --- load / write / upsert --------------------------------------------------


def test_load_missing_returns_empty(tmp_path):
    assert load(tmp_path) == {}


def test_load_invalid_json_raises(tmp_path):
    (tmp_path / "index.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load(tmp_path)


def test_load_non_object_raises(tmp_path):
    # The wrong shape is a TypeError; invalid JSON (below) is a ValueError.
    (tmp_path / "index.json").write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(TypeError, match="expected a JSON object, got list"):
        load(tmp_path)


def test_load_bad_record_raises_naming_the_message_id(tmp_path):
    (tmp_path / "index.json").write_text(
        '{"<m@h>": {"path": "d/p/b", "status": "not-a-stage"}}', encoding="utf-8"
    )
    # The Message-ID pins which record is corrupt, and index.json which file.
    with pytest.raises(ValueError, match=r"invalid record for '<m@h>'"):
        load(tmp_path)


@pytest.mark.parametrize("record", ["null", '"a string"', "[1, 2]", "3"])
def test_load_non_object_record_raises(tmp_path, record):
    # A record that is not a JSON object must be reported as such, not blow up
    # with an AttributeError from inside the record parse. It stays a TypeError
    # through load, which only adds the file + Message-ID context.
    (tmp_path / "index.json").write_text(f'{{"<m@h>": {record}}}', encoding="utf-8")
    with pytest.raises(TypeError, match=r"invalid record for '<m@h>'.*expected a JSON object"):
        load(tmp_path)


def test_load_returns_entries(tmp_path):
    write(tmp_path, {"<abc@host>": Entry(path="d/p/b", pmc="spark")})
    loaded = load(tmp_path)
    assert isinstance(loaded["<abc@host>"], Entry)
    assert loaded["<abc@host>"].pmc == "spark"


def test_write_is_sorted_with_trailing_newline(tmp_path):
    write(tmp_path, {"<b@h>": Entry(path="b"), "<a@h>": Entry(path="a")})
    text = (tmp_path / "index.json").read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.index("<a@h>") < text.index("<b@h>")
