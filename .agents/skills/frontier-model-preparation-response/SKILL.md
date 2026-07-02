---
name: frontier-model-preparation-response
description: >-
  Draft a reply to a PMC member or contributor asking about the ASF Security team's Frontier Model Preparation scan offer —
  what model it uses,
  what threat-model framework is expected,
  how it compares to other scanners,
  how to get scanned.
  Use whenever someone replies to (or directly asks about) Jarek's "[IMPORTANT][SECURITY] Possibility of running your project through Frontier Model Preparation security scan" announcement,
  or otherwise asks for the scan.
  Output is an email draft for human review — never sends.
  Bundles a companion threat-model producer
  to attach to the response when one is needed.
---

# Frontier Model Preparation scan-response SKILL

This SKILL answers inquiries about the ASF Security team's Frontier Model Preparation scan offer —
*not* the scan itself.
The deliverable is a draft email reply that the human (Jarek, or another Security-team member) reviews and sends.
The SKILL never sends mail directly.

## When to invoke

- A PMC member or contributor replies to the "[IMPORTANT][SECURITY] Possibility of running your project through Frontier Model Preparation security scan" announcement (or its descendants)
  with questions, concerns, or scoping discussion.
- A PMC member writes in (e.g. to `security@apache.org` or directly to a Security-team member) asking about the scan.
- A reviewer asks "what threat-model framework do you expect?" or "how does this compare to GitHub code scanning / Snyk / Dependabot / …" in any related thread.

## Hard rules (do not skip)

1. **Different identity expectations for discussion vs. submitting a scan request.**

   - **For general questions and discussion** about the program
     (what framework is expected, how the scan compares to other tools,
     scoping back-and-forth, clarifying what we mean by X, etc.):
     **any email is fine.**
     Personal Gmail, employer address, a non-Apache forum — all acceptable.
     Answer the substantive questions normally.
     Do **not** push the requester to switch to `@apache.org` just to continue talking;
     making people hop accounts to ask a question is friction we don't need.

   - **For the actual `[GLASSWING]` scan request** (the formal opt-in message that queues a scan):
     the request itself must anchor to an `@apache.org` identity.
     Acceptable shapes are **either** the From: header is `@apache.org`
     (a personal `@apache.org`, or a project alias like `security@<pmc>.apache.org` / `private@<pmc>.apache.org`),
     **or** the body of the request explicitly states the requester's `@apache.org` address.
     The reason isn't bureaucracy:
     **scan results are delivered only to the `@apache.org` personal addresses listed in the request**,
     so we need at least one concrete `@apache.org` address attached to every request before queuing —
     that's where the output goes.
     The hard enforcement of this lives in the **Scan-request verification gates** section (gates 2 and 3);
     this rule is the policy summary.

   When a general-inquiry exchange starts heading toward an actual request,
   mention this expectation in passing —
   *"when you're ready to formally request, the request will need at least one `@apache.org` address listed, since that's where the scan results go"* —
   as a forward-looking note, not a gate on the current discussion.

2. **Cc the PMC's verified `security_contact`.**
   Run, for every PMC, before constructing the CC list:

       uv run --project tools/whimsy_lookup whimsy-lookup \
         pmc-security-info <pmc-slug>

   and Cc the `security_contact` it reports.
   That is the PMC's own `security@<pmc>.apache.org` when it has registered one
   (which itself auto-Ccs `security@apache.org`), or the foundation-wide
   `security@apache.org` otherwise.

   The lookup consults `apache/security-site:scripts/project-coordinates.json` (the authoritative source) and is the only acceptable evidence;
   do **not** WebFetch the URL (same summarisation hazard as the LDAP / committee JSON).

   If the original thread was on a project's `private@<pmc>.apache.org` list, keep that list on To/CC (don't quietly drop it).
   CC is enough;
   do not move the substantive discussion to `security_contact` unless the requester does.

3. **Confirm before sending.**
   Per the user's "draft and show first" rule,
   always render the full draft (subject, To, CC, body, any attachments)
   and wait for explicit approval.
   The user invokes the send.

4. **Never reveal contents of `private@<pmc>` or `security@` correspondence
   to anyone outside the trust boundary** —
   the reply should not quote excerpts from other PMCs' private discussions,
   even if the requester is also on those lists.
   Keep references abstract ("other PMCs have asked similar questions" — never names).

5. **Vendor opacity in PMC-facing communications.**
   The Security team's relationship with the scan vendor is internal context
   and **must not** be disclosed in any PMC-facing email this SKILL drafts.
   Never include the vendor's individual contact name, the vendor company name,
   the vendor email address,
   or any phrasing that identifies them (e.g. "the Frontier Model Preparation pipeline" when used as a synonym for the vendor).
   Canonical replacement phrases for PMC-facing text:

   - "our scan vendor partner"
   - "our vendor relationship"
   - "the scan pipeline"
   - "the third-party scan vendor"

   The Frontier Model Preparation **program name** is fine to use (it's already in the `[GLASSWING]` subject line PMCs use).
   What's redacted is **who runs the pipeline downstream of the Security team**.
   Anthropic — as the Claude-for-OSS program runner and the model provider —
   IS fine to mention by name in PMC-facing text;
   the redaction is specifically the scan vendor.

   This rule applies to every PMC-facing template in this SKILL:
   the four gate-reply fragments, the pre-flight- pass template, the canned-response answers, and any ad-hoc replies.
   Cross-referenced from `frontier-model-preparation-submit` (PMC notification email;
   not the form submission itself, which is internal vendor-side and may name vendor staff freely)
   and `frontier-model-preparation-forward` (scan-results forwarding email) —
   both apply the same rule.

## Scan-request verification gates

These checks apply to inbound `[GLASSWING]` **scan-request** emails
(subject pattern `[GLASSWING] <PMC>: request to scan repositories`) —
not to general inquiries about the program.
Run all four gates before drafting the reply.
Multiple failing gates roll up into one reply that addresses all of them;
do not play whack-a-mole across multiple round-trips.

### Gate 1 — All required fields are present (and result destinations are `@apache.org`-rooted)

The announcement asked for:

- PMC name + confirmation of interest (one message per PMC),
- primary and backup PMC contacts (names + `@apache.org` addresses),
- `@apache.org` email addresses to send scan results to,
- links to the GitHub repos to scan.

If any of those are missing or empty,
list the missing items specifically —
don't ask "could you fill in the rest", name them.

**Result-destination validation (hard policy):** every results-destination address must be `@apache.org`-rooted.
The three acceptable shapes, in order of preference:

1. **Personal `@apache.org` addresses** (`<id>@apache.org`) — the preferred default.
   Silently accepted; no push-back.
2. **Project aliases** (`private@<pmc>.apache.org`, `security@<pmc>.apache.org`) — acceptable **on explicit PMC confirmation only**.
   If the PMC nominates a project alias on the first request,
   ask them to confirm they really want list-based delivery before accepting;
   don't silently accept on first mention.
   Once confirmed, treat it as a valid destination.
3. **Nothing else** —
   non-Apache addresses (personal Gmail, employer address, third-party forum, etc.)
   are unconditionally rejected, even when the requester explicitly asks for them.

Why ask-to-confirm on project aliases rather than silent accept?
Three reasons we want the PMC to consciously choose the list-delivery path:

1. **Pre-disclosure scope discipline.**
   Scan reports contain pre-disclosure vulnerability candidates.
   Personal recipients tie the disclosure scope to named individuals at a known point in time;
   project lists deliver to whoever's subscribed at delivery time and whoever joins later.
   Both are fine if the PMC has thought about it;
   the ask-to-confirm step is what surfaces "did you mean personal or list?"
   as an explicit decision rather than a default.
2. **Concrete triage accountability.**
   Personal recipients have names against the triage work;
   a list has only a collective inbox.
   Some PMCs prefer the list (broader visibility);
   others prefer named individuals (clear ownership).
   Either is valid — we surface the choice.
3. **Vendor trust boundary.**
   Our scan vendor partner expects ASF-anchored recipient addresses.
   Both personal `@apache.org` and project-list `@<pmc>.apache.org` addresses satisfy that requirement;
   the trust-boundary constraint is just "must be ASF-rooted", not "must be personal".
   (Internal note — the vendor here is Alpha-Omega;
   do *not* name them in the PMC-facing reply fragment below per Hard Rule 5.)

If a request lists a non-Apache address (Gmail, employer address, etc.),
reject with the corresponding reply fragment below.
If a request lists a project alias, send the ask-to-confirm reply fragment.
If a request lists only personal `@apache.org` addresses, no push-back is needed on this gate.

Reply fragment (missing fields):

> Thanks — to queue the scan we still need the following items
> the original request didn't include:
>
> - <missing field 1>
> - <missing field 2>
>
> Once we have those we'll continue with the verification steps.

Reply fragment (results-destination is non-personal-`@apache.org` — a project list, personal Gmail, employer address, etc.).
This is the *default push-back* fragment;
if the PMC comes back and explicitly confirms they want the project alias
(typically chair-sanctioned with a known-bounded membership),
accept it on that second pass —
the canned response's NOTES column documents the established exceptions (Fineract, plus historically Tapestry / Thrift / Commons / JSPWiki).

> A small adjustment on the results destination. Scan reports
> contain pre-disclosure vulnerability candidates, and we
> deliver them only to personal `@apache.org` addresses — not
> to project lists — so the disclosure scope stays tight (a
> list's membership can drift over time; a personal address
> is one named recipient). Instead of
> `<list / non-apache address>` we'd send results to
> `<primary @apache.org>` and `<backup @apache.org>`. You can
> configure either address to forward wherever you prefer on
> your side.

### Gate 2 — Sender identity is apache.org-rooted

The From: header on the request must be either a personal `@apache.org` address **or** a project alias (`security@<pmc>.apache.org` / `private@<pmc>.apache.org`).

If the body *already* states the `@apache.org` address, this gate passes — proceed to gate 3 with that stated address.

If the request came from a non-apache.org address (personal Gmail, employer address, third-party forum, …)
**and** the message body does not explicitly state the sender's `@apache.org` address,
**do not block immediately** —
first try to resolve the sender to a candidate Apache ID.
Apache emails are public and committer rosters are publicly browsable;
in most cases we can do the lookup work ourselves rather than pushing it onto the maintainer.

**Resolution procedure** — start with the canonical source.
The ASF roster is the only source that always gives the correct ID;
everything else is a hint.

1. **Apache Projects MCP — `search_people` (canonical, no auth, structured).** Resolve the name via the `mcp__apache-projects__search_people` tool:

       search_people(query="<full name from From: or signature line>")

   It returns structured records (`id`, `name`, `member`, `groups`) for every committer whose ID or name matches —
   no multi-MB JSON enters context and there is no summarizing layer to hallucinate.
   Typically one hit.
   Bonus: the `groups` array already lists the person's PMC groups (e.g. `camel-pmc`), so a single call often answers Gate 3 as well.
   Use this first.

   Example.
   Sender wrote from `ancosen@gmail.com`.
   The local-part heuristic (step 3) would propose `ancosen@apache.org`, but `search_people(query="Andrea Cosentino")` returns id `acosentino` (groups include `camel-pmc`, `servicemix-pmc`).
   Trust the roster, not the heuristic.

2. **`whimsy-lookup resolve-id` (deterministic fallback when the MCP isn't registered).** Same authoritative data via the CLI in [`tools/whimsy_lookup/`](../../../tools/whimsy_lookup/), fetching <https://whimsy.apache.org/public/public_ldap_people.json> with stdlib urllib + json (no summarizing layer):

       uv run --project tools/whimsy_lookup whimsy-lookup \ resolve-id "<full name from From: or signature line>"

   **Do NOT use WebFetch on this URL.**
   The LDAP people JSON is several MB;
   WebFetch summarises it and has been observed to return hallucinated keys, truncated rosters, or fabricated entries.
   The 2026-05-21 Doris incident (Calvin Kirs) traces back to a WebFetch summary
   that drove an unnecessary gate-3 challenge in a PMC-facing email;
   both the MCP (step 1) and this deterministic helper would have returned the correct answer.
   Treat WebFetch on `*.json` Whimsy endpoints as a bug.

3. **Local-part heuristic (hint only — confirm against the roster)** — `<local-part-of-sender>@apache.org`.
   Often right, sometimes wrong (Andrea Cosentino's gmail local-part is `ancosen` but his Apache ID is `acosentino`).
   Never propose this as a candidate without confirming against step 1 or 2.

4. **Project committers / team page** — fetch `https://<pmc>.apache.org/team.html` (or `/committers.html` / `/community/team-list.html`, naming varies).
   Useful when the roster has an ambiguous-name case (two people with similar names), since the team page lists *which PMC* each member is on.

5. **Git history on the project's primary repo** — `gh api search/commits?q=author-name:<First>+<Last>+repo:apache/<repo>` (use the GitHub `search/commits` endpoint, not the per-repo `commits?author=` endpoint, which only accepts GitHub-login authors).
   Commit emails are sometimes `@apache.org` (definitive) but more often a personal address (a hint at best).

6. **Whimsy interactive roster** — `https://whimsy.apache.org/roster/committee/<pmc>` and `https://whimsy.apache.org/roster/people/<id>`.
   Requires Apache ID auth;
   use it for the user-side confirmation step, not the agent's automated resolution.

**If a candidate is found:** reply with the propose-and-confirm template below.
The candidate is *not* an authentication claim —
it's a hypothesis the maintainer either confirms (Gate 2 passes) or corrects (re-resolve against the corrected ID).

**If no candidate is found:** fall through to the explicit "please anchor your identity" reply.

Reply fragment — propose-and-confirm (preferred when a candidate exists):

> Thanks for the request — to anchor it to your Apache identity:
> you wrote from `<non-apache address>` and the message body
> doesn't state which `@apache.org` address the request should
> be attributed to. I believe your Apache ID is `<candidate>`
> (so `<candidate>@apache.org`) based on
> `<source — committers page / git history / local-part match>`.
> Could you confirm or correct? A one-line reply is enough; we
> verify against the PMC roster before queuing.

Reply fragment — block (only when no candidate can be inferred):

> Thanks for the request — before we queue it we need to anchor
> it to your Apache identity. You wrote from
> `<non-apache address>`, which isn't an `@apache.org` address,
> and the message body doesn't say which `@apache.org` address
> the request should be attributed to. We checked the public
> committer rosters and couldn't infer a candidate Apache ID
> from your name / sender address.
>
> Either of these works:
>
> - **Resend from your `@apache.org` address.** Easiest path:
>   open <https://lists.apache.org/list.html?private@<pmc>.apache.org>
>   in your browser, sign in with your Apache ID, then press
>   `c` to open the compose dialog. Address the new message to
>   `security@apache.org` (with `private@<pmc>.apache.org` on
>   CC), keep the same subject and body — it'll go out from
>   your `@apache.org` address.
>
> - **State your `@apache.org` address in this thread.** A
>   one-line "I'm `<handle>@apache.org`" is enough; we'll
>   verify against the PMC roster.

### Gate 3 — Sender is on the PMC roster

Cross-check the sender's `@apache.org` address (From: header or body-stated, whichever gate 2 resolved to) against the PMC roster.
Two structured, deterministic ways, in order:

1. **Apache Projects MCP (primary).**
   If Gate 2 used `search_people`, the returned `groups` array already settles this —
   membership of `<slug>-pmc` (e.g. `camel-pmc`) means the sender is on the PMC.
   Otherwise confirm directly:

   - `mcp__apache-projects__get_person(id="<apache-id>")` — returns the person's PMC groups; check for `<slug>-pmc`.
   - `mcp__apache-projects__get_committee(id="<slug>")` — returns the full roster (`id`, `name`, `joined`) plus the `chair`; check the sender's ID is present.
     Use this when drafting the reply or verifying the chair.

   Structured output — no multi-MB JSON in context, no summarizing layer to hallucinate.

2. **`whimsy-lookup` CLI (deterministic fallback when the MCP isn't registered).** `check-pmc-member` for a yes/no per ID, or `pmc-info` for the full roster:

       uv run --project tools/whimsy_lookup whimsy-lookup \ check-pmc-member <pmc-slug> <apache-id> [<apache-id> ...]

   The helper queries <https://whimsy.apache.org/public/committee-info.json> via stdlib urllib + json (no summarizing layer), looks up the PMC under `committees.<slug>`, and reports YES/NO per Apache ID with the member's name + joining date for context.
   Exit code 1 if any queried ID is not on the roster; 0 if all are.
   For the full roster (useful when drafting the reply or verifying the chair), use `whimsy-lookup pmc-info <slug>`.

**Do NOT use WebFetch on `committee-info.json`.**
Same caveat as Gate 2:
WebFetch summarises this multi-MB file and has been observed to return hallucinated roster entries.
The MCP (1) and the CLI (2) are the only ways to get a deterministic answer.

The interactive roster page `https://whimsy.apache.org/roster/committee/<pmc>` requires Apache ID auth and is a fallback for the human's double-check, not the agent's automated gate.

If the address is not on the PMC's roster, decline politely.
Past abuse exists where non-members tried to get scans against projects they weren't part of,
so this gate is non-negotiable —
but the phrasing is "we need PMC anchoring", not "we don't trust you".

Reply fragment:

> One wrinkle before we queue this: the address
> `<stated address>` isn't currently on the <PMC name> PMC
> roster (per
> <https://whimsy.apache.org/roster/committee/<pmc>>). We
> require PMC-roster anchoring before queuing a scan. Could a
> PMC member send the request on your behalf, or could the PMC
> chair confirm in this thread that the scan is sanctioned by
> the PMC?

### Gate 4 — Scope confirmation against the PMC's active repos

**This gate fires on every request, not only on under-specified ones.**
Even when the request enumerates a clear list of repos,
the SKILL must cross-check that list against the PMC's *active* repo set (defined below)
and surface any discrepancy as a scope-confirmation question.
A common failure mode is the PMC naming "the obvious ones" and forgetting an active side repo
(typically a Maven plugin, a connectors module, a docs site, or a benchmarks repo);
we'd rather ask once than scan incomplete and have to re-queue.

There are three cases; only case (a) needs no follow-up.

| Case | What the request looks like | Action |
| --- | --- | --- |
| (a) Request lists repos AND the PMC has no other *active* repos beyond those | Accept the list as-is; write it to the PMC's `Repositories requested` cell verbatim. |
| (b) Request lists repos AND the PMC has additional *active* repos not in the list — **including the special sub-case where the request lists only one repo while the PMC has multiple active repos** | Ask the PMC to confirm scope. Send back the full list of their additional active repos and ask, explicitly: *"are you sure you want only the repos you listed, and not these other active ones?"* Wait for confirmation before writing the `Repositories requested` cell. |
| (c) Request doesn't enumerate any repos (just expresses PMC interest) | Ask the PMC to enumerate. Pre-populate the suggestion with the PMC's active repos as a starting point; let them subset / extend. |

**"Active" definition.**
A repo counts as active if it has a non-blank `Criticality Score (%)` cell on the Repositories sheet of the Mythos tracker.
OSSF's criticality_score indexes only repos with meaningful recent activity,
so a non-blank score is a reliable "this repo is alive enough to need scan coverage" signal.
Repos with a blank score (sandbox / Attic / abandoned) don't need to be in scope and shouldn't trigger this gate.

**Source for "what repos does the PMC own (active)"**:
the Mythos tracker's Repositories sheet —
use the `frontier-model-preparation-status` SKILL to fetch it.
Filter by `PMC Slug` matching the requester's PMC;
keep only rows where `Criticality Score (%)` is non-blank.

**Explain what the scope is *for*.**
PMC members often hear "scope confirmation" and think it's a procedural step.
It isn't —
it determines which repos are run through the two pre-flight checks (model discoverability + completeness)
and which repos the agentic scan will subsequently look at.
The reply must say so explicitly so the PMC's confirmation is informed.

This is a confirmation, not a refusal.
Keep it light —
PMCs commonly forget side repos (docs sites, client SDKs, sample apps)
and would rather be asked than scanned incomplete.

Reply fragment (case b — request narrower than active set):

> Quick scope check before we queue this. The request lists:
>
>   - apache/<repo-1>
>   - apache/<repo-2>
>   - ...
>
> The PMC also has these additional active repos under
> github.com/apache (recent commits + meaningful stars or
> OSSF criticality score in parentheses):
>
>   - apache/<other-1> (<score / stars / "active YYYY-MM">)
>   - apache/<other-2> (...)
>   - apache/<other-3> (...)
>   - (... N more)
>
> **Are you sure you want only the repos you listed, and not
> these other active ones?** Either answer is fine; we'd
> rather ask than guess. The list you confirm here is what
> we'll run pre-flight (model discoverability +
> completeness) against for each repo, and what we'll pass to
> the scan vendor as the actual scope.

Reply fragment (case c — no repos enumerated):

> Quick scope check before we queue this — the request didn't
> enumerate which repos to scan, just PMC interest. The PMC
> owns these active repos under github.com/apache (OSSF
> criticality score in parentheses):
>
>   - apache/<repo-1> (<score>%)
>   - apache/<repo-2> (<score>%)
>   - ...
>
> Which of these should be in scope? The list you confirm
> here determines which repos we run pre-flight against
> (model discoverability + completeness) and what we pass to
> the scan vendor as the actual scope. Subset or include all
> — either is fine.

**After scope is confirmed**,
write the confirmed list to the PMC's `Repositories requested` cell (newline-separated full URLs)
via `frontier-model-preparation-update`'s `apply` flow.
That cell becomes the canonical scope:
`frontier-model-preparation-model-verify` reads it,
`frontier-model-preparation-submit` reads it,
no one re-derives scope from elsewhere.

The PMC's `PMC thread (ponymail)` cell is **not** written by this SKILL —
only `frontier-model-preparation-run` populates it,
with a **direct thread permalink** (`https://lists.apache.org/thread/<tid>`) resolved via the ponymail API.
The cell stays blank until ponymail-auth is set up and a sync has run;
never write a non-direct fallback URL there.

If this SKILL ever opens a PR on a PMC repo
(the response SKILL doesn't normally — that's `frontier-model-preparation-model-verify`'s job —
but the helper subcommand path goes through it),
the URL goes into the PMC's `PR/Issues` cell as a **new line** appended to whatever's there.
Never overwrite an existing PR URL when adding a new one —
the cell is a running list, not a single-slot field,
and `build-status-tab` relies on every URL being present to compute open/merged counts.

## Pre-flight-pass template — ready-to-scan notification + OSS-tooling offer

**When to use this template.**
Fires when `frontier-model-preparation-model-verify` has just passed for a PMC
(threat model verified + per-repo discoverability either landed or in flight as a small PR),
and the PMC's row in the tracker has `Security model verified` filled.
This is **not** a question-response — it's a workflow step.
The `frontier-model-preparation-submit` SKILL no longer fires automatically on pre-flight pass;
this template is what goes out first instead.

**One path, not two.**
The scan itself follows a single path:
when the Security team operator gives the green light,
we submit the request to our scan vendor partner,
the scan runs,
results come back to the Security team for a pre-forward sanity check
(catching catastrophic generation errors only — wrong project, wrong/stale model, truncated output),
then we forward the vendor's report verbatim to the PMC's named triage contacts
for the PMC's own per-finding triage against the project's threat model.
That sequence is the same for every PMC.

**Separately**, the template raises an offer for PMC members who'll be doing the triage work on the results:
**Anthropic's Claude-for-Open-Source subscription**,
which gives them access to Claude Opus 4.7 + tooling like Apache Magpie
(the hopefully-to-be-established ASF TLP at github.com/apache/airflow-steward)
to manage the scan findings —
convert them into GitHub issues, pre-triage,
draft fixes and PRs based on the maintainer discussion around each issue.
The OSS subscription is a *tool the triagers may want to use on the results*, not an alternative path for the scan itself.
PMC members who want the subscription **register first** at the Anthropic form
and **then** tell us which @apache.org addresses to include in an expedite ask —
we can attempt (no promise) to expedite via our vendor relationship
for projects that have completed pre-flight.

The template collects the PMC's expedite-account list —
the `@apache.org` addresses they want included in the expedite ask after registering —
into the new `Expedite Claude OSS Requests` column on the PMC's row via `frontier-model-preparation-update`.
Confirmed subscriptions (once they come back) land in the `Claude OSS Subscriptions Submitted` column.

**Vendor opacity (cross-reference to Hard rule 5 below).**
This template does **not** name the scan vendor anywhere —
"our scan vendor partner" / "the vendor relationship" / "the scan pipeline" are the canonical wordings.
Do not write "Mirko", "Alpha-Omega", "the Frontier Model Preparation pipeline" (when used to mean the vendor) or any similar attribution in the body.
The Frontier Model Preparation *program name* is fine (it's already in the `[GLASSWING]` subject line);
vendor attribution is internal-only.

**To**: PMC primary contact.

**CC**: PMC backup contact(s), `private@<pmc>.apache.org`, `security@<pmc>.apache.org` *(if exists)*, `security@apache.org`, every `@apache.org` address from the original `[GLASSWING]` request's "send results to" list.

**Subject**: `Re: [GLASSWING] <original subject>` — reply on the existing PMC thread so the conversation history stays linked.

**Body**:

```text
Hi <Primary contact first name>,

Pre-flight is complete for Apache <PMC name>:
  - Threat model verified at <URL> (<one-line
    completeness verdict — PASS / PASS-with-soft-gaps>).
  - Per-repo discoverability: <PASS for all N repos / PASS
    for X of N; the remaining are in flight via
    PR(s)#NN+#NN>.

Ready to queue whenever you give the green light — we
don't auto-submit. One scheduling note worth flagging:
we're now provisioned on the scanning model and expect to
run scans through July, so there's a live cycle to land in —
green-lighting now (and landing anything still in flight
above) puts you into the queue at your criticality rank, and
the sooner it lands the better the chance your scan runs in
this window. Typical end-to-end cycle is days to a couple
of weeks depending on queue position.

A program-shape note for context.

In parallel with the vendor-relay path above, the ASF Security,
ASF Infrastructure, and ASF Tooling teams are jointly pursuing
direct-access scanning of ASF projects without the third-party
vendor relay. This is what we're currently working on at the
ASF in parallel. Both paths feed the same internal queue; we
work whichever lands fastest for any given PMC, to make the
best use of the opportunities each party involved has made
available. From the PMC's perspective the process is identical
either way: pre-flight gate, scan, sanity-check, forward
results to your named recipients. We mention it so you have
the full picture of how the program is wired — nothing changes
about what shows up in your inbox.

A separate offer for PMC members who'll be doing the
triage work:

When scan results come back, the work of reading them,
classifying findings against the threat model, deciding
on fixes, and drafting PRs is exactly the kind of thing
Claude Opus 4.7 has proven solid at. Several ASF projects
are using it in this capacity today, paired with Apache
Magpie (hopefully to be established as an ASF TLP) — a
set of reusable skills at
https://github.com/apache/airflow-steward that already
supports:

  - Importing scan results and converting them into
    GitHub issues (JIRA support landing very soon).
  - Pre-triage + first-pass scan-result assessment
    (grouping by component, classifying against the
    project's threat model, weeding out findings that
    fall outside the project's scope).
  - Looking at possible solutions per issue based on the
    maintainer discussion around it.
  - Creating PRs based on the issue + the maintainer
    discussion.

If any of your PMC members would benefit from an Anthropic
Claude-for-Open-Source subscription to use this tooling
(or for any other open-source work), Anthropic runs a
subscription program at
https://claude.com/contact-sales/claude-for-oss.

How the expedite ask works — **two steps, in order**:

  Step 1 — Register first. Each interested PMC member
  submits a subscription request directly through the
  Anthropic form above, using their @apache.org address.
  This step is required; we can't relay an expedite ask
  for someone Anthropic hasn't received a request from
  yet.

  Step 2 — Tell us which addresses to expedite. Once the
  individuals have submitted via the form, reply on this
  thread listing the @apache.org addresses that should
  be included in the expedite ask. We'll reference those
  addresses specifically when we ask on your behalf via
  our vendor relationship.

  The expedite is **best-effort, not a promise** — our
  vendor partner relays the ask to Anthropic, and
  Anthropic's subscription team makes the call. That
  said, track record so far is that Anthropic has been
  moving expedite requests through quickly when our
  vendor flags them — so the practical expectation is
  "fast, with no guarantee", not "slow and unlikely". The
  per-individual grant remains Anthropic's decision.

If no PMC member wants the OSS-subscription path, that's
fine — it's a tool offered to triagers, not a
prerequisite for the scan. The scan goes through the
normal pipeline either way; we just won't submit until
you tell us to.

Best,
<sign-off>
```

**Procedure for this template:**

1. Read the PMC's row from the tracker (via Sheets API per the truncation caveat).
   Confirm `Security model verified` is filled —
   if not, this template doesn't fire yet;
   point the user at `frontier-model-preparation-model-verify` instead.

2. Render the draft with the per-PMC specifics (model URL, per-repo discoverability verdict, primary contact first-name, etc.).
   Wait for explicit approval before creating the Gmail draft.

3. **When the PMC reply lands** naming accounts for the expedite ask, do two things:

   - Write the @apache.org addresses to the PMC's `Expedite Claude OSS Requests` cell via `frontier-model-preparation-update apply` (newline-separated).
     If the PMC explicitly opts out of the OSS subscription offer,
     write the literal string `none` to the cell
     so the absence is deliberate-and-recorded rather than blank-and-unclear.
     **The PMC must confirm they've completed Step 1 (registered via the Anthropic form)
     before we write addresses to this cell** —
     we don't write addresses that haven't been registered yet
     because the expedite ask would be a no-op.
   - Surface the PMC as `pmc-pitch-replied-awaiting- operator-decision` for the next `frontier-model-preparation-run` sweep.
     The operator then decides whether to invoke `frontier-model-preparation-submit` for that PMC.
     The two decisions (whether to submit the scan; what to do about the OSS expedite ask) are independent —
     the scan can be submitted with or without an OSS expedite ask in flight,
     and an OSS expedite ask can go out before, during, or after the scan submission.

4. **When Anthropic confirms a subscription** for one of the addresses
   (typically via reply to the expedite-ask thread),
   append the confirmed `@apache.org` address to the PMC's `Claude OSS Subscriptions Submitted` cell
   via `frontier-model-preparation-update apply`.
   This column tracks actually-granted subscriptions, distinct from the `Expedite Claude OSS Requests` column which tracks addresses the PMC asked us to expedite.

5. **Do not invoke `frontier-model-preparation-submit` directly from this template's response handling.**
   That SKILL is operator-gated —
   surface the state, let the operator pick.

## Canned responses (consult first, contribute back)

The Mythos tracker spreadsheet has a `Canned Responses` sheet that accumulates reusable answer fragments —
see the `frontier-model-preparation-status` SKILL for its column schema.
**Before drafting any reply, fetch this sheet and check for matches against the requester's questions.**
If a high-confidence match exists, base the reply on the canned `Response` (verbatim or lightly adapted for thread register);
if no match, draft fresh from the standard fragments below.

How to consult:

1. Read the workbook via the `frontier-model-preparation-status` SKILL's fetch step (`mcp__claude_ai_Google_Drive__read_file_content` on the file ID from the `mythos-tracker` memory entry).
   The `Canned Responses` sheet is the fourth tab.

2. For each question the requester raised, scan the `Topic` + `Question pattern` columns for semantic matches.
   Don't do keyword-only matching —
   `Topic: scope` is the right hit for "can the model swallow the whole monorepo?", even if the words don't overlap.

3. Pull the `Response` column verbatim, then lightly adapt for the specific thread (e.g. substitute the actual repo name).
   Respect the `Notes` column — it captures *when not* to reuse the answer.

4. If the `Canned Responses` sheet doesn't exist yet (older snapshot of the workbook), fall back to the fragments inlined below.
   The two sources should converge over time; the spreadsheet wins on conflict.

How to contribute back:

After the user has approved a reply that contained a *novel* answer (one not already covered by an existing canned row),
ask the user whether to save it as a canned entry.
If yes, build a one-element JSON file at `$TMPDIR/canned-add-<timestamp>.json` and route through the `frontier-model-preparation-update` SKILL's `append-canned` flow (same draft-and-confirm gates).
The shape of an entry is:

```json
{
  "topic": "<one-word tag>",
  "question_pattern": "<one-line description of when this applies>",
  "response": "<the canned reply text — markdown OK>",
  "author": "<@apache.org address of the human who signed the reply>",
  "notes": "<when this applies / when to NOT reuse / what to swap>"
}
```

The inlined fragments below are the seed set;
once they're loaded into the spreadsheet (via the `seed_canned_responses.json` bootstrap in the update SKILL),
this file's role becomes documentary —
the spreadsheet is the live source of truth.

## Standard answer fragments

These are the canonical answers to the recurring questions.
Pull from them; reword for the specific thread.

### "What scanning model / framework are you using?"

The scan uses the latest Frontier Model Preparation-available security models —
the operational profile is whichever model Frontier Model Preparation has currently designated as production
for code-level vulnerability scanning.
The Frontier Model Preparation project announcement is here: <https://glasswing.openai.com> (linked from <https://openai.com/index/glasswing-grant-program/>; cross-check the canonical URL for the announcement at draft time — the gist of the program changes more slowly than the model lineup).

If the requester wants the specific model name for the run on *their* repo,
point at the eventual scan-result markdown —
it includes the model identifier as a header field.
Don't pin a specific model in the reply unless the user has explicitly told you to.

**Note on the dual-path program shape.**
Beyond the vendor-relay path that uses Frontier Model Preparation's currently-designated production model,
the ASF Security, ASF Infrastructure, and ASF Tooling teams are jointly pursuing
a parallel direct-access path that runs the scan without the third-party vendor relay (using ASF-side tooling).
Both paths feed the same internal queue and produce the same shape of output for the PMC;
the choice between them is an internal scheduling decision
aimed at moving each PMC's scan through the queue as fast as possible.
The PMC-facing process is identical either way.

### "What threat-modeling framework do you expect — STRIDE / LINDDUN /
PASTA / something else?"

No specific framework.
The scan accepts any *human-readable* threat model that:

- describes what the project considers a security issue and what it does not,
- names the user roles and trust boundaries the project assumes,
- says what's in scope for the scan and what's out (e.g. `contrib/`, `examples/`, demo apps),
- includes the recurring false-positives the project already knows about, so the scan does not re-discover them.

For projects that **don't** already have such a model, or want to update the one they have before the scan, the ASF Security team will run the `threat-model-producer` SKILL (Michael Scovetta's recipe, imported verbatim at <https://gist.github.com/scovetta/2dc9a0695c7cbcc32e23799e00d2ced3>) against the project's public artifacts using Claude Opus 4.7.
The output is a draft `THREAT-MODEL.md` that:

- is itself human-readable
  (it explains what a "good threat model from the agentic-scan point of view" looks like,
  and produces a document in that shape),
- tags every claim with provenance —
  *(documented)* if it comes from the project's own docs,
  *(inferred)* if the agent guessed,
  *(maintainer)* if the PMC has explicitly ratified it,
- collects every *(inferred)* claim into an "Open questions for the maintainers" section so the PMC can react to a draft rather than fill in a blank form,
- ships alongside an `AGENTS.md` linking to it (the marker the scan uses to find the model).

The Security team submits the draft as a PR to the project's repo for the PMC to review and merge.
The scan is gated on the PR being merged (or the PMC supplying their own equivalent).
The PMC owns the document; the Security team just bootstraps it.

**Hard pre-flight: the model must be discoverable and complete enough.**
Before the scan is queued,
the Security team's own agent runs a pre-flight pass against the project's repo at the designated commit
and confirms it can locate the threat model via `AGENTS.md` → `SECURITY.md`.
The mechanics of that pre-flight —
both the discoverability check and the minimum-bar completeness check against the `threat-model-producer` rubric —
live in the companion `frontier-model-preparation-model-verify` SKILL;
invoke it once a model has been nominated.
**If the agent cannot find the model, the scan is refused**
and the PMC is asked to make the model reachable through that discovery path before re-requesting.
This rule is non-negotiable:
without the model, the scan produces a false-positive rate the PMC cannot reasonably triage,
and refusing upfront beats wasting reviewer cycles on a noise-heavy output.
State this requirement explicitly in any reply to a PMC that mentions
"we don't have a SECURITY.md / we use X instead / our model is on the website" —
the answer is "great, just make sure the agent can mechanically follow `AGENTS.md` → `SECURITY.md` to it, otherwise we'll refuse the scan."
Saying this preempts the most common pre-scan back-and-forth.

### "How does this compare to GitHub code scanning / Snyk / Dependabot
/ other tools?"

Complementary, not a replacement:

- **GitHub code scanning** (CodeQL) does taint-tracking and pattern matching against the source.
  It's fast, runs per PR, and is great at well-known sink/source patterns.
- **SCA tools** (Dependabot, Snyk OSS) look at dependency manifests against vulnerability databases.
- **Frontier Model Preparation-style agentic scans** read the code with much more semantic understanding —
  including configuration-driven behaviour,
  cross-file flows that defy static taint analysis,
  and project- specific misuse patterns that no signature would catch.
  They cost more per finding but reach places the cheaper tools miss.

The scan does not replace any of the above.
PMCs that already run CodeQL etc. should keep doing so;
the Frontier Model Preparation run is an *additional* pass aimed at the long-tail of semantic-flow issues.
If the requester is asking because they're worried about duplicating effort:
it is fine and expected to see overlap with CodeQL findings —
those are re-confirmation, not waste.

(Refs that may come up: the asfyaml CodeQL discussion at <https://github.com/apache/infrastructure-asfyaml/issues/94>.)

### "Can the model swallow the whole monorepo?"

Yes for most projects.
For monorepo-scale codebases (Lucene + Solr + Tika scale, or Airflow scale)
the run is chunked by directory tree or by component;
the chunking is invisible to the PMC.
If the project has a clean modular layout (top-level dirs are coherent components), mention that the modular layout makes chunking deterministic.
If it doesn't, mention that we'll work out the chunking with the PMC contacts before kickoff.

### "What does a finding look like?"

A single markdown file with multiple findings, one section per issue, each tagged with:
file & line refs,
the security property violated (citing the project's threat model when one exists),
reproducer sketch where feasible,
and a severity hint.
The Security team does a quick pre-forward sanity check on the report
(right project, right model, no truncation, all submitted repos covered —
catching catastrophically broken vendor output so PMCs aren't asked to read clearly broken reports)
and forwards the vendor's findings to the PMC **verbatim** —
no per-finding triage or filtering on our side.
The PMC then triages through its normal process —
the `private@<pmc>.apache.org` → `security@<project>.apache.org` → coordinated disclosure / CVE / release flow —
applying the project's own threat model for the per-finding read.

### "We'd like to opt in — what do we do?"

Point at the announcement's instructions:
send a new message (not a reply) from a `@apache.org` address to `security@apache.org`,
CC `private@<pmc>.apache.org`,
with the subject `[GLASSWING] <PMC>: request to scan repositories`,
and include:

- confirmation of interest (PMC name, one message per PMC),
- primary + backup PMC contacts (names, `@apache.org` addresses),
- `@apache.org` email addresses to send scan results to,
- links to the GitHub repos to scan.

Verify the requester is on the PMC roster before queuing.
Past abuse exists where non-members tried to get scans against projects they weren't part of;
we say "no" to those.
The full request-handling checks (required fields, identity anchoring, roster check, single- repo scope confirmation)
live in the **Scan-request verification gates** section above —
run those four gates on every `[GLASSWING]` request before drafting a reply.

## Procedure for drafting the reply

1. **Identify the requester's PMC.**
   Look at where their reply landed (`private@<pmc>.apache.org` on To/CC is the strongest signal).
   If ambiguous, ask the user which PMC.

2. **Decide which path applies.**

   - **General inquiry** (someone asking what the program is, what framework we expect,
     how it compares to other tools, scoping questions, clarifications, etc.):
     use the standard answer fragments and continue with step 3 below.
     **Any sender address is fine** — including non-`@apache.org`.
     **Do not** push the requester to switch to `@apache.org` just to keep the conversation going;
     questions are welcome from any address.
     If the discussion is clearly heading toward "let's request a scan"
     (the requester says "we want to opt in", starts listing repos, etc.),
     mention in passing that the formal `[GLASSWING]` request itself
     will need at least one `@apache.org` address listed in it —
     because scan results are delivered only to the `@apache.org` personal addresses listed in the request.
     Frame it as a forward-looking note
     ("when you're ready to formally request, the request needs an `@apache.org` address listed — that's where the results will be sent"),
     not as a gate on the current exchange.

   - **`[GLASSWING]` scan-request email** (subject pattern `[GLASSWING] <PMC>: request to scan repositories`):
     route through the **Scan-request verification gates** above (gates 1–4) instead of the soft-ask.
     The From: identity must be anchored to a PMC member *now*, not "for future messages", before the request can be queued.
     Build the reply out of the gate fragments for any gates that failed;
     if all four pass, the reply is a short confirmation that the request meets entry criteria and will be queued.

3. **Pull out their questions and propose answers — always.**
   Scan the request body for any sentence that ends in `?`
   or that is phrased as a question even without punctuation
   ("What is the minimum we need to do", "We do not want to have to ... — is there a way", "Can the scan ...", "How should we ...").
   Quote each one verbatim from their message (use `> ` blockquote).
   For each question, **first** check the `Canned Responses` sheet for a semantic match
   (see the **Canned responses** section above);
   if a match exists, base the answer on the canned `Response`.
   If not, address the question with the matching fragment from below, lightly reworded for the thread's register.

   If the request *embeds* a question inside a larger logistical email
   (which is common — Mark Thomas's Tomcat request, for example,
   listed contacts + repos + model URL and slipped in a single "what is the minimum we need to do" line in the middle),
   it's especially important not to miss the question.
   The reply that addresses logistics but silently ignores the embedded question reads as inattentive
   and forces the requester to re-ask.
   Pull every question out explicitly even if there's just one.

   A reply that quotes the requester's questions back as blockquotes with answers underneath is the canonical shape;
   resist the urge to "address them inline in the prose" —
   the blockquote-and-answer pattern makes it easy for the requester to scan and confirm we got their question right.

4. **Decide whether a threat-model draft is needed in this reply.**
   - If the requester is asking process / framework questions only (the typical first round),
     the reply contains *no* attached model —
     answer in prose and offer the threat-model-producer SKILL as the next step if they want it.
   - If the user explicitly says "attach the draft",
     run `threat-model-producer` against the relevant repository
     and attach the generated markdown (inline, fenced, or as a follow-up PR link).
     The draft is **what** the reply attaches; the SKILL itself is not attached.

5. **Render the full draft for review.** Show:
   - To / CC / Subject (with `[GLASSWING]` or `Re:` as appropriate),
   - body in plain text (no markdown rendering quirks),
   - any attachments by path or inline content,
   - reply-to message id (so Gmail threading lands correctly).

   Wait for the user to say "send" / "post" / "go ahead" / similar.
   Do not invoke `mcp__claude_ai_Gmail__create_draft` before approval.

6. **On approval**, create a Gmail draft via `mcp__claude_ai_Gmail__create_draft` (per user preference — `oauth-draft-create` is the fallback).
   Do not call `send` directly —
   the user reviews the draft once more in the Gmail UI and presses send.

7. **Offer to save novel answers back to `Canned Responses`.**
   If the approved reply contained any answer that was *not* pulled from an existing canned row,
   ask the user one question: *"Want me to save this as a canned response for future similar requests?"*
   If yes, build an entry and route through `frontier-model-preparation-update`'s `append-canned` flow.
   Default to *yes* for answers that took non-trivial drafting;
   skip the offer for one-line replies that wouldn't benefit from caching.

## Style notes

- Plain prose.
  No marketing language ("cutting-edge AI", "next- generation").
  The audience is Apache committers who can smell that from a mile away.
- Concise.
  Reply length should be proportional to the question's size;
  a one-line question gets a paragraph or two, not three pages.
- **Don't restate what the recipient already knows.**
  A quick acknowledgment is fine;
  full re-explanation of the pipeline, sanity-check mechanics,
  or process steps they've seen in prior emails on the thread isn't.
  Cut "what happens next" recaps and process preambles.
  Keep the substance (URLs, repo lists, sanity-check observations, the actual ask).
- Be honest about overlap with other tools (the "complementary, not replacement" framing).
  PMCs respect that more than over-claiming.
- When you don't know the answer to a project-specific question
  (e.g. "will this miss our X-Y-Z framework's flow analysis?"),
  say so and offer to find out, rather than guessing.
- The reply is from the ASF Security team's voice, signed by the human;
  don't sign it as the agent.

## Examples of bad drafts (avoid)

- A reply that quotes the original announcement back at the requester.
  They sent it; they don't need it back.
- A reply that drops `private@<pmc>` from the recipient list and silently moves to `security@`.
  The original list owns the thread.
- A reply that includes a full threat-model draft when the requester hasn't asked for one yet —
  overkill on round 1.
- A reply that promises the scan "in the next two weeks" or similar.
  Don't commit to a timeline; the Security team coordinates queue.
- A reply that lists which other PMCs have signed up.
  PMC-list membership is between each PMC and the Security team.

## Provenance

This SKILL captures the response patterns Jarek has been using in replies to the May 2026 Frontier Model Preparation scan announcement,
plus the operational rules he's added in subsequent feedback
(always CC `security@apache.org`, require `@apache.org` addresses, attach threat-model drafts on request rather than by default).
