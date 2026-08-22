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

# The report-cache Agent Contract

## Purpose

`report-cache` has two faces.
Programmatic callers (`populate-cache` on download, `inbox-manager` on send) use the **Python API**
(`report_cache.index`, `report_cache.report_md`),
which hands back typed `Entry` / `Header` objects.
The **CLI** documented here exists for one consumer only:
the triage agent (the classifying pass in triage-populate-cache,
the assessing pass in triage-assess).
Its whole job is to let that agent work a bundle
without knowing the on-disk layout, the front-matter schema, or the index format.

Two invariants hold the design together:

- The agent touches a bundle **only** through these commands.
  It never opens `report.md`, `index.json`, or a file under the bundle directory by path.
  The storage format is `report-cache`'s secret; the agent sees text.
- Reads never mutate.
  The only writers are the triage verbs (`move` / `set` / `classify`)
  and `put-artifact` / `remove-artifact`.
  `index.json` is the single source of truth for triage state,
  and nothing outside `report-cache` writes it,
  which is why there is no "reindex": the index is never out of step with a second copy.

## Identifying a bundle

Every command that acts on one bundle takes an `<id>`,
resolved the same way everywhere (the existing `find_entry` rule):
an exact RFC `Message-ID` or bundle-leaf directory name wins,
otherwise a unique prefix of either is accepted;
no match or an ambiguous prefix is an error.

## Reading

### `list [--status <s>] [--pmc <p>] [--disposition <d>]`

Enumerate the indexed bundles as a table
(short message-id, date, pmc, status, disposition, subject),
newest first, narrowed by any of the filters.
This is the loop driver:
the classifying pass walks `list --status downloaded`,
the assessing pass walks `list --status classified`.
The agent enumerates through this, never by globbing the tree.

### `show <id>`

The merged report view, as text, not JSON.
A curated, labeled metadata block
(the fields the agent needs, drawn from the Gmail `Header` **and** the index `Entry`),
then `---`, then the body verbatim.
Attachments and any triage artifacts present are listed by name
so the agent knows what it can fetch:

```
Message-ID: <xxe-123@example.com>
Date:       2026-05-24
From:       Jane Reporter <jane@example.com>
To:         security@spark.apache.org
Subject:    XXE in the Spark REST API

pmc:         spark  (guessed from To)
status:      downloaded
disposition: -
labels:      -
attachments: poc.xml  (application/xml, 1.2 KB)
artifacts:   (none)

---

<the body, verbatim Markdown>
```

The body is emitted as text rather than a JSON string on purpose:
it is the payload the agent reasons over,
often carrying quoted config, stack traces, and PoC snippets
whose formatting must survive intact,
and JSON escaping would only degrade it and cost tokens.

### `get-attachment <id> <name>`

Render one attachment to text so the agent never has to read raw bytes.
The converter is chosen from the attachment's recorded content type
(falling back to its extension):

| Content type | Conversion |
|---|---|
| `text/plain`, `text/markdown` | emitted as-is |
| `text/html` | HTML to Markdown via `markdownify` |
| `application/pdf` | text extraction via `pypdf` |
| anything else | a one-line "unsupported (`<type>`, `<size>` bytes)" notice, nothing dumped |

### `get-artifact <id> <name>`

Print one triage artifact a prior pass wrote (see `put-artifact`),
so a later agent can read `summary.md`, `reason.md`, or a draft it did not write itself.

## Writing

### `put-artifact <id> <name> [--from <file>]`

Store a triage artifact in the bundle:
content from stdin by default, or from `--from <file>`.
`report-cache` stays the single writer of bundle storage,
so the agent supplies a name and content and never learns the path.
This is how triage-assess deposits `summary.md`, `reason.md`, `draft-reply.md`, and the like.

`<name>` is a free-form but safe filename:
a plain relative name, no path separators or traversal, resolved inside the bundle only.

### `remove-artifact <id> <name>`

Delete a triage artifact a prior pass wrote.
This is for a flipped decision:
an assessor that drafted `summary.md` for a forward and then re-decides to decline
drops the stale draft here,
so `inbox-manager` never pre-fills a send preview from an artifact
that no longer matches the disposition.
The reserved report files (`report.md`, `raw.eml`) are refused,
and removing an artifact that does not exist is an error,
so a typo cannot pass for a cleanup.

### `move` / `set` / `classify`

The triage-state mutations (relocate a bundle, edit index status/disposition/labels,
and the classify one-shot).
These predate this contract; see `report-cache <verb> --help`.

## Not in scope

The contract deliberately stops at the local cache:

- **No sending, no drafts on the wire.** Delivery is `inbox-manager`'s job.
- **No live mailbox.** Reading the inbox is `populate-cache`'s job;
  `report-cache` only ever sees what has already been downloaded.
- **No direct storage access by the agent.** `report.md` and `index.json` are format details,
  reachable only through the verbs above.

## Relationship to the mail-source contract

This is **not** an implementation of Magpie's `mail-source` contract.
That contract abstracts live or archived **mailbox backends** (Gmail, PonyMail, IMAP, mbox)
over raw mail threads, with a multi-backend resolution chain, drafts, and thread URLs.
`report-cache` sits a layer below that:
it is the local **triage-state store** for reports a mail-source already delivered,
and its unit is a report bundle, not a raw thread.
It borrows the contract's discipline
(named operations, stable text shapes, capability honesty, a firm read/write split)
without borrowing its backend-resolution machinery, drafting, or send semantics.
