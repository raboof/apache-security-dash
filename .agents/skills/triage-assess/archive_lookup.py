#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# ///
"""Search the email-classification archive for prior reports similar to a tag.

The Security team's `email-classification` branch keeps a per-PMC archive of
every triaged report's tag, structured as one `.json` per report under:

    email-classification/<pmc>/                           open / pending
    email-classification/zzz-non-issue/<pmc>/             classified non-issues
    email-classification/zzz-resolved/<pmc>/              shipped fixes (often CVE-prefixed)
    email-classification/archive/<zzz-...>/<pmc>/         older entries

The filename is the report's tag (space-separated keywords, optionally
prefixed by a CVE id or date). Each file holds the list of messages in the
thread (mailtime, subj, from, to, message_id).

This helper:

1. Ensures `email-classification/` exists as a worktree of the
   `email-classification` branch (creates it on first run if missing).
2. For a given PMC + keyword set, finds .json files whose filename keywords
   overlap with the query, and ranks them by overlap size.
3. Prints one line per match: category, score, date, filename, plus a detail
   block with the initial message's reporter / subject / Message-Id.

Privacy: the archive contains third-party reporter PII (subj/from/to/
message_id). The triage-assess SKILL must not surface that info to a
reporter-facing draft unless the matched archive is from the SAME reporter.
The data IS appropriate to share with the PMC on a forward (they own the
report) and to use for Ponymail lookups for context.

Examples:
    ./archive_lookup.py --pmc cxf --keywords "xxe digester"
    ./archive_lookup.py --pmc spark --keywords "ui disclosure" --limit 3
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parents[2]
ARCHIVE_DIR = REPO_ROOT / "email-classification"
BRANCH = "email-classification"

# Tokens that should not count as keywords when comparing filenames.
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CVE = re.compile(r"^cve-\d{4}-\d+$")
_WF_MARKERS = {
    "wf",
    "reporter",
    "cve-allocation",
    "non-issue-feedback",
    "non-issue-docs",
}


def keyword_tokens(stem: str) -> set[str]:
    """Tag keywords from a filename stem (already without .json). Drops dates,
    CVE ids, and the wf marker words."""
    out = set()
    for tok in stem.lower().split():
        if _DATE.fullmatch(tok) or _CVE.fullmatch(tok) or tok in _WF_MARKERS:
            continue
        out.add(tok)
    return out


def ensure_worktree() -> None:
    """Create the email-classification worktree under the repo root if absent."""
    if ARCHIVE_DIR.is_dir() and any(ARCHIVE_DIR.iterdir()):
        return
    print(
        f"Setting up the {BRANCH} worktree at {ARCHIVE_DIR.relative_to(REPO_ROOT)}/ ...",
        file=sys.stderr,
    )
    try:
        subprocess.run(
            ["git", "worktree", "add", str(ARCHIVE_DIR), BRANCH],
            cwd=REPO_ROOT,
            check=True,
        )
        return
    except subprocess.CalledProcessError:
        pass
    # Fall back: branch may only exist on a remote; fetch and retry.
    for remote in ("apache", "origin"):
        try:
            subprocess.run(
                ["git", "fetch", remote, f"{BRANCH}:{BRANCH}"],
                cwd=REPO_ROOT,
                check=True,
            )
            subprocess.run(
                ["git", "worktree", "add", str(ARCHIVE_DIR), BRANCH],
                cwd=REPO_ROOT,
                check=True,
            )
            return
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(
        f"Could not create the {BRANCH} worktree. Ensure the branch exists "
        f"locally (`git fetch apache {BRANCH}`) and try again."
    )


def category_for(path: Path, pmc: str) -> str:
    """Folder category of a match. e.g. 'open', 'zzz-non-issue',
    'zzz-resolved', 'archive/zzz-non-issue'."""
    rel = path.relative_to(ARCHIVE_DIR).parts
    try:
        idx = rel.index(pmc)
    except ValueError:
        return "/".join(rel[:-1]) or "?"
    prefix = "/".join(rel[:idx])
    return prefix or "open"


def initial_message(path: Path) -> dict:
    """Return the first (initial-report) message in the file, or an empty
    dict if the file is malformed or empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first
    return {}


def fmt_date(mailtime) -> str:
    try:
        import datetime as _dt

        return _dt.datetime.fromtimestamp(int(mailtime), tz=_dt.timezone.utc).strftime(
            "%Y-%m-%d"
        )
    except (TypeError, ValueError):
        return "?"


def find_matches(pmc: str, query: set[str]) -> list[tuple[int, Path, set[str]]]:
    """All archived .json files for `pmc` whose filename keywords overlap with
    `query`, ranked by overlap size (descending)."""
    pmc = pmc.lower()
    matches: list[tuple[int, Path, set[str]]] = []
    for jf in ARCHIVE_DIR.rglob("*.json"):
        if pmc not in [p.lower() for p in jf.parent.parts]:
            continue
        toks = keyword_tokens(jf.stem)
        overlap = toks & query
        if not overlap:
            continue
        matches.append((len(overlap), jf, overlap))
    matches.sort(key=lambda r: (-r[0], str(r[1])))
    return matches


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pmc", required=True, help="PMC slug (e.g. cxf, spark)")
    ap.add_argument(
        "--keywords",
        required=True,
        help="Space-separated keywords to match against archived tag filenames",
    )
    ap.add_argument(
        "--limit", type=int, default=10, help="Maximum matches to print (default 10)"
    )
    args = ap.parse_args()

    ensure_worktree()

    query = keyword_tokens(args.keywords)
    if not query:
        raise SystemExit(
            f"--keywords {args.keywords!r} yields no usable tokens (dates, CVE "
            f"ids, and {sorted(_WF_MARKERS)} are dropped)."
        )

    matches = find_matches(args.pmc, query)
    if not matches:
        print(f"No archived reports for {args.pmc!r} match keywords {sorted(query)!r}.")
        return 0

    shown = matches[: args.limit]
    print(
        f"{len(matches)} archived match(es) for {args.pmc!r} on {sorted(query)!r}"
        + (f" (showing top {len(shown)})" if len(matches) > len(shown) else "")
        + ":"
    )
    print()
    for score, path, overlap in shown:
        msg = initial_message(path)
        category = category_for(path, args.pmc.lower())
        keywords = path.stem
        date = fmt_date(msg.get("mailtime"))
        print(f"  [{category}]  score={score}  {keywords}")
        print(f"    date:       {date}")
        if msg.get("subj"):
            print(f"    subject:    {msg['subj']}")
        if msg.get("from"):
            print(f"    from:       {msg['from']}")
        if msg.get("message_id"):
            print(f"    message-id: {msg['message_id']}")
        print(f"    overlap:    {sorted(overlap)}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
