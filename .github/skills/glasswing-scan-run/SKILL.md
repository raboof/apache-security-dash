---
name: glasswing-scan-run
description: Umbrella orchestration SKILL for the Glasswing scan pipeline — the periodic "run a full sweep across the program" entrypoint. Performs a read-only sweep across all four input surfaces (Gmail [GLASSWING] threads, the Mythos tracker spreadsheet's PMCs sheet, GitHub PRs the Security team has opened on PMC repos, incoming Mirko/Alpha-Omega scan-result mail) and produces a single action list — per-PMC, classified by where each engagement sits in the pipeline (new request, awaiting PMC reply, model-verify pending, ready to submit, submitted to vendor, results back, forwarded, etc.). The user picks what to act on; this SKILL never writes — it hands off to glasswing-scan-response, glasswing-model-verify, glasswing-scan-update, glasswing-scan-submit, glasswing-scan-forward, or glasswing-scan-status for actual work. Use this at the start of a work session, when picking back up after time away, or whenever Jarek says "where do we stand on Glasswing", "run a full scan sweep", or "what's pending across the program".
---

# glasswing-scan-run SKILL

The umbrella orchestration for the Glasswing scan-outreach
pipeline. This SKILL's only job is to **survey**: it scans
every input surface, cross-references state, classifies every
in-flight engagement, and surfaces a per-PMC action list that
the user can triage. All writes happen via the per-task SKILLs
that this one hands off to.

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

**OSS-tooling side flow** (parallel, non-blocking on the
scan pipeline). The PMC's reply to the pitch above may
nominate `@apache.org` addresses for an
Anthropic-Claude-for-Open-Source subscription expedite ask.
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

The two flows are independent: the scan can be submitted
with or without an OSS expedite ask in flight, and an
expedite can be relayed before, during, or after the scan
submission. The pitch step in the scan pipeline raises the
OSS-tooling offer (one outbound email), and the PMC reply
step collects both decisions in one inbound response (which
@apache.org addresses to expedite — if any — and any
substantive scoping / threat-model follow-up).

The `Archived` step is a synchronous part of `glasswing-scan-forward`:
the SKILL sanity-checks Mirko's report (catching catastrophic
generation errors — wrong project, wrong/stale model, truncation,
missing repos), commits the vendor's markdown + `.json` raw +
`.notes.md` sanity-check log to
[`scans/<project>/<repo>/`](../../../scans/README.md), then drafts
the forwarding email (vendor findings verbatim, no per-finding
triage) citing the archive filename. The single user-approval
gates both the commit and the email; see
[`scans/README.md`](../../../scans/README.md) for the path /
metadata / confidentiality spec.

Each stage has its own SKILL responsible for the work that
moves an engagement through it. This SKILL doesn't replicate
that logic — it just figures out which stage each engagement
is *in* and surfaces what to do next.

## When to invoke

- **Start of a work session.** "Where do we stand on
  Glasswing?" — run a full sweep first so the rest of the
  session is grounded in current state, not in what was true
  last time we worked.
- **After time away.** Multiple days of accumulated email +
  spreadsheet edits + open PRs need cross-referencing before
  any per-PMC work makes sense.
- **Before sending a status update.** Foundation-level or
  Security-team rollup emails should be sourced from the
  Status sheet that this SKILL refreshes.
- Whenever Jarek says explicit triggers: "sync up the scan
  tracker", "what's pending across the program", "do a full
  Glasswing sweep", "are there new requests?", or anything
  similarly broad.

Skip when the user is already mid-task on a specific PMC
(don't sweep when they say "draft a reply to Mark" — go
straight to `glasswing-scan-response`).

## Hard rules (do not skip)

1. **Read-only at the umbrella level.** This SKILL never
   writes to Gmail, the spreadsheet, or GitHub. It surveys,
   classifies, and surfaces. When something needs writing,
   the user invokes the matching per-task SKILL.

2. **Surface, don't auto-decide.** When multiple PMCs are
   pending the same action, *list them* and let the user
   pick where to start. Do not silently batch.

3. **Cite the source of every conclusion.** If the sweep
   says "Tomcat is waiting on Mark to choose a path for
   the 3 missing repos", cite the Gmail thread id (or
   subject) and the spreadsheet row that supports that
   conclusion. Stale reads happen; the user verifies.

4. **Don't replicate per-task SKILL logic.** Don't decide
   what reply to draft — that's `glasswing-scan-response`'s
   job. Don't decide model remediation — that's
   `glasswing-model-verify`. This SKILL's output is a list
   of "needs X; SKILL Y handles it"; the per-task SKILL
   does the actual decision-making.

5. **Refresh the Status sheet at the end** by invoking
   `glasswing-scan-update`'s `build-status-tab` subcommand.
   That makes the sweep's findings durable for anyone else
   on the team to read.

## Procedure

### Step 1 — Email sweep

Search Gmail for `subject:GLASSWING OR subject:Glasswing`,
limit 50 most recent threads. For each thread, classify into
one of these buckets:

| Bucket | Signal |
| --- | --- |
| **New `[GLASSWING]` request** | Subject matches `[GLASSWING] <PMC>:` and the PMC isn't yet in the spreadsheet as `Scan Requested = Yes`. |
| **Reply on existing request thread** | We've already replied at least once (`SENT` label present in thread); a *newer* message exists from the PMC after our last reply. |
| **Reply we haven't acted on** | Same as above but our last action (Gmail draft or sheet write) is older than the most recent PMC message. |
| **Pure announcement-thread chatter** | A reply to the original `[IMPORTANT][SECURITY]` announcement that isn't substantive (just "+1", "interesting", etc.). Log and skip. |
| **Bot / automated** | Git push notifications, PR review notifications, MAILER-DAEMON, etc. Filter out — don't include in the action list. |
| **Mirko / Alpha-Omega correspondence** | From `mirko@alpha-omega.dev` or `@alpha-omega.dev`; subject containing scan-request acknowledgement, queue position, or scan result delivery. |

Filter out noise (the announcement-thread `+1`s, the git push
emails, the GitHub PR-review notifications, MAILER-DAEMON
bounces). These typically arrive in volume; skipping them
keeps the action list useful.

### Step 2 — Spreadsheet read

Fetch the `Mythos scan` workbook (file ID in user-scope
reference memory under `mythos-tracker`). Specifically:

- **PMCs sheet** — full row dump for every row where
  `Scan Requested = Yes`. Capture every column: scope,
  contacts, model status, every date, notes, assessment,
  PR/Issues.
- **Status sheet** (if present) — the previously-generated
  in-flight + completed view, as a fast confirmation of
  what the email sweep should match.

**Important — Drive MCP truncation caveat.** The Drive MCP
(`mcp__claude_ai_Google_Drive__read_file_content`) silently
truncates the spreadsheet rendering at ~80KB of markdown,
dropping rows past the first ~140 alphabetically (cuts off
around "Apache Phoenix" with the current ~210-PMC tracker).
PMC rows beyond that boundary are **invisible** to a sweep
that relies on the MCP output alone — sweeps will silently
miss in-flight PMCs like Tomcat, Polaris, Shiro, Spark,
Thrift, Traffic Server, and anything else that sorts after
`P`. For accurate sweep coverage, query the Sheets API
directly via `sheets_writer.py` (the helper in
`glasswing-scan-update`): read `PMCs!A:C` to enumerate slugs
+ Scan-Requested state across the whole sheet, then read
the rest of the row content for the slugs you actually care
about. The MCP read remains useful for the *content* of rows
you've identified via the API. Misdiagnosis from trusting
the truncated MCP output cost the 2026-05-16 sweep a wrong
"6 PMCs need new rows" conclusion that the helper's
duplicate-slug guard then caught on first append-attempt.

For each PMC row, compute the same pipeline state that
`build-status-tab` does (Pre-flight / Ready / Submitted /
Triaging / Delivered). ("Triaging" is the legacy state-column
name written to the sheet; the team's actual activity in
that state is a pre-forward sanity check, not per-finding
triage — see `glasswing-scan-forward`.)

### Step 3 — GitHub PR sweep

For each PMC with a non-empty `PR/Issues` cell:

- Parse the URL(s).
- Query `gh pr view <url> --json state,merged,mergeable,
  reviewDecision,latestReviews` to get the current state.
- Bucket the PR: `open` / `closed` / `merged`.
- Note: a merged AGENTS.md PR means we can re-run
  `glasswing-model-verify`'s discoverability check on that
  repo; surface it.

### Step 4 — Cross-reference and classify

For each `Scan Requested = Yes` PMC, produce a single
classification:

| Classification | Definition | Next action |
| --- | --- | --- |
| `new-request-untouched` | Inbound `[GLASSWING]` request exists; no row in the sheet for that PMC yet, or the row has no `Request date`. | Run `glasswing-scan-response` gates 1–4. |
| `pmc-reply-awaiting-action` | PMC has sent a newer message than our last reply / sheet write. | Read the new message; run `glasswing-scan-response` if it raises questions; run `glasswing-model-verify` if they nominated a model; run `glasswing-scan-update` if it confirms scope / dates. |
| `awaiting-pmc-reply` | We've replied last; nothing new from PMC. | Wait; nothing to do unless time-overdue (see below). |
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

The "time-overdue" rule: any engagement in `awaiting-pmc-reply`
or `submitted-awaiting-vendor` for more than 14 days gets
flagged for a nudge. Don't draft the nudge automatically;
surface it for the user.

### Step 5 — Produce the action list

Output format:

```
# Glasswing pipeline sweep — <YYYY-MM-DD>

## New since last sweep
- <new requests / new PMC replies> with thread refs

## Ready to act on (per stage)

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

## Awaiting PMC reply (no action needed)
- <PMC> — we replied <date>; <D days> ago.
- (overdue >14d): <PMC> — overdue by <D days>; consider nudge.

## Submitted, awaiting vendor (no action needed)
- <PMC> — submitted <date>; <D days> ago.
- (overdue >14d): <PMC> — Mirko nudge candidate.

## Completed since last sweep
- <PMC> — forwarded <date>; end-to-end <D days>.

## Status sheet refresh
- Status tab refreshed at <time>. <N> in flight, <N>
  completed, <N> timeline events.
```

### Step 5.5 — Resolve ponymail thread URLs

The PMCs sheet has two columns dedicated to **direct**
lists-apache.org thread permalinks:

- `PMC thread (ponymail)` — the `[GLASSWING]` request thread
  between the Security team and the PMC.
- `Mirko thread (ponymail)` — historically the scan-submission
  + scan-results delivery thread with the vendor. As of
  2026-05-19, `glasswing-scan-submit` submits scan requests
  via a Google form rather than email, so this column stays
  blank for new submissions — there is no public-list thread
  to permalink to. Kept for back-compat with pre-2026-05-19
  submissions; not maintained for new ones.

Both cells should only ever contain
`https://lists.apache.org/thread/<tid>` URLs — direct
permalinks to the actual thread. **No fallback or "starter"
URLs.** If a thread cannot be resolved (because ponymail
auth isn't set up, or the thread isn't indexed yet), leave
the cell blank rather than write a substitute.

Procedure:

1. Call `mcp__ponymail__auth_status`. If "Not authenticated",
   surface a one-line note in the action list ("Ponymail
   columns require `mcp__ponymail__login` — N rows skipped")
   and continue with the rest of the sync. Do not attempt to
   resolve URLs without auth.

2. For each PMC row where `PMC thread (ponymail)` is blank
   (or where it currently contains a non-permalink URL from
   an older sync run):

   - Call `mcp__ponymail__search_list` with `list=private`,
     `domain=<pmc>.apache.org`, `subject=GLASSWING`,
     `emails_only=true` (and a `timespan` covering the
     period since the original announcement to bound the
     search).
   - From the results, find the thread whose subject
     matches `[GLASSWING] <PMC>:` (or its forwarded /
     replied variants — e.g. Fineract has a "Fwd:" subject
     line) and whose first message's `from` matches the PMC
     contact recorded in the sheet's `Contact Person` cell.
   - Read the thread's `tid` from the result. Construct
     `https://lists.apache.org/thread/<tid>`.
   - Write back via `glasswing-scan-update` `apply`.

   Note: the ponymail MCP **blocks `security@apache.org`**
   entirely (restricted-list policy), so we always resolve
   PMC threads via the PMC's own `private@<pmc>` list —
   the original `[GLASSWING]` request is CC'd there, so the
   thread is in that archive too.

3. **`Mirko thread (ponymail)` is not maintained for
   submissions made after 2026-05-19.** `glasswing-scan-submit`
   now uses a Google form rather than email, so there is no
   public-list thread to permalink to. Leave the cell blank
   for new submissions; do not search for it. The column
   stays in the schema for back-compat with pre-2026-05-19
   submissions whose Mirko-email thread was permalinked
   before the transition.

4. If a thread can't be found despite ponymail auth being
   active, leave the cell blank and surface the row in the
   action list under a "ponymail thread not yet indexed"
   note. Indexing can lag by a day or two for new threads.

The columns are blank-tolerant. Never substitute a list-view
URL or a search URL for a direct thread permalink — the
columns commit to direct permalinks specifically so a click
lands on the thread itself.

### Step 6 — Refresh the Status sheet

Invoke
`glasswing-scan-update`'s `build-status-tab` subcommand at the
end of the sweep. This produces a durable view of the same
classification for anyone else on the team to read. The
classification logic in this SKILL and the state machine in
`build-status-tab` should be kept in sync — if you find them
diverging, that's a bug to fix.

### Step 7 — Hand off

Surface the action list and stop. The user picks an item and
invokes the matching SKILL by name. Do not chain into a SKILL
unbidden.

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

- **One screen** of action list. If the list is too long
  to scan in one sitting, group by status and collapse
  long sections to counts ("12 PMCs awaiting reply — list
  on request").
- **Cite sources concretely.** A thread id, a sheet row
  number, a PR URL. "PMC says X" without citation can be
  wrong; with citation it's verifiable.
- **Don't editorialize on PMC priorities.** Surface the
  state; let the user decide which PMC to attend to. The
  sweep doesn't know that Logging is the test bed or that
  Tomcat has more eyes on it.
- **Use the same color/state taxonomy as `build-status-
  tab`.** If the action list says "Tomcat: Pre-flight",
  the Status sheet should also show Tomcat in the
  Pre-flight bucket. Divergence is a bug.

## Examples of bad sweeps (avoid)

- A sweep that dumps every Gmail thread in the action
  list. Filter out the noise (`+1`s, git pushes, GitHub
  notifications, MAILER-DAEMON). The action list is for
  things the user must act on.
- A sweep that auto-drafts replies as part of the survey.
  Per hard rule 1 — this SKILL is read-only. The user
  picks an item and then invokes the response SKILL.
- A sweep that omits the GitHub PR check. Discoverability
  PRs we've opened are real state changes; a sweep that
  ignores them produces a "Tomcat is blocked on
  discoverability PR" line when in fact the PR landed
  three days ago.
- A sweep that uses stale memory for the spreadsheet.
  Always read fresh — Piotr may have edited columns or
  rows between sweeps.
- A sweep that doesn't refresh the Status sheet at the
  end. The Status sheet is the team's shared view; a
  sweep that only reports in chat leaves the rest of the
  team out of date.

## Provenance

This SKILL was added to formalize the periodic-sweep pattern
Jarek has been running by hand: re-fetch Gmail, re-fetch the
sheet, re-check each PR's state, classify per PMC, then drive
the next batch of work. Codifying it as a SKILL makes the
classification deterministic, lets other Security-team members
run the same sweep, and gives the team a shared vocabulary
for pipeline state across the PMC cohort.
