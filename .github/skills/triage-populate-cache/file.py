#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""File or dismiss a report bundle from report-cache/_inbox/.

The agent-driven half of the triage-populate-cache SKILL. After `sweep.py`
spools candidate threads, the agent reads each bundle's `report.md` and calls
this script for each one:

  file:     ./file.py <id> [--pmc <slug>] --keywords "<up-to-3 words>"
            Moves the bundle to its canonical
            report-cache/<date>/<pmc>/<keywords>/ home and stamps the tag
            (<pmc>/<date> <keywords>) into the front-matter.

  dismiss:  ./file.py <id> --remove [--reason "<why>"]
            For a false positive (spam/phishing/not-a-report that the
            deterministic sweep cannot filter out). Deletes the bundle and
            records it in report-cache/.dismissed.json; keeps the id in
            .seen.json so the sweep never downloads it again.

Operates only on the local cache; never talks to Ponymail, never sends. The
workflow marker is NOT set here; it belongs to a later actioning phase.

Examples:
    ./file.py g3pt8531 --keywords "xxe digester file_read"   # pmc auto-detected
    ./file.py to82voon --pmc spark --keywords "info_disclosure rest api"
    ./file.py 0dys652d --remove --reason "phishing (account-update)"
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_md import BUNDLE_FILE, read as read_md, write as write_md  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
INBOX = "_inbox"
SEEN_FILE = ".seen.json"
DISMISSED_FILE = ".dismissed.json"

MAX_KEYWORDS = 3
KEYWORD_RE = re.compile(r"^[a-z0-9_]+$")


def slugify_dir(value: str, *, fallback: str = "report") -> str:
    """Directory-name slug: preserves [a-z0-9_], collapses other runs to '-'."""
    slug = re.sub(r"[^a-z0-9_]+", "-", (value or "").lower()).strip("-")
    return slug or fallback


def find_bundle(inbox: Path, ident: str) -> Path:
    """Locate the inbox bundle for `ident` (a ponymail id, a dir-name prefix,
    or the truncated id printed by the sweep). Errors on no/ambiguous match."""
    if not inbox.is_dir():
        raise SystemExit(f"No inbox at {inbox} - run the sweep first.")
    ident = ident.strip()
    matches = []
    for d in sorted(inbox.iterdir()):
        bundle_file = d / BUNDLE_FILE
        if not bundle_file.exists():
            continue
        try:
            meta, _ = read_md(bundle_file)
        except (OSError, ValueError):
            continue
        pid = str(meta.get("ponymail_id") or "")
        if (
            d.name == ident
            or pid == ident
            or d.name.startswith(ident)
            or pid.startswith(ident)
        ):
            matches.append(d)
    if not matches:
        raise SystemExit(f"No inbox bundle matching {ident!r}.")
    if len(matches) > 1:
        names = ", ".join(d.name for d in matches)
        raise SystemExit(f"{ident!r} is ambiguous, matches: {names}")
    return matches[0]


def resolve_date(meta: dict, override: str | None) -> str:
    if override:
        date = override.strip()
    else:
        # report date looks like "2026/05/24 06:43:54"; take the calendar day.
        date = (meta.get("date") or "")[:10].replace("/", "-")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise SystemExit(
            f"Could not derive a yyyy-mm-dd date (got {date!r}); pass --date."
        )
    return date


def parse_keywords(raw: str) -> list[str]:
    tokens = (raw or "").split()
    if not tokens:
        raise SystemExit("--keywords must contain at least one word.")
    if len(tokens) > MAX_KEYWORDS:
        raise SystemExit(
            f"--keywords accepts at most {MAX_KEYWORDS} words "
            f"(got {len(tokens)}: {tokens!r}). Simplify the tag."
        )
    bad = [t for t in tokens if not KEYWORD_RE.fullmatch(t)]
    if bad:
        raise SystemExit(
            f"Each keyword must be a single lowercase word ([a-z0-9_]+); "
            f"reject: {bad!r}."
        )
    return tokens


def unique_dir(path: Path) -> Path:
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}-{n}")
        n += 1
    return candidate


def add_seen(cache: Path, ponymail_id: str) -> None:
    """Keep the id in the sweep's dedup ledger so it is never re-downloaded."""
    path = cache / SEEN_FILE
    data = json.loads(path.read_text()) if path.exists() else {}
    ids = set(data.get("ids", []))
    ids.add(ponymail_id)
    path.write_text(json.dumps({"ids": sorted(ids)}, indent=2) + "\n")


def dismiss(cache: Path, bundle: Path, meta: dict, reason: str, dry_run: bool) -> int:
    pid = str(meta.get("ponymail_id") or "")
    record = {
        "ponymail_id": pid,
        "subject": meta.get("subject"),
        "reporter": meta.get("reporter"),
        "reason": reason,
        "dismissed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
    print(f"DISMISS {bundle.name}: {meta.get('subject')!r}")
    print(f"  reason: {reason}")
    if dry_run:
        print("(dry-run, nothing written)")
        return 0

    ledger = cache / DISMISSED_FILE
    records = json.loads(ledger.read_text()) if ledger.exists() else []
    records.append(record)
    ledger.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    add_seen(cache, pid)  # belt-and-suspenders: it is already there from the sweep
    shutil.rmtree(bundle)
    print(f"Dismissed and removed. Recorded in {ledger.relative_to(cache.parent)}.")
    return 0


def file_report(
    cache: Path,
    bundle: Path,
    meta: dict,
    body: str,
    pmc: str,
    keywords_raw: str,
    date_override: str | None,
    dry_run: bool,
) -> int:
    pmc = pmc.strip().lower()
    if not pmc:
        raise SystemExit(
            "No PMC: the sweep did not detect one from the headers, so pass --pmc "
            "(read the report body to determine the project)."
        )
    tokens = parse_keywords(keywords_raw)
    date = resolve_date(meta, date_override)
    kw_slug = slugify_dir("-".join(tokens))

    tag = f"{pmc}/{date} {' '.join(tokens)}"
    target = unique_dir(cache / date / pmc / kw_slug)

    print(f"{bundle.name}  ->  {target.relative_to(cache)}")
    print(f"  tag: {tag}")
    if dry_run:
        print("(dry-run, nothing written)")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(bundle), str(target))
    meta.update({"tag": tag, "pmc": pmc, "keywords": tokens, "status": "filed"})
    write_md(target / BUNDLE_FILE, meta, body)
    print(
        f"Filed. {len(list((target / 'attachments').glob('*')))} attachment(s) moved."
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("id", help="Ponymail id or dir-name prefix of the inbox bundle")
    ap.add_argument("--pmc", help="PMC slug (defaults to the sweep-detected pmc field)")
    ap.add_argument(
        "--keywords",
        help=f"Space-separated tag keywords (1-{MAX_KEYWORDS}, [a-z0-9_]+ each)",
    )
    ap.add_argument(
        "--remove",
        action="store_true",
        help="Dismiss a non-report: delete the bundle and record it as dismissed",
    )
    ap.add_argument("--reason", help="Why it is dismissed (used with --remove)")
    ap.add_argument("--date", help="Override report date (yyyy-mm-dd)")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument(
        "--dry-run", action="store_true", help="Show the action, write nothing"
    )
    args = ap.parse_args()

    cache = args.cache_dir
    bundle = find_bundle(cache / INBOX, args.id)
    meta, body = read_md(bundle / BUNDLE_FILE)

    if args.remove:
        if args.keywords or args.pmc:
            raise SystemExit("--remove does not take --keywords/--pmc.")
        return dismiss(cache, bundle, meta, args.reason or "non-report", args.dry_run)

    if not args.keywords:
        raise SystemExit(
            "--keywords is required to file (or pass --remove to dismiss)."
        )
    return file_report(
        cache,
        bundle,
        meta,
        body,
        args.pmc or meta.get("pmc") or "",
        args.keywords,
        args.date,
        args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
