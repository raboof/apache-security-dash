---
name: threat-model-producer
description: Produce an open-source project's threat model — the implicit contract between the project and downstream users (what's in scope, what's out, what's claimed, what's disclaimed). Use when a project needs a threat model for an automated security scan (e.g. Glasswing), to anchor vulnerability-report triage, or when a maintainer asks "what's our security model?". Source — Michael Scovetta's gist `https://gist.github.com/scovetta/2dc9a0695c7cbcc32e23799e00d2ced3`, imported verbatim and bound here as a reusable SKILL.
---

# THREAT MODEL — Skill for Producing Open-Source Project Threat Models

This document is an **instruction set for whoever is producing a threat
model** for an open-source project — a human reviewer, a coding assistant,
an automated tooling pipeline, or any combination. It is deliberately
agnostic to the producer: the procedure, questions, and output structure are
the same regardless of who or what is following them.

When asked to "produce a threat model for this project" (or similar), follow
the procedure below. The deliverable is a separate document (typically
`docs/threat-model.md` or similar) — *this* file is the recipe, not the
output.

The skill is intentionally generic. It is designed for any open-source
library or component, regardless of language or domain. Adapt the questions
and sections to fit; do not omit them silently.

---

## 1. What this threat model is — and is not

**It IS** a description of the *implicit contract* between the project and its
downstream users: the assumptions the project makes about its environment,
inputs, and callers; the security properties it tries to uphold; the
properties it explicitly does *not* uphold; and the misuses that, while
syntactically possible, fall outside the intended use of the project.

The document serves **two consumers**:

- The **downstream integrator**, who needs to know which threats the project
  has taken on and which are left to them.
- The **triager** — maintainer, security team, or automated pipeline — who
  must classify an inbound vulnerability report, static-analysis finding, or
  AI-generated analysis as *valid*, *out of model*, or *disclaimed by
  design*, and cite the section that justifies the call.

Write every section so that both consumers can use it without re-deriving
the reasoning.

**It IS NOT**:

- A vulnerability assessment, audit, or pentest report. Do not hunt for bugs.
  Do not enumerate CVE-style findings.
- A supply-chain or build-hygiene checklist. Whether GitHub Actions are pinned,
  whether releases are signed, whether dependencies are up to date, whether
  there is a `SECURITY.md` — none of that belongs here.
- A restatement of what the source code already says. If a reader can see the
  fact by skimming the code or reading the public API docs, it does not need
  to be in the threat model. The threat model captures the *unwritten*
  assumptions, not the written ones.
- A coding-standards or secure-coding guide.
- A list of every theoretical attack. Focus on the threats the project's
  design actually has an opinion about (whether by addressing them or by
  declining to address them).

If you find yourself writing "the project should..." or "we recommend...", stop —
that is audit output, not threat model output. The threat model describes the
project as it *is*, not as it should be.

---

## 2. The core question framework

Every section of the resulting threat model should answer one of four
questions:

1. **What does the project assume?** (Environment, callers, inputs, threat
   actors in and out of scope.)
2. **What does the project guarantee** *given those assumptions*? (Memory
   safety on valid input, deterministic output, bounded resource use, etc.)
3. **What does the project explicitly leave to the downstream user?** (Input
   validation at the trust boundary, transport security, key management, rate
   limiting, etc.)
4. **What known misuses or anti-patterns exist** that look reasonable but
   violate the assumptions in (1)?

A useful threat model lets a downstream integrator answer: *"If I drop this
into my system, which threats am I now responsible for, and which are the
responsibility of the library/project?"* — and lets a triager answer:
*"Given this report, is the violated property one the project claims, is
the attacker in the project's adversary model, and is the affected code in
scope?"*

---

## 3. Procedure

### Step 3.1 — Orient

Before asking any questions, do a *light* pass over the project to form
hypotheses:

- Read `README`, top-level docs, and any existing `SECURITY*`, `THREAT*`, or
  `docs/` content. If an existing document is *titled* "threat model" but
  is structurally an audit, risk register, or findings list (symptoms:
  likelihood×impact scoring, "recommended mitigations", owner/due-date
  columns), do not silently supersede it — mine it as a *(documented)*
  source for §8/§9/§11 and add a §14 meta question proposing how
  the two documents should coexist (replace / merge / sit alongside).
- **Read the project's website security page(s), not just the repo.**
  Many projects publish their security policy / threat model as HTML on
  their project site rather than as a `SECURITY.md` in the repo —
  for example
  [`cloudstack.apache.org/security/`](https://cloudstack.apache.org/security/).
  The fastest way to enumerate the relevant URLs across ASF projects
  is the cross-Foundation security index at
  [`security.apache.org/projects/`](https://security.apache.org/projects/),
  whose source of truth is
  [`apache/security-site/scripts/project-coordinates.json`](https://github.com/apache/security-site/blob/main/scripts/project-coordinates.json).
  Pull every URL that page lists for the target project and treat the
  contents as *(documented)* with the same weight as an in-repo
  `SECURITY.md` (see §3.1a). When the website and the repo disagree,
  the more recent one wins, but raise the discrepancy as a §14
  question rather than silently picking one.
- **Mine for maintainer positions already on the record.** The
  highest-yield sources are places where maintainers have already explained
  a design decision or declined to do something: `FAQ` files, header-file
  commentary, `NOTES`/`CAVEATS`/`LIMITATIONS` docs, issue-tracker
  closures labeled "wontfix" / "by design" / "not a bug", and changelog
  entries that explain *why* a behavior is the way it is. These often
  answer threat-model questions before they need to be asked.
- Identify the primary public API surface (entry points, exported symbols,
  CLI commands, network protocols, file formats consumed/produced).
- **Carve the project into component families** that may have different
  threat profiles. A single library often exposes a pure-computation core,
  a convenience layer that touches the OS (files, sockets, env vars), and
  one or more ancillary utilities. Model each at its own trust level rather
  than averaging them.
- **Identify code that ships but is not supported.** `contrib/`,
  `examples/`, `vendor/`, `third_party/`, `test/`, demo apps, generated bindings.
  Decide explicitly whether each is in or out of threat model.
- Identify the language(s), runtime(s), and obvious trust boundaries (process
  boundary, FFI boundary, network boundary, file-system boundary).
- Note what the project clearly *is not* (e.g., "this is a parser, not a
  network service" — that shapes the threat model).

This pass should take minutes, not hours. The goal is to ask informed
questions in the next step, not to produce findings.

### Step 3.1a — Mine the existing SECURITY.md or website security page

Many projects publish a security policy either as a `SECURITY.md` in
the repo **or** as a page on the project website (linked from
[`security.apache.org/projects/`](https://security.apache.org/projects/)
for ASF projects — see §3.1). Both forms count for the rules below;
"`SECURITY.md`" in the rest of this section is shorthand for "the
project's own security-policy artifact, wherever it lives". When a
project has both a repo file and a website page, treat the union as
the source-of-truth and raise any contradiction as a §14 question.

These artifacts are part disclosure process (how to report, embargo
policy, team roster — all out of scope per §1) and part **embedded
threat model** (what the project trusts, what counts as a
vulnerability, examples of non-vulnerabilities). The second part is the
single highest-authority *(documented)* source available: it is maintainer
policy that has already survived public review and, often, dispute with
reporters.

When such a section exists:

- **Do not re-derive it.** Every trust statement, vuln/non-vuln example,
  and resource threshold in the existing document is *(documented)*, not
  *(inferred)*. Lift it directly into the corresponding §x section with
  a citation. A producer who tags "the project trusts the code it is asked
  to run" as *(inferred)* when `SECURITY.md` already says so has not done
  the orient pass.
- **The output must be a strict superset.** Nothing the existing
  `SECURITY.md` asserts about scope may be silently dropped, weakened, or
  contradicted. If the producer believes an existing claim is wrong or
  stale, that is a §14 open question to the maintainer — not a
  unilateral edit.
- **Build a back-map.** Keep a short appendix in the draft —
  "`SECURITY.md` statement → threat-model §" — one row per claim. This
  proves coverage and lets maintainers diff the two documents when either
  changes. Drop the appendix from the published version only if the
  maintainer agrees the new threat model has become canonical.
- **Raise the coexistence question in wave 1.** The §3.1 rule about prior
  documents *titled* "threat model" also applies here: when `SECURITY.md`
  embeds threat-model content, ask whether the new document (a) replaces
  that section of `SECURITY.md`, (b) becomes the canonical model that
  `SECURITY.md` links to, or (c) sits alongside as an expansion. Two
  overlapping authorities let triagers cite whichever is convenient;
  resolve this before publishing.

The same applies to any other artifact that states maintainer security
policy in the project's own voice: a `docs/security-model.md`, a "Security
Considerations" section of an RFC the project implements, a bug-bounty
scope page, or a wiki page the issue tracker routinely cites when closing
reports. Treat each as *(documented)* and back-map it.

### Step 3.2 — Ask clarifying questions, in waves

Iteration is mandatory. There are two viable modes; choose based on
maintainer availability:

- **Interview-first.** Ask questions, then draft. Best when a maintainer is
  actively engaged and answers come back quickly.
- **Draft-first.** Write a v1 entirely from public artifacts (per §3.1),
  tag every claim with its provenance (see §3.3), and collect the
  unresolved questions in a dedicated "Open questions" section at the end
  of the draft. Hand the maintainer a document to *react to* rather than a
  questionnaire to fill in. Best when maintainer time is scarce or
  asynchronous. This is usually the more efficient mode.

Either way, do **not** dump every question at once; the maintainer will not
answer 30 questions in one go and the answers will be shallow if they do.
Ask in **waves of 3–7 questions**, prioritized by which answers most shape
the rest of the model.

The first wave should always cover **scope and intended use**, because
everything else depends on it. Subsequent waves drill into trust boundaries,
adversary model, and known misuses.

A reference question bank is in §6. Pull from it; do not read it verbatim.
Reword for the specific project.

**Frame each question as a proposed answer.** Maintainers respond faster
and more precisely to "we believe X — confirm or correct" than to an
open-ended "what is X?". Wherever the orient pass yielded a plausible
answer, state it as the working hypothesis and ask the maintainer to
ratify or override. Reserve genuinely open questions for cases where no
reasonable default exists. Example:

> *Instead of:* "What is the adversary model?"
> *Ask:* "We believe the only adversary in scope is whoever supplies the
> compressed input; in-process callers and side-channel observers are out
> of scope. Is that right, and is anything missing?"

After each wave:

- Record the answers (in the threat model draft, not just in chat).
- State which next-wave questions the answers unlock or render moot.
- Stop asking once the marginal value of another question is low — a good
  threat model is *finite*. Better a tight 3-page document than a sprawling
  20-page one.

### Step 3.3 — Draft

Write the threat model in the structure given in § Each section must
either contain substantive content or be explicitly marked
`Not applicable — <reason>`. Empty headings with no commentary are a smell.

**Provenance tagging.** Every non-trivial claim in the draft must carry one
of these inline tags so readers (and the next iteration) know how much
weight it carries:

| Tag | Meaning |
| --- | --- |
| *(documented)* | Stated in the project's own docs (README, header comments, FAQ, manpage). Cite the source. |
| *(maintainer)* | Stated by a maintainer in response to a question from this process. |
| *(inferred)*   | Reasoned from code structure, absence of a feature, or general domain knowledge — not yet confirmed. Must have a matching entry in the open-questions section. |

Use exactly these three tags. **Do not invent hedge-tags** such as
"*(implicit)*", "*(documented in purpose)*", or "*(generally known)*" —
they leak uncertainty without making it actionable. If a claim is not
clearly *(documented)* or *(maintainer)*, it is *(inferred)* and gets an
open question.

A draft with no *(inferred)* tags has either been fully reviewed or is
overclaiming; a draft that is mostly *(inferred)* is not ready to publish.
As maintainer answers come in, promote *(inferred)* → *(maintainer)* and
retire the corresponding open question.

**Retain provenance in the published version.** Do not strip tags once the
model is accepted. When the document is used to close a vulnerability
report ("not a bug — §9 disclaims this property"), the reporter will
push back, and *(maintainer, 2025-03)* is a defensible citation where bare
prose is not. Convert tags to footnotes if the house style prefers, but
keep the chain of authority intact.

**Style rules for the output:**

- Plain prose and short bulleted lists. Tables are fine when every cell is
  meaningful (e.g., a trust-transition table or an input-trust matrix);
  avoid templated tables with empty cells.
- When a property is *not* guaranteed, say so plainly. "Constant-time
  comparison is not provided" is more useful than silence.
- Do not hedge into uselessness. "May or may not be safe depending on usage"
  tells the reader nothing. If you cannot get a clear answer, name the
  ambiguity as the finding.

### Step 3.4 — Iterate

Present the draft to the maintainer. Solicit corrections and new threats
they think of *while reading*. Update. Repeat until the maintainer signs off
or the marginal change rate falls to near zero.

Treat the threat model as a living document: note in its header the date,
the project version/commit it was written against, and what *kind* of change
should trigger a revision (new public API, new input format, new deployment
mode — not internal refactors).

---

## 4. Structure of the output document

The structural template a produced threat model follows is in a
separate file: [](assets/output-structure.md).
It defines §1 through §15 of the **output document** — independently
numbered, so the produced threat model does not inherit "§X"
artifacts from this SKILL's own document numbering.

When citing the output structure from this SKILL or sibling SKILLs,
write **§N of the output structure** (or just §N where unambiguous in
context) — never §N. The §N notation in the git history (pre-2026-05-15)
referred to the same content when it was still inline; the move was
prompted by [a review comment from Piotr Karwasz on apache/security#50](https://github.com/apache/security/pull/50)
pointing out that the inline numbering was bleeding into produced
threat models.

The mirrored public gist (see §10) holds both  and
 as separate files.

## 5. What to leave out (recurring temptations)

- **CVE history.** Past bugs are not the threat model. (A *pattern* across
  past bugs may be — e.g., "historically the project has had bugs around
  integer overflow on 32-bit systems, so the assumption that `size_t` does
  not wrap is load-bearing." That is a model claim, not a CVE list.)
- **Code-level findings.** "Function X does not check the return value of Y"
  is a code review finding. Out of scope.
- **Build / release / SDLC hygiene.** Action pinning, signing, reproducible
  builds, branch protection, 2FA — all important, none belong here.
- **Things the README already says.** Do not paraphrase the project tagline
  back at the reader.
- **Generic platitudes.** "Use defense in depth." "Keep dependencies up to
  date." Cut these on sight.
- **Speculation about future features.** Model what exists.

---

## 6. Reference question bank

Pull from these in waves. Reword for the specific project. The first wave
should be drawn from §6.1.

### 6.1 Scope and intended use (ask first)
1. Who is the intended caller of this project, and at what trust level do you
   assume they operate?
2. What deployment shapes did you have in mind when designing it
   (in-process library, CLI, daemon, embedded, etc.)?
3. What use cases do you consider clearly *out of scope* — uses people
   sometimes attempt that you do not support?
4. Is there a security boundary inside the project, or is the entire API
   surface the boundary?

### 6.2 Inputs and trust
5. Of the inputs accepted by the public API, which do you assume are
   attacker-controllable, and which do you assume are trusted?
6. Are there documented or undocumented size/shape/rate limits on inputs
   beyond which behavior is undefined or degraded?
7. Does any input flow into resource allocation (memory, threads, file
   handles) in a way whose magnitude is controlled by the input?

### 6.3 Adversary model
8. Who is the adversary you most cared about when designing this? Who is
   explicitly out of scope?
9. What capabilities does the assumed adversary have — can they observe
   timing? Memory? Influence inputs? Inject inputs? Cause restarts?
10. Are there adversaries sometimes assumed by users that you do *not* defend
    against (e.g., side-channel adversaries, co-tenant adversaries, malicious
    callers)?

### 6.4 Properties the project tries to uphold
11. What properties do you believe the project provides given valid input,
    and where are those properties documented or tested?
12. Are any of those properties only conditional (e.g., only on certain
    platforms, only when certain features are compiled in)?
12a. Where is the line on resource consumption — is super-linear CPU or
    memory in input size a bug? Is a hang on pathological input a bug?
    Or do you make no resource guarantee at all?

### 6.5 Properties the project does *not* uphold
13. What security properties have you deliberately decided are *not* this
    project's job?
14. Are there functions that look general-purpose but are unsafe for a
    particular use (e.g., comparison functions that are not constant-time,
    RNG that is not cryptographic, hash that is not collision-resistant)?

### 6.6 Misuse and downstream responsibility
15. What is the most common way you have seen this project misused?
16. What single thing do you wish every integrator did before calling the
    API, that they often do not?
17. Are there configurations or modes that should never be combined?
18. Does the project expose anything that *looks like* a security
    primitive but is not one (a checksum mistaken for a MAC, a hash
    mistaken for collision-resistant, a PRNG mistaken for a CSPRNG, a
    sandbox mistaken for an isolation boundary)?
18a. What do scanners, fuzzers, or security researchers most often
    report against this project that you consider a non-finding, and
    why? (Feeds §11a.)

### 6.7 Environmental assumptions
19. What does the project assume about its host (OS, allocator, threading,
    signal handling, byte order, integer width)?
20. Are there platforms that are nominally supported but not really first
    class for security purposes?
21. What does the project *refrain* from doing to its host — no signal
    handlers, no spawning, no sockets, no env-var reads, no global state?
    Which of these are deliberate guarantees vs. incidental?

### 6.8 Build and configuration variants
22. Which compile-time defines, feature flags, or runtime configuration
    knobs change the security envelope? What is the default for each, and
    which do you actively discourage?
23. Is there code shipped in the repository (`contrib/`, `examples/`,
    bindings, demos) that you do not consider part of the project for
    security purposes?
23a. For each §5a knob whose *default* is the less-secure value: is
    that default the supported production posture (so a report against
    it is `VALID`), or a dev-convenience that operators are expected to
    flip (so it is `OUT-OF-MODEL: non-default-build`)?

### 6.9 Stability and revision
24. What kind of change to the project would invalidate the answers you have
    just given?

---

## 7. Worked sketch (using zlib as a sounding board)

A few illustrative entries — *not* a complete threat model, just the flavor.
A real run would go deeper and would be driven by maintainer answers, not by
the producer's guesses. (When using this skill against a real project, do
not fabricate maintainer positions; ask.)

- **Intended use** — In-process DEFLATE/gzip/zlib (de)compression invoked by
  a host application. Not a network service; not a sandbox.
- **Trust boundary** — The API surface. Once data is inside the library, it
  is treated as authenticated by virtue of the caller having presented it.
  Authentication of compressed data (e.g., HMAC) is the caller's problem.
- **Adversary out of scope** — A caller already running in the host process.
  Such a caller has trivially full control and is not a meaningful adversary
  to model at this layer.
- **Property provided (conditional)** — Memory safety for well-formed,
  size-bounded inputs and correctly-initialized streams, on supported
  platforms with a conformant C runtime.
- **Property not provided** — No defense against adversarially constructed
  inputs that maximize CPU/memory cost (a.k.a. "decompression bombs"). The
  caller is responsible for capping the output size or wall-clock budget.
- **Downstream responsibility** — Bounding decompressed-output size; not
  feeding `gz*` file APIs filenames sourced from untrusted users without
  sanitization (path is interpreted by the OS, not the library).
- **Known misuse** — Treating the gzip CRC as an integrity guarantee against
  a malicious sender. CRC-32 is an error-detection code, not a MAC.

These bullets are deliberately the kind of thing **not** visible from
reading `inflate.c`. They are statements about *contract*, not *code*.

---

## 8. Self-check before finalizing

Before declaring the threat model done, verify:

- [ ] Every section is either substantive or marked N/A with a reason.
- [ ] No bullet would be more at home in a code review or audit report.
- [ ] No bullet restates what the README/API docs already say.
- [ ] Every non-trivial claim carries a *(documented)* / *(maintainer)* /
      *(inferred)* tag, the header explains the legend, and **no hedge-tag
      variants** ("implicit", "documented in purpose", "generally known")
      have crept in.
- [ ] The header reports a draft-confidence count (documented /
      maintainer / inferred).
- [ ] Every *(inferred)* tag has a matching open question in §14, and
      every open question states a proposed answer for the maintainer to
      confirm or correct. (Questions without an *(inferred)* backing —
      edge-case probes of documented claims, meta/ownership — are
      permitted.)
- [ ] If the project has distinct component families (core vs.
      OS-touching convenience layer vs. shipped-but-unsupported), each is
      modeled at its own trust level or explicitly placed out of scope.
- [ ] Build/configuration variants that change the security envelope are
      enumerated (§5a), or the section states there are none. For each
      knob whose *default* is the less-secure value, the maintainer's
      ruling (supported posture vs dev-only) is recorded.
- [ ] §9 (properties NOT provided) and §10 (downstream responsibilities)
      are at least as substantive as §8 (properties provided). If they
      aren't, the model is probably under-specified.
- [ ] §9 names at least the obvious "false-friend" properties and the
      well-known attack classes for this category of project.
- [ ] §6 contains a per-parameter trust table, not just prose.
- [ ] Every §8 property carries a violation symptom and a severity
      tier, and resource properties state a threshold.
- [ ] §11a (known non-findings) is populated or marked N/A with a
      reason.
- [ ] §13 enumerates the triage dispositions and each cites the
      section that licenses it.
- [ ] A reader who has never seen the project can answer: "what threats has
      the library taken responsibility for, and which have been left to me?"
- [ ] A triager handed an arbitrary finding — from a tool, a human, or
      an AI — can route it to exactly one §13 disposition, citing a
      section, without consulting the maintainer.
- [ ] The document fits comfortably in one sitting (typically 3–8 pages).
      Sprawl is a smell.

If any check fails, iterate before publishing.

---

## 9. Skill provenance

This SKILL is a verbatim import of Michael Scovetta's gist
[`scovetta/2dc9a0695c7cbcc32e23799e00d2ced3`](https://gist.github.com/scovetta/2dc9a0695c7cbcc32e23799e00d2ced3),
with `§3.1a` updates and the website-security-pages section from
PR-review feedback (see commits `fa6afe5` and later in
`apache/security`). The original is the upstream rubric; this local
copy is what the Security team's agents run against. When the
upstream gist is updated, re-import to keep this file in sync.

## 10. Public mirror

`apache/security` is a **private** repo. The Security team's
outbound emails to PMCs (drafted by `frontier-model-preparation-response`,
`frontier-model-preparation-model-verify`, `frontier-model-preparation-forward`,
`frontier-model-preparation-submit`) routinely link to this SKILL as the
rubric a PMC's threat model should hit. A private-repo URL
would 404 for the recipient.

The canonical **public** mirror lives at:

> <https://gist.github.com/potiuk/da14a826283038ddfe38cc9fe6310573>

Outbound SKILL references in PMC-facing email templates (this
SKILL and the others) use that URL, not the in-repo path.
Internal docs (this repo, the README, the helper script
comments) can still link to the in-repo file.

### Keeping the mirror in sync

When this SKILL is edited in `apache/security`, the gist must
be updated to match. The gist holds **two** files —
`SKILL.md` and `assets/output-structure.md` — and both must
be synced together when either changes:

```
gh gist edit da14a826283038ddfe38cc9fe6310573 \
    .github/skills/threat-model-producer/SKILL.md
gh gist edit da14a826283038ddfe38cc9fe6310573 \
    -a .github/skills/threat-model-producer/assets/output-structure.md
```

(Run from the repo root. The first command replaces the
gist's `SKILL.md`; the second `-a` adds — or, if it already
exists, updates — `output-structure.md`. Both files are
needed: `SKILL.md` §4 references `output-structure.md` and
the outbound URL recipients need access to both.)

A `git push` to `apache/security` does **not** propagate to
the gist — the sync is manual on purpose, so a half-finished
edit doesn't immediately leak. After every PR that touches
this file merges into `apache/security`'s default branch, the
maintainer running the merge also pushes the new content to
the gist via the command above.

If the gist URL ever needs to be rotated (lost access, etc.):
update this section and grep the rest of the repo for the
old gist ID — the SKILLs that link the rubric externally
need their URLs updated too.
