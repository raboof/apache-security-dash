<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# whimsy-lookup

Deterministic Apache Whimsy / LDAP lookups for the
`glasswing-scan-response` SKILL's identity (Gate 2) and PMC-roster
(Gate 3) checks. Stdlib-only — no third-party deps.

## Why this exists

Gates 2 and 3 cross-check sender identity and PMC-roster membership
against two public Whimsy JSON dumps:

- <https://whimsy.apache.org/public/public_ldap_people.json>
- <https://whimsy.apache.org/public/committee-info.json>

These files are large (several MB) and have been observed to confuse
WebFetch-style summarising readers — WebFetch returns hallucinated
keys, truncated rosters, or fabricated entries that look plausible
but are wrong. The 2026-05-21 Doris incident (Calvin Kirs) traces
back to a WebFetch summary that drove an unnecessary gate-3
challenge in a PMC-facing email; this helper would have returned
the correct answer.

The helper fetches the raw JSON via stdlib `urllib` + `json` and
answers four structural questions deterministically:

- `resolve-id "<full name>"` — find Apache ID(s) matching a human name
- `pmc-info <slug>` — chair + full roster of a PMC committee
- `check-pmc-member <slug> <apache-id> [...]` — true/false per ID
- `pmc-security-info <slug> [--json]` — a PMC's security coordinates:
  the `security_contact` to Cc (its own `security@<slug>.apache.org` when registered, else `security@apache.org`) and the threat-model link

**Use this from SKILL prompts instead of WebFetch on the JSON URLs.**
WebFetch on these endpoints is unreliable and should be treated as
a bug.

The `pmc-security-info` lookup hits a different source —
`apache/security-site:scripts/project-coordinates.json` — but
the same WebFetch hazard applies (multi-KB JSON, summarising
the contents has been observed to fabricate entries), so
prefer the CLI.

## Usage

```bash
# Find Apache ID(s) matching a name:
uv run --project tools/whimsy_lookup whimsy-lookup resolve-id "Calvin Kirs"

# Dump a PMC's chair + roster:
uv run --project tools/whimsy_lookup whimsy-lookup pmc-info hbase

# Boolean PMC-membership check (exit 0 if all present, 1 if any missing):
uv run --project tools/whimsy_lookup whimsy-lookup check-pmc-member hbase ndimiduk apurtell

# PMC security coordinates — the security_contact to Cc + the threat-model link.
# security_contact is the PMC's own security@<pmc> when registered, else the
# foundation-wide security@apache.org fallback, so a caller can just Cc it:
uv run --project tools/whimsy_lookup whimsy-lookup pmc-security-info tomcat
uv run --project tools/whimsy_lookup whimsy-lookup pmc-security-info cassandra
uv run --project tools/whimsy_lookup whimsy-lookup pmc-security-info kafka --json
```

## Exit codes

- `0` — success (resolve-id found at least one match; pmc-info OK; check-pmc-member all-present; pmc-security-info ran the lookup — read the security_contact from its output)
- `1` — domain failure (no match; PMC slug not in committee-info; some IDs missing from roster)
- `2` — fetch failure (network error, JSON parse error, timeout against Whimsy or security-site)

CLI callers (the SKILL prompt) can distinguish "no answer" from
"couldn't ask" via the exit code.

## Invocation from Claude Code SKILLs

```bash
uv run --project tools/whimsy_lookup whimsy-lookup <subcommand> ...
```

This bypasses the need for any global install. The first run
on a machine triggers `uv` to materialise a virtualenv under
`~/.cache/uv/`; subsequent runs reuse it.

## Development

```bash
cd tools/whimsy_lookup
uv sync --extra test            # install pytest + the package in editable mode
uv run pytest                   # run the unit tests
uvx ruff check src tests        # lint
uvx ruff format src tests --check
```

## Layout

```
tools/whimsy_lookup/
├── pyproject.toml         — hatchling build, stdlib-only deps
├── README.md              — this file
├── src/whimsy_lookup/
│   ├── __init__.py        — version + Whimsy URL constants
│   ├── __main__.py        — `python -m whimsy_lookup` entry
│   ├── fetch.py           — urllib wrapper + normalize_name()
│   ├── ldap.py            — pure resolve_ids() over the people JSON
│   ├── committee.py       — pure pmc_entry / chair_of / check_membership over committee-info
│   └── cli.py             — argparse + subcommand handlers
└── tests/
    ├── conftest.py        — shared sample LDAP/committee JSON fixtures
    ├── test_fetch.py      — normalize_name + fetch_json + error wrapping
    ├── test_ldap.py       — resolve_ids edge cases (incl. Calvin Kirs, Andrea Cosentino)
    ├── test_committee.py  — pmc_entry / chair_of / check_membership
    └── test_cli.py        — argparse routing + handler exit codes
```

## Provenance

Promoted from `whimsy_lookup.py` (inline single-file helper) in
`.github/skills/glasswing-scan-response/` 2026-05-27, after the
`jira_writer` promotion validated the `tools/<name>/` pattern.

The original was added 2026-05-21 in response to the Doris-incident
WebFetch hallucination — a Calvin Kirs / `kirs@apache.org` lookup
returned a fabricated answer that drove a wrong gate-3 challenge in
a PMC-facing email. Logging the canonical-source helper as a
testable project gives the same deterministic behaviour with test
coverage that catches regressions.
