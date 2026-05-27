#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""Sweep new security reports off a Ponymail list into report-cache/_inbox/.

The heavy-I/O, fully-deterministic step of the triage-populate-cache SKILL.
It talks to the Ponymail HTTP API directly (reusing the ponymail-mcp session
cookie) and writes message bodies + attachments to disk. The only thing it
prints is a compact funnel + table, so message bytes never enter the
model's context.

Why a classifier: `security@apache.org` is a firehose (~1000 thread
heads/week) of spam, CVE-workflow automation, SVN/GitHub notifications and
outbound announcements around a small core of genuine inbound reports. One
cheap `stats` call returns every message's metadata + a body snippet;
classify.py keeps only external, non-automation thread heads whose subject
looks like a report (security/Apache keywords). Full bodies + attachments
are then fetched only for the survivors, where the To/Cc headers drop any
report already in a PMC's hands (private@<pmc> recipient) and auto-assign
the PMC from a security@<pmc> recipient.

Incremental by default: a .sweep-state.json watermark + .seen.json index
mean each run only pulls messages newer than the last sweep. Use --full to
reclassify the whole --since window (dedup still prevents re-download).

Downloads land in <cache>/_inbox/<slug>/ (report.txt, meta.yaml,
attachments/); a separate filing SKILL later promotes a bundle to its
canonical <date>/<pmc>/<keywords>/ path. See SKILL.md for the full
report-cache layout, which downstream SKILLs reuse.

Examples:
    ./sweep.py                          # new reports since last sweep (2d window)
    ./sweep.py --since 7d --full        # reclassify a full week (catch-up)
    ./sweep.py --since 7d --dry-run     # preview, write nothing
    ./sweep.py --no-keyword-filter      # denylist only (see the spam residue)
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import Rules  # noqa: E402
from ponymail_api import (  # noqa: E402
    PonymailClient,
    PonymailError,
    emails_list,
    load_cookie,
    parse_from,
    slugify,
)

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
    """Ponymail ids already downloaded. .seen.json is the source of truth;
    we also union ids found in existing meta.yaml so a lost index never
    causes a duplicate download."""
    seen: set[str] = set(load_json(cache / SEEN_FILE, {}).get("ids", []))
    for meta in cache.rglob("meta.yaml"):
        try:
            pid = yaml.safe_load(meta.read_text()).get("ponymail_id")
        except (ValueError, AttributeError):
            continue
        if pid:
            seen.add(str(pid))
    return seen


def build_reply_index(emails: list[dict]) -> dict[str, list[dict]]:
    """Map a Message-ID to the messages that reply to it (by In-Reply-To)."""
    idx: dict[str, list[dict]] = {}
    for e in emails:
        irt = (e.get("in-reply-to") or "").strip()
        if irt:
            idx.setdefault(irt, []).append(e)
    return idx


def thread_has_answer(root_msgid: str, reporter: str, reply_index: dict) -> bool:
    """True if the report's thread already has a reply from someone other than
    the reporter, i.e. a team member already triaged it (a reporter's own
    follow-ups don't count). Walks the In-Reply-To chain within the window."""
    root_msgid = (root_msgid or "").strip()
    reporter = (reporter or "").lower()
    if not root_msgid:
        return False
    seen_ids, stack = set(), [root_msgid]
    while stack:
        for reply in reply_index.get(stack.pop(), []):
            cid = (reply.get("message-id") or "").strip()
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            _, addr = parse_from(reply.get("from"))
            if addr and addr.lower() != reporter:
                return True
            if cid:
                stack.append(cid)
    return False


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
    (bundle / "report.txt").write_text(msg.body, encoding="utf-8")

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
    with (bundle / "meta.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(meta, fh, sort_keys=False, allow_unicode=True, width=100)
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
        help=f"Cache root (default: {DEFAULT_CACHE})",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max new reports to download this run (0 = no limit)",
    )
    ap.add_argument(
        "--filter-config",
        type=Path,
        default=None,
        help="YAML overriding the classifier rules (see classify.py)",
    )
    ap.add_argument(
        "--include-internal",
        action="store_true",
        help="Keep @apache.org senders (CVE workflow, announcements)",
    )
    ap.add_argument(
        "--no-keyword-filter",
        action="store_true",
        help="Disable the report-subject signal (denylist only)",
    )
    ap.add_argument(
        "--full",
        action="store_true",
        help="Reclassify the whole window, ignoring the watermark",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch + classify, but write nothing to disk",
    )
    ap.add_argument(
        "--from",
        dest="from_addr",
        default=None,
        help="Only cache reports from this sender address (case-insensitive). "
        "Applied after the full window is fetched, so the already-answered "
        "check still sees other senders' replies in each thread. Implies "
        "--no-keyword-filter: a named sender is a trusted scope, so the "
        "spam/false-positive keyword filter is skipped.",
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

    rules = Rules.from_config(
        yaml.safe_load(args.filter_config.read_text()) if args.filter_config else None,
        include_internal=args.include_internal,
        # A specific --from sender is an explicit, trusted scope, so don't apply
        # the spam/false-positive keyword filter (it would drop genuine reports
        # whose subject lacks a security keyword, e.g. "XML Bomb (Billion
        # Laughs) DoS ..."). Reply / already-answered / recipient filters stay.
        require_signal=not args.no_keyword_filter and not args.from_addr,
    )
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

    emails = emails_list(stats)
    reply_index = build_reply_index(emails)
    max_epoch = watermark
    funnel: dict[str, int] = {}
    survivors = []
    sender = (args.from_addr or "").lower()
    for e in emails:
        epoch = int(e.get("epoch") or 0)
        max_epoch = max(max_epoch, epoch)
        _, addr = parse_from(e.get("from"))
        # --from restricts which reports we cache, but only after the reply
        # index (built from the whole window) is in place, so the
        # already-answered check still sees other senders' replies.
        if sender and addr.lower() != sender:
            continue
        keep, reason = rules.classify(
            addr, e.get("subject") or "", e.get("in-reply-to") or ""
        )
        # A report whose thread already drew a reply was triaged by another
        # team member; leave it to them.
        if keep and thread_has_answer(e.get("message-id"), addr, reply_index):
            keep, reason = False, "already-answered"
        funnel[reason] = funnel.get(reason, 0) + 1
        if not keep:
            continue
        mid = str(e.get("mid") or e.get("id") or "")
        if not mid or mid in seen or epoch <= watermark:
            continue
        survivors.append((epoch, mid, addr, e.get("subject") or ""))

    survivors.sort()
    if args.limit:
        survivors = survivors[: args.limit]

    rows = []
    skipped_private = 0
    for epoch, mid, addr, subject in survivors:
        try:
            msg = client.email(mid)
        except PonymailError as exc:
            print(f"  ! fetch {mid} failed: {exc}", file=sys.stderr)
            continue
        # Recipient rule: a report also addressed to a project's private@ list
        # is the PMC's to handle, not ours. (Verified from To/Cc headers.)
        if not msg.needs_triage:
            skipped_private += 1
            funnel["pmc-private"] = funnel.get("pmc-private", 0) + 1
            if not args.dry_run:
                seen.add(mid)
            continue
        pmc = msg.pmc_recipients[0] if len(msg.pmc_recipients) == 1 else None
        if not args.dry_run:
            write_bundle(cache, client, msg, base_url, pmc=pmc)
            seen.add(mid)
        natt = len(msg.attachments)
        subj = (subject[:54] + "...") if len(subject) > 57 else subject
        rows.append(
            (
                slugify(mid)[:14],
                (msg.date or "")[:16],
                (addr or "?")[:24],
                (pmc or "-")[:14],
                str(natt),
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
        f"{len(emails)} messages scanned."
    )
    print("  funnel: " + ", ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
    print(
        f"{verb} {len(rows)} new report(s)"
        + (f", skipped {skipped_private} already with a PMC" if skipped_private else "")
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
            f"Next: review each report.txt under {cache / INBOX}/, then file it "
            "with the triage filing SKILL (promotes to <date>/<pmc>/<keywords>/)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
