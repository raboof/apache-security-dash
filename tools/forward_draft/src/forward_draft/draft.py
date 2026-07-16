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
"""Build a Gmail draft with a plain-text body plus file attachments.

The message is ``multipart/mixed``: a single ``text/plain`` body part
followed by one attachment part per file. This is **not** HTML and adds
**no** tracking — the body is transmitted verbatim as text/plain, links
are not rewrapped, and no ``multipart/alternative`` / ``text/html``
inline body is ever produced (see :func:`assert_no_inline_html`, which
the test suite exercises). It exists because the plain-text Gmail MCP
(and its Magpie ``oauth-draft`` backend) is deliberately locked to a
single text/plain part and cannot attach files.
"""

from __future__ import annotations

import base64
import email.message
import email.utils
import json
import mimetypes
import pathlib
import urllib.error
import urllib.request

from forward_draft.credentials import GMAIL_API

# Extension -> (maintype, subtype). Covers the scan-forward attachments
# (a scan .zip + an assessment .md) plus the other bundle sidecars an
# operator might attach. Anything not listed falls back to mimetypes,
# then application/octet-stream.
_EXT_TYPES: dict[str, tuple[str, str]] = {
    ".zip": ("application", "zip"),
    ".md": ("text", "markdown"),
    ".markdown": ("text", "markdown"),
    ".txt": ("text", "plain"),
    ".json": ("application", "json"),
    ".yml": ("application", "yaml"),
    ".yaml": ("application", "yaml"),
    ".csv": ("text", "csv"),
    ".pdf": ("application", "pdf"),
}


def guess_attachment_type(path: str | pathlib.Path) -> tuple[str, str]:
    """Return ``(maintype, subtype)`` for an attachment path.

    Pure: extension map first (deterministic for our known types), then
    stdlib ``mimetypes``, then ``application/octet-stream``.
    """
    suffix = pathlib.Path(path).suffix.lower()
    if suffix in _EXT_TYPES:
        return _EXT_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed and "/" in guessed:
        maintype, subtype = guessed.split("/", 1)
        return maintype, subtype
    return ("application", "octet-stream")


def assert_no_inline_html(msg: email.message.EmailMessage) -> None:
    """Raise if the message carries an inline ``text/html`` body part.

    An ``text/html`` *attachment* (Content-Disposition: attachment) is a
    file and is allowed; an *inline* html part is a tracking/rich-text
    body and is forbidden — this helper is the by-construction guard that
    the draft never grows an HTML alternative.
    """
    for part in msg.walk():
        if (
            part.get_content_type() == "text/html"
            and part.get_content_disposition() != "attachment"
        ):
            raise ValueError("refusing to build a draft with an inline text/html body part")


def build_mime(
    from_addr: str,
    to: list[str],
    cc: list[str],
    subject: str,
    body: str,
    attachments: list[str | pathlib.Path],
) -> bytes:
    """Build the raw RFC822 bytes of a plain-text draft with attachments.

    Body is a single ``text/plain`` part; each attachment becomes its own
    part (text/* attachments carried as text, everything else as binary).
    Raises ``FileNotFoundError`` for a missing attachment and ``ValueError``
    via :func:`assert_no_inline_html` if an inline html body ever appears.
    """
    msg = email.message.EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    # Plain-text body only — never add_alternative / text/html here.
    msg.set_content(body)

    for att in attachments:
        p = pathlib.Path(att).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"attachment not found: {p}")
        maintype, subtype = guess_attachment_type(p)
        if maintype == "text":
            # text/* attachments are carried as decoded text (implies
            # maintype=text); pass only the subtype.
            msg.add_attachment(p.read_text(encoding="utf-8"), subtype=subtype, filename=p.name)
        else:
            msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)
        # Also set the LEGACY Content-Type ``name`` parameter, mirroring the
        # modern Content-Disposition ``filename``. Apple Mail keys attachment
        # identity/display on ``Content-Type; name=`` first and falls back to a
        # generic name when it's absent — so multiple attachments with no
        # ``name`` collapse to the same fallback and render as one/identical
        # files. Setting it makes each attachment distinct in every client.
        # (``EmailMessage.add_attachment`` deliberately omits this legacy param.)
        msg.get_payload()[-1].set_param("name", p.name, header="Content-Type")

    assert_no_inline_html(msg)
    return bytes(msg)


def api_post(access_token: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{GMAIL_API}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 — fixed Google endpoint
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f"Gmail API {path} failed ({e.code}): {e.read().decode(errors='replace')}"
        ) from e


def create_draft(access_token: str, raw_bytes: bytes) -> dict:
    """POST the raw MIME to Gmail ``drafts.create``. Leaves the draft UNSENT."""
    raw_b64url = base64.urlsafe_b64encode(raw_bytes).decode().rstrip("=")
    return api_post(access_token, "/drafts", {"message": {"raw": raw_b64url}})
