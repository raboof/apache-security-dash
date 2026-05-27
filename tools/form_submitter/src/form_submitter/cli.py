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
"""Argparse CLI for form-submitter."""

from __future__ import annotations

import argparse
import json
import sys

from form_submitter import SUBMITTER_PATH
from form_submitter.auth import AuthError
from form_submitter.plan import NothingSubmittable, build_plan, print_plan
from form_submitter.sheets import PMCStateError, fetch_pmc_state
from form_submitter.submitter import SubmitterError, load_submitter, write_submitter


def cmd_setup(_args: argparse.Namespace) -> int:
    """Launch Chromium with persistent profile so the operator signs in."""
    from form_submitter.browser import run_setup

    run_setup()
    return 0


def cmd_setup_submitter(args: argparse.Namespace) -> int:
    """Write the submitter identity to submitter.json (mode 0o600)."""
    write_submitter(name=args.name, email=args.email, github=args.github)
    print(f"Wrote submitter config to {SUBMITTER_PATH}.")
    return 0


def cmd_submit_pmc(args: argparse.Namespace) -> int:
    """Submit forms (or dry-run) for one PMC."""
    if args.dry_run and not SUBMITTER_PATH.exists():
        submitter = {
            "name": "<run setup-submitter to set>",
            "email": "<your.id>@apache.org",
            "github": "<https://github.com/your-handle>",
        }
        print(
            f"NOTE: {SUBMITTER_PATH} missing — using placeholders. "
            "Run setup-submitter before live submission.\n"
        )
    else:
        submitter = load_submitter()
    state = fetch_pmc_state(args.slug)
    plan, skipped = build_plan(state, submitter)

    print_plan(plan)
    if skipped:
        print(
            f"\nSkipped {len(skipped)} repo(s) — no AGENTS.md / SECURITY.md / security.txt at HEAD:"
        )
        for r in skipped:
            print(f"  - apache/{r.name}")
        print(
            "These won't be submitted. Land discoverability "
            "(via glasswing-model-verify) before re-running for them."
        )

    if args.dry_run:
        print("\nDry run — no form submissions.")
        return 0

    from form_submitter.browser import run_live

    result = run_live(plan, starting_from=args.starting_from)
    print("\nSubmission complete.")
    print(json.dumps(result, indent=2))

    submission_date = result["submitted_at"][:10]
    submitted_urls = [s["repo_url"] for s in result["submitted"]]
    print("\nValues for glasswing-scan-update apply:")
    print(f"  Date scan requested: {submission_date}")
    print("  Repositories submitted:")
    for url in submitted_urls:
        print(f"    {url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="form-submitter",
        description=(
            "Submit per-repo scan-request forms for a PMC via the vendor's "
            "project-enrollment Google Form."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="One-time Google sign-in into persistent profile.")

    s = sub.add_parser("setup-submitter", help="Write submitter identity to submitter.json.")
    s.add_argument("--name", required=True, help="Submitter's full name.")
    s.add_argument("--email", required=True, help="Submitter's @apache.org email.")
    s.add_argument("--github", required=True, help="Submitter's GitHub profile URL.")

    s = sub.add_parser("submit-pmc", help="Submit forms for one PMC.")
    s.add_argument("--slug", required=True, help="PMC slug (e.g. tomcat, logging).")
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan only; don't drive the browser.",
    )
    s.add_argument(
        "--starting-from",
        metavar="REPO_NAME",
        help=(
            "Resume mid-batch: skip repos with names earlier than this in "
            "the ordering. Use the bare repo name (e.g. tomcat-native), "
            "not the full URL."
        ),
    )

    return p


DISPATCH = {
    "setup": cmd_setup,
    "setup-submitter": cmd_setup_submitter,
    "submit-pmc": cmd_submit_pmc,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return DISPATCH[args.cmd](args)
    except (AuthError, SubmitterError, PMCStateError, NothingSubmittable) as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
