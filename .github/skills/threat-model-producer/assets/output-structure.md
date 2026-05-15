# Threat Model — Output Document Structure

> This file is the **structural template** that a produced threat
> model follows. It is referenced by
> [`../SKILL.md`](../SKILL.md) §4. Section numbers in this file
> (§1, §2, …) become the section numbers of the produced threat
> model — they are *independent* of the SKILL document's own
> section numbering.

Use these sections, in this order. Rename if the project has a strong
house style, but cover the same ground.

## §1 Header
- Project name, version/commit, date, author(s) of the threat model.
- **Version binding** — the threat model is versioned alongside the
  project (tagged with releases). A report against project version *N* is
  triaged against the model as it stood at *N*, not at HEAD.
- **Reporting cross-reference** — one line: findings that fall under §8
  (claimed properties) should be reported per the project's `SECURITY.md`
  / disclosure channel; findings that fall under §3 or §9 will be
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

## §2 Scope and intended use
- Primary intended use cases. Be concrete — "in-process compression of
  application data" beats "general compression library".
- Deployment contexts the project was designed for (in-process library? CLI
  tool? server? embedded? kernel?).
- Caller expectations: who is expected to call this, and at what trust level?
  For a **network service or daemon** (as opposed to an in-process
  library), there is rarely a single "caller" — typically the role
  splits into *client* (untrusted), *operator/admin* (trusted for the
  instance), and *peer* (authenticated but adversarial). Name each role
  here; they get separate rows in §6 and separate actors in §7.
- **Component-family table.** Carve the public surface into families with
  distinct threat profiles, one row each: family name, representative
  API/entry point, whether it touches anything outside the process
  (filesystem, network, env, child processes), and whether it is in or out
  of this model. This table does more orienting work than the surrounding
  prose; lead with it. Anything out of model here must reappear in §3
  with the reason.

## §3 Out of scope (explicit non-goals)
- Use cases the project does *not* aim to support. State them, even if they
  seem obvious — they are obvious to the maintainer, not to a new integrator.
- Threats the project does not attempt to defend against, with the reason
  ("not a security boundary", "out of layer", "unsolvable at this layer", etc.).
- **Code that ships in the repository but is not covered by the model.**
  `contrib/`, `examples/`, `vendor/`, `third_party/`, demo apps, generated
  bindings. State the policy explicitly ("unsupported, separately
  authored, threat-model separately") so integrators do not extend the
  core's guarantees to them by association.

## §4 Trust boundaries and data flow
- Where the trust boundary sits (e.g., "API surface is the boundary; all
  bytes inside the library are assumed already-authenticated").
- The path data takes through the project, expressed as the trust transitions
  it crosses. Skip this section if the project is purely computational with
  no meaningful trust transitions; say so.
- **Reachability preconditions per component.** For each component family
  in the §2 table, state the condition a finding must meet to matter:
  *"a finding in `inflate.c` is in-model only if reachable from the
  compressed input bytes; a finding in `deflate.c` is in-model only if
  reachable from a caller-supplied dictionary."* This is the test a
  triager applies to a static-analysis or AI-reported hit before anything
  else.

## §5 Assumptions about the environment
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

## §5a Build-time and configuration variants
List the compile-time defines, feature flags, build options, or runtime
configuration knobs that **change which security properties hold.** For
each: the default, the effect on the model, and whether the maintainers
discourage it. (Examples from the zlib trial: `ZLIB_INSECURE` removes
`gzprintf` overflow protection; `BUILDFIXED` / `DYNAMIC_CRC_TABLE` remove
thread safety on pre-C11 toolchains.) If no such knobs exist, say so.

This is not build hygiene (out of scope per the SKILL's §1) — it is the
recognition that "the project" is actually a family of binaries (or
deployment modes), and the threat model must say which member of the
family it describes.

**The insecure-default case.** When the *default* value of a knob is the
one that voids a §8 property (e.g., an auth gate that ships
`enabled = false`), the model is ambiguous until the maintainer rules:
either (a) the default *is* the supported production posture, in which
case a report against it is `VALID`; or (b) the default is a
dev-convenience and operators are documented as required to flip it, in
which case the report is `OUT-OF-MODEL: non-default-build` and the
requirement appears in §10. Do not guess — make this a **wave-1**
question (it reshapes §8, §10, §11a, and §13 simultaneously) and
record the maintainer's answer in this section's "Maintainer stance"
column.

## §6 Assumptions about inputs
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

## §7 Adversary model
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
  in the §8 "conditions" column and its complement ("≥ threshold
  Byzantine") in §3 as out of scope.

## §8 Security properties the project provides
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
  carries the honest-participant bound from §7, and the violation
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

## §9 Security properties the project does *not* provide
The companion to §8. State each plainly. Examples (project-dependent):
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

## §10 Downstream responsibilities
A short, action-oriented list of what the *user* of the project must do in
order for the assumptions in §5–§7 to hold. For a library, "user"
means the embedding application; for a service/daemon, it means the
**operator/deployer** (and, if SDKs ship, separately the SDK
integrator). Every §5a knob whose default the maintainer has
designated dev-only must reappear here as "set X before exposing the
service." This is not a how-to guide; it is a contract. ("Validate that input length fits the documented bounds
before calling X." "Do not expose the API surface directly to untrusted
network peers." "Re-key on a schedule appropriate to the data lifetime.")

## §11 Known misuse patterns
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

## §11a Known non-findings (recurring false positives)
The mirror of §11: patterns that scanners, fuzzers, AI analyzers, or
human reviewers repeatedly flag against this project that are **not**
bugs given the model. For each: what the tool reports, why it is safe
under the model (cite the §6 trust assumption or §8 invariant that
discharges it), and — where helpful — the suppression pattern.

Examples of the shape:
- "`strcpy` at `foo.c:NN` — length is bounded by the 4-byte header field
  parsed at `foo.c:MM`; per §8 the header is validated before this
  point."
- "Unchecked `malloc` return in `examples/` — out of scope per §3."
- "Integer overflow on `len * 2` — `len` is capped to 2^28 by the API
  contract per §6."

This section is the highest-leverage input for automated or AI-assisted
triage: it can be fed back verbatim as a suppression list or negative
prompt. Keep it current as new tools produce new noise.

## §12 Conditions that would change this model
List the kinds of changes that should trigger a revision: e.g., a new public
API, accepting a new input format, gaining a network surface, taking on a
new deployment context, a change in default for a §5a build knob, or a
shipped-but-unsupported component being promoted into core.

Also list **evidence that the model is incomplete** as a trigger: a
vulnerability report that cannot be cleanly routed to one of the §13
dispositions means the model has a gap, and the correct response is to
revise the model (add the property to §8 or §9), not to make an
ad-hoc call on the report. This keeps future maintainers from drifting
away from the model without realizing it.

## §13 Triage dispositions
Enumerate the **closed set of outcomes** a vulnerability report, tool
finding, or AI analysis can receive when judged against this model. Each
disposition cites the section that licenses it, so the triager's response
is "see threat model §X" rather than ad-hoc prose.

| Disposition | Meaning | Licensed by |
| --- | --- | --- |
| `VALID` | Violates a property the project claims, via an in-scope adversary and input. | §8, §6, §7 |
| `VALID-HARDENING` | No §8 property is violated, but the API makes a §11 misuse easy enough that the project elects to harden it. Reported privately; fixed at maintainer discretion; typically no CVE. | §11 |
| `OUT-OF-MODEL: trusted-input` | Requires attacker control of a parameter the model marks trusted. | §6 |
| `OUT-OF-MODEL: adversary-not-in-scope` | Requires an attacker capability the model excludes. | §7 |
| `OUT-OF-MODEL: unsupported-component` | Lands in `contrib/`, `examples/`, or other code placed out of scope. | §3 |
| `OUT-OF-MODEL: non-default-build` | Only manifests under a discouraged or non-default §5a flag. | §5a |
| `BY-DESIGN: property-disclaimed` | Concerns a property the project explicitly does not provide. | §9 |
| `KNOWN-NON-FINDING` | Matches a documented recurring false positive. | §11a |
| `MODEL-GAP` | Cannot be cleanly routed to any of the above. | triggers §12 |

Adapt the labels to house style, but keep the set closed and the
section citations intact. A finding that does not fit is not "other" —
it is `MODEL-GAP`, and the model gets revised.

## §14 Open questions for the maintainers
Required while any *(inferred)* tags remain; may be dropped once the model
is fully ratified. For each question:

- State the **proposed answer** alongside the question, so the maintainer
  can confirm, correct, or strike it rather than compose from scratch.
- Note which section of the model the answer will land in.
- Group into waves of 3–7 (per the SKILL's §3.2) so the maintainer can
  respond to one wave at a time.

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

## §15 Optional: machine-readable companion
Where triage will be automated or AI-assisted, emit a sidecar (e.g.
`threat-model.yaml`) alongside the prose document containing only the
triage-relevant facts in structured form:

- entry points → per-parameter trust level (from §6),
- component families → in/out of scope (from §2/§3),
- build flags → security-relevant? default? (from §5a),
- claimed properties → severity tier + violation symptom (from §8),
- disclaimed properties and false friends (from §9),
- known non-findings (from §11a),
- disposition labels (from §13).

The prose document remains canonical; the sidecar is a derived index for
tooling. Regenerate it whenever the prose changes.
