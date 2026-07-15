<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# form-submitter

> **RETIRED — do not use.** The scan program moved in-house:
> **ASF Tooling** now runs scans internally (Mythos-5,
> officially provisioned 2026-07-01) and enrolls them from
> the Mythos tracker spreadsheet + the
> `apache/tooling-agents-private` archive. There is **no
> external Google Form** to fill anymore. Enrollment is done
> by `frontier-model-preparation-submit`, which just sets
> `Date scan requested` + `Repositories submitted` on the
> PMC's tracker row. This tool is kept in-tree only as a
> historical reference to the legacy external-relay
> (Alpha-Omega Google-Form) intake; it is not part of the
> current flow. The rest of this document describes that
> retired flow.

Glasswing scan-submission helper (legacy). Filled ASF
Tooling's project-enrollment Google Form once per repo for a
PMC, ordered by OSSF Criticality Score (highest first). The
headline submission carried the maintainer roster +
OSS-expedite addresses + the Claude Max 20x checkbox;
subsequent submissions pointed back to the headline.

Formerly used by the `frontier-model-preparation-submit` SKILL
(which now enrolls via the tracker instead — see that SKILL).

## Why this existed

Apache projects with multi-repo scopes (HBase: 12+ repos;
Tomcat: 4; Spark: 3) needed a separate form submission per
repo against the external enrollment form. Doing that
manually was error-prone — wrong ordering, copy-paste drift
between headline and follow-ups, forgotten checkboxes.
`form-submitter` built the plan from the Mythos tracker,
showed it to the operator with a dry-run, then drove a
headless Chromium through Playwright to submit each form
in order. The persistent profile + lazy Playwright import
kept the surface area narrow.

## One-time setup

1. **OAuth token for Sheets reads.** form-submitter shares
   the `token.json` produced by
   `sheets_writer.py setup` — run that first if you
   haven't.

2. **Submitter identity.** Tells the form your name +
   @apache.org email + GitHub profile URL.

   ```bash
   uv run --project tools/form_submitter form-submitter \
       setup-submitter \
       --name "Your Name" \
       --email you@apache.org \
       --github https://github.com/your-handle
   ```

   Writes `~/.config/asf-security/glasswing/submitter.json`
   (mode 0o600).

3. **Persistent Chromium profile.** Sign in to Google
   interactively once; subsequent runs reuse the session
   in headless mode.

   ```bash
   uv run --project tools/form_submitter form-submitter setup
   ```

   Opens Chromium with the persistent profile at
   `~/.config/asf-security/glasswing/playwright-profile/`.
   Sign in to Google, confirm the form loads, close the
   browser. The profile is now populated.

   Playwright's Chromium binary is downloaded on first
   `setup` run via `playwright install chromium` (the
   package's standard one-time setup; ~150 MB).

## Usage

```bash
# Dry-run first — prints the plan, no browser:
uv run --project tools/form_submitter form-submitter \
    submit-pmc --slug hbase --dry-run

# Live submission (one form per submittable repo,
# OSSF-criticality-ordered):
uv run --project tools/form_submitter form-submitter \
    submit-pmc --slug hbase

# Resume mid-batch after an error:
uv run --project tools/form_submitter form-submitter \
    submit-pmc --slug hbase --starting-from hbase-thirdparty
```

The dry-run prints every form's filled-in field +
checkbox state so the operator can sanity-check before the
browser drives anything. Repos without AGENTS.md /
SECURITY.md / security.txt at HEAD are dropped from the
plan and listed as "skipped" — discoverability has to
land first (via `frontier-model-preparation-model-verify`).

## Test coverage

Pure-function tests only — no Playwright browser tests.
The browser drives Google's live form, which (a) we don't
control the markup of and (b) requires a real signed-in
session that's not reproducible in CI without secrets.

Tests cover:
- `parse_criticality` — OSSF Criticality Score parsing.
- `RepoEntry.is_submittable` + `can_claim_security_md` —
  per-repo gating logic.
- Sort ordering — OSSF-criticality-descending, alphabetical
  tiebreak, None-sorted-last.
- `parse_expedite_cell` — multi-line list / `none` / blank.
- `parse_submission_notes` — strip + passthrough.
- `get_scan_result_recipients_for_pmc` — extract +
  dedupe + ignore non-apache.org.
- `build_headline_additional_info` /
  `build_subsequent_additional_info` — rendering shape,
  expedite block conditional, submission notes appended.
- `build_plan` — headline ordering, claude-max checkbox,
  per-repo SECURITY.md checkbox, skip logic, PMC name
  prefix normalisation.
- `load_submitter` / `write_submitter` — file mode 0o600,
  @apache.org validation, idempotency.
- CLI argparse routing for all three subcommands.

The browser path (`submit_one`, `run_live`, `run_setup`)
is exercised manually before each live submission via the
`--dry-run` plan review + the actual form's
required-field validation on submit.

## Manual smoke test before live submission

1. `--dry-run` against a real PMC; eyeball the headline +
   subsequent additional-info blocks.
2. `setup` (re-)opens the profile if signed out; confirm
   the form loads.
3. Live `submit-pmc --slug <pmc>`; watch the first repo go
   through. If anything looks wrong, ctrl-C immediately
   and use `--starting-from` to resume after fixing.

## Layout

```
tools/form_submitter/
├── pyproject.toml         — hatchling build, google-api +
│                            google-auth + playwright runtime deps
├── README.md              — this file
├── src/form_submitter/
│   ├── __init__.py        — version + config paths + form/spreadsheet IDs
│   ├── __main__.py        — `python -m form_submitter` entry
│   ├── auth.py            — load_sheets_credentials
│   ├── sheets.py          — read_grid + fetch_pmc_state
│   ├── repos.py           — RepoEntry + parse_criticality + discoverability probes
│   ├── submitter.py       — load_submitter + write_submitter
│   ├── plan.py            — FormFill + build_plan + print_plan (browser-free)
│   ├── browser.py         — Playwright orchestration (lazy import)
│   └── cli.py             — argparse + subcommand handlers
└── tests/
    ├── conftest.py        — shared sample PMC rows + RepoEntry fixtures
    ├── test_repos.py      — RepoEntry + parse_criticality
    ├── test_plan.py       — plan-builder edge cases
    ├── test_submitter.py  — submitter.json load + write
    └── test_cli.py        — argparse routing
```

## Provenance

Promoted from `form_submitter.py` (inline single-file
helper) in `.github/skills/frontier-model-preparation-submit/`
2026-05-28, mirroring the `jira_writer` (#72) and
`whimsy_lookup` (#73) promotions. Same module-split shape,
same `uv run --project tools/<name>` invocation contract.

The pure-function tests lock in the per-PMC plan shape so
regressions in OSSF ordering, Claude-Max-checkbox gating,
or expedite-block rendering surface in CI before the
operator runs a live submission.
