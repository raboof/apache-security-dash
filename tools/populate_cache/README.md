<!--
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
-->

# populate-cache

Ingest new security reports from the Gmail `security@` inbox into the local
`report-cache/` via the read-only Gmail API. This is the deterministic
**download** step of the triage-populate-cache SKILL: it pulls bytes off the
mailbox and writes one bundle per message: labelling, disposition and
finalisation are left to the SKILL.

## What it does

For every new **thread head** it has not seen before (dedup keys on the RFC
`Message-ID`), it writes a `report.md` bundle into the message's dated, per-PMC
home:

```
report-cache/<date>/<pmc>/<message-id-slug>/report.md       # PMC named by a security@<pmc> recipient
report-cache/<date>/_unsorted/<message-id-slug>/report.md   # no PMC in the headers
report-cache/<date>/<pmc>/<message-id-slug>/raw.eml         # verbatim RFC822 message
report-cache/<date>/<pmc>/<message-id-slug>/attachments/    # decoded attachments, if any
```

Each bundle is YAML front-matter (subject, reporter, message-id, recipients,
date, attachments, ...) followed by the body as Markdown (HTML parts are
converted with `markdownify`), written with `status: downloaded` and
`keywords: null`. The verbatim RFC822 message is also saved as `raw.eml`, a
safety net in case the parsing or Markdown conversion ever drops something. The
SKILL's labelling step assigns the label, places the `_unsorted` bundles,
renames the leaf to the keyword slug, and promotes the status.

Any **custom Gmail labels** already on the message seed the message's `tags`
field (system labels like `INBOX`/`UNREAD` are ignored). `tags` are the
message's Gmail labels: the tool records what is there at download, the SKILL
extends the same field as it labels, and a later tool reconciles `tags` against
Gmail. A pre-existing label is a routing hint, not a sign the report was already
handled: a message still in the inbox is untriaged (a handled one would have
been archived, see *Delete handled reports* below). Gmail auto-applies some labels by subject
keyword, e.g. a follow-up that names a public CVE number gets that CVE's
existing label; the SKILL uses such a label to relate the report to a prior one,
then triages it normally. A report with no labels yet has `tags: null`. Reading
labels needs only the `gmail.readonly` scope.

The tool is **read-only** on the mailbox: it authenticates with the
`gmail.readonly` scope, which cannot modify, move or delete mail. It only writes
under `report-cache/`.

## Delete handled reports

A report stays in the Gmail inbox until the team archives it, so a cached bundle
whose message is **no longer in the inbox** has been handled. On a full inbox
scan the tool deletes such bundles (and their index entry, plus the now-empty
`<pmc>` directory) rather than keeping a tombstone: the message is gone from the
inbox, so a later scan will not re-download it.

The delete sweep only runs on a full scan (default `--label INBOX`, no
`--query`), where the scanned set is the complete current inbox; a narrowed scan
would wrongly "handle" everything outside its window, so it is skipped there.
Pass `--no-delete` to turn it off entirely, or `--dry-run` to see what would be
deleted.

## Thread heads and skips

Only **thread heads** become reports; replies are tracked by their shared label,
not as separate bundles. A message is a head when it is the Gmail thread root
(`id == threadId`) **or** has no `In-Reply-To` header. The first rule keeps a
standalone reply whose parent is not in this mailbox; the second keeps a fresh
mail that Gmail merged into an existing thread by subject (e.g. a recurring
`Currently open security reports for <pmc>`).

Heads that are automated notifications, not fresh reports, are skipped (a
header-only decision adapted from `inbox_manager`):

- CVE-process mail injected by `security-vm-he-fi.apache.org` (per the `Received`
  chain) - CVE reservations / status churn;
- CERT/CC VINCE notifications (`From: cert+donotreply@cert.org`);
- SVN commit mail (`Subject:` starts `svn commit: r`).

Whether a *kept* message is a genuine, in-scope report is decided downstream by
the SKILL reading the body.

## PMC routing (tier-1 only)

The PMC is taken from the **address-domain** signal only: a
`security@<pmc>.apache.org` address among the `To`/`Cc` recipients, validated
against the authoritative Whimsy committee-info slug set. This is the strong
signal of `whimsy_lookup.pmc_guess`; weaker prose-token and product-name
guesses are deliberately not applied here, so the tool never misfiles into the
canonical tree on a weak signal. Anything without an address-domain hit goes to
`<date>/_unsorted/`, where the SKILL (which has the body in hand) resolves the
PMC. If Whimsy is unreachable the slug set is empty and every report routes to
`_unsorted`.

## Configuration

OAuth2 credentials for the Gmail account are read from the environment (a local
`.env` is loaded automatically). The refresh token must carry the
`https://www.googleapis.com/auth/gmail.readonly` scope:

| Variable | Purpose |
|---|---|
| `GMAIL_READONLY_OAUTH_CLIENT_ID` | OAuth2 client id |
| `GMAIL_READONLY_OAUTH_CLIENT_SECRET` | OAuth2 client secret |
| `GMAIL_READONLY_OAUTH_REFRESH_TOKEN` | OAuth2 refresh token (gmail.readonly) |

This is the **read-only** Gmail API token. It is named to stay distinct from
`inbox_manager`'s **read/write** IMAP token (`GMAIL_READWRITE_OAUTH_*`), so both
tools can share one `.env` without colliding.

The mailbox is whichever account the refresh token belongs to (the Gmail API
`me` user); no separate mailbox address is needed.

## Usage

```bash
uv run --project tools/populate_cache populate-cache                    # pull new reports
uv run --project tools/populate_cache populate-cache --dry-run          # report, write nothing
uv run --project tools/populate_cache populate-cache --limit 5          # stop after 5 new bundles
uv run --project tools/populate_cache populate-cache --query newer_than:30d  # narrow the scan
```

| Flag | Default | Meaning |
|---|---|---|
| `--cache-dir` | repo `report-cache/` | cache root to write into |
| `--label` | `INBOX` | Gmail label to sweep |
| `--query` | none | Gmail search to narrow the scan (e.g. `newer_than:30d`) |
| `--limit` | `0` (no limit) | max new reports to download |
| `--dry-run` | off | select + report, write nothing |
| `--no-delete` | off | skip deleting handled (left-the-inbox) bundles |

## Development

```bash
uv sync --project tools/populate_cache --extra test
uv run --project tools/populate_cache pytest
```

The message-parsing primitives (`email_utils.py`) are derived from the
`inbox_manager` tool; the Gmail API access layer (`gmail.py`) is new.
