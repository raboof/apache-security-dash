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

from populate_cache.gmail import resolve_labels, thread_heads


def test_gmail_root_and_no_references_are_heads():
    messages = [
        {"id": "A", "threadId": "A"},  # Gmail root -> head
        {"id": "B", "threadId": "A"},  # reply in A's thread (has References) -> dropped
        {"id": "C", "threadId": "C"},  # Gmail root, orphan reply (has References) -> head
        {"id": "D", "threadId": "X"},  # fresh mail Gmail merged by subject -> head
        {"id": "E", "threadId": "A"},  # forward in A's thread (has References) -> dropped
    ]
    metadata = {
        "A": {"references": ""},
        "B": {"references": "<parent@a>"},
        "C": {"references": "<external@elsewhere>"},
        "D": {"references": ""},
        "E": {"references": "<parent@a>"},
    }
    assert thread_heads(messages, metadata) == ["A", "C", "D"]


def test_order_preserved():
    messages = [
        {"id": "Z", "threadId": "Z"},
        {"id": "Y", "threadId": "Z"},
        {"id": "X", "threadId": "X"},
    ]
    metadata = {"Z": {}, "Y": {"references": "<z@x>"}, "X": {}}
    assert thread_heads(messages, metadata) == ["Z", "X"]


def test_reply_with_references_and_merged_thread_dropped():
    messages = [{"id": "B", "threadId": "A"}]
    metadata = {"B": {"references": "<a@x>"}}
    assert thread_heads(messages, metadata) == []


def test_missing_metadata_defaults_to_head():
    # A message we could not fetch metadata for (-> {}) is kept, never silently
    # dropped: better to over-ingest than to lose a report.
    messages = [{"id": "M", "threadId": "T"}]
    assert thread_heads(messages, {}) == ["M"]


def test_empty():
    assert thread_heads([], {}) == []


def test_resolve_labels_keeps_known_in_order():
    names = {"Label_1": "superset/2026-05-29 sqli", "Label_7": "tracked"}
    # System labels (INBOX/UNREAD) are not in the user-label map -> dropped.
    label_ids = ["INBOX", "Label_7", "Label_1", "UNREAD"]
    assert resolve_labels(label_ids, names) == ["tracked", "superset/2026-05-29 sqli"]


def test_resolve_labels_none_known():
    assert resolve_labels(["INBOX", "UNREAD"], {"Label_1": "x"}) == []
    assert resolve_labels([], {"Label_1": "x"}) == []
