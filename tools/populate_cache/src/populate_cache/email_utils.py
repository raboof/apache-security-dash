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

"""Shared, read-only message-parsing primitives.

These helpers turn a parsed (or header-only) email into the plain values both
the ingest tool (``populate_cache``) and the disposition tool
(``inbox_manager``) need: the plain-text body, the real reporter address, the
message date, attachment bytes, and a header-only parse of an IMAP fetch.

The outbound, disposition-side message building (forwards, receipts, HTML
sanitisation, templates, SMTP) lives in ``inbox_manager.email_utils``, which
imports the shared names from here.
"""

import email
import re
from datetime import date
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime

from markdownify import markdownify as _markdownify

MAX_BODY_CHARS = 500_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _strip_controls(s):
    return _CONTROL.sub("", (s or "").replace("\r\n", "\n").replace("\r", "\n"))


def _header_value(s):
    """One-line, control-free version of an untrusted header for display/use."""
    return _strip_controls(s or "").replace("\n", " ").strip()


def _html_to_markdown(html):
    """Convert an HTML body to Markdown via markdownify.

    Used for HTML-only and multipart/alternative messages, where it keeps
    structure (lists, links, headings, code) that a plain regex strip loses.
    """
    return _markdownify(html or "", heading_style="ATX").strip()


def body_to_text(original):
    """Markdown / plain-text representation of a parsed message's body.

    Prefers the HTML part rendered to Markdown (richer structure, the usual
    multipart/alternative case), falling back to a real text/plain part, then
    to empty."""
    html_part = original.get_body(preferencelist=("html",))
    plain_part = original.get_body(preferencelist=("plain",))
    if html_part is not None:
        text = _html_to_markdown(html_part.get_content())
    elif plain_part is not None:
        text = plain_part.get_content()
    else:
        text = ""
    return _strip_controls(text)[:MAX_BODY_CHARS]


def reporter_from(original):
    """The reporter's address, resolving the security@ list's 'via' munging.

    A report arriving through security@apache.org has its From rewritten to
    'Name via security <security@apache.org>' with the real sender in Reply-To;
    in that case the Reply-To is returned, otherwise the original From.
    """
    _, addr = parseaddr(original["From"] or "")
    if addr.lower() == "security@apache.org" and original["Reply-To"]:
        return original["Reply-To"]
    return original["From"]


def message_date(original):
    """The message's Date as yyyy-mm-dd, falling back to today if unparsable."""
    raw = original["Date"]
    if raw:
        try:
            return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
    return date.today().strftime("%Y-%m-%d")


def extract_attachments(original):
    """Yield ``(filename, content_type, data)`` for each real attachment.

    Hands back the decoded bytes so a caller can write them next to a report
    bundle (the save-to-disk counterpart of inbox_manager's _copy_attachments).
    """
    for part in original.iter_attachments():
        data = part.get_payload(decode=True)
        if data is None:
            continue
        yield part.get_filename(), part.get_content_type(), data


def parse_headers(fetch_data):
    """Parse a header-only message from an IMAP ``HEADER.FIELDS`` fetch.

    The fetch response keys the header bytes under ``BODY[HEADER.FIELDS ...]``;
    return them parsed with the same policy used for full messages so header
    access (decoding, addressing) behaves identically.
    """
    for key, value in fetch_data.items():
        if key.startswith(b"BODY[HEADER"):
            return email.message_from_bytes(value, policy=default)
    return email.message_from_bytes(b"", policy=default)
