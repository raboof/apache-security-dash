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

"""Read-only Gmail API access to the security inbox.

Uses the ``gmail.readonly`` scope (least privilege: list + read, never write or
delete) via ``google-api-python-client``. The OAuth2 credentials are read from
the environment (a local ``.env`` is loaded automatically); ``google-auth``
refreshes the access token on the first request.

The fetch layer mirrors the cheap-headers-then-full-body pattern: list message
ids, fetch just the ``Message-Id`` header per message (batched) for dedup, then
fetch the full RFC822 bytes (``format=raw``) only for the survivors. The raw
bytes parse with the same ``email`` machinery the IMAP path used.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from os import getenv

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()
load_dotenv(".claude-env")

# This tool only reads the inbox (gmail.readonly scope), so its credentials are
# named GMAIL_READONLY_* to make that explicit, and to keep them distinct from
# inbox_manager's read/write IMAP token (GMAIL_READWRITE_OAUTH_*) so both can
# live in one .env without colliding.
CLIENT_ID = getenv("GMAIL_READONLY_OAUTH_CLIENT_ID")
CLIENT_SECRET = getenv("GMAIL_READONLY_OAUTH_CLIENT_SECRET")
REFRESH_TOKEN = getenv("GMAIL_READONLY_OAUTH_REFRESH_TOKEN")

# Google's installed-app OAuth2 token endpoint + the single read-only scope.
_TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# The authenticated user's own mailbox.
_ME = "me"
# Gmail API page size and batch size ceilings (the API caps batches at 100).
_PAGE = 500
_BATCH = 50


def connect():
    """Build a read-only Gmail API service for the credentialed mailbox.

    ``google-api-python-client`` refreshes the access token on demand, so this
    does no network I/O itself.
    """
    missing = [
        name
        for name, value in {
            "GMAIL_READONLY_OAUTH_CLIENT_ID": CLIENT_ID,
            "GMAIL_READONLY_OAUTH_CLIENT_SECRET": CLIENT_SECRET,
            "GMAIL_READONLY_OAUTH_REFRESH_TOKEN": REFRESH_TOKEN,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing read-only Gmail OAuth2 credentials in environment "
            "(.env supported): " + ", ".join(missing)
        )

    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri=_TOKEN_URI,
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_messages(service, query: str | None = None) -> list[dict]:
    """All INBOX messages (most-recent first) as ``{id, threadId}`` dicts.

    ``query`` is an optional Gmail search expression (e.g. ``newer_than:30d``)
    to narrow the scan.
    """
    out: list[dict] = []
    messages = service.users().messages()
    request = messages.list(userId=_ME, labelIds=["INBOX"], q=query, maxResults=_PAGE)
    while request is not None:
        response = request.execute()
        out.extend(response.get("messages", []))
        request = messages.list_next(request, response)
    return out


@dataclass(frozen=True)
class MessageMeta:
    """The header + label fields ``fetch_metadata`` pulls for one message id.

    A metadata-only projection of a Gmail message (no body):
    the headers the head-detection / dedup / skip pass needs, plus the label ids.
    An id whose metadata fetch failed is an all-default instance.
    """

    message_id: str = ""
    subject: str = ""
    sender: str = ""  # the ``From`` header ("from" is a keyword)
    has_references: bool = False  # head detection only needs presence, not the value
    received: list[str] = field(default_factory=list)
    label_ids: list[str] = field(default_factory=list)


def thread_heads(messages: list[dict], metadata: dict[str, MessageMeta]) -> list[str]:
    """The ids of messages that start a thread (heads), order preserved.

    A message is a head when either:

    * it is the Gmail thread root (``id == threadId``):
      this keeps a standalone reply whose parent is not in this mailbox,
    * or it has no ``References`` header:
      a fresh message that Gmail nonetheless merged into an existing thread by subject.

    Genuine replies and forwards (``id != threadId`` *and* a ``References`` header) are dropped.
    ``References`` is used rather than ``In-Reply-To``
    because forwards carry ``References`` but often omit ``In-Reply-To``.

    The root test is Gmail's own threading heuristic, and it deliberately over-keeps:
    a reply Gmail could not thread (a parent in Spam or a rewritten subject)
    becomes a root of its own.
    """
    out: list[str] = []
    for message in messages:
        info = metadata.get(message["id"], MessageMeta())
        if message["id"] == message["threadId"] or not info.has_references:
            out.append(message["id"])
    return out


# Headers the head detection + dedup + skip pass needs, without the body.
_META_HEADERS = ["Message-Id", "Subject", "From", "References", "Received"]


def _parse_metadata(response: dict) -> MessageMeta:
    """Pull the headers + label ids we care about out of a metadata response."""
    message_id = subject = sender = ""
    has_references = False
    received: list[str] = []
    for header in response.get("payload", {}).get("headers", []):
        name = header.get("name", "").lower()
        value = header.get("value", "")
        if name == "message-id":
            message_id = value
        elif name == "subject":
            subject = value
        elif name == "from":
            sender = value
        elif name == "references":
            has_references = bool(value)
        elif name == "received":
            received.append(value)
    return MessageMeta(
        message_id=message_id,
        subject=subject,
        sender=sender,
        has_references=has_references,
        received=received,
        label_ids=response.get("labelIds", []) or [],
    )


def fetch_metadata(service, ids: list[str]) -> dict[str, MessageMeta]:
    """Map each Gmail id to its parsed metadata headers (no message body).

    A batched ``format=metadata`` pass does the bulk of the work; any id the
    batch drops (transient errors are not retried inside a batch) is re-fetched
    individually with retries, so coverage is reliable - a dropped id must never
    silently bypass the automation skips.
    An id that still fails maps to an empty ``MessageMeta``.
    """
    out: dict[str, MessageMeta] = {}
    messages = service.users().messages()

    def _collect(request_id, response, exception):
        if exception is None and response is not None:
            out[request_id] = _parse_metadata(response)

    for start in range(0, len(ids), _BATCH):
        batch = service.new_batch_http_request(callback=_collect)
        for gmail_id in ids[start : start + _BATCH]:
            batch.add(
                messages.get(
                    userId=_ME, id=gmail_id, format="metadata", metadataHeaders=_META_HEADERS
                ),
                request_id=gmail_id,
            )
        batch.execute()

    for gmail_id in ids:
        if gmail_id in out:
            continue
        try:
            response = messages.get(
                userId=_ME, id=gmail_id, format="metadata", metadataHeaders=_META_HEADERS
            ).execute(num_retries=3)
            out[gmail_id] = _parse_metadata(response)
        except Exception:  # noqa: BLE001 - a failed id maps to MessageMeta() (kept, not skipped)
            out[gmail_id] = MessageMeta()
    return out


def label_map(service) -> dict[str, str]:
    """Map Gmail label id -> name for the mailbox's *user* (custom) labels.

    System labels (INBOX, UNREAD, CATEGORY_*, ...) are omitted: the labels that
    matter for triage are the team's custom ``<pmc>/<date> <keywords>`` labels.
    Reading labels needs only the ``gmail.readonly`` scope.
    """
    response = service.users().labels().list(userId=_ME).execute()
    return {
        label["id"]: label.get("name", "")
        for label in response.get("labels", [])
        if label.get("type") == "user"
    }


def resolve_labels(label_ids: list[str], names: dict[str, str]) -> list[str]:
    """The custom-label names for ``label_ids``, order preserved, unknown dropped."""
    return [names[label_id] for label_id in label_ids if label_id in names]


def raw_bytes(service, gmail_id: str) -> bytes:
    """The full RFC822 bytes of a message (``format=raw``, base64url-decoded)."""
    message = service.users().messages().get(userId=_ME, id=gmail_id, format="raw").execute()
    return base64.urlsafe_b64decode(message["raw"].encode("ascii"))
