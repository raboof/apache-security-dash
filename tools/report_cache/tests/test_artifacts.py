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

from report_cache import artifacts

# --- read / write round-trip ------------------------------------------------


def test_write_then_read_round_trips(tmp_path):
    path = artifacts.write_artifact(tmp_path, "summary.md", "the summary\n")
    assert path == tmp_path / "summary.md"
    assert artifacts.read_artifact(tmp_path, "summary.md") == "the summary\n"


def test_read_absent_artifact_is_none(tmp_path):
    # Forgiving like Bundle.fragment: a missing file is None, not an error, so a
    # caller can do `read_artifact(...) or ""`.
    assert artifacts.read_artifact(tmp_path, "reason.md") is None


def test_write_returns_the_path(tmp_path):
    assert artifacts.write_artifact(tmp_path, "note.md", "x").read_text() == "x"


# --- listing ----------------------------------------------------------------


def test_list_artifacts_excludes_reserved_and_sorts(tmp_path):
    (tmp_path / "report.md").write_text("front matter")
    (tmp_path / "raw.eml").write_text("raw")
    (tmp_path / "summary.md").write_text("s")
    (tmp_path / "note.md").write_text("n")
    (tmp_path / "attachments").mkdir()  # a dir is not an artifact
    assert artifacts.list_artifacts(tmp_path) == ["note.md", "summary.md"]


def test_list_artifacts_empty_bundle(tmp_path):
    assert artifacts.list_artifacts(tmp_path) == []


# --- name safety ------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", ".", "..", "../escape", "sub/dir.md", "a/b"])
def test_unsafe_names_are_rejected(tmp_path, bad):
    with pytest.raises(ValueError, match="unsafe name"):
        artifacts.safe_name(bad)
    with pytest.raises(ValueError, match="unsafe name"):
        artifacts.read_artifact(tmp_path, bad)
    with pytest.raises(ValueError, match="unsafe name"):
        artifacts.write_artifact(tmp_path, bad, "x")


@pytest.mark.parametrize("name", ["report.md", "raw.eml"])
def test_write_refuses_reserved_names(tmp_path, name):
    with pytest.raises(ValueError, match="reserved"):
        artifacts.write_artifact(tmp_path, name, "clobber")


def test_safe_name_returns_a_plain_name_unchanged(tmp_path):
    assert artifacts.safe_name("summary.md") == "summary.md"
