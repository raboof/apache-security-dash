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

# report-cache

The single owner of `report-cache/` storage.
Every read and write of a report bundle or the shared `index.json` goes through this package,
so the storage format lives in exactly one place
instead of being copied into each tool.

It has two faces:

- a **CLI** (`report-cache`) the triage-populate-cache SKILL runs
  to classify and file a downloaded bundle (the `move` / `set` / `classify` subcommands);
- a **Python API** (`report_cache.report_md`, `report_cache.index`)
  that `populate-cache` (download) and `inbox-manager` (send + archive) import
  instead of re-implementing the storage.

It operates only on the local cache.
It never talks to a mailbox and never sends:
reading the inbox is `populate-cache`'s job, sending is `inbox-manager`'s.

## Storage layout

A bundle is a directory holding one `report.md`
(YAML front-matter with the message's Gmail provenance, then the body),
the verbatim `raw.eml`,
and any `attachments/`.
The cache root also carries `index.json`,
mapping each report's RFC `Message-ID`
to where its bundle lives and its triage state:

```
report-cache/
  index.json                # Message-ID -> Entry {path, pmc, labels, status, disposition, ...}
  <pmc>/<date>-<keywords>/   # a classified report: report.md + raw.eml + attachments/
```

A freshly downloaded bundle (written by `populate-cache`) starts at `status: downloaded`
under a message-id-slug leaf.
Classifying moves it to the flat `<pmc>/<date>-<keywords>` leaf
and renames it from the message-id slug to the keyword slug,
so the Message-ID is no longer recoverable from the path;
`index.json` keeps every bundle findable by Message-ID
without scanning every `report.md`.
Label collections such as `zzz-non-issue/<pmc>/...` are label *prefixes*
(see `set --collection`), not directories.

## CLI

Three subcommands over the local cache
(the global `--cache-dir` defaults to the repo `report-cache/`):

```bash
# classify = the skill's one-shot: move under <pmc>/<date>-<keywords>, add the label, set the state
uv run --project tools/report_cache report-cache classify 0af31c \
    --pmc spark --keywords "xxe rest api"

# a report the PMC already received: status assessed + disposition track (nothing for us to send)
uv run --project tools/report_cache report-cache classify tomcat-9912 \
    --pmc tomcat --keywords "deser tribes" --track-only

# move = relocate a bundle (destination <pmc>/<date>-<slug>; slug defaults to the keywords)
uv run --project tools/report_cache report-cache move 0af31c --pmc spark --keywords "xxe rest api"

# set = update index state / labels in place, without moving
uv run --project tools/report_cache report-cache set spammy-7710 --disposition skip
uv run --project tools/report_cache report-cache set accenture-77 --disposition decline \
    --collection zzz-non-issue --pmc hadoop --keywords "aaa_dependencies"
uv run --project tools/report_cache report-cache set 0af31c \
    --add-label "spark/CVE-2026-1234 xxe rest api"
```

`<id>` matches an index entry by RFC `Message-ID` (a unique prefix works)
or by the bundle's leaf directory name.
`report.md` (Gmail provenance) is never rewritten;
all triage state lives in the index.

## Python API

The storage, importable by the other tools instead of re-implementing it:

```python
from report_cache import index
from report_cache.report_md import BUNDLE_FILE, read

header, body = read(bundle / BUNDLE_FILE)   # Gmail provenance as a Header (addresses, date, ...)
idx = index.load(cache_root)                # {Message-ID: Entry}
entry = idx["<msg-id@host>"]                # entry.pmc, entry.status, entry.labels, ...
index.write(cache_root, idx)                # persist the mutated index
```

## Develop

```bash
uv sync --project tools/report_cache --extra test
uv run --project tools/report_cache pytest
```
