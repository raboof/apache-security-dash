---
name: triage-populate-cache
description: >-
  Pull new inbound security reports from the foundation-wide
  `security@apache.org` Ponymail archive into the local `report-cache/`, ready
  for assessment. Two-step flow inside one skill: a deterministic Python sweep
  (`sweep.py`) selects candidates on objective header facts only (thread head,
  addressed To an ASF `security@` alias, not a project's own specialized
  security list, not Cc'd to a `private@` list), downloads each survivor's
  body + attachments straight off the Ponymail HTTP API (reusing the
  ponymail-mcp session cookie), and writes one `report.md` per bundle (YAML
  front-matter + body, no separate metadata file). Then the agent (as part of
  THIS skill) reads each `_inbox/` bundle, drops any that are not genuine
  security reports (spam, marketing, phishing, automated bounces) via
  `./file.py <id> --remove`, and files each real report into its canonical
  `<date>/<pmc>/<keywords>/` home via `./file.py <id> --keywords "..."`. The
  tag keywords are short single words ordered most-specific to most-generic,
  with the hyphen-joined slug capped at 60 chars. Message bytes never
  enter the model's context during the sweep - only a compact funnel + table
  is printed. This SKILL is also the canonical reference for the
  `report-cache/` layout that downstream drafting and status SKILLs reuse. Use
  whenever the Security team says "pull new security reports", "populate the
  cache", "sweep security@", "file the inbox", "tag report X", or to refresh
  the cache before a triage session. It downloads and files; it does not
  draft, classify against the threat model, or send.
---

# triage-populate-cache SKILL

The **populate** phase of the report-triage pipeline. It answers one
question: "what genuine new vulnerability reports have arrived on
`security@apache.org` that the Security team still needs to triage?", and
puts a local copy of each in its canonical home on disk. Drafting replies
or forwards and reporting status are **separate downstream SKILLs** that
operate on the cache this one fills.

The skill has two halves, both driven by helpers in this directory:

1. **Sweep** - `sweep.py` downloads candidates from Ponymail. Deterministic
   header-based selection only.
2. **File** - the agent reads each downloaded `report.md`, then calls
   `file.py` to either dismiss a non-report or file a real report under
   `<date>/<pmc>/<keywords>/` with a short tag.

## When to invoke

- "Pull / sweep new security reports", "populate the report cache", "what
  came in on `security@`", "refresh the cache before triage".
- "File the inbox", "tag report X", "sort the spool", or right after a
  sweep to process what landed in `_inbox/`.

This SKILL never drafts, never sends, and never talks to anything outside
Ponymail (read) and the local `report-cache/` (write).

## Prerequisites: authentication

`security@apache.org` is a private list, so the sweep needs an
authenticated Ponymail session. It reuses the cookie that ponymail-mcp
caches at `~/.ponymail-mcp/session.json` (or the
`PONYMAIL_SESSION_COOKIE` env var). Sessions last ~20 h.

If `sweep.py` prints "No Ponymail session cookie found" or the funnel is
empty/unauthorized, re-authenticate via the ponymail-mcp `login` tool
(`auth_status` to check first), then re-run. `sweep.py` deliberately
refuses a cookie older than 20 h rather than firing dead requests.

## Phase 1: sweep

```bash
# Ongoing: new reports since the last sweep (incremental off the watermark)
.github/skills/triage-populate-cache/sweep.py

# Cold start / catch-up: rescan a whole window (dedup still prevents
# re-download). The current backlog starts 2026-05-24, so a 4-day window
# reaches it from late May:
.github/skills/triage-populate-cache/sweep.py --since 4d --full

# Preview without writing anything:
.github/skills/triage-populate-cache/sweep.py --since 4d --dry-run
```

The script self-installs its one dependency (PyYAML) via the `uv run`
shebang. Useful flags:

| Flag | Effect |
|------|--------|
| `--since` | Query window: `<N>d`, `yyyy-mm`, or a raw Ponymail `d` value (default `2d`) |
| `--full` | Rescan the whole window, ignoring the incremental watermark |
| `--limit N` | Stop after N new downloads (handy for a quick look) |
| `--dry-run` | Select + fetch, write nothing |
| `--from ADDR` | Only cache reports from this sender (e.g. triage one reporter) |
| `--list ADDR` | Sweep a different list (default `security@apache.org`) |

Only the funnel + a one-line-per-report table reach the model. To read a
report, open its `report.md` from the cache.

### How the sweep decides what to download

Selection is by objective header facts only (`classify.py`), no content
heuristics. The funnel, printed each run, is:

- **reply** - has an In-Reply-To header (not a thread head). Dropped from
  the cheap stats summary, no fetch.
- **automation-sender** - From is in the small `AUTOMATION_SENDERS`
  denylist (e.g. `notifications@github.com`) that never carries a report.
  Also dropped without fetch. Kept deliberately tiny so real mail is
  never missed.
- **not-security-addressed** - the To header is not any ASF `security@`
  alias (the message reached the archive by some other path). Checked
  after fetch (To/Cc are not in the summary).
- **specialized-pmc** - To is one of the specialized per-PMC security
  lists in `classify.py`'s `SPECIALIZED_LISTS` (e.g.
  `security@tomcat.apache.org`); that project runs its own security team,
  so the report is theirs, not ours.
- **pmc-private** - addressed (To/Cc) to a project's
  `private@<pmc>.apache.org`, so that PMC already owns it.
- **candidate** - downloaded into `_inbox/`.

`SPECIALIZED_LISTS` is hardcoded on purpose (only lists that actually
exist count); refresh it from apache/security-site's
[`project-coordinates.json`](https://raw.githubusercontent.com/apache/security-site/refs/heads/main/scripts/project-coordinates.json)
when projects gain or lose a dedicated team. A `security@<pmc>` address
in To also **auto-identifies the PMC** (recorded in the front-matter
`pmc:` field).
Because To/Cc are not in the stats summary, the sweep fetches each
surviving thread head to read them; for the normal incremental window
that is a handful of fetches, a full rescan over a long window is
correspondingly slower.

## Phase 2: file or dismiss

The deterministic sweep is intentionally coarse: it downloads everything
sent to a triageable `security@` address, which still includes spam,
marketing, and other non-reports. **Deciding whether each downloaded
message is a genuine new security report, and filing it, is this skill's
job, done by the agent reading the text** (not by code, and not deferred
to a downstream skill).

For each bundle in `report-cache/_inbox/`:

1. Open the bundle's `report.md` (and skim any file under `attachments/`).
   The YAML front-matter already carries the subject, reporter, and a
   sweep-detected `pmc` when the report was addressed to a
   `security@<pmc>` alias.
2. **Classify** it as one of:
   - **Report** - a genuine vulnerability report (even a weak, duplicate,
     or non-issue one: those are still real reports the team answers, so
     they are filed and the disposition is handled later).
   - **Not a report** - spam, phishing, marketing, a "thank you" note, an
     automated/bounce message, a vendor blast, etc. These get dismissed.
3. **Propose**, per bundle: **FILE** (with the PMC + suggested keywords)
   or **DISMISS** (with a one-line reason). Present the proposals as a
   short list and **get the user's confirmation before dismissing
   anything** - dismissal deletes files. Filing is also worth confirming
   so the keywords are right.
4. **Execute** the confirmed actions with `file.py` (below).

### Deciding PMC + keywords

- **PMC** - confirm the auto-detected `pmc:` if the sweep set it from a
  `security@<pmc>` recipient; otherwise read the body to determine the
  project (the subject/body almost always name it, e.g. "Apache Spark").
  Use the PMC slug (`spark`, `httpd`, `commons`, …).
- **Keywords** - short, lowercase, single-word terms capturing the
  issue. Each keyword must match `[a-z0-9_]+`: no `-` inside a keyword
  (use `_` if you must join two parts, e.g. `file_read`, not
  `file-read`). The directory name is the hyphen-join of the keywords,
  so the tag's space-separated form roundtrips without ambiguity.
  `file.py` enforces the character set and caps the hyphen-joined slug
  at 60 chars (long enough for a handful of words, short enough to keep
  paths and `ls` output legible). If `file.py` rejects your keywords,
  drop the least informative one or shorten it.
- **Keyword order: most specific to most generic.** The first keyword
  is the strongest filter, so similar reports cluster by their tag
  prefix. Concretely:
  1. Most specific PMC subproject / component (from
     `per_pmc.<pmc>` in [`tag-vocabulary.yaml`](tag-vocabulary.yaml),
     or a global `component` entry if the project has no subproject
     for this surface).
  2. The vulnerability class (`vuln_class` in the vocabulary).
  3. Optional further narrowing: a more specific component, a
     `modifier`, or a CVE-vector keyword.

  Examples: `digester xxe file_read` (commons-digester XXE leading to
  file read), `tribes deser cluster` (Tomcat Tribes cluster-channel
  deserialization), `dag operator rce` (Airflow operator-templating
  RCE via DAG). When the report is squarely about a vuln class with no
  meaningful subproject (e.g. a foundation-wide CVE intake), the vuln
  class can lead: `deser jdbc h2`.

### Pick keywords from the established vocabulary

Before inventing a new keyword, consult
[`tag-vocabulary.yaml`](tag-vocabulary.yaml) and **prefer an existing
canonical keyword over a synonym**. New reports clustering under the
same tag as historical ones is the whole point: the cache and the
sibling `email-classification/` archive both become searchable by tag.

The file has three sections:

- `global.vuln_class` - the lead keyword for almost every report
  (`rce`, `dos`, `deser`, `xss`, `ssrf`, `traversal`, `sqli`, `xxe`,
  `bypass`, `injection`, …).
- `global.component` - what the vuln hits (`file`, `path`, `session`,
  `header`, `jdbc`, `jwt`, `xml`, `yaml`, `regex`, `template`, …).
- `global.modifier` - optional third keyword to narrow (`read`,
  `write`, `stored`, `reflected`, `pre_auth`, `default`, …).
- `per_pmc.<pmc>` - subprojects / components specific to a PMC (e.g.
  commons `compress`, `jexl`, `fileupload`; airflow `dag`, `operator`;
  tomcat `tribes`, `hpack`; logging `log4j`, `log4j2`).

Rules of thumb:

1. **First keyword** is almost always a `vuln_class` entry. If the
   report names a deserialization sink, use `deser` (the canonical
   form), not `deserialization` or `deserialize`.
2. **Second keyword** is a `component` entry or, if the PMC has a list
   in `per_pmc`, an entry from there (subprojects sort the cache better
   than generic component words).
3. **Third keyword** (often omitted) is a `modifier` or a narrower
   component pointer.
4. If the report does not fit any existing keyword, a new one is fine -
   just make sure the form matches the existing style (single lowercase
   word, `_` not `-` for compounds). Mention the new keyword in your
   filing proposal so the user can decide whether it belongs in the
   vocabulary file.

### Helper commands

```bash
# File a genuine report (PMC auto-filled by the sweep -> omit --pmc):
.github/skills/triage-populate-cache/file.py <id> \
    [--pmc <slug>] --keywords "<up to 3 single words>"

# Dismiss a non-report:
.github/skills/triage-populate-cache/file.py <id> --remove \
    --reason "<why>"
```

`<id>` is the bundle's Ponymail id or any unique prefix (the truncated id
the sweep printed works). Add `--dry-run` to preview either action
without touching disk.

- **File** derives the date from the report, builds the tag
  `<pmc>/<date> <keywords>`, moves the bundle to
  `report-cache/<date>/<pmc>/<keywords>/`, and sets `status: filed` in
  the front-matter. `handled` stays `false` until the report is actioned
  downstream.
- **Dismiss** deletes the bundle, appends a record (id, subject,
  reporter, reason, timestamp) to `report-cache/.dismissed.json`, and
  keeps the id in `report-cache/.seen.json`. Because the sweep skips ids
  in `.seen.json`, a dismissed non-report is **never downloaded again**;
  `.dismissed.json` is the human-readable record of what was thrown out
  and why.

Work one report at a time so each gets the right keywords and the right
file/dismiss call. After processing, `_inbox/` holds only what is still
untriaged. Dismissals are one-way (the bundle is deleted), so confirm
them before running `--remove`.

## report-cache structure (canonical reference)

`report-cache/` lives at the repo root and is **gitignored** (see
`.gitignore`): cached report content, attachments, and drafts are never
committed. Downstream SKILLs MUST follow this layout.

```text
report-cache/
  .seen.json                      # dedup index: every ponymail id downloaded or dismissed
  .sweep-state.json               # incremental watermark: {"last_epoch": <int>}
  .dismissed.json                 # WRITTEN BY THIS SKILL (file.py --remove): non-reports
                                  #   removed from the spool (id + subject + reason); their
                                  #   ids stay in .seen.json so the sweep never re-downloads

  _inbox/<slug>/                  # WRITTEN BY THIS SKILL (sweep.py): untriaged report bundles
      report.md                   #   YAML front-matter (schema below) + full plain-text body
      attachments/                #   verbatim attachment bytes (md / pdf / zip / py / ...)
          <filename>

  <date>/<pmc>/<keywords>/        # WRITTEN BY THIS SKILL (file.py): triaged bundles
      report.md                   #   moved from _inbox; tag/pmc/keywords/status now set
      attachments/
      draft-forward.md            # WRITTEN BY THE DRAFTING SKILL: forward to the PMC
      draft-reply.md              #   ack / push-back to the reporter
```

- `<slug>` is the sanitized Ponymail message id (`[A-Za-z0-9._-]`).
- `<date>` is `yyyy-mm-dd` (the report's date).
- `<pmc>` is the PMC slug (e.g. `tomcat`).
- `<keywords>` is the hyphen-joined keyword set from the report tag
  (single words, ordered most-specific to most-generic, slug capped at
  60 chars).

The report **tag** stamped on filing has the form:

```text
<pmc>/<date> <space-separated keywords> [<wf>]
```

The optional trailing `<wf>` workflow marker (one of `reporter`,
`cve-allocation`, `non-issue-feedback`, `non-issue-docs`) is added by a
later actioning phase, not at filing time. The tag maps to the canonical
path `<date>/<pmc>/<keywords>/` (keywords hyphen-joined).

### `report.md` front-matter schema

`report.md` is the bundle's single file: YAML front-matter (Jekyll-style,
delimited by `---` lines), then the original plain-text report body.

```yaml
---
# Provenance (written by sweep.py, never edited downstream)
subject:        # report subject
reporter:       # From: email address
reporter_name:  # From: display name
message_id:     # RFC Message-ID header
ponymail_id:    # Ponymail mid / permalink id
archive_url:    # https://lists.apache.org/thread/<ponymail_id>
list:           # archiving list (e.g. <security.apache.org>)
to:             # To: header (recipient routing; null if absent)
cc:             # Cc: header (null if absent)
date:           # original message date
references:     # References header, or null (null == thread head)
attachments:    # list of {filename, content_type, size, hash}
fetched_at:     # ISO-8601 UTC fetch time

# Routing hints (written by sweep.py from To/Cc)
pmc:            # auto-assigned PMC slug when exactly one security@<pmc> recipient, else null
pmc_candidates: # all PMC slugs seen in security@<pmc> recipients, or null

# Triage state (pmc/keywords/tag set by file.py at filing time)
tag:            # full tag string, or null until filed
keywords:       # list of up to 3 single-word keywords, or null until filed
wf:             # workflow marker, set by a later actioning phase, or null
handled:        # false until the team has actioned the report
status:         # "inbox" -> "filed" (file.py) -> downstream skills advance further
---

<report body - the original plain-text message, verbatim>
```

Downstream SKILLs look up a report by `ponymail_id` / `message_id`, treat
the provenance block as read-only, and may add their own fields (e.g.
`decision`, `triager`, `drafted_at`) to the front-matter.

## Why a deterministic script, not the MCP

`get_mbox` / `get_email` return message text as MCP tool-result content,
so the model tokenizes every byte. This SKILL instead hits the Ponymail
HTTP API directly from `ponymail_api.py` (same cookie) and writes bodies
+ attachments to disk; only the summary table is tokenized. The
attachment download endpoint
(`email.lua?attachment=true&id=<mid>&file=<sha256>`), which the MCP does
not expose, was verified against the live API.

## Authorization and privacy

`security@apache.org` is foundation-private and can carry PII. Running
this SKILL is an authorized, local-processing activity by a Security-team
member who is entitled to read the list. Report content stays in the
gitignored `report-cache/` and is never committed. Keep the working copy
on a machine appropriate for the content, per the ponymail-mcp PII
guidance.

## Handoff

After a sweep + file pass, `_inbox/` is empty (or holds only what is
still pending a triage decision), and the canonical
`<date>/<pmc>/<keywords>/` directories hold the filed reports. The
**drafting SKILL** then assesses each filed report against the PMC's
threat model and adds `draft-forward.md` / `draft-reply.md`. A **status
SKILL** reports handled/unhandled counts across the cache. Both rely on
the layout and front-matter schema documented above.
