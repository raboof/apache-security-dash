---
name: glasswing-scan-run
description: >-
  Umbrella orchestration SKILL for the Glasswing scan pipeline —
  the periodic "run a full sweep across the program" entrypoint.
  Performs a read-only sweep across all four input surfaces (Gmail [GLASSWING] threads, the Mythos tracker spreadsheet's PMCs sheet, GitHub PRs the Security team has opened on PMC repos, incoming Mirko/Alpha-Omega scan-result mail) and produces a single action list — per-PMC, classified by where each engagement sits in the pipeline (new request, awaiting PMC reply, model-verify pending, ready to submit, submitted to vendor, results back, forwarded, etc.).
  The user picks what to act on;
  this SKILL never writes —
  it hands off to glasswing-scan-response, glasswing-model-verify, glasswing-scan-update, glasswing-scan-submit, glasswing-scan-forward, or glasswing-scan-status for actual work.
  Use this at the start of a work session,
  when picking back up after time away,
  or whenever Jarek says "where do we stand on Glasswing", "run a full scan sweep", or "what's pending across the program".
---

# glasswing-scan-run SKILL

The umbrella orchestration for the Glasswing scan-outreach pipeline.
This SKILL's only job is to **survey**:
it scans every input surface,
cross-references state,
classifies every in-flight engagement,
and surfaces a per-PMC action list that the user can triage.
All writes happen via the per-task SKILLs that this one hands off to.

The pipeline this SKILL covers:

**Scan pipeline** (one path; operator-gated):

```
                                                                              +-------------------+
                                                                              | Vendor pipeline   |
                                                                              +---------+---------+
                                                                                        | scan results
                                                                                        v
+--------+  +---------+  +---------+  +-----------+  +-----------+  +-----------+  +-----------+  +-----------+
|[GLASS- |->|Pre-     |->|Pitch    |->|PMC reply  |->|Operator   |->|Submitted  |->|Sanity-    |->|Archived + |
| WING]  |  |flight   |  |sent to  |  |(expedite  |  |gate       |  |to vendor  |  |checked    |  |Forwarded  |
| request|  |(model + |  |PMC      |  | list /    |  |(explicit  |  |(Forms +   |  |(catastr.  |  |to PMC     |
|        |  | discov.) |  |(scan-   |  | 'none')   |  | go-ahead) |  | PMC mail) |  | errors    |  |verbatim   |
|        |  |         |  | response|  |           |  |           |  |           |  | only)     |  |(named     |
|        |  |         |  | template)|  |           |  |           |  |           |  |           |  | contacts) |
+--------+  +---------+  +---------+  +-----------+  +-----------+  +-----------+  +-----------+  +-----------+
   ^                                                                                                       |
   |                                                                                                       v
PMC inbox                                                                                              PMC's normal
                                                                                                       triage process
```

**OSS-tooling side flow** (parallel, non-blocking on the scan pipeline).
The PMC's reply to the pitch above may nominate `@apache.org` addresses for an Anthropic-Claude-for-Open-Source subscription expedite ask.
If it does, the flow is:

```
+-----------+    +---------------+    +---------------+    +---------------+
| Step 1:   |    | Step 2:       |    | We relay      |    | Anthropic     |
| PMC mem-  |--->| Expedite list |--->| expedite via  |--->| grants subs.  |
| bers reg- |    | written to    |    | vendor to     |    | Recorded in   |
| ister at  |    | "Expedite     |    | Anthropic     |    | "Claude OSS   |
| claude.   |    |  Claude OSS   |    | (best-effort, |    |  Subscriptions|
| com/      |    |  Requests"    |    |  no promise;  |    |  Submitted"   |
| contact-  |    | cell          |    |  track record |    | cell as they  |
| sales/    |    |               |    |  is fast)     |    | confirm       |
| claude-   |    |               |    |               |    |               |
| for-oss   |    |               |    |               |    |               |
+-----------+    +---------------+    +---------------+    +---------------+
```

The two flows are independent:
the scan can be submitted with or without an OSS expedite ask in flight,
and an expedite can be relayed before, during, or after the scan submission.
The pitch step in the scan pipeline raises the OSS-tooling offer (one outbound email),
and the PMC reply step collects both decisions in one inbound response (which @apache.org addresses to expedite — if any — and any substantive scoping / threat-model follow-up).

The `Archived` step is a synchronous part of `glasswing-scan-forward`:
the SKILL sanity-checks Mirko's report (catching catastrophic generation errors — wrong project, wrong/stale model, truncation, missing repos),
commits the vendor's markdown + `.json` raw + `.notes.md` sanity-check log to [`scans/<project>/<repo>/`](../../../scans/README.md),
then drafts the forwarding email (vendor findings verbatim, no per-finding triage) citing the archive filename.
The single user-approval gates both the commit and the email; see [`scans/README.md`](../../../scans/README.md) for the path / metadata / confidentiality spec.

Each stage has its own SKILL responsible for the work that moves an engagement through it.
This SKILL doesn't replicate that logic —
it just figures out which stage each engagement is *in* and surfaces what to do next.

## Program timeline — deadline lifted; criticality-ordered queue (read this)

Until late May 2026 the program ran on a *"no rush"* footing:
scans went through the third-party **vendor-relay path** (Alpha-Omega runs the scan off a Google-Form submission and emails the report back),
the queue was open-ended,
and PMCs were told there was no deadline.

Anthropic/Glasswing's **27 May 2026 donation of $1M in Mythos credits to the ASF** briefly added a **direct-internal path** (the ASF Security / Infra / Tooling teams run scans themselves on directly-granted access, no vendor relay) under an original **30 June 2026** credit-expiry.

**That hard 30 June expiry is gone.**
Per Sally Khudairi's 2026-06-09 program update and the 2026-06-10 all-PMC broadcast, the cut-off is being **extended**:
the program is moving from Mythos Preview onto the upgraded **Mythos 5** model and the ASF retains its spot/status in Anthropic's provisioning queue.
As of **2026-06-13**, Anthropic has a broad **pause on new provisioning** (tied to the US export-control situation in the `fable-mythos-access` announcement) — the ASF is explicitly **"not out,"** but direct provisioning is on hold **with no ETA**.
None of that stops scanning:
the pipeline is **model-agnostic** (the vendor-relay path plus any-model internal runs — Opus / Sonnet / Haiku or any family), so scans continue regardless of where direct-Mythos provisioning lands.

What this changes for *this* SKILL is the **patience posture**: there is **no hard cliff** anymore.
Ordering is by **readiness + OSS Criticality Score**, drawn from the pre-flight-cleared **Scan Queue** (see `build-status-tab`).
Engagements parked in `awaiting-pmc-reply`, `blocked-on-discoverability`, `blocked-on-gate-2`, `model-verify-pending`, or `pmc-pitch-replied-awaiting-operator-decision` are still worth nudging —
not to beat a deadline, but because clearing those items is what puts a PMC *into* the queue at its criticality rank, and the sooner they land the sooner it is in line.
A gentle-but-firm nudge canned response (topic `deadline`) exists for these stalled PMCs and is already reframed around the queue, not a cliff.
The signed-up PMCs already in the pipeline keep their spot;
the nudge is about getting prerequisites in, not re-qualifying them.

Internal only — keep OUT of PMC-facing text (Hard Rule 5 / the response SKILL): the seat/credit conditions, the provisioning pause, and the vendor identity.
PMC-facing framing is simply "no hard deadline; scans run in OSS Criticality Score order from a pre-flight-cleared queue."

## When to invoke

- **Start of a work session.** "Where do we stand on Glasswing?" —
  run a full sweep first so the rest of the session is grounded in current state,
  not in what was true last time we worked.
- **After time away.** Multiple days of accumulated email + spreadsheet edits + open PRs need cross-referencing before any per-PMC work makes sense.
- **Before sending a status update.** Foundation-level or Security-team rollup emails should be sourced from the Status sheet that this SKILL refreshes.
- Whenever Jarek says explicit triggers: "sync up the scan tracker", "what's pending across the program", "do a full Glasswing sweep", "are there new requests?", or anything similarly broad.

Skip when the user is already mid-task on a specific PMC (don't sweep when they say "draft a reply to Mark" —
go straight to `glasswing-scan-response`).

## Hard rules (do not skip)

1. **Read-only at the umbrella level.** This SKILL never writes to Gmail, the spreadsheet, or GitHub.
   It surveys, classifies, and surfaces.
   When something needs writing, the user invokes the matching per-task SKILL.

2. **Surface, don't auto-decide.** When multiple PMCs are pending the same action, *list them* and let the user pick where to start.
   Do not silently batch.

3. **Cite the source of every conclusion.** If the sweep says "Tomcat is waiting on Mark to choose a path for the 3 missing repos", cite the Gmail thread id (or subject) and the spreadsheet row that supports that conclusion.
   Stale reads happen; the user verifies.

4. **Don't replicate per-task SKILL logic.** Don't decide what reply to draft —
   that's `glasswing-scan-response`'s job.
   Don't decide model remediation — that's `glasswing-model-verify`.
   This SKILL's output is a list of "needs X; SKILL Y handles it";
   the per-task SKILL does the actual decision-making.

5. **Refresh the Status sheet at the end** by invoking `glasswing-scan-update`'s `build-status-tab` subcommand.
   That makes the sweep's findings durable for anyone else on the team to read.

6. **Never claim "draft queued / not sent" without calling `list_drafts` in the same sweep.** Session memory of "I created draft X earlier" is not evidence X is still pending —
   Gmail's `create_draft` returns a draft ID immediately,
   but the operator may have already opened Gmail and clicked Send between then and now.
   The only trustworthy signal that a draft is still pending is a live `mcp__claude_ai_Gmail__list_drafts` call returning the draft.
   A sweep that asserts "N drafts queued" without that call is making things up —
   that's how the 2026-05-28 sweep falsely reported 6 drafts pending when all 6 had already been sent.

7. **Never trust a thread-search result's "last message" —
   resolve the true latest message per-thread with `get_thread`.**
   `mcp__claude_ai_Gmail__search_threads` caps the `messages` array it returns at ~5 per thread,
   and those 5 are **not** guaranteed to be the newest —
   it has been observed returning the *oldest* 5 on `newer_than:` / paginated queries.
   So `messages[-1]` from a search result is a reliable "last message" ONLY for threads with ≤5 messages total;
   for any thread at the 5-message cap it is stale.
   This cuts both ways and both failure modes are real:
   the 2026-05-31 sweep **undercounted** (six older PMC threads — Grails, APISIX, Dubbo, Fineract, Hop, Directory — had recent PMC replies sitting past the cap,
   so they looked quiet when they were actually awaiting us)
   **and overcounted** (DB and Struts were flagged "awaiting us" when we had in fact already replied past the cap).
   The only trustworthy "who sent the last message, and is it ours?" signal is a per-thread `get_thread` (MINIMAL format is enough —
   it returns every message's `sender`, `labelIds` (look for `SENT`), and `date`).
   Step 1 below makes this mechanical and cheap via a thread-state cache so you don't re-pull every thread every sweep —
   but when the cache says a thread changed, or when you're about to assert a thread's awaiting-state,
   the verdict must come from `get_thread`, never from the search snippet.

   **Corollary — `is:unread` is NOT a safe proxy for "awaiting us".**
   It is tempting to shortcut the per-thread resolution with `subject:GLASSWING is:unread`,
   on the theory that an unprocessed PMC reply is unread.
   It is not reliable:
   the operator reads mail in the Gmail UI,
   which clears the unread flag *without* the thread being actioned —
   so a read-but-unanswered PMC reply is invisible to `is:unread`.
   The 2026-06-01 verification sweep proved this:
   an `is:unread` pass surfaced 5 awaiting-us threads but **missed OpenDAL and bRPC**,
   both of which had PMC replies (scope confirmation; a revised threat-model) that had been read but never answered.
   `is:unread` may be used as a *hint* to prioritise,
   never as the awaiting-state verdict —
   that always comes from the per-thread true-last-message resolution below.

   **Why the snippet is stale even after full pagination.**
   `search_threads` orders threads by **creation date** (the thread's first message) and the `messages` array it returns is the **first** messages, not the newest.
   So a thread created early (e.g. 05-13) with a fresh reply today sorts onto a *late* page AND shows a stale "last message" in its snippet —
   the cap and the ordering compound.
   Paginating to exhaustion (Step 1) is necessary but **not** sufficient:
   it guarantees you *see* every thread, not that you know its true latest message.
   Only a per-thread `get_thread` on every thread with ≥5 messages (where the snippet is, by definition, possibly truncated) closes the gap.
   The 2026-06-01 sweep, run after the pagination fix had already landed, still found three awaiting-us threads hidden this way (OpenDAL, bRPC, Superset) —
   pagination alone would not have caught them.

## Procedure

### Shell-safety note — write `awk`/`jq` programs to a file, never inline

Several steps below post-process tool output with `awk` or `jq` (the PR-attention triage in Step 3, the thread-direction extraction in Step 1, the spreadsheet projection in Step 2).
**Do not pass non-trivial `awk`/`jq` programs as inline single-quoted strings to the Bash tool.**
The session shell is `zsh`,
and `awk` programs containing `!` (e.g. `!=`, `!isbot`) get mangled by history-expansion/quoting before `awk` ever sees them —
the program arrives with stray backslashes (`$7\!=ours`) and dies with `awk: syntax error`.
This repeatedly cost re-runs during the 2026-06-04 sweep.

Instead, **write the program to a file in `$TMPDIR` / `/tmp/claude` and run it with `-f`:**

```bash
cat > /tmp/claude/pr_analyze.awk <<'AWK'
BEGIN{FS="\t"}
$3=="OPEN" && $4=="CHANGES_REQUESTED" { ... }
AWK
awk -f /tmp/claude/pr_analyze.awk /tmp/claude/pr_state.tsv
```

The quoted `<<'AWK'` heredoc (single-quoted delimiter) passes the body through verbatim —
no history expansion, no variable interpolation, no `!` mangling.
The same applies to multi-line `jq` filters:
write them to a `.jq` file and use `jq -f file.jq`,
or — when the JSON comes straight from a tool that emits its own `jq` (e.g. `gh ... --json ... --jq '<expr>'`) — prefer that tool's built-in `--jq`,
which parses the JSON natively and sidesteps both the shell-quoting hazard and the control-characters-in-piped-bodies hazard (comment/review
bodies contain raw newlines that a shell `echo "$json" | jq` round-trip chokes on).

Rule of thumb: anything past a one-liner with no `!` goes in a file.

### Step 1 — Email sweep

Search Gmail for `subject:GLASSWING OR subject:Glasswing`.

**Paginate to exhaustion — never stop at the first page.**
`mcp__claude_ai_Gmail__search_threads` caps each page at `pageSize=50` and returns a `nextPageToken` whenever more threads exist.
Loop: issue the search,
accumulate the returned thread IDs,
and if the response carries a `nextPageToken`, re-issue with that token —
repeat until the token is empty.
After any page returns 50 results, **assume there is a next page until the empty-token response proves otherwise**.
The program already exceeds 100 GLASSWING threads (≈106 across 3 pages as of 2026-06-01),
so a single 50-thread page is a fraction of the set.
A sweep that classifies only the first page produces *complete spreadsheet-derived state but incomplete email-direction state* —
PMCs whose thread sorts onto page 2+ look quiet when they may in fact be awaiting our reply (the 2026-06-01 sweep missed APISIX, Thrift, Hop, Directory, and Grails this way).
Cross-check the full accumulated thread set against every `Scan Requested = Yes` row in the spreadsheet so no in-flight PMC is left only-sheet-classified.

For each thread (across all pages), classify into one of these buckets:

| Bucket | Signal |
| --- | --- |
| **New `[GLASSWING]` request** | Subject matches `[GLASSWING] <PMC>:` and the PMC isn't yet in the spreadsheet as `Scan Requested = Yes`. |
| **Reply on existing request thread** | We've already replied at least once (`SENT` label present in thread); a *newer* message exists from the PMC after our last reply. |
| **Reply we haven't acted on** | Same as above but our last action (Gmail draft or sheet write) is older than the most recent PMC message. |
| **Pure announcement-thread chatter** | A reply to the original `[IMPORTANT][SECURITY]` announcement that isn't substantive (just "+1", "interesting", etc.). Log and skip. |
| **Bot / automated** | Git push notifications, PR review notifications, MAILER-DAEMON, etc. Filter out — don't include in the action list. |
| **Mirko / Alpha-Omega correspondence** | From `mirko@alpha-omega.dev` or `@alpha-omega.dev`; subject containing scan-request acknowledgement, queue position, or scan result delivery. |

Filter out noise (the announcement-thread `+1`s, the git push emails, the GitHub PR-review notifications, MAILER-DAEMON bounces).
These typically arrive in volume; skipping them keeps the action list useful.

**Per-thread true-last-message resolution (mandatory — see hard rule 7).**
The search above tells you *which* threads exist;
it does **not** reliably tell you who sent the last message (it caps each thread at ~5 messages and may return the oldest).
Whether a thread is `awaiting-pmc-reply` vs `pmc-reply-awaiting-action` therefore must be decided from a per-thread `get_thread` (MINIMAL format),
never from the search snippet.
For each non-noise thread, the resolved record is:

```
{ thread_id, subject, msg_count, latest_msg_id,
  latest_msg_date, latest_from, latest_is_ours, awaiting }
```

where `latest_is_ours = (latest message's labelIds contains "SENT")`, and `awaiting` is `us` (last message is the PMC's), `pmc` (last message is ours), or `none` (closed/submitted).
Only after this record is built do you classify the thread in Step 4.

**Exhaust message pagination *inside* each thread, not only the thread list.**
"Who sent the last message" is correct only if you have actually fetched the *last* message.
`get_thread` returns a thread's messages in order,
but a long thread can exceed one page —
if the response carries a `nextPageToken` (or otherwise signals the `messages` array is capped with more to come),
follow it until the token is empty and take the true final message.
A thread can sit awaiting *us* with the operative PMC reply on the last message-page while earlier pages still show our older reply;
stopping at page 1 of the *messages* repeats the page-1-of-*threads* mistake one level down.
Both axes — the thread list (above) **and** the message list within every changed thread — must be drained to exhaustion before any `awaiting` verdict is recorded.

**Thread-state cache (do this so you don't re-pull every thread every sweep).**
Email is append-only:
a message, once sent, is immutable and a thread's message list only ever *grows*.
So a thread whose newest message hasn't changed since the last sweep keeps its previously-resolved verdict —
there is nothing new to read.
Exploit that:

1. **Cache file:** `~/.cache/asf-security/glasswing/thread-state.json` (sandbox-writable; create the dir if missing).
   Shape: `{ "last_sweep": "<ISO8601>", "threads": { "<tid>": <record above> } }`.
2. **Load** the cache at sweep start (empty `{}` on first run).
3. **Find the changed set** with a search: `mcp__claude_ai_Gmail__search_threads` with `query="subject:GLASSWING after:YYYY/MM/DD"`, where the date is `last_sweep` minus a 1-day safety buffer.
   Every `thread_id` it returns is a thread that gained ≥1 message since the last sweep (new PMC requests show up here too).
   **This search paginates too** —
   if the response carries a `nextPageToken`, loop on it until empty (a busy week can exceed 50 changed threads).
   Do not stop at the first page.
4. **Refresh only the changed set + any thread absent from the cache:**
   call `get_thread` (MINIMAL) on each, rebuild its record, and overwrite the cache entry.
   Threads in the cache but *not* in the changed set are unchanged —
   reuse their cached record verbatim (no `get_thread`).
5. **Save** the cache with `last_sweep` set to the start time of this sweep (pass the timestamp in;
   do not call `Date.now()` inside a helper that must stay deterministic).

The cache is a *speed + correctness aid*, never the source of truth —
Gmail and the spreadsheet are.
If a record looks stale, contradictory, or you're about to act on it, re-pull the thread.
The first sweep (cold cache) resolves every active thread once;
every later sweep only re-reads the handful of threads that actually moved.

Note: `get_thread` here is **MINIMAL** — you only need direction, not bodies.
Fetch `FULL_CONTENT` only later, in the per-task SKILL, when you actually draft a reply to a specific thread.

**Draft-folder enumeration** (mandatory — see hard rule 6).
After the thread sweep, call `mcp__claude_ai_Gmail__list_drafts` with `query="subject:GLASSWING"` and `pageSize=50` and capture the result as `{thread_id, draft_id, draft_subject}` for each returned row —
**paginating on `nextPageToken` until empty**, same as the thread search (a backlog of unsent drafts can exceed one page).
This is the *only* trustworthy signal that a draft is still pending in Drafts vs. already sent —
session memory of "I created draft X earlier in this session" is not evidence (the operator may have manually clicked Send between draft-create and sweep).
If `list_drafts` returns empty, every PMC thread classified in earlier steps as "we replied last" is in `awaiting-pmc-reply`, not in `draft-pending-manual-send`.

### Step 2 — Spreadsheet read

Fetch the `Mythos scan` workbook (file ID in user-scope reference memory under `mythos-tracker`).
Specifically:

- **PMCs sheet** — full row dump for every row where `Scan Requested = Yes`.
  Capture every column:
  scope, contacts, model status, every date, notes, assessment, PR/Issues.
- **Status sheet** (if present) — the previously-generated in-flight + completed view, as a fast confirmation of what the email sweep should match.

**Important — Drive MCP truncation caveat.**
The Drive MCP (`mcp__claude_ai_Google_Drive__read_file_content`) silently truncates the spreadsheet rendering at ~80KB of markdown, dropping rows past the first ~140 alphabetically (cuts off around "Apache Phoenix" with the current ~210-PMC tracker).
PMC rows beyond that boundary are **invisible** to a sweep that relies on the MCP output alone —
sweeps will silently miss in-flight PMCs like Tomcat, Polaris, Shiro, Spark, Thrift, Traffic Server, and anything else that sorts after `P`.
For accurate sweep coverage, read the whole sheet straight off the Sheets API with the `sheets-writer dump` subcommand (read-only; in `tools/sheets_writer/`) instead of the MCP:

```bash
uv run --project tools/sheets_writer sheets-writer dump \
  --spreadsheet-id <id> --sheet PMCs --objects | jq '...'
```

`dump` prints the full sheet as JSON with **no truncation** (`{header, rows}` by default, or `--objects` to key each row by its header) and pipes to `jq`,
so the row bytes never enter model context.
The MCP read remains fine for the *content* of a single row you've already identified.
Misdiagnosis from trusting the truncated MCP output cost the 2026-05-16 sweep a wrong "6 PMCs need new rows" conclusion that the helper's duplicate-slug guard then caught on first append-attempt.

For each PMC row, compute the same pipeline state that `build-status-tab` does (Pre-flight / Ready / Submitted / Triaging / Delivered).
("Triaging" is the legacy state-column name written to the sheet;
the team's actual activity in that state is a pre-forward sanity check, not per-finding triage —
see `glasswing-scan-forward`.)

### Step 3 — Open-PR + change sweep (state + attention triage)

This pass must cover **every open PR/change the operator has authored**, not only the ones recorded on the tracker —
the tracker's `PR/Issues` cells lag reality (model and discoverability PRs get opened mid-discussion and added to the sheet later, if at all;
the 2026-06 audit found several operator-opened model PRs — ozone, santuario, solr, creadur — that no tracker cell pointed at).
Build the candidate set from **three** sources and dedupe:

1. **Tracker-listed** — every URL in a non-empty `PR/Issues` cell.
2. **Author-discovered (exhaustive)** — query GitHub for *all* open PRs authored by the operator, paginating to exhaustion:

   ```
   gh search prs --author=@me --state=open --limit 100 \
     --json url,repository,title,updatedAt
   ```

   `gh search` caps at 100 results;
   if the result hits the cap, re-query with date-window narrowing (`--updated <range>`) until every window is drained.
   Do **not** restrict to GLASSWING-spawned or `asf-security/*` branches —
   any open PR waiting on us counts,
   including ones opened from a past discussion that never made it onto the sheet.
3. **Gerrit changes** — the operator also opens changes on Apache-adjacent Gerrit hosts (e.g. `gerrit.cloudera.org` for Kudu) that GitHub never sees.
   For each Gerrit instance the team uses, list the operator's open changes (`is:open owner:self`) and fold them into the candidate set.
   When a Gerrit host can't be reached from this environment (not allowlisted / auth not set up), **surface it as an explicit manual-check item** in the action list rather than silently dropping it —
   an unreachable host is an unresolved direction, not an absent PR.

Dedupe the union by `owner/repo#num` (a tracker URL and an author-discovered hit are the same PR;
keep the PMC association from the tracker where one exists, else label the PR's repo).
Then for each candidate:

- Parse the URL(s).
- Query each PR's current state.
  Pull enough to triage attention, not just open/closed:

  ```
  gh pr view <url> --json number,state,isDraft,merged,mergeable,\
    reviewDecision,updatedAt,author,comments,reviews,statusCheckRollup
  ```

- Bucket the PR by lifecycle: `open` / `closed` / `merged`.
- Note: a merged AGENTS.md / model PR means we can re-run `glasswing-model-verify`'s discoverability check on that repo;
  surface it.

**Attention triage (run on every sweep — this is the "are any PRs waiting on *us*?" pass).**
The Security team opens many PRs on PMC repos (model + discoverability),
almost all authored by the operator's GitHub identity via `asf-security/*` fork branches.
Those PRs accumulate reviewer feedback, CI results, and merge drift that the team must act on, and that rot silently between sweeps if nobody looks.
For every **open** PR, classify into one or more attention flags (skip merged/closed — just tally them):

| Flag | Signal (`gh pr view` field) | Why it needs us |
| --- | --- | --- |
| `pr-needs-reply` | A `comments`/`reviews` entry from someone **other than the PR author (us)** is newer than the author's last activity — the ball is in our court. | A maintainer asked a question / pushed back and we haven't answered; silence reads as abandonment. |
| `pr-changes-requested` | `reviewDecision == CHANGES_REQUESTED` | A reviewer is blocking on requested edits. |
| `pr-ci-failing` | `statusCheckRollup` has any `FAILURE`/`ERROR` | Our PR is red; the PMC won't merge a red PR. |
| `pr-conflict` | `mergeable == CONFLICTING` | Needs a rebase before it can land. |
| `pr-approved-awaiting-merge` | `reviewDecision == APPROVED`, still open | Low-priority: ready, just needs the PMC to click merge — a nudge candidate. |

The `pr-needs-reply` test mirrors hard rule 7 for email:
**who acted last?** Compare the latest non-author comment/review timestamp against the author's (our) latest commit/comment;
if theirs is newer, it's awaiting us.
Don't infer from `updatedAt` alone —
a CI re-run bumps it without a human acting.

A PR can carry several flags (e.g. `pr-needs-reply` + `pr-ci-failing`).
Collect, per flagged PR:
PMC, `owner/repo#num`, the flags, the commenter + a one-line gist of what they want, and `updatedAt`.
These feed the `prs-needing-attention` section of the action list (Step 5) and are **the Security team's, not the PMC's, to clear** —
route each to `glasswing-model-verify` (for model-PR review threads) or a direct reply/rebase/CI-fix,
gated on operator approval per that SKILL's draft-and-confirm rules.
The `pr-approved-awaiting-merge` set is surfaced separately as merge-nudge candidates (the merge itself is the PMC's call).

This pass is **wide** (every open PR across every in-flight PMC),
so for a large cohort fan it out —
but it runs on **every** sweep;
a PR left waiting on us for days is exactly the kind of state this umbrella exists to surface.

### Step 4 — Cross-reference and classify

For each `Scan Requested = Yes` PMC, produce a single classification:

| Classification | Definition | Next action |
| --- | --- | --- |
| `new-request-untouched` | Inbound `[GLASSWING]` request exists; no row in the sheet for that PMC yet, or the row has no `Request date`. | Run `glasswing-scan-response` gates 1–4. |
| `pmc-reply-awaiting-action` | PMC has sent a newer message than our last reply / sheet write. | Read the new message; run `glasswing-scan-response` if it raises questions; run `glasswing-model-verify` if they nominated a model; run `glasswing-scan-update` if it confirms scope / dates. |
| `draft-pending-manual-send` | A Gmail draft exists in Drafts for this PMC's thread that the operator hasn't sent yet. **Detection signal: `list_drafts` (Step 1) returned a draft on this thread — not session memory of having created one.** | Surface for operator action — the operator reviews in the Gmail UI and clicks Send. No SKILL re-invocation needed. |
| `awaiting-pmc-reply` | We've replied last; nothing new from PMC. **Confirm via the thread's latest message having a `SENT` label, and confirm no draft is pending in `list_drafts` output.** | Wait; nothing to do unless time-overdue (see below). |
| `model-verify-pending` | Model nominated but not yet assessed for completeness + per-repo discoverability. | Run `glasswing-model-verify`. |
| `pre-flight-passed-pitch-not-sent` | `Security model verified` set; `Expedite Claude OSS Requests` cell empty; no pre-flight-pass OSS-expedite pitch has gone out yet on the PMC thread. | Run `glasswing-scan-response`'s pre-flight-pass template (OSS-expedite pitch + ready-to-scan notification). Does **not** trigger `glasswing-scan-submit` directly — `submit` is now operator-gated. |
| `pre-flight-passed-awaiting-pmc-pitch-reply` | `Security model verified` set; pre-flight-pass pitch sent but PMC hasn't replied yet; `Expedite Claude OSS Requests` still empty. | Wait. No action unless overdue (>14d). |
| `pmc-pitch-replied-awaiting-operator-decision` | `Expedite Claude OSS Requests` cell populated (with addresses or the literal string `none`); `Date scan requested` still blank. PMC has chosen path(s); waiting for the Security team operator to explicitly say "submit X" (or to defer further). | Surface for operator decision. `glasswing-scan-submit` is operator-gated — never auto-fire on this state. |
| `submitted-awaiting-vendor` | `Date scan requested` set; `Date scan received` blank. | Wait; surface if > 14 days. |
| `results-back-awaiting-sanity-check` | A scan report has arrived from Mirko but the team hasn't sanity-checked + archived + forwarded it yet. Detection signal: a `mirko@alpha-omega.dev` email with the PMC's results, plus the PMC sheet's `Date scan received` still blank. | Run `glasswing-scan-forward` (covers pre-forward sanity check, archive commit to `scans/`, and the forwarding-email draft as a single approval gate). |
| `archived-not-forwarded` | An archive commit exists under `scans/<project>/<repo>/` for this PMC but `Forwarded scan to PMC` is still blank. Process bug (the email should have been drafted at the same time). Detection signal: `git log --grep="^\[scan\] <project>/"` returns a commit newer than the sheet's `Forwarded scan to PMC` date. | Surface for manual intervention; re-run `glasswing-scan-forward` from step 7 (draft email) using the existing archive entry. |
| `forwarded-closed` | `Forwarded scan to PMC` set **and** the corresponding archive commit exists in `scans/`. | Done. Move to "Completed" section of report. |
| `blocked-on-discoverability` | Some repos in `Repositories requested` lack `AGENTS.md`; PMC needs to fix or we PR. | Surface; await PMC decision on path. |
| `blocked-on-gate-2` | Request came from non-`@apache.org` address and no `@apache.org` anchor stated. | Wait for PMC reply confirming Apache identity. |
| `mirko-correspondence` | Reply from Mirko on a queued / submitted scan. | Read the message; possibly forward to the PMC; update sheet. |

The "time-overdue" rule: any engagement in `awaiting-pmc-reply` or `submitted-awaiting-vendor` for more than 14 days gets flagged for a nudge.
**There is no longer a hard deadline (see "Program timeline" above), so the nudge is about queue entry, not beating a cliff:**
any PMC that still owes *us* something before it can be queued —
`awaiting-pmc-reply`, `blocked-on-discoverability`, `blocked-on-gate-2`, `model-verify-pending`, or `pmc-pitch-replied-awaiting-operator-decision` —
and has been quiet for more than ~7–14 days is a nudge candidate,
because clearing those items is what puts the PMC *into* the criticality-ordered queue at its rank.
Don't draft the nudge automatically;
surface it for the user and point at the `deadline`-topic canned response (gentle-but-firm, already reframed around the queue) for these stalled PMCs.

### Step 5 — Produce the action list

Output format:

```
# Glasswing pipeline sweep — <YYYY-MM-DD>

## New since last sweep
- <new requests / new PMC replies> with thread refs

## Ready to act on (per stage)

### draft-pending-manual-send (N)
- <PMC> — draft <draft_id>; on thread <thread_id>. Next:
  operator reviews in Gmail UI and clicks Send. **Listed
  here only if `list_drafts` returned the draft in this
  sweep — never from session memory.**

### new-request-untouched (N)
- <PMC> — <thread id> — next: glasswing-scan-response

### pmc-reply-awaiting-action (N)
- <PMC> — <thread id>, latest from <sender> @ <date>; key
  content: <one-line summary>. Next: <which SKILL>.

### model-verify-pending (N)
- <PMC> — model: <URL or "missing">. Repos: <count>.
  Next: glasswing-model-verify.

### pre-flight-passed-pitch-not-sent (N)
- <PMC> — verified <date>; <repo count> repos in scope.
  Next: glasswing-scan-response's pre-flight-pass template
  (OSS-expedite pitch + ready-to-scan notification).

### pre-flight-passed-awaiting-pmc-pitch-reply (N)
- <PMC> — pitch sent <date>; awaiting PMC reply on
  expedite-account list. No action unless overdue.

### pmc-pitch-replied-awaiting-operator-decision (N)
- <PMC> — verified <date>; expedite list:
  <N addresses / "none" / "empty">; awaiting operator
  decision on whether to submit. Next: operator
  says "submit X" → then glasswing-scan-submit
  (form-per-repo submission via vendor's enrollment form
  + PMC notification email).

### blocked-on-discoverability (N)
- <PMC> — <N> of <M> repos have AGENTS.md; awaiting PMC
  reply on path. Last followed up <date>.

### blocked-on-gate-2 (N)
- <PMC> — last reply from non-apache.org; we asked for
  anchor <date>.

### mirko-correspondence (N)
- <thread> — re: <PMC>; <one-line summary>.

### prs-needing-attention (N)   [waiting on US — from Step 3 triage]
- <PMC> — <owner/repo#num> — <flags: pr-needs-reply / pr-changes-requested /
  pr-ci-failing / pr-conflict> — <commenter>: <one-line gist>; last
  activity <date>. Next: glasswing-model-verify (model-PR review threads) or
  direct reply / rebase / CI fix.

### prs-approved-awaiting-merge (N)   [merge is the PMC's call — nudge candidates]
- <PMC> — <owner/repo#num> — approved <date>; open <D> days. Optional nudge.

## Awaiting PMC reply (no action needed)
- <PMC> — we replied <date>; <D days> ago.
- (overdue >14d): <PMC> — overdue by <D days>; consider nudge.

## Submitted, awaiting vendor (no action needed)
- <PMC> — submitted <date>; <D days> ago.
- (overdue >14d): <PMC> — Mirko nudge candidate.

## Completed since last sweep
- <PMC> — forwarded <date>; end-to-end <D days>.

## Who waits for whom — direction ledger (every thread + every open PR/change)
- **Awaiting us (N):** <PMC / owner/repo#num> — <thread or PR> —
  they acted last @ <date>; what we owe: <one line>.
- **Awaiting them (N):** <PMC / owner/repo#num> — we acted last
  @ <date>; nothing owed unless overdue.
- **Direction UNRESOLVED (N) — drive this to zero before the
  sweep is done:** <thread / PR / Gerrit change> — why it
  couldn't be resolved (thread or message list not fully paged,
  Gerrit host unreachable, ambiguous last actor). Each entry is
  a gap to close *now*, not to defer — re-page the
  thread/message list or do the manual Gerrit check until the
  direction is definite.

## Status sheet refresh
- Status tab refreshed at <time>. <N> in flight, <N>
  completed, <N> timeline events.
```

### Step 5.5 — Resolve ponymail thread URLs

The PMCs sheet has two columns dedicated to **direct** lists-apache.org thread permalinks:

- `PMC thread (ponymail)` — the `[GLASSWING]` request thread between the Security team and the PMC.
- `Mirko thread (ponymail)` — historically the scan-submission
  + scan-results delivery thread with the vendor.
    As of
  2026-05-19, `glasswing-scan-submit` submits scan requests via a Google form rather than email,
  so this column stays blank for new submissions —
  there is no public-list thread to permalink to.
  Kept for back-compat with pre-2026-05-19 submissions; not maintained for new ones.

Both cells should only ever contain `https://lists.apache.org/thread/<tid>` URLs — direct permalinks to the actual thread.
**No fallback or "starter" URLs.**
If a thread cannot be resolved (because ponymail auth isn't set up, or the thread isn't indexed yet), leave the cell blank rather than write a substitute.

Procedure:

1. Call `mcp__ponymail__auth_status`.
   If "Not authenticated", surface a one-line note in the action list ("Ponymail columns require `mcp__ponymail__login` — N rows skipped") and continue with the rest of the sync.
   Do not attempt to resolve URLs without auth.

2. For each PMC row where `PMC thread (ponymail)` is blank (or where it currently contains a non-permalink URL from an older sync run):

   - Call `mcp__ponymail__search_list` with `list=private`, `domain=<pmc>.apache.org`, `subject=GLASSWING`, `emails_only=true` (and a `timespan` covering the period since the original announcement to bound the search).
   - From the results, find the thread whose subject matches `[GLASSWING] <PMC>:` (or its forwarded / replied variants — e.g. Fineract has a "Fwd:" subject line) and whose first message's `from` matches the PMC contact recorded in the sheet's `Contact Person` cell.
   - Read the thread's `tid` from the result.
     Construct `https://lists.apache.org/thread/<tid>`.
   - Write back via `glasswing-scan-update` `apply`.

   Note: the ponymail MCP **blocks `security@apache.org`** entirely (restricted-list policy),
   so we always resolve PMC threads via the PMC's own `private@<pmc>` list —
   the original `[GLASSWING]` request is CC'd there,
   so the thread is in that archive too.

3. **`Mirko thread (ponymail)` is not maintained for submissions made after 2026-05-19.**
   `glasswing-scan-submit` now uses a Google form rather than email,
   so there is no public-list thread to permalink to.
   Leave the cell blank for new submissions; do not search for it.
   The column stays in the schema for back-compat with pre-2026-05-19 submissions whose Mirko-email thread was permalinked before the transition.

4. If a thread can't be found despite ponymail auth being active, leave the cell blank and surface the row in the action list under a "ponymail thread not yet indexed" note.
   Indexing can lag by a day or two for new threads.

The columns are blank-tolerant.
Never substitute a list-view URL or a search URL for a direct thread permalink —
the columns commit to direct permalinks specifically so a click lands on the thread itself.

### Step 6 — Refresh the Status sheet

Invoke `glasswing-scan-update`'s `build-status-tab` subcommand at the end of the sweep.
This produces a durable view of the same classification for anyone else on the team to read.
The classification logic in this SKILL and the state machine in `build-status-tab` should be kept in sync —
if you find them diverging, that's a bug to fix.

### Step 7 — Hand off

Before surfacing, confirm the direction ledger accounts for **every** in-flight thread *and* every open PR / Gerrit change with a definite "awaiting us" / "awaiting them" verdict,
and that the UNRESOLVED bucket is empty.
If it isn't, the sweep is **not finished** —
go back and drain the missing thread/message pages (Step 1) or do the outstanding manual Gerrit check (Step 3) first.
A sweep is complete only when who-waits-for-whom is clear for every thread and every open PR/change;
"I didn't get to page 2" or "that Gerrit host wasn't reachable" is an open action, not a closed sweep.

Surface the action list and stop.
The user picks an item and invokes the matching SKILL by name.
Do not chain into a SKILL unbidden.

## Cross-references — which SKILL handles each next action

| Next action | Downstream SKILL |
| --- | --- |
| Run gates 1–4 on a new request | `glasswing-scan-response` |
| Reply to a PMC's follow-up message | `glasswing-scan-response` |
| Run pre-flight model assessment for a PMC | `glasswing-model-verify` |
| Draft email response with model gaps | `glasswing-model-verify` (Templates 4 or 5) |
| Open AGENTS.md/SECURITY.md PR | `glasswing-model-verify` (Templates 1–3) |
| Write any cell on the PMCs sheet | `glasswing-scan-update` (apply) |
| Add a new column / rename / insert | `glasswing-scan-update` (add-columns / insert-column / rename-column) |
| Save a canned response | `glasswing-scan-update` (append-canned) |
| Refresh the Status sheet | `glasswing-scan-update` (build-status-tab) |
| Submit per-repo scan-request forms + draft PMC notification | `glasswing-scan-submit` |
| Sanity-check Mirko's report + forward verbatim to PMC | `glasswing-scan-forward` |
| Generate a status rollup | `glasswing-scan-status` |
| Produce a fresh threat-model draft for a PMC | `threat-model-producer` |

## Style notes

- **One screen** of action list.
  If the list is too long to scan in one sitting, group by status and collapse long sections to counts ("12 PMCs awaiting reply — list on request").
- **Cite sources concretely.** A thread id, a sheet row number, a PR URL.
  "PMC says X" without citation can be wrong; with citation it's verifiable.
- **Don't editorialize on PMC priorities.** Surface the state;
  let the user decide which PMC to attend to.
  The sweep doesn't know that Logging is the test bed or that Tomcat has more eyes on it.
- **Use the same color/state taxonomy as `build-status- tab`.**
  If the action list says "Tomcat: Pre-flight", the Status sheet should also show Tomcat in the Pre-flight bucket.
  Divergence is a bug.

## Examples of bad sweeps (avoid)

- A sweep that dumps every Gmail thread in the action list.
  Filter out the noise (`+1`s, git pushes, GitHub notifications, MAILER-DAEMON).
  The action list is for things the user must act on.
- A sweep that auto-drafts replies as part of the survey.
  Per hard rule 1 — this SKILL is read-only.
  The user picks an item and then invokes the response SKILL.
- A sweep that omits the GitHub PR check.
  Discoverability PRs we've opened are real state changes;
  a sweep that ignores them produces a "Tomcat is blocked on discoverability PR" line when in fact the PR landed three days ago.
- A sweep that uses stale memory for the spreadsheet.
  Always read fresh — Piotr may have edited columns or rows between sweeps.
- A sweep that doesn't refresh the Status sheet at the end.
  The Status sheet is the team's shared view;
  a sweep that only reports in chat leaves the rest of the team out of date.
- A sweep that reads "who replied last" off the thread-search snippet instead of `get_thread` (hard rule 7).
  For any thread past the ~5-message search cap the snippet's last message is stale —
  this both buries PMC replies we owe answers to and invents "awaiting us" items we already answered.
  Resolve the latest message per-thread with `get_thread` (MINIMAL),
  cached against last sweep so it stays cheap.

## Provenance

This SKILL was added to formalize the periodic-sweep pattern Jarek has been running by hand:
re-fetch Gmail, re-fetch the sheet, re-check each PR's state,
classify per PMC, then drive the next batch of work.
Codifying it as a SKILL makes the classification deterministic,
lets other Security-team members run the same sweep,
and gives the team a shared vocabulary for pipeline state across the PMC cohort.
