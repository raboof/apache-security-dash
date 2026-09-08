---
name: frontier-model-preparation-run
description: >-
  Umbrella orchestration SKILL for the Frontier Model Preparation scan pipeline —
  the periodic "run a full sweep across the program" entrypoint.
  Performs a read-only sweep across all four input surfaces (Gmail programme threads — subject-prefixed `[GLASSWING]` or `[ASF CLAUDE SECURITY SCAN]`, both live — the Mythos tracker spreadsheet's PMCs sheet, GitHub PRs the Security team has opened on PMC repos, ASF Tooling scan results landing in the `apache/tooling-agents-private` archive) and produces a single action list — per-PMC, classified by where each engagement sits in the pipeline (new request, awaiting PMC reply, model-verify pending, ready to submit, submitted to ASF Tooling, results back, forwarded, etc.).
  The user picks what to act on;
  this SKILL never writes —
  it hands off to frontier-model-preparation-response, frontier-model-preparation-model-verify, frontier-model-preparation-update, frontier-model-preparation-submit, frontier-model-preparation-forward, or frontier-model-preparation-status for actual work.
  Use this at the start of a work session,
  when picking back up after time away,
  or whenever Jarek says "where do we stand on Frontier Model Preparation", "run a full scan sweep", or "what's pending across the program".
---

# frontier-model-preparation-run SKILL

The umbrella orchestration for the Frontier Model Preparation scan-outreach pipeline.
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
                                                                              | ASF Tooling       |
                                                                              +---------+---------+
                                                                                        | scan results
                                                                                        v
+--------+  +---------+  +---------+  +-----------+  +-----------+  +-----------+  +-----------+  +-----------+
|[GLASS- |->|Pre-     |->|Pitch    |->|PMC reply  |->|Operator   |->|Submitted  |->|Sanity-    |->|Archived + |
| WING]  |  |flight   |  |sent to  |  |(expedite  |  |gate       |  |ASF Tooling|  |checked    |  |Forwarded  |
| request|  |(model + |  |PMC      |  | list /    |  |(explicit  |  |(Tracker + |  |(catastr.  |  |to PMC     |
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
| bers reg- |    | written to    |    | ASF Tooling to|    | Recorded in   |
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

The `Archived` step is a synchronous part of `frontier-model-preparation-forward`:
the SKILL sanity-checks ASF Tooling's report (catching catastrophic generation errors — wrong project, wrong/stale model, truncation, missing repos),
commits ASF Tooling's markdown + `.json` raw + `.notes.md` sanity-check log to [`scans/<project>/<repo>/`](../../../scans/README.md),
then drafts the forwarding email (ASF Tooling findings verbatim, no per-finding triage) citing the archive filename.
The single user-approval gates both the commit and the email; see [`scans/README.md`](../../../scans/README.md) for the path / metadata / confidentiality spec.

Each stage has its own SKILL responsible for the work that moves an engagement through it.
This SKILL doesn't replicate that logic —
it just figures out which stage each engagement is *in* and surfaces what to do next.

## Program timeline — the pause was technical; restart is ASF Tooling's to announce (read this)

The program has run through several timeline shapes. History: a *"no rush"* footing through late May 2026 (an early **external-relay arrangement** — a third party ran the scan off a Google-Form submission and emailed the report back; since superseded by the internal ASF Tooling path); a **27 May 2026 donation of $1M in Mythos credits** briefly added a **direct-internal path** under a 30 June cliff; that cliff was **lifted** while the ASF sat in Anthropic's provisioning queue (Mythos Preview → Mythos 5 transition). The ASF then executed a **Claude Mythos 5** work order (2026-06-30) with a nominal 1–31 July 2026 credit window.

**Correction (2026-07-30) — earlier revisions of this section were wrong, in a way that would make the sweep tell PMCs something untrue.**
This SKILL previously asserted the ASF was "officially provisioned as of 2026-07-01" and that Mythos 5 scans were running. They were not. Per **Dave Fisher (wave@, VP Tooling)** on the internal `Glasswing scan queue status` thread, 2026-07-29:

- Scans — including ours — were **blocked for technical reasons**, and **Glasswing was "unusable until we have 1st party provisioning."**
- The ASF is being **de-provisioned from AWS Bedrock and migrated to Anthropic 1P directly**.
- wave@ declared the pause over on **2026-07-30 07:51Z**: *"We are now unblocked."* The **restart announcement is Tooling's to make, not ours.**

**Credit window — a rolling monthly renewal, not a cliff.** Per **Sally Khudairi (sk@)**, 2026-07-29, marked confidential: a new order form was executed at the **$1M** level — nominal expiry **31 August 2026**, but **access through June 2027**, with **a new order form signed monthly**. So there is no date to nudge against, and there never was. Treat any date-based urgency as **unsourced** until the Tooling team states it.

**Scope boundary — Security prepares, Tooling scans.** Per **Mark J Cox (mjc@, VP Security)**, 2026-07-30: *"we agreed to let Jarek help projects with their Threat Models … Our position has always been that security do not run code scanning."* Threat-model preparation, model verification, discoverability wiring, outreach, queue management, the pre-forward sanity check and forwarding are in remit; **running scans is not**. Never describe the Security team as running or owning scans in PMC-facing or foundation-facing text. Note the operator does currently *send* the reports, which is why Security has a legitimate stake in vetting what goes out (akm@'s proposal: Security + Tooling jointly confirm Critical/High/Medium findings are actionable, and tell PMCs that Lows are defense-in-depth).

**NDA:** Glasswing's methods / agents / skills are under NDA and must not be shared.

Internal scanning is run by **VP Tooling + Infra + Security**: **Andrew Musselman (akm@apache.org)** is the **technical contact for the scans**, while the **Security team (Jarek Potiuk) continues to manage the scan queue** — PMC outreach, pre-flight / model verification, and criticality-ordering — from the Security side.
Route technical scan-execution questions to Andrew; queue / pre-flight / model-verification / outreach stays with the Security team.

What this changes for *this* SKILL is: **no deadline-driven urgency.**
The priority is still to get every signed-up PMC **pre-flight-complete (model verified + discoverable on the default branch)**, because that is what puts a project into the queue at its rank — but the lever is *readiness*, not a clock.
Engagements that still owe us prerequisites — `awaiting-pmc-reply`, `blocked-on-discoverability`, `blocked-on-gate-2`, `model-verify-pending`, `pmc-pitch-replied-awaiting-operator-decision`, or an open model PR awaiting PMC merge — are ordinary nudge candidates on the 14-day rule below, framed as "this is the one thing between you and the queue", never as "before the window closes".
Ordering within that push is still **readiness + OSS Criticality Score**, drawn from the pre-flight-cleared **Scan Queue** (see `build-status-tab`).
The `Scan Queue` tab is the submission manifest, **one row per submitted repo × branch/tag** (the Repositories sheet's `Branches/tags to scan` cell is comma-split; blank = a single default-branch row), criticality-ranked. Each row carries auto-derived identity (`Report recipients`, `Branch/tag`, `Model discussion (ponymail)`, `When ready`) plus a per-scan tracking block — `When scanned` · `Model send thread (ponymail)` · `When report sent` · `Commit hash` — that **repeats as `Scan 1` … `Scan 5`** (alternating yellow blocks). Those per-scan columns have no automated source yet, so they stay blank, carried over across refreshes keyed by (Repo, Branch/tag) until their automation lands. Continuation branch-rows of a repo are greyed; **a row with any scan data is never dropped** (retained + flagged if it leaves the current spec).
The signed-up PMCs keep their spot; the nudge is about landing prerequisites in time, not re-qualifying them.

Internal only — keep OUT of PMC-facing text (Hard Rule 5 / the response SKILL): the program's cost mechanics — the $1M figure, the per-MTok credit pricing, and the seat/provisioning mechanics. (ASF Tooling as the runner is fine to name.)
PMC-facing framing is "we're provisioned on the scanning model and scans are running in the sequence of submission — finalizing / merging your threat model is the one thing between your project and the queue."
Do **not** promise a cycle, a window, or a turnaround date; if a PMC asks how long, say scans run in the sequence of submission and that you'd rather not give a date you can't stand behind.
A gentle-but-firm nudge canned response (topic `deadline`) exists for stalled PMCs — despite the topic name it is framed around readiness and submission order, with no date claim, and should stay that way.

## When to invoke

- **Start of a work session.** "Where do we stand on Frontier Model Preparation?" —
  run a full sweep first so the rest of the session is grounded in current state,
  not in what was true last time we worked.
- **After time away.** Multiple days of accumulated email + spreadsheet edits + open PRs need cross-referencing before any per-PMC work makes sense.
- **Before sending a status update.** Foundation-level or Security-team rollup emails should be sourced from the Status sheet that this SKILL refreshes.
- Whenever Jarek says explicit triggers: "sync up the scan tracker", "what's pending across the program", "do a full Frontier Model Preparation sweep", "are there new requests?", or anything similarly broad.

Skip when the user is already mid-task on a specific PMC (don't sweep when they say "draft a reply to Mark" —
go straight to `frontier-model-preparation-response`).

## Hard rules (do not skip)

1. **Read-only at the umbrella level.** This SKILL never writes to Gmail, the spreadsheet, or GitHub.
   It surveys, classifies, and surfaces.
   When something needs writing, the user invokes the matching per-task SKILL.

2. **Surface, don't auto-decide.** When multiple PMCs are pending the same action, *list them* and let the user pick where to start.
   Do not silently batch.

3. **Cite the source of every conclusion.** If the sweep says "Tomcat is waiting on Mark to choose a path for the 3 missing repos", cite the Gmail thread id (or subject) and the spreadsheet row that supports that conclusion.
   Stale reads happen; the user verifies.

4. **Don't replicate per-task SKILL logic.** Don't decide what reply to draft —
   that's `frontier-model-preparation-response`'s job.
   Don't decide model remediation — that's `frontier-model-preparation-model-verify`.
   This SKILL's output is a list of "needs X; SKILL Y handles it";
   the per-task SKILL does the actual decision-making.

5. **Refresh the Status sheet at the end** by invoking `frontier-model-preparation-update`'s `build-status-tab` subcommand.
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
   It is tempting to shortcut the per-thread resolution with `(subject:GLASSWING OR subject:"ASF CLAUDE SECURITY SCAN") is:unread`,
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

**Programme subject prefixes — single source of truth.**
The programme has used **two** subject prefixes over its life and **both are live**:
older engagements sit under `[GLASSWING]`, newer ones under `[ASF CLAUDE SECURITY SCAN]`.
A sweep that searches only one prefix silently drops every engagement filed under the other —
and drops it *invisibly*, because the sweep still returns a full-looking action list.
Every Gmail query in this SKILL — the thread search below, the changed-set search in the cache step, draft enumeration, and the `is:unread` hints — uses this same set:

```
subject:GLASSWING OR subject:"ASF CLAUDE SECURITY SCAN"
```

**Quote the multi-word prefix — the quotes are load-bearing.**
Gmail's `subject:` operator binds to a single token,
so an unquoted `subject:ASF CLAUDE SECURITY SCAN` parses as `subject:ASF` **AND** a free-text body search for `CLAUDE SECURITY SCAN`.
That returns a wrong set that looks entirely plausible — some real threads, plus unrelated mail that merely mentions the words.
Keep the double quotes in every query.
Gmail matching is case-insensitive and tokenises on `[`/`]`, so one spelling per prefix is enough and the brackets need not appear in the query.

Search Gmail for the prefix set above.

**Paginate to exhaustion — never stop at the first page.**
`mcp__claude_ai_Gmail__search_threads` caps each page at `pageSize=50` and returns a `nextPageToken` whenever more threads exist.
Loop: issue the search,
accumulate the returned thread IDs,
and if the response carries a `nextPageToken`, re-issue with that token —
repeat until the token is empty.
After any page returns 50 results, **assume there is a next page until the empty-token response proves otherwise**.
The program already exceeds 100 FRONTIER MODEL PREPARATION threads (≈106 across 3 pages as of 2026-06-01, and that count predates the `[ASF CLAUDE SECURITY SCAN]` prefix — the combined set is larger and needs more pages, not fewer),
so a single 50-thread page is a fraction of the set.
A sweep that classifies only the first page produces *complete spreadsheet-derived state but incomplete email-direction state* —
PMCs whose thread sorts onto page 2+ look quiet when they may in fact be awaiting our reply (the 2026-06-01 sweep missed APISIX, Thrift, Hop, Directory, and Grails this way).
Cross-check the full accumulated thread set against every `Scan Requested = Yes` row in the spreadsheet so no in-flight PMC is left only-sheet-classified.

For each thread (across all pages), classify into one of these buckets:

| Bucket | Signal |
| --- | --- |
| **New programme request** | Subject matches `[GLASSWING] <PMC>:` **or** `[ASF CLAUDE SECURITY SCAN] <PMC>:` and the PMC isn't yet in the spreadsheet as `Scan Requested = Yes`. Both prefixes mean the same thing for classification — do not treat the newer prefix as a different kind of engagement. |
| **Reply on existing request thread** | We've already replied at least once (`SENT` label present in thread); a *newer* message exists from the PMC after our last reply. |
| **Reply we haven't acted on** | Same as above but our last action (Gmail draft or sheet write) is older than the most recent PMC message. |
| **Pure announcement-thread chatter** | A reply to the original `[IMPORTANT][SECURITY]` announcement that isn't substantive (just "+1", "interesting", etc.). Log and skip. |
| **Bot / automated** | Git push notifications, PR review notifications, MAILER-DAEMON, etc. Filter out — don't include in the action list. |
| **ASF Tooling correspondence** | Scan results / queue updates from ASF Tooling; they land in the `apache/tooling-agents-private` archive, and any legacy relay email is back-compat — subject containing scan-request acknowledgement, queue position, or scan result delivery. |

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
   Shape: `{ "last_sweep": "<ISO8601>", "prefixes": ["GLASSWING", "ASF CLAUDE SECURITY SCAN"], "threads": { "<tid>": <record above> } }`.
2. **Load** the cache at sweep start (empty `{}` on first run).
2b. **Compare the cache's `prefixes` against the current prefix set (Step 1). If they differ — or the field is absent — discard the incremental path for this sweep and do a cold full enumeration** (the unbounded thread search at the top of Step 1, paginated to exhaustion), then write the current prefix set into the cache.
   **This is mandatory and it is not optional tidying.** The changed-set search in the next step is bounded by `after:<last_sweep>`, so it only ever returns threads that gained a message *recently*. A prefix newly added to the sweep has threads that are **older than `last_sweep`** and have not moved since; the incremental search will never return them, the cache has no entry for them, and they will be missing from the action list on every subsequent sweep — permanently, and with no error. A cold pass on the first sweep after a prefix change is the only thing that pulls them in. The same applies if a prefix is ever removed or renamed.
3. **Find the changed set** with a search: `mcp__claude_ai_Gmail__search_threads` with `query="(subject:GLASSWING OR subject:\"ASF CLAUDE SECURITY SCAN\") after:YYYY/MM/DD"`, where the date is `last_sweep` minus a 1-day safety buffer.
   **Parenthesise the prefix alternation.** Gmail binds `OR` tighter than the implicit `AND` with `after:`, so an unparenthesised `subject:GLASSWING OR subject:"ASF CLAUDE SECURITY SCAN" after:...` applies the date filter to only the second branch and returns the *entire* `[GLASSWING]` history on every sweep — slow, and it masks the bug because the result set looks generously large rather than short.
   Every `thread_id` it returns is a thread that gained ≥1 message since the last sweep (new PMC requests show up here too).
   **This search paginates too** —
   if the response carries a `nextPageToken`, loop on it until empty (a busy week can exceed 50 changed threads).
   Do not stop at the first page.
   **Never narrow the `after:` date to dodge a large result set.** `resultCountEstimate` is unreliable and often returns the whole-corpus figure (~200+) even for a tight window — that is not a signal to move the date forward. Moving it forward by even one day silently drops that day's replies. This is exactly how the 2026-07-04 sweep missed five same-day PMC replies (Knox, CloudStack, Creadur, Guacamole) to a broadcast sent the prior day: the window was narrowed from `after:07/02` to `after:07/03` because `07/02` "looked like it returned the whole corpus," and the 07-02 afternoon replies vanished. The fix is always to keep the `last_sweep − 1d` window and **paginate**, never to shrink it. Broadcast days are the highest-risk case: one outbound blast to N PMCs produces a burst of same-day inbound replies that all sort onto the broadcast's date.
4. **Refresh only the changed set + any thread absent from the cache:**
   call `get_thread` (MINIMAL) on each, rebuild its record, and overwrite the cache entry.
   Threads in the cache but *not* in the changed set are unchanged —
   reuse their cached record verbatim (no `get_thread`).
5. **Save** the cache with `last_sweep` set to the start time of this sweep (pass the timestamp in;
   do not call `Date.now()` inside a helper that must stay deterministic).

**The working set for the rest of the sweep is the whole cache — every record in `threads` — not the changed set.**
The changed set exists only to decide *which records need re-reading*;
once step 4 has refreshed them, the cache holds a current verdict for every thread the programme has ever seen,
and that full map is what Step 4's classification, Step 5's direction ledger and Step 6.5's unresolved-asks pass all read from.

This is the single easiest way to produce a confident, wrong sweep,
and it fails in the direction that hides work rather than inventing it.
A thread that went quiet *before* the `after:` window — a PMC reply nobody answered three weeks ago — is by construction absent from the changed set,
so a ledger built from the changed set alone silently omits exactly the threads that have been waiting longest.
The 2026-09-07 sweep did this: it reported **4** threads awaiting us when the cache held **41**,
and Guacamole — last message from the PMC on 08-07, cached as `awaiting: us` the whole time — never appeared in the ledger at all
and had been sitting 31 days.
Most of the other 41 were correctly annotated as bare acks with no ask, which is the Step 6.5 distinction and is fine;
the bug is that they were never *considered*, not that they were dismissed.

Two mechanical consequences:

- Iterate `cache["threads"].values()`, never the changed-set list, when building the ledger or the action list.
- The ledger's thread count must equal the number of non-noise records in the cache. Step 7 makes that a completion check.

The cache is a *speed + correctness aid*, never the source of truth —
Gmail and the spreadsheet are.
If a record looks stale, contradictory, or you're about to act on it, re-pull the thread.
The first sweep (cold cache) resolves every active thread once;
every later sweep only re-reads the handful of threads that actually moved.

Note: `get_thread` here is **MINIMAL** — you only need direction, not bodies.
Fetch `FULL_CONTENT` only later, in the per-task SKILL, when you actually draft a reply to a specific thread.

**Draft-folder enumeration** (mandatory — see hard rule 6).
After the thread sweep, call `mcp__claude_ai_Gmail__list_drafts` with `query="subject:GLASSWING OR subject:\"ASF CLAUDE SECURITY SCAN\""` and `pageSize=50` and capture the result as `{thread_id, draft_id, draft_subject}` for each returned row —
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
see `frontier-model-preparation-forward`.)

### Step 2.5 — Archive sweep (new ASF Tooling scans → assess → forward)

ASF Tooling delivers each scan by committing it to the `apache/tooling-agents-private` archive under **`august-scans/<project>/<scan-id>/`** — a **top-level** tree, *not* under `scans/` — where `<scan-id>` is a **UTC timestamp directory**, e.g. `august-scans/activemq/20260811T042551Z/`.

That tree landed 2026-09-08 (`5a485696`, "Adding August scans") and is now where the reports are. It re-drops 228 of the 253 `scans/glasswing/` bundles with the `.pre-stack` patch intermediates removed and two artefacts added — `scan-meta.json` (machine-readable identity; on all 245 bundles) and `PMC-FEEDBACK.md` (collated PMC replies off lists.apache.org; on the 50 that have drawn any) — plus 17 bundles `scans/glasswing/` never had. `scans/glasswing/` was **not** deleted and is still the only home of: `apisix/20260806T183531Z`, `apisix-ingress-controller/20260806T235139Z`, `commons-parent/20260815T193415Z`, `directory-kerby/20260811T042516Z`, `shiro/20260810T152236Z`, `superset/20260807T173517Z`, `superset/20260810T185727Z`, the `tooling-trusted-releases/` bundles, the older `<project>-<YYYY-MM-DD>-<sha>`-named directories, and the `fleet/` coverage analysis. So sweep **both** trees, and where a scan-id appears in both, the `august-scans/` copy wins.

The archive also carries `scans/experiments/` (alternate-model runs, including a `mythos` tree); that is **not** a delivery tree and PMC-facing state must never be sourced from it. This step detects **new** scans and routes each to its next action — pre-forward assessment, then forward — so a freshly-landed scan surfaces in the action list without waiting on an email.

Work against a **local clone at `~/code/tooling-agents-private`** (clone if absent; `git pull --ff-only` on a clean tree otherwise, to pick up the **latest** commits). Reaching the private repo needs the keychain — bypass the sandbox for the fetch, loud banner per the user's rule. (Record the clone path in the `secure-setup-local-paths` memory so later sweeps find it.)

Enumerate every scan-id directory under `august-scans/*/` **and** `scans/glasswing/*/`. Take `<project>` from the directory name. For identity, read **`scan-meta.json`** first — every `august-scans/` bundle has one, and it gives `repo`, `branch`, `commit` and `scanned_utc` as JSON, so no prose parsing. Note its `commit` is the **short** (7-hex) SHA. Fall back to `PROVENANCE.md` — the only identity file in `scans/glasswing/` bundles, and the source of the full 40-hex SHA and the clone date — which is the same file [`frontier-model-preparation-forward`](../frontier-model-preparation-forward/SKILL.md) reads for scan identity. There the commit is a 40-hex SHA whose surrounding prose varies between bundles (`- HEAD:`, `Commit:`, `@ <sha>`), so match the SHA rather than a fixed key. Then classify:

1. **No assessment** under any assessment tree — today `pre-forward-results/mythos/` and `pre-forward-results/glasswing-asvs/`, so check both. Their scan-id shape is `<project>-<YYYY-MM-DD>-<sha>`, which does **not** match the timestamp directory names under `august-scans/` or `scans/glasswing/`, so match on project plus bundle identity (the `scan-meta.json` / `PROVENANCE.md` commit, compared on the short-SHA prefix since `scan-meta.json` carries only 7 hex), never on a shared id string → bucket **`scan-needs-assessment`** → route to `pre-forward-report-preparation`. (Eligible only if the PMC's `Security model verified` is set; if not, it's blocked on model-verify — surface that instead of assessing.)
2. **Assessment exists** → read its `metadata.yml` `sanity_check`:
   - `RETURNED` → bucket **`scan-returned`** → escalate to ASF Tooling; do **not** forward a broken scan.
   - `PASS` / `PASS-with-notes` → cross-reference the PMC's tracker row:
     - `Forwarded scan to PMC` **blank** → bucket **`scan-needs-forward`** → route to `frontier-model-preparation-forward`.
     - `Forwarded scan to PMC` **set** → already delivered; no action (confirm the scan-id is recorded in the row's `Notes` / ponymail cell).

**A zero-bundle result means the path is wrong, not that the archive is empty — stop and re-derive it.** The delivery tree has now been renamed twice (`scans/mythos/` → `scans/glasswing/` → top-level `august-scans/`, the last on 2026-09-08), and enumerating a directory that does not exist returns an empty list rather than an error, so the sweep reports "no new scans" with total confidence and no warning. This cost the 2026-08-30 sweep a full pass. Sanity-check any zero against `ls august-scans | wc -l` (245 bundles as of 2026-09-08) and `ls scans/glasswing | wc -l` before believing it. Before concluding the tree moved again, run `git ls-tree origin/main --name-only` at the **archive root** and look for a new top-level scan tree — that is how `august-scans/` was found; it is not under `scans/`. **Also check which branch the clone is on** (`git status`): it is a working checkout, not a read-only mirror, and it sat on the feature branch `report-quality-analysis` on 2026-08-30 — `git pull --ff-only` on a feature branch silently leaves you reading something other than `main`.

Write the enumeration to a file and post-process with `jq`/`awk` **from a file** (never inline — shell-safety note above). A scan-id whose `project` is not a `Scan Requested = Yes` PMC is surfaced as an anomaly, never silently dropped. This is the trigger path end-to-end: new scan → `scan-needs-assessment`; assessed PASS → `scan-needs-forward` on the next sweep.

### Step 3 — Open-PR + change sweep (state + attention triage)

This pass must cover **every open PR/change the operator has authored**, not only the ones recorded on the tracker —
the tracker's `PR/Issues` cells lag reality (model and discoverability PRs get opened mid-discussion and added to the sheet later, if at all;
the 2026-06 audit found several operator-opened model PRs — ozone, santuario, solr, creadur — that no tracker cell pointed at).
Build the candidate set from **two** sources and dedupe:

1. **Tracker-listed** — every URL in a non-empty `PR/Issues` cell.
2. **Author-discovered (exhaustive)** — query GitHub for *all* open PRs authored by the operator, paginating to exhaustion:

   ```
   gh search prs --author=@me --state=open --limit 100 \
     --json url,repository,title,updatedAt
   ```

   `gh search` caps at 100 results;
   if the result hits the cap, re-query with date-window narrowing (`--updated <range>`) until every window is drained.
   Do **not** restrict to FRONTIER MODEL PREPARATION-spawned or `asf-security/*` branches —
   any open PR waiting on us counts,
   including ones opened from a past discussion that never made it onto the sheet.
**Do not sweep Gerrit.** Earlier revisions asked for a pass over Apache-adjacent Gerrit hosts (e.g. `gerrit.cloudera.org` for Kudu). That work is **done and closed** (operator, 2026-08-30); the host is not reachable from this environment anyway, so the check only ever produced a standing manual-check item that the operator had already actioned. Do not add it to the candidate set, and do not surface it as unresolved.

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
- Note: a merged AGENTS.md / model PR means we can re-run `frontier-model-preparation-model-verify`'s discoverability check on that repo;
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

**This verdict MUST come from actually fetching each open PR's `comments` + `reviews` arrays — never from the email threads, never from `reviewDecision` alone, and never skipped because the fetch is slow.**
`reviewDecision` staying `REVIEW_REQUIRED` / empty does **not** mean "no maintainer input": a `COMMENTED` review or a plain issue-comment carries questions and scope pushback *without* changing `reviewDecision` or setting `CHANGES_REQUESTED`.
The 2026-07-05 sweep is the cautionary tale: Maven `#12421` (elharo's scope review — "these plugins are missing from the table; are non-plugins in scope?") and CloudStack `#13293` (a maintainer's "how is this to be reviewed / is it ready to merge?") were **both** `COMMENTED` / issue-comments with **no** `CHANGES_REQUESTED` — so a `reviewDecision`-only read called them clean, and *deriving the flag from the email threads* (the shortcut taken when the comment fetch timed out) missed them too. Both were genuine unanswered questions sitting on the operator, found only on a dedicated re-run. Fetch the threads; compare recency; do not shortcut.

**Mechanical recipe (the fetch that neither times out nor silently no-ops):**
- **One event-pull call per PR** — pass the repo through the env so `env.REPO` labels the row (inlining `"$repo"` into the `--jq` string breaks the filter):
  `REPO=apache/<repo> gh pr view <n> --repo apache/<repo> --json number,author,commits,comments,reviews --jq '{repo:env.REPO,num:.number,last_commit:(.commits|max_by(.committedDate)|.committedDate),comments:[.comments[]|{a:.author.login,at:.createdAt,body:(.body|.[0:240])}],reviews:[.reviews[]|{a:.author.login,st:.state,at:.submittedAt,body:(.body|.[0:240])}]}'`
- **Sandbox bypass is required.** `comments` / `reviews` / `statusCheckRollup` / `reviewDecision` all traverse GitHub's **GraphQL** path, which needs authenticated `gh`; under the sandbox the keyring is unreadable and every call **401s**. Run this pass with `dangerouslyDisableSandbox: true` (loud banner per user rule). Keep `statusCheckRollup` (the slow field on big repos) in a **separate lean call** from the comments/reviews call so one heavy field can't stall the loop.
- **Loop from a `bash` array in a script file** (`PRS=( ... ); for p in "${PRS[@]}"; do …; done`) run with `bash script.sh` — **never** an inline `for p in $LIST` in the Bash tool, whose shell is `zsh`, which does **not** word-split an unquoted variable and silently mangles every iteration (symptom: 0 lines written). For a large cohort use `run_in_background: true` so it can't block the sweep.
- **Compare in a Python analyzer** (write it to a file per the shell-safety note): flag any PR whose latest non-us, non-bot `comment`/`review` timestamp is newer than our latest `comment`/`review`/`commit`. Treat `potiuk` as us; treat `*[bot]` / `asfgit` / `github-actions` / `apache-*` / CI apps as bots.
- **A `COMMENTED` review with an empty top-level body means inline line-comments** (elharo's shape). Pull them with `gh api "repos/apache/<repo>/pulls/<n>/comments"` to see the actual questions.

A PR can carry several flags (e.g. `pr-needs-reply` + `pr-ci-failing`).
Collect, per flagged PR:
PMC, `owner/repo#num`, the flags, the commenter + a one-line gist of what they want, and `updatedAt`.
These feed the `prs-needing-attention` section of the action list (Step 5) and are **the Security team's, not the PMC's, to clear** —
route each to `frontier-model-preparation-model-verify` (for model-PR review threads) or a direct reply/rebase/CI-fix,
gated on operator approval per that SKILL's draft-and-confirm rules.
The `pr-approved-awaiting-merge` set is surfaced separately as merge-nudge candidates (the merge itself is the PMC's call).

**Merged-PR reconciliation — the `enrollable-not-enrolled` pass (run on every sweep; do NOT skip because the PR is closed).**
Everything above triages **open** PRs. That leaves a blind spot with real cost: a discoverability PR that **merges quietly** disappears from every open-PR query at the same moment it becomes the thing that makes a repo scannable. Nobody is waiting on us, no thread moves, no flag fires — and the repo sits enrollable and un-enrolled indefinitely. On 2026-07-30 this pass found `apache/solr-operator` (merged 2026-07-17, 13 days idle) and `apache/opendal` (discoverable since 2026-07-02, **28 days** idle, and the only non-blank-criticality repo in its PMC's scope). Neither was visible to any check this SKILL previously ran.

For every PMC with `Scan Requested = Yes`, reconcile **merged** state against enrolment:

1. Take every repo in the PMC's `Repositories requested` cell.
2. Subtract the repos already listed in `Repositories submitted`.
3. For each remainder, check discoverability **on the default branch** (Check A — `AGENTS.md` → `SECURITY.md` → model). The default branch is the only branch a scan sees; a chain that exists only on a PR branch does not count.
4. Any repo that passes is **`enrollable-not-enrolled`** → surface it with its OSSF Criticality Score.

Two traps this pass must avoid, both hit on 2026-07-30:

- **Bare autolinks.** `SECURITY.md` may point at the model as `<https://example/model>` rather than `[label](url)`. A markdown-link-only grep false-negatives it and reports a passing repo as FAIL (this happened to `apache/avro-rs`). Accept **both** forms.
- **Criticality-weighted judgement, not a raw count.** "3 of 4 repos still failing" is not a reason to hold the PMC if the one that passes is the only repo with a non-blank Criticality Score. Blank score = not "active" by the same definition the scope gate uses, so a phase-1 enrolment of the scored repo is usually right and holding it is usually wrong. Surface the scores and let the operator decide; never present a bare pass/fail ratio.

This pass is **read-only and surfaces only** — enrolment stays operator-gated via `frontier-model-preparation-submit` (it changes what gets scanned and triggers a PMC notification). Also correct any tracker `PR/Issues` cell still recording a merged PR as `OPEN`; those cells go stale silently and are what makes this blind spot invisible on a spreadsheet read.

This pass is **wide** (every open PR across every in-flight PMC),
so for a large cohort fan it out —
but it runs on **every** sweep;
a PR left waiting on us for days is exactly the kind of state this umbrella exists to surface.

### Step 4 — Cross-reference and classify

For each `Scan Requested = Yes` PMC, produce a single classification:

| Classification | Definition | Next action |
| --- | --- | --- |
| `new-request-untouched` | Inbound `[GLASSWING]` **or** `[ASF CLAUDE SECURITY SCAN]` request exists; no row in the sheet for that PMC yet, or the row has no `Request date`. | Run `frontier-model-preparation-response` gates 1–4. |
| `pmc-reply-awaiting-action` | PMC has sent a newer message than our last reply / sheet write. | Read the new message; run `frontier-model-preparation-response` if it raises questions; run `frontier-model-preparation-model-verify` if they nominated a model; run `frontier-model-preparation-update` if it confirms scope / dates. |
| `draft-pending-manual-send` | A Gmail draft exists in Drafts for this PMC's thread that the operator hasn't sent yet. **Detection signal: `list_drafts` (Step 1) returned a draft on this thread — not session memory of having created one.** | Surface for operator action — the operator reviews in the Gmail UI and clicks Send. No SKILL re-invocation needed. |
| `awaiting-pmc-reply` | We've replied last; nothing new from PMC. **Confirm via the thread's latest message having a `SENT` label, and confirm no draft is pending in `list_drafts` output.** | Wait; nothing to do unless time-overdue (see below). |
| `model-verify-pending` | Model nominated but not yet assessed for completeness + per-repo discoverability. | Run `frontier-model-preparation-model-verify`. |
| `pre-flight-passed-pitch-not-sent` | `Security model verified` set; `Expedite Claude OSS Requests` cell empty; no pre-flight-pass OSS-expedite pitch has gone out yet on the PMC thread. | Run `frontier-model-preparation-response`'s pre-flight-pass template (OSS-expedite pitch + ready-to-scan notification). Does **not** trigger `frontier-model-preparation-submit` directly — `submit` is now operator-gated. |
| `pre-flight-passed-awaiting-pmc-pitch-reply` | `Security model verified` set; pre-flight-pass pitch sent but PMC hasn't replied yet; `Expedite Claude OSS Requests` still empty. | Wait. No action unless overdue (>14d). |
| `pmc-pitch-replied-awaiting-operator-decision` | `Expedite Claude OSS Requests` cell populated (with addresses or the literal string `none`); `Date scan requested` still blank. PMC has chosen path(s); waiting for the Security team operator to explicitly say "submit X" (or to defer further). | Surface for operator decision. `frontier-model-preparation-submit` is operator-gated — never auto-fire on this state. |
| `submitted-awaiting-asf-tooling` | `Date scan requested` set; `Date scan received` blank. | Wait; surface if > 14 days. |
| `scan-needs-assessment` | A scan bundle exists at `august-scans/<project>/<scan-id>/` (or the legacy `scans/glasswing/<project>/<scan-id>/`) in the archive but has **no** matching assessment under `pre-forward-results/` (either tree) (detected in Step 2.5). The pre-forward assessment (sanity check + dispositions) hasn't been produced yet. | Run `pre-forward-report-preparation` (eligible only if the PMC's `Security model verified` is set; else surface as blocked-on-model-verify). |
| `scan-needs-forward` | The scan has an assessment with `sanity_check: PASS` / `PASS-with-notes`, but the PMC row's `Forwarded scan to PMC` is blank (Step 2.5). Ready to deliver. | Run `frontier-model-preparation-forward` (attaches the scan `.zip` + assessment `.md`, drafts the email, records the tracker + ponymail permalink). |
| `scan-returned` | The scan's assessment recorded `sanity_check: RETURNED` (a broken scan — wrong project / stale model / truncation / cross-PMC leak). | Escalate to ASF Tooling for a re-run; do **not** forward. |
| `enrollable-not-enrolled` | A repo in `Repositories requested` passes Check A on its **default branch** but is absent from `Repositories submitted` (detected by the merged-PR reconciliation in Step 3). Usually caused by a discoverability PR merging quietly — it vanishes from open-PR queries exactly when it becomes enrollable. | Surface with the repo's OSSF Criticality Score and how long it has been enrollable. Operator decides; on go-ahead, `frontier-model-preparation-submit` for that repo (phase-1 subset is fine — see hard rule 6 there). Never auto-enrol. |
| `archived-not-forwarded` | An archive commit exists under `scans/<project>/<repo>/` for this PMC but `Forwarded scan to PMC` is still blank. Process bug (the email should have been drafted at the same time). Detection signal: `git log --grep="^\[scan\] <project>/"` returns a commit newer than the sheet's `Forwarded scan to PMC` date. | Surface for manual intervention; re-run `frontier-model-preparation-forward` from step 7 (draft email) using the existing archive entry. |
| `forwarded-closed` | `Forwarded scan to PMC` set **and** the corresponding archive commit exists in `scans/`. | Done. Move to "Completed" section of report. |
| `blocked-on-discoverability` | Some repos in `Repositories requested` lack `AGENTS.md`; PMC needs to fix or we PR. | Surface; await PMC decision on path. |
| `blocked-on-gate-2` | Request came from non-`@apache.org` address and no `@apache.org` anchor stated. | Wait for PMC reply confirming Apache identity. |
| `asf-tooling-correspondence` | Scan-results / queue update from ASF Tooling on a queued / submitted scan (from the `apache/tooling-agents-private` archive, or a legacy relay email). | Read the update; possibly forward to the PMC; update sheet. |

The "time-overdue" rule: any engagement in `awaiting-pmc-reply` or `submitted-awaiting-asf-tooling` for more than 14 days gets flagged for a nudge.
**There is no cliff to nudge against** (see "Program timeline" above — the credit arrangement is a rolling monthly renewal running through June 2027, and any change to it is ASF Tooling's to announce), so the nudge is the ordinary readiness kind: land the prerequisite because it is what puts the PMC into the queue, not because a clock is running.
Any PMC that still owes *us* something before it can be queued —
`awaiting-pmc-reply`, `blocked-on-discoverability`, `blocked-on-gate-2`, `model-verify-pending`, or `pmc-pitch-replied-awaiting-operator-decision` —
and has been quiet for more than ~7–14 days is a nudge candidate,
because clearing those items is what puts the PMC *into* the criticality-ordered queue at its rank.
Don't draft the nudge automatically;
surface it for the user and point at the `deadline`-topic canned response (gentle-but-firm, already reframed around the queue) for these stalled PMCs.

### Step 5 — Produce the action list

Output format:

```
# Frontier Model Preparation pipeline sweep — <YYYY-MM-DD>

## New since last sweep
- <new requests / new PMC replies> with thread refs

## Ready to act on (per stage)

### draft-pending-manual-send (N)
- <PMC> — draft <draft_id>; on thread <thread_id>. Next:
  operator reviews in Gmail UI and clicks Send. **Listed
  here only if `list_drafts` returned the draft in this
  sweep — never from session memory.**

### new-request-untouched (N)
- <PMC> — <thread id> — next: frontier-model-preparation-response

### pmc-reply-awaiting-action (N)
- <PMC> — <thread id>, latest from <sender> @ <date>; key
  content: <one-line summary>. Next: <which SKILL>.

### model-verify-pending (N)
- <PMC> — model: <URL or "missing">. Repos: <count>.
  Next: frontier-model-preparation-model-verify.

### pre-flight-passed-pitch-not-sent (N)
- <PMC> — verified <date>; <repo count> repos in scope.
  Next: frontier-model-preparation-response's pre-flight-pass template
  (OSS-expedite pitch + ready-to-scan notification).

### pre-flight-passed-awaiting-pmc-pitch-reply (N)
- <PMC> — pitch sent <date>; awaiting PMC reply on
  expedite-account list. No action unless overdue.

### pmc-pitch-replied-awaiting-operator-decision (N)
- <PMC> — verified <date>; expedite list:
  <N addresses / "none" / "empty">; awaiting operator
  decision on whether to submit. Next: operator
  says "submit X" → then frontier-model-preparation-submit
  (enroll in the tracker: set Date scan requested +
  Repositories submitted, + PMC notification email).

### scan-needs-assessment (N)   [new scan in the archive — from Step 2.5]
- <PMC> — scan <scan-id> (repo <repo>, <scan_date>); no
  assessment yet. Next: pre-forward-report-preparation (if Security model
  verified; else blocked-on-model-verify).

### scan-needs-forward (N)   [assessed PASS, ready to deliver — from Step 2.5]
- <PMC> — scan <scan-id>; assessment PASS (<VALID> VALID /
  <hardening> hardening). Next: frontier-model-preparation-forward
  (attach scan .zip + assessment .md, draft to designated recipients).

### scan-returned (N)   [broken scan — from Step 2.5]
- <PMC> — scan <scan-id>; assessment verdict RETURNED (<reason>).
  Next: escalate to ASF Tooling for a re-run; do not forward.

### blocked-on-discoverability (N)
- <PMC> — <N> of <M> repos have AGENTS.md; awaiting PMC
  reply on path. Last followed up <date>.

### blocked-on-gate-2 (N)
- <PMC> — last reply from non-apache.org; we asked for
  anchor <date>.

### asf-tooling-correspondence (N)
- <thread / archive ref> — re: <PMC>; <one-line summary>.

### prs-needing-attention (N)   [waiting on US — from Step 3 triage]
- <PMC> — <owner/repo#num> — <flags: pr-needs-reply / pr-changes-requested /
  pr-ci-failing / pr-conflict> — <commenter>: <one-line gist>; last
  activity <date>. Next: frontier-model-preparation-model-verify (model-PR review threads) or
  direct reply / rebase / CI fix.

### prs-approved-awaiting-merge (N)   [merge is the PMC's call — nudge candidates]
- <PMC> — <owner/repo#num> — approved <date>; open <D> days. Optional nudge.

### enrollable-not-enrolled (N)   [ready to scan, nobody noticed — from Step 3 reconciliation]
- <PMC> — <owner/repo> — passes Check A on the default
  branch since <date> (<D> days); criticality <NN.N%>;
  absent from `Repositories submitted`. Enabling PR
  <owner/repo#num> merged <date>. Next: operator
  decision, then frontier-model-preparation-submit.
  Note the PMC's other in-scope repos and their scores so
  the phase-1-vs-wait call is informed.

## Awaiting PMC reply (no action needed)
- <PMC> — we replied <date>; <D days> ago.
- (overdue >14d): <PMC> — overdue by <D days>; consider nudge.

## Submitted, awaiting ASF Tooling (no action needed)
- <PMC> — submitted <date>; <D days> ago.
- (overdue >14d): <PMC> — ASF Tooling nudge candidate.

## Completed since last sweep
- <PMC> — forwarded <date>; end-to-end <D days>.

## Who waits for whom — direction ledger (every thread + every open PR/change)
<!-- Built from EVERY record in the thread-state cache, not from this
     sweep's changed set. Threads that went quiet before the `after:`
     window are absent from the changed set by construction and are
     exactly the ones that have waited longest — see Step 1. State the
     cache total here so the omission is visible if it recurs. -->
- **Cache coverage:** <N> non-noise threads in the cache; <N>
  classified below. These two numbers must match.
- **Awaiting us (N):** <PMC / owner/repo#num> — <thread or PR> —
  they acted last @ <date>; what we owe: <one line>.
  Include long-quiet threads, not just ones that moved this
  sweep; annotate each as a genuine ask or a bare ack per
  Step 6.5 rather than dropping it.
- **Awaiting them (N):** <PMC / owner/repo#num> — we acted last
  @ <date>; nothing owed unless overdue.
- **Direction UNRESOLVED (N) — drive this to zero before the
  sweep is done:** <thread / PR> — why it couldn't be resolved
  (thread or message list not fully paged, ambiguous last
  actor). Each entry is a gap to close *now*, not to defer —
  re-page the thread/message list until the direction is
  definite.

## Status sheet refresh
- Status tab refreshed at <time>. <N> in flight, <N>
  completed, <N> timeline events.
```

### Step 5.5 — Resolve ponymail thread URLs

The PMCs sheet has one column dedicated to **direct** lists-apache.org thread permalinks:

- `PMC thread (ponymail)` — the programme request thread between the Security team and the PMC (subject prefixed `[GLASSWING]` or `[ASF CLAUDE SECURITY SCAN]`, depending on when the engagement started).

The cell should only ever contain a `https://lists.apache.org/thread/<tid>` URL — a direct permalink to the actual thread.
**No fallback or "starter" URLs.**
If a thread cannot be resolved (because ponymail auth isn't set up, or the thread isn't indexed yet), leave the cell blank rather than write a substitute.

Procedure:

1. Call `mcp__ponymail__auth_status`.
   If "Not authenticated", surface a one-line note in the action list ("Ponymail columns require `mcp__ponymail__login` — N rows skipped") and continue with the rest of the sync.
   Do not attempt to resolve URLs without auth.

2. For each PMC row where `PMC thread (ponymail)` is blank (or where it currently contains a non-permalink URL from an older sync run):

   - Call `mcp__ponymail__search_list` with `list=private`, `domain=<pmc>.apache.org`, `subject=FRONTIER MODEL PREPARATION`, `emails_only=true` (and a `timespan` covering the period since the original announcement to bound the search).
   - From the results, find the thread whose subject matches `[GLASSWING] <PMC>:` **or** `[ASF CLAUDE SECURITY SCAN] <PMC>:` (or their forwarded / replied variants — e.g. Fineract has a "Fwd:" subject line) and whose first message's `from` matches the PMC contact recorded in the sheet's `Contact Person` cell.
     If both prefixes turn up a thread for the same PMC, prefer the one whose first message's `from` and date line up with the sheet's `Contact Person` / `Request date`; surface the ambiguity in the action list rather than guessing.
   - Read the thread's `tid` from the result.
     Construct `https://lists.apache.org/thread/<tid>`.
   - Write back via `frontier-model-preparation-update` `apply`.

   Note: the ponymail MCP **blocks `security@apache.org`** entirely (restricted-list policy),
   so we always resolve PMC threads via the PMC's own `private@<pmc>` list —
   the original request — under either prefix — is CC'd there,
   so the thread is in that archive too.

3. If a thread can't be found despite ponymail auth being active, leave the cell blank and surface the row in the action list under a "ponymail thread not yet indexed" note.
   Indexing can lag by a day or two for new threads.

The column is blank-tolerant.
Never substitute a list-view URL or a search URL for a direct thread permalink —
the column commits to direct permalinks specifically so a click lands on the thread itself.

### Step 6 — Refresh the Status sheet + the Scan Results tab

Invoke `frontier-model-preparation-update`'s `build-status-tab` subcommand at the end of the sweep.
This produces a durable view of the same classification for anyone else on the team to read.
The classification logic in this SKILL and the state machine in `build-status-tab` should be kept in sync —
if you find them diverging, that's a bug to fix.

**Then refresh the `Scan Results` tab** — the per-scan outcome view (findings, pre-forward dispositions with counts + percentages, sanity verdict, and the PMC's feedback). It reads the archive clone, so it is a separate command from `build-status-tab`:

```bash
uv run --project tools/sheets_writer sheets-writer build-scan-results-tab \
    --spreadsheet-id "<id from memory>" \
    --archive-root ~/code/tooling-agents-private \
    --today <YYYY-MM-DD>
```

Run it whenever Step 2.5 found archive movement (a new scan, a new assessment) or Step 1 surfaced PMC feedback on a delivered scan.
The auto columns are rebuilt from the archive every time; the four feedback columns are **carried over keyed by Scan ID** and are never clobbered by a rebuild.

**Recording PMC feedback (this is the part only the sweep can do).**
`Feedback received` / `Sentiment` / `Feedback summary` / `Improvements suggested` have no automated source — they are the sweep's read of what the PMC actually said on the programme results thread (either subject prefix).
When a delivered scan gets a substantive reply, write it with:

```bash
uv run --project tools/sheets_writer sheets-writer scan-results-set \
    --spreadsheet-id "<id>" --scan-id <project>-<YYYY-MM-DD>-<sha> \
    --feedback-received <YYYY-MM-DD> \
    --sentiment "<Positive / Neutral / Mixed / Negative — <one-clause why>>" \
    --summary "<what they said, quoting the load-bearing phrase verbatim>" \
    --improvements "<what the programme should change, or 'None raised'>"
```

Three rules for those cells, because they are the programme's only feedback record:

1. **Read the full message, never the search snippet.** The 2026-07-20 APISIX reply opened "no major issues found" and the snippet stopped there; the body went on to "to say I was disappointed would be an understatement", called the descriptions unreadable, and called 150+ findings "a DDoS in itself". A snippet-based summary would have recorded that delivery as mildly positive when it was the programme's sharpest criticism to date.
2. **Quote the load-bearing phrase verbatim** in the summary. Paraphrase drifts toward the comfortable reading.
3. **Sentiment is about the report, not the tone.** A polite, friendly message that says the findings were not worth the triage effort is `Negative`. Courtesy is not approval.

Feedback that explicitly covers more than one scan (APISIX's did) gets recorded on **each** affected scan's row, noting the extension — otherwise a per-scan reader sees a blank and assumes silence.

### Step 6.5 — Final pass: unresolved PMC asks (always the last analytical step)

**Always run this as the last step of every sweep**, after the Status-sheet refresh and immediately before hand-off.
The direction ledger (Step 5) answers *who acted last*;
this pass answers the sharper question the operator actually cares about: **does any PMC have a concrete ask sitting unanswered on our side?**
"Awaiting us" and "has an unanswered ask" are not the same —
a PMC's last message is often a bare acknowledgement ("thanks", "looking forward to the results"), a "we'll follow up" deferral (the ball is in *their* court), or a courtesy note, none of which owe them a reply.
An unanswered *ask* is a question or request they're waiting on us to act on.

Procedure:

1. Take every in-flight thread whose true-latest message is the PMC's (`awaiting = us`, resolved per Step 1 / hard rule 7 — **never** off the search snippet).
2. Cross-check with a live `mcp__claude_ai_Gmail__search_threads` on `(subject:GLASSWING OR subject:"ASF CLAUDE SECURITY SCAN") is:unread` as a *hint* only (per hard rule 7's corollary, `is:unread` misses read-but-unanswered messages, so it narrows but never bounds the set).
3. Read each candidate's latest message and classify the ask:
   - **Unanswered ask** — a question or request awaiting our reply/action → surface it.
   - **No ask** — bare ack / thanks / courtesy → not surfaced (note in passing).
   - **Ball in their court** — an explicit "we'll follow up / post back / merge next week" deferral → not an ask on us; note who we're waiting on.
   - **Already handled this session** — a draft was created or an action taken → note it as pending-send, not unresolved.
4. Surface a dedicated **`## Unresolved PMC asks`** section at the end of the action list — one line per genuine unanswered ask: `<PMC> — <thread id>, <who> asked <date>: <one-line ask>. Next: <SKILL>.` If the set is empty, say so explicitly ("No unresolved PMC asks — every genuine question/request is answered or waiting on the PMC.").

This section is the operator's final at-a-glance "is anyone waiting on me for an answer?" — keep it tight and cite thread ids.

### Step 7 — Hand off

Before surfacing, confirm the direction ledger accounts for **every** in-flight thread *and* every open PR with a definite "awaiting us" / "awaiting them" verdict,
and that the UNRESOLVED bucket is empty.
If it isn't, the sweep is **not finished** —
go back and drain the missing thread/message pages (Step 1) first.
A sweep is complete only when who-waits-for-whom is clear for every thread and every open PR;
"I didn't get to page 2" is an open action, not a closed sweep.

**Run the count check, do not eyeball it.** Compare the number of threads classified in the ledger against the number of non-noise records in the thread-state cache:

```python
cached = [t for t in cache["threads"].values() if t.get("awaiting") != "noise"]
assert len(classified) == len(cached), (
    f"ledger covers {len(classified)} of {len(cached)} cached threads"
)
```

A shortfall means the ledger was built from this sweep's changed set rather than the whole cache (see Step 1) — the threads missing are the ones that went quiet earliest, i.e. the ones most likely to be owed a reply. Rebuild from `cache["threads"]` before surfacing anything. The 2026-09-07 sweep shipped with 4 of 41 and read as complete.

Surface the action list and stop.
The user picks an item and invokes the matching SKILL by name.
Do not chain into a SKILL unbidden.

## Cross-references — which SKILL handles each next action

| Next action | Downstream SKILL |
| --- | --- |
| Run gates 1–4 on a new request | `frontier-model-preparation-response` |
| Reply to a PMC's follow-up message | `frontier-model-preparation-response` |
| Run pre-flight model assessment for a PMC | `frontier-model-preparation-model-verify` |
| Draft email response with model gaps | `frontier-model-preparation-model-verify` (Templates 4 or 5) |
| Open AGENTS.md/SECURITY.md PR | `frontier-model-preparation-model-verify` (Templates 1–3) |
| Write any cell on the PMCs sheet | `frontier-model-preparation-update` (apply) |
| Add a new column / rename / insert | `frontier-model-preparation-update` (add-columns / insert-column / rename-column) |
| Save a canned response | `frontier-model-preparation-update` (append-canned) |
| Refresh the Status sheet | `frontier-model-preparation-update` (build-status-tab) |
| Enroll scan in the tracker + draft PMC notification | `frontier-model-preparation-submit` |
| Forward the scan bundle + assessment (attachments) to PMC | `frontier-model-preparation-forward` |
| Generate a status rollup | `frontier-model-preparation-status` |
| Produce a fresh threat-model draft for a PMC (no model yet) | `magpie-security:security-model-prepare` |
| Grow an existing model to close rubric gaps | `magpie-security:security-model-update` |

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
- A sweep that builds the direction ledger from the **changed set** instead of the whole thread-state cache (Step 1, Step 7).
  This is the inverse of the pagination failures above and it is worse, because the changed set is *supposed* to be a subset —
  nothing looks truncated, no page is missing, and the action list reads as complete.
  What it omits is precisely the threads that stopped moving earliest, i.e. the ones most likely to be owed a reply.
  The 2026-09-07 sweep reported **4** threads awaiting us against **41** in the cache, and Guacamole — a PMC reply from 08-07, cached `awaiting: us`, three repos and the whole engagement parked on it — was never listed at all.
  Iterate `cache["threads"].values()`; run the Step 7 count check before surfacing.
  A `COMMENTED` review or an issue-comment carries a maintainer's question with **no** `CHANGES_REQUESTED` and no `reviewDecision` change, so the shortcut reports the PR clean while a real question sits unanswered.
  The 2026-07-05 Maven `#12421` (elharo scope review) and CloudStack `#13293` (review-process question) misses are the reference failure — both were caught only by a dedicated comment-fetch re-run.
  Fetch the comment/review threads on **every** sweep (mechanical recipe in Step 3); never derive the flag second-hand.
- A sweep that only looks at **open** PRs and therefore never notices a repo that became scannable when its discoverability PR merged (the `enrollable-not-enrolled` pass in Step 3).
  This failure is silent by construction: the PR leaves the open-PR query at the exact moment the repo becomes enrollable, so no thread moves and no flag fires.
  On 2026-07-30 it had left `apache/solr-operator` idle 13 days and `apache/opendal` idle 28 — the latter being the only scored repo in its PMC's scope, i.e. that PMC's entire scan value was parked.
  Reconcile `Repositories requested` minus `Repositories submitted` against default-branch discoverability on every sweep, and fix any `PR/Issues` cell still saying `OPEN` for a merged PR.
- A sweep that decides a PMC isn't ready from a bare pass/fail ratio ("only 1 of 4 repos passes") without looking at Criticality Scores.
  Blank-criticality repos are not "active" by the definition the scope gate uses; holding a scored repo behind unscored ones parks the real scan value. Surface the scores, let the operator choose.

## Provenance

This SKILL was added to formalize the periodic-sweep pattern Jarek has been running by hand:
re-fetch Gmail, re-fetch the sheet, re-check each PR's state,
classify per PMC, then drive the next batch of work.
Codifying it as a SKILL makes the classification deterministic,
lets other Security-team members run the same sweep,
and gives the team a shared vocabulary for pipeline state across the PMC cohort.
