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

from form_submitter.plan import (
    NothingSubmittable,
    build_headline_additional_info,
    build_plan,
    build_subsequent_additional_info,
    get_scan_result_recipients_for_pmc,
    parse_expedite_cell,
    parse_submission_notes,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("   ", []),
        ("none", []),
        ("NONE", []),
        ("None\n", []),
        ("a@apache.org", ["a@apache.org"]),
        ("a@apache.org\nb@apache.org", ["a@apache.org", "b@apache.org"]),
        ("  a@apache.org  \n\n  b@apache.org  ", ["a@apache.org", "b@apache.org"]),
        # Lines without an @ are dropped (e.g. blank free-text noise).
        ("a@apache.org\n# comment\nb@apache.org", ["a@apache.org", "b@apache.org"]),
        (None, []),
    ],
)
def test_parse_expedite_cell(raw, expected) -> None:
    assert parse_expedite_cell(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("   ", ""),
        ("\n\n", ""),
        ("Branch-level scope: master only.", "Branch-level scope: master only."),
        ("  trimmed   ", "trimmed"),
        (None, ""),
    ],
)
def test_parse_submission_notes(raw, expected) -> None:
    assert parse_submission_notes(raw) == expected


def test_get_scan_result_recipients_extracts_apache_addresses() -> None:
    row = {
        "Contact Person": "Nick Dimiduk <ndimiduk@apache.org>",
        "Backup contact": "Andrew Purtell <apurtell@apache.org>, Duo <zhangduo@apache.org>",
    }
    recipients = get_scan_result_recipients_for_pmc(row)
    assert "ndimiduk@apache.org" in recipients
    assert "apurtell@apache.org" in recipients
    assert "zhangduo@apache.org" in recipients


def test_get_scan_result_recipients_dedupes() -> None:
    row = {
        "Contact Person": "ndimiduk@apache.org",
        "Backup contact": "ndimiduk@apache.org",
    }
    assert get_scan_result_recipients_for_pmc(row) == ["ndimiduk@apache.org"]


def test_get_scan_result_recipients_ignores_non_apache() -> None:
    row = {
        "Contact Person": "n@external.com",
        "Backup contact": "apurtell@apache.org",
    }
    assert get_scan_result_recipients_for_pmc(row) == ["apurtell@apache.org"]


def test_get_scan_result_recipients_empty_cells() -> None:
    assert get_scan_result_recipients_for_pmc({}) == []


def test_build_headline_includes_pmc_contacts_and_model(hbase_pmc_row, repo_hbase) -> None:
    out = build_headline_additional_info(
        pmc_name="Apache HBase",
        pmc_row=hbase_pmc_row,
        expedite_addrs=[],
        repos=[repo_hbase],
        headline_repo=repo_hbase,
        submission_notes_text="",
    )
    assert "Apache HBase" in out
    assert "ndimiduk@apache.org" in out
    assert "apurtell@apache.org" in out
    assert "https://hbase.apache.org/security-model/" in out
    assert "OSSF Criticality Score" in out
    assert "← this submission (headline)" in out


def test_build_headline_renders_solo_contact_when_backup_blank(hbase_pmc_row, repo_hbase) -> None:
    """A blank Backup contact is a legitimate solo-PMC case (e.g. Santuario);
    the headline block renders it as '(none — solo PMC contact)', not empty."""
    row = {**hbase_pmc_row, "Backup contact": ""}
    out = build_headline_additional_info(
        pmc_name="Apache HBase",
        pmc_row=row,
        expedite_addrs=[],
        repos=[repo_hbase],
        headline_repo=repo_hbase,
        submission_notes_text="",
    )
    assert "  - Backup:  (none — solo PMC contact)" in out


def test_build_headline_includes_expedite_addresses_when_present(hbase_pmc_row, repo_hbase) -> None:
    out = build_headline_additional_info(
        pmc_name="Apache HBase",
        pmc_row=hbase_pmc_row,
        expedite_addrs=["ndimiduk@apache.org", "apurtell@apache.org"],
        repos=[repo_hbase],
        headline_repo=repo_hbase,
        submission_notes_text="",
    )
    assert "Claude-for-Open-Source subscription expedite" in out
    assert "  - ndimiduk@apache.org" in out
    assert "  - apurtell@apache.org" in out


def test_build_headline_omits_expedite_block_when_empty(hbase_pmc_row, repo_hbase) -> None:
    out = build_headline_additional_info(
        pmc_name="Apache HBase",
        pmc_row=hbase_pmc_row,
        expedite_addrs=[],
        repos=[repo_hbase],
        headline_repo=repo_hbase,
        submission_notes_text="",
    )
    assert "expedite" not in out.lower()


def test_build_headline_appends_submission_notes(hbase_pmc_row, repo_hbase) -> None:
    out = build_headline_additional_info(
        pmc_name="Apache HBase",
        pmc_row=hbase_pmc_row,
        expedite_addrs=[],
        repos=[repo_hbase],
        headline_repo=repo_hbase,
        submission_notes_text="Branch-level scope: master + branch-2.6.\nNo Hadoop forks.",
    )
    assert "Submission notes (operator-supplied):" in out
    assert "Branch-level scope: master + branch-2.6." in out
    assert "No Hadoop forks." in out


def test_build_headline_marks_each_repo_with_index_and_criticality(
    hbase_pmc_row, repo_hbase, repo_hbase_only_agents
) -> None:
    repos = [repo_hbase, repo_hbase_only_agents]
    out = build_headline_additional_info(
        pmc_name="Apache HBase",
        pmc_row=hbase_pmc_row,
        expedite_addrs=[],
        repos=repos,
        headline_repo=repos[0],
        submission_notes_text="",
    )
    assert "1. https://github.com/apache/hbase (criticality 63.0%)" in out
    assert "2. https://github.com/apache/hbase-thirdparty (criticality 45.0%)" in out


def test_build_subsequent_references_headline(repo_hbase, repo_hbase_only_agents) -> None:
    out = build_subsequent_additional_info(
        pmc_name="Apache HBase",
        this_repo=repo_hbase_only_agents,
        headline_repo=repo_hbase,
    )
    assert "apache/hbase-thirdparty" in out
    assert "apache/hbase" in out
    assert "headline submission" in out


def test_build_plan_orders_headline_first_and_skips_unsubmittable(
    submitter, hbase_pmc_row, repo_hbase, repo_hbase_only_agents, repo_no_markers
) -> None:
    state = {
        "pmc": hbase_pmc_row,
        "repos": [repo_hbase, repo_hbase_only_agents, repo_no_markers],
    }
    plan, skipped = build_plan(state, submitter)

    assert len(plan) == 2
    assert plan[0].repo_name == "hbase"
    assert plan[0].is_headline is True
    assert plan[1].repo_name == "hbase-thirdparty"
    assert plan[1].is_headline is False

    assert len(skipped) == 1
    assert skipped[0].name == "hbase-operator-tools"


def test_build_plan_headline_claude_max_only_when_expedite_present(
    submitter, hbase_pmc_row, repo_hbase
) -> None:
    state = {"pmc": hbase_pmc_row, "repos": [repo_hbase]}
    plan, _ = build_plan(state, submitter)
    # HBase fixture has 2 expedite addresses → Claude Max checkbox ticks.
    assert plan[0].confirm_claude_max is True


def test_build_plan_headline_no_claude_max_without_expedite(submitter, repo_hbase) -> None:
    row = {
        "PMC Slug": "hbase",
        "PMC Name": "Apache HBase",
        "Contact Person": "Nick <ndimiduk@apache.org>",
        "Backup contact": "Andrew <apurtell@apache.org>",
        "Security Model": "https://hbase.apache.org/security-model/",
        "Expedite Claude OSS Requests": "none",
        "Submission notes": "",
    }
    state = {"pmc": row, "repos": [repo_hbase]}
    plan, _ = build_plan(state, submitter)
    assert plan[0].confirm_claude_max is False


def test_build_plan_subsequent_never_claims_claude_max(
    submitter, hbase_pmc_row, repo_hbase, repo_hbase_only_agents
) -> None:
    state = {"pmc": hbase_pmc_row, "repos": [repo_hbase, repo_hbase_only_agents]}
    plan, _ = build_plan(state, submitter)
    assert plan[1].confirm_claude_max is False


def test_build_plan_confirm_security_md_reflects_per_repo_marker(
    submitter, hbase_pmc_row, repo_hbase, repo_hbase_only_agents
) -> None:
    """Per the SKILL: only ticks when AGENTS or SECURITY.md or security.txt exists."""
    state = {"pmc": hbase_pmc_row, "repos": [repo_hbase, repo_hbase_only_agents]}
    plan, _ = build_plan(state, submitter)
    assert plan[0].confirm_security_md is True
    assert plan[1].confirm_security_md is True  # AGENTS.md alone qualifies


def test_build_plan_pmc_name_prefixes_apache_when_missing(submitter, repo_hbase) -> None:
    row = {
        "PMC Slug": "hbase",
        "PMC Name": "HBase",  # no "Apache " prefix
        "Contact Person": "n@apache.org",
        "Backup contact": "a@apache.org",
        "Security Model": "https://x.org",
        "Expedite Claude OSS Requests": "",
        "Submission notes": "",
    }
    state = {"pmc": row, "repos": [repo_hbase]}
    plan, _ = build_plan(state, submitter)
    assert plan[0].project_name == "Apache HBase"


def test_build_plan_pmc_name_preserves_apache_when_present(
    submitter, hbase_pmc_row, repo_hbase
) -> None:
    state = {"pmc": hbase_pmc_row, "repos": [repo_hbase]}
    plan, _ = build_plan(state, submitter)
    assert plan[0].project_name == "Apache HBase"


def test_build_plan_raises_when_nothing_submittable(
    submitter, hbase_pmc_row, repo_no_markers
) -> None:
    state = {"pmc": hbase_pmc_row, "repos": [repo_no_markers]}
    with pytest.raises(NothingSubmittable):
        build_plan(state, submitter)
