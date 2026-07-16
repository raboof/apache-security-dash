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

Ingest new security reports from the Gmail `security@` inbox into the local `report-cache/`,
through the read-only Gmail API.
This is the deterministic **download** step of the triage-populate-cache SKILL:
it pulls bytes off the mailbox and writes one bundle per new report.
Everything after the download belongs to the [`report-cache`](../report_cache/README.md) tool and the SKILL.

The tool is **read-only** on the mailbox:
it authenticates with the `gmail.readonly` scope,
which cannot modify, move or delete mail.
It only writes under `report-cache/`.

## Where the reports land

The bundle and index format is `report-cache`'s, not this tool's:
see its [Storage layout](../report_cache/README.md#storage-layout).
Each download writes the message's Gmail provenance, the verbatim `raw.eml` and any attachments,
and seeds one triage record at `status: downloaded`.
Dedup keys on the RFC `Message-ID`, so a re-run never duplicates a bundle.

Read cached reports through the `report-cache` CLI rather than off disk;
the storage layout is its concern, and it is free to change.

## Configuration

OAuth2 credentials for the Gmail account are read from the environment
(a local `.env` is loaded automatically).
The refresh token must carry the `https://www.googleapis.com/auth/gmail.readonly` scope:

| Variable                             | Purpose                               |
|--------------------------------------|---------------------------------------|
| `GMAIL_READONLY_OAUTH_CLIENT_ID`     | OAuth2 client id                      |
| `GMAIL_READONLY_OAUTH_CLIENT_SECRET` | OAuth2 client secret                  |
| `GMAIL_READONLY_OAUTH_REFRESH_TOKEN` | OAuth2 refresh token (gmail.readonly) |

This is the **read-only** Gmail API token.
It is named to stay distinct from `inbox_manager`'s **read/write** IMAP token
(`GMAIL_READWRITE_OAUTH_*`), so both tools can share one `.env` without colliding.

The mailbox is whichever account the refresh token belongs to (the Gmail API `me` user);
no separate mailbox address is needed.

## Usage

```bash
uv run --project tools/populate_cache populate-cache                    # pull new reports
uv run --project tools/populate_cache populate-cache --dry-run          # report, write nothing
uv run --project tools/populate_cache populate-cache --limit 5          # stop after 5 new bundles
uv run --project tools/populate_cache populate-cache --query newer_than:30d  # narrow the scan
```

| Flag          | Default              | Meaning                                                       |
|---------------|----------------------|---------------------------------------------------------------|
| `--cache-dir` | `$REPORT_CACHE_DIR`, else the repo's `report-cache/` | cache root to write into      |
| `--query`     | none                 | Gmail search to narrow the inbox scan (e.g. `newer_than:30d`) |
| `--limit`     | `0` (no limit)       | max new reports to download                                   |
| `--dry-run`   | off                  | select + report, write nothing                                |
| `--no-delete` | off                  | skip deleting handled (left-the-inbox) bundles                |

## What becomes a report

Only **thread heads** are downloaded;
replies belong to an already-ingested thread and are tracked by its shared label,
not as separate bundles.
A message is a head when:

* it is the Gmail thread root (`id == threadId`),
* or when it carries no `References` header.

The root test is Gmail's own threading, so it errs towards keeping:
a reply Gmail could not thread (a parent in Spam, a rewritten subject)
looks like a root and is downloaded too.
That is deliberate: a missed report costs more than a re-read follow-up,
and the SKILL recognizes it from the body.

Heads that are automated notifications, not fresh reports, are skipped
(a header-only decision):

- CVE-process mail injected by `security-vm-he-fi.apache.org` (per the `Received` chain);
- CERT/CC VINCE notifications (`From: cert+donotreply@cert.org`);
- SVN commit mail (`Subject:` starts `svn commit: r`).

Whether a *kept* message is a genuine, in-scope report
is decided downstream by the SKILL reading the body.

## Delete handled reports

A report stays in the Gmail inbox until the team archives it,
so a cached bundle whose message is **no longer in the inbox** has been handled:
the tool deletes it and drops its triage record,
rather than keeping a tombstone.
The message is gone from the inbox, so a later scan will not re-download it.

The sweep only runs on a full scan (the default, i.e. no `--query`),
where the scanned set is the complete current inbox;
a narrowed scan would wrongly "handle" everything outside its window, so it is skipped there.
Pass `--no-delete` to turn it off entirely, or `--dry-run` to see what would be deleted.

## Development

```bash
uv sync --project tools/populate_cache --extra test
uv run --project tools/populate_cache pytest
```

The message-parsing primitives (`email_utils.py`) are derived from the `inbox_manager` tool;
the Gmail API access layer (`gmail.py`) is new.
