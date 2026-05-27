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
"""Argparse CLI for jira-writer.

Subcommands:
  whoami        Verify PAT auth via GET /myself.
  create-issue  Create a JIRA issue.
  add-comment   Add a comment to an existing issue.

All write subcommands have --dry-run which prints the payload preview
without contacting JIRA. The conversational flow this CLI is designed
for (Claude Code calling it via Bash) is: agent runs --dry-run, shows
the diff to the user, user approves, agent re-runs without --dry-run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jira_writer import JIRA_BASE
from jira_writer.auth import PATError
from jira_writer.client import APIError, add_comment, create_issue, get_myself


def cmd_whoami(_args: argparse.Namespace) -> int:
    me = get_myself()
    print(f"Authenticated as: {me.get('displayName')} (name={me.get('name')}, key={me.get('key')})")
    if me.get("emailAddress"):
        print(f"Email: {me['emailAddress']}")
    return 0


def _read_text_arg(inline: str | None, file_path: str | None) -> str:
    """Return inline text or file contents (exactly one is set)."""
    if file_path:
        return Path(file_path).read_text()
    assert inline is not None
    return inline


def _preview(label: str, text: str, *, head_lines: int = 60) -> None:
    """Print a multi-line preview of ``text`` with a ``|`` gutter."""
    lines = text.splitlines()
    print(f"  {label} ({len(text)} chars, {len(lines)} lines):")
    for line in lines[:head_lines]:
        print(f"    | {line}")
    if len(lines) > head_lines:
        print(f"    | ... ({len(lines) - head_lines} more lines)")


def cmd_create_issue(args: argparse.Namespace) -> int:
    description = _read_text_arg(args.description, args.description_file)
    print("Will create JIRA issue:")
    print(f"  Project: {args.project}")
    print(f"  Type:    {args.issuetype}")
    print(f"  Summary: {args.summary}")
    _preview("Description", description)
    if args.dry_run:
        print("\nDry run — no issue created.")
        return 0
    result = create_issue(
        project=args.project,
        summary=args.summary,
        description=description,
        issuetype=args.issuetype,
    )
    key = result.get("key")
    if not key:
        print(f"\nUnexpected response from POST /issue: {result}", file=sys.stderr)
        return 1
    print(f"\nCreated: {JIRA_BASE}/browse/{key}")
    return 0


def cmd_add_comment(args: argparse.Namespace) -> int:
    comment = _read_text_arg(args.body, args.body_file)
    print(f"Will comment on {args.issue}:")
    _preview("Body", comment, head_lines=30)
    if args.dry_run:
        print("\nDry run — no comment added.")
        return 0
    add_comment(args.issue, comment)
    print(f"\nComment added: {JIRA_BASE}/browse/{args.issue}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jira-writer",
        description="Apache JIRA write helper (PAT-authenticated).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="Verify PAT auth.")

    p_create = sub.add_parser("create-issue", help="Create a new JIRA issue.")
    p_create.add_argument("--project", required=True, help="Project key (e.g. HBASE).")
    p_create.add_argument("--summary", required=True)
    g = p_create.add_mutually_exclusive_group(required=True)
    g.add_argument("--description")
    g.add_argument("--description-file")
    p_create.add_argument("--issuetype", default="Task")
    p_create.add_argument("--dry-run", action="store_true")

    p_comment = sub.add_parser("add-comment", help="Add a comment to an issue.")
    p_comment.add_argument("--issue", required=True, help="Issue key (e.g. HBASE-12345).")
    g2 = p_comment.add_mutually_exclusive_group(required=True)
    g2.add_argument("--body")
    g2.add_argument("--body-file")
    p_comment.add_argument("--dry-run", action="store_true")

    return parser


DISPATCH = {
    "whoami": cmd_whoami,
    "create-issue": cmd_create_issue,
    "add-comment": cmd_add_comment,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return DISPATCH[args.cmd](args)
    except PATError as e:
        print(str(e), file=sys.stderr)
        return 1
    except APIError as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
