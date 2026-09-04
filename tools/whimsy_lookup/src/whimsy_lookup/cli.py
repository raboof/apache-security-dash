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
import json
import sys

from whimsy_lookup.committee import PMCNotFound, chair_of, check_membership, pmc_entry
from whimsy_lookup.fetch import (
    FetchError,
    fetch_committee_info,
    fetch_ldap_people,
    fetch_security_coordinates,
)
from whimsy_lookup.ldap import resolve_ids
from whimsy_lookup.pmc_guess import guess_pmcs
from whimsy_lookup.security_info import pmc_security_info


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
    committees = fetch_committee_info()
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
    committees = fetch_committee_info()
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


def cmd_pmc_security_info(args: argparse.Namespace) -> int:
    """Print a PMC's security coordinates: who to CC and the security-model URLs.

    Reads apache/security-site's project-coordinates.json and reports, for one PMC slug:
    the ``security_contact`` to CC
    (the PMC's own ``security@<slug>.apache.org`` when registered,
     else the foundation-wide ``security@apache.org`` fallback),
    the ``has_own_security_team`` flag + the ``team_cc`` PMC-side channel to CC
    on a pre-disclosure forward
    (its own ``security@<slug>`` when it runs a team, else its ``private@<slug>`` list),
    the ``security_model_source`` to read/WebFetch the model,
    and the ``security_model_link`` human page to cite it to a person.

    A PMC may register a model per sub-project instead (``axis``, ``ws``); those are printed under
    ``subprojects`` and the caller must pick the one matching the product it
    is assessing, since they differ per product.

    ``--json`` emits the full record as one JSON object (for programmatic use, e.g. triage-assess);
    the default is a human-readable key/value block.
    """
    coordinates = fetch_security_coordinates()
    info = pmc_security_info(coordinates, args.slug)

    if args.json:
        print(json.dumps(info, ensure_ascii=False))
    else:
        print(f"slug:                  {info['slug']}")
        print(f"name:                  {info['name'] or '(unknown — not in coordinates.json)'}")
        print(f"security_contact:      {info['security_contact']}")
        print(f"has_own_security_team: {info['has_own_security_team']}")
        print(f"team_cc:               {info['team_cc']}")
        subs = info.get("subprojects") or []
        if info["security_model_source"] or info["security_model_link"] or not subs:
            print(f"security_model_source: {info['security_model_source'] or '(none on record)'}")
            print(f"security_model_link:   {info['security_model_link'] or '(none on record)'}")
        if subs:
            print(f"subprojects:           {len(subs)} with a registered model")
            for sub in subs:
                print(f"  - {sub['name'] or '(unnamed)'}")
                print(f"      security_model_source: {sub['security_model_source']}")
                print(f"      security_model_link:   {sub['security_model_link']}")

    return 0


def cmd_guess_pmc(args: argparse.Namespace) -> int:
    """Guess the PMC(s) referenced by free text and show their security page.

    Exit 0 if at least one candidate is found, 1 otherwise.
    """
    committees = fetch_committee_info()
    coordinates = fetch_security_coordinates()
    candidates = guess_pmcs(args.text, committees, coordinates)
    if not candidates:
        print("No PMC could be guessed from the supplied text.")
        return 1
    print("PMC guess(es):")
    for pmc in candidates:
        if not pmc.security_model_source and not pmc.subprojects:
            print(f"  {pmc.id:24} (no security page on record)")
        if pmc.security_model_source:
            print(f"  {pmc.id:24} {pmc.security_model_source}")
        if pmc.subprojects:
            print(f"  {pmc.id:24} (per sub-project):")
            for sub in pmc.subprojects:
                print(f"  {'':24}   {sub['name'] or '(unnamed)'}: {sub['security_model_source']}")
    return 0


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

    p_sec = sub.add_parser(
        "pmc-security-info",
        help=(
            "Print a PMC's security coordinates from the security-site "
            "project-coordinates.json: the security_contact to CC (the PMC's "
            "own security@<pmc> when registered, else security@apache.org) and "
            "the threat-model link."
        ),
    )
    p_sec.add_argument("slug", help="PMC slug (e.g. 'tomcat', 'kafka').")
    p_sec.add_argument(
        "--json",
        action="store_true",
        help="Emit the full record as one JSON object instead of a key/value block.",
    )

    p_guess = sub.add_parser(
        "guess-pmc",
        help=(
            "Guess the PMC(s) referenced by free text (e.g. an email's "
            "headers) and print each one's security page URL. Exit 0 if a "
            "candidate is found, 1 otherwise."
        ),
    )
    p_guess.add_argument(
        "text",
        help="Free text to scan (addresses + standalone slug tokens).",
    )

    return p


DISPATCH = {
    "resolve-id": cmd_resolve_id,
    "pmc-info": cmd_pmc_info,
    "check-pmc-member": cmd_check_pmc_member,
    "pmc-security-info": cmd_pmc_security_info,
    "guess-pmc": cmd_guess_pmc,
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
