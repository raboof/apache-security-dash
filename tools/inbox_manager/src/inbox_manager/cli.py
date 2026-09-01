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
import json
import re
import smtplib
import subprocess
import sys
import termios
import tty
from datetime import datetime
from email.policy import default
from email.utils import formataddr, parseaddr
from os import getenv
from urllib.request import urlopen

from dotenv import load_dotenv
from report_cache import artifacts
from report_cache import index as report_index
from report_cache.index import Disposition, Entry, Status
from report_cache.paths import cache_dir
from whimsy_lookup.fetch import (
    FetchError,
    fetch_committee_info,
    fetch_security_coordinates,
)
from whimsy_lookup.pmc_guess import guess_pmcs, pmc_for

# Load .env in the entry point, not as an import side effect, and before the
# imports below that read config at import time (imap's OAuth vars, gnureadline's
# TERMINFO_DIRS).
load_dotenv()

# Prefer the stdlib readline when it is GNU-backed.
# Fall back to gnureadline on libedit interpreters (uv's standalone Python),
# where input_with_prefill's prefill is a no-op.
# See the README "Terminal editing" section (TERMINFO_DIRS).
import readline as _stdlib_readline  # noqa: E402

from inbox_manager import email_utils, imap  # noqa: E402

if _stdlib_readline.backend == "readline":
    readline = _stdlib_readline
else:
    import gnureadline as readline

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
    text = " ".join(original[h] or "" for h in ("Subject", "From", "To", "Cc", "Delivered-To"))
    return guess_pmcs(text, committees, coordinates)


def prompt_for_pmc(committees, coordinates):
    """Ask the operator for a PMC slug and build its Pmc; None if left blank."""
    pmc_id = input("PMC? enter PMC id (blank to skip): ").strip().lower()
    if not pmc_id:
        return None
    return pmc_for(pmc_id, committees, coordinates)


def print_pmc(pmc):
    """Print the given PMC guesses and their security coordinates."""
    if not pmc:
        print("PMC: (could not guess)")
        return
    if pmc.security_model_source is None:
        print(f"PMC: {pmc.id} ({pmc.internal_security_contact})")
    else:
        print(f"PMC: {pmc.id} ({pmc.internal_security_contact}) {pmc.security_model_link}")


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


def file_message(inbox, original, uid, pmc, entry=None, prefix=""):
    """Attach the message's triage labels, then archive it out of the inbox.

    A label the message already carries is left alone.
    The rest split by whether the label exists in Gmail at all,
    because the two are different risks:
    an existing label is a known bucket,
    so the whole set takes one confirmation,
    while a label being created is permanent and silently wrong if mistyped,
    so each is offered prefilled and editable.

    Returns True if the message was filed, False if filing was abandoned.
    """
    labels = []
    for label in list(entry.labels) if entry else []:
        if label.startswith(prefix):
            labels.append(label)
        else:
            labels.append(f"{prefix}{label}")

    if not labels:
        pmc_name = pmc.id if pmc else ""
        labels = [f"{prefix}{pmc_name}/{email_utils.message_date(original)} "]

    on_message = gmail_labels(inbox, uid)
    todo = [label for label in labels if label not in on_message]
    if not todo:
        print(f"All {len(labels)} label(s) already on the message.")

    attach = []
    for label in todo:
        edited = input_with_prefill("Label: ", label).strip()
        if not edited:
            print(f"  skipped: {label}")
            continue
        attach.append(edited)

    if attach:
        print(f"{len(attach)} label(s) to attach:")
        for label in attach:
            print(f"  + {label}")
    else:
        print("Archive it (remove from inbox)? [y]es / [n]o: ", end="", flush=True)
        choice = read_key().lower()
        print()
        if choice != "y":
            print("left in inbox\n")
            return False

    for label in attach:
        if not inbox.folder_exists(label):
            inbox.create_folder(label)
    if attach:
        inbox.add_gmail_labels([uid], attach)
    # Archiving moves the message to ``[Gmail]/All Mail``:
    # in Gmail that drops the INBOX label while keeping every other label.
    # Removing the ``\\Inbox`` label directly does not work through imapclient: it quotes the value,
    # so Gmail treats it as a (non-existent) user label rather than the system one.
    inbox.move([uid], "[Gmail]/All Mail")
    print(f"attached {len(attach)} label(s), archived\n")
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


def gmail_labels(inbox, uid):
    """The Gmail labels currently on the message, as a set of str."""
    got = inbox.get_gmail_labels([uid]).get(uid, []) or []
    return {lbl.decode() if isinstance(lbl, bytes) else str(lbl) for lbl in got}


def _preview(msg, title):
    """Print a message envelope + rendered plain-text body for review."""
    print(f"--- {title} ---")
    print(f"From: {msg['From']}")
    print(f"To: {msg['To']}")
    if msg["Cc"]:
        print(f"Cc: {msg['Cc']}")
    if msg["Bcc"]:
        print(f"Bcc: {msg['Bcc']}")
    print(f"Subject: {msg['Subject']}")
    print()
    print(email_utils.body_to_text(msg))
    print()


def send_forward_and_receipt(inbox, original, uid, pmc, to_addr, forward_md, receipt_md, entry):
    """Preview a PMC forward (forward_md) + reporter receipt (receipt_md), send
    on confirmation, then file the report.

    The Markdown bodies are rendered to plain text + HTML; [e]dit edits the
    Markdown source and re-renders (so both parts stay in sync).
    Returns True if sent.
    """
    while True:
        fwd = email_utils.make_forward(
            original, forward_md, formataddr((TRIAGER_NAME, TRIAGER_EMAIL)), to_addr
        )
        receipt = email_utils.make_receipt(original, receipt_md)
        print()
        _preview(fwd, "Forward to PMC")
        _preview(receipt, "Receipt to reporter")
        print("Send forward + receipt? [y]es / [n]o / [e]dit: ", end="", flush=True)
        choice = read_key().lower()
        print()
        if choice == "y":
            send_messages(fwd, receipt)
            print(f"forwarded to {fwd['To']}, receipt sent to {receipt['To']}\n")
            file_message(inbox, original, uid, pmc, entry)
            return True
        if choice == "e":
            print("editing forward note...")
            forward_md = email_utils.edit_markdown_in_editor(forward_md)
            print("editing receipt...")
            receipt_md = email_utils.edit_markdown_in_editor(receipt_md)
            continue
        print("not sent\n")
        return False


def send_reply(inbox, original, uid, pmc, body_md, entry):
    """Preview a reply to the reporter (body_md), send on confirmation, then
    file the report. Returns True if sent.
    """
    while True:
        reply = email_utils.make_reject(original, body_md)
        print()
        _preview(reply, "Reply to reporter")
        print("Send reply? [y]es / [n]o / [e]dit: ", end="", flush=True)
        choice = read_key().lower()
        print()
        if choice == "y":
            send_messages(reply)
            print(f"reply sent to {reply['To']}\n")
            file_message(inbox, original, uid, pmc, entry, prefix="zzz-non-issue/")
            return True
        if choice == "e":
            body_md = email_utils.edit_markdown_in_editor(body_md)
            continue
        print("not sent\n")
        return False


def draft_artifact(entry: Entry | None, name: str) -> str:
    """The text of a triage-assess draft artifact for ``entry``, or ``""`` when absent.

    triage-assess writes ``summary.md`` / ``note.md`` / ``reason.md`` into
    the bundle through ``report-cache put-artifact``; here they pre-fill the forward /
    receipt / reject the operator previews. A missing artifact (an interactive report with
    no draft) reads as ``""`` so the template keeps its empty-marker behaviour and the
    operator writes it at the preview.
    """
    if entry is None or not entry.path:
        return ""
    return artifacts.read_artifact(cache_dir() / entry.path, name) or ""


def accept_message(inbox, original, uid, pmc, entry, committees, coordinates):
    """Forward to the PMC + reporter receipt.

    Prompts for the PMC when it could not be guessed.
    The forward pre-fills triage-assess's drafted ``summary.md`` and the entry's
    ``assessment_model`` (and the receipt's ``note.md``), or the forward-duplicate
    template when the entry records a ``duplicate_ponymail_link``; the operator
    reviews and can edit at the preview.
    Returns True if sent.
    """
    if pmc is None:
        pmc = prompt_for_pmc(committees, coordinates)
    contact = ""
    if pmc:
        contact = pmc.internal_security_contact
    to_addr = input_with_prefill("Forward to: ", contact).strip()
    if not to_addr:
        print("not forwarded - no recipient\n")
        return False
    summary = draft_artifact(entry, "summary.md")
    model = (entry.assessment_model or "") if entry else ""
    duplicate_of = str(entry.duplicate_ponymail_link or "") if entry else ""
    forward_md = email_utils.fill_forward_template(
        pmc, original, summary, model, TRIAGER_NAME, duplicate_of=duplicate_of
    )
    note = draft_artifact(entry, "note.md")
    reporter_name = entry.reporter_name if entry else None
    receipt_md = email_utils.fill_receipt_template(pmc, original, note, TRIAGER_NAME, reporter_name)
    return send_forward_and_receipt(
        inbox, original, uid, pmc, to_addr, forward_md, receipt_md, entry
    )


def reject_message(inbox, original, uid, pmc, entry):
    """reply that the report is out of scope.

    Built from templates/reject.md, pre-filled with triage-assess's drafted ``reason.md``,
    with the report quoted inline for reference. When there is no drafted reason (an
    interactive report), it opens in $EDITOR so the operator can write it.
    Files under 'zzz-non-issue/<pmc>/...'. Returns True if sent.
    """
    reason = draft_artifact(entry, "reason.md")
    reporter_name = entry.reporter_name if entry else None
    body_md = email_utils.fill_reject_template(pmc, original, reason, TRIAGER_NAME, reporter_name)
    if not reason:
        print("editing reject reply...")
        body_md = email_utils.edit_markdown_in_editor(body_md)
    return send_reply(inbox, original, uid, pmc, body_md, entry)


def suggested_action(entry: Entry | None) -> str | None:
    """The menu key the cache's triage state implies, or None to let the operator decide.

    Only an assessed report carries a disposition worth acting on, and each maps to the
    action that consumes what the skills recorded:
    ``track`` -> [f]ile under the recorded labels (the PMC has it, or nothing to send),
    ``forward`` -> [a]ccept (forward triage-assess's drafted summary + receipt),
    ``decline`` -> [r]eject (send its drafted reply).
    ``skip`` is out of the skill's scope, so it stays interactive.
    """
    if entry is None or entry.status is not Status.ASSESSED:
        return None
    return {
        Disposition.TRACK: "f",
        Disposition.FORWARD: "a",
        Disposition.DECLINE: "r",
    }.get(entry.disposition)


CVE_RESERVED_RE = re.compile(r"\s*(CVE-\d{4}-\d+)\s+reserved for\s+(\S+)", re.IGNORECASE)


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


CVE_ANNOUNCEMENT_RE = re.compile(r"^(CVE-\d{4}-\d+):")


def handle_cve_announcement(inbox, original, uid, current_labels):
    """True if this was a CVE announcement"""
    m = CVE_ANNOUNCEMENT_RE.match(str(original["Subject"] or ""))
    if not m:
        return False
    cve = m.group(1)
    current_label = ""
    for lbl in current_labels:
        if cve in lbl:
            current_label = lbl

    if current_label.startswith("zzz-resolved"):
        print(f"Auto-filing under existing label {current_label}")
        inbox.move([uid], current_label)
        return True

    json_url = f"https://cveawg.mitre.org/api/cve-id/{cve}"
    j = json.loads(urlopen(json_url).read())
    state = j.get("state")
    print(f"CVE state for {cve} is {state}")
    print(f"Review at https://cveprocess.apache.org/cve5/{cve}")
    # TODO also find and show ponymail link
    print(f"Action? [s]kip [m]ark '{current_label}' resolved")
    choice = read_key().lower()
    if choice in ("s", "\x03"):
        print("not marked\n")
    elif choice == "m":
        inbox.rename_folder(current_label, f"zzz-resolved/{current_label}")
        # TODO also remove from inbox
    return True


def handle_cve_reservation(inbox, original, uid, cve_id, pmc_id):
    """Attach a reserved CVE to one of the PMC's existing report labels.

    Lists the labels under ``<pmc_id>/``; when the user picks one, moves this
    message there and renames the label, replacing its date with the CVE id.
    """
    title = cve_title(original, cve_id)
    if title:
        print(f"{cve_id}: {title}")
    print(f"https://cveprocess.apache.org/cve5/{cve_id}")
    prefix = f"{pmc_id}/"

    all_labels = [name for _, _, name in inbox.list_folders() if name.startswith(prefix)]

    existing_cve_labels = [label for label in all_labels if label.startswith(prefix + cve_id)]
    if existing_cve_labels:
        print(f"Auto-filing under existing label {existing_cve_labels[0]}")
        inbox.move([uid], existing_cve_labels[0])
        return

    labels = sorted(label for label in all_labels if not label.startswith(prefix + "CVE"))
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
    if "/aaa" in label:
        new_label = label
    else:
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
HEADER_FETCH = "BODY.PEEK[HEADER.FIELDS (MESSAGE-ID REFERENCES FROM SUBJECT)]"

# The server's receive time, fetched so the inbox can be processed oldest-first.
INTERNAL_DATE = "INTERNALDATE"

# Fetched alongside the headers: Gmail's per-message and per-thread ids. They are
# the IMAP form of the Gmail API's `id` / `threadId` (hex of these), so the
# thread-head test `id == threadId` becomes `X-GM-MSGID == X-GM-THRID`.
GMAIL_ID_FETCH = ["X-GM-MSGID", "X-GM-THRID"]


def header_message(fetch_data):
    """Parse the header-only message from a HEADER.FIELDS fetch response."""
    for key, value in fetch_data.items():
        if key.startswith(b"BODY[HEADER"):
            return email.message_from_bytes(value, policy=default)
    return email.message_from_bytes(b"", policy=default)


def is_thread_head(data, headers):
    """Whether the message starts its thread - the same rule populate_cache uses.

    A message is a head when it is its Gmail thread's root
    (``X-GM-MSGID == X-GM-THRID``) or it carries no ``References`` (a fresh
    mail Gmail merged into an existing thread by subject, e.g. a recurring
    "Currently open security reports" digest). A genuine reply or forward - a
    different message and thread id *and* a ``References`` header - is not a
    head. ``References`` is used rather than ``In-Reply-To`` because forwards
    carry ``References`` but often omit ``In-Reply-To``.
    """
    return data.get(b"X-GM-MSGID") == data.get(b"X-GM-THRID") or not headers["References"]


def skip_reason(headers, is_head):
    """Why this message can be skipped from its headers alone, else None.

    CVE reservations are never skipped here - they are recognised from headers
    but handled with the full message.
    """
    if parse_cve_reservation(headers):
        return None
    if not is_head:
        return "not a thread head"
    subject = headers["Subject"] or ""
    if (
        subject.startswith("Comment added on CVE-")
        or subject.endswith("is now REVIEW")
        or subject.endswith("is now READY")
    ):
        return "CVE-process update"
    if headers["From"] == "VINCE <cert+donotreply@cert.org>":
        return "VINCE notifications are usually updates"
    if subject.startswith("svn commit: r"):
        return "SVN updates are usually updates"
    return None


def handle_message(inbox, uid, committees, coordinates, index):
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

    # What the triage skills already decided about this report, if anything.
    entry = index.get(original["Message-ID"] or "")
    pmc = pmc_for(entry.pmc, committees, coordinates) if entry and entry.pmc else None

    if not pmc:
        pmcs = guess_pmc(original, committees, coordinates)
        pmc = pmcs[0] if pmcs else None

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
    print_pmc(pmc)
    current_labels = gmail_labels(inbox, uid)
    print(f"Current labels: {current_labels}")

    if handle_cve_announcement(inbox, original, uid, current_labels):
        return

    suggested = suggested_action(entry)
    if suggested == "f":
        labels = ", ".join(entry.labels or []) or "(no label recorded)"
        print(f"Suggested action: [f]ile under {labels}")
    elif suggested == "a":
        print("Suggested action: [a]ccept (forward the drafted summary + receipt)")
    elif suggested == "r":
        print("Suggested action: [r]eject (send the drafted reply)")
    prompt = (
        "Action? [a]ccept / [r]eject / [s]kip / [j]unk / [f]ile under / "
        "[q]uit / [d]isplay / [c]onfused: "
    )
    if suggested:
        # Mark the key Enter runs, so the default is visible in the menu itself.
        prompt = prompt.replace(f"[{suggested}]", f"[{suggested.upper()}]", 1)
    print(prompt, end="", flush=True)
    while True:
        action = read_key().lower()
        # Enter takes the suggestion.
        # Every action it can reach either previews before sending or confirms before moving,
        # so this can never send mail.
        if action in ("\r", "\n") and suggested:
            action = suggested
            print()
        if action == "a":
            print()
            if accept_message(
                inbox,
                original,
                uid,
                pmc,
                entry,
                committees,
                coordinates,
            ):
                return
            print(prompt, end="", flush=True)
        if action == "r":
            print()
            if reject_message(inbox, original, uid, pmc, entry):
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
            if file_message(inbox, original, uid, pmc, entry):
                return
            print(prompt, end="", flush=True)
        if action == "c":
            print()
            inbox.move([uid], "zzz-non-issue/aaa-hack or license confusion")
            print("Filed under 'hack or license confusion'")
            return
        if action in ("q", "\x03"):
            sys.exit(0)
        if action == "d":
            print()
            subprocess.run(["less"], input=body, text=True)
            print(prompt, end="", flush=True)


# Everything a triage session needs before it touches the network: identity for
# signing forwards, the read/write IMAP OAuth token (imap.connect), and the
# mail-relay SMTP credentials (send_messages). Checked up front so a missing
# secret fails with a clear message instead of an opaque auth error mid-run.
REQUIRED_ENV = (
    "TRIAGER_NAME",
    "TRIAGER_EMAIL",
    *imap.REQUIRED_ENV,
    "APACHE_USER",
    "APACHE_PASS",
)


def main(argv: list[str] | None = None) -> int:
    missing = [name for name in REQUIRED_ENV if not getenv(name)]
    if missing:
        sys.exit(
            "Missing required environment variables (a local .env is loaded "
            "automatically): " + ", ".join(missing)
        )
    committees, coordinates = load_pmc_data()
    index = report_index.load(cache_dir())
    if index:
        print(f"(report-cache: {len(index)} reports indexed)")
    inbox = imap.connect()
    uids = inbox.search(["ALL"])
    fetched = inbox.fetch(uids, [HEADER_FETCH, INTERNAL_DATE, *GMAIL_ID_FETCH]) if uids else {}

    # Process oldest-first by server receive time. Gmail's INBOX UIDs are not in
    # date order, so a UID sort is not chronological - sort on INTERNALDATE.
    def _received(u):
        return (fetched.get(u) or {}).get(b"INTERNALDATE") or datetime.min

    for uid in sorted(uids, key=_received):
        data = fetched.get(uid)
        if data is None:
            continue
        hdrs = header_message(data)

        reason = skip_reason(hdrs, is_thread_head(data, hdrs))
        if reason:
            print(f"Next: {hdrs['Subject']}")
            print(f"skipping - {reason}\n")
            continue
        handle_message(inbox, uid, committees, coordinates, index)
