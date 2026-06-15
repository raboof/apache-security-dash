---
name: glasswing-scan-broadcast
description: >-
  Draft a program-status update to the opted-in (Scan Requested = Yes) PMCs about where the Glasswing scanning program stands —
  the Mythos Preview → Mythos 5 transition and the extended timeline,
  the criticality-sorted Scan Queue tab in the tracker,
  what each PMC can expect next,
  and a tailored nudge for PMCs that have not yet cleared pre-flight.
  One message per PMC on its existing [GLASSWING] thread,
  tailored by pipeline state.
  Output is email drafts for human review — never sends.
  Use when a Foundation-level program change (model/timeline/queue policy) needs to be communicated to the whole opted-in cohort at once.
---

# Glasswing scan-broadcast SKILL

A **fan-out status-update** skill.
Where `glasswing-scan-response` answers one PMC's inbound question and `glasswing-scan-run` surveys state,
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
- The change affects only one PMC — use `glasswing-scan-response`.
- There is no concrete change to communicate (don't manufacture a broadcast;
  PMCs awaiting results don't need a "still waiting" ping unless something actually moved).
- You are mid-survey — that's `glasswing-scan-run`;
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
   Pull the state and the per-PMC outstanding items from the tracker row + thread (reuse `glasswing-scan-run`'s classification;
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

6. **Vendor opacity (shared with `glasswing-scan-response` Hard Rule 5).** PMC-facing text must not name the scan-relay vendor (Alpha-Omega / its staff).
   **Anthropic, Mythos / Mythos 5, Claude Fable 5, the Glasswing program name, Claude-for-OSS are all fine to name** —
   they are public (Anthropic's own announcement; Sally Khudairi's ai-discuss@ update).
   What's redacted is who runs the scan pipeline downstream of the Security team.
   Keep board-private detail (seat counts, credit mechanics, sponsor negotiations) out —
   relay only the PMC-relevant facts: model/timeline/queue.

7. **CC discipline** (same as `glasswing-scan-response` Hard Rule 2):
   To = primary contact;
   CC = backup contact + `private@<pmc>` + `security@apache.org` + the `security@<pmc>` alias **only when `whimsy-lookup check-security-alias <pmc>` confirms it exists**.

## Procedure

### Step 1 — Settle the message content (the "what changed")

Before drafting,
write down the 2–4 PMC-relevant facts being communicated, sourced from the triggering announcement.
For the 2026-06-10 Mythos 5 broadcast these were:

- The program is moving from Mythos Preview onto the upgraded **Mythos 5** model (via Glasswing / Trusted Access);
  the ASF is still in the provisioning queue with its **spot and status retained**.
- The **30 June 2026 cut-off is being extended** once Mythos 5 onboarding completes —
  no longer a hard cliff.
- Scans run in **OSS Criticality Score order** from the **Scan Queue** tab;
  readiness + criticality rank (not a deadline) drive ordering.
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

Run (or reuse from a fresh `glasswing-scan-run` sweep) the per-PMC pipeline state for every `Scan Requested = Yes` PMC.
Group into:

- **Submitted / awaiting vendor** (`Date scan requested` set) — in the queue; nothing owed by them.
- **Ready** (`Security model verified` set, not yet submitted) — cleared pre-flight; queued at criticality rank; nothing owed.
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
Note in the tracker `Notes` (via `glasswing-scan-update`) that a program-status update was drafted/sent,
so the next sweep doesn't re-broadcast.
Do not re-flag broadcast threads as `awaiting-us` —
a status update we sent is `awaiting-pmc` (or no-action for the submitted group).

## Templates

All three open the same way (the shared "what changed" paragraph) and then diverge on the per-PMC ask.
Keep the program-status wording aligned with the `program-status` canned response.

### Shared opener (all groups)

> Hi <Primary> — a quick status update on the Glasswing scanning
> program; the timeline has shifted (in your favour) and we want
> everyone who's signed up kept in the loop.
>
> Anthropic has moved the program from the earlier "Mythos Preview"
> access onto the upgraded **Mythos 5** model. The ASF is still in the
> provisioning queue and has kept its spot and status — we shift from
> Mythos Preview to Mythos 5 once onboarding completes, with the same
> pool of usage credits. The upshot for you: **the original 30 June 2026
> cut-off is being extended**, so there's no longer a hard deadline to
> race. We'll confirm the new window once the paperwork lands.
>
> How scans are ordered: we work in **OSS Criticality Score order** —
> highest-criticality repositories first — from a single queue of
> everything that's passed pre-flight. The live queue is the "Scan
> Queue" tab in the tracker:
> https://docs.google.com/spreadsheets/d/<tracker-id>/edit#gid=<scan-queue-gid>

### Group A — Submitted (awaiting vendor)

> **Where you stand:** apache/<repo(s)> is submitted and sits in that
> queue at its criticality rank — you're done on the prep side. Nothing
> is needed from you. When your scan runs, results come back to us for a
> sanity check and are forwarded verbatim to <recipients> on a fresh
> thread.
>
> Best, <signature>

### Group B — Ready (verified, not yet submitted)

> **Where you stand:** pre-flight is complete for apache/<repo(s)> —
> threat model verified and discoverable — so you're queued at your
> criticality rank with nothing outstanding. We'll queue the scan on
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
> queue; with the deadline now being extended, it's readiness + rank
> (not a clock) that determines when you're scanned. The sooner they
> land, the sooner you're in line. If the PMC has decided to sit this one
> out, just say so and we'll take you off the active queue.
>
> Best, <signature>

(Group C is the `deadline` canned response reframed for the extended window;
keep the two in sync.)

## Cross-references

| Need | Skill / tool |
| --- | --- |
| Per-PMC state classification | `glasswing-scan-run` (sweep) |
| One-off reply to a PMC question | `glasswing-scan-response` |
| Reusable answer wording | Canned Responses tab (`program-status`, `timing`, `deadline`) via `glasswing-scan-update` |
| `security@<pmc>` alias check | `whimsy-lookup check-security-alias <pmc>` |
| Record the broadcast in the tracker | `glasswing-scan-update` (apply, `Notes`) |
| Draft creation (oauth backend) | `oauth-draft` (per `.apache-magpie-overrides/user.md`) |

## Style notes

- **One screen per draft.** A status update is short:
  the shared opener, the one tailored paragraph, a sign-off.
  Don't restate the whole program.
- **Lead with the good news.** The deadline extension and "you're in the queue / you're done" are reassuring;
  open there, not with the model mechanics.
- **No false urgency.** With the window extended, do not imply a cliff.
  The lever is readiness + criticality rank, not a clock.
- **Never the vendor.** Anthropic / Mythos / Glasswing yes;
  the scan relay vendor never (Hard Rule 6).
