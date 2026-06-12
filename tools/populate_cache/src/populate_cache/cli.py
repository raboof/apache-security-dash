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

"""Download new security reports off the Gmail inbox into ``report-cache/``.

The ingest step of the triage-populate-cache SKILL. It reads the security inbox
through the Gmail API (read-only ``gmail.readonly`` scope), and for every
message it has not seen before writes one ``report.md`` bundle (YAML
front-matter + plain-text body + ``attachments/``) into its dated, per-PMC
home::

    report-cache/<date>/<pmc>/<message-id-slug>/      # PMC named by a
                                                      # security@<pmc> recipient
    report-cache/<date>/_unsorted/<message-id-slug>/  # no PMC in the headers

PMC routing uses the *address-domain* signal only (see ``pmc.tier1_pmcs``);
when the recipients name no project alias the bundle lands in ``_unsorted`` for
the SKILL's labelling step to place. Bundles are written with
``status: downloaded`` and ``keywords: null``; the SKILL later assigns the
label, finalises the leaf name and promotes the status.

This tool is read-only on the mailbox (the ``gmail.readonly`` scope cannot
modify or delete mail); it only writes under ``report-cache/``. Dedup keys on
the RFC ``Message-ID`` so a re-run never duplicates a bundle. Whether a
downloaded message is actually a genuine, in-scope report is decided downstream
by the triager reading the text.

On a full inbox scan it also reconciles the cache: a report stays in the inbox
until the team archives it, so a cached bundle whose message is no longer in the
inbox has been handled and is moved into ``report-cache/handled/`` (keeping its
``<date>/<pmc>/<leaf>`` path). The bundle stays inside the cache, so dedup still
sees it; ``--no-reconcile`` turns the sweep off.

Examples::

    populate-cache                       # pull new reports from the inbox
    populate-cache --dry-run             # select + report, write nothing
    populate-cache --limit 5             # stop after 5 new bundles
    populate-cache --query newer_than:30d  # narrow the inbox scan
"""

from __future__ import annotations

import argparse
import datetime
import email
import hashlib
import re
import shutil
import sys
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from populate_cache import email_utils, gmail, pmc, skip
from populate_cache.report_md import BUNDLE_FILE
from populate_cache.report_md import read as read_md
from populate_cache.report_md import write as write_md

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
UNSORTED = "_unsorted"
# Bundles whose message left the inbox (archived = handled by the team) are
# moved here, preserving their <date>/<pmc>/<leaf> path, to declutter the
# active queue while staying inside the cache so dedup still sees them.
HANDLED = "handled"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_LIST_ID = re.compile(r"<([^>]+)>")
_WS = re.compile(r"\s+")
_NON_HEADER = re.compile(r"[^\x20-\x7e\s]")  # non-printable ASCII, excluding whitespace


def _clean_header(value: str | None) -> str:
    """One-line, printable ASCII form of an RFC 822 header value."""
    text = _NON_HEADER.sub("", str(value or ""))
    return _WS.sub(" ", text).strip()


def slugify(value: str) -> str:
    """Filesystem-safe slug for the bundle dir, or ``""`` if nothing survives
    (the caller decides the fallback - see :func:`write_bundle`)."""
    return _UNSAFE.sub("-", (value or "").strip()).strip("-._")


def safe_attachment_name(name: str, fallback: str) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or fallback
    return base[:120]


def unique_dir(parent: Path, slug: str) -> Path:
    candidate = parent / slug
    n = 2
    while candidate.exists():
        candidate = parent / f"{slug}-{n}"
        n += 1
    return candidate


def load_seen_message_ids(cache: Path) -> set[str]:
    """RFC Message-IDs already in the cache, so a re-run never duplicates a
    bundle. The stable key is the Message-ID."""
    seen: set[str] = set()
    for bundle in cache.rglob(BUNDLE_FILE):
        try:
            meta, _ = read_md(bundle)
        except (OSError, ValueError):
            continue
        mid = meta.get("message_id")
        if mid:
            seen.add(str(mid))
    return seen


def inbox_message_ids(metadata: dict[str, dict]) -> set[str]:
    """The RFC Message-IDs currently in the scanned inbox, from the metadata
    pass. A message whose metadata fetch failed contributes nothing (it has no
    Message-ID), which is why reconciliation only runs on a full inbox scan."""
    ids: set[str] = set()
    for info in metadata.values():
        mid = _clean_header(info.get("message_id"))
        if mid:
            ids.add(mid)
    return ids


def reconcile_handled(cache: Path, inbox_ids: set[str], dry_run: bool) -> list[Path]:
    """Move bundles whose message left the inbox into ``handled/``.

    A report stays in the Gmail inbox until the team archives it; once archived
    its Message-ID is no longer in ``inbox_ids``, so it has been handled. We move
    the bundle under ``<cache>/handled/`` (keeping its ``<date>/<pmc>/<leaf>``
    path) rather than deleting it: it stays inside the cache, so the Message-ID
    dedup still finds it and it is never re-downloaded. Bundles already under
    ``handled/``, and any whose Message-ID we cannot read, are left alone.
    """
    moved: list[Path] = []
    for bundle_file in sorted(cache.rglob(BUNDLE_FILE)):
        rel = bundle_file.relative_to(cache)
        if rel.parts and rel.parts[0] == HANDLED:
            continue
        try:
            meta, _ = read_md(bundle_file)
        except (OSError, ValueError):
            continue
        mid = _clean_header(meta.get("message_id"))
        if not mid or mid in inbox_ids:
            continue
        source = bundle_file.parent
        rel_dir = source.relative_to(cache)
        moved.append(rel_dir)
        if dry_run:
            continue
        target = unique_dir(cache / HANDLED / rel_dir.parent, rel_dir.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    return moved


def list_id(original) -> str | None:
    """The list address from a List-Id header, formatted ``<security.apache.org>``;
    None when the header is absent."""
    raw = original["List-Id"]
    if not raw:
        return None
    m = _LIST_ID.search(str(raw))
    return f"<{m.group(1)}>" if m else None


def report_date(original) -> str:
    """The Date header as ``YYYY/MM/DD HH:MM:SS`` for the front-matter ``date``
    field (the schema shared with the Ponymail sweep)."""
    raw = original["Date"]
    if raw:
        try:
            return parsedate_to_datetime(raw).strftime("%Y/%m/%d %H:%M:%S")
        except (TypeError, ValueError):
            return _clean_header(raw)
    return ""


def date_dir(original) -> str:
    """The ``<date>`` path segment as ``YYYY-MM-DD`` (matches the cache layout)."""
    return email_utils.message_date(original)


def build_meta(original, *, pmc_slug, candidates, tags) -> dict:
    """The report.md front-matter for a Gmail-sourced report. ``ponymail_id`` /
    ``archive_url`` are null (no archive); ``keywords`` is filled by the SKILL's
    labelling step. ``tags`` are the message's Gmail labels - the custom triage
    labels already on it at download (e.g. a prior ``<pmc>/<date> <keywords>``,
    or a subject-CVE auto-label). The SKILL extends this same field as it labels,
    and a later tool reconciles it against Gmail."""
    reporter = email_utils.reporter_from(original) or original["From"] or ""
    name, addr = parseaddr(str(reporter))
    return {
        "subject": _clean_header(original["Subject"]) or "(no subject)",
        "reporter": addr or None,
        "reporter_name": name or None,
        "message_id": _clean_header(original["Message-ID"]) or None,
        "ponymail_id": None,
        "archive_url": None,
        "list": list_id(original),
        "to": _clean_header(original["To"]) or None,
        "cc": _clean_header(original["Cc"]) or None,
        "date": report_date(original),
        "references": _clean_header(original["References"]) or None,
        "attachments": [],  # filled by write_bundle
        "pmc": pmc_slug,
        "pmc_candidates": candidates or None,
        "collection": None,
        "cve": None,
        "keywords": None,
        "tags": tags or None,
        "wf": None,
        "handled": False,
        "status": "downloaded",
        "fetched_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }


def write_bundle(cache: Path, original, raw: bytes, *, pmc_slug, candidates, tags=None) -> Path:
    """Write one report.md bundle into
    ``<date>/<pmc-or-_unsorted>/<message-id-slug>/``: ``report.md`` (front-matter
    + body), ``raw.eml`` (the verbatim RFC822 message, kept as a safety net in
    case parsing/Markdown conversion ever drops something), and ``attachments/``.
    """
    # The slug is the Message-ID; fall back to a content hash when it is absent
    # or made entirely of unsafe characters (slugify would return "").
    message_id = _clean_header(original["Message-ID"])
    slug = slugify(message_id) or hashlib.sha1(raw).hexdigest()[:16]
    parent = cache / date_dir(original) / (pmc_slug or UNSORTED)
    bundle = unique_dir(parent, slug)
    (bundle / "attachments").mkdir(parents=True, exist_ok=True)
    (bundle / "raw.eml").write_bytes(raw)

    att_meta = []
    attachments_dir = bundle / "attachments"
    for filename, content_type, data in email_utils.extract_attachments(original):
        digest = hashlib.sha256(data).hexdigest()
        fname = safe_attachment_name(filename, digest)
        target = attachments_dir / fname
        n = 2
        while target.exists():
            p = Path(fname)
            fname = f"{p.stem}-{n}{p.suffix}"
            target = attachments_dir / fname
            n += 1
        target.write_bytes(data)
        att_meta.append(
            {
                "filename": fname,
                "content_type": content_type,
                "size": len(data),
                "hash": digest,
            }
        )

    meta = build_meta(original, pmc_slug=pmc_slug, candidates=candidates, tags=tags)
    meta["attachments"] = att_meta
    write_md(bundle / BUNDLE_FILE, meta, email_utils.body_to_text(original))
    return bundle


def build_args(argv):
    ap = argparse.ArgumentParser(
        prog="populate-cache",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"Cache root (default: {DEFAULT_CACHE})",
    )
    ap.add_argument(
        "--label",
        default="INBOX",
        help="Gmail label to sweep (default: INBOX)",
    )
    ap.add_argument(
        "--query",
        default=None,
        help="Optional Gmail search to narrow the scan (e.g. 'newer_than:30d')",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max new reports to download (0 = no limit)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Select + report, but write nothing to disk",
    )
    ap.add_argument(
        "--no-reconcile",
        action="store_true",
        help="Skip moving bundles whose message left the inbox into handled/",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = build_args(argv)
    cache = args.cache_dir

    known_slugs = pmc.load_known_slugs()
    if not known_slugs:
        print("(PMC routing degraded: committee-info unreachable, all -> _unsorted)")

    service = gmail.connect()
    label_names = gmail.label_map(service)
    messages = gmail.list_messages(service, args.label, args.query)
    metadata = gmail.fetch_metadata(service, [m["id"] for m in messages])
    # Only thread heads become reports; replies belong to an already-ingested
    # thread and are tracked by their shared label, not as separate bundles.
    heads = gmail.thread_heads(messages, metadata)
    seen = load_seen_message_ids(cache)

    # Cheap header pass: drop automation/notification heads, then dedup on
    # Message-ID. Every surviving head is downloaded - deciding whether it is a
    # genuine report is the SKILL's job.
    funnel: dict[str, int] = {"reply": len(messages) - len(heads)}
    survivors: list[str] = []
    for gmail_id in heads:
        info = metadata.get(gmail_id, {})
        reason = skip.skip_reason(info)
        if reason:
            funnel[reason] = funnel.get(reason, 0) + 1
            continue
        message_id = _clean_header(info.get("message_id"))
        if message_id and message_id in seen:
            funnel["already-seen"] = funnel.get("already-seen", 0) + 1
            continue
        funnel["new"] = funnel.get("new", 0) + 1
        survivors.append(gmail_id)
        if message_id:
            seen.add(message_id)
        if args.limit and len(survivors) >= args.limit:
            break

    rows = []
    for gmail_id in survivors:
        raw = gmail.raw_bytes(service, gmail_id)
        original = email.message_from_bytes(raw, policy=default)
        candidates = pmc.tier1_pmcs(f"{original['To'] or ''} {original['Cc'] or ''}", known_slugs)
        pmc_slug = candidates[0] if candidates else None
        tags = gmail.resolve_labels(metadata.get(gmail_id, {}).get("label_ids", []), label_names)
        if not args.dry_run:
            write_bundle(
                cache,
                original,
                raw,
                pmc_slug=pmc_slug,
                candidates=candidates,
                tags=tags,
            )
        subject = _clean_header(original["Subject"])
        subj = (subject[:54] + "...") if len(subject) > 57 else subject
        _, addr = parseaddr(str(email_utils.reporter_from(original) or ""))
        rows.append(
            (
                (slugify(_clean_header(original["Message-ID"])) or "?")[:14],
                date_dir(original),
                (addr or "?")[:24],
                (pmc_slug or UNSORTED)[:14],
                str(sum(1 for _ in email_utils.extract_attachments(original))),
                subj,
            )
        )

    # Reconcile: a report stays in the inbox until handled, so a cached bundle
    # whose message is no longer in the inbox has been archived = handled; move
    # it to handled/. Only safe on a full inbox scan, where inbox_ids is the
    # complete current inbox; a narrowed scan would wrongly "handle" everything
    # outside the window.
    full_scan = args.label == "INBOX" and not args.query
    handled: list[Path] = []
    if args.no_reconcile:
        pass
    elif not full_scan:
        print("(reconcile skipped: handled/ sweep needs a full INBOX scan, no --query)")
    else:
        handled = reconcile_handled(cache, inbox_message_ids(metadata), args.dry_run)

    verb = "Would download" if args.dry_run else "Downloaded"
    print(
        f"Swept {args.label}: {len(messages)} scanned, {len(heads)} thread heads, "
        f"{len(survivors)} new."
    )
    print("  funnel: " + ", ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
    print(f"{verb} {len(rows)} report(s)" + ("" if args.dry_run else f" to {cache}") + ".")
    if handled:
        moved_verb = "Would move" if args.dry_run else "Moved"
        print(f"{moved_verb} {len(handled)} handled report(s) (left the inbox) to {HANDLED}/.")
    if rows:
        print()
        print(f"  {'id':<14}  {'date':<10}  {'reporter':<24}  {'pmc':<14}  att  subject")
        print(f"  {'-' * 14}  {'-' * 10}  {'-' * 24}  {'-' * 14}  ---  {'-' * 18}")
        for r in rows:
            print(f"  {r[0]:<14}  {r[1]:<10}  {r[2]:<24}  {r[3]:<14}  {r[4]:>3}  {r[5]}")
        print()
        print(
            "Next (triage-populate-cache SKILL): label each downloaded bundle, "
            "place the _unsorted ones, and finalise."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
