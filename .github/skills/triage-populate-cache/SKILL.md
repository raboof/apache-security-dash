---
name: triage-populate-cache
description: >-
  Populate the local report-cache with new inbound security reports from the
  foundation-wide security@apache.org Ponymail archive, ready for triage. Runs
  a deterministic Python sweep (sweep.py) that talks to the Ponymail HTTP API
  directly, reusing the ponymail-mcp session cookie, and writes each report's
  full body + attachments to disk while keeping message bytes out of the
  model's context (only a compact funnel + table is printed). A classifier
  drops the firehose of spam / CVE-workflow automation / SVN+GitHub
  notifications / replies, and the To/Cc headers drop reports already in a
  PMC's hands and auto-assign the PMC. This SKILL is also the canonical
  reference for the report-cache directory layout that the downstream filing,
  drafting, and status SKILLs reuse. Use whenever the Security team says
  "pull new security reports", "populate the cache", "sweep security@",
  "what new reports came in", or to refresh the cache before a triage session.
  Populates report-cache/_inbox/ only; it does not file, draft, or send.
---

# triage-populate-cache SKILL

The **populate** phase of the report-triage pipeline. It answers one
question: "what genuine new vulnerability reports have arrived on
`security@apache.org` that the Security team still needs to triage?", and
puts a local copy of each on disk. Filing, drafting replies/forwards, and
status reporting are **separate downstream SKILLs** that operate on the
cache this one fills.

## When to invoke

- "Pull / sweep new security reports", "populate the report cache",
  "what came in on `security@`", "refresh the cache before triage".
- At the start of a triage session, to bring `_inbox/` up to date.

Do **not** use this SKILL to file, tag, draft, or send anything. It only
writes untriaged bundles into `report-cache/_inbox/`.

## Prerequisites: authentication

`security@apache.org` is a private list, so the sweep needs an
authenticated Ponymail session. It reuses the cookie that ponymail-mcp
caches at `~/.ponymail-mcp/session.json` (or the
`PONYMAIL_SESSION_COOKIE` env var). Sessions last ~20 h.

If `sweep.py` prints "No Ponymail session cookie found" or the funnel is
empty/unauthorized, re-authenticate via the ponymail-mcp `login` tool
(`auth_status` to check first), then re-run. `sweep.py` deliberately
refuses a cookie older than 20 h rather than firing dead requests.

## How to run

```bash
# Ongoing: new reports since the last sweep (incremental off the watermark)
.github/skills/triage-populate-cache/sweep.py

# Cold start / catch-up: reclassify a whole window (dedup still prevents
# re-download). The current backlog starts 2026-05-24, so a 4-day window
# reaches it from late May:
.github/skills/triage-populate-cache/sweep.py --since 4d --full

# Preview without writing anything:
.github/skills/triage-populate-cache/sweep.py --since 4d --dry-run

# Audit what the keyword stage drops (denylist only, shows the spam residue):
.github/skills/triage-populate-cache/sweep.py --no-keyword-filter --dry-run
```

The script self-installs its one dependency (PyYAML) via the `uv run`
shebang. Useful flags:

| Flag | Effect |
|------|--------|
| `--since` | Query window: `<N>d`, `yyyy-mm`, or a raw Ponymail `d` value (default `2d`) |
| `--full` | Reclassify the whole window, ignoring the incremental watermark |
| `--limit N` | Stop after N new downloads (handy for a quick look) |
| `--dry-run` | Fetch + classify, write nothing |
| `--include-internal` | Keep `@apache.org` senders (CVE workflow, announcements) |
| `--no-keyword-filter` | Disable the report-subject signal (denylist only) |
| `--filter-config FILE` | YAML overriding the classifier rules (see `classify.py`) |
| `--list ADDR` | Sweep a different list (default `security@apache.org`) |

Only the funnel + a one-line-per-report table reach the model. To read a
report, open its `report.txt` (and any attachment) from the cache.

## report-cache structure (canonical reference)

`report-cache/` lives at the repo root and is **gitignored** (see
`.gitignore`): cached report content, attachments, and drafts are never
committed. Downstream SKILLs MUST follow this layout.

```text
report-cache/
  .seen.json                      # dedup index: every ponymail id ever downloaded
  .sweep-state.json               # incremental watermark: {"last_epoch": <int>}

  _inbox/<slug>/                  # WRITTEN BY THIS SKILL: untriaged report bundles
      report.txt                  #   full plain-text body (not a snippet)
      meta.yaml                   #   provenance + triage state (schema below)
      attachments/                #   verbatim attachment bytes (md / pdf / zip / py / ...)
          <filename>

  <date>/<pmc>/<keywords>/        # WRITTEN BY THE FILING SKILL: triaged bundles
      report.txt                  #   (moved from _inbox, unchanged)
      meta.yaml                   #   tag / pmc / keywords / wf filled in; status advanced
      attachments/
      draft-forward.md            # WRITTEN BY THE DRAFTING SKILL: forward to the PMC
      draft-reply.md              #   ack / push-back to the reporter
```

- `<slug>` is the sanitized Ponymail message id (`[A-Za-z0-9._-]`).
- `<date>` is `yyyy-mm-dd` (the report's date).
- `<pmc>` is the PMC slug (e.g. `tomcat`).
- `<keywords>` is the hyphen-joined keyword set from the report tag.

The report **tag** the team assigns has the form:

```text
<pmc>/<date> <space-separated keywords> [wf:(reporter|cve-allocation|non-issue-feedback|non-issue-docs)]
```

which maps to the canonical path `<date>/<pmc>/<keywords>/` plus the
optional `wf` workflow marker.

### meta.yaml schema

Written by this SKILL on download; later fields are completed by the
filing SKILL.

```yaml
# Provenance (written by triage-populate-cache, never edited downstream)
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

# Routing hints (written by triage-populate-cache from To/Cc)
pmc:            # auto-assigned PMC slug when exactly one security@<pmc> recipient, else null
pmc_candidates: # all PMC slugs seen in security@<pmc> recipients, or null

# Triage state (pmc/keywords/wf/tag completed by the filing SKILL)
tag:            # full tag string, or null until filed
keywords:       # list of keywords, or null until filed
wf:             # workflow marker, or null
handled:        # false until the team has actioned the report
status:         # "inbox" -> (filing SKILL advances this)
```

Downstream SKILLs find a report by `ponymail_id` / `message_id` and treat
the provenance block as read-only.

## How the sweep decides what to keep

`security@apache.org` is a firehose (~1000 thread heads/week). The funnel,
printed each run, is:

- **reply** - has an In-Reply-To header (not a thread head).
- **automation-sender** - GitHub/JIRA/SVN/gitbox notification senders.
- **internal** - `@apache.org` sender (CVE workflow, outbound
  announcements, commits). Override with `--include-internal`.
- **noise-subject** - `Re:` / `svn commit` / `is now ready` / etc.
- **no-report-signal** - external thread head whose subject shows no
  security/Apache signal (the bulk of the residual spam). Disable the
  signal requirement with `--no-keyword-filter`.
- **already-answered** - a thread head whose thread already drew a reply
  from someone other than the reporter, i.e. another team member triaged
  it. Detected from the In-Reply-To graph of the swept window (reporter
  self-follow-ups do not count).
- **pmc-private** - reaches the central list but is also addressed to a
  project's `private@<pmc>.apache.org`, so that PMC already owns it (the
  Security team does not triage it). Detected from To/Cc after fetch.
- **candidate** - kept, downloaded into `_inbox/`.

Rules live in `classify.py` as data (sender denylist, internal domains,
noise-subject regexes, report-subject regexes) and can be overridden per
operator with `--filter-config`. Recurring spammers can be added to the
sender denylist.

### Routing rule (why a report is "ours")

All `security@*.apache.org` aliases exist; projects with a custom contact
in apache/security-site's `project-coordinates.json` get their reports
routed straight to the PMC and never reach the central archive. Anything
that *does* reach `security@apache.org` needs Security-team triage **unless
it is also addressed to a project's `private@` list** (then it is already
the PMC's). A `security@<pmc>` recipient both confirms the report fell
through to central triage and **auto-identifies the PMC** (recorded in
`meta.yaml: pmc`). This is derived from the To/Cc headers via regex, so no
per-PMC list needs hardcoding and new PMCs work with no code change.

## Why a deterministic script, not the MCP

`get_mbox` / `get_email` return message text as MCP tool-result content, so
the model tokenizes every byte. This SKILL instead hits the Ponymail HTTP
API directly from `ponymail_api.py` (same cookie) and writes bodies +
attachments to disk; only the summary table is tokenized. The attachment
download endpoint (`email.lua?attachment=true&id=<mid>&file=<sha256>`),
which the MCP does not expose, was verified against the live API.

## Authorization and privacy

`security@apache.org` is foundation-private and can carry PII. Running this
SKILL is an authorized, local-processing activity by a Security-team member
who is entitled to read the list. Report content stays in the gitignored
`report-cache/` and is never committed. Keep the working copy on a machine
appropriate for the content, per the ponymail-mcp PII guidance.

## Handoff

After a sweep, `_inbox/` holds untriaged bundles. The downstream **filing
SKILL** reads each `report.txt`, confirms/sets the PMC and keywords, writes
the `tag`, and moves the bundle to `<date>/<pmc>/<keywords>/`. The
**drafting SKILL** adds `draft-forward.md` / `draft-reply.md`. A **status
SKILL** reports handled/unhandled counts across the cache. All of them rely
on the structure documented above.
