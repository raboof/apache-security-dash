# AGENTS.md

Conventions for agentic tooling (Claude Code, Codex, similar) working in this repo.
The goal is to keep the diff small, the commits readable,
and the PR-creation flow consistent with how the apache/security maintainers prefer to review.

## What this repo is

apache/security is the ASF Security team's private skill set + tooling for managing the Glasswing scan-outreach program.
SKILLs live under `.agents/skills/` and are symlinked into `.claude/skills/` and `.github/skills/`.
This lets different agent runtimes find them with their preferred directory layout.
Helper tools that have outgrown the single-file-inside-a-SKILL pattern live under `tools/` as proper Python projects (`pyproject.toml` + tests + CI); see the [README's "Two helper tiers" section](README.md#two-helper-tiers--inline-scripts-vs-tools-projects).
The [README](README.md) at the repo root is the entry point and the canonical workflow reference (diagrams, per-PMC state machine, sequence diagram).

## apache-steward framework

This repo adopts the [`apache/airflow-steward`](https://github.com/apache/airflow-steward) framework via the snapshot mechanism.
The framework's skills are gitignored symlinks (each `magpie-`-prefixed) into the `.apache-magpie/` snapshot;
only the always-on `setup-*` / `list-*` maintenance skills are wired in this adopter (no opt-in `security-*` / `pr-management-*` / `issue-*` families).

A fresh clone needs the snapshot populated before any framework skill is invocable.
Run `/magpie-setup` (or follow [`.claude/skills/magpie-setup/`](.claude/skills/magpie-setup/)) to fetch it per the committed [`.apache-magpie.lock`](.apache-magpie.lock).
The contributor-facing summary lives in the [Agent-assisted contribution section of `README.md`](README.md#agent-assisted-contribution-apache-steward).

Adopter-specific modifications to framework-skill workflows live in [`.apache-magpie-overrides/`](.apache-magpie-overrides/) — never edit the snapshot directly.
Framework changes go via PR to [`apache/airflow-steward`](https://github.com/apache/airflow-steward).

## Pre-commit hooks

**Required before any PR.**
The repo uses [`prek`](https://github.com/j178/prek) (a faster Rust-based drop-in replacement for `pre-commit`) for static checks.
Every push to a branch that will become a PR must first pass `prek run --all-files` locally
— agents and humans both.
The hooks catch the easy mistakes before a maintainer's review cycle is spent on them.

### One-time setup per checkout

```bash
# 1. Install prek (if you don't already have it).
#    Recommended: install as a uv tool so it's per-user, not per-project:
uv tool install prek

#    Alternatives:
#    - pipx:                       pipx install prek
#    - homebrew (macOS / Linux):   brew install prek
#    - cargo (from source):        cargo install prek
#
#    If you're stuck on classic pre-commit instead (e.g. an env where
#    prek won't install), `pre-commit install` + `pre-commit run` work
#    too — the config in `.pre-commit-config.yaml` is compatible.

# 2. Install the git hooks into this checkout.
prek install
```

`prek install` writes **two** shims into `.git/hooks/` — `pre-commit` and `pre-push` —
because `.pre-commit-config.yaml` sets `default_install_hook_types: [pre-commit, pre-push]`.
The `pre-commit` shim fires on `git commit`;
the `pre-push` shim fires on `git push` and **blocks the push if any hook fails**.
You only run `prek install` once per fresh checkout.
(If you cloned before this was added, re-run `prek install` to pick up the pre-push shim.)

### Before pushing

With the pre-push shim installed, `git push` runs the hooks for you and refuses to push on failure
— so prek **always** runs before a push lands.
Run the full sweep yourself first anyway,
so you fix issues before the push round-trip rather than during it:

```bash
prek run --all-files    # runs every hook against every file
```

The hooks catch:

- **Generic safety** (`pre-commit-hooks`):
  merge-conflict markers, accidentally-committed private keys, trailing whitespace, mixed line endings, missing trailing newline.
- **Markdown structure** (`markdownlint-cli2` against `.markdownlint.json`):
  broken anchors (`MD051`), dangling link references (`MD053`).
  Style rules are off — the existing docs settled those.
- **Typos** (`typos` against `.typos.toml`): fast spell-checker.
  Project-specific terms (`Glasswing`, `Mythos`, PMC names) are allowlisted;
  common English misspellings are caught.
- **Python lint + format** (`ruff` against every `.py` under `.github/skills/` and `tools/`).
  Both `ruff check` and `ruff format --check` run.
  Today that covers the `tools/jira_writer/`, `tools/whimsy_lookup/`, `tools/form_submitter/`, and `tools/sheets_writer/` packages + tests.

If a hook fails, fix the underlying issue rather than bypassing
— `--no-verify` is not a convention here.
The hooks are fast (single-digit seconds for a clean run);
running them locally before pushing is the expected workflow.

## Commit messages

- **Title under 70 characters; user-impact-focused.** "Add OSS-expedite path to scan-response" beats "Update scan-response.md".
- **Body explains *why*, not *what*** — the diff already shows what.
- **Use `Generated-by:` trailer, not `Co-Authored-By:`.** Generative AI tooling cannot be a commit author;
  humans are authors, agents are assistants.
  Use:

  ```
  Generated-by: Claude Code (Claude Opus 4.7) following the apache/security AGENTS.md conventions
  ```

  at the bottom of the commit body.
  Substitute the actual agent name / version you're running.

- **One logical change per commit.** SKILL doc updates that touch multiple files for one policy shift land as one commit;
  unrelated touch-ups stay out.
  If you find yourself writing "and also" in a commit message body, it's two commits.

## Pull requests

**Prerequisite check before pushing**: confirm `prek` is installed and the hooks pass (see [Pre-commit hooks](#pre-commit-hooks) above).
If `prek install` has not run on this checkout yet, do that first
— it installs both the pre-commit and the pre-push git hooks,
so future commits stay clean automatically and every push is gated on the hooks passing.

**Always use `gh pr create --web`** so the browser opens for the human to review the PR description + click Submit themselves.
The agent drafts; the human submits.

```bash
gh pr create --web \
  --title "Short title (under 70 chars)" \
  --body "$(cat <<'EOF'
## Summary

Brief description of what + why.

## Test plan

- [ ] checklist of how this was validated

Generated-by: Claude Code (Claude Opus 4.7)
EOF
)"
```

The `--web` flag is non-negotiable for agent-created PRs.
It gives the human a final review pass before the PR opens against `apache/security`'s main branch.
The agent prepares; the human commits to the public action.

After the user has the PR open, **do not push more commits to the branch without their explicit approval**.
Each push is content the user is attributing to themselves once they submit.

## SKILL changes

Changes to files under `.github/skills/<skill>/SKILL.md` become canonical immediately on merge
— the SKILL doc IS the source of truth for agent behaviour.
Be precise about what changes and why.
The PR description should quote the new template / rule text so reviewers can compare against the prose without context-switching to the file.

Cross-references between SKILLs (e.g. "per `frontier-model-preparation-response` hard rule 5") need to stay accurate;
when you renumber a rule, grep for the rule reference across all SKILLs and update them in the same commit.

## Semantic line breaks

`SKILL.md` files and this `AGENTS.md` are written with [semantic line breaks](https://sembr.org/).
Start every sentence on its own line.
You may break a long sentence further at clause boundaries (after a comma, semicolon, or colon) when it aids readability.
Never hard-wrap prose to a fixed column,
and never run several sentences together on one line;
let the editor soft-wrap.
The payoff is small, reviewable diffs:
editing one sentence touches one line, not a whole reflowed paragraph.

## Live spreadsheet writes

The Glasswing program coordinates state in a Google Sheet that lives outside this repo (the `mythos-tracker` user-scope memory entry holds its ID + URL).
SKILLs that mutate the sheet go through [`tools/sheets_writer/`](tools/sheets_writer/) — invoked as `uv run --project tools/sheets_writer sheets-writer <subcommand>`.
The helper authenticates via per-user OAuth (`~/.config/asf-security/glasswing/`).

Spreadsheet writes are out-of-band relative to git
— they're applied at SKILL invocation time, not at PR-merge time.
If a SKILL PR depends on a new column or renamed column,
**apply the schema change to the live sheet FIRST** (via `insert-column` / `add-columns` / `rename-column`) so the SKILL doc can reference the live cell layout accurately.
Don't let a schema reference in a merged SKILL doc race ahead of the live sheet.

## Live JIRA writes

Companion to the sheet writer: filing JIRA tickets against `issues.apache.org` (HBase's PR-title-needs-a-JIRA-id convention is the canonical case; several other PMCs follow the same pattern) goes through [`tools/jira_writer/`](tools/jira_writer/).
It's a small standalone Python project (`pyproject.toml`, stdlib-only runtime deps, pytest test suite) invoked from SKILLs as `uv run --project tools/jira_writer jira-writer <subcommand>`.
PAT lives at `~/.config/asf-security/jira/token` (mode 0o600 enforced by the helper).
Same draft-and-confirm discipline as the sheet writer:
every write subcommand has `--dry-run`;
SKILLs run `--dry-run`, show the payload to the user, and only re-run without it after explicit approval.

## Sandbox bypass — when it's OK, when to be loud

Per the user's CLAUDE.md, sandbox-bypass proposals must be **visually loud** (`!!! SANDBOX BYPASS: <reason> !!!`).
Bypass is OK for:

- `git push` / `git commit` (SSH signing reads `~/.ssh`)
- `gh pr create` / `gh gist create` / other `gh api` (macOS cert-chain issue against `api.github.com`)
- `uv run --project tools/sheets_writer sheets-writer …` (reads OAuth state from `~/.config/asf-security/glasswing/`, writes to `sheets.googleapis.com`)
- `uv run --project tools/jira_writer jira-writer …` (reads the PAT from `~/.config/asf-security/jira/token`, writes to `issues.apache.org`)
- Reading `~/.config/asf-security/{glasswing,jira}/` files (sandbox denies those paths by default)

Bypass is **not** OK for one-off curls or general internet access
— those should go through `WebFetch` against allowlisted hosts.

## Provenance

This AGENTS.md captures conventions surfaced during the 2026-05 Glasswing pipeline development,
when multiple PRs (#54 through #59) landed back-to-back
and the team realized the agent-side conventions for commit trailers + PR creation + pre-commit hygiene weren't written down anywhere.
Patterned after Airflow's AGENTS.md (`apache/airflow/AGENTS.md`)
and apache-steward's pre-commit config (`apache/airflow-steward/.pre-commit-config.yaml`);
scoped down for apache/security's much smaller surface area.
