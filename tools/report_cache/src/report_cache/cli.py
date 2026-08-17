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

"""Move and label report bundles in the local cache.

The agent-driven half of the triage-populate-cache SKILL.
`populate-cache` downloads each new thread head,
writing its Gmail provenance to report.md and an initial index entry (``status: downloaded``).
This command then classifies and files those bundles
by moving them into place and updating the shared index;
report.md (Gmail data) is never rewritten - all triage state lives in the index.

  classify:  the skill's one-shot = move + label + set state.
        Moves the bundle under ``<pmc>/<date>-<keywords>``,
        adds the composed label,
        and sets ``status: classified`` (no disposition) - or, with
        ``--track-only`` (the PMC already received the report),
        ``status: assessed`` + ``disposition: track``.

  move:  relocate a bundle and update its index path / pmc.
        Destination is the flat ``<pmc>/<date>-<slug>``;
        ``slug`` defaults to the keywords hyphen-joined (collisions auto-resolve);
        ``date`` defaults to the report's UTC day.

  set:   update index metadata (status, disposition, labels).
        ``--add-label`` / ``--remove-label`` edit the label set directly;
        the ``--pmc`` / ``--keywords`` / ``--collection`` / ``--waiting-for`` /
        ``--cve`` helpers compose one label and add it:
        ``[<collection>/]<pmc>/<key> <keywords>[ wf <waiting-for>]``,
        where ``key`` is ``--cve`` if given, else the report's date.
        ``--assessment-model`` records the AI model that assessed the report.
        ``--duplicate-ponymail-link`` records the Ponymail archive URL of an
        earlier report this one duplicates.
        ``--security-model-source`` / ``--security-model-link`` record the PMC's
        security-model URLs (machine-readable source, human-readable page).

Operates only on the local cache; never talks to a mailbox, never sends.
``<id>`` matches an index entry by RFC Message-ID (a unique prefix works) or by
the bundle's leaf directory name.

Examples:
    report-cache classify 0af31c --pmc spark --keywords "xxe rest api"
    report-cache classify tomcat-9912 --pmc tomcat --keywords "deser tribes" --track-only
    report-cache set spammy-7710 --disposition skip
    report-cache set accenture-77 --disposition decline \
        --collection zzz-non-issue --pmc hadoop --keywords "aaa_dependencies"
    report-cache set 0af31c --add-label "spark/CVE-2026-1234 xxe rest api"
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from enum import StrEnum
from pathlib import Path

from report_cache import index
from report_cache.index import Disposition, Entry, Status
from report_cache.report_md import BUNDLE_FILE, Header
from report_cache.report_md import read as read_report

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
UNSORTED = "_unsorted"


class WaitingFor(StrEnum):
    """What a filed report is still waiting on (encoded in its label)."""

    NON_ISSUE_FEEDBACK = "non-issue-feedback"
    NON_ISSUE_DOCS = "non-issue-docs"
    REPORTER = "reporter"
    CVE_ALLOCATION = "cve-allocation"


MAX_SLUG_LEN = 60  # length of the hyphen-joined keyword slug (the dir name)
KEYWORD_RE = re.compile(r"^[a-z0-9_]+$")


def slugify_dir(value: str, *, fallback: str = "report") -> str:
    """Directory-name slug: preserves [a-z0-9_], collapses other runs to '-'."""
    slug = re.sub(r"[^a-z0-9_]+", "-", (value or "").lower()).strip("-")
    return slug or fallback


def parse_keywords(raw: str) -> list[str]:
    """Validated keyword tokens, most-specific to most-generic."""
    tokens = (raw or "").split()
    if not tokens:
        raise SystemExit("--keywords must contain at least one word.")
    bad = [t for t in tokens if not KEYWORD_RE.fullmatch(t)]
    if bad:
        raise SystemExit(
            f"Each keyword must be a single lowercase word ([a-z0-9_]+); reject: {bad!r}."
        )
    slug_len = len("-".join(tokens))
    if slug_len > MAX_SLUG_LEN:
        raise SystemExit(
            f"--keywords slug is {slug_len} chars (max {MAX_SLUG_LEN}): "
            f"{tokens!r}. Drop or shorten a keyword."
        )
    return tokens


def unique_dir(path: Path) -> Path:
    """`path`, or `path-2`, `path-3`, ... - the first name that does not exist."""
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}-{n}")
        n += 1
    return candidate


def compose_label(
    pmc: str,
    keywords: list[str],
    *,
    collection: str | None = None,
    waiting_for: str | None = None,
    key: str | None = None,
) -> str:
    """Build a Gmail label from its parts.

    Active reports get ``<pmc>/<key> <keywords>`` (``key`` = a CVE or the date);
    a ``collection`` (e.g. ``zzz-non-issue``) prefixes it and drops the key:
    ``<collection>/<pmc>/<keywords>``.
    A ``waiting_for`` state is appended as `` wf <state>``.
    """
    words = " ".join(keywords)
    if collection:
        label = f"{collection}/{pmc}/{words}"
    elif key:
        label = f"{pmc}/{key} {words}"
    else:
        label = f"{pmc}/{words}"
    if waiting_for:
        label += f" wf {waiting_for}"
    return label


def find_entry(idx: dict[str, Entry], ident: str) -> tuple[str, Entry]:
    """The ``(message_id, Entry)`` whose Message-ID or bundle leaf matches ``ident``.

    An exact Message-ID or leaf-name match wins;
    otherwise a unique prefix of either is accepted.
    Errors on no match or an ambiguous prefix.
    """
    exact = [(mid, e) for mid, e in idx.items() if mid == ident or Path(e.path).name == ident]
    matches = exact or [
        (mid, e)
        for mid, e in idx.items()
        if mid.startswith(ident) or Path(e.path).name.startswith(ident)
    ]
    if not matches:
        raise SystemExit(f"No index entry matching {ident!r} (run populate-cache first?).")
    if len(matches) > 1:
        names = ", ".join(Path(e.path).name for _, e in matches)
        raise SystemExit(f"{ident!r} is ambiguous, matches: {names}")
    return matches[0]


def report_date(header: Header) -> str:
    """The report's yyyy-mm-dd day, from its Date header (UTC, so it never oscillates)."""
    if header.date is None:
        raise SystemExit("report.md has no Date header; cannot derive the report date.")
    return header.date.date().isoformat()


def _move_entry(
    cache: Path,
    entry: Entry,
    header: Header,
    *,
    pmc: str,
    keywords: list[str] | None,
    slug: str | None,
) -> Path:
    """Relocate the bundle; update ``entry.path`` and ``entry.pmc``. Returns the target."""
    if not pmc or pmc == UNSORTED:
        raise SystemExit("--pmc is required (this bundle has no assigned project).")
    if slug:
        slug = slugify_dir(slug)
    elif keywords:
        slug = slugify_dir("-".join(keywords))
    else:
        raise SystemExit("pass --keywords or --slug to name the destination.")

    # A flat <pmc>/<date>-<slug> leaf; the date is a prefix, not a grouping dir.
    target = unique_dir(cache / pmc / f"{report_date(header)}-{slug}")

    source = cache / entry.path
    print(f"{entry.path}  ->  {target.relative_to(cache)}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    entry.path = str(target.relative_to(cache))
    entry.pmc = pmc
    return target


def _set_entry(
    entry: Entry,
    header: Header,
    *,
    status: str | None,
    disposition: str | None,
    reporter_name: str | None,
    add_labels: list[str],
    remove_labels: list[str],
    pmc: str | None,
    keywords: list[str] | None,
    collection: str | None,
    waiting_for: str | None,
    cve: str | None,
    assessment_model: str | None = None,
    duplicate_ponymail_link: str | None = None,
    security_model_source: str | None = None,
    security_model_link: str | None = None,
) -> None:
    """Update the entry's status / disposition / reporter name / labels in place."""
    if status is not None:
        entry.status = Status(status)
    if disposition is not None:
        entry.disposition = Disposition(disposition)
    if reporter_name is not None:
        entry.reporter_name = reporter_name
    if assessment_model is not None:
        entry.assessment_model = assessment_model
    # URL fields are assigned raw; Entry's URL converter validates on set (raises on a bad URL).
    if duplicate_ponymail_link is not None:
        entry.duplicate_ponymail_link = duplicate_ponymail_link
    if security_model_source is not None:
        entry.security_model_source = security_model_source
    if security_model_link is not None:
        entry.security_model_link = security_model_link

    add = list(add_labels)
    if pmc and keywords:
        key = cve or report_date(header)
        add.append(
            compose_label(
                pmc,
                keywords,
                collection=collection,
                waiting_for=waiting_for,
                key=None if collection else key,
            )
        )

    labels = list(entry.labels or [])
    for label in add:
        if label and label not in labels:
            labels.append(label)
    for label in remove_labels:
        if label in labels:
            labels.remove(label)
    entry.labels = labels or None


def cmd_move(cache: Path, args: argparse.Namespace) -> int:
    idx = index.load(cache)
    mid, entry = find_entry(idx, args.id)
    header, _ = read_report(cache / entry.path / BUNDLE_FILE)
    keywords = parse_keywords(args.keywords) if args.keywords else None
    _move_entry(cache, entry, header, pmc=args.pmc, keywords=keywords, slug=args.slug)
    idx[mid] = entry
    index.write(cache, idx)
    return 0


def cmd_set(cache: Path, args: argparse.Namespace) -> int:
    idx = index.load(cache)
    mid, entry = find_entry(idx, args.id)
    header, _ = read_report(cache / entry.path / BUNDLE_FILE)
    _set_entry(
        entry,
        header,
        status=args.status,
        disposition=args.disposition,
        reporter_name=args.reporter_name,
        add_labels=args.add_label,
        remove_labels=args.remove_label,
        pmc=args.pmc,
        keywords=parse_keywords(args.keywords) if args.keywords else None,
        collection=args.collection,
        waiting_for=args.waiting_for,
        cve=args.cve,
        assessment_model=args.assessment_model,
        duplicate_ponymail_link=args.duplicate_ponymail_link,
        security_model_source=args.security_model_source,
        security_model_link=args.security_model_link,
    )
    idx[mid] = entry
    index.write(cache, idx)
    return 0


def cmd_classify(cache: Path, args: argparse.Namespace) -> int:
    """Move the bundle, add the composed label, and set the lifecycle state.

    Default: ``status: classified`` with no disposition (the report still needs
    assessment). ``--track-only`` is the shortcut for a report the PMC already
    received: ``status: assessed`` + ``disposition: track`` (nothing for us to
    send, just track it)."""
    idx = index.load(cache)
    mid, entry = find_entry(idx, args.id)
    header, _ = read_report(cache / entry.path / BUNDLE_FILE)
    keywords = parse_keywords(args.keywords)
    _move_entry(cache, entry, header, pmc=args.pmc, keywords=keywords, slug=None)
    if args.track_only:
        status, disposition = Status.ASSESSED.value, "track"
    else:
        status, disposition = Status.CLASSIFIED.value, None
    _set_entry(
        entry,
        header,
        status=status,
        disposition=disposition,
        reporter_name=args.reporter_name,
        add_labels=args.add_label,
        remove_labels=[],
        pmc=args.pmc,
        keywords=keywords,
        collection=args.collection,
        waiting_for=args.waiting_for,
        cve=args.cve,
    )
    idx[mid] = entry
    index.write(cache, idx)
    return 0


def _add_label_args(parser: argparse.ArgumentParser) -> None:
    """Shared label-composition + direct-label options for `set` and `classify`.

    These only affect the label set; ``--keywords`` has no effect beyond it (in
    `classify` it doubles as the move slug, but that is `classify`'s own use).
    """
    parser.add_argument("--keywords", help="Keywords for the composed label")
    parser.add_argument("--collection", help="Label prefix, e.g. zzz-non-issue (default: none)")
    parser.add_argument(
        "--waiting-for", choices=tuple(w.value for w in WaitingFor), help="'waiting for' state"
    )
    parser.add_argument("--cve", help="CVE id to use as the label key instead of the date")
    parser.add_argument(
        "--add-label", action="append", default=[], metavar="LABEL", help="Add a label verbatim"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="report-cache",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    sub = ap.add_subparsers(dest="command", required=True)

    statuses = tuple(s.value for s in Status)
    dispositions = tuple(d.value for d in Disposition)

    p_move = sub.add_parser("move", help="Relocate a bundle")
    p_move.add_argument("id", help="Message-ID (prefix ok) or bundle leaf name")
    p_move.add_argument("--pmc", required=True, help="PMC slug the report is assigned to")
    p_move.add_argument("--keywords", help="Keywords whose hyphen-join is the slug")
    p_move.add_argument("--slug", help="Destination leaf name (overrides --keywords)")

    p_set = sub.add_parser("set", help="Update index metadata")
    p_set.add_argument("id", help="Message-ID (prefix ok) or bundle leaf name")
    p_set.add_argument("--status", choices=statuses, help="Lifecycle status")
    p_set.add_argument("--disposition", choices=dispositions, help="Triage disposition")
    p_set.add_argument("--reporter-name", help="How to address the reporter (from their signature)")
    p_set.add_argument(
        "--assessment-model",
        help="AI model that assessed the report (credited in the forward's disclaimer)",
    )
    p_set.add_argument(
        "--duplicate-ponymail-link",
        help="Ponymail archive URL of the earlier report this one duplicates",
    )
    p_set.add_argument(
        "--security-model-source",
        help="URL of the PMC's machine-readable security model (e.g. its SECURITY.md)",
    )
    p_set.add_argument(
        "--security-model-link",
        help="URL of the PMC's human-readable security page (to cite to a person)",
    )
    p_set.add_argument("--pmc", help="PMC slug (with --keywords, composes a label)")
    p_set.add_argument(
        "--remove-label", action="append", default=[], metavar="LABEL", help="Remove a label"
    )
    _add_label_args(p_set)

    p_classify = sub.add_parser("classify", help="Move + label + set state (the skill's one-shot)")
    p_classify.add_argument("id", help="Message-ID (prefix ok) or bundle leaf name")
    p_classify.add_argument("--pmc", required=True, help="PMC slug the report is assigned to")
    p_classify.add_argument(
        "--track-only",
        action="store_true",
        help="The PMC already received it: set status assessed + disposition track "
        "(default: status classified, no disposition)",
    )
    p_classify.add_argument(
        "--reporter-name", help="How to address the reporter (from their signature)"
    )
    _add_label_args(p_classify)

    args = ap.parse_args()
    handlers = {"move": cmd_move, "set": cmd_set, "classify": cmd_classify}
    return handlers[args.command](args.cache_dir, args)


if __name__ == "__main__":
    sys.exit(main())
