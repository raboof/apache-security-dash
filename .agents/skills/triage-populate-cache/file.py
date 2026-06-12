#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""Label or set the disposition of a downloaded report bundle.

The agent-driven half of the triage-populate-cache SKILL. The `populate-cache`
tool downloads each new thread head into its dated home with `status:
downloaded`:

    report-cache/<date>/<pmc>/<message-id-slug>/        # PMC from a security@<pmc> recipient
    report-cache/<date>/_unsorted/<message-id-slug>/    # no PMC in the headers

The agent then reads each bundle's `report.md` and calls this script to give it
a disposition. NOTHING is deleted: every thread head stays in the cache, so its
Message-ID is always found by the tool's dedup pass and it is never downloaded
again.

  file:   ./file.py <id> [--pmc <slug>] --keywords "<words>" [--wf <state>]
          A report we triage. Renames the leaf from the message-id slug to the
          keyword slug, moves an _unsorted bundle under its <pmc>, stamps the
          tag (<pmc>/<date> <keywords>) and `status: filed`. Keywords run
          most-specific to most-generic. `--wf <state>` records what the report
          is waiting for (e.g. reporter, cve-allocation, non-issue-feedback); a
          report in a PMC's hands has no `wf`.

  spam:   ./file.py <id> --spam [--reason "<why>"]
          A non-report (spam / phishing / marketing / bounce). Stamps
          `status: spam` in place and keeps the bundle as a tombstone so the
          tool never re-downloads it. The body/attachments are left untouched.

  digest: ./file.py <id> --digest --pmc <slug> [--tag "<tag>" ...]
          A "Currently open security reports for <pmc>" summary. Not a report
          to assess: files it under <pmc>/digest/ (keywords: [digest]) and
          labels it with every covered report's tag (--tag, repeatable; each is
          a tag from email-classification/<pmc>/). Terminal (handled: true).

  non-issue: ./file.py <id> --non-issue <label-leaf> --pmc <slug>
          A known non-issue class, most often a CVE-in-a-dependency inquiry
          (--non-issue aaa-dependencies). Files under
          zzz-non-issue/<pmc>/<label-leaf>/ and tags it
          zzz-non-issue/<pmc>/<label-leaf>. The leaf is verbatim (not all start
          with aaa-).

Operates only on the local cache; never talks to a mailbox, never sends. Match
`<id>` against the message-id-slug directory name (a unique prefix works, e.g.
the truncated id the tool printed) or the RFC Message-ID.

Examples:
    ./file.py report-123    --keywords "xxe digester file_read"   # pmc auto-detected
    ./file.py 0af31c       --pmc spark --keywords "info_disclosure rest api"
    ./file.py tomcat-9912  --keywords "deser tribes cluster" --wf cve-allocation
    ./file.py spammy-7710  --spam --reason "marketing blast (SEO services)"
    ./file.py digest-0031  --digest --pmc doris \
        --tag "doris/2026-06-08 sqli jdbc" --tag "doris/CVE-2026-50229 xss"
    ./file.py accenture-77  --non-issue aaa-dependencies --pmc hadoop
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_md import BUNDLE_FILE, read as read_md, write as write_md  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
UNSORTED = "_unsorted"

DOWNLOADED = "downloaded"  # status the tool writes; what this script acts on
FILED = "filed"
SPAM = "spam"
DIGEST_KW = "digest"  # leaf + keyword for a "Currently open security reports" summary
NON_ISSUE = "zzz-non-issue"  # top-level cache category mirroring the email-classification label
INDEX_FILE = "index.json"  # Message-ID -> {path, ...}; finds a bundle once its leaf is renamed

MAX_TAG_LEN = 60  # length of the hyphen-joined keyword slug (the dir name)
KEYWORD_RE = re.compile(r"^[a-z0-9_]+$")
NON_ISSUE_LEAF_RE = re.compile(
    r"^[a-z0-9][a-z0-9 ._-]*$"
)  # a non-issue label leaf, e.g. "aaa-dependencies"


def slugify_dir(value: str, *, fallback: str = "report") -> str:
    """Directory-name slug: preserves [a-z0-9_], collapses other runs to '-'."""
    slug = re.sub(r"[^a-z0-9_]+", "-", (value or "").lower()).strip("-")
    return slug or fallback


def find_bundle(cache: Path, ident: str) -> Path:
    """Locate the downloaded bundle for `ident` anywhere under the cache.

    `ident` matches the message-id-slug directory name (or a unique prefix, such
    as the truncated id the tool printed) or the RFC `message_id`. Only bundles
    still awaiting a disposition (`status: downloaded`) are considered, so a
    re-run never re-files an already-triaged report. Errors on no/ambiguous
    match.
    """
    if not cache.is_dir():
        raise SystemExit(f"No cache at {cache} - run populate-cache first.")
    ident = ident.strip()
    bundle_files = sorted(cache.rglob(BUNDLE_FILE))

    def downloaded(bundle_file: Path):
        try:
            meta, _ = read_md(bundle_file)
        except (OSError, ValueError):
            return None
        return meta if str(meta.get("status") or "") == DOWNLOADED else None

    # Fast path: `ident` is usually the bundle's directory name or a prefix of it
    # (the truncated id the tool printed). Match dir names with a cheap string
    # test and only parse the YAML of those.
    matches = [
        bf.parent
        for bf in bundle_files
        if (bf.parent.name == ident or bf.parent.name.startswith(ident)) and downloaded(bf)
    ]

    # Fallback: the RFC Message-ID. Parse the rest only when the dir-name fast
    # path found nothing (passing a full Message-ID is the uncommon case).
    if not matches:
        for bf in bundle_files:
            meta = downloaded(bf)
            if meta is None:
                continue
            mid = str(meta.get("message_id") or "")
            if mid == ident or mid.startswith(ident):
                matches.append(bf.parent)

    if not matches:
        raise SystemExit(
            f"No downloaded bundle matching {ident!r} (already triaged, or wrong id?)."
        )
    if len(matches) > 1:
        names = ", ".join(d.name for d in matches)
        raise SystemExit(f"{ident!r} is ambiguous, matches: {names}")
    return matches[0]


def resolve_date(bundle: Path, meta: dict, override: str | None) -> str:
    """The yyyy-mm-dd date for the canonical path.

    Prefer the report `date` header; fall back to the `<date>` segment the tool
    already placed the bundle under (bundle is `<cache>/<date>/<pmc>/<slug>/`).
    """
    if override:
        date = override.strip()
    else:
        # report date looks like "2026/05/24 06:43:54"; take the calendar day.
        date = (meta.get("date") or "")[:10].replace("/", "-")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            date = bundle.parent.parent.name  # the <date> dir the tool used
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise SystemExit(f"Could not derive a yyyy-mm-dd date (got {date!r}); pass --date.")
    return date


def parse_keywords(raw: str) -> list[str]:
    tokens = (raw or "").split()
    if not tokens:
        raise SystemExit("--keywords must contain at least one word.")
    bad = [t for t in tokens if not KEYWORD_RE.fullmatch(t)]
    if bad:
        raise SystemExit(
            f"Each keyword must be a single lowercase word ([a-z0-9_]+); reject: {bad!r}."
        )
    slug_len = len("-".join(tokens))
    if slug_len > MAX_TAG_LEN:
        raise SystemExit(
            f"--keywords slug is {slug_len} chars (max {MAX_TAG_LEN}): "
            f"{tokens!r}. Drop or shorten a keyword."
        )
    return tokens


def unique_dir(path: Path) -> Path:
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}-{n}")
        n += 1
    return candidate


def merge_tags(meta: dict, *new: str) -> list[str]:
    """The bundle's Gmail labels with `new` appended, de-duplicated, order kept.

    `tags` starts as the labels already on the message at download (read by the
    tool); labelling adds the assigned triage tag(s) to the same set, and a
    later tool reconciles `tags` against Gmail."""
    out: list[str] = []
    for t in list(meta.get("tags") or []) + list(new):
        t = t.strip() if isinstance(t, str) else t
        if t and t not in out:
            out.append(t)
    return out


def _index_entry(cache: Path, bundle: Path, meta: dict) -> dict:
    return {
        "path": str(bundle.relative_to(cache)),
        "subject": meta.get("subject"),
        "pmc": meta.get("pmc"),
        "collection": meta.get("collection"),
        "tags": meta.get("tags"),
        "status": meta.get("status"),
    }


def load_index(cache: Path) -> dict:
    p = cache / INDEX_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def update_index(cache: Path, bundle: Path, meta: dict) -> None:
    """Upsert the bundle's entry in ``index.json``, keyed by Message-ID.

    Filing renames the leaf from the message-id slug to the keyword slug, so the
    Message-ID is no longer in the path; the index keeps it findable - look up
    the Message-ID to get the bundle's current path, pmc and tags without
    scanning every report.md."""
    mid = str(meta.get("message_id") or "").strip()
    if not mid:
        return
    index = load_index(cache)
    index[mid] = _index_entry(cache, bundle, meta)
    (cache / INDEX_FILE).write_text(
        json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def reindex(cache: Path) -> int:
    """Rebuild ``index.json`` from every report.md under the cache."""
    if not cache.is_dir():
        raise SystemExit(f"No cache at {cache}.")
    index: dict = {}
    for bundle_file in sorted(cache.rglob(BUNDLE_FILE)):
        try:
            meta, _ = read_md(bundle_file)
        except (OSError, ValueError):
            continue
        mid = str(meta.get("message_id") or "").strip()
        if mid:
            index[mid] = _index_entry(cache, bundle_file.parent, meta)
    (cache / INDEX_FILE).write_text(
        json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Reindexed {len(index)} bundles into {INDEX_FILE}.")
    return 0


def mark_spam(cache: Path, bundle: Path, meta: dict, body: str, reason: str, dry_run: bool) -> int:
    """Stamp `status: spam` in place; keep the bundle as a dedup tombstone."""
    print(f"SPAM {bundle.name}: {meta.get('subject')!r}")
    print(f"  reason: {reason}")
    if dry_run:
        print("(dry-run, nothing written)")
        return 0
    meta.update({"status": SPAM, "disposition": reason, "handled": True})
    write_md(bundle / BUNDLE_FILE, meta, body)
    update_index(cache, bundle, meta)
    print("Marked spam (kept in place so it is never re-downloaded).")
    return 0


def file_report(
    cache: Path,
    bundle: Path,
    meta: dict,
    body: str,
    pmc: str,
    keywords_raw: str,
    wf: str | None,
    date_override: str | None,
    dry_run: bool,
) -> int:
    pmc = pmc.strip().lower()
    if not pmc or pmc == UNSORTED:
        raise SystemExit(
            "No PMC: this bundle is unsorted, so pass --pmc "
            "(read the report body to determine the project)."
        )
    tokens = parse_keywords(keywords_raw)
    date = resolve_date(bundle, meta, date_override)
    kw_slug = slugify_dir("-".join(tokens))

    # The label key is the allocated CVE if there is one, else the report's day.
    # The composed label (active collection -> no prefix) also carries the `wf`.
    key = (meta.get("cve") or date).strip()
    tag = f"{pmc}/{key} {' '.join(tokens)}"
    if wf:
        tag += f" wf {wf}"
    target = unique_dir(cache / date / pmc / kw_slug)

    print(f"{bundle.relative_to(cache)}  ->  {target.relative_to(cache)}")
    print(f"  tag: {tag}")
    if dry_run:
        print("(dry-run, nothing written)")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(bundle), str(target))
    meta.update(
        {
            "tags": merge_tags(meta, tag),
            "pmc": pmc,
            "collection": None,
            "keywords": tokens,
            "status": FILED,
        }
    )
    if wf:
        meta["wf"] = wf
    write_md(target / BUNDLE_FILE, meta, body)
    update_index(cache, target, meta)
    print(f"Filed. {len(list((target / 'attachments').glob('*')))} attachment(s) moved.")
    return 0


def file_digest(
    cache: Path,
    bundle: Path,
    meta: dict,
    body: str,
    pmc: str,
    tags: list[str],
    date_override: str | None,
    dry_run: bool,
) -> int:
    """File a "Currently open security reports for <pmc>" digest.

    The digest is not itself a report to assess: it summarises the PMC's still
    open reports. We label it with every tag of the reports it lists (looked up
    by the agent in `email-classification/<pmc>/`) so it surfaces alongside
    them, file it under `<date>/<pmc>/digest/` (keywords: [digest]), and mark it
    terminal (`handled: true`). A digest has no `wf` - it is the team's own
    summary, not a report waiting for anything."""
    pmc = pmc.strip().lower()
    if not pmc or pmc == UNSORTED:
        raise SystemExit("--digest needs --pmc <slug> (the project the digest is 'for').")
    covered = [t.strip() for t in tags if t.strip()]
    date = resolve_date(bundle, meta, date_override)
    target = unique_dir(cache / date / pmc / DIGEST_KW)
    merged = merge_tags(meta, *covered)

    print(f"{bundle.relative_to(cache)}  ->  {target.relative_to(cache)}")
    print(f"  {DIGEST_KW}: {len(covered)} covered report tag(s)")
    for t in covered:
        print(f"    - {t}")
    if dry_run:
        print("(dry-run, nothing written)")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(bundle), str(target))
    meta.update(
        {
            "tags": merged or None,
            "pmc": pmc,
            "collection": None,
            "keywords": [DIGEST_KW],
            "status": FILED,
            "handled": True,
        }
    )
    write_md(target / BUNDLE_FILE, meta, body)
    update_index(cache, target, meta)
    print(f"Filed digest with {len(covered)} covered report tag(s).")
    return 0


def file_non_issue(
    cache: Path,
    bundle: Path,
    meta: dict,
    body: str,
    pmc: str,
    leaf: str,
    dry_run: bool,
) -> int:
    """File a recognised non-issue under ``zzz-non-issue/<pmc>/<leaf>/``.

    Some inbound mail is a known non-issue class rather than a fresh
    vulnerability - most commonly a request about a CVE in an Apache project the
    sender merely depends on, filed under the standing ``aaa-dependencies``
    label. ``leaf`` is the full label leaf exactly as it appears in the
    email-classification archive (e.g. ``aaa-dependencies``, ``aaa-nvd``,
    ``aaa-oss-fuzz``); it is NOT assumed to start with ``aaa-``. The bundle keeps
    its message-id-slug directory name, so several reports can share one label.

    This is the standing-category path. A report dismissed case-by-case instead
    gets filed normally as ``<pmc>/<date> <keywords>`` with ``--wf
    non-issue-feedback`` while the reporter feedback is in flight, and is moved
    to ``zzz-non-issue/<pmc>/<date> <keywords>`` later (downstream), not here."""
    pmc = pmc.strip().lower()
    if not pmc or pmc == UNSORTED:
        raise SystemExit("--non-issue needs --pmc <slug> (the Apache project the CVE is in).")
    leaf = (leaf or "").strip().lower()
    if not NON_ISSUE_LEAF_RE.fullmatch(leaf):
        raise SystemExit(
            f"--non-issue takes the full label leaf (e.g. 'aaa-dependencies'); "
            f"[a-z0-9 ._-], no slashes. Got {leaf!r}."
        )
    tag = f"{NON_ISSUE}/{pmc}/{leaf}"
    target = unique_dir(cache / NON_ISSUE / pmc / leaf / bundle.name)

    print(f"{bundle.relative_to(cache)}  ->  {target.relative_to(cache)}")
    print(f"  tag: {tag}")
    if dry_run:
        print("(dry-run, nothing written)")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(bundle), str(target))
    meta.update(
        {
            "tags": merge_tags(meta, tag),
            "pmc": pmc,
            "collection": NON_ISSUE,
            "keywords": None,
            "status": FILED,
        }
    )
    write_md(target / BUNDLE_FILE, meta, body)
    update_index(cache, target, meta)
    print(f"Filed as non-issue ({leaf}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "id",
        nargs="?",
        help="message-id-slug dir name (or unique prefix) or RFC Message-ID",
    )
    ap.add_argument("--pmc", help="PMC slug (defaults to the tool-detected pmc field)")
    ap.add_argument(
        "--keywords",
        help=(
            "Space-separated tag keywords, each [a-z0-9_]+, ordered "
            f"most-specific to most-generic. Hyphen-joined slug capped at {MAX_TAG_LEN} chars."
        ),
    )
    ap.add_argument(
        "--wf",
        help="'waiting for' state the report sits in (e.g. reporter, cve-allocation, "
        "non-issue-feedback, non-issue-docs, disclosure, or a fix-release version); a report "
        "in a PMC's hands has none",
    )
    ap.add_argument(
        "--spam",
        action="store_true",
        help="Non-report: stamp status: spam in place (kept as a dedup tombstone, not deleted)",
    )
    ap.add_argument("--reason", help="Why it is spam (used with --spam)")
    ap.add_argument(
        "--digest",
        action="store_true",
        help="A 'Currently open security reports for <pmc>' summary: file under "
        "<pmc>/digest/ and tag with every covered report (--tag, repeatable)",
    )
    ap.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        metavar="TAG",
        help="A covered report's tag from email-classification/<pmc>/ (repeatable, used "
        "with --digest)",
    )
    ap.add_argument(
        "--non-issue",
        dest="non_issue",
        metavar="LABEL",
        help="A known non-issue: the full label leaf (e.g. 'aaa-dependencies' for a "
        "CVE-in-a-dependency inquiry). Files under zzz-non-issue/<pmc>/<LABEL>/ and tags it "
        "zzz-non-issue/<pmc>/<LABEL> (needs --pmc)",
    )
    ap.add_argument("--date", help="Override report date (yyyy-mm-dd)")
    ap.add_argument(
        "--reindex",
        action="store_true",
        help=f"Rebuild {INDEX_FILE} (Message-ID -> bundle path) from the cache and exit",
    )
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--dry-run", action="store_true", help="Show the action, write nothing")
    args = ap.parse_args()

    cache = args.cache_dir
    if args.reindex:
        return reindex(cache)
    if not args.id:
        raise SystemExit("an id is required (or pass --reindex to rebuild the index).")
    bundle = find_bundle(cache, args.id)
    meta, body = read_md(bundle / BUNDLE_FILE)

    if args.spam:
        if args.keywords or args.pmc or args.wf or args.digest:
            raise SystemExit("--spam does not take --keywords/--pmc/--wf/--digest.")
        return mark_spam(cache, bundle, meta, body, args.reason or "non-report", args.dry_run)

    if args.digest:
        if args.keywords or args.wf:
            raise SystemExit("--digest does not take --keywords/--wf.")
        return file_digest(
            cache,
            bundle,
            meta,
            body,
            args.pmc or meta.get("pmc") or "",
            args.tags,
            args.date,
            args.dry_run,
        )

    if args.non_issue:
        if args.keywords or args.wf or args.digest or args.spam:
            raise SystemExit("--non-issue does not take --keywords/--wf/--digest/--spam.")
        return file_non_issue(
            cache,
            bundle,
            meta,
            body,
            args.pmc or meta.get("pmc") or "",
            args.non_issue,
            args.dry_run,
        )

    if not args.keywords:
        raise SystemExit("--keywords is required to file (or pass --spam for a non-report).")
    return file_report(
        cache,
        bundle,
        meta,
        body,
        args.pmc or meta.get("pmc") or "",
        args.keywords,
        args.wf,
        args.date,
        args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
