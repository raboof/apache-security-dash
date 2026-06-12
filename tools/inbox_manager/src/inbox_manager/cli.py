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

import email
from email.policy import default
from email.utils import formataddr, parseaddr
from inbox_manager import imap, email_utils
from os import getenv
import re
import readline
import smtplib
import subprocess
import sys
import termios
import tty

from whimsy_lookup.fetch import (
    FetchError,
    fetch_committee_info,
    fetch_security_coordinates,
)
from whimsy_lookup.pmc_guess import guess_pmcs, pmc_for

# Operator identity used to sign forwards and as the forward's From address.
TRIAGER_NAME = getenv("TRIAGER_NAME")
TRIAGER_EMAIL = getenv("TRIAGER_EMAIL")


def load_pmc_data():
    """Fetch the committee-info mapping + security coordinates once per run.

    Returns ``(committees, coordinates)``; both empty if Whimsy / the
    security-site are unreachable, so PMC guessing degrades to a no-op
    rather than breaking triage.
    """
    try:
        committees = fetch_committee_info()
        committees.pop("infrastructureadministrator", None)
        committees.pop("security", None)
        coordinates = fetch_security_coordinates()
        return committees, coordinates
    except FetchError as e:
        print(f"(PMC guessing disabled - {e})")
        return {}, {}


def guess_pmc(original, committees, coordinates):
    """Best-guess PMCs for a message (most likely first), fully resolved."""
    text = " ".join(
        original[h] or "" for h in ("Subject", "From", "To", "Cc", "Delivered-To")
    )
    return guess_pmcs(text, committees, coordinates)


def prompt_for_pmc(committees, coordinates):
    """Ask the operator for a PMC slug and build its Pmc; None if left blank."""
    pmc_id = input("PMC? enter PMC id (blank to skip): ").strip().lower()
    if not pmc_id:
        return None
    return pmc_for(pmc_id, committees, coordinates)


def private_list(pmc):
    """The PMC's private@ list, keyed off its mail_list (falls back to the slug)."""
    return f"private@{pmc.mail_list or pmc.id}.apache.org"


def print_pmc_guess(pmcs):
    """Print the given PMC guesses and their security coordinates."""
    if not pmcs:
        print("PMC: (could not guess)")
        return
    for pmc in pmcs:
        if pmc.security_link is None:
            print(f"PMC: {pmc.id} ({pmc.security_contact or private_list(pmc)})")
        else:
            print(
                f"PMC: {pmc.id} ({pmc.security_contact or private_list(pmc)}) {pmc.security_link}"
            )


def read_key():
    """Read a single keypress from the terminal without waiting for Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def input_with_prefill(prompt, text):
    """Like input(), but with an editable pre-filled value at the cursor."""
    readline.set_startup_hook(lambda: readline.insert_text(text))
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()


def file_message(inbox, original, uid, pmc, prefix=""):
    """File the message under a '<prefix><pmc>/<yyyy-mm-dd> <summary>' label.

    The prompt is pre-filled with the (optional) prefix, PMC name and message
    date so the user only types the summary (and can edit the prefix). If the
    resulting label already exists, lets the user add to it or pick a different
    one. Filing moves the message out of the inbox, mirroring the other actions.

    Returns True if the message was filed, False if filing was abandoned.
    """
    pmc_name = pmc.id if pmc else ""
    label = input_with_prefill(
        "File under label: ",
        f"{prefix}{pmc_name}/{email_utils.message_date(original)} ",
    ).strip()
    if not label:
        print("not filed - no label\n")
        return False

    while inbox.folder_exists(label):
        print(f"Label already exists: {label}")
        print(
            "  [a]dd to it / [c]hoose a different label / [s]kip filing: ",
            end="",
            flush=True,
        )
        choice = read_key().lower()
        print()
        if choice == "a":
            break
        if choice in ("s", "\x03"):
            print("not filed\n")
            return False
        if choice == "c":
            label = input_with_prefill("File under label: ", label).strip()
            if not label:
                print("not filed - no label\n")
                return False

    if not inbox.folder_exists(label):
        inbox.create_folder(label)
    inbox.move([uid], label)
    print(f"filed under: {label}\n")
    return True


def send_messages(*messages):
    """Open a fresh authenticated SMTP connection, send the messages, close it.

    A connection is made per send rather than held open for the whole triage
    session - an idle connection spanning the review of many messages gets
    dropped by the server and fails when a send finally happens.
    """
    with smtplib.SMTP_SSL("mail-relay.apache.org") as smtp:
        smtp.login(getenv("APACHE_USER"), getenv("APACHE_PASS"))
        for msg in messages:
            smtp.send_message(msg)


def accept_message(inbox, original, uid, pmc, committees, coordinates):
    """Accept the report: forward it to the PMC and acknowledge the reporter.

    Builds a hardened forward (templates/forward.md, to the PMC's security
    contact) plus a receipt to the reporter(s) (templates/receipt.md, from
    security@apache.org). Both are previewed and only sent on confirmation,
    after which the report is filed under a label like the 'file' action.
    Prompts for the PMC when it could not be guessed. Returns True if they
    were sent, False if abandoned.
    """
    if pmc is None:
        pmc = prompt_for_pmc(committees, coordinates)
    contact = ""
    if pmc:
        contact = pmc.security_contact or private_list(pmc)
    to_addr = input_with_prefill("Forward to: ", contact).strip()
    if not to_addr:
        print("not forwarded - no recipient\n")
        return False

    # TODO: pick up the summary and model from the triage-assess skill's output
    # when available; for now both are left empty (fill_forward_template then
    # also omits the AI disclaimer).
    intro = email_utils.fill_forward_template(pmc, "", "", TRIAGER_NAME)
    fwd = email_utils.make_forward(
        original, intro, formataddr((TRIAGER_NAME, TRIAGER_EMAIL)), to_addr
    )
    receipt = email_utils.make_receipt(original, pmc, TRIAGER_NAME)

    while True:
        print()
        print("--- Forward to PMC ---")
        print(f"From: {fwd['From']}")
        print(f"To: {fwd['To']}")
        if fwd["Cc"]:
            print(f"Cc: {fwd['Cc']}")
        print(f"Subject: {fwd['Subject']}")
        print()
        print(email_utils.body_to_text(fwd))
        print()
        print("--- Receipt to reporter ---")
        print(f"From: {receipt['From']}")
        print(f"To: {receipt['To']}")
        print(f"Bcc: {receipt['Bcc']}")
        print(f"Subject: {receipt['Subject']}")
        print()
        print(email_utils.body_to_text(receipt))
        print("\nSend forward + receipt? [y]es / [n]o / [e]dit: ", end="", flush=True)
        choice = read_key().lower()
        print()
        if choice == "y":
            send_messages(fwd, receipt)
            print(f"forwarded to {fwd['To']}, receipt sent to {receipt['To']}\n")
            file_message(inbox, original, uid, pmc)
            return True
        if choice == "e":
            print("editing forward body...")
            fwd = email_utils.edit_body_in_editor(fwd)
            print("editing receipt body...")
            receipt = email_utils.edit_body_in_editor(receipt)
            continue
        print("not sent\n")
        return False


def reject_message(inbox, original, uid, pmc):
    """Reject the report: reply to the reporter that it is out of scope.

    Builds a reply from templates/reject.md with the original report quoted
    inline for reference, opens it in $EDITOR so the operator can fill in the
    project-specific reasoning, then previews and sends on confirmation. After
    sending, files the report under 'zzz-non-issue/<pmc>/<date> <name>'.
    Returns True if it was sent, False if abandoned.
    """
    reject = email_utils.make_reject(original, pmc, TRIAGER_NAME)
    edit = True  # opened in the editor up front so the reasoning gets filled in
    while True:
        if edit:
            print("editing reject reply...")
            reject = email_utils.edit_body_in_editor(reject)
            edit = False
        print()
        print("--- Reject reply to reporter ---")
        print(f"From: {reject['From']}")
        print(f"To: {reject['To']}")
        if reject["Cc"]:
            print(f"Cc: {reject['Cc']}")
        print(f"Bcc: {reject['Bcc']}")
        print(f"Subject: {reject['Subject']}")
        print()
        print(email_utils.body_to_text(reject))
        print("\nSend reject? [y]es / [n]o / [e]dit: ", end="", flush=True)
        choice = read_key().lower()
        print()
        if choice == "y":
            send_messages(reject)
            print(f"reject sent to {reject['To']}\n")
            file_message(inbox, original, uid, pmc, prefix="zzz-non-issue/")
            return True
        if choice == "e":
            edit = True
            continue
        print("not sent\n")
        return False


CVE_RESERVED_RE = re.compile(
    r"\s*(CVE-\d{4}-\d+)\s+reserved for\s+(\S+)", re.IGNORECASE
)


def parse_cve_reservation(original):
    """``(cve_id, pmc_id)`` if `original` is a cveprocess reservation, else None."""
    name, addr = parseaddr(original["From"] or "")
    if addr.lower() != "security@apache.org" or "cveprocess" not in name.lower():
        return None
    m = CVE_RESERVED_RE.match(str(original["Subject"] or ""))
    return (m.group(1), m.group(2)) if m else None


def cve_title(original, cve_id):
    """The CVE title from the body - the first non-empty line after the id."""
    lines = email_utils.body_to_text(original).splitlines()
    for i, ln in enumerate(lines):
        if cve_id in ln:
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt.strip()
    return None


def handle_cve_reservation(inbox, original, uid, cve_id, pmc_id):
    """Attach a reserved CVE to one of the PMC's existing report labels.

    Lists the labels under ``<pmc_id>/``; when the user picks one, moves this
    message there and renames the label, replacing its date with the CVE id.
    """
    title = cve_title(original, cve_id)
    if title:
        print(f"{cve_id}: {title}")
    prefix = f"{pmc_id}/"
    labels = sorted(
        name
        for _, _, name in inbox.list_folders()
        if name.startswith(prefix) and not name.startswith(prefix + "CVE")
    )
    if not labels:
        print(f"no existing labels under '{prefix}' - skipping\n")
        return
    for i, name in enumerate(labels, 1):
        print(f"  [{i}] {name}")
    choice = input(f"Attach {cve_id} to which label? [number] / [s]kip: ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(labels)):
        print("skipped\n")
        return
    label = labels[int(choice) - 1]
    new_label = re.sub(r"(?<=/)\d{4}-\d{2}-\d{2}", cve_id, label, count=1)
    suffix = " wf cve-allocation"
    if new_label.lower().endswith(suffix):
        new_label = new_label[: -len(suffix)]
    if new_label != label:
        inbox.rename_folder(label, new_label)
    inbox.move([uid], new_label)
    print(f"moved to {new_label}\n")


# Header fields sufficient to decide the body-free skips below (and to detect
# CVE reservations), so replies/noise are dropped without downloading bodies.
HEADER_FETCH = "BODY.PEEK[HEADER.FIELDS (IN-REPLY-TO REFERENCES FROM SUBJECT)]"


def header_message(fetch_data):
    """Parse the header-only message from a HEADER.FIELDS fetch response."""
    for key, value in fetch_data.items():
        if key.startswith(b"BODY[HEADER"):
            return email.message_from_bytes(value, policy=default)
    return email.message_from_bytes(b"", policy=default)


def skip_reason(headers):
    """Why this message can be skipped from its headers alone, else None.

    CVE reservations are never skipped here - they are recognised from headers
    but handled with the full message.
    """
    if parse_cve_reservation(headers):
        return None
    if (headers["Subject"] or "").startswith("Comment added on CVE-") or (
        headers["Subject"] or ""
    ).endswith("is now REVIEW"):
        return "not a fresh thread"
    if headers["In-Reply-To"] or headers["References"]:
        return "not a fresh thread"
    if (headers["Subject"] or "").startswith("Re: "):
        return "not a fresh thread"
    if headers["From"] == "VINCE <cert+donotreply@cert.org>":
        return "VINCE notifications are usually updates"
    if (headers["Subject"] or "").startswith("svn commit: r"):
        return "SVN updates are usually updates"
    return None


def handle_message(inbox, uid, committees, coordinates):
    resp = inbox.fetch([uid], ["BODY.PEEK[]"])

    if uid not in resp:
        print("no longer in inbox, skipping")
        return

    raw = resp[uid][b"BODY[]"]
    original = email.message_from_bytes(raw, policy=default)
    print(f"Next: {original['Subject']}")
    cve = parse_cve_reservation(original)
    if cve:
        handle_cve_reservation(inbox, original, uid, *cve)
        return

    body = email_utils.body_to_text(original)
    lines = body.splitlines()
    print()
    print("\n".join(lines[:10]))
    if len(lines) > 10:
        print(f"... ({len(lines) - 10} more lines, press [d] to view)")
    print()
    print(f"Subject: {original['Subject']}")
    print(f"From: {email_utils.reporter_from(original)}")
    print(f"To: {original['To']}")
    if original["Cc"]:
        print(f"Cc: {original['Cc']}")
    pmcs = guess_pmc(original, committees, coordinates)
    print_pmc_guess(pmcs)
    prompt = "Action? [a]ccept / [r]eject / [s]kip / [j]unk / [f]ile under / [q]uit / [d]isplay / [c]onfused: "
    print(prompt, end="", flush=True)
    while True:
        action = read_key().lower()
        if action == "a":
            print()
            if accept_message(
                inbox, original, uid, pmcs[0] if pmcs else None, committees, coordinates
            ):
                return
            print(prompt, end="", flush=True)
        if action == "r":
            print()
            if reject_message(inbox, original, uid, pmcs[0] if pmcs else None):
                return
            print(prompt, end="", flush=True)
        if action == "s":
            print("skipping - user requested\n")
            return
        if action == "j":
            # Moving to Gmail's Spam folder marks the message as spam and
            # removes it from the inbox in a single operation.
            print()
            inbox.move([uid], "[Gmail]/Spam")
            print("junked - moved to Spam\n")
            return
        if action == "f":
            print()
            if file_message(inbox, original, uid, pmcs[0] if pmcs else None):
                return
            print(prompt, end="", flush=True)
        if action == "c":
            print()
            inbox.move([uid], "zzz-non-issue/aaa-hack or license confusion")
            print("Filed under 'hack or license confusion'")
            return
        if action in ("q", "\x03"):
            exit(0)
        if action == "d":
            print()
            subprocess.run(["less"], input=body, text=True)
            print(prompt, end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    if not TRIAGER_NAME:
        sys.exit("TRIAGER_NAME is not set - it is required to sign forwarded reports")
    if not TRIAGER_EMAIL:
        sys.exit(
            "TRIAGER_EMAIL is not set - it is required as the From address on forwards"
        )
    committees, coordinates = load_pmc_data()
    inbox = imap.connect()
    uids = list(reversed(inbox.search(["ALL"])))
    headers = inbox.fetch(uids, [HEADER_FETCH]) if uids else {}
    for uid in uids:
        data = headers.get(uid)
        if data is None:
            continue
        hdrs = header_message(data)
        reason = skip_reason(hdrs)
        if reason:
            print(f"Next: {hdrs['Subject']}")
            print(f"skipping - {reason}\n")
            continue
        handle_message(inbox, uid, committees, coordinates)
