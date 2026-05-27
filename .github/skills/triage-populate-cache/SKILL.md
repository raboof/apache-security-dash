---
name: triage-populate-cache
description: >-
  Populate the local report-cache with new inbound security reports from the
  foundation-wide security@apache.org Ponymail archive, ready for triage. Runs
  a deterministic Python sweep (sweep.py) that talks to the Ponymail HTTP API
  directly, reusing the ponymail-mcp session cookie, and writes each report's
  full body + attachments to disk while keeping message bytes out of the
  model's context (only a compact funnel + table is printed). The deterministic
  sweep uses objective header facts only, no content heuristics: it downloads a
  message iff it is a thread head, addressed To an ASF security@ alias that is
  NOT a project's own specialized security list (those projects triage
  themselves), and not addressed (To/Cc) to a private@ list. Then the agent (as
  part of THIS skill) reads each downloaded message and removes any that are
  not genuine security reports -- that judgement is the skill's, not code's.
  This SKILL is also the canonical reference for the report-cache directory
  layout that the downstream filing, drafting, and status SKILLs reuse. Use
  whenever the Security team says "pull new security reports", "populate the
  cache", "sweep security@", "what new reports came in", or to refresh the
  cache before a triage session. It does not file, tag, draft, or send.
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

This SKILL downloads candidate reports and then **removes the non-reports**
among them (see below), leaving genuine reports in `report-cache/_inbox/`. It
does not file, tag, draft, or send.

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
report, open its `report.txt` (and any attachment) from the cache.

## report-cache structure (canonical reference)

`report-cache/` lives at the repo root and is **gitignored** (see
`.gitignore`): cached report content, attachments, and drafts are never
committed. Downstream SKILLs MUST follow this layout.

```text
report-cache/
  .seen.json                      # dedup index: every ponymail id downloaded or dismissed
  .sweep-state.json               # incremental watermark: {"last_epoch": <int>}
  .dismissed.json                 # WRITTEN BY THE FILING SKILL: false positives removed
                                  #   from the spool (id + subject + reason); their ids
                                  #   stay in .seen.json so the sweep never re-downloads them

  _inbox/<slug>/                  # WRITTEN BY THIS SKILL: untriaged report bundles
      report.txt                  #   full plain-text body (not a snippet)
      meta.yaml                   #   provenance + triage state (schema below)
      attachments/                #   verbatim attachment bytes (md / pdf / zip / py / ...)
          <filename>

  <date>/<pmc>/<keywords>/        # WRITTEN BY THE FILING SKILL: triaged bundles
      report.txt                  #   (moved from _inbox, unchanged)
      meta.yaml                   #   tag / pmc / keywords filled in; status advanced
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
<pmc>/<date> <space-separated keywords> [<wf>]
```

The filing SKILL stamps the `<pmc>/<date> <keywords>` part. The optional
trailing `<wf>` workflow marker (one of `reporter`, `cve-allocation`,
`non-issue-feedback`, `non-issue-docs`) is added by a later actioning phase,
not at filing time. The tag maps to the canonical path
`<date>/<pmc>/<keywords>/` (keywords hyphen-joined).

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

# Triage state (pmc/keywords/tag set by the filing SKILL)
tag:            # full tag string, or null until filed
keywords:       # list of keywords, or null until filed
wf:             # workflow marker, set by a later actioning phase, or null
handled:        # false until the team has actioned the report
status:         # "inbox" -> (filing SKILL advances this)
```

Downstream SKILLs find a report by `ponymail_id` / `message_id` and treat
the provenance block as read-only.

## How the sweep decides what to download

The sweep selects on objective header facts only (`classify.py`), no content
heuristics. The funnel, printed each run, is:

- **reply** - has an In-Reply-To header (not a thread head). Dropped from the
  cheap stats summary, no fetch.
- **automation-sender** - From is in the small `AUTOMATION_SENDERS` denylist
  (e.g. `notifications@github.com`) that never carries a report. Also dropped
  without fetch. Kept deliberately tiny so real mail is never missed.
- **not-security-addressed** - the To header is not any ASF `security@` alias
  (the message reached the archive by some other path). Checked after fetch
  (To/Cc are not in the summary).
- **specialized-pmc** - To is one of the specialized per-PMC security lists in
  `classify.py`'s `SPECIALIZED_LISTS` (e.g. `security@tomcat.apache.org`); that
  project runs its own security team, so the report is theirs, not ours.
- **pmc-private** - addressed (To/Cc) to a project's `private@<pmc>.apache.org`,
  so that PMC already owns it.
- **candidate** - downloaded into `_inbox/`.

`SPECIALIZED_LISTS` is hardcoded on purpose (only lists that actually exist
count); refresh it from project-coordinates.json when projects gain or lose a
dedicated team. A `security@<pmc>` address in To also **auto-identifies the
PMC** (recorded in `meta.yaml: pmc`). Because To/Cc are not in the stats
summary, the sweep fetches each surviving thread head to read them; for the
normal incremental window that is a handful of fetches, a full rescan over a
long window is correspondingly slower.

## Remove non-reports (this skill's filter)

The deterministic sweep is intentionally coarse: it downloads everything sent
to a triageable `security@` address, which still includes spam, marketing, and
other non-reports. **Deciding whether each downloaded message is a genuine new
security report is this skill's job, done by the agent reading the text** (not
by code, and not deferred downstream). After a sweep:

1. Read each new `_inbox/<slug>/report.txt` (and skim any attachment).
2. **Remove** the bundle (`rm -rf` the `_inbox/<slug>/` directory) for anything
   that is not a security report: spam, phishing, marketing, vendor blasts, a
   "thank you" note, an automated bounce, etc.
3. Genuine reports stay in `_inbox/` for the filing SKILL.

Removed ids remain in `.seen.json` (written by the sweep), so a deleted
non-report is never re-downloaded. When in doubt, keep it — the filing/assess
steps can still dismiss it.

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
