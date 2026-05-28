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

import pytest

from sheets_writer.canned import build_canned_rows


def _entry(**overrides) -> dict:
    base = {
        "topic": "scope",
        "question_pattern": "asks about repo scope",
        "response": "Two layers — ...",
        "author": "jarek@potiuk.com",
    }
    base.update(overrides)
    return base


def test_build_canned_rows_single() -> None:
    rows = build_canned_rows([_entry()], today="2026-05-27")
    assert rows == [
        [
            "2026-05-27",
            "scope",
            "asks about repo scope",
            "Two layers — ...",
            "jarek@potiuk.com",
            "",
        ]
    ]


def test_build_canned_rows_with_notes() -> None:
    rows = build_canned_rows(
        [_entry(notes="don't reuse if Hive-style monorepo")], today="2026-05-27"
    )
    assert rows[0][-1] == "don't reuse if Hive-style monorepo"


def test_build_canned_rows_today_auto_fills() -> None:
    rows = build_canned_rows([_entry()])  # no `today` kwarg
    # First column is today's date — accept any ISO-shape since the
    # exact value depends on clock; key thing is it's a YYYY-MM-DD string.
    import re

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", rows[0][0])


def test_build_canned_rows_missing_required_field() -> None:
    bad = _entry()
    del bad["author"]
    with pytest.raises(ValueError) as excinfo:
        build_canned_rows([bad])
    assert "author" in str(excinfo.value)


def test_build_canned_rows_missing_question_pattern() -> None:
    bad = _entry()
    del bad["question_pattern"]
    with pytest.raises(ValueError) as excinfo:
        build_canned_rows([bad])
    assert "question_pattern" in str(excinfo.value)


def test_build_canned_rows_multiple_preserves_order() -> None:
    rows = build_canned_rows(
        [
            _entry(topic="first"),
            _entry(topic="second"),
            _entry(topic="third"),
        ],
        today="2026-05-27",
    )
    assert [r[1] for r in rows] == ["first", "second", "third"]
