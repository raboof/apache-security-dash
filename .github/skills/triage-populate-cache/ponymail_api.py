"""Shared Ponymail HTTP-API client for the triage-populate-cache SKILL.

This module talks to the Ponymail Foal API (`/api/stats.lua`,
`/api/email.lua`) **directly**, reusing the session cookie the
ponymail-mcp server already caches at ~/.ponymail-mcp/session.json
(or the PONYMAIL_SESSION_COOKIE env var). The point is to keep message
bodies and attachment bytes out of the model's context: the helper
writes them to disk, and the calling script only emits a compact
summary. See SKILL.md for the rationale.

Not a SKILL entry point on its own; imported by sweep.py / file_report.py /
status.py.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.utils import parseaddr

DEFAULT_BASE_URL = "https://lists.apache.org"
SESSION_FILE = os.path.expanduser("~/.ponymail-mcp/session.json")
# ponymail-mcp expires its cached cookie after ~20h; mirror that here so we
# fail loudly instead of firing authenticated requests with a dead cookie.
SESSION_MAX_AGE_S = 20 * 60 * 60


class PonymailError(RuntimeError):
    """Raised for transport- or auth-level failures talking to Ponymail."""


def load_cookie() -> str | None:
    """Return the Ponymail session cookie, or None if none is available.

    Priority: PONYMAIL_SESSION_COOKIE env var, then the cached session file
    written by ponymail-mcp's `login` tool. An expired cached cookie is
    treated as absent.
    """
    env = os.environ.get("PONYMAIL_SESSION_COOKIE")
    if env:
        return env.strip()
    try:
        with open(SESSION_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    ts = data.get("timestamp")
    if ts and (time.time() * 1000 - ts) > SESSION_MAX_AGE_S * 1000:
        return None
    cookie = data.get("cookie")
    return cookie.strip() if cookie else None


def parse_from(value: str | None) -> tuple[str, str]:
    """Split a From-style header into (display_name, email)."""
    if not value:
        return "", ""
    name, addr = parseaddr(value)
    return name, addr


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str, *, fallback: str = "report") -> str:
    """Filesystem-safe slug. Used for inbox dir names and keyword paths."""
    slug = _UNSAFE.sub("-", (value or "").strip()).strip("-._")
    return slug or fallback


def thread_root_ids(stats: dict) -> list[str]:
    """Extract the message ids of thread roots from a stats.lua response.

    Ponymail's `thread_struct` is a forest: each top-level node is a thread
    head, with replies nested under `children`. We want only the heads. The
    node's message id lives under `tid` or `mid` depending on Ponymail
    version, so we try both. Returns [] when thread_struct is absent so the
    caller can fall back to the flat email list.
    """
    roots: list[str] = []
    for node in stats.get("thread_struct") or []:
        if not isinstance(node, dict):
            continue
        mid = node.get("tid") or node.get("mid") or node.get("id")
        if mid:
            roots.append(str(mid))
    return roots


def emails_list(stats: dict) -> list[dict]:
    """Normalise stats.lua `emails` (object or array) to a list of dicts."""
    emails = stats.get("emails")
    if not emails:
        return []
    if isinstance(emails, dict):
        return list(emails.values())
    return list(emails)


# Recipient routing. A report reaches the central security@apache.org archive
# either addressed directly or auto-forwarded from a per-PMC security@<pmc>
# alias (projects with a custom contact in apache/security-site's
# project-coordinates.json never reach here, so any security@<pmc> we see is a
# no-custom-contact project that needs central triage). A report also cc'd to a
# project's private@ list is already in that PMC's hands and is NOT ours.
_PMC_SECURITY_RE = re.compile(r"\bsecurity@([a-z0-9][a-z0-9-]*)\.apache\.org\b", re.I)
_PRIVATE_RE = re.compile(r"\bprivate@([a-z0-9][a-z0-9-]*)\.apache\.org\b", re.I)


@dataclass
class Attachment:
    hash: str
    filename: str
    content_type: str
    size: int
    body_b64: str | None = field(default=None, repr=False)


@dataclass
class Message:
    """A single fetched email, decoupled from Ponymail's raw JSON shape."""

    ponymail_id: str
    message_id: str
    subject: str
    from_raw: str
    reporter_name: str
    reporter_email: str
    date: str
    epoch: int | None
    list_addr: str
    tid: str
    in_reply_to: str
    references: str
    private: bool
    body: str
    attachments: list[Attachment]
    to_addr: str = ""
    cc_addr: str = ""
    raw: dict = field(repr=False, default_factory=dict)

    @property
    def is_thread_head(self) -> bool:
        """A direct report: no References header threading it onto another."""
        return not self.references.strip()

    @property
    def pmc_recipients(self) -> list[str]:
        """PMC slugs from any security@<pmc>.apache.org in To/Cc (excludes the
        central list). One match auto-identifies the report's project."""
        rcpt = f"{self.to_addr} {self.cc_addr}"
        pmcs = {m.lower() for m in _PMC_SECURITY_RE.findall(rcpt)}
        pmcs.discard("apache")
        return sorted(pmcs)

    @property
    def private_recipients(self) -> list[str]:
        """PMC slugs from any private@<pmc>.apache.org in To/Cc."""
        rcpt = f"{self.to_addr} {self.cc_addr}"
        return sorted({m.lower() for m in _PRIVATE_RE.findall(rcpt)})

    @property
    def needs_triage(self) -> bool:
        """A report reaching the central archive needs Security-team triage
        unless it's also addressed to a project's private@ list (the PMC is
        already looped in and owns it)."""
        return not self.private_recipients


class PonymailClient:
    def __init__(self, cookie: str | None = None, base_url: str | None = None):
        self.cookie = cookie
        self.base_url = (
            base_url or os.environ.get("PONYMAIL_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")

    # -- transport ---------------------------------------------------------
    def _request(self, path: str, params: dict, *, accept: str) -> bytes:
        query = {k: v for k, v in params.items() if v not in (None, "", False)}
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={"Accept": accept})
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:  # noqa: UP024 - explicit is fine
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise PonymailError(
                f"Ponymail API {exc.code} for {path}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise PonymailError(f"Cannot reach {url}: {exc.reason}") from exc

    def get_json(self, path: str, params: dict) -> dict:
        raw = self._request(path, params, accept="application/json")
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise PonymailError(f"Non-JSON response from {path}") from exc

    # -- API surface -------------------------------------------------------
    def stats(
        self,
        list_prefix: str,
        domain: str,
        *,
        timespan: str | None = None,
        emails_only: bool = True,
    ) -> dict:
        params = {"list": list_prefix, "domain": domain, "d": timespan}
        if emails_only:
            params["emailsOnly"] = "1"
        return self.get_json("/api/stats.lua", params)

    def email(self, mid: str) -> Message:
        data = self.get_json("/api/email.lua", {"id": mid})
        return self._to_message(data)

    def attachment_bytes(self, mid: str, att: Attachment) -> bytes:
        """Return the raw bytes for an attachment, straight from the API.

        Ponymail Foal serves attachment payloads from email.lua with
        `attachment=true&file=<sha256-hash>` (verified against the live API:
        it returns the raw bytes with the original content-type, not JSON).
        Bytes go straight to disk, never through the model.
        """
        if att.body_b64:  # older Ponymail variants inline base64
            import base64

            return base64.b64decode(att.body_b64)
        return self._request(
            "/api/email.lua",
            {"attachment": "true", "id": mid, "file": att.hash},
            accept="application/octet-stream",
        )

    # -- mapping -----------------------------------------------------------
    @staticmethod
    def _to_message(data: dict) -> Message:
        name, addr = parse_from(data.get("from"))
        # Ponymail returns `attachments` as a list of dicts in current Foal
        # ({filename, content_type, size, hash}); older versions keyed them
        # by hash. Normalise both to a list of (hash, meta) pairs.
        raw_atts = data.get("attachments") or []
        items = (
            raw_atts.items()
            if isinstance(raw_atts, dict)
            else ((a.get("hash"), a) for a in raw_atts if isinstance(a, dict))
        )
        attachments = []
        for h, meta in items:
            if not isinstance(meta, dict):
                continue
            attachments.append(
                Attachment(
                    hash=str(h or meta.get("hash") or ""),
                    filename=meta.get("filename") or str(h),
                    content_type=meta.get("content_type") or "application/octet-stream",
                    size=int(meta.get("size") or 0),
                    body_b64=meta.get("body") or meta.get("data"),
                )
            )
        return Message(
            ponymail_id=str(data.get("mid") or data.get("id") or ""),
            message_id=str(data.get("message-id") or ""),
            subject=data.get("subject") or "(no subject)",
            from_raw=data.get("from") or "",
            reporter_name=name,
            reporter_email=addr,
            date=str(data.get("date") or ""),
            epoch=int(data["epoch"]) if data.get("epoch") else None,
            list_addr=str(data.get("list") or data.get("list_raw") or ""),
            tid=str(data.get("tid") or ""),
            in_reply_to=str(data.get("in-reply-to") or ""),
            references=str(data.get("references") or ""),
            private=bool(data.get("private")),
            body=data.get("body") or "",
            attachments=attachments,
            to_addr=str(data.get("to") or ""),
            cc_addr=str(data.get("cc") or ""),
            raw=data,
        )
