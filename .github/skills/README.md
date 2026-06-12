<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# ASF Security Team — Agentic SKILLs

This directory holds reusable **agent SKILLs** — instruction-set
documents written in the form that coding assistants and agentic
runtimes (Claude Code, the OpenAI Agents SDK, etc.) load as
behavior modules. Each SKILL is self-contained and can be invoked
by any member of the Security team with a compatible agent setup.

SKILLs that live here are operational: they encode the patterns
the team uses repeatedly when responding to PMC inquiries, drafting
threat models, classifying inbound mail, and so on. They are
opinionated and team-specific; they are not intended to be generic
external guidance.

## Layout

The canonical home is `.github/skills/<name>/`. Each SKILL is a
directory with a `SKILL.md` and any supporting files:

```
.github/skills/
├── README.md                          # this file
├── <skill-name>/
│   ├── SKILL.md                       # required — frontmatter + body
│   ├── <reference-file>.md            # optional, per skill
│   └── <helper-script>.{py,sh,...}    # optional, per skill
```

`SKILL.md` follows the convention used by Claude Code's skill
loader: YAML frontmatter with `name` and `description`, then the
body in markdown. Other agent runtimes can ingest the same files
since the body is plain markdown.

### Where each runtime looks

Runtimes look for skills in different conventional locations.
This repo puts the source of truth in `.github/skills/` and
symlinks the other typical locations to it, so every runtime
finds the same content:

```
.github/skills/<name>/                                 ← canonical (GitHub Copilot, raw fetch)
.claude/skills/<name> → ../../.github/skills/<name>    (Claude Code per-project)
```

If a new runtime convention emerges, add another symlink — never
duplicate the content.

### Sibling: `tools/` for promoted helpers

Some SKILLs hand off mechanical work to a Python helper. Two
shapes coexist:

- **Inline** — single PEP-723 script inside the SKILL dir.
  None currently — every Python helper has been promoted.
- **Promoted** — standalone Python project under
  [`../../tools/`](../../tools/) with `pyproject.toml`, tests,
  and CI. Invoked from SKILLs via
  `uv run --project tools/<name> <cli> ...`.

Currently in `tools/`:

| Project | Used by | Purpose |
| --- | --- | --- |
| [`jira_writer`](../../tools/jira_writer/) | `glasswing-scan-update` (today); `glasswing-scan-response` + `glasswing-model-verify` (as JIRA-id-in-title PMCs come up) | Apache JIRA write helper (PAT-authenticated). Files companion tickets when a SKILL opens a PR against a PMC repo that needs a JIRA id (HBASE convention; ~5 other PMCs follow the same pattern). |
| [`whimsy_lookup`](../../tools/whimsy_lookup/) | `glasswing-scan-response` (Gate 2 identity resolution + Gate 3 PMC-roster check) | Deterministic Apache Whimsy / LDAP lookups. Replaces unreliable WebFetch-summary calls against `public_ldap_people.json` and `committee-info.json` after the 2026-05-21 Doris-incident hallucination. |
| [`form_submitter`](../../tools/form_submitter/) | `glasswing-scan-submit` | Playwright-driven Google Form filler. Submits one form per repo for a PMC, OSSF-criticality-ordered; headline carries maintainer roster + OSS-expedite addresses + Claude Max 20x checkbox. |
| [`sheets_writer`](../../tools/sheets_writer/) | `glasswing-scan-update` (every write subcommand) | OAuth-authenticated writer for the Mythos tracker Google Sheet. Row-level applies, canned-response management, PMC-row appends, the Status/Completed/Timeline tab rebuild, a read-only grid `dump`, and column-schema mutations. |
| [`model_pr`](../../tools/model_pr/) | `glasswing-model-verify`; path-3 threat-model drafting | One-shot opener of discoverability / threat-model PRs on PMC repos: fork → clone → write the `AGENTS.md → SECURITY.md → model` scaffold (create-or-append) → commit → push → `gh pr create`. Collapses the per-repo dance the model-verify SKILL and the path-3 rollout otherwise do by hand. |

The top-level [README's "Two helper tiers" section](../../README.md#two-helper-tiers--inline-scripts-vs-tools-projects)
documents the promotion criteria.

## SKILLs currently here

| Skill | Purpose |
| --- | --- |
| [`glasswing-scan-run/`](glasswing-scan-run/SKILL.md) | Umbrella orchestration SKILL for the Glasswing pipeline — the "run a full sweep" entrypoint. Does a periodic read-only sweep across Gmail (`[GLASSWING]` threads + Mirko correspondence), the Mythos tracker spreadsheet, and the discoverability PRs we've opened. Cross-references state, classifies each PMC by pipeline stage (`new-request-untouched`, `pmc-reply-awaiting-action`, `model-verify-pending`, `ready-to-submit`, `blocked-on-discoverability`, `blocked-on-gate-2`, `submitted-awaiting-vendor`, `results-back-awaiting-sanity-check`, `forwarded-closed`, etc.), produces a per-PMC action list with the next downstream SKILL named, and refreshes the `Status` tab in the workbook. Never writes; the per-task SKILLs do that. Use at the start of a work session or after time away. |
| [`glasswing-scan-response/`](glasswing-scan-response/SKILL.md) | Draft replies to PMC inquiries about the Glasswing scan offer — what model is being used, what threat-model framework is expected, how the scan compares to GitHub code scanning / SCA / etc. Captures the operational rules (CC `security@apache.org`, require `@apache.org` from requester, draft-before-send, attach threat-model drafts only on request). |
| [`glasswing-model-verify/`](glasswing-model-verify/SKILL.md) | Pre-flight verification of a PMC's nominated security model before a scan is queued. Checks (a) discoverability via `AGENTS.md → SECURITY.md` so the scan agent can mechanically find the model, and (b) completeness against the `threat-model-producer` rubric. Produces concrete remediation: PR for mechanical fixes (one-line `AGENTS.md` link, draft additions for missing sections via the producer SKILL), issue for substantive gaps. Hands off to `glasswing-scan-update` to flip `Security model verified` once both checks pass. All external writes (issue, PR, spreadsheet) gated on user approval. |
| [`glasswing-scan-submit/`](glasswing-scan-submit/SKILL.md) | Submit a PMC's scan request to the vendor's project-enrollment Google Form (one form submission per repo, ordered by OSSF Criticality Score — highest first; headline form carries the maintainer roster + OSS-expedite addresses + "I'm interested in Claude Max 20x" checkbox) and then draft the PMC notification email. Replaced the "Email 1 to Mirko" flow on 2026-05-19. Form submission uses a Playwright persistent profile (one-time Google sign-in via `form-submitter setup` from `tools/form_submitter/`); PMC notification is a Gmail draft for human review. After human sends, hand off to `glasswing-scan-update` to set `Date scan requested` + `Repositories submitted`. |
| [`glasswing-scan-forward/`](glasswing-scan-forward/SKILL.md) | Process a scan report received from Mirko/Alpha-Omega and forward it to the appropriate PMC after a Security-team pre-forward sanity check. The sanity check catches catastrophic generation errors only (wrong project, wrong/stale model, truncated output, missing repos, cross-PMC leakage, mangled formatting); if it passes, the vendor's findings are forwarded **verbatim** to the PMC's listed recipients — no per-finding triage on the Security team's side (no classification against the model, no filtering, no annotation). Per-finding triage stays with the PMC against the project's own threat model. After send, hand off to `glasswing-scan-update` to set `Date scan received` + `Forwarded scan to PMC`. Output is a Gmail draft for human review — never sends directly. |
| [`glasswing-scan-status/`](glasswing-scan-status/SKILL.md) | Read-only rollup of the Glasswing / Mythos scan-outreach effort. Pulls the shared "Mythos scan" Google Sheet (Piotr Karwasz's tracker) via the Google Drive MCP, then summarizes: PMCs opted in, contacts, security-model status, request → delivery turnaround, backlog age, status-bucket roll-up, repo coverage, unmapped high-criticality repos, prospecting list. The sheet's file ID is kept in user-scope reference memory (`mythos-tracker`), not in this repo. |
| [`glasswing-scan-update/`](glasswing-scan-update/SKILL.md) | Write counterpart to `glasswing-scan-status`. Applies row updates (set `Scan Requested`, `Request date`, `Date scan requested`, `Date scan received`, `Forwarded scan to PMC`, `Security model verified`, etc.) to the Mythos tracker via a bundled OAuth-authenticated Python helper, since Claude Workspace's Google Drive MCP is read-only. Always diffs and confirms before writing. OAuth client secret + refresh token live in `~/.config/asf-security/glasswing/` (outside the repo); per-user, not shared. |
| [`glasswing-dashboard/`](glasswing-dashboard/SKILL.md) | Refresh the program-totals dashboard. `sheets-writer build-status-tab` rebuilds the tracker's five tabs AND overwrites one private GitHub gist that mirrors the Program-totals tables + the PMC funnel as markdown (Unicode bar chart). Created on first run, overwritten after; gist id kept in `~/.config/asf-security/glasswing/dashboard_gist.json`. Aggregate counts only — no PMC names, no vendor identity. |
| [`threat-model-producer/`](threat-model-producer/SKILL.md) | Produce a project threat model — the *implicit contract* between the project and downstream users (what is in scope, what is out, what is claimed, what is disclaimed). Imported verbatim from [Michael Scovetta's gist](https://gist.github.com/scovetta/2dc9a0695c7cbcc32e23799e00d2ced3). |
| [`triage-populate-cache/`](triage-populate-cache/SKILL.md) | Pull new inbound security reports off the foundation-wide `security@apache.org` Gmail inbox into the local `report-cache/`, ready for assessment. Two-step flow inside one skill: the deterministic `populate-cache` tool (`tools/populate_cache/`) reads the inbox through the read-only Gmail API, selects thread heads by header facts only (not automated CVE-process / VINCE / svn notifications), and writes one `report.md` bundle per message straight into its dated, per-PMC home (`<date>/<pmc>/<message-id-slug>/` or `_unsorted/`) alongside a verbatim `raw.eml`. Then the agent (a Haiku subagent does the read) gives each `status: downloaded` bundle a disposition via `file.py`: file a real report under `<date>/<pmc>/<keywords>/`, label a digest or a known non-issue, or mark spam (kept as a dedup tombstone, never deleted). Nothing is deleted; once a report is archived out of the inbox the next run moves it to `handled/`. Drafting and status are separate downstream SKILLs; this one is also the canonical reference for the `report-cache/` layout they reuse. |
| [`triage-assess/`](triage-assess/SKILL.md) | Assess filed reports against the project's threat model + source and draft the response. Per report: specialized PMCs (own security contact in `project-coordinates.json`) are only tracked; otherwise the model judges plausibility, then a deterministic helper (`draft.py`) writes either a non-assertive push-back to the reporter (high-confidence false-positive / hardening) or a PMC forward (`templates/forward.md`) plus a reporter receipt (`templates/receipt.md`). The PMC owns the final non-issue / hardening / CVE call, so drafts are never assertive and nothing is sent. Coordinates come from a committed `coordinates.yaml` (regenerated from security-site by `build_coordinates.py`); project source is read from `--workspace/<pmc>`. The "assessment + drafting" phase of the report-triage pipeline. |

## Using a SKILL

In Claude Code, copy the SKILL into a local skills directory the
agent loads from (typically `~/.claude/skills/`) — for example
via a `git clone` of this repo into `~/.claude/skills-asf/` plus a
symlink, or via manual `cp`. The exact wiring depends on the
contributor's local setup. Other agent runtimes wire SKILLs in
their own way; see the runtime's docs.

## Contributing a new SKILL

Open a PR adding `skills/<short-kebab-case-name>/SKILL.md` plus
any reference files. The PR description should explain *when* an
agent should invoke the SKILL (the discovery hint that goes in the
`description` frontmatter field).

For SKILLs that are imports of someone else's work (like
`threat-model-producer/`), preserve attribution and indicate where
to re-import from when upstream changes.

## Why these are here and not in a public repo

Some SKILLs encode the Security team's operational rules
(verification policies, response shapes, CC conventions) that the
team prefers to iterate on internally before sharing externally.
Once a SKILL stabilizes and is generic enough to be useful outside
the team, opening a public copy is encouraged — but `apache/security`
is the canonical home for the team-internal version.
