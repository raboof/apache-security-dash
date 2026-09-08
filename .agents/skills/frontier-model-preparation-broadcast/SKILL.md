---
name: frontier-model-preparation-broadcast
description: >-
  Draft a program-status update to the opted-in (Scan Requested = Yes) PMCs about where the Frontier Model Preparation scanning program stands —
  the Mythos 5 provisioning and that scans run in the sequence of submission,
  the criticality-sorted Scan Queue tab in the tracker,
  what each PMC can expect next,
  and a tailored nudge for PMCs that have not yet cleared pre-flight.
  One message per PMC on its existing [GLASSWING] thread,
  tailored by pipeline state.
  Output is email drafts for human review — never sends.
  Use when a Foundation-level program change (model/timeline/queue policy) needs to be communicated to the whole opted-in cohort at once.
---

# Frontier Model Preparation scan-broadcast SKILL

A **fan-out status-update** skill.
Where `frontier-model-preparation-response` answers one PMC's inbound question and `frontier-model-preparation-run` surveys state,
this skill **proactively informs the whole opted-in cohort** of a program-level change —
a model/timeline shift,
a queue-policy change,
a foundation-level announcement that affects what PMCs can expect.

The deliverable is a set of **per-PMC email drafts**,
one per in-flight PMC,
each a reply on that PMC's existing `[GLASSWING]` thread and **tailored to where that PMC sits in the pipeline**.
The operator reviews and sends; the skill never sends.

It exists because a flat all-PMC blast reads as spam (and has already drawn that complaint on the members' list),
while a per-thread, state-aware note reads as the status update each PMC actually wants:
*"here's what changed, here's specifically where you stand, here's what (if anything) you need to do."*

## When to invoke

- A **Foundation-level program change** lands that the opted-in PMCs need to hear:
  a model transition (e.g. Mythos Preview → Mythos 5),
  a deadline/window change,
  a change to how the queue is ordered or worked.
- Jarek says "tell the PMCs where we stand", "broadcast the status",
  "inform everyone waiting for the scan", "send the program update", or similar.
- After a VP-Sponsor-Relations / board update about the Anthropic relationship that changes PMC-facing expectations (timing, model, credits) —
  relay the PMC-relevant parts, not the board-internal detail.

**Skip** when:
- The change affects only one PMC — use `frontier-model-preparation-response`.
- There is no concrete change to communicate (don't manufacture a broadcast;
  PMCs awaiting results don't need a "still waiting" ping unless something actually moved).
- You are mid-survey — that's `frontier-model-preparation-run`;
  this skill drafts the outbound, it does not classify.

## Hard rules (do not skip)

1. **Target only the opted-in cohort.** Draft only for PMCs with `Scan Requested = Yes` on the tracker.
   **Never** blast all ~200 Foundation PMCs,
   and never email a PMC that has not opted in.
   The "unsolicited Anthropic marketing" complaint on members@ (Trevor Grant, 2026-06-09) is exactly what this rule prevents —
   this is a status update to people who asked to be in the program, not outreach.

2. **One message per PMC, on its own `[GLASSWING]` thread.** Reply on the existing request thread (so the whole engagement stays on one thread of record),
   not a fresh blast and not a single mega-To/BCC.
   The per-thread placement is what makes it a status update rather than a mailing.

3. **Tailor by pipeline state.** Each draft must reflect *that PMC's* actual state (Submitted / Ready / Pre-flight-or-blocked) —
   see the templates below.
   A submitted PMC must not be told to "finish your model";
   a blocked PMC must not be told "you're in the queue".
   Pull the state and the per-PMC outstanding items from the tracker row + thread (reuse `frontier-model-preparation-run`'s classification;
   do not re-derive a different one here).

4. **Honor opt-outs and sensitivities.** If a PMC (or a named member on the thread) has asked to stop receiving program mail, has resigned over it, or has explicitly declined,
   **do not draft for them** —
   surface them in the skipped list with the reason.
   When in doubt about a contentious thread,
   surface it for the operator rather than auto-drafting.

5. **Draft + confirm; never send.** Render every draft (To / CC / Subject / Body) for the operator.
   For a large cohort, batch by state group so the operator can approve a group at a time.
   Create the drafts via the operator's chosen draft backend (the oauth_curl `oauth-draft` tool per `.apache-magpie-overrides/user.md`);
   the operator sends from the mail client.
   Never call a send tool.

6. **Program-cost confidentiality (shared with `frontier-model-preparation-response` Hard Rule 5).** PMC-facing text must not disclose the program's cost mechanics (the $1M credit value, per-MTok pricing, seat/provisioning).
   **ASF Tooling (the runner), Anthropic, Mythos / Mythos 5, Claude Fable 5, the Frontier Model Preparation program name, Claude-for-OSS are all fine to name** —
   they are public (Anthropic's own announcement; Sally Khudairi's ai-discuss@ update).
   What's redacted is who runs the scan pipeline downstream of the Security team.
   Keep board-private detail (seat counts, credit mechanics, sponsor negotiations) out —
   relay only the PMC-relevant facts: model/timeline/queue.

7. **CC discipline** (same as `frontier-model-preparation-response` Hard Rule 2):
   To = primary contact;
   CC = backup contact,
   `private@<pmc>`,
   the PMC's verified `security_contact` from `whimsy-lookup pmc-security-info <pmc>`
   (its own `security@<pmc>` when registered, else `security@apache.org`),
   and **the ASF Tooling PMC private list (`private@tooling.apache.org`)** — always Cc'd (the Tooling team's channel for the scanning effort), unless already on the thread.
   No personal introduction is needed when Cc'ing the list.

## Procedure

### Step 1 — Settle the message content (the "what changed")

Before drafting,
write down the 2–4 PMC-relevant facts being communicated, sourced from the triggering announcement.
For the 2026-07 Mythos 5 provisioning update these were:

- The ASF runs scans internally on **Mythos 5**, via ASF Tooling.
  **Do not claim a "provisioned as of 2026-07-01, scanning is kicking off" state** — an earlier
  revision of this SKILL asserted exactly that and it was untrue. Per Dave Fisher (wave@, VP Tooling)
  on 2026-07-29, scans were **blocked for technical reasons** through July while the ASF migrated off
  AWS Bedrock to Anthropic 1P; wave@ declared the pause over on **2026-07-30** ("We are now unblocked").
  Any restart or scheduling announcement is **Tooling's to make, not ours**.
- **No deadline claim, and there is no cliff to nudge against.** Per Sally Khudairi (sk@, 2026-07-29,
  confidential): the order form is a **rolling monthly renewal with access through June 2027**. Treat any
  date-based urgency as unsourced unless the Tooling team states it. Never tell a PMC their scan must land
  "this cycle" or "before the window closes".
- **Ordering, stated precisely — these are two different things and only one is PMC-facing.**
  The **Scan Queue** tab is *sorted* by OSS Criticality Score; that is a tracker artefact we use internally
  to decide who to chase. **Scans are run by ASF Tooling in the sequence of submission**, and that — not
  criticality — is what goes in PMC-facing text. Saying "you're queued at your criticality rank" tells a
  PMC something we cannot stand behind and implies we control the running order. Use the `timing` canned
  response's wording verbatim.
- (Context, optional) Claude Fable 5 — the public "safe" model released the same week — ships safety classifiers that block security-research prompts,
  so it is deliberately not the model used for the scans.

These facts already live as reusable **canned responses** —
keep them in sync, don't fork the wording:

| Canned topic | Use for |
| --- | --- |
| `program-status` | the model/timeline transition paragraph |
| `timing` | how the queue is ordered + the Scan Queue tab link |
| `deadline` | the per-PMC nudge body for not-yet-ready PMCs |

The live Scan Queue tab (criticality-sorted, rebuilt by `build-status-tab`) is: `https://docs.google.com/spreadsheets/d/<tracker-id>/edit#gid=<scan-queue-gid>` (resolve the gid from the workbook; as of 2026-06-10 it is `986633862`).

### Step 2 — Classify the cohort

Run (or reuse from a fresh `frontier-model-preparation-run` sweep) the per-PMC pipeline state for every `Scan Requested = Yes` PMC.
Group into:

- **Submitted / awaiting ASF Tooling** (`Date scan requested` set) — in the queue; nothing owed by them.
- **Ready** (`Security model verified` set, not yet submitted) — cleared pre-flight; **not yet in the queue at all** (submission is what puts them in it, and it is operator-gated); nothing owed by them.
- **Pre-flight / blocked** (model not verified, or discoverability / scope / gate items outstanding) —
  owes specific items before it can enter the queue.

Pull, per PMC:
contacts, thread id, and (for the blocked group) the concrete outstanding items from the row/thread.

### Step 3 — Compose one tailored draft per PMC

Use the matching template (§ Templates).
Splice in the shared program-status + timing content (from the canned responses) and the per-PMC specifics.
**Replace every `<placeholder>` with the PMC's real value — never leave a `<…>` in a draft.**

### Step 4 — Render for approval, batched by group

Present the drafts grouped (Submitted / Ready / Blocked),
with a count and a one-line per-PMC summary, plus the skipped list (Hard Rule 4).
The operator approves a group (or edits), then the drafts are created.
Do not create drafts before the operator has seen the group.

### Step 5 — Create drafts + record

On approval, create each draft (oauth_curl backend) on the PMC's thread.
Note in the tracker `Notes` (via `frontier-model-preparation-update`) that a program-status update was drafted/sent,
so the next sweep doesn't re-broadcast.
Do not re-flag broadcast threads as `awaiting-us` —
a status update we sent is `awaiting-pmc` (or no-action for the submitted group).

## Templates

All three open the same way (the shared "what changed" paragraph) and then diverge on the per-PMC ask.
Keep the program-status wording aligned with the `program-status` canned response.

### Shared opener (all groups)

> Hi <Primary> — a quick status update on the Frontier Model Preparation scanning
> program; the timeline has shifted (in your favour) and we want
> everyone who's signed up kept in the loop.
>
> Good news: the ASF is now **provisioned on the upgraded Mythos 5
> model**, and the scanning is under way. Scans run in the sequence in
> which projects were submitted, so if your project's pre-flight items
> (threat model / merging the discoverability PR we opened) come
> together, that's the one thing between you and a place in that
> sequence. We'll keep you posted as your slot comes up.
>
> How scans are ordered: we work in **OSS Criticality Score order** —
> highest-criticality repositories first — from a single queue of
> everything that's passed pre-flight. The live queue is the "Scan
> Queue" tab in the tracker:
> https://docs.google.com/spreadsheets/d/<tracker-id>/edit#gid=<scan-queue-gid>

### Group A — Submitted (awaiting ASF Tooling)

> **Where you stand:** apache/<repo(s)> is submitted and sits in that
> queue in the sequence it was submitted — you're done on the prep
> side. Nothing
> is needed from you. When your scan runs, results come back to us for a
> sanity check and are forwarded verbatim to <recipients> on a fresh
> thread.
>
> Best, <signature>

### Group B — Ready (verified, not yet submitted)

> **Where you stand:** pre-flight is complete for apache/<repo(s)> —
> threat model verified and discoverable — so there is nothing
> outstanding on your side. We'll queue the scan on
> your go-ahead (we don't auto-submit); just reply when you're ready, or
> say the word and we'll line it up now.
>
> Best, <signature>

### Group C — Pre-flight / blocked (owes items)

> **Where you stand:** you're in the program, but apache/<repo(s)>
> isn't in the scan queue yet because it's waiting on a couple of things
> from your side:
>
> - <outstanding item 1 — real item from the row/thread>
> - <outstanding item 2>
>
> None of these are heavy — most PMCs clear them in a single reply.
> Finishing them is what puts your project *into* the criticality-sorted
> queue; scanning is under way now, and repos are scanned in the
> sequence of submission. The sooner they land, the sooner you're in
> line. If the PMC has
> decided to sit this one out, just say so and we'll take you off the
> active queue.
>
> Best, <signature>

(Group C is the `deadline` canned response reframed for the extended window;
keep the two in sync.)

## Cross-references

| Need | Skill / tool |
| --- | --- |
| Per-PMC state classification | `frontier-model-preparation-run` (sweep) |
| One-off reply to a PMC question | `frontier-model-preparation-response` |
| Reusable answer wording | Canned Responses tab (`program-status`, `timing`, `deadline`) via `frontier-model-preparation-update` |
| PMC `security_contact` (to Cc) | `whimsy-lookup pmc-security-info <pmc>` |
| Record the broadcast in the tracker | `frontier-model-preparation-update` (apply, `Notes`) |
| Draft creation (oauth backend) | `oauth-draft` (per `.apache-magpie-overrides/user.md`) |

## Style notes

- **One screen per draft.** A status update is short:
  the shared opener, the one tailored paragraph, a sign-off.
  Don't restate the whole program.
- **Lead with the good news.** "Scanning is under way" and "you're in the queue / you're done" are reassuring;
  open there, not with the model mechanics.
- **No false urgency, and no date claims at all.** Do not imply a cliff, and do not promise a window, cycle, or turnaround date —
  the nominal 1–31 July 2026 credit window has **not** closed, and its status is **ASF Tooling's to announce**, not ours to forecast.
  The lever is readiness + submission order, not a clock.
  If a PMC asks how long, say scans run in the sequence of submission and decline to give a date.
- **Never the cost mechanics.** Anthropic / Mythos / Frontier Model Preparation / ASF Tooling yes;
  the $1M / credit / seat cost mechanics never (Hard Rule 6).
