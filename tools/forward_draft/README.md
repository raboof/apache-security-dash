<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# forward-draft

OAuth Gmail draft helper for the Glasswing scan-**forward** step. Creates
an **unsent** Gmail draft whose body is plain text and which carries file
**attachments** — the scan bundle (`.zip`) and the pre-forward assessment
(`.md`) — as a `multipart/mixed` message. A human reviews the draft and
presses Send.

Used by the `frontier-model-preparation-forward` SKILL.

## Why this exists

The forwarding email attaches two files (the zipped scan bundle and the
assessment `.md`). Neither available Gmail-draft tool can do that:

- the claude.ai Gmail MCP connector rewrites links / adds tracking (banned
  for mail sent in a committer's name), and
- the plain-text OAuth MCP (`mcp__gmail-plaintext__create_draft`, backed by
  Magpie's `oauth-draft`) is **deliberately** locked to a single
  `text/plain` part — its code and tests forbid attachments.

`forward-draft` fills the gap without breaking the no-tracking rule: the
body stays a single `text/plain` part (links verbatim, no redirects), and
the attachments ride as separate `multipart/mixed` parts. There is **no**
`text/html` body and **no** `multipart/alternative` — a build-time guard
(`assert_no_inline_html`, covered by tests) enforces that by construction.
An HTML *attachment* (a file) is still allowed; an inline HTML *body* is
refused.

It reuses the **same** OAuth credentials the plain-text MCP already uses
(`~/.config/apache-magpie/gmail-oauth.json`) — no new credential to set up.

## Usage

```bash
uv run --project tools/forward_draft forward-draft create \
    --to alice@apache.org --to bob@apache.org \
    --cc security@apache.org \
    --cc private@tooling.apache.org \
    --subject "[GLASSWING] ASVS Tooling security scan results Apache APISIX apisix-ingress-controller/main 2026-07-15" \
    --body-file /tmp/claude/forward-body.txt \
    --attach /tmp/claude/apisix-ingress-controller-2026-07-15-611487c.zip \
    --attach /tmp/claude/pre-forward-assessment-apisix-ingress-controller-2026-07-15-611487c.md
```

`--dry-run` builds and validates the message (attachments exist, sizes,
no inline HTML) and prints the plan **without** any network call. The
live path creates the draft `UNSENT` and prints its Gmail URL; the
operator reviews and sends from Gmail.

To reply **in an existing thread** — attaching the draft to it and setting
`In-Reply-To` / `References` from the thread's last message so it threads on
every client — pass `--thread-id <gmail-threadId>`. Omit it to start a new
thread.

### Attachment content types

Chosen by extension, then stdlib `mimetypes`, then
`application/octet-stream`:

| Extension | Content-Type |
| --- | --- |
| `.zip` | `application/zip` |
| `.md` / `.markdown` | `text/markdown` |
| `.json` | `application/json` |
| `.yml` / `.yaml` | `application/yaml` |
| `.txt` / `.csv` | `text/plain` / `text/csv` |
| `.pdf` | `application/pdf` |

## Credentials

Reads `~/.config/apache-magpie/gmail-oauth.json` (or
`$GMAIL_OAUTH_CREDENTIALS`, or `--credentials`). Same four-field shape as
the Magpie `oauth-draft` backend:

```json
{
  "client_id":     "...apps.googleusercontent.com",
  "client_secret": "...",
  "refresh_token": "...",
  "from_address":  "you@apache.org"
}
```

The `refresh_token` is traded for a short-lived access token at send time;
nothing is written back. See the Magpie `tools/gmail/oauth-draft` docs for
how to create the Google Cloud OAuth client and obtain the refresh token.

## Tests

```bash
uv run --project tools/forward_draft pytest -q
```

Covers the MIME builder (multipart/mixed shape, per-attachment
content-types, binary round-trip, the no-inline-HTML guard, missing-file
handling) and credential loading/location. No network is exercised.
