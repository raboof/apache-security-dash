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

The ingest step of the triage-populate-cache SKILL.
It reads the security inbox through the Gmail API (read-only ``gmail.readonly`` scope),
and for every message it has not seen before writes one bundle into its flat, per-PMC home::

    report-cache/<pmc>/<date>-<message-id-slug>/       # PMC determined from a recipient address
    report-cache/_unsorted/<date>-<message-id-slug>/   # no (or an ambiguous) PMC in the headers

Each bundle is a directory made of:

* ``report.md`` - the structured report:
  YAML front-matter with the message's Gmail provenance (a ``report_cache.report_md.Header``),
  then the body rendered to Markdown.
* ``raw.eml`` - the verbatim RFC 5322 message (a safety net against parser / Markdown loss).
* ``attachments/`` - the decoded attachments, if any.

The bundle holds only what Gmail gives us.
A report's triage state is kept separately
and is read and written through the ``report-cache`` tool, never by touching its store directly;
this tool records each new download there as ``status: downloaded``,
with an unambiguous To/Cc PMC guess.

This tool is read-only on the mailbox (the ``gmail.readonly`` scope cannot modify or delete mail);
it only writes under ``report-cache/``.
Dedup keys on the RFC ``Message-ID`` (read from the index) so a re-run never duplicates a bundle.

On a full inbox scan it also deletes handled reports:
a report keeps its bundle only while its message sits in the inbox.
Once the team archives the message, its bundle and triage record are removed.
Use ``--no-delete`` to skip this step.

Examples::

    populate-cache                       # pull new reports from the inbox
    populate-cache --dry-run             # select + report, write nothing
    populate-cache --limit 5             # stop after 5 new bundles
    populate-cache --query newer_than:30d  # narrow the inbox scan
"""

from __future__ import annotations

import argparse
import email
import hashlib
import re
import shutil
import sys
from email.message import Message
from email.policy import default
from email.utils import parseaddr
from pathlib import Path

from report_cache import index
from report_cache.report_md import BUNDLE_FILE, Attachment, Header
from report_cache.report_md import write as write_report
from whimsy_lookup.fetch import FetchError, fetch_committee_info, fetch_security_coordinates

from populate_cache import email_utils, gmail, skip

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
UNSORTED = "_unsorted"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
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


def inbox_message_ids(metadata: dict[str, gmail.MessageMeta]) -> set[str]:
    """The RFC Message-IDs currently in the scanned inbox, from the metadata pass.

    A message whose metadata fetch failed contributes nothing (it has no Message-ID),
    which is why the delete-handled sweep only runs on a full inbox scan.
    """
    ids: set[str] = set()
    for info in metadata.values():
        mid = _clean_header(info.message_id)
        if mid:
            ids.add(mid)
    return ids


def delete_handled(
    cache: Path, idx: dict[str, index.Entry], inbox_ids: set[str], dry_run: bool
) -> list[str]:
    """Delete cached bundles whose message has left the inbox.

    A report stays in the Gmail inbox until the team archives it;
    once archived its Message-ID is no longer in ``inbox_ids``, so it has been handled.
    We delete the bundle and drop its triage record (and remove the now-empty ``<pmc>`` directory),
    rather than keeping a tombstone:
    the message is gone from the inbox, so a later scan will not re-download it.
    Mutates ``idx``.
    """
    removed: list[str] = []
    for mid, entry in list(idx.items()):
        if mid in inbox_ids:
            continue
        removed.append(entry.path)
        if dry_run:
            continue
        bundle = cache / entry.path
        if bundle.exists():
            shutil.rmtree(bundle)
        parent = bundle.parent
        if parent != cache and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
        del idx[mid]
    return removed


def reporter_name(original: Message[str, str]) -> str | None:
    """The reporter's display name, resolving the security@ list's 'via' rewrite.

    Seeds ``Entry.reporter_name``; the SKILL refines it from the signature.
    """
    name, _ = parseaddr(str(email_utils.reporter_from(original) or ""))
    return _clean_header(name) or None


def write_bundle(
    cache: Path, original: Message[str, str], raw: bytes, *, header: Header, pmc_slug: str | None
) -> Path:
    """Write one bundle into ``<pmc>/<date>-<message-id-slug>/`` and return its dir.

    ``report.md`` (the ``Header`` + body),
    ``raw.eml`` (the verbatim RFC822 message, a safety net against parser/Markdown loss),
    and ``attachments/``.
    The leaf is the Message-ID slug (a content hash when the Message-ID is absent or entirely
    unsafe), prefixed with the report's UTC day.
    """
    slug = slugify(header.message_id or "") or hashlib.sha1(raw).hexdigest()[:16]
    leaf = f"{email_utils.message_date(original)}-{slug}"
    bundle = unique_dir(cache / (pmc_slug or UNSORTED), leaf)
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
            Attachment(filename=fname, content_type=content_type, size=len(data), hash=digest)
        )

    header.attachments = att_meta
    write_report(bundle / BUNDLE_FILE, header, email_utils.body_to_text(original))
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
        "--query",
        default=None,
        help="Optional Gmail search to narrow the inbox scan (e.g. 'newer_than:30d')",
    )
    ap.add_argument(
        "--limit", type=int, default=0, help="Max new reports to download (0 = no limit)"
    )
    ap.add_argument("--dry-run", action="store_true", help="Select + report, but write nothing")
    ap.add_argument(
        "--no-delete",
        action="store_true",
        help="Skip deleting handled reports (those whose message left the inbox)",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = build_args(argv)
    cache = args.cache_dir

    # Both sources are required for triage and must not degrade silently:
    # committee-info resolves recipient hosts to PMC slugs (report routing),
    # and project-coordinates.json tells a real security@ / private@ list from a bare alias.
    # A fetch failure aborts the run rather than misrouting.
    try:
        committees = fetch_committee_info()
        coordinates = fetch_security_coordinates()
    except FetchError as exc:
        raise SystemExit(
            f"Cannot reach Whimsy / security-site (triage data unavailable): {exc}"
        ) from exc

    service = gmail.connect()
    label_names = gmail.label_map(service)
    messages = gmail.list_messages(service, args.query)
    metadata: dict[str, gmail.MessageMeta] = gmail.fetch_metadata(
        service, [m["id"] for m in messages]
    )
    # Only thread heads become reports;
    # replies belong to an already-ingested thread and are tracked by their shared label,
    # not as separate bundles.
    heads = gmail.thread_heads(messages, metadata)

    idx = index.load(cache)
    seen = set(idx)  # Message-IDs already cached; dedup reads the index, not report.md.

    # Cheap header pass: drop automation/notification heads, then dedup on Message-ID.
    # Every surviving head is downloaded -
    # deciding whether it is a genuine report is the SKILL's job.
    funnel: dict[str, int] = {"reply": len(messages) - len(heads)}
    survivors: list[str] = []
    for gmail_id in heads:
        message_meta = metadata.get(gmail_id, gmail.MessageMeta())
        reason = skip.skip_reason(message_meta)
        if reason:
            funnel[reason] = funnel.get(reason, 0) + 1
            continue
        message_id = _clean_header(message_meta.message_id)
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
        message_meta = metadata.get(gmail_id, gmail.MessageMeta())
        labels = gmail.resolve_labels(message_meta.label_ids, label_names)
        header = Header.from_message(original)
        header.gmail_id = gmail_id
        header.labels = labels
        guess = index.guess_pmcs(header, committees)
        pmc_slug = guess[0] if len(guess) == 1 else None
        if not args.dry_run:
            bundle = write_bundle(cache, original, raw, header=header, pmc_slug=pmc_slug)
            entry = index.Entry.from_report(cache, bundle, header, committees, coordinates)
            entry.reporter_name = reporter_name(original)
            if header.message_id:
                idx[header.message_id] = entry
        subject = _clean_header(original["Subject"])
        subj = (subject[:54] + "...") if len(subject) > 57 else subject
        _, addr = parseaddr(str(email_utils.reporter_from(original) or ""))
        rows.append(
            (
                (slugify(header.message_id or "") or "?")[:14],
                email_utils.message_date(original),
                (addr or "?")[:24],
                (pmc_slug or UNSORTED)[:14],
                str(sum(1 for _ in email_utils.extract_attachments(original))),
                subj,
            )
        )

    # Delete handled reports: a report stays in the inbox until handled,
    # so a cached bundle whose message is no longer in the inbox has been archived = handled.
    # Only safe on a full inbox scan, where inbox_ids is the complete current inbox;
    # a --query-narrowed scan would wrongly "handle" everything outside the window.
    removed: list[str] = []
    if args.no_delete:
        pass
    elif args.query:
        print("(delete skipped: the handled-report sweep needs a full INBOX scan, no --query)")
    else:
        removed = delete_handled(cache, idx, inbox_message_ids(metadata), args.dry_run)

    if not args.dry_run:
        index.write(cache, idx)

    verb = "Would download" if args.dry_run else "Downloaded"
    print(f"Swept INBOX: {len(messages)} scanned, {len(heads)} thread heads, {len(survivors)} new.")
    print("  funnel: " + ", ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
    print(f"{verb} {len(rows)} report(s)" + ("" if args.dry_run else f" to {cache}") + ".")
    if removed:
        removed_verb = "Would remove" if args.dry_run else "Removed"
        print(f"{removed_verb} {len(removed)} handled report(s) (left the inbox).")
    if rows:
        print()
        print(f"  {'id':<14}  {'date':<10}  {'reporter':<24}  {'pmc':<14}  att  subject")
        print(f"  {'-' * 14}  {'-' * 10}  {'-' * 24}  {'-' * 14}  ---  {'-' * 18}")
        for r in rows:
            print(f"  {r[0]:<14}  {r[1]:<10}  {r[2]:<24}  {r[3]:<14}  {r[4]:>3}  {r[5]}")
        print()
        print(
            "Next (triage-populate-cache SKILL): classify each downloaded bundle "
            "and place the _unsorted ones."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
