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

"""The triage state the cache hands to inbox-manager: what it suggests, what it files."""

import email
from email.policy import default

import pytest
from report_cache.index import Disposition, Entry, Status

from inbox_manager import cli


def entry(status=Status.ASSESSED, disposition=Disposition.TRACK, labels=None):
    return Entry(
        path="spark/2026-05-24-xxe",
        status=status,
        disposition=disposition,
        labels=labels,
    )


class FakeInbox:
    """The handful of IMAP calls file_message makes, recorded rather than sent."""

    def __init__(self, folders=(), on_message=()):
        self.folders = set(folders)
        self.on_message = list(on_message)
        self.created = []
        self.added = []
        self.moved_to = None

    def get_gmail_labels(self, uids):
        return {uids[0]: [label.encode() for label in self.on_message]}

    def folder_exists(self, name):
        return name in self.folders

    def create_folder(self, name):
        self.created.append(name)
        self.folders.add(name)

    def add_gmail_labels(self, uids, labels):
        self.added.extend(labels)

    def move(self, uids, folder):
        self.moved_to = folder


@pytest.fixture
def message():
    return email.message_from_string(
        "Subject: report\r\nDate: Sun, 24 May 2026 10:00:00 +0000\r\n", policy=default
    )


@pytest.fixture
def confirm(monkeypatch):
    """Answer the attach/archive confirm with 'y', and every label prompt with its prefill."""
    monkeypatch.setattr(cli, "read_key", lambda: "y")
    monkeypatch.setattr(cli, "input_with_prefill", lambda prompt, text: text)


# suggested_action: only an assessed track entry implies an action.


def test_assessed_track_suggests_file():
    assert cli.suggested_action(entry()) == "f"


def test_assessed_forward_suggests_accept():
    assert cli.suggested_action(entry(disposition=Disposition.FORWARD)) == "a"


def test_assessed_decline_suggests_reject():
    assert cli.suggested_action(entry(disposition=Disposition.DECLINE)) == "r"


@pytest.mark.parametrize("disposition", [Disposition.SKIP, None])
def test_out_of_scope_dispositions_stay_interactive(disposition):
    # skip is out of the skill's scope and a report with no disposition is
    # undecided: the operator decides.
    assert cli.suggested_action(entry(disposition=disposition)) is None


@pytest.mark.parametrize("status", [Status.DOWNLOADED, Status.CLASSIFIED, Status.FILED])
def test_unassessed_track_is_not_suggested(status):
    # A disposition is only trustworthy once the report has been assessed.
    assert cli.suggested_action(entry(status=status)) is None


def test_no_entry_no_suggestion():
    assert cli.suggested_action(None) is None


# draft_artifact: the triage-assess fragments that pre-fill the forward / receipt / reject.


def _bundle(tmp_path, monkeypatch, e):
    """Make the entry's bundle dir under a REPORT_CACHE_DIR-overridden cache."""
    monkeypatch.setenv("REPORT_CACHE_DIR", str(tmp_path))
    d = tmp_path / e.path
    d.mkdir(parents=True)
    return d


def test_draft_artifact_reads_a_written_fragment(tmp_path, monkeypatch):
    e = entry()
    (_bundle(tmp_path, monkeypatch, e) / "summary.md").write_text("the summary\n")
    assert cli.draft_artifact(e, "summary.md") == "the summary\n"


def test_draft_artifact_absent_is_empty_string(tmp_path, monkeypatch):
    e = entry()
    _bundle(tmp_path, monkeypatch, e)
    assert cli.draft_artifact(e, "reason.md") == ""


def test_draft_artifact_no_entry_is_empty_string():
    assert cli.draft_artifact(None, "summary.md") == ""


# file_message: the labels come from the cache, and split by whether they exist.


def test_existing_label_is_attached_and_archived(message, confirm):
    inbox = FakeInbox(folders=["spark/2026-05-24 xxe rest api"])
    ok = cli.file_message(inbox, message, 1, None, entry(labels=["spark/2026-05-24 xxe rest api"]))
    assert ok
    assert inbox.added == ["spark/2026-05-24 xxe rest api"]
    assert inbox.created == []  # it already exists: nothing to mint
    assert inbox.moved_to == "[Gmail]/All Mail"


def test_fresh_label_is_created(message, confirm):
    inbox = FakeInbox()  # no folders: the label does not exist yet
    ok = cli.file_message(inbox, message, 1, None, entry(labels=["spark/2026-05-24 xxe rest api"]))
    assert ok
    assert inbox.created == ["spark/2026-05-24 xxe rest api"]
    assert inbox.added == ["spark/2026-05-24 xxe rest api"]


def test_label_already_on_the_message_is_left_alone(message, confirm):
    inbox = FakeInbox(folders=["spark/2026-05-24 xxe"], on_message=["spark/2026-05-24 xxe"])
    ok = cli.file_message(inbox, message, 1, None, entry(labels=["spark/2026-05-24 xxe"]))
    assert ok
    assert inbox.added == []  # nothing to attach, but still archived
    assert inbox.moved_to == "[Gmail]/All Mail"


def test_digest_attaches_every_label_it_covers(message, confirm):
    # A digest carries one label per report it lists; all of them already exist.
    labels = [
        "spark/2026-05-24 xxe",
        "tomcat/2026-05-20 deser",
        "hadoop/2026-05-21 rce",
    ]
    inbox = FakeInbox(folders=labels, on_message=["tomcat/2026-05-20 deser"])
    ok = cli.file_message(inbox, message, 1, None, entry(labels=labels))
    assert ok
    # The one already on the message is skipped, the other two attached.
    assert sorted(inbox.added) == ["hadoop/2026-05-21 rce", "spark/2026-05-24 xxe"]


def test_declining_the_confirm_leaves_the_message_in_the_inbox(message, monkeypatch):
    monkeypatch.setattr(cli, "read_key", lambda: "n")
    monkeypatch.setattr(cli, "input_with_prefill", lambda prompt, text: text)
    inbox = FakeInbox(folders=["spark/2026-05-24 xxe"])
    ok = cli.file_message(inbox, message, 1, None, entry(labels=["spark/2026-05-24 xxe"]))
    assert not ok
    assert inbox.added == []
    assert inbox.moved_to is None


def test_an_emptied_fresh_label_is_skipped_not_aborted(message, monkeypatch):
    # A digest's labels are independent: emptying one drops that label only.
    monkeypatch.setattr(cli, "read_key", lambda: "y")
    monkeypatch.setattr(
        cli,
        "input_with_prefill",
        lambda prompt, text: "" if text.startswith("hadoop") else text,
    )
    inbox = FakeInbox(folders=["spark/2026-05-24 xxe"])
    ok = cli.file_message(
        inbox,
        message,
        1,
        None,
        entry(labels=["spark/2026-05-24 xxe", "hadoop/2026-05-21 rce"]),
    )
    assert ok
    assert inbox.added == ["spark/2026-05-24 xxe"]
    assert inbox.moved_to == "[Gmail]/All Mail"


def test_an_edited_fresh_label_is_the_one_attached(message, monkeypatch):
    monkeypatch.setattr(cli, "read_key", lambda: "y")
    monkeypatch.setattr(cli, "input_with_prefill", lambda prompt, text: "spark/2026-05-24 xxe rest")
    inbox = FakeInbox()
    ok = cli.file_message(inbox, message, 1, None, entry(labels=["spark/2026-05-24 xxe"]))
    assert ok
    assert inbox.added == ["spark/2026-05-24 xxe rest"]
    assert inbox.created == ["spark/2026-05-24 xxe rest"]
