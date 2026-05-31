<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# model-pr

Open a threat-model / discoverability PR on an Apache PMC repo in one
invocation. Collapses the repeated **fork → clone → write the
`AGENTS.md → SECURITY.md → model` scaffold (create or append) → commit →
push → `gh pr create`** dance that `glasswing-model-verify` and the path-3
threat-model rollout do by hand for every repo.

Used by the `glasswing-model-verify` SKILL and during path-3 model drafting.

## Why this exists

Landing a model + discoverability scaffold on a PMC repo is the same ~10
git/gh steps every time, with one fiddly branch: `SECURITY.md` and `AGENTS.md`
must be **created** when absent but **appended to** (a single new section, never
editing existing prose) when present. Doing that by hand per repo is slow and
error-prone — across one rollout it was ~15 repos. This tool makes the
file-merge logic a tested pure function and the rest a single command.

## Usage

In-repo model (lands `THREAT_MODEL.md`, wires `AGENTS.md → SECURITY.md → THREAT_MODEL.md`):

```bash
uv run --project tools/model_pr model-pr open \
  --repo apache/jspwiki \
  --model /path/to/THREAT_MODEL.md \
  --date 2026-05-31 \
  --title "Add draft threat model + SECURITY.md + AGENTS.md for security-model discoverability" \
  --body-file /path/to/pr-body.md
```

Pointer (satellite repo that defers to an umbrella model elsewhere — wires
`AGENTS.md → SECURITY.md → <URL>`, lands no model file):

```bash
uv run --project tools/model_pr model-pr open \
  --repo apache/cxf-xjc-utils \
  --pointer https://github.com/apache/cxf/blob/main/THREAT_MODEL.md \
  --date 2026-05-31 \
  --agents-note "This repository is build-time tooling for Apache CXF."
```

By default the PR is opened with `gh pr create --web` (you review and submit in
the browser). Pass `--submit` to create it non-interactively, or `--dry-run` to
build the files and print the staged diff without committing/pushing/opening.

## Options

| Flag | Meaning |
| --- | --- |
| `--repo` | `apache/<repo>` or a bare `<repo>` (prefixed with `apache/`). |
| `--model PATH` / `--pointer URL` | Exactly one. In-repo model file, or a cross-repo umbrella URL. |
| `--model-name` | In-repo model filename (default `THREAT_MODEL.md`). |
| `--date` | Date stamp for the branch (`asf-security/threat-model-<date>`). |
| `--base` | Base branch (default: the repo's default branch). |
| `--fork-owner` | Fork to push to (default: the `gh`-authenticated user). |
| `--agents-note` | Extra note appended to the `AGENTS.md` Security section. |
| `--title` / `--body-file` | PR title (also the commit subject) and body. |
| `--submit` | Create the PR directly instead of `--web`. |
| `--dry-run` | Build files + show the diff; no commit/push/PR. |

## What's tested

The pure file-merge core (`content.py`) is fully unit-tested:
`build_security_md` and `build_agents_md` (create vs. append, idempotency,
in-repo vs. pointer model refs, existing-prose preservation) and `branch_name`,
plus argparse routing. The git/gh side effects in `cli.py` are exercised through
operator use; `--dry-run` shows the staged diff before anything leaves the machine.

## Development

```bash
cd tools/model_pr
uv sync --extra test
uv run pytest
uvx ruff check src tests
```

## Layout

```
tools/model_pr/
├── pyproject.toml          — hatchling build, no runtime deps (stdlib + git/gh)
├── README.md               — this file
├── src/model_pr/
│   ├── __init__.py
│   ├── __main__.py         — `python -m model_pr`
│   ├── content.py          — build_security_md / build_agents_md / branch_name (pure)
│   └── cli.py              — `model-pr open` orchestration (git + gh)
└── tests/
    └── test_content.py     — pure builders + argparse routing
```
