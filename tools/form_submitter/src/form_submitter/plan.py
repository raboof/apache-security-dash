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
"""Plan computation — pure functions over PMC state.

This module is intentionally browser-free so unit tests can exercise
plan logic without Playwright installed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from form_submitter.repos import RepoEntry


@dataclass
class FormFill:
    project_name: str
    repo_url: str
    your_name: str
    your_email: str
    github_profile: str
    your_role: str
    additional_info: str
    confirm_authorized: bool
    confirm_security_md: bool
    confirm_claude_max: bool
    is_headline: bool
    repo_name: str


class NothingSubmittable(Exception):
    """All repos in PMC scope lack discoverability markers at HEAD."""


def parse_expedite_cell(raw: str) -> list[str]:
    """Return list of @apache.org addresses; empty if cell is blank or 'none'."""
    raw = (raw or "").strip()
    if not raw or raw.lower() == "none":
        return []
    return [line.strip() for line in raw.splitlines() if line.strip() and "@" in line.strip()]


def parse_submission_notes(raw: str) -> str:
    """Return the PMCs sheet's 'Submission notes' free-text cell, stripped.

    Rendered verbatim in the headline form's Additional Information
    under a ``Submission notes (operator-supplied):`` section. Empty
    cell -> empty string -> no section appended.

    The helper does not parse structured tags out of this cell.
    Operators write whatever per-PMC quirks they need the vendor's
    scan team to see (branch-level scope, repo opt-outs, model-URL
    caveats, etc.). Vendor-facing only; don't put internal-process
    overrides here.
    """
    return (raw or "").strip()


def get_scan_result_recipients_for_pmc(pmc_row: dict) -> list[str]:
    """Best-effort: derive recipients from the PMC row's Contact / Backup columns.

    The original [GLASSWING] request thread is the source of truth, but
    we don't re-fetch Gmail here — operator confirms the list during
    the plan review.
    """
    out: list[str] = []
    for col in ("Contact Person", "Backup contact"):
        raw = pmc_row.get(col, "").strip()
        if "@apache.org" in raw:
            for tok in raw.replace("<", " ").replace(">", " ").replace(",", " ").split():
                tok = tok.strip().rstrip(",.;")
                if tok.endswith("@apache.org") and tok not in out:
                    out.append(tok)
    return out


def build_headline_additional_info(
    pmc_name: str,
    pmc_row: dict,
    expedite_addrs: list[str],
    repos: list[RepoEntry],
    headline_repo: RepoEntry,
    submission_notes_text: str = "",
) -> str:
    """Build the headline form's Additional Information block.

    Deliberately does NOT include the scan-result delivery destination.
    Vendor scan results come back to the ASF Security team's submitter
    address; the team then forwards manually to the PMC's named contacts
    via ``glasswing-scan-forward``. The form's submission shouldn't pin
    the downstream forwarding destination — that's an internal ASF
    process detail.
    """
    primary = pmc_row.get("Contact Person", "").strip()
    backup = pmc_row.get("Backup contact", "").strip()
    model_url = pmc_row.get("Security Model", "").strip()

    lines = [
        f"Submitted by the ASF Security Committee on behalf of {pmc_name} PMC at their request.",
        "",
        "PMC contacts:",
        f"  - Primary: {primary}",
        f"  - Backup:  {backup}",
        "",
        "Threat model (verified by the ASF Security team against the",
        "Scovetta rubric):",
        f"  - {model_url}",
    ]

    if expedite_addrs:
        lines.extend(
            [
                "",
                "Claude-for-Open-Source subscription expedite — the following",
                "PMC members have registered for the Claude Max 20x program at",
                "https://claude.com/contact-sales/claude-for-oss and would",
                "benefit from an expedite of their applications. The",
                '"I\'m interested in Claude Max 20x" checkbox on this form',
                "refers specifically to:",
            ]
        )
        for addr in expedite_addrs:
            lines.append(f"  - {addr}")

    lines.extend(
        [
            "",
            f"Repos in scope for {pmc_name} (submitted as separate",
            "forms, ordered by OSSF Criticality Score):",
        ]
    )
    for i, r in enumerate(repos, start=1):
        marker = "  ← this submission (headline)" if r.url == headline_repo.url else ""
        crit = f"{r.criticality:.1f}%" if r.criticality is not None else "blank"
        lines.append(f"  {i}. {r.url} (criticality {crit}){marker}")

    if submission_notes_text:
        lines.extend(["", "Submission notes (operator-supplied):"])
        for line in submission_notes_text.splitlines():
            lines.append(f"  {line}" if line.strip() else "")

    return "\n".join(lines)


def build_subsequent_additional_info(
    pmc_name: str, this_repo: RepoEntry, headline_repo: RepoEntry
) -> str:
    return "\n".join(
        [
            (
                f"Submitted by the ASF Security Committee on behalf of "
                f"{pmc_name} PMC at their request."
            ),
            "",
            f"This is the apache/{this_repo.name} submission within a per-repo",
            f"batch for {pmc_name}. The maintainer roster, scan-result",
            "recipients, threat model, and any OSS-subscription expedite",
            "request are on the headline submission for this PMC (the",
            f"apache/{headline_repo.name} submission, submitted via this form",
            "immediately before this one).",
        ]
    )


def build_plan(state: dict, submitter: dict) -> tuple[list[FormFill], list[RepoEntry]]:
    """Return ``(plan, skipped)``.

    ``plan`` is the per-repo FormFill list (ordered). ``skipped`` is the
    list of repos dropped because they lack any discoverability marker
    at HEAD.

    Raises:
        NothingSubmittable: every repo in scope was skipped.
    """
    pmc_row = state["pmc"]
    all_repos: list[RepoEntry] = state["repos"]

    submittable = [r for r in all_repos if r.is_submittable]
    skipped = [r for r in all_repos if not r.is_submittable]

    if not submittable:
        raise NothingSubmittable(
            "No repos are submittable — every repo in Repositories requested "
            "lacks AGENTS.md, SECURITY.md, and security.txt at HEAD. Land "
            "discoverability via glasswing-model-verify before re-running."
        )

    repos = submittable
    pmc_name_raw = pmc_row.get("PMC Name", "").strip() or pmc_row["PMC Slug"]
    pmc_name = (
        pmc_name_raw if pmc_name_raw.lower().startswith("apache ") else f"Apache {pmc_name_raw}"
    )
    expedite_addrs = parse_expedite_cell(pmc_row.get("Expedite Claude OSS Requests", ""))
    submission_notes_text = parse_submission_notes(pmc_row.get("Submission notes", ""))

    sec_model = pmc_row.get("Security Model", "").strip()
    if sec_model and not sec_model.lower().startswith(("http://", "https://")):
        print(
            f"WARN: Security Model cell on {pmc_row.get('PMC Slug')!r} is a label, "
            f"not a URL: {sec_model!r}. Form expects a URL — the operator should "
            "supply one before live submission (typically by editing the cell or "
            "passing the URL inline).",
            file=sys.stderr,
        )

    headline = repos[0]
    role = f"ASF Security Committee member, submitting on behalf of {pmc_name} PMC at their request"

    plan: list[FormFill] = []
    for i, repo in enumerate(repos):
        is_headline = i == 0
        if is_headline:
            additional = build_headline_additional_info(
                pmc_name=pmc_name,
                pmc_row=pmc_row,
                expedite_addrs=expedite_addrs,
                repos=repos,
                headline_repo=headline,
                submission_notes_text=submission_notes_text,
            )
            confirm_claude_max = bool(expedite_addrs)
        else:
            additional = build_subsequent_additional_info(
                pmc_name=pmc_name,
                this_repo=repo,
                headline_repo=headline,
            )
            confirm_claude_max = False

        plan.append(
            FormFill(
                project_name=pmc_name,
                repo_url=repo.url,
                your_name=submitter["name"],
                your_email=submitter["email"],
                github_profile=submitter["github"],
                your_role=role,
                additional_info=additional,
                confirm_authorized=True,
                # Per-repo: tick only when SECURITY.md or security.txt
                # exists at HEAD. If only AGENTS.md was found, the repo
                # is submittable but the form's "valid SECURITY.md"
                # assertion stays unchecked — the assertion needs to be
                # literally true.
                confirm_security_md=repo.can_claim_security_md,
                confirm_claude_max=confirm_claude_max,
                is_headline=is_headline,
                repo_name=repo.name,
            )
        )

    return plan, skipped


def print_plan(plan: list[FormFill]) -> None:
    print(f"Plan: {len(plan)} form submission(s)")
    for i, f in enumerate(plan, start=1):
        marker = " (HEADLINE)" if f.is_headline else ""
        print(f"\n--- Form {i}/{len(plan)}: apache/{f.repo_name}{marker} ---")
        print(f"  Name of the Open Source Project: {f.project_name}")
        print(f"  URL of the Repository: {f.repo_url}")
        print(f"  Your Name: {f.your_name}")
        print(f"  Your Email Address: {f.your_email}")
        print(f"  URL of your Github profile: {f.github_profile}")
        print(f"  Your Role: {f.your_role}")
        print(f"  Additional information ({len(f.additional_info)} chars):")
        for line in f.additional_info.splitlines():
            print(f"    {line}")
        print(
            f"  [{'x' if f.confirm_authorized else ' '}] "
            "I confirm I'm authorized to request this scan"
        )
        print(
            f"  [{'x' if f.confirm_security_md else ' '}] "
            "There is a valid security.txt or SECURITY.md"
        )
        print(
            f"  [{'x' if f.confirm_claude_max else ' '}] "
            "I'm interested in Claude Max 20x for my Open Source work"
        )
