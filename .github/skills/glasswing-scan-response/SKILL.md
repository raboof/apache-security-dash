---
name: glasswing-scan-response
description: Draft a reply to a PMC member or contributor asking about the ASF Security team's Glasswing scan offer — what model it uses, what threat-model framework is expected, how it compares to other scanners, how to get scanned. Use whenever someone replies to (or directly asks about) Jarek's "[IMPORTANT][SECURITY] Possibility of running your project through Glasswing security scan" announcement, or otherwise asks for the scan. Output is an email draft for human review — never sends. Bundles a companion threat-model producer to attach to the response when one is needed.
---

# Glasswing scan-response SKILL

This SKILL answers inquiries about the ASF Security team's Glasswing
scan offer — *not* the scan itself. The deliverable is a draft email
reply that the human (Jarek, or another Security-team member) reviews
and sends. The SKILL never sends mail directly.

## When to invoke

- A PMC member or contributor replies to the "[IMPORTANT][SECURITY]
  Possibility of running your project through Glasswing security scan"
  announcement (or its descendants) with questions, concerns, or
  scoping discussion.
- A PMC member writes in (e.g. to `security@apache.org` or directly to
  a Security-team member) asking about the scan.
- A reviewer asks "what threat-model framework do you expect?" or "how
  does this compare to GitHub code scanning / Snyk / Dependabot / …"
  in any related thread.

## Hard rules (do not skip)

1. **All Glasswing communication must come from an apache.org-rooted
   identity.** That means **either** a personal `@apache.org`
   address **or** a project-level alias such as
   `security@<pmc>.apache.org` / `private@<pmc>.apache.org` whose
   subscriber list is the PMC. Both are acceptable: the personal
   `@apache.org` ties the message to a named PMC member; the
   `security@<pmc>` alias ties it to the PMC's collective security
   identity (and the team behind the alias has already been
   verified by the PMC). Either form is sufficient to anchor
   PMC-membership verification.

   If the question came from **neither** — a personal Gmail, an
   employer address, a non-Apache forum etc. — the reply must (a)
   answer the substantive questions and (b) politely ask the
   person to continue the conversation from either form going
   forward. Wording: *"either your personal `@apache.org` or your
   project's `security@<project>.apache.org` alias is fine"* —
   that preempts the back-and-forth where the person asks which
   one we want.

2. **Always CC `security@apache.org` on the reply, and CC the
   project's own `security@<pmc>.apache.org` alias when one
   exists.** The Foundation-level CC keeps the Security team's
   audit trail; the per-project CC makes sure the PMC's collective
   security team sees the thread regardless of which individual
   reached out. Look up whether a project has a `security@<pmc>`
   alias via
   [`security.apache.org/projects/`](https://security.apache.org/projects/)
   or its source-of-truth JSON at
   [`apache/security-site/scripts/project-coordinates.json`](https://github.com/apache/security-site/blob/main/scripts/project-coordinates.json) —
   not every project has one, in which case fall back to the
   project's `private@<pmc>.apache.org` list.

   If the original thread was on a project's
   `private@<pmc>.apache.org` list, keep that list on To/CC
   (don't quietly drop it). CC is enough; do not move the
   substantive discussion to `security@apache.org` unless the
   requester does.

3. **Confirm before sending.** Per the user's "draft and show first"
   rule, always render the full draft (subject, To, CC, body, any
   attachments) and wait for explicit approval. The user invokes the
   send.

4. **Never reveal contents of `private@<pmc>` or `security@`
   correspondence to anyone outside the trust boundary** — the reply
   should not quote excerpts from other PMCs' private discussions, even
   if the requester is also on those lists. Keep references abstract
   ("other PMCs have asked similar questions" — never names).

## Standard answer fragments

These are the canonical answers to the recurring questions. Pull from
them; reword for the specific thread.

### "What scanning model / framework are you using?"

The scan uses the latest Glasswing-available security models — the
operational profile is whichever model Glasswing has currently
designated as production for code-level vulnerability scanning. The
Glasswing project announcement is here:
<https://glasswing.openai.com> (linked from
<https://openai.com/index/glasswing-grant-program/>; cross-check the
canonical URL for the announcement at draft time — the gist of the
program changes more slowly than the model lineup).

If the requester wants the specific model name for the run on *their*
repo, point at the eventual scan-result markdown — it includes the
model identifier as a header field. Don't pin a specific model in the
reply unless the user has explicitly told you to.

### "What threat-modeling framework do you expect — STRIDE / LINDDUN /
PASTA / something else?"

No specific framework. The scan accepts any *human-readable* threat
model that:

- describes what the project considers a security issue and what it
  does not,
- names the user roles and trust boundaries the project assumes,
- says what's in scope for the scan and what's out (e.g. `contrib/`,
  `examples/`, demo apps),
- includes the recurring false-positives the project already knows
  about, so the scan does not re-discover them.

For projects that **don't** already have such a model, or want to update
the one they have before the scan, the ASF Security team will run the
`threat-model-producer` SKILL (Michael Scovetta's recipe, imported
verbatim at
<https://gist.github.com/scovetta/2dc9a0695c7cbcc32e23799e00d2ced3>)
against the project's public artifacts using Claude Opus 4.7. The
output is a draft `THREAT-MODEL.md` that:

- is itself human-readable (it explains what a "good threat model from
  the agentic-scan point of view" looks like, and produces a document
  in that shape),
- tags every claim with provenance — *(documented)* if it comes from
  the project's own docs, *(inferred)* if the agent guessed,
  *(maintainer)* if the PMC has explicitly ratified it,
- collects every *(inferred)* claim into an "Open questions for the
  maintainers" section so the PMC can react to a draft rather than
  fill in a blank form,
- ships alongside an `AGENTS.md` linking to it (the marker the scan
  uses to find the model).

The Security team submits the draft as a PR to the project's repo for
the PMC to review and merge. The scan is gated on the PR being merged
(or the PMC supplying their own equivalent). The PMC owns the
document; the Security team just bootstraps it.

### "How does this compare to GitHub code scanning / Snyk / Dependabot
/ other tools?"

Complementary, not a replacement:

- **GitHub code scanning** (CodeQL) does taint-tracking and pattern
  matching against the source. It's fast, runs per PR, and is great
  at well-known sink/source patterns.
- **SCA tools** (Dependabot, Snyk OSS) look at dependency manifests
  against vulnerability databases.
- **Glasswing-style agentic scans** read the code with much more
  semantic understanding — including configuration-driven behaviour,
  cross-file flows that defy static taint analysis, and project-
  specific misuse patterns that no signature would catch. They cost
  more per finding but reach places the cheaper tools miss.

The scan does not replace any of the above. PMCs that already run
CodeQL etc. should keep doing so; the Glasswing run is an *additional*
pass aimed at the long-tail of semantic-flow issues. If the requester
is asking because they're worried about duplicating effort: it is
fine and expected to see overlap with CodeQL findings — those are
re-confirmation, not waste.

(Refs that may come up: the asfyaml CodeQL discussion at
<https://github.com/apache/infrastructure-asfyaml/issues/94>.)

### "Can the model swallow the whole monorepo?"

Yes for most projects. For monorepo-scale codebases (Lucene + Solr +
Tika scale, or Airflow scale) the run is chunked by directory tree or
by component; the chunking is invisible to the PMC. If the project
has a clean modular layout (top-level dirs are coherent components),
mention that the modular layout makes chunking deterministic. If it
doesn't, mention that we'll work out the chunking with the PMC
contacts before kickoff.

### "What does a finding look like?"

A single markdown file with multiple findings, one section per issue,
each tagged with: file & line refs, the security property violated
(citing the project's threat model when one exists), reproducer
sketch where feasible, and a severity hint. The Security team
pre-reviews to filter slop before forwarding. The PMC then triages
through its normal process — the `private@<pmc>.apache.org` →
`security@<project>.apache.org` → coordinated disclosure / CVE /
release flow.

### "We'd like to opt in — what do we do?"

Point at the announcement's instructions: send a new message (not a
reply) from a `@apache.org` address to `security@apache.org`, CC
`private@<pmc>.apache.org`, with the subject
`[GLASSWING] <PMC>: request to scan repositories`, and include:

- confirmation of interest (PMC name, one message per PMC),
- primary + backup PMC contacts (names, `@apache.org` addresses),
- `@apache.org` email addresses to send scan results to,
- links to the GitHub repos to scan.

Verify the requester is on the PMC roster before queuing. Past abuse
exists where non-members tried to get scans against projects they
weren't part of; we say "no" to those.

## Procedure for drafting the reply

1. **Identify the requester's PMC.** Look at where their reply landed
   (`private@<pmc>.apache.org` on To/CC is the strongest signal). If
   ambiguous, ask the user which PMC.

2. **Identify the sender address.** If it's not `@apache.org`, the
   reply must include the "please continue from your `@apache.org`
   address" note at the top, politely but explicitly.

3. **Pull out their questions.** Quote each one verbatim from their
   message (use `> ` blockquote). Address each in order with the
   matching fragment from above, lightly reworded for the thread's
   register.

4. **Decide whether a threat-model draft is needed in this reply.**
   - If the requester is asking process / framework questions only
     (the typical first round), the reply contains *no* attached
     model — answer in prose and offer the threat-model-producer
     SKILL as the next step if they want it.
   - If the user explicitly says "attach the draft", run
     `threat-model-producer` against the relevant repository and
     attach the generated markdown (inline, fenced, or as a follow-up
     PR link). The draft is **what** the reply attaches; the SKILL
     itself is not attached.

5. **Render the full draft for review.** Show:
   - To / CC / Subject (with `[GLASSWING]` or `Re:` as appropriate),
   - body in plain text (no markdown rendering quirks),
   - any attachments by path or inline content,
   - reply-to message id (so Gmail threading lands correctly).

   Wait for the user to say "send" / "post" / "go ahead" / similar.
   Do not invoke `mcp__claude_ai_Gmail__create_draft` before approval.

6. **On approval**, create a Gmail draft via
   `mcp__claude_ai_Gmail__create_draft` (per user preference —
   `oauth-draft-create` is the fallback). Do not call `send`
   directly — the user reviews the draft once more in the Gmail UI
   and presses send.

## Style notes

- Plain prose. No marketing language ("cutting-edge AI", "next-
  generation"). The audience is Apache committers who can smell that
  from a mile away.
- Concise. Reply length should be proportional to the question's
  size; a one-line question gets a paragraph or two, not three pages.
- Be honest about overlap with other tools (the "complementary, not
  replacement" framing). PMCs respect that more than over-claiming.
- When you don't know the answer to a project-specific question
  (e.g. "will this miss our X-Y-Z framework's flow analysis?"), say
  so and offer to find out, rather than guessing.
- The reply is from the ASF Security team's voice, signed by the
  human; don't sign it as the agent.

## Examples of bad drafts (avoid)

- A reply that quotes the original announcement back at the
  requester. They sent it; they don't need it back.
- A reply that drops `private@<pmc>` from the recipient list and
  silently moves to `security@`. The original list owns the thread.
- A reply that includes a full threat-model draft when the requester
  hasn't asked for one yet — overkill on round 1.
- A reply that promises the scan "in the next two weeks" or similar.
  Don't commit to a timeline; the Security team coordinates queue.
- A reply that lists which other PMCs have signed up. PMC-list
  membership is between each PMC and the Security team.

## Provenance

This SKILL captures the response patterns Jarek has been using in
replies to the May 2026 Glasswing scan announcement, plus the
operational rules he's added in subsequent feedback (always CC
`security@apache.org`, require `@apache.org` addresses, attach
threat-model drafts on request rather than by default).
