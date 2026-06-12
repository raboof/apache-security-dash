---
name: triage-populate-cache
description: >-
  Pull new inbound security reports from the foundation-wide `security@apache.org` Gmail inbox into the local `report-cache/`, ready for assessment.
  Two-step flow inside one skill:
  a deterministic download tool (`populate-cache`, in `tools/populate_cache/`) reads the inbox through the read-only Gmail API, selects thread heads on objective header facts only (thread head, not an automated CVE-process / VINCE / svn notification), and writes one `report.md` bundle per message straight into its dated, per-PMC home `report-cache/<date>/<pmc>/<message-id-slug>/` (tier-1 PMC routing from a `security@<pmc>` recipient) or `report-cache/<date>/_unsorted/<message-id-slug>/`.
  Then the agent (as part of THIS skill, with a small Haiku subagent doing the read) gives every downloaded thread head a disposition:
  a genuine report is filed under `<date>/<pmc>/<keywords>/` via `file.py <id> --keywords "..."`;
  a specialized-PMC report is filed the same way with no `wf` (it is in the project's hands; the downstream skill tracks it);
  a "Currently open security reports" digest is filed under `<date>/<pmc>/digest/` and tagged with every report it lists via `--digest`;
  a non-report (spam / phishing / marketing / bounce) is stamped `--spam` and kept in place as a tombstone.
  Nothing is deleted, so the tool's Message-ID dedup never re-downloads a triaged message;
  once the team archives a report out of the inbox, the next run moves its bundle into `report-cache/handled/`.
  The tag keywords are short single words ordered most-specific to most-generic, with the hyphen-joined slug capped at 60 chars.
  Message bytes never enter the model's context during the download - only a compact funnel + table is printed.
  This SKILL is also the canonical reference for the `report-cache/` layout that downstream drafting and status SKILLs reuse.
  Use whenever the Security team says "pull new security reports", "populate the cache", "sweep the inbox", "file the inbox", "label report X", or to refresh the cache before a triage session.
  It downloads and labels;
  it does not draft, assess against the threat model, or send.
---

# triage-populate-cache SKILL

The **populate** phase of the report-triage pipeline.
It answers one question:
"what genuine new vulnerability reports have arrived on `security@apache.org` that the Security team still needs to triage?",
and puts a local copy of each in its canonical home on disk.
Drafting replies or forwards and reporting status are **separate downstream SKILLs** that operate on the cache this one fills.

The skill has two halves:

1. **Download** - the `populate-cache` tool reads the Gmail inbox and writes one `report.md` bundle per new thread head.
   Deterministic, header-based selection only; no message bytes reach the model.
2. **Label** - the agent reads each downloaded bundle (delegating the read to a Haiku subagent) and gives it a disposition with `file.py`:
   file a real report, mark a non-report as spam, or label-without-assessing a specialized-PMC report.

## When to invoke

- "Pull / sweep new security reports", "populate the report cache", "what came in on `security@`", "refresh the cache before triage".
- "File the inbox", "label report X", "sort the spool", or right after a download to process what landed.

This SKILL never drafts, never sends, and never talks to anything outside the Gmail inbox (read-only) and the local `report-cache/` (write).

## Prerequisites: authentication

The download reads the inbox through the **read-only Gmail API** (`gmail.readonly` scope: list + read, never modify, move or delete).
OAuth2 credentials are read from the environment;
a local `.env` in the repo root is loaded automatically:

| Variable | Purpose |
|---|---|
| `GMAIL_IMAP_OAUTH_CLIENT_ID` | OAuth2 client id |
| `GMAIL_IMAP_OAUTH_CLIENT_SECRET` | OAuth2 client secret |
| `GMAIL_IMAP_OAUTH_REFRESH_TOKEN` | OAuth2 refresh token (must carry `gmail.readonly`) |

The mailbox is whichever account the refresh token belongs to (the Gmail API `me` user);
no separate mailbox address is needed.
`google-auth` refreshes the access token on the first request, so an expired access token is not an error;
a missing/invalid refresh token or scope is.

## Phase 1: download

```bash
# Ongoing: pull every new thread head not already in the cache
uv run --project tools/populate_cache populate-cache

# Narrow the scan to a recent window (faster on a cold cache):
uv run --project tools/populate_cache populate-cache --query newer_than:30d

# Preview without writing anything:
uv run --project tools/populate_cache populate-cache --dry-run
```

Useful flags:

| Flag | Effect |
|------|--------|
| `--cache-dir` | Cache root to write into (default: repo `report-cache/`) |
| `--label` | Gmail label to sweep (default `INBOX`) |
| `--query` | Gmail search to narrow the scan, e.g. `newer_than:30d` |
| `--limit N` | Stop after N new downloads (handy for a quick look) |
| `--dry-run` | Select + report, write nothing |
| `--no-reconcile` | Skip moving handled (left-the-inbox) bundles to `handled/` |

Only the funnel + a one-line-per-report table reach the model.
To read a report, open its `report.md` from the cache.

### How the download decides what to write

Selection is by objective header facts only, no content heuristics.
The tool fetches just the metadata headers for every inbox message, keeps the **thread heads**, drops automated notifications and anything already in the cache, then fetches the full RFC822 body only for the survivors.
The funnel, printed each run, is:

- **reply** - not a thread head.
  A message is a head when it is the Gmail thread root (`id == threadId`) **or** has no `In-Reply-To` header (the second rule keeps a fresh mail that Gmail merged into an old thread by subject, e.g. a recurring `Currently open security reports for <pmc>` digest).
  Replies belong to an already-ingested thread and are tracked by their shared label, not as separate bundles.
  The team's own `Currently open security reports ...` digest is deliberately **not** skipped:
  it is downloaded like any head and given the `digest` disposition in Phase 2 (it tells us which reports a PMC still considers open).
- **cve-process** - CVE-process mail injected by `security-vm-he-fi.apache.org` (per the `Received` chain): CVE reservations / status churn, not a fresh report.
- **vince** - CERT/CC VINCE notifications (`From: cert+donotreply@cert.org`).
- **svn-commit** - SVN commit mail (`Subject:` starts `svn commit: r`).
- **already-seen** - the RFC `Message-ID` is already a bundle in the cache (dedup); never re-downloaded.
  **This is why nothing is deleted in Phase 2** (see below).
- **new** - downloaded into its dated home.

Spam is handled by Gmail's own filtering upstream, so there is no quarantine step.
Whether a *kept* message is a genuine, in-scope report is decided in Phase 2 by reading the text.

### Reconcile: handled reports move to `handled/`

A report stays in the inbox until the team archives it, so a cached bundle whose message is **no longer in the inbox** has been handled.
On a full inbox scan (the default; not when `--query` or a non-`INBOX` `--label` narrows it) the download moves such bundles into `report-cache/handled/`, keeping their `<date>/<pmc>/<leaf>` path.
They stay inside the cache, so the Message-ID dedup still sees them (never re-downloaded) and the active triage queue stops showing what is already done.
Pass `--no-reconcile` to skip the sweep, `--dry-run` to preview it.
This is why a bundle still sitting in the cache outside `handled/` is one that is still open in the inbox and may need triage.

### PMC routing (tier-1 only)

The PMC is taken from the **address-domain** signal only:
a `security@<pmc>.apache.org` address among the `To`/`Cc` recipients, validated against the authoritative Whimsy committee-info slug set.
This is the strong signal;
weaker prose-token and product-name guesses are deliberately not applied at download time, so the tool never misfiles into the canonical tree on a weak signal.
Anything without an address-domain hit goes to `<date>/_unsorted/`, where Phase 2 (which has the body in hand) resolves the PMC.
If Whimsy is unreachable the slug set is empty and every report routes to `_unsorted` (the tool prints a degraded-routing notice).

A `security@<pmc>` recipient also records the routing in the front-matter `pmc` / `pmc_candidates` fields.

## Phase 2: label each downloaded head

The download is intentionally coarse and **never deletes**:
every new thread head lands in the cache with `status: downloaded`, and the tool's dedup keys on the Message-ID by scanning the existing bundles.
**Phase 2 gives each downloaded head a disposition, and the bundle stays on disk** (even a non-report) so its Message-ID is always found and it is never downloaded again.
Deciding the disposition is this skill's job, done by the agent reading the text - not by code, and not deferred to a downstream skill.

Work the cache one bundle at a time.
For each bundle still at `status: downloaded` (find them with the `--dry-run` table, or `grep -rl 'status: downloaded' report-cache/`):

1. **Read** the bundle.
   Delegate the read to a **Haiku subagent** (cheap, and keeps raw message bytes out of the main context):
   give it the bundle's `report.md`, any file under `attachments/`, and [`tag-vocabulary.yaml`](tag-vocabulary.yaml), and have it return a compact proposal (schema below).
   Run one subagent per bundle; they are independent and can fan out in parallel.
2. **Decide the disposition** from the proposal.
   The dispositions are an open set we extend as new cases appear on the inbox; the ones in place today:
   - **report** - a genuine vulnerability report for a project we triage (even a weak, duplicate, or non-issue one: those are still real reports the team answers, so they are filed and the content disposition is handled downstream).
     File it.
   - **specialized-pmc** - addressed to a project that runs its own security team (e.g. `security@tomcat.apache.org`).
     **We do not assess it** - it is in the PMC's hands.
     File it like a normal report (`--keywords`, **no** `wf` - a report in a PMC's hands has none); the downstream `triage-assess` skill recognises the specialized PMC (from `project-coordinates.json`) and only tracks it.
   - **digest** - a `Currently open security reports for <pmc>` summary the team itself sends.
     Not a report to assess: it lists the PMC's still-open reports, so tag it with **every one of those reports' tags** (see below) and file it with `--digest`.
   - **non-issue (standing label)** - a known non-issue class, most often a request about a CVE in an Apache project the sender merely **depends on** (a fix/release-info inquiry, or a transitive-CVE report).
     Not a vulnerability we assess: file it under the standing non-issue label with `--non-issue aaa-dependencies --pmc <pmc>` (tag `zzz-non-issue/<pmc>/aaa-dependencies`; see below).
     A report we dismiss case-by-case is different: file it normally as `<pmc>/<date> <keywords>` with `--wf non-issue-feedback`, reply to the reporter, then (downstream) it is moved to `zzz-non-issue/<pmc>/<date> <keywords>`.
   - **spam / non-report** - phishing, marketing, a "thank you" note, an automated bounce, a vendor blast.
     Stamp it `--spam`; the bundle is kept in place as a dedup tombstone, not deleted.
3. **Propose**, per bundle:
   **FILE** (PMC + keywords; note if it is specialized-PMC), **DIGEST** (PMC + the covered report tags), **NON-ISSUE** (PMC + the standing label, e.g. `aaa-dependencies`), or **SPAM** (one-line reason).
   Present the proposals as a short list and **get the user's confirmation before running anything** - filing is worth confirming so the keywords are right, and a wrong `--spam` buries a real report.
4. **Execute** the confirmed actions with `file.py` (below).

### The open-reports digest

A `Currently open security reports for <pmc>` mail is the team's own periodic summary of the reports a PMC still has open.
We label it with the tag of every report it lists so it surfaces alongside each of them.
The tags come from the sibling **`email-classification/<pmc>/`** archive, which mirrors the Gmail labels:
each file there is named for a report's tag (e.g. `email-classification/tomcat/2026-06-08 webxml tostring.json`, `email-classification/tomcat/CVE-2026-50229 examples xss.json`).

The digest body lists each still-open report as a bullet - `* <Title> [N days]` followed by a Ponymail thread link (`https://lists.apache.org/thread/<id>`), sometimes with a CVE link - grouped under sections like `# Untriaged` and `# Confirmed`.
The `<Title>` is the report's email subject.
`email-classification/<pmc>/` stores each report's `subj` and `message_id` but **not** the Ponymail thread-id, so the cross-check is **by subject**: match each digest `<Title>` to the tag file whose `subj` is the same report.

Delegate this to a **Haiku subagent** (one per digest), giving it the digest bundle and `email-classification/<pmc>/`, and ask it to return the matched tag list.
When matching a `<Title>` to a `subj`, normalize for:

- the trailing `[N days]` and a leading `Re:`;
- the digest's dropped spaces from line-wrapping (`MCPServer` vs `MCP Server`, `viaHTTP` vs `via HTTP`);
- MIME/UTF-8 encoding in the archive `subj` (`=?UTF-8?...`);
- a `CVE-XXXX: ...` entry, whose tag file usually starts with that CVE id.

Take **every** report the digest lists (all sections).
The tag is `<pmc>/<filename-without-.json>` verbatim - it may carry a `wf ...` marker or be a standing `aaa-*` label (e.g. `dubbo/aaa-non-fwd`).
Verify each tag is a real file under `email-classification/<pmc>/` before filing, and present the list for confirmation.

Then file the digest, passing each tag with a repeated `--tag` (prefix it with the PMC):

   ```bash
   .agents/skills/triage-populate-cache/file.py <id> --digest --pmc tomcat \
       --tag "tomcat/2026-06-08 webxml tostring" \
       --tag "tomcat/CVE-2026-50229 examples xss"
   ```

This files the digest under `<date>/<pmc>/digest/` (`keywords: [digest]`), stamps `handled: true` (terminal - never assessed; a digest has no `wf`, it is not a report waiting for anything), and records the covered tags as the bundle's `tags` (so the digest carries each covered report's label, the same set the sync tool will put on the Gmail message).
If a listed report has no tag file yet (it is itself still in this download batch), label that report first.

### Pre-labelled heads (`tags`)

`tags` is the message's Gmail labels, seeded by the download from whatever was already on the message.
A pre-existing entry does **not** mean it was already triaged:
a message still in the inbox is by definition untriaged (a handled report would have been archived and swept into `handled/`, see below).
Gmail auto-applies some labels by **subject keyword** - most often a public CVE number.
So a follow-up report whose subject names an already-public CVE (e.g. a fix that turned out incomplete) arrives with that CVE's existing `<pmc>/<date> <keywords>` label already in `tags`, even though it is a fresh report that needs full triage.

Treat a pre-existing `tags` entry as a **routing hint**, not a disposition:
it tells you which prior report or CVE this one relates to, so you can reuse its PMC and align the keywords, and (downstream) cross-reference the earlier thread.
Then triage the head normally - decide its disposition and file it like any other; `file.py` keeps the pre-existing labels and adds the assigned one.
A head with no labels yet has `tags: null`.

### Special recipients

A few `To`/`Cc` recipients mean a message is not a fresh report but a **mirror** of one that arrived (or will arrive) by the normal path.
Do not file it as a new report: find the report it mirrors and give the mirror the **same tag**, so both messages carry one Gmail label.

Known special recipients:

- **`airflow-s@noreply.github.com`** (Airflow) - a GitHub notification for the Airflow PMC's private `airflow-s/airflow-s` security-issue repo, where a PMC member re-files each inbound report.
  So this notification mirrors a report the reporter also sent to `security@airflow.apache.org` or `security@apache.org`.
  Find that report by matching the subject - among the still-`downloaded` bundles, the already-filed ones, or anywhere in `email-classification/` (the original is often classified already, in any collection: active, `zzz-non-issue/`, `zzz-resolved/`, even `archive/`).
  Apply **its** tag to the notification, reproducing it with the `file.py` mode that matches the original's collection:
  `--keywords "<kw>" --date <date>` for an active label, or `--non-issue "<date> <kw>" --pmc airflow` for a `zzz-non-issue/...` one.
  If you cannot find the original (the mirror may have arrived first, or the report went elsewhere), flag it rather than invent a tag.

### Deciding PMC + keywords

- **PMC** - confirm the tool-detected `pmc:` if the download set it from a `security@<pmc>` recipient (tier-1);
  otherwise (an `_unsorted` bundle) read the body to determine the project (the subject/body almost always name it, e.g. "Apache Spark").
  Use the PMC slug (`spark`, `httpd`, `commons`, …) and pass it with `--pmc`.
- **Keywords** - short, lowercase, single-word terms capturing the issue.
  Each keyword must match `[a-z0-9_]+`: no `-` inside a keyword (use `_` if you must join two parts, e.g. `file_read`, not `file-read`).
  The directory name is the hyphen-join of the keywords, so the tag's space-separated form roundtrips without ambiguity.
  `file.py` enforces the character set and caps the hyphen-joined slug at 60 chars (long enough for a handful of words, short enough to keep paths and `ls` output legible).
  If `file.py` rejects your keywords, drop the least informative one or shorten it.
- **Keyword order: most specific to most generic.**
  The first keyword is the strongest filter, so similar reports cluster by their tag prefix.
  Concretely:
  1. Most specific PMC subproject / component (from `per_pmc.<pmc>` in [`tag-vocabulary.yaml`](tag-vocabulary.yaml), or a global `component` entry if the project has no subproject for this surface).
  2. The vulnerability class (`vuln_class` in the vocabulary).
  3. Optional further narrowing: a more specific component, a `modifier`, or a CVE-vector keyword.

  Examples: `digester xxe file_read` (commons-digester XXE leading to file read), `tribes deser cluster` (Tomcat Tribes cluster-channel deserialization), `dag operator rce` (Airflow operator-templating RCE via DAG).
  When the report is squarely about a vuln class with no meaningful subproject (e.g. a foundation-wide CVE intake), the vuln class can lead: `deser jdbc h2`.

### Pick keywords from the established vocabulary

Before inventing a new keyword, consult [`tag-vocabulary.yaml`](tag-vocabulary.yaml) and **prefer an existing canonical keyword over a synonym**.
New reports clustering under the same tag as historical ones is the whole point:
the cache and the sibling `email-classification/` archive both become searchable by tag.

The file has three sections:

- `global.vuln_class` - the lead keyword for almost every report (`rce`, `dos`, `deser`, `xss`, `ssrf`, `traversal`, `sqli`, `xxe`, `bypass`, `injection`, …).
- `global.component` - what the vuln hits (`file`, `path`, `session`, `header`, `jdbc`, `jwt`, `xml`, `yaml`, `regex`, `template`, …).
- `global.modifier` - optional third keyword to narrow (`read`, `write`, `stored`, `reflected`, `pre_auth`, `default`, …).
- `per_pmc.<pmc>` - subprojects / components specific to a PMC (e.g. commons `compress`, `jexl`, `fileupload`; airflow `dag`, `operator`; tomcat `tribes`, `hpack`; logging `log4j`, `log4j2`).

Rules of thumb:

1. **First keyword** is almost always a `vuln_class` entry.
   If the report names a deserialization sink, use `deser` (the canonical form), not `deserialization` or `deserialize`.
2. **Second keyword** is a `component` entry or, if the PMC has a list in `per_pmc`, an entry from there (subprojects sort the cache better than generic component words).
3. **Third keyword** (often omitted) is a `modifier` or a narrower component pointer.
4. If the report does not fit any existing keyword, a new one is fine -
   just make sure the form matches the existing style (single lowercase word, `_` not `-` for compounds).
   Mention the new keyword in your filing proposal so the user can decide whether it belongs in the vocabulary file.

### The Haiku labelling subagent

Spawn one Haiku subagent per `status: downloaded` bundle.
Keep raw bytes out of the main context: the subagent reads the files, the main agent sees only the small proposal.
Give the subagent the bundle path, tell it to read `report.md` (and skim `attachments/`) and `tag-vocabulary.yaml`, and to return **only** this JSON:

```json
{
  "is_report": true,
  "disposition": "report",          // "report" | "specialized-pmc" | "digest" | "non-issue" | "spam"
  "pmc": "spark",                    // slug; echo the front-matter pmc if set, else infer
  "keywords": ["ssrf", "rest", "api"], // most-specific -> most-generic, [a-z0-9_], <=3
  "label": null,                     // for "non-issue": the standing label leaf, e.g. "aaa-dependencies"
  "reason": "SSRF in the REST API admin proxy"  // one line; for spam, why it is not a report
}
```

For a **digest** the subagent returns `disposition: "digest"`, the `pmc` it is "for", and the listed reports (subject / CVE / reporter) under `reason` so the main agent can resolve each to its `email-classification/<pmc>/` tag;
it does not invent keywords for a digest.
For a **non-issue** (e.g. a CVE-in-a-dependency inquiry) it returns `disposition: "non-issue"`, the `pmc`, and `label` set to the standing leaf (`aaa-dependencies`).

The subagent decides nothing irreversible;
the main agent presents the proposals, gets the user's confirmation, and runs `file.py`.
Treat the subagent's keywords as a draft - reconcile them against the vocabulary before filing.

### Helper commands

```bash
# File a genuine report (PMC auto-filled by the download for tier-1 -> omit --pmc):
.agents/skills/triage-populate-cache/file.py <id> \
    [--pmc <slug>] --keywords "<up to 3 single words>"

# A specialized-PMC report is filed like a normal report (no wf - it is the PMC's);
# the downstream skill recognises the specialized PMC and only tracks it.

# Record what a report is waiting for with --wf (e.g. reporter, cve-allocation):
.agents/skills/triage-populate-cache/file.py <id> \
    --keywords "<words>" --wf reporter

# Label an open-reports digest with the tag of every report it lists:
.agents/skills/triage-populate-cache/file.py <id> --digest --pmc <slug> \
    --tag "<pmc>/<date> <keywords>" --tag "<pmc>/CVE-... <keywords>"

# File a known non-issue (e.g. a CVE-in-a-dependency inquiry) under its standing label:
.agents/skills/triage-populate-cache/file.py <id> --non-issue aaa-dependencies --pmc <slug>

# Mark a non-report as spam (kept in place as a dedup tombstone, not deleted):
.agents/skills/triage-populate-cache/file.py <id> --spam \
    --reason "<why it is not a report>"
```

`<id>` is the bundle's **message-id-slug directory name** or any unique prefix (the truncated id the download printed works), or the RFC Message-ID.
Only bundles still at `status: downloaded` are matched, so a re-run never re-files an already-triaged report.
Add `--dry-run` to preview any action.

- **File** composes the label `<pmc>/<date> <keywords>` (the `cve` field replaces the date once allocated; `--wf <state>` appends ` wf <state>`) and adds it to `tags`, keeping any pre-existing Gmail labels. It renames the leaf from the message-id slug to the keyword slug, moves an `_unsorted` bundle under its `<pmc>/`, sets `collection: null` (active) and `status: filed`.
  `handled` stays `false` until the report is actioned downstream.
  `--wf <state>` records what the report is waiting for (see below); omit it for a report in a PMC's hands.
- **Digest** files the bundle under `<date>/<pmc>/digest/` (`keywords: [digest]`), stamps `handled: true` (terminal, no `wf`), and records the covered report tags (each `--tag`) as the bundle's `tags`.
  It is a status summary, never assessed.
- **Non-issue** moves the bundle to `zzz-non-issue/<pmc>/<label>/<slug>/` and adds the label `zzz-non-issue/<pmc>/<label>` to `tags`, with `status: filed`.
  The `<label>` leaf is verbatim (e.g. `aaa-dependencies`); not all standing labels are `aaa-` prefixed, so `--non-issue` takes the whole leaf.
- **Spam** stamps `status: spam` and a `disposition` reason in place and sets `handled: true`.
  The bundle is **kept** (its Message-ID stays in the cache), so the download never re-fetches it;
  nothing is written to a separate ledger.

Work one report at a time so each gets the right keywords and the right disposition.
After a pass, no bundle is left at `status: downloaded`.

## report-cache structure (canonical reference)

`report-cache/` lives at the repo root and is **gitignored** (see `.gitignore`):
cached report content, attachments, and drafts are never committed.
Downstream SKILLs MUST follow this layout.

```text
report-cache/
  index.json                        # WRITTEN BY file.py: Message-ID -> {path, pmc, tags, status, ...}
                                    #   so a filed report stays findable by Message-ID after its leaf
                                    #   is renamed. `file.py --reindex` rebuilds it from the cache.
  <date>/<pmc>/<message-id-slug>/   # WRITTEN BY populate-cache: a downloaded,
      report.md                     #   tier-1-routed report awaiting a label
      raw.eml                       #   verbatim RFC822 message (safety net); moves with the bundle
      attachments/                  #   decoded attachment bytes (md / pdf / zip / py / ...)
          <filename>
  <date>/_unsorted/<message-id-slug>/  # WRITTEN BY populate-cache: no PMC in the headers
      report.md                        #   Phase 2 resolves the PMC from the body
      attachments/

  <date>/<pmc>/<keywords>/          # WRITTEN BY THIS SKILL (file.py): a filed report
      report.md                     #   leaf renamed from the message-id slug; tag/keywords/status set
      attachments/
      draft-forward.md              # WRITTEN BY THE DRAFTING SKILL: forward to the PMC
      draft-reply.md                #   ack / push-back to the reporter

  <date>/<pmc>/digest/             # WRITTEN BY THIS SKILL (file.py --digest): an open-reports
      report.md                    #   summary; keywords [digest], its tags are the covered reports' tags
      attachments/

  zzz-non-issue/<pmc>/<label>/<slug>/  # WRITTEN BY THIS SKILL (file.py --non-issue): a known
      report.md                        #   non-issue, e.g. <label>=aaa-dependencies for a CVE-in-a-
      attachments/                     #   dependency inquiry; tag zzz-non-issue/<pmc>/<label>

  handled/<date>/<pmc>/<leaf>/     # MOVED HERE BY populate-cache: a bundle whose message left
      report.md                    #   the inbox (archived = handled); kept for dedup, off the queue
      attachments/
```

Every bundle also keeps `raw.eml`, the verbatim RFC822 message the download saved as a safety net; it travels with the bundle into the filed / digest / non-issue / `handled/` locations (only the top-level `<filename>` lines and `draft-*.md` are omitted from the other entries above for brevity).

`index.json` maps each Message-ID to its bundle's current `path` (plus `pmc` / `tags` / `status` / `collection`).
`file.py` upserts the entry on every disposition, so once filing renames the leaf from the message-id slug to the keyword slug the report stays findable by Message-ID - look it up rather than scanning every `report.md`.
`file.py --reindex` rebuilds the whole index from the cache.

A spam bundle stays where it was downloaded (usually `<date>/_unsorted/...`) with `status: spam`;
it is a tombstone for dedup, not part of the triage queue.
A bundle under `handled/` has left the inbox (the team archived it);
it is kept only so the dedup never re-downloads it.

- `<message-id-slug>` is the sanitized RFC Message-ID (`[A-Za-z0-9._-]`), the provisional leaf the download writes.
- `<date>` is `yyyy-mm-dd` (the report's date).
- `<pmc>` is the PMC slug (e.g. `tomcat`).
- `<keywords>` is the hyphen-joined keyword set from the report tag (single words, ordered most-specific to most-generic, slug capped at 60 chars), the leaf after filing.

A report's own triage **label** (one entry in `tags`) is composed of these parts:

```text
[archive/] [<collection>/] <pmc> / <date-or-CVE> <space-separated keywords> [wf <status>]
```

- **`<collection>`** - the prefix: omitted = active, `zzz-non-issue`, or `zzz-resolved` (no longer actionable). Held in the `collection` field (null = active).
- **`archive/`** - an extra prefix for a label evicted from Gmail (its label limit) but kept under `email-classification/archive/`. Not a separate field; only ever present in `tags`.
- **`<date-or-CVE>`** - the report's day (`yyyy-mm-dd`) or, once allocated, `CVE-YYYY-NNNNN` (the `cve` field).
- **`<keywords>`** - the `keywords` field, space-separated (for a standing non-issue this is a fixed leaf like `aaa-dependencies`).
- **`wf <status>`** - the `wf` field, appended when set.

So the bundle's `collection` / `cve` / `keywords` / `wf` fields are the decomposed parts; `tags` carries the composed string(s). An active report maps to the canonical path `<date>/<pmc>/<keywords>/` (the digest's keyword is `digest`); a non-issue to `zzz-non-issue/<pmc>/<label>/`.

The **`wf`** field is short for **"waiting for"** - the state a report is parked in while the team waits on something.
A report in a PMC's hands (assessed and forwarded, or owned by a specialized PMC) has **no** `wf`.
The common values, seen in the `email-classification` archive (where the `wf` is appended to the label filename, e.g. `… wf reporter`):

- `reporter` - waiting for the reporter to respond;
- `cve-allocation` - waiting for a CVE to be allocated;
- `non-issue-feedback` - waiting to send the reporter the "not an issue" feedback;
- `non-issue-docs` - a documented, by-design behaviour (non-issue);
- `disclosure` - waiting for coordinated disclosure;
- a fix-release **version** (e.g. `2.0.1`, `1.14.1`) - waiting for that release;
- and a long tail (`reject`, `public-followup`, `patch`, `announcement`, …).

### `report.md` front-matter schema

`report.md` is the bundle's single file:
YAML front-matter (Jekyll-style, delimited by `---` lines), then the report body (HTML parts converted to Markdown).

```yaml
---
# Provenance (written by populate-cache, treated as read-only downstream)
subject:        # report subject
reporter:       # From: email address
reporter_name:  # From: display name
message_id:     # RFC Message-ID header (the stable dedup key)
ponymail_id:    # null (Gmail-sourced, no Ponymail archive id)
archive_url:    # null
list:           # List-Id, formatted <security.apache.org>, or null
to:             # To: header (recipient routing; null if absent)
cc:             # Cc: header (null if absent)
date:           # original message date, "yyyy/mm/dd hh:mm:ss"
references:     # References header, or null (null == thread head)
attachments:    # list of {filename, content_type, size, hash}
fetched_at:     # ISO-8601 UTC download time

# Routing hints (written by populate-cache from To/Cc, tier-1 only)
pmc:            # PMC slug when a security@<pmc> recipient named it, else null
pmc_candidates: # all PMC slugs seen in security@<pmc> recipients, or null

# Triage state (set by file.py)
tags:           # the message's Gmail labels, as a list (or null): the full COMPOSED
                #   labels. Seeded by populate-cache with the labels already on the
                #   message, then extended by file.py with the assigned label. A later
                #   tool reconciles `tags` against Gmail. The fields below are the
                #   decomposed parts of the bundle's own label.
collection:     # the label PREFIX: null = active, "zzz-non-issue", "zzz-resolved"
cve:            # the allocated CVE (CVE-YYYY-NNNNN); when set it is the label's key
                #   instead of the date. null until a CVE is allocated (downstream).
keywords:       # list of up to 3 single-word keywords, or null until filed
wf:             # "waiting for" state (reporter, cve-allocation, non-issue-feedback,
                #   non-issue-docs, disclosure, a fix-release version, ...); null when
                #   the report is in a PMC's hands. Also appended to the composed tag.
disposition:    # spam reason, set by `file.py --spam`; absent otherwise
handled:        # false until the team has actioned the report
status:         # "downloaded" -> "filed" (file.py / --digest) | "spam" (--spam);
                #   downstream skills advance a filed report further
---

<report body - the message body as Markdown, verbatim>
```

Downstream SKILLs look up a report by `message_id`, treat the provenance block as read-only, and may add their own fields (e.g. `decision`, `triager`, `drafted_at`) to the front-matter.

## Why a download tool, not the MCP

Reading messages through an MCP tool returns the text as tool-result content, so the model tokenizes every byte.
This SKILL instead uses the read-only Gmail API directly from `tools/populate_cache` and writes bodies + attachments to disk;
only the summary table is tokenized.
The labelling read in Phase 2 is likewise delegated to a Haiku subagent so raw bytes stay out of the main context.
The tool lives in `tools/populate_cache/` (its own `README.md` documents the Gmail API access, scopes, and skip rules);
the message-parsing primitives there are derived from the `inbox_manager` tool.

## Authorization and privacy

`security@apache.org` is foundation-private and can carry PII.
Running this SKILL is an authorized, local-processing activity by a Security-team member who is entitled to read the list.
The download authenticates with the read-only `gmail.readonly` scope, which cannot modify, move or delete mail.
Report content stays in the gitignored `report-cache/` and is never committed.
Keep the working copy on a machine appropriate for the content.

## Handoff

After a download + label pass, no bundle is left at `status: downloaded`:
real reports sit at `<date>/<pmc>/<keywords>/` (`status: filed`), specialized-PMC reports are filed the same way (no `wf`), open-reports digests under `<pmc>/digest/` (`keywords: [digest]`), non-issues under `zzz-non-issue/<pmc>/<label>/`, and non-reports are spam tombstones.
The **drafting SKILL** then assesses each filed report against the PMC's threat model and adds `draft-forward.md` / `draft-reply.md`, skipping digests (`keywords: [digest]`) and reports for a specialized PMC (which it recognises from `project-coordinates.json`).
A **status SKILL** reports handled/unhandled counts across the cache.
Both rely on the layout and front-matter schema documented above, and both ignore the `handled/` subtree (reports the team has since archived out of the inbox).
