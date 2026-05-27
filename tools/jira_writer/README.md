<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# jira-writer

Apache JIRA write helper (PAT-authenticated) for the ASF Security
team's Glasswing scan pipeline. Files companion JIRA tickets when
opening discoverability / threat-model PRs against PMC repos that
require a JIRA id in the PR title (HBASE is the canonical example;
several other PMCs use the same convention).

Stdlib-only — no third-party dependencies.

## Why this exists

The Glasswing scan pipeline lives in [apache/security](../..). Its
SKILLs (`glasswing-scan-response`, `glasswing-model-verify`,
`glasswing-scan-update`) sometimes need to file a JIRA ticket as a
companion to a PR they open against a PMC repo. Doing this through
the Atlassian web UI breaks the agent loop; doing it via raw `curl`
loses the dry-run-and-confirm discipline the rest of the SKILL tree
follows. `jira-writer` is the narrow tool that closes that gap: a
small, auditable CLI with a Bearer-auth PAT and three subcommands,
each of which has a `--dry-run` mode so the agent can show the
payload to a human before posting.

The PAT-in-a-mode-0600-file design mirrors what `sheets_writer.py`
does for Google Sheets writes: per-user secret in
`~/.config/asf-security/`, no daemon, no shared service account.

## One-time setup

1. Generate a Personal Access Token at
   <https://issues.apache.org/jira/secure/ViewProfile.jspa> →
   **Personal Access Tokens** tab → **Create token**. Suggested
   name: `claude-glasswing`. Pick an expiry (90 days is a
   reasonable default). Copy the token — JIRA shows it only once.

2. Save it locally, mode 0o600:

   ```bash
   mkdir -p ~/.config/asf-security/jira
   printf '%s' '<PAT>' > ~/.config/asf-security/jira/token
   chmod 600 ~/.config/asf-security/jira/token
   ```

3. Verify the auth round-trips:

   ```bash
   uv run --project tools/jira_writer jira-writer whoami
   ```

   Output is the authenticated user's displayName / Apache ID /
   user-key from `GET /rest/api/2/myself`.

## Usage

All write subcommands accept `--dry-run` to preview the payload
without contacting JIRA.

### whoami — verify auth

```bash
uv run --project tools/jira_writer jira-writer whoami
```

### create-issue — file a new ticket

```bash
uv run --project tools/jira_writer jira-writer create-issue \
    --project HBASE \
    --summary "Add SECURITY.md pointing at security-model + reporting flow" \
    --description-file /tmp/jira-description.md \
    --issuetype Task           # default: Task; --issuetype Bug etc.
    --dry-run                  # optional; omit to actually file
```

On success, prints the canonical issue URL:

```
Created: https://issues.apache.org/jira/browse/HBASE-30181
```

### add-comment — append a comment

```bash
uv run --project tools/jira_writer jira-writer add-comment \
    --issue HBASE-30181 \
    --body-file /tmp/comment.md \
    --dry-run
```

`--body` (inline) and `--body-file` are mutually exclusive; same for
`--description` and `--description-file` on `create-issue`.

## Invocation from Claude Code SKILLs

The SKILLs in `.github/skills/` invoke `jira-writer` via `uv run`
with the `--project` flag pointed at this directory:

```bash
uv run --project tools/jira_writer jira-writer <subcommand> ...
```

This bypasses the need for any global install. The first run on a
machine triggers `uv` to materialise a virtualenv under
`~/.cache/uv/`; subsequent runs reuse it.

## Development

```bash
cd tools/jira_writer
uv sync --extra test     # install pytest + the package in editable mode
uv run pytest            # run the unit tests
uvx ruff check src tests # lint
uvx ruff format src tests --check
```

## Layout

```
tools/jira_writer/
├── pyproject.toml         — hatchling build, stdlib-only deps
├── README.md              — this file
├── src/jira_writer/
│   ├── __init__.py        — version, JIRA_BASE constant
│   ├── __main__.py        — `python -m jira_writer` entry
│   ├── auth.py            — load_pat(), mode-0600 enforcement
│   ├── client.py          — api_call(), get_myself(), create_issue(), add_comment()
│   └── cli.py             — argparse + subcommand handlers
└── tests/
    ├── conftest.py        — shared fixtures (tmp_pat, mock_urlopen)
    ├── test_auth.py       — PAT-loading scenarios
    ├── test_client.py     — API-call wiring (mocked urllib)
    └── test_cli.py        — argparse routing + handler behaviour
```

## Security notes

- **PAT permissions.** The PAT inherits whatever JIRA permissions
  the Apache ID that minted it has. For most ASF committers that
  includes Create-Issue on the projects they're on. For
  security-sensitive projects (security@ projects with private
  issue types), file from a member of that PMC.
- **Mode 0o600 enforced.** `auth.load_pat()` refuses any other
  mode. The error message walks the operator through `chmod 600`.
  An escape hatch (`JIRA_WRITER_SKIP_MODE_CHECK=1`) exists for
  Windows where file modes are not meaningful — never set it on
  POSIX.
- **No PAT in logs.** The CLI never prints the PAT value; only
  `Authorization: Bearer <PAT>` reaches urllib, and urllib doesn't
  log request headers.
- **No telemetry.** The tool talks to `issues.apache.org` and
  nothing else.

## Provenance

Promoted from `jira_writer.py` (inline single-file helper) in
`.github/skills/glasswing-scan-update/` after the first operational
use (HBASE-30181 filed 2026-05-27 paired with `apache/hbase#8275`
retitle). The promotion was requested 2026-05-27 to give the helper
test coverage, versioning, and a documentable surface that other
SKILLs (`glasswing-model-verify`, `glasswing-scan-response`) can
depend on without copy-paste.
