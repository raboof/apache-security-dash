---
name: triage-populate-cache
description: >-
  Pull new inbound security reports from the foundation-wide `security@apache.org` Gmail inbox into the local `report-cache/`, ready for assessment.
  Two-step flow inside one skill:
  a deterministic download tool (`populate-cache`, in `tools/populate_cache/`) reads the inbox through the read-only Gmail API, selects thread heads on objective header facts only (thread head, not an automated CVE-process / VINCE / svn notification), and records each new one at `status: downloaded`.
  Then the agent (as part of THIS skill, with a lightweight-model subagent doing the read) sorts every downloaded message into a category and records it through the `report-cache` CLI:
  a genuine report is classified with its PMC + keywords (`report-cache classify <id> --pmc <pmc> --keywords "..."`), plus `--track-only` when it already reached the PMC's own security team (nothing for us to send);
  a "Currently open security reports" digest gets `set --disposition track` plus one `--add-label` per report it lists;
  a known non-issue class gets its standing `zzz-non-issue/<pmc>/<label>` label via `set --add-label`;
  a mirror of a report that arrived by another path gets that report's label;
  a non-report (spam / phishing / marketing / bounce) gets `set --disposition skip`.
  Dedup keys on the RFC `Message-ID`, so a triaged message is never re-downloaded;
  once the team archives a report out of the inbox, the next run deletes its bundle and its triage record.
  The keywords are short single words ordered where-then-what-then-which (subproject or component, vulnerability class, then whatever makes the tag unique), with the hyphen-joined slug capped at 60 chars.
  Message bytes never enter the model's context during the download - only a compact funnel + table is printed.
  Bundle storage and the index belong to the `report-cache` tool: this SKILL goes through its CLI and never reads or writes the layout directly.
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

1. **Download**: the `populate-cache` tool reads the Gmail inbox and writes one report bundle per new thread head.
   Deterministic, header-based selection only; no message bytes reach the model.
2. **Classify**: the agent reads each downloaded bundle (delegating the read to a
   [lightweight, low-latency, cost-efficient](#the-lightweight-model) subagent) and:
   * Validates or determines the PMC,
   * Determines the keywords for the report,
   * Determines the reporter's preferred name.
   * Advances the status to `classified`.

## When to invoke

- "Pull / sweep new security reports", "populate the report cache", "what came in on `security@`", "refresh the cache before triage".
- "File the inbox", "label report X", "sort the spool", or right after a download to process what landed.

This SKILL never drafts, never sends, and never talks to anything outside the Gmail inbox (read-only) and the local `report-cache/` (write).

## Prerequisites: authentication

The download reads the inbox through the **read-only Gmail API** (`gmail.readonly` scope: list + read, never modify, move or delete).
OAuth2 credentials are read from the environment;
a local `.env` in the repo root is loaded automatically:

| Variable                             | Purpose                                            |
|--------------------------------------|----------------------------------------------------|
| `GMAIL_READONLY_OAUTH_CLIENT_ID`     | OAuth2 client id                                   |
| `GMAIL_READONLY_OAUTH_CLIENT_SECRET` | OAuth2 client secret                               |
| `GMAIL_READONLY_OAUTH_REFRESH_TOKEN` | OAuth2 refresh token (must carry `gmail.readonly`) |

These are the **read-only** Gmail API token, named to stay distinct from `inbox_manager`'s **read/write** IMAP token (`GMAIL_READWRITE_OAUTH_*`), so both can share one `.env`.

The mailbox is whichever account the refresh token belongs to (the Gmail API `me` user);
no separate mailbox address is needed.
`google-auth` refreshes the access token on the first request, so an expired access token is not an error;
a missing/invalid refresh token or scope is.

## Phase 1: download

In this phase incoming messages are downloaded to the cache,
using one of the commands below:

```bash
# Ongoing: pull every new thread head not already in the cache
uv run --project tools/populate_cache populate-cache

# Narrow the scan to a recent window (faster on a cold cache):
uv run --project tools/populate_cache populate-cache --query newer_than:30d

# Preview without writing anything:
uv run --project tools/populate_cache populate-cache --dry-run
```

Useful flags:

| Flag             | Effect                                                     |
|------------------|------------------------------------------------------------|
| `--cache-dir`    | Cache root to write into (default: repo `report-cache/`)   |
| `--query`        | Gmail search to narrow the scan, e.g. `newer_than:30d`     |
| `--limit N`      | Stop after N new downloads (handy for a quick look)        |
| `--dry-run`      | Select + report, write nothing                             |
| `--no-delete`    | Keep bundles whose message has left the inbox              |

On a full scan (no `--query`) the download also deletes the bundles whose message has left the inbox:
the team archives a report once it is handled, so the bundle and its triage record go with it.

Only the funnel and a one-line-per-report table reach the model.
To read a report, use `report-cache show <id>` (below); never open the cache files directly.

## Phase 2: classify each downloaded message

The download selects on headers alone, so it is deliberately coarse:
what it hands over is a pile of *messages*, only some of which are new vulnerability reports.
This phase reads each one and decides what kind of message it is,
then records that through the `report-cache` CLI.

List what is waiting:

```bash
uv run --project tools/report_cache report-cache list --status downloaded
```

Work one message at a time.
For each one the listing shows at `status: downloaded`:

1. **Read** it.
   Delegate the read to a **[lightweight-model](#the-lightweight-model) subagent** (it keeps raw message bytes out of the main context):
   give it the message's `<id>` and have it return a compact proposal
   ([schema](#the-labelling-subagent)).
   Run one subagent per message; they are independent and can fan out in parallel.
2. **Settle the category** from the proposal (below).
3. **Propose**, per message: its category, its PMC, and the values that category needs.
   Reports need keywords and reporter name,
   the remaining categories need labels.
   Present the proposals as a short list and **get the user's confirmation before running anything**:
   the keywords are worth a second pair of eyes, and a wrong `skip` buries a real report.
4. **Execute** the confirmed actions with the `report-cache` CLI ([below](#tools-available)).

### The categories

These are the kinds of message the inbox actually delivers.
They are an open set - we extend it as new cases appear:

| Category      | What it is                                                       | What it needs               |
|---------------|------------------------------------------------------------------|-----------------------------|
| **report**    | a genuine vulnerability report for a project                     | keywords + reporter name    |
| **digest**    | the team's own `Currently open security reports for <pmc>` mail  | the covered reports' labels |
| **non-issue** | a known standing class, e.g. a CVE-in-a-dependency inquiry       | the standing label          |
| **mirror**    | a notification duplicating a report that arrived by another path | the original's label        |
| **other**     | phishing, marketing, a "thank you", a bounce, a vendor blast     | nothing                     |

- **report**: even a weak, duplicate, or ultimately-invalid one is still a real report the team answers,
  so it is a report here; whether it has merit is decided downstream, not now.
  Classify it with its PMC and keywords, and add `--track-only` when it already reached the PMC
  (see [Deciding PMC + keywords](#deciding-pmc-track-only-and-keywords)).

  ```bash
  report-cache classify <id> --pmc <pmc> --keywords "<kw>" --reporter-name "<name>"
  ```

- **digest**: not a report to assess.
  It summarizes the PMC's still-open reports.
  Label it with **every one of those reports' labels** ([below](#the-open-reports-digest)) and record that we owe nothing:

  ```bash
  report-cache set <id> --disposition track --add-label "<label>" --add-label "<label>"
  ```

- **non-issue**: most often a request about a CVE in a project the sender merely **depends on**
  (a fix/release-info inquiry, or a transitive-CVE report).
  Not a vulnerability we assess: give it the standing label **verbatim**,
  spelled as in `email-classification/<pmc>/` (the standing `aaa-*` labels are hyphenated),
  so it joins the existing class instead of minting a near-duplicate:

  ```bash
  report-cache set <id> --add-label "zzz-non-issue/<pmc>/aaa-dependencies"
  ```

  A report we dismiss case-by-case is **not** this: that is a **report**, classified normally with
  `--waiting-for non-issue-feedback`, replied to, and moved to the `zzz-non-issue` collection downstream.

- **mirror**: a copy of a report that also arrived by the normal path ([below](#special-recipients)).
  Do not classify it as a new report: give it the original's label verbatim, and record that we owe nothing:

  ```bash
  report-cache set <id> --disposition track --add-label "<the original's label>"
  ```

- **other**: nothing for the pipeline to do:

  ```bash
  report-cache set <id> --disposition skip
  ```

  The bundle stays where it is, out of the skill's scope, until the team archives the message.

Note the two vocabularies do not line up, and should not be confused:
a **category** is what kind of message arrived (above),
while `--disposition` is `report-cache`'s record of what the team owes on it
(`track` - nothing to send; `skip` - out of scope; `forward` / `decline` - decided downstream).

### Tools available

`<id>` is the RFC `Message-ID` (a unique prefix works) or the bundle's leaf directory name;
`list` prints one you can pass straight back.

```bash
# Find reports with a given status
uv run --project tools/report_cache report-cache list --status <status>

# Read a report: metadata + body + its attachment / artifact listing
uv run --project tools/report_cache report-cache show <id>

# Read an attachment, rendered to text (text / markdown / html / pdf)
uv run --project tools/report_cache report-cache get-attachment <id> <name>

# Classify a report: move it under <pmc>/<date>-<keywords>, add the label, set status classified
uv run --project tools/report_cache report-cache classify <id> --pmc <pmc> --keywords "<kw>"

# Classify a report that is already in its PMC's hands: status assessed + disposition track
uv run --project tools/report_cache report-cache classify <id> --pmc <pmc> --keywords "<kw>" --track-only

# Record a disposition without moving the bundle (skip = not a report; track = nothing to send)
uv run --project tools/report_cache report-cache set <id> --disposition skip

# Add labels verbatim (repeat --add-label; used for a digest's covered reports)
uv run --project tools/report_cache report-cache set <id> --add-label "<label1>" --add-label "<label2>"

# Label a standing non-issue class (a label, not a directory) - spelled as in the archive
uv run --project tools/report_cache report-cache set <id> \
    --add-label "zzz-non-issue/<pmc>/aaa-dependencies"
```

Labels are recorded exactly as passed, so a standing `aaa-*` label goes through `--add-label` verbatim.
Do not reach for `--collection`/`--keywords` to build one:
keywords are validated as `[a-z0-9_]+`, so they cannot spell the hyphenated archive labels
and would mint a near-duplicate class.

### The open-reports digest

A `Currently open security reports for <pmc>` mail is the team's own periodic summary of the reports a PMC still has open.
We label it with the tag of every report it lists so it surfaces alongside each of them.
The tags come from the sibling **`email-classification/<pmc>/`** archive, which mirrors the Gmail labels:
each file there is named for a report's tag (e.g. `email-classification/tomcat/2026-06-08 webxml tostring.json`, `email-classification/tomcat/CVE-2026-50229 examples xss.json`).

The digest body lists each still-open report as a bullet - `* <Title> [N days]` followed by a Ponymail thread link (`https://lists.apache.org/thread/<id>`), sometimes with a CVE link - grouped under sections like `# Untriaged` and `# Confirmed`.
The `<Title>` is the report's email subject.
`email-classification/<pmc>/` stores each report's `subj` and `message_id` but **not** the Ponymail thread-id, so the cross-check is **by subject**: match each digest `<Title>` to the tag file whose `subj` is the same report.

Delegate this to a **[lightweight-model](#the-lightweight-model) subagent** (one per digest), giving it the digest's `<id>` (to read with `report-cache show <id>`) and `email-classification/<pmc>/`, and ask it to return the matched tag list.
When matching a `<Title>` to a `subj`, normalize for:

- the trailing `[N days]` and a leading `Re:`;
- the digest's dropped spaces from line-wrapping (`MCPServer` vs `MCP Server`, `viaHTTP` vs `via HTTP`);
- MIME/UTF-8 encoding in the archive `subj` (`=?UTF-8?...`);
- a `CVE-XXXX: ...` entry, whose tag file usually starts with that CVE id.

Take **every** report the digest lists (all sections).
The tag is `<pmc>/<filename-without-.json>` verbatim - it may carry a `wf ...` marker or be a standing `aaa-*` label (e.g. `dubbo/aaa-non-fwd`).
Verify each tag is a real file under `email-classification/<pmc>/` before labelling, and present the list for confirmation.

Then label the digest, passing each tag with a repeated `--add-label` (prefix it with the PMC),
and record that there is nothing for us to send:

   ```bash
   uv run --project tools/report_cache report-cache set <id> --disposition track \
       --add-label "tomcat/2026-06-08 webxml tostring" \
       --add-label "tomcat/CVE-2026-50229 examples xss"
   ```

Labels are stored exactly as given, so pass each tag verbatim.
`--disposition track` is what marks the digest as needing nothing from us:
it is the team's own summary, never a report to assess.
The digest's Gmail message must carry each of those labels so it surfaces alongside every report it lists;
the credentialed `inbox_manager` tool does that attach-and-archive step (see "Applying the cache labels to Gmail" below).
If a listed report has no tag file yet (it is itself still in this download batch), label that report first.

### Pre-labelled heads

A report's `labels` are the message's Gmail labels, seeded by the download from whatever was already on the message;
`show` lists them.
A pre-existing entry does **not** mean it was already triaged:
a message still in the inbox is by definition untriaged (a handled report would have been archived, and its bundle deleted with it).
Gmail auto-applies some labels by **subject keyword**: most often a public CVE number.
So a follow-up report whose subject names an already-public CVE (e.g., a fix that turned out incomplete)
arrives with that CVE's existing `zzz-resolved/<pmc>/<cve-number> <keywords>` label already on it,
even though it is a fresh report that needs full triage.

Treat a pre-existing label as a **routing hint**, not a decision:
it tells you which prior report or CVE this one relates to,
so you can reuse its PMC and align the keywords,
and (downstream) cross-reference the earlier thread.
Then triage the head normally: decide its category and classify it like any other;
`classify` adds the assigned label and keeps the pre-existing ones.

### Special recipients

A few `To`/`Cc` recipients mean a message is not a fresh report but a **mirror** of one that arrived (or will arrive) by the normal path.
Do not file it as a new report: find the report it mirrors and give the mirror the **same tag**, so both messages carry one Gmail label.

Known special recipients:

- **`airflow-s@noreply.github.com`** (Airflow).
  A GitHub notification for the Airflow PMC's private `airflow-s/airflow-s` security-issue repo, where a PMC member re-files each inbound report.
  So this notification mirrors a report the reporter also sent to `security@airflow.apache.org` or `security@apache.org`.
  Find that report by matching the subject in `email-classification/<pmc>`.
  Apply **its** tag to the notification verbatim, with `set <id> --add-label "<tag>"`,
  and record that it needs nothing from us (`--disposition track`).
  Labels are stored as given, so an active tag and a `zzz-non-issue/...` one are both just passed through.
  If you cannot find the original (the mirror may have arrived first, or the report went elsewhere), flag it rather than invent a tag.

### Deciding PMC, track-only and keywords

- **PMC**: confirm the PMC the report is for, based on the report content.
  The PMC guessed in the download phase and showed by `show` is the starting point,
  but is not always correct.
- **Track-only?**: once the PMC is settled, decide whether the report already reached *its* security team.
  That is the whole question behind `--track-only`:
  if the report was delivered where we would otherwise forward it, there is nothing for us to send, and we only track it.

  Ask whimsy-lookup for the PMC's security contact:

  ```bash
  uv run --project tools/whimsy_lookup whimsy-lookup pmc-security-info <pmc> --json
  ```

  Read `security_contact` off the record, then compare it with the report's `To`/`Cc` (from `show`):

  1. If `private@<pmc>.apache.org` is among the recipients, then it was delivered to the PMC.
     Classify it --track-only.
  2. If `security@<pmc>.apache.org` is among the recipients, there are two possibilities:
     1. The project's security contact is `security@<pmc>.apache.org`:
        the PMC's own security team already has the report.
        Classify it with `--track-only`.
     2. The project's security contact is `security@apache.org`:
        the PMC does not have a security team.
        Classify it normally: it still needs forwarding, so it is not track-only.

- **Keywords**: short, lowercase, single-word terms capturing the issue.
  Each keyword must match `[a-z0-9_]+`: no `-` inside a keyword (use `_` if you must join two parts, e.g. `file_read`, not `file-read`).
  `report-cache` enforces the character set and caps the hyphen-joined slug at 60 chars
  (long enough for a handful of words, short enough to keep paths and `ls` output legible).
  If it rejects your keywords, drop the least informative one or shorten it.
- **Keyword order: where, then what, then which one.**
  This order is fixed, and it is the only place it is stated - the leading keyword is the strongest filter,
  so similar reports cluster by their tag prefix, and a tag that leads with the wrong thing files itself
  next to unrelated reports.
  1. **Where it is**: the PMC's subproject (`per_pmc.<pmc>` in [`tag-vocabulary.yaml`](tag-vocabulary.yaml),
     e.g. `compress` for Commons), or a component of the main project when the PMC has no subproject for that surface.
  2. **What it is**: the vulnerability class (`vuln_class` in the vocabulary).
  3. **Which one**: whatever else makes the tag unique - a narrower component, a `modifier`, a CVE-vector keyword.

  The class is *not* the lead, however specific it feels:
  `xxe` is what happened, `digester` is where, and the cache is organised by where.

  Examples: `digester xxe file_read` (commons-digester XXE leading to file read),
  `tribes deser cluster` (Tomcat Tribes cluster-channel deserialization),
  `operator rce dag` (Airflow operator-templating RCE, reached via a DAG).
  Each leads with the subproject, then the class, then what distinguishes it.

  The exception is a report with no project surface to lead with -
  a foundation-wide CVE intake, say - where the class has to: `deser jdbc h2`.

### Deciding reporter's name

`reporter_name` is **how to address the reporter**, not who they are:
it is the name a downstream reply greets them by (`Hi <name>,`),
so record the name they would expect to be called.
Pass it with `--reporter-name` on `classify` (or `set`).

The download seeds it from the `From` display name,
resolving the list's `<Name> via security <security@apache.org>` rewrite through `Reply-To` when there is one.
That seed is only a default, and for addressing someone it is often wrong:

- it may be missing entirely (an address-only `From`);
- it may be a handle, an alias, or an employer's `Last, First` formatting;
- it may still read `<Name> via security`, if the rewrite left no `Reply-To` to recover the sender from;
- it is usually the full name, where a reply wants only the given name.

The **signature** is the better source:
how a reporter signs off is how they want to be called.
Prefer it over the display name whenever the two disagree.

Rules of thumb:

1. Record the given name the signature uses (`Jane`), not the full name (`Jane Reporter`), and never the address.
2. Do not derive it by splitting the display name.
   Name order is not universal, so a family-name-first `From` would yield the wrong greeting;
   take what the signature shows.
3. Drop a surviving `via security`: it is a DKIM-rewrite artifact, not part of anyone's name.
4. If the report is unsigned and the display name is unusable, leave it unset rather than guess -
   greeting someone by the wrong name is worse than not greeting them by name at all.
   Say so in your proposal.

### Pick keywords from the established vocabulary

Before inventing a new keyword, consult [`tag-vocabulary.yaml`](tag-vocabulary.yaml) and **prefer an existing canonical keyword over a synonym**.
New reports clustering under the same tag as historical ones is the whole point:
the cache and the sibling `email-classification/` archive both become searchable by tag.

The file has these sections:

- `global.vuln_class` - the vulnerability class (`rce`, `dos`, `deser`, `xss`, `ssrf`, `traversal`, `sqli`, `xxe`, `bypass`, `injection`, …).
- `global.component` - what the vuln hits (`file`, `path`, `session`, `header`, `jdbc`, `jwt`, `xml`, `yaml`, `regex`, `template`, …).
- `global.modifier` - narrowing (`read`, `write`, `stored`, `reflected`, `pre_auth`, `default`, …).
- `per_pmc.<pmc>` - subprojects / components specific to a PMC (e.g. commons `compress`, `jexl`, `fileupload`; airflow `dag`, `operator`; tomcat `tribes`, `hpack`; logging `log4j`, `log4j2`).

Which section a keyword comes from does **not** set its position:
the order is fixed in [Deciding PMC, track-only and keywords](#deciding-pmc-track-only-and-keywords) -
subproject or component first, the class second, the rest after.
These sections say what a keyword *is*, not where it goes.

Rules of thumb:

1. **Prefer the canonical form over a synonym.**
   If the report names a deserialization sink, use `deser`, not `deserialization` or `deserialize`.
2. **A `per_pmc` subproject beats a generic `component`** for the leading keyword:
   subprojects sort the cache better than generic component words.
   Reach for `global.component` only when the PMC has no subproject for the surface in question.
3. If the report does not fit any existing keyword, a new one is fine -
   just make sure the form matches the existing style (single lowercase word, `_` not `-` for compounds).
   Mention the new keyword in your proposal so the user can decide whether it belongs in the vocabulary file.

### The labelling subagent

Spawn one [lightweight-model](#the-lightweight-model) subagent per `status: downloaded` message.
Keep raw bytes out of the main context: the subagent reads the message, the main agent sees only the small proposal.

Give it the message's `<id>` and tell it to:

- read the message with `report-cache show <id>`,
  and any attachment worth reading with `report-cache get-attachment <id> <name>`;
- consult [`tag-vocabulary.yaml`](tag-vocabulary.yaml) before inventing a keyword;
- look the PMC up with `whimsy-lookup pmc-security-info <pmc> --json` to settle `reached_pmc`;
- return **only** this JSON:

```json
{
  "category": "report",                 // report | digest | non-issue | mirror | non-report
  "pmc": "spark",                       // slug, from the CONTENT (see below); null if none is named
  "reached_pmc": false,                 // did it also reach the PMC's own security team?
  "keywords": ["rest", "ssrf", "api"],  // report only: where, then what, then which; [a-z0-9_], <=3
  "reporter_name": "Jane",              // report only: how to greet them, from the signature
  "labels": [],                         // digest / non-issue / mirror: labels to add, verbatim
  "reason": "SSRF in the REST API admin proxy"  // one line; for non-report, why it is not one
}
```

Which fields carry the answer depends on the category:

| Category       | `pmc`               | `reached_pmc` | `keywords` + `reporter_name` | `labels`                    |
|----------------|---------------------|---------------|------------------------------|-----------------------------|
| **report**     | yes                 | yes           | yes                          | -                           |
| **digest**     | the PMC it is *for* | -             | -                            | every listed report's label |
| **non-issue**  | yes                 | -             | -                            | the standing label          |
| **mirror**     | yes                 | -             | -                            | the original's label        |
| **non-report** | null                | -             | -                            | -                           |

Two fields need care, because the obvious answer is the wrong one:

- **`pmc` comes from the content, not the headers.**
  Which list a message was sent to says where it landed, not what it is about:
  a dependency inquiry arrives on `security@apache.org` but concerns whichever project the body names.
  Read the subject and body for the project, and treat the `pmc` that `show` reports
  (the download's guess from `To`/`Cc`) as a hint to confirm, not an answer to echo.
- **`reached_pmc` is about delivery, not capability.**
  It is true only when the PMC's registered `security_contact` is itself in the message's `To`/`Cc` -
  that is, the report is already with the people who would receive our forward.
  A project *having* its own security team does not make it true
  (see [Deciding PMC + keywords](#deciding-pmc-track-only-and-keywords)).
  It is what drives `--track-only`, and it only applies to a **report**:
  a digest or a mirror needs nothing from us whatever the PMC does.

The subagent decides nothing irreversible;
the main agent presents the proposals, gets the user's confirmation, and runs the `report-cache` CLI.
Treat its keywords as a draft - reconcile them against the vocabulary before classifying -
and its `labels` as a claim to verify, not a value to pass through unchecked.

## Authorization and privacy

`security@apache.org` is foundation-private and can carry PII.
Running this SKILL is an authorized, local-processing activity by a Security-team member who is entitled to read the list.
The download authenticates with the read-only `gmail.readonly` scope, which cannot modify, move, or delete mail.
Report content stays in the gitignored `report-cache/` and is never committed.
Keep the working copy on a machine appropriate for the content.

## Applying the cache labels to Gmail

`report-cache` records the labels a report should carry, but it never touches Gmail (the download/label half of the pipeline is read-only).
The credentialed **`inbox_manager`** tool is what reconciles them onto the live message: when it processes a report (a forward or reply, a tracked report, a digest, or a standing non-issue) it fetches the message's current Gmail labels, offers the operator the recorded set that is **missing from Gmail**, and on confirmation adds them and archives the message (drops `\Inbox`).

This is what puts every covered report's label on a **digest** message (its label set is that whole list, often a dozen-plus, none of which Gmail has yet), and what applies a report's own `<pmc>/<date> <keywords>` label when it is forwarded, replied to, or tracked.
Because the attach is driven off the recorded labels, getting the digest's `--add-label` list right here is what makes the digest surface alongside each report it lists.

After `inbox_manager` archives a message, the next full `populate-cache` run deletes its bundle and triage record: the message has left the inbox, so it is handled.

## Handoff

After a download and label pass, nothing is left at `--status downloaded`:
real reports are `classified` under `<pmc>/<date>-<keywords>/`,
reports that already reached their PMC - and digests and mirrors - are `assessed` + `--disposition track`
(nothing for us to send),
standing non-issues carry a `zzz-non-issue/<pmc>/<label>` label,
and non-reports carry `disposition: skip`.
The **drafting SKILL** then assesses each classified report against the PMC's threat model
and attaches the model's fragments (`summary.md` / `reason.md`) with `report-cache put-artifact`,
skipping anything already `track`ed (a digest, or a report in a specialized PMC's hands).
A **status SKILL** reports handled/unhandled counts across the cache.
Both go through the `report-cache` CLI rather than the layout,
and neither sees a handled report: its bundle is deleted once the message leaves the inbox.

## The lightweight model

Where this SKILL says *lightweight model*, use the smallest capable model the host agent offers.
The point is not a particular model:
it is that the reading is delegated, so raw message bytes stay out of the main context
and one subagent per report is affordable enough to fan out.

| Host          | lightweight model         |
|---------------|---------------------------|
| Claude Code   | Haiku                     |
| Codex         | an OpenAI nano-tier model |
