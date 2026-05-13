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
  source for §4.8/§4.9/§4.11 and add a §4.14 meta question proposing how
  the two documents should coexist (replace / merge / sit alongside).
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

### Step 3.1a — Mine the existing SECURITY.md (or embedded threat model)

Many projects ship a `SECURITY.md` that is part disclosure process (how to
report, embargo policy, team roster — all out of scope per §1) and part
**embedded threat model** (what the project trusts, what counts as a
vulnerability, examples of non-vulnerabilities). The second part is the
single highest-authority *(documented)* source available: it is maintainer
policy that has already survived public review and, often, dispute with
reporters.

When such a section exists:

- **Do not re-derive it.** Every trust statement, vuln/non-vuln example,
  and resource threshold in the existing document is *(documented)*, not
  *(inferred)*. Lift it directly into the corresponding §4.x section with
  a citation. A producer who tags "the project trusts the code it is asked
  to run" as *(inferred)* when `SECURITY.md` already says so has not done
  the orient pass.
- **The output must be a strict superset.** Nothing the existing
  `SECURITY.md` asserts about scope may be silently dropped, weakened, or
  contradicted. If the producer believes an existing claim is wrong or
  stale, that is a §4.14 open question to the maintainer — not a
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

Write the threat model in the structure given in §4. Each section must
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
report ("not a bug — §4.9 disclaims this property"), the reporter will
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

Use these sections, in this order. Rename if the project has a strong house
style, but cover the same ground.

### 4.1 Header
- Project name, version/commit, date, author(s) of the threat model.
- **Version binding** — the threat model is versioned alongside the
  project (tagged with releases). A report against project version *N* is
  triaged against the model as it stood at *N*, not at HEAD.
- **Reporting cross-reference** — one line: findings that fall under §4.8
  (claimed properties) should be reported per the project's `SECURITY.md`
  / disclosure channel; findings that fall under §4.3 or §4.9 will be
  closed citing this document.
- **Status** — draft / under maintainer review / accepted, with the date.
- **Provenance legend** — a one-line key for the *(documented)* /
  *(maintainer)* / *(inferred)* tags used throughout.
- **Draft confidence** — a rough count of *(documented)* vs *(maintainer)*
  vs *(inferred)* claims (e.g., "29 documented / 0 maintainer / 30
  inferred"). This tells a reader at a glance how much of the model is
  still hypothesis. Update it as questions are resolved.
- One-paragraph description of the project's purpose, written for someone who
  has never seen it. This anchors everyone on what is being modeled.

### 4.2 Scope and intended use
- Primary intended use cases. Be concrete — "in-process compression of
  application data" beats "general compression library".
- Deployment contexts the project was designed for (in-process library? CLI
  tool? server? embedded? kernel?).
- Caller expectations: who is expected to call this, and at what trust level?
  For a **network service or daemon** (as opposed to an in-process
  library), there is rarely a single "caller" — typically the role
  splits into *client* (untrusted), *operator/admin* (trusted for the
  instance), and *peer* (authenticated but adversarial). Name each role
  here; they get separate rows in §4.6 and separate actors in §4.7.
- **Component-family table.** Carve the public surface into families with
  distinct threat profiles, one row each: family name, representative
  API/entry point, whether it touches anything outside the process
  (filesystem, network, env, child processes), and whether it is in or out
  of this model. This table does more orienting work than the surrounding
  prose; lead with it. Anything out of model here must reappear in §4.3
  with the reason.

### 4.3 Out of scope (explicit non-goals)
- Use cases the project does *not* aim to support. State them, even if they
  seem obvious — they are obvious to the maintainer, not to a new integrator.
- Threats the project does not attempt to defend against, with the reason
  ("not a security boundary", "out of layer", "unsolvable at this layer", etc.).
- **Code that ships in the repository but is not covered by the model.**
  `contrib/`, `examples/`, `vendor/`, `third_party/`, demo apps, generated
  bindings. State the policy explicitly ("unsupported, separately
  authored, threat-model separately") so integrators do not extend the
  core's guarantees to them by association.

### 4.4 Trust boundaries and data flow
- Where the trust boundary sits (e.g., "API surface is the boundary; all
  bytes inside the library are assumed already-authenticated").
- The path data takes through the project, expressed as the trust transitions
  it crosses. Skip this section if the project is purely computational with
  no meaningful trust transitions; say so.
- **Reachability preconditions per component.** For each component family
  in the §4.2 table, state the condition a finding must meet to matter:
  *"a finding in `inflate.c` is in-model only if reachable from the
  compressed input bytes; a finding in `deflate.c` is in-model only if
  reachable from a caller-supplied dictionary."* This is the test a
  triager applies to a static-analysis or AI-reported hit before anything
  else.

### 4.5 Assumptions about the environment
Cover, where applicable:
- Operating system, runtime, hardware assumptions.
- Concurrency assumptions (thread-safety guarantees, reentrancy, signal-safety).
- Memory model assumptions (allocator behavior, alignment, sizeof guarantees).
- Time/clock assumptions.
- Filesystem, network, or peripheral assumptions.
- **What the project does *not* do to its host.** This is the
  "no-surprise side effects" inventory: does it open sockets? spawn
  processes? install signal handlers? read environment variables? write
  to stdout/stderr? touch global locale or FPU state? mutate process-wide
  state? An integrator embedding the project into a larger system needs
  this list as much as the positive assumptions.

  Note that these are **negative claims** ("the project never does X"),
  which are rarely written down and almost impossible to cite — so this
  inventory will be predominantly *(inferred)* in any first draft. That
  makes it one of the **highest-priority confirmation targets**: put the
  corresponding question in wave 1 or wave 2, not later.

### 4.5a Build-time and configuration variants
List the compile-time defines, feature flags, build options, or runtime
configuration knobs that **change which security properties hold.** For
each: the default, the effect on the model, and whether the maintainers
discourage it. (Examples from the zlib trial: `ZLIB_INSECURE` removes
`gzprintf` overflow protection; `BUILDFIXED` / `DYNAMIC_CRC_TABLE` remove
thread safety on pre-C11 toolchains.) If no such knobs exist, say so.

This is not build hygiene (out of scope per §1) — it is the recognition
that "the project" is actually a family of binaries (or deployment
modes), and the threat model must say which member of the family it
describes.

**The insecure-default case.** When the *default* value of a knob is the
one that voids a §4.8 property (e.g., an auth gate that ships
`enabled = false`), the model is ambiguous until the maintainer rules:
either (a) the default *is* the supported production posture, in which
case a report against it is `VALID`; or (b) the default is a
dev-convenience and operators are documented as required to flip it, in
which case the report is `OUT-OF-MODEL: non-default-build` and the
requirement appears in §4.10. Do not guess — make this a **wave-1**
question (it reshapes §4.8, §4.10, §4.11a, and §4.13 simultaneously) and
record the maintainer's answer in this section's "Maintainer stance"
column.

### 4.6 Assumptions about inputs
- What inputs the project accepts and from where it expects them to come.
- **Per-parameter trust table.** For every public entry point that accepts
  external data, one row per parameter:

  | Function | Parameter | Attacker-controllable? | Caller must enforce |
  | --- | --- | --- | --- |
  | `gzopen` | `path` | no — trusted caller string | path sanitization |
  | `gzread` | file contents | **yes** | output buffer ≥ `len` |
  | `gzprintf` | `format` | no — trusted literal | never source from input |

  For a **network service**, the first column is the route/endpoint or
  protocol message (e.g., `POST /v1/configuration`, `Handshake` frame)
  rather than a function name, and rows should cover headers and
  connection metadata as well as bodies — header-presence checks
  (`X-Forwarded-*`, auth tokens) are common false friends.

  Prose ("file contents may be attacker-controlled; format strings may
  not") is not sufficient for triage: tool and AI findings are reported
  against specific sinks, and the triager needs to look up the exact
  parameter. Group rows by component family if the table grows large.
- Size, shape, and rate assumptions (bounded? streaming? memory-mapped?).

### 4.7 Adversary model
- Who is the assumed attacker? (Network peer? User of the embedding app?
  Local process? Co-tenant?)
- What capabilities does the attacker have, and what do they not have?
- What is the attacker assumed to be trying to do? (Crash the host? Read
  memory? Smuggle data? Cause CPU exhaustion? Simply send malformed input?)
- Which actors are explicitly *not* in the model? ("Attackers with control
  over the calling process are out of scope — they have already won.")
- For **distributed / replicated / consensus systems**, include the
  *authenticated-but-Byzantine participant* as a distinct actor: a peer
  who holds a legitimate identity, passes the handshake, and then
  behaves arbitrarily. State the honest-fraction threshold (e.g.,
  `< n/3`, `< ½ stake`) under which the model holds; put the threshold
  in the §4.8 "conditions" column and its complement ("≥ threshold
  Byzantine") in §4.3 as out of scope.

### 4.8 Security properties the project provides
For each property, state **four things**:

1. **The property** and the conditions under which it holds.
2. **Violation symptom** — what a break looks like in practice (crash,
   OOB read/write, information leak, hang, wrong output, unbounded
   allocation). This lets a triager map a fuzzer artifact or report
   symptom back to the property it violates.
3. **Severity tier** — whether a violation is security-critical (warrants
   a CVE / coordinated disclosure) or correctness-only (ordinary bug).
   "Memory safety on untrusted input" and "deterministic output" must not
   be presented with the same weight.
4. **Provenance tag**, as everywhere else.

Cover, where applicable:
- Memory/safety properties (no OOB reads/writes given size invariants from
  the API contract, etc.).
- Correctness properties (deterministic output, idempotency, round-trip
  fidelity).
- **Distributed-system properties** (safety, liveness, finality,
  ordering, replica consistency) where applicable. These are
  *network-wide* rather than single-process; the "conditions" field
  carries the honest-participant bound from §4.7, and the violation
  symptom is typically observable across nodes (fork, indefinite
  stall, divergent state hash) rather than on one host.
- Resource properties (bounded memory given bounded input, bounded CPU,
  no unbounded recursion). **State the threshold, not just the
  direction.** DoS reports are the most contested triage category;
  "bounded" is not actionable. Push the maintainer for a categorical or
  quantitative line — e.g., "super-linear in input size is a bug;
  constant-factor blowup is not", "a hang is a bug; slow is not", or "no
  resource guarantee is made at all". Whichever it is, write it down.
- Confidentiality / integrity / availability properties, if any.

A property only counts if the project has actually committed to it — either
in docs, in tests, or in maintainer statement. Do not invent properties.

### 4.9 Security properties the project does *not* provide
The companion to §4.8. State each plainly. Examples (project-dependent):
- "No constant-time guarantees; do not use for secret comparison."
- "Not safe against adversarially-crafted inputs designed to maximize
  CPU/memory cost (no compression-bomb defense)."
- "No authentication of input data; the caller must verify integrity before
  calling."
- "Not designed for use across a security boundary within a single process."

Within this section, **call out "false-friend" properties separately** —
features that *look like* a security property but are not one. The
canonical shape is "X is provided for purpose A; it is sometimes mistaken
for purpose B, which it does not satisfy." (Examples: a CRC that looks
like an integrity guarantee but is not a MAC; a non-cryptographic hash
that looks collision-resistant; a PRNG that looks like a CSPRNG; a
"sandbox" mode that isolates resources but not security.) These are the
single highest-value statements for a downstream integrator, because they
correct an assumption the integrator is likely to bring with them.

Also name **well-known attack classes against this category of project**
that the project itself cannot defend against and leaves to the caller
(e.g., compression-oracle attacks for compression libraries, XXE for XML
parsers, ReDoS for regex engines, billion-laughs for recursive-format
parsers). One sentence per class is enough; the point is to put the
integrator on notice, not to write a tutorial.

This is the most valuable section for a downstream integrator. Spend time
here.

### 4.10 Downstream responsibilities
A short, action-oriented list of what the *user* of the project must do in
order for the assumptions in §4.5–§4.7 to hold. For a library, "user"
means the embedding application; for a service/daemon, it means the
**operator/deployer** (and, if SDKs ship, separately the SDK
integrator). Every §4.5a knob whose default the maintainer has
designated dev-only must reappear here as "set X before exposing the
service." This is not a how-to guide; it is a contract. ("Validate that input length fits the documented bounds
before calling X." "Do not expose the API surface directly to untrusted
network peers." "Re-key on a schedule appropriate to the data lifetime.")

### 4.11 Known misuse patterns
Common ways the project is or has been misused, even though the API permits
them. Examples:
- Passing untrusted data to an interface intended for trusted data.
- Using the project as a security boundary when it is not one.
- Exceeding documented size or recursion limits.
- Mixing modes/contexts that the project does not synchronize.

**In a draft**, one-liners are acceptable — capture the inventory first.
**Before publishing**, expand each entry to *what the misuse looks like*,
*why it is unsafe*, *what to do instead*. No need to attribute or shame;
just describe.

### 4.11a Known non-findings (recurring false positives)
The mirror of §4.11: patterns that scanners, fuzzers, AI analyzers, or
human reviewers repeatedly flag against this project that are **not**
bugs given the model. For each: what the tool reports, why it is safe
under the model (cite the §4.6 trust assumption or §4.8 invariant that
discharges it), and — where helpful — the suppression pattern.

Examples of the shape:
- "`strcpy` at `foo.c:NN` — length is bounded by the 4-byte header field
  parsed at `foo.c:MM`; per §4.8 the header is validated before this
  point."
- "Unchecked `malloc` return in `examples/` — out of scope per §4.3."
- "Integer overflow on `len * 2` — `len` is capped to 2^28 by the API
  contract per §4.6."

This section is the highest-leverage input for automated or AI-assisted
triage: it can be fed back verbatim as a suppression list or negative
prompt. Keep it current as new tools produce new noise.

### 4.12 Conditions that would change this model
List the kinds of changes that should trigger a revision: e.g., a new public
API, accepting a new input format, gaining a network surface, taking on a
new deployment context, a change in default for a §4.5a build knob, or a
shipped-but-unsupported component being promoted into core.

Also list **evidence that the model is incomplete** as a trigger: a
vulnerability report that cannot be cleanly routed to one of the §4.13
dispositions means the model has a gap, and the correct response is to
revise the model (add the property to §4.8 or §4.9), not to make an
ad-hoc call on the report. This keeps future maintainers from drifting
away from the model without realizing it.

### 4.13 Triage dispositions
Enumerate the **closed set of outcomes** a vulnerability report, tool
finding, or AI analysis can receive when judged against this model. Each
disposition cites the section that licenses it, so the triager's response
is "see threat model §X" rather than ad-hoc prose.

| Disposition | Meaning | Licensed by |
| --- | --- | --- |
| `VALID` | Violates a property the project claims, via an in-scope adversary and input. | §4.8, §4.6, §4.7 |
| `VALID-HARDENING` | No §4.8 property is violated, but the API makes a §4.11 misuse easy enough that the project elects to harden it. Reported privately; fixed at maintainer discretion; typically no CVE. | §4.11 |
| `OUT-OF-MODEL: trusted-input` | Requires attacker control of a parameter the model marks trusted. | §4.6 |
| `OUT-OF-MODEL: adversary-not-in-scope` | Requires an attacker capability the model excludes. | §4.7 |
| `OUT-OF-MODEL: unsupported-component` | Lands in `contrib/`, `examples/`, or other code placed out of scope. | §4.3 |
| `OUT-OF-MODEL: non-default-build` | Only manifests under a discouraged or non-default §4.5a flag. | §4.5a |
| `BY-DESIGN: property-disclaimed` | Concerns a property the project explicitly does not provide. | §4.9 |
| `KNOWN-NON-FINDING` | Matches a documented recurring false positive. | §4.11a |
| `MODEL-GAP` | Cannot be cleanly routed to any of the above. | triggers §4.12 |

Adapt the labels to house style, but keep the set closed and the
section citations intact. A finding that does not fit is not "other" —
it is `MODEL-GAP`, and the model gets revised.

### 4.14 Open questions for the maintainers
Required while any *(inferred)* tags remain; may be dropped once the model
is fully ratified. For each question:

- State the **proposed answer** alongside the question, so the maintainer
  can confirm, correct, or strike it rather than compose from scratch.
- Note which section of the model the answer will land in.
- Group into waves of 3–7 (per §3.2) so the maintainer can respond to one
  wave at a time.

**Mapping rule.** The mapping is one-directional: every *(inferred)* tag
in the body **must** route to a question here. The reverse is not
required — it is legitimate to also include questions that:

- probe the **edge cases of a *(documented)* claim** (e.g., "the docs say
  the decoder never crashes on corrupted input — are there builds or
  platforms where you would not make that claim?"), or
- cover **meta concerns** with no body claim behind them (ownership of
  the document, revision policy, publication venue).

When a question is answered, promote the matching body tag(s) and delete
the question.

### 4.15 Optional: machine-readable companion
Where triage will be automated or AI-assisted, emit a sidecar (e.g.
`threat-model.yaml`) alongside the prose document containing only the
triage-relevant facts in structured form:

- entry points → per-parameter trust level (from §4.6),
- component families → in/out of scope (from §4.2/§4.3),
- build flags → security-relevant? default? (from §4.5a),
- claimed properties → severity tier + violation symptom (from §4.8),
- disclaimed properties and false friends (from §4.9),
- known non-findings (from §4.11a),
- disposition labels (from §4.13).

The prose document remains canonical; the sidecar is a derived index for
tooling. Regenerate it whenever the prose changes.

---

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
    why? (Feeds §4.11a.)

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
23a. For each §4.5a knob whose *default* is the less-secure value: is
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
- [ ] Every *(inferred)* tag has a matching open question in §4.14, and
      every open question states a proposed answer for the maintainer to
      confirm or correct. (Questions without an *(inferred)* backing —
      edge-case probes of documented claims, meta/ownership — are
      permitted.)
- [ ] If the project has distinct component families (core vs.
      OS-touching convenience layer vs. shipped-but-unsupported), each is
      modeled at its own trust level or explicitly placed out of scope.
- [ ] Build/configuration variants that change the security envelope are
      enumerated (§4.5a), or the section states there are none. For each
      knob whose *default* is the less-secure value, the maintainer's
      ruling (supported posture vs dev-only) is recorded.
- [ ] §4.9 (properties NOT provided) and §4.10 (downstream responsibilities)
      are at least as substantive as §4.8 (properties provided). If they
      aren't, the model is probably under-specified.
- [ ] §4.9 names at least the obvious "false-friend" properties and the
      well-known attack classes for this category of project.
- [ ] §4.6 contains a per-parameter trust table, not just prose.
- [ ] Every §4.8 property carries a violation symptom and a severity
      tier, and resource properties state a threshold.
- [ ] §4.11a (known non-findings) is populated or marked N/A with a
      reason.
- [ ] §4.13 enumerates the triage dispositions and each cites the
      section that licenses it.
- [ ] A reader who has never seen the project can answer: "what threats has
      the library taken responsibility for, and which have been left to me?"
- [ ] A triager handed an arbitrary finding — from a tool, a human, or
      an AI — can route it to exactly one §4.13 disposition, citing a
      section, without consulting the maintainer.
- [ ] The document fits comfortably in one sitting (typically 3–8 pages).
      Sprawl is a smell.

If any check fails, iterate before publishing.

---

## 9. Skill provenance

This SKILL is a verbatim import of Michael Scovetta's gist
[`scovetta/2dc9a0695c7cbcc32e23799e00d2ced3`](https://gist.github.com/scovetta/2dc9a0695c7cbcc32e23799e00d2ced3).
The original is the canonical source; this local copy is what the
agent runs against. When the upstream gist is updated, re-import to
keep this file in sync.
