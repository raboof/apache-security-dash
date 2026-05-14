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

## SKILLs currently here

| Skill | Purpose |
| --- | --- |
| [`glasswing-scan-response/`](glasswing-scan-response/SKILL.md) | Draft replies to PMC inquiries about the Glasswing scan offer — what model is being used, what threat-model framework is expected, how the scan compares to GitHub code scanning / SCA / etc. Captures the operational rules (CC `security@apache.org`, require `@apache.org` from requester, draft-before-send, attach threat-model drafts only on request). |
| [`glasswing-scan-status/`](glasswing-scan-status/SKILL.md) | Read-only rollup of the Glasswing / Mythos scan-outreach effort. Pulls the shared "Mythos scan" Google Sheet (Piotr Karwasz's tracker) via the Google Drive MCP, then summarizes: PMCs opted in, contacts, security-model status, request → delivery turnaround, backlog age, status-bucket roll-up, repo coverage, unmapped high-criticality repos, prospecting list. The sheet's file ID is kept in user-scope reference memory (`mythos-tracker`), not in this repo. |
| [`threat-model-producer/`](threat-model-producer/SKILL.md) | Produce a project threat model — the *implicit contract* between the project and downstream users (what is in scope, what is out, what is claimed, what is disclaimed). Imported verbatim from [Michael Scovetta's gist](https://gist.github.com/scovetta/2dc9a0695c7cbcc32e23799e00d2ced3). |

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
