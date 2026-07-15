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
"""CLI: create a Gmail draft with a plain-text body + file attachments.

    forward-draft create \\
        --to alice@apache.org --to bob@apache.org \\
        --cc security@apache.org --cc private@tooling.apache.org \\
        --subject "[GLASSWING] ASVS Tooling security scan results ..." \\
        --body-file body.txt \\
        --attach scan.zip --attach assessment.md

``--dry-run`` builds and validates the message (attachments exist, no
inline HTML, sizes) and prints the plan without touching the network.
The live path creates an **unsent** draft; a human reviews and sends it.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from forward_draft.credentials import Credentials, locate_credentials, refresh_access_token
from forward_draft.draft import build_mime, create_draft, guess_attachment_type


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="forward-draft", description=(__doc__ or "").split("\n\n", 1)[0]
    )
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="create an unsent Gmail draft with attachments")
    c.add_argument("--to", action="append", required=True, help="Primary recipient (repeatable)")
    c.add_argument("--cc", action="append", default=[], help="Cc recipient (repeatable)")
    c.add_argument("--subject", required=True, help="Subject line")
    c.add_argument(
        "--body-file", required=True, help="Path to a plain-text body file ('-' for stdin)"
    )
    c.add_argument(
        "--attach",
        action="append",
        default=[],
        dest="attachments",
        help="Path to a file to attach (repeatable)",
    )
    c.add_argument(
        "--credentials", help="OAuth credentials JSON (default: apache-magpie gmail-oauth.json)"
    )
    c.add_argument(
        "--dry-run", action="store_true", help="Validate + print the plan; do not create the draft"
    )
    return p.parse_args(argv)


def _read_body(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return pathlib.Path(path).expanduser().read_text(encoding="utf-8")


def cmd_create(args: argparse.Namespace) -> int:
    body = _read_body(args.body_file)

    # Validate attachments exist + report the plan before any network I/O.
    plan_lines = [
        "Draft plan (UNSENT — a human reviews and sends):",
        f"  To:      {', '.join(args.to)}",
        f"  Cc:      {', '.join(args.cc) or '(none)'}",
        f"  Subject: {args.subject}",
        f"  Body:    {len(body)} chars ({len(body.splitlines())} lines), text/plain",
        f"  Attachments ({len(args.attachments)}):",
    ]
    for att in args.attachments:
        p = pathlib.Path(att).expanduser()
        if not p.is_file():
            print(f"ERROR: attachment not found: {p}", file=sys.stderr)
            return 2
        maintype, subtype = guess_attachment_type(p)
        plan_lines.append(
            f"    - {p.name}  ({maintype}/{subtype}, {_human_size(p.stat().st_size)})"
        )
    if not args.attachments:
        plan_lines.append("    (none)")
    print("\n".join(plan_lines))

    # Build the MIME now so --dry-run catches a bad attachment / inline-html
    # before we ever hit the network.
    raw = build_mime(
        from_addr="(resolved from credentials at send time)",
        to=args.to,
        cc=args.cc,
        subject=args.subject,
        body=body,
        attachments=args.attachments,
    )
    print(f"  Built multipart/mixed message: {_human_size(len(raw))} raw.")

    if args.dry_run:
        print("\n--dry-run: not creating the draft.")
        return 0

    creds = Credentials.load(locate_credentials(args.credentials))
    access_token = refresh_access_token(creds)
    # Rebuild with the real From: now that we have the credentials.
    raw = build_mime(
        from_addr=creds.from_address,
        to=args.to,
        cc=args.cc,
        subject=args.subject,
        body=body,
        attachments=args.attachments,
    )
    result = create_draft(access_token, raw)
    draft_id = result.get("id", "?")
    msg_id = result.get("message", {}).get("id", "?")
    print(f"\nDraft created (UNSENT). From: {creds.from_address}")
    print(f"  Draft ID:   {draft_id}")
    print(f"  Gmail URL:  https://mail.google.com/mail/u/0/#drafts/{msg_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "create":
        return cmd_create(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
