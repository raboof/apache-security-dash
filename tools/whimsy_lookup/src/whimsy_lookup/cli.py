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
"""Argparse CLI for whimsy-lookup."""

from __future__ import annotations

import argparse
import sys

from whimsy_lookup.committee import PMCNotFound, chair_of, check_membership, pmc_entry
from whimsy_lookup.fetch import (
    FetchError,
    fetch_committee_info,
    fetch_ldap_people,
    fetch_security_coordinates,
)
from whimsy_lookup.ldap import resolve_ids
from whimsy_lookup.security_alias import classify_security_alias


def cmd_resolve_id(args: argparse.Namespace) -> int:
    """Search public_ldap_people.json for Apache IDs matching a name."""
    if not args.name.strip():
        print("Empty name argument.", file=sys.stderr)
        return 1
    people = fetch_ldap_people().get("people", {})
    hits = resolve_ids(people, args.name)
    if not hits:
        print(f"No Apache ID found matching {args.name!r}.")
        return 1
    print(f"Apache IDs matching {args.name!r}:")
    for apache_id, name in hits:
        print(f"  {apache_id:24} {name}")
    return 0


def cmd_pmc_info(args: argparse.Namespace) -> int:
    """Dump chair + roster for a PMC."""
    committees = fetch_committee_info().get("committees", {})
    entry = pmc_entry(committees, args.slug)
    chair_id, chair_name = chair_of(entry)
    roster = entry.get("roster", {})

    print(f"PMC: {args.slug}")
    print(f"Chair: {chair_id} ({chair_name})")
    print(f"Roster ({len(roster)}):")
    for apache_id, member in sorted(roster.items()):
        name = member.get("name", "?")
        date = member.get("date", "?")
        print(f"  {apache_id:24} {name:30}  since {date}")
    return 0


def cmd_check_pmc_member(args: argparse.Namespace) -> int:
    """Boolean PMC-membership check for one or more Apache IDs."""
    committees = fetch_committee_info().get("committees", {})
    entry = pmc_entry(committees, args.slug)
    roster = entry.get("roster", {})

    results = check_membership(roster, args.apache_ids)
    any_missing = False
    print(f"PMC: {args.slug} (roster size {len(roster)})")
    for apache_id, member in results.items():
        if member is None:
            print(f"  {apache_id:24} NO   (not on {args.slug} PMC roster)")
            any_missing = True
        else:
            name = member.get("name", "?")
            date = member.get("date", "?")
            print(f"  {apache_id:24} YES  ({name}, since {date})")
    return 1 if any_missing else 0


def cmd_check_security_alias(args: argparse.Namespace) -> int:
    """Verify whether security@<slug>.apache.org exists per coordinates.json.

    Exit codes:

      * 0 — alias is present (contact matches ``security@<slug>.apache.org``);
        safe to CC the alias on PMC-facing email.
      * 1 — alias is NOT present (slug missing from coordinates.json,
        OR contact is the foundation-wide ``security@apache.org``);
        do NOT CC the per-PMC alias — qmail will bounce.
    """
    coordinates = fetch_security_coordinates()
    status, contact = classify_security_alias(coordinates, args.slug)
    expected = f"security@{args.slug}.apache.org"
    if status == "present":
        print(f"{args.slug:24} PRESENT  ({expected})")
        return 0
    if status == "generic":
        print(
            f"{args.slug:24} ABSENT   (coordinates contact = "
            f"{contact!r}, not {expected!r}). Do NOT CC the alias."
        )
        return 1
    print(
        f"{args.slug:24} ABSENT   (no entry in project-coordinates.json). Do NOT CC {expected!r}."
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="whimsy-lookup",
        description=(
            "Deterministic Apache Whimsy / LDAP lookups for the "
            "Glasswing scan-response identity + PMC-roster gates."
        ),
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

    p_info = sub.add_parser(
        "pmc-info",
        help="Dump chair + full roster for a PMC (committee-info.json).",
    )
    p_info.add_argument("slug", help="PMC slug (e.g. 'doris', 'tomcat').")

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

    p_alias = sub.add_parser(
        "check-security-alias",
        help=(
            "Verify whether security@<pmc>.apache.org exists per the "
            "security-site project-coordinates.json. Exit 0 = present "
            "(safe to CC), exit 1 = absent (do NOT CC; qmail will bounce)."
        ),
    )
    p_alias.add_argument("slug", help="PMC slug (e.g. 'tomcat', 'kafka').")

    return p


DISPATCH = {
    "resolve-id": cmd_resolve_id,
    "pmc-info": cmd_pmc_info,
    "check-pmc-member": cmd_check_pmc_member,
    "check-security-alias": cmd_check_security_alias,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return DISPATCH[args.cmd](args)
    except FetchError as e:
        print(str(e), file=sys.stderr)
        return 2
    except PMCNotFound as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
