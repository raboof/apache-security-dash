#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""Sweep new security reports off a Ponymail list into report-cache/_inbox/.

The deterministic, token-light step of the triage-populate-cache SKILL. It
talks to the Ponymail HTTP API directly (reusing the ponymail-mcp cookie) and
writes message bodies + attachments to disk; only a compact funnel + table is
printed, so message bytes never enter the model's context.

Selection is by objective header facts only (see classify.py), no content
heuristics: a message is downloaded iff it is a thread head, addressed To a
known ASF security@ list, and not addressed (To/Cc) to a project private@ list
(plus a tiny automation-sender denylist). Whether a downloaded message is
actually a *new security report* is decided downstream by the triager reading
the text, not here.

The cheap stats call gives From + In-Reply-To for the whole window, so replies
and automation senders are dropped without fetching; the To/Cc check needs the
per-message fetch, done only for the remaining thread heads.

Incremental by default: a .sweep-state.json watermark + .seen.json index mean
each run only pulls messages newer than the last sweep (heads rejected on
To/Cc are recorded too, so they are not re-fetched). Use --full to rescan the
whole --since window.

Downloads land in <cache>/_inbox/<slug>/ as a single `report.md` (YAML
front-matter + body) plus an `attachments/` dir. The same SKILL (`file.py`)
then promotes a bundle to its canonical <date>/<pmc>/<keywords>/ path with a
≤3-word keyword tag. See SKILL.md for the full report-cache layout.

Examples:
    ./sweep.py                          # new reports since last sweep (2d window)
    ./sweep.py --since 7d --full        # rescan a week (catch-up)
    ./sweep.py --from someone@example.com --since 7d
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import AUTOMATION_SENDERS, pmc_from_to, select  # noqa: E402
from ponymail_api import (  # noqa: E402
    PonymailClient,
    PonymailError,
    emails_list,
    load_cookie,
    parse_from,
    slugify,
)
from report_md import BUNDLE_FILE, read as read_md, write as write_md  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
INBOX = "_inbox"
SEEN_FILE = ".seen.json"
STATE_FILE = ".sweep-state.json"


def map_timespan(value: str) -> str:
    """Translate friendly --since values to Ponymail's `d` parameter."""
    value = value.strip()
    if re.fullmatch(r"\d+d", value):
        return f"lte={value}"  # "last N days", per the Ponymail stats API
    return value  # yyyy-mm, dfr=.. dto=.., or a raw passthrough


def split_address(addr: str) -> tuple[str, str]:
    if "@" not in addr:
        raise SystemExit(f"--list must be a full address, got {addr!r}")
    prefix, domain = addr.split("@", 1)
    return prefix, domain


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    return default


def load_seen(cache: Path) -> set[str]:
    """Ponymail ids already processed. .seen.json is the source of truth; we
    also union ids found in existing report.md front-matter so a lost index
    never causes a duplicate download."""
    seen: set[str] = set(load_json(cache / SEEN_FILE, {}).get("ids", []))
    for bundle in cache.rglob(BUNDLE_FILE):
        try:
            meta, _ = read_md(bundle)
        except (OSError, ValueError):
            continue
        pid = meta.get("ponymail_id")
        if pid:
            seen.add(str(pid))
    return seen


def safe_attachment_name(name: str, fallback: str) -> str:
    base = os.path.basename(name or "").replace("\\", "_").strip()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or fallback
    return base[:120]


def unique_dir(parent: Path, slug: str) -> Path:
    candidate = parent / slug
    n = 2
    while candidate.exists():
        candidate = parent / f"{slug}-{n}"
        n += 1
    return candidate


def write_bundle(
    cache: Path, client: PonymailClient, msg, base_url: str, *, pmc: str | None = None
) -> Path:
    bundle = unique_dir(cache / INBOX, slugify(msg.ponymail_id))
    (bundle / "attachments").mkdir(parents=True, exist_ok=True)

    att_meta = []
    for att in msg.attachments:
        fname = safe_attachment_name(att.filename, att.hash)
        try:
            data = client.attachment_bytes(msg.ponymail_id, att)
            (bundle / "attachments" / fname).write_bytes(data)
        except PonymailError as exc:
            print(f"  ! attachment {fname} failed: {exc}", file=sys.stderr)
            fname = f"{fname} (download failed)"
        att_meta.append(
            {
                "filename": fname,
                "content_type": att.content_type,
                "size": att.size,
                "hash": att.hash,
            }
        )

    meta = {
        "subject": msg.subject,
        "reporter": msg.reporter_email,
        "reporter_name": msg.reporter_name,
        "message_id": msg.message_id,
        "ponymail_id": msg.ponymail_id,
        "archive_url": f"{base_url}/thread/{msg.ponymail_id}",
        "list": msg.list_addr,
        "to": msg.to_addr or None,
        "cc": msg.cc_addr or None,
        "date": msg.date,
        "references": msg.references or None,
        "attachments": att_meta,
        "tag": None,
        "pmc": pmc,
        "pmc_candidates": msg.pmc_recipients or None,
        "keywords": None,
        "wf": None,
        "handled": False,
        "status": "inbox",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
    write_md(bundle / BUNDLE_FILE, meta, msg.body)
    return bundle


def build_args():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--list",
        default="security@apache.org",
        help="Full list address (default: security@apache.org)",
    )
    ap.add_argument(
        "--since",
        default="2d",
        help="Query window: <N>d, yyyy-mm, or a raw Ponymail 'd' value (default: 2d)",
    )
    ap.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"Cache root ({DEFAULT_CACHE})",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max new reports to download (0 = no limit)",
    )
    ap.add_argument(
        "--from",
        dest="from_addr",
        default=None,
        help="Only cache reports from this sender address (e.g. triage one reporter)",
    )
    ap.add_argument(
        "--full",
        action="store_true",
        help="Rescan the whole window, ignore the watermark",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Select + fetch, but write nothing to disk",
    )
    ap.add_argument("--base-url", default=None, help="Override Ponymail base URL")
    return ap.parse_args()


def main() -> int:
    args = build_args()
    prefix, domain = split_address(args.list)

    cookie = load_cookie()
    if not cookie:
        print(
            "No Ponymail session cookie found. Run the ponymail-mcp `login` "
            "tool or set PONYMAIL_SESSION_COOKIE. Private lists need auth.",
            file=sys.stderr,
        )
        return 2

    client = PonymailClient(cookie=cookie, base_url=args.base_url)
    base_url = client.base_url
    cache = args.cache_dir
    if not args.dry_run:
        (cache / INBOX).mkdir(parents=True, exist_ok=True)

    try:
        stats = client.stats(prefix, domain, timespan=map_timespan(args.since))
    except PonymailError as exc:
        print(f"Discovery failed: {exc}", file=sys.stderr)
        return 1

    state = load_json(cache / STATE_FILE, {})
    watermark = 0 if args.full else int(state.get("last_epoch") or 0)
    seen = load_seen(cache)
    sender = (args.from_addr or "").lower()

    emails = emails_list(stats)
    max_epoch = watermark
    funnel: dict[str, int] = {}
    # Cheap pass: From + In-Reply-To are in the stats summary, so drop replies
    # and automation senders without fetching. To/Cc need the per-message fetch.
    heads = []
    for e in emails:
        epoch = int(e.get("epoch") or 0)
        max_epoch = max(max_epoch, epoch)
        _, addr = parse_from(e.get("from"))
        if (e.get("in-reply-to") or "").strip():
            funnel["reply"] = funnel.get("reply", 0) + 1
            continue
        if addr.lower() in AUTOMATION_SENDERS:
            funnel["automation-sender"] = funnel.get("automation-sender", 0) + 1
            continue
        if sender and addr.lower() != sender:
            continue
        mid = str(e.get("mid") or e.get("id") or "")
        if not mid or mid in seen or epoch <= watermark:
            continue
        heads.append((epoch, mid, e.get("subject") or ""))

    heads.sort()
    rows = []
    for _epoch, mid, subject in heads:
        if args.limit and len(rows) >= args.limit:
            break
        try:
            msg = client.email(mid)
        except PonymailError as exc:
            print(f"  ! fetch {mid} failed: {exc}", file=sys.stderr)
            continue
        keep, reason = select(
            msg.reporter_email, msg.to_addr, msg.cc_addr, msg.in_reply_to
        )
        funnel[reason] = funnel.get(reason, 0) + 1
        if not keep:
            if not args.dry_run:
                seen.add(mid)  # headers won't change; don't re-fetch
            continue
        pmc = pmc_from_to(msg.to_addr)
        if not args.dry_run:
            write_bundle(cache, client, msg, base_url, pmc=pmc)
            seen.add(mid)
        subj = (subject[:54] + "...") if len(subject) > 57 else subject
        rows.append(
            (
                slugify(mid)[:14],
                (msg.date or "")[:16],
                (msg.reporter_email or "?")[:24],
                (pmc or "-")[:14],
                str(len(msg.attachments)),
                subj,
            )
        )

    if not args.dry_run:
        (cache / SEEN_FILE).write_text(
            json.dumps({"ids": sorted(seen)}, indent=2) + "\n"
        )
        if max_epoch > watermark:
            (cache / STATE_FILE).write_text(
                json.dumps({"last_epoch": max_epoch}, indent=2) + "\n"
            )

    verb = "Would download" if args.dry_run else "Downloaded"
    print(
        f"Swept {args.list} ({args.since}{', full' if args.full else ''}): "
        f"{len(emails)} messages scanned, {len(heads)} thread heads fetched."
    )
    print("  funnel: " + ", ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
    print(
        f"{verb} {len(rows)} new report(s)"
        + ("" if args.dry_run else f" to {cache / INBOX}")
        + "."
    )
    if rows:
        print()
        print(
            f"  {'id':<14}  {'date':<16}  {'reporter':<24}  {'pmc':<14}  att  subject"
        )
        print(f"  {'-' * 14}  {'-' * 16}  {'-' * 24}  {'-' * 14}  ---  {'-' * 18}")
        for r in rows:
            print(
                f"  {r[0]:<14}  {r[1]:<16}  {r[2]:<24}  {r[3]:<14}  {r[4]:>3}  {r[5]}"
            )
        print()
        print(
            f"Next: read each report.md under {cache / INBOX}/, then file the genuine "
            "reports (./file.py <id> --keywords '...') or dismiss the rest (--remove)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
