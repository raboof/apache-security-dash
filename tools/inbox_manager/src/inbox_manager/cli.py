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

from inbox_manager import imap, email_utils, cache  # noqa: E402

# Prefer the stdlib readline when it is GNU-backed.
# Fall back to gnureadline on libedit interpreters (uv's standalone Python),
# where input_with_prefill's prefill is a no-op.
# See the README "Terminal editing" section (TERMINFO_DIRS).
import readline as _stdlib_readline  # noqa: E402

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


def print_pmc(pmc):
    """Print the given PMC guesses and their security coordinates."""
    if not pmc:
        print("PMC: (could not guess)")
        return
    if pmc.security_model_source is None:
        print(f"PMC: {pmc.id} ({pmc.internal_security_contact})")
    else:
        print(
            f"PMC: {pmc.id} ({pmc.internal_security_contact}) {pmc.security_model_link}"
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


def file_message(inbox, original, uid, pmc, prefix="", keywords=""):
    """File the message under a '<prefix><pmc>/<yyyy-mm-dd> <keywords>' label.

    If the resulting label already exists, lets the user add to it or pick a different one.
    Filing moves the message out of the inbox.

    Returns True if the message was filed, False if filing was abandoned.
    """
    pmc_name = pmc.id if pmc else ""
    label = input_with_prefill(
        "File under label: ",
        f"{prefix}{pmc_name}/{email_utils.message_date(original)} {keywords}",
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


def gmail_labels(inbox, uid):
    """The Gmail labels currently on the message, as a set of str."""
    got = inbox.get_gmail_labels([uid]).get(uid, []) or []
    return {lbl.decode() if isinstance(lbl, bytes) else str(lbl) for lbl in got}


def file_with_tags(inbox, uid, tags):
    """Attach every cache label the Gmail message is missing, then archive it.

    A Gmail message carries many labels, but only the ones already on it live in
    Gmail; the bundle's `tags` is the full set the triage tools recorded (for a
    digest, every report it covers). Offer to add the labels that are in `tags`
    but not yet on the message, then archive it out of the inbox (so the next
    populate-cache reconcile sweeps the bundle into handled/). Returns True if
    the operator confirmed, False if left in place.

    Archiving moves the message to ``[Gmail]/All Mail``: in Gmail that drops the
    INBOX label while keeping every other label. Removing the ``\\Inbox`` label
    directly does not work through imapclient - it quotes the value, so Gmail
    treats it as a (non-existent) user label rather than the system one.
    """
    tags = [t for t in (tags or []) if t]
    current = gmail_labels(inbox, uid)
    missing = [t for t in tags if t not in current]
    if missing:
        print(f"{len(missing)} cache label(s) not yet on the Gmail message:")
        for t in missing:
            print(f"  + {t}")
        prompt = "Attach them and archive? [y]es / [n]o: "
    else:
        print(f"All {len(tags)} cache label(s) already on the message.")
        prompt = "Archive it (remove from inbox)? [y]es / [n]o: "
    print(prompt, end="", flush=True)
    choice = read_key().lower()
    print()
    if choice != "y":
        print("left in inbox\n")
        return False
    for t in missing:
        if not inbox.folder_exists(t):
            inbox.create_folder(t)
    if missing:
        inbox.add_gmail_labels([uid], missing)
    inbox.move([uid], "[Gmail]/All Mail")  # archive: drops INBOX, keeps labels
    print(f"attached {len(missing)} label(s), archived\n")
    return True


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


def send_forward_and_receipt(
    inbox, original, uid, pmc, to_addr, forward_md, receipt_md, keywords
):
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
            file_message(inbox, original, uid, pmc, keywords=keywords)
            return True
        if choice == "e":
            print("editing forward note...")
            forward_md = email_utils.edit_markdown_in_editor(forward_md)
            print("editing receipt...")
            receipt_md = email_utils.edit_markdown_in_editor(receipt_md)
            continue
        print("not sent\n")
        return False


def send_reply(inbox, original, uid, pmc, body_md, keywords):
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
            file_message(
                inbox, original, uid, pmc, prefix="zzz-non-issue/", keywords=keywords
            )
            return True
        if choice == "e":
            body_md = email_utils.edit_markdown_in_editor(body_md)
            continue
        print("not sent\n")
        return False


def accept_message(
    inbox, original, uid, pmc, keywords, bundle, committees, coordinates
):
    """Forward to the PMC + reporter receipt.

    The forward summary/model are read lazily in this method.
    An edit the operator makes to summary.md while deciding is picked up.
    Prompts for the PMC when it could not be guessed.
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
    summary = bundle.fragment("summary.md") if bundle else ""
    model = bundle.model if bundle else ""
    forward_md = email_utils.fill_forward_template(
        pmc, original, summary, model, TRIAGER_NAME
    )
    note = ""
    receipt_md = email_utils.fill_receipt_template(pmc, original, note, TRIAGER_NAME)
    return send_forward_and_receipt(
        inbox, original, uid, pmc, to_addr, forward_md, receipt_md, keywords
    )


def reject_message(inbox, original, uid, pmc, keywords, bundle):
    """reply that the report is out of scope.

    Built from templates/reject.md and opened in $EDITOR so the operator can fill in the project-specific reasoning,
    with the report quoted inline for reference.
    The reason draft (`bundle`) is read here, at send time, not when the action menu was shown,
    so a mid-decision edit to reason.md is picked up.
    Files under 'zzz-non-issue/<pmc>/...'. Returns True if sent.
    """
    reason = bundle.fragment("reason.md") if bundle else ""
    body_md = email_utils.fill_reject_template(pmc, original, reason, TRIAGER_NAME)
    print("editing reject reply...")
    body_md = email_utils.edit_markdown_in_editor(body_md)
    return send_reply(inbox, original, uid, pmc, body_md, keywords)


def handle_cached(inbox, original, uid, bundle, committees, coordinates):
    """Act on a message the triage SKILLs have already dispositioned.

    Dispatches on the bundle's `status`: send the ready drafts for a forward or
    push-back, or just file/junk the no-send dispositions. Every send and every
    move is still operator-confirmed. Returns True when the cache disposition
    was driven (caller stops), False to fall back to interactive triage (the
    drafts are missing, or the report is not assessed yet).
    """
    status = bundle.status
    tags = bundle.meta.get("tags") or []

    if status == "drafted-forward":
        return False

    if status == "drafted-reply":
        return False

    if status == "tracked":
        return False

    if status == "spam":
        return False

    if bundle.is_digest or bundle.is_non_issue:
        kind = "open-reports digest" if bundle.is_digest else "known non-issue"
        print(f"{kind} - nothing to send.")
        file_with_tags(inbox, uid, tags)
        return True

    # filed-but-unassessed / downloaded: no draft yet, let the operator triage.
    print(
        "in the cache but not assessed yet (run triage-assess) - triaging interactively\n"
    )
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


CVE_ANNOUNCEMENT_RE = re.compile(r"^(CVE-\d{4}-\d+):")


def handle_cve_announcement(inbox, original, current_labels):
    """True if this was a CVE announcement"""
    m = CVE_ANNOUNCEMENT_RE.match(str(original["Subject"] or ""))
    if not m:
        return False
    cve = m.group(1)
    current_label = ""
    for lbl in current_labels:
        if cve in lbl:
            current_label = lbl
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
    return (
        data.get(b"X-GM-MSGID") == data.get(b"X-GM-THRID") or not headers["References"]
    )


def skip_reason(headers, is_head):
    """Why this message can be skipped from its headers alone, else None.

    CVE reservations are never skipped here - they are recognised from headers
    but handled with the full message.
    """
    if parse_cve_reservation(headers):
        return None
    if not is_head:
        return "not a thread head"
    if (headers["Subject"] or "").startswith("Comment added on CVE-") or (
        headers["Subject"] or ""
    ).endswith("is now REVIEW"):
        return "CVE-process update"
    if headers["From"] == "VINCE <cert+donotreply@cert.org>":
        return "VINCE notifications are usually updates"
    if (headers["Subject"] or "").startswith("svn commit: r"):
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

    # Fetch LLM suggestions
    bundle = cache.lookup(original["Message-ID"], index)
    if bundle:
        # Some have bespoke handling defined
        if handle_cached(inbox, original, uid, bundle, committees, coordinates):
            return
        # Others provide pre-filled values in the regular flow.
        tags = bundle.meta.get("tags")
        keywords = tags[0].split(" ", 1)[1] if tags and " " in tags[0] else None
        pmc = pmc_for(bundle.pmc, committees, coordinates) if bundle.pmc else None
    else:
        keywords = ""
        pmc = None

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

    if handle_cve_announcement(inbox, original, current_labels):
        return

    if bundle:
        if bundle.status == "drafted-forward":
            print("Suggested action: [a]ccept")
        elif bundle.status == "drafted-reply":
            print("Suggested action: [r]eject")
        elif bundle.status == "filed" or bundle.status == "tracked":
            print(f"Suggested action: [f]ile under '{keywords}'")
        else:
            print(f"Suggested action: {bundle.status}")
    prompt = "Action? [a]ccept / [r]eject / [s]kip / [j]unk / [f]ile under / [q]uit / [d]isplay / [c]onfused: "
    print(prompt, end="", flush=True)
    while True:
        action = read_key().lower()
        if action == "a":
            print()
            if accept_message(
                inbox,
                original,
                uid,
                pmc,
                keywords,
                bundle,
                committees,
                coordinates,
            ):
                return
            print(prompt, end="", flush=True)
        if action == "r":
            print()
            if reject_message(inbox, original, uid, pmc, keywords, bundle):
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
            if file_message(inbox, original, uid, pmc, keywords=keywords):
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
    index = cache.load_index()
    if index:
        print(f"(report-cache: {len(index)} reports indexed)")
    inbox = imap.connect()
    uids = inbox.search(["ALL"])
    fetched = (
        inbox.fetch(uids, [HEADER_FETCH, INTERNAL_DATE, *GMAIL_ID_FETCH])
        if uids
        else {}
    )

    # Process oldest-first by server receive time. Gmail's INBOX UIDs are not in
    # date order, so a UID sort is not chronological - sort on INTERNALDATE.
    def _received(u):
        return (fetched.get(u) or {}).get(b"INTERNALDATE") or datetime.min

    for uid in sorted(uids, key=_received):
        data = fetched.get(uid)
        if data is None:
            continue
        hdrs = header_message(data)

        # A report already in the cache has been assessed; surface it even if
        # the head test would otherwise skip it (defensive).
        in_cache = bool(hdrs["Message-ID"] and hdrs["Message-ID"] in index)
        reason = None if in_cache else skip_reason(hdrs, is_thread_head(data, hdrs))
        if reason:
            print(f"Next: {hdrs['Subject']}")
            print(f"skipping - {reason}\n")
            continue
        handle_message(inbox, uid, committees, coordinates, index)
