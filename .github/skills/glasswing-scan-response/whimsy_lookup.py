#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic Whimsy / Apache LDAP lookups for the Glasswing scan gates.

Gates 2 and 3 of `glasswing-scan-response` cross-check sender identity and
PMC-roster membership against two Whimsy JSON files:

  * https://whimsy.apache.org/public/public_ldap_people.json
  * https://whimsy.apache.org/public/committee-info.json

These files are large (several MB) and have been observed to confuse
WebFetch-style summarizing readers — WebFetch returns hallucinated keys,
truncated rosters, or fabricated entries that look plausible but are
wrong. The 2026-05-21 Doris incident (Calvin Kirs, kirs@apache.org)
caught a WebFetch summary that omitted his correct PMC entry and
fabricated unrelated names; the bad output drove an unnecessary
gate-3 challenge in a PMC-facing email.

This helper fetches the raw JSON via stdlib urllib + json and answers
the specific structural questions the gates need:

  * resolve-id "<full name>" — find Apache ID(s) matching a human name
  * pmc-info <slug>          — chair + full roster of a PMC committee
  * check-pmc-member <slug> <apache-id> [...]
                             — true/false per ID, exit 1 if any miss

Use this from SKILL prompts instead of WebFetch on the JSON URLs.
WebFetch on these endpoints is unreliable and should be treated as a
bug.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

LDAP_PEOPLE_URL = "https://whimsy.apache.org/public/public_ldap_people.json"
COMMITTEE_INFO_URL = "https://whimsy.apache.org/public/committee-info.json"

_REQ_TIMEOUT_S = 30


def _fetch_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=_REQ_TIMEOUT_S) as resp:
            return json.load(resp)
    except Exception as exc:  # noqa: BLE001 — single boundary for diagnostics
        sys.exit(f"FETCH-ERROR: {url}: {exc}")


def _normalize_name(s: str) -> str:
    """Lowercase + collapse whitespace; preserves order-of-words.

    Apache LDAP `name` fields vary in casing and sometimes include middle
    names or honorifics; loose matching is enough for the resolve-id
    use case (the human reviews the candidate IDs before acting on
    them).
    """
    return re.sub(r"\s+", " ", s.strip().lower())


def cmd_resolve_id(args: argparse.Namespace) -> int:
    """Search public_ldap_people.json for Apache IDs matching a name.

    Match strategy: case-insensitive substring match on the normalized
    `name` field. Returns all hits; the caller picks the right one
    (typically there's exactly one).
    """
    people = _fetch_json(LDAP_PEOPLE_URL).get("people", {})
    needle = _normalize_name(args.name)
    if not needle:
        sys.exit("Empty name argument.")

    hits = []
    for apache_id, entry in people.items():
        name = entry.get("name", "")
        if needle in _normalize_name(name):
            hits.append((apache_id, name))

    if not hits:
        print(f"No Apache ID found matching {args.name!r}.")
        return 1

    print(f"Apache IDs matching {args.name!r}:")
    for apache_id, name in sorted(hits):
        print(f"  {apache_id:24} {name}")
    return 0


def _pmc_entry(slug: str) -> dict:
    committees = _fetch_json(COMMITTEE_INFO_URL).get("committees", {})
    entry = committees.get(slug)
    if entry is None:
        sys.exit(
            f"PMC-NOT-FOUND: slug {slug!r} not in committee-info.json. "
            f"(Available slugs are committee-info.json keys; common "
            f"misnames: 'logging-services' vs 'logging', '<group>-go' "
            f"split repos belong to the parent PMC, etc.)"
        )
    return entry


def cmd_pmc_info(args: argparse.Namespace) -> int:
    """Dump committee-info.json's entry for a PMC.

    Prints chair + roster (Apache ID -> name, with the joining date)
    in deterministic alphabetical order, suitable for direct quoting
    in a PMC-facing email.
    """
    entry = _pmc_entry(args.slug)
    chair = entry.get("chair", {})
    roster = entry.get("roster", {})

    chair_id = next(iter(chair), "?") if isinstance(chair, dict) else "?"
    chair_name = (
        chair.get(chair_id, {}).get("name", "?")
        if isinstance(chair, dict) and chair_id != "?"
        else "?"
    )

    print(f"PMC: {args.slug}")
    print(f"Chair: {chair_id} ({chair_name})")
    print(f"Roster ({len(roster)}):")
    for apache_id, member in sorted(roster.items()):
        name = member.get("name", "?")
        date = member.get("date", "?")
        print(f"  {apache_id:24} {name:30}  since {date}")
    return 0


def cmd_check_pmc_member(args: argparse.Namespace) -> int:
    """Boolean PMC-membership check for one or more Apache IDs.

    Exit code 0 if every queried ID is on the PMC roster; 1 if any
    is missing. Prints YES/NO per ID with the name from LDAP for
    context.
    """
    entry = _pmc_entry(args.slug)
    roster = entry.get("roster", {})

    any_missing = False
    print(f"PMC: {args.slug} (roster size {len(roster)})")
    for apache_id in args.apache_ids:
        member = roster.get(apache_id)
        if member is None:
            print(f"  {apache_id:24} NO   (not on {args.slug} PMC roster)")
            any_missing = True
        else:
            name = member.get("name", "?")
            date = member.get("date", "?")
            print(f"  {apache_id:24} YES  ({name}, since {date})")
    return 1 if any_missing else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser(
        "resolve-id",
        help="Find Apache ID(s) matching a human name (Gate 2 helper).",
    )
    p_resolve.add_argument(
        "name",
        help="Full name to search for (case-insensitive substring match).",
    )
    p_resolve.set_defaults(func=cmd_resolve_id)

    p_info = sub.add_parser(
        "pmc-info",
        help="Dump chair + full roster for a PMC (committee-info.json).",
    )
    p_info.add_argument("slug", help="PMC slug (e.g. 'doris', 'tomcat').")
    p_info.set_defaults(func=cmd_pmc_info)

    p_check = sub.add_parser(
        "check-pmc-member",
        help="Boolean PMC-membership check for one or more Apache IDs.",
    )
    p_check.add_argument("slug", help="PMC slug (e.g. 'doris', 'tomcat').")
    p_check.add_argument(
        "apache_ids",
        nargs="+",
        metavar="apache-id",
        help="One or more Apache IDs to check against the PMC roster.",
    )
    p_check.set_defaults(func=cmd_check_pmc_member)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
